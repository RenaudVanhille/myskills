# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Revue d'une architecture logicielle ou solution décrite en JSON, à la manière d'ATAM.

Le modèle écrit la description (composants, flux, couches, scénarios de
qualité évalués, risques, points de sensibilité, compromis, décisions) ou
reprend une option d'architecture-options (`source`). Le script, et non le
modèle :
- vérifie toutes les références (composants, exigences, scénarios, décisions) ;
- applique des règles mécaniques : structure (cycles synchrones, base
  partagée, couches, composant pivot, chaîne synchrone longue, dépendance
  synchrone à un externe, point unique de défaillance), traçabilité des
  exigences, scénarios, décisions et risques ;
- avec `cloud`, ajoute les piliers Well-Architected (wa_check.py du skill
  well-architected-review) ;
- avec `code`, compare le code à l'architecture à partir du graphe de
  graphify (skill externe, `graphify extract --code-only` : analyse locale,
  sans modèle ; avec `semantic`, les documents sont lus aussi par le modèle
  du harness ou un modèle local) : dépendances du code absentes des flux,
  cycles entre composants, fichiers non rattachés ; avec plusieurs dépôts
  (`code.repos`, ou ceux de la mission quand `code` est vide), un graphe par
  dépôt, en parallèle et gardé par commit, et les appels entre services lus
  dans la configuration et les contrats (URL d'un autre service, base de
  données, canaux AsyncAPI) : appel absent de l'architecture, flux déclaré
  sans trace, base partagée, dépôt sans composant ;
- calcule l'avis (défavorable dès un constat haut ouvert, avec réserves dès
  un constat moyen ouvert) et écrit <sujet>.revue.md. Chaque risque noté et
  chaque scénario non satisfait est un constat de sa gravité (RSK-03,
  QUA-05) : il compte dans la synthèse et l'avis tant qu'il n'est pas
  accepté.

Un écart voulu s'accepte dans `accept`, avec sa raison : il reste dans la
revue mais ne compte plus.

Avec `--vault`, la revue va aussi dans le vault Obsidian du workflow, selon
son ontologie : une note revue-architecture (avis, relation evalue vers la
note de l'option et l'ADR), une note par constat et par risque (porte-sur
l'exigence ou l'option, issu-de la revue), vérifiées avant l'écriture.

    uv run scripts/arch_review.py REVUE.json [--out REVUE.revue.md] [--fail-on haute|moyenne|basse|aucune]
                                  [--vault VAULT --folder DOSSIER_DU_VAULT]
    uv run scripts/arch_review.py --rules
"""

import argparse
import difflib
import json
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import external_skill  # noqa: E402
from skill_paths import absent, load_module, require_module, schema_of  # noqa: E402
from spec_schema import check, print_schema, read_spec, schema_option, validate  # noqa: E402
from text_tools import beside, from_data  # noqa: E402
from review_code import cycles, glob_regex, longest_sync, service_calls  # noqa: E402
from review_common import ATTRIBUTES, RULES, SEVERITIES, count_of  # noqa: E402
from review_render import accept, expected, list_rules, markdown, principles, verdict_of  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")
workspace = require_module("mission-workspace", "lib/workspace.py")

APPLICATIVE = {"system", "db", "queue"}
HUB = 6        # voisins à partir desquels un composant est un pivot
CHAIN = 4      # sauts synchrones au-delà desquels la chaîne est longue
# Relations de graphify qui sont des dépendances (contains, rationale_for, method... n'en sont pas).
DEPENDS = {"calls", "imports", "imports_from", "references", "inherits", "implements", "uses"}

# Scénarios attendus selon les exigences : règles livrées, complétées par celles de l'utilisateur et de la mission.
EXPECTED = Path(__file__).resolve().parent.parent / "references" / "scenarios-attendus.json"


def load_json(path: Path, label: str, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{label} : illisible {path} ({error})")
        return None


def load_catalog(path: Path | None, errors: list[str], warnings: list[str]) -> dict[str, dict]:
    if path is None:
        return {}
    catalog = load_json(path, "requirements", errors)
    if catalog is None:
        return {}
    # Catalogue validé contre le schéma de req_build.py (skill requirements-catalog).
    schema = schema_of("requirements-catalog", "req_build.py")
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent("requirements-catalog", "req_build.py"))
    invalid = check(catalog, schema) if schema else []
    if invalid or not isinstance(catalog, dict) or not isinstance(catalog.get("requirements"), list):
        errors += [f"requirements : {path.name} : {e}" for e in invalid[:10]] or \
                  [f"requirements : {path.name} sans liste requirements"]
        return {}
    return {r["id"]: r for r in catalog["requirements"] if isinstance(r, dict) and "id" in r}


def load_source(base: Path, spec: dict, errors: list[str], warnings: list[str]) -> dict | None:
    """Option d'architecture-options revue : composants, flux et écarts."""
    source = spec.get("source")
    if not source:
        return None
    path = base / source["options"]
    options = load_json(path, "source", errors)
    if options is None:
        return None
    schema = schema_of("architecture-options", "options_build.py")
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent("architecture-options", "options_build.py"))
    invalid = check(options, schema) if schema else []
    if invalid:
        errors += [f"source : {path.name} : {e}" for e in invalid[:10]]
        return None
    found = next((o for o in options.get("options", []) if o.get("id") == source["option"]), None)
    if found is None:
        ids = ", ".join(str(o.get("id")) for o in options.get("options", []))
        errors.append(f"source/option : option « {source['option']} » absente de {path.name} ({ids})")
    elif not spec.get("requirements"):
        # Même catalogue que les options (exigences.json à côté d'options.json par défaut).
        found["_catalog"] = from_data(path.parent, options.get("requirements", "exigences.json"))
    return found


def merge(source: dict | None, spec: dict) -> tuple[list[dict], list[dict]]:
    """Composants et flux de l'option, complétés ou précisés (même id) par ceux de la description."""
    comps: dict[str, dict] = {c["id"]: dict(c) for c in (source or {}).get("components", [])}
    for comp in spec.get("components", []):
        comps[comp["id"]] = {**comps.get(comp["id"], {}), **comp}
    flows = [dict(f) for f in (source or {}).get("flows", [])] + [dict(f) for f in spec.get("flows", [])]
    return list(comps.values()), flows


def graph_of(root: Path, given: Path | None, out_dir: Path, semantic: str, label: str,
             errors: list[str], warnings: list[str]) -> tuple[dict, str] | None:
    """Graphe d'un dossier de code : graph.json donné, sinon graphify extract (--code-only par défaut)."""
    contract = external_skill.contract("graphify")
    if given is not None:
        path = given
    else:
        contract, entry = external_skill.locate("graphify")
        if entry is None:
            errors.append(f"{label} : " + external_skill.missing_message(contract))
            return None
        if not root.is_dir():
            errors.append(f"{label} : dossier introuvable {root}")
            return None
        _, warning = external_skill.version(contract, entry)
        if warning and warning not in warnings:
            warnings.append(warning)
        # Documents lus par un modèle seulement sur demande : celui du harness (claude) ou un local (ollama),
        # jamais un autre fournisseur (AGENTS.md, section 5).
        mode = ["--code-only"] if semantic == "aucune" else ["--backend", semantic] + (
            ["--max-concurrency", "1"] if semantic == "ollama" else [])
        result = subprocess.run([str(entry), "extract", str(root), *mode, "--out", str(out_dir)],
                                capture_output=True, text=True, encoding="utf-8", errors="replace")
        path = out_dir / "graphify-out" / "graph.json"
        if result.returncode != 0 or not path.is_file():
            tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["sans message"]
            errors.append(f"{label} : graphify extract en échec (code {result.returncode}) : {tail[0]}")
            return None
    graph = load_json(path, f"{label}/graph", errors)
    if graph is None:
        return None
    invalid = check(graph, contract["output_schema"])
    if not invalid and not isinstance(graph.get("links", graph.get("edges")), list):
        invalid = ["racine : liste links ou edges attendue"]
    if invalid:
        errors += [f"{label}/graph : {path.name} non conforme au contrat de graphify : {e}" for e in invalid[:5]]
        return None
    return graph, str(path)


def code_repos(base: Path, spec: dict, errors: list[str]) -> list[dict] | None:
    """Dépôts revus : code.repos, sinon ceux de la mission (mission.json) quand code n'a ni root ni repos ;
    None pour un seul dossier de code (code.root)."""
    code = spec["code"]
    if code.get("root") and code.get("repos"):
        errors.append("code : root ou repos, pas les deux")
        return []
    if code.get("root"):
        return None
    if code.get("repos"):
        return [{**r, "root": str(base / r["root"]), "graph": str(base / r["graph"]) if r.get("graph") else None}
                for r in code["repos"]]
    root = workspace.find(base)
    mission, invalid = workspace.load(root) if root else (None, [])
    errors += invalid
    repos = workspace.repos(root, mission) if mission else []
    if not repos and not invalid:
        errors.append("code : ni root, ni repos, et aucun dépôt dans mission.json (mission.py repo)")
    return repos


def code_graph(base: Path, spec: dict, repos: list[dict] | None, out_dir: Path, errors: list[str],
               warnings: list[str]) -> tuple[dict, str] | None:
    """Graphe du code. Plusieurs dépôts : un graphe par dépôt (graphify en parallèle, gardé par commit sous
    graphify/<dépôt>/), fusionnés avec le nom du dépôt en préfixe des fichiers (<dépôt>/src/...)."""
    code = spec["code"]
    semantic = code.get("semantic", "aucune")
    if semantic != "aucune":
        warnings.append(f"code : documents lus par le modèle {semantic} (liens INFERRED, hors des contrôles du code)")
    if repos is None:
        return graph_of(base / code["root"], base / code["graph"] if code.get("graph") else None, out_dir,
                        semantic, "code", errors, warnings)

    # graphify absent : une seule erreur pour tous les dépôts à analyser.
    pending = [r["name"] for r in repos if not r.get("graph")]
    if pending:
        contract, entry = external_skill.locate("graphify")
        if entry is None:
            errors.append(f"code ({', '.join(pending)}) : " + external_skill.missing_message(contract))
            return None

    def one(repo):
        folder = out_dir / "graphify" / repo["name"]
        given = Path(repo["graph"]) if repo.get("graph") else None
        marker = folder / "commit.txt"
        cached = folder / "graphify-out" / "graph.json"
        if given is None and repo.get("commit") and cached.is_file() and marker.is_file() \
                and marker.read_text(encoding="utf-8").strip() == repo["commit"]:
            given = cached
        local_errors: list[str] = []
        found = graph_of(Path(repo["root"]), given, folder, semantic, f"code/{repo['name']}", local_errors, warnings)
        if found and given is None and repo.get("commit"):
            marker.write_text(repo["commit"] + "\n", encoding="utf-8")
        return found, local_errors

    with ThreadPoolExecutor(max_workers=min(4, len(repos)) or 1) as pool:
        results = list(pool.map(one, repos))
    nodes, links = [], []
    for repo, (found, local_errors) in zip(repos, results):
        errors += local_errors
        if not found:
            continue
        graph = found[0]
        name = repo["name"]
        for node in graph["nodes"]:
            source = (node.get("source_file") or "").replace("\\", "/").removeprefix("./")
            nodes.append({**node, "id": f"{name}:{node['id']}", "source_file": f"{name}/{source}" if source else ""})
        for link in graph.get("links", graph.get("edges", [])):
            links.append({**link, "source": f"{name}:{link['source']}", "target": f"{name}:{link['target']}"})
    if errors:
        return None
    return {"nodes": nodes, "links": links}, ", ".join(f"{r['name']} ({p[0][1]})" for r, p in zip(repos, results))


def code_review(graph: dict, comps: list[dict], flows: list[dict], repos: list[dict] | None, add,
                errors: list[str], warnings: list[str]) -> dict:
    """Dépendances du code ramenées aux composants (motifs code) et comparées aux flux déclarés ; avec
    plusieurs dépôts, aussi les appels entre services de la configuration."""
    multi = repos is not None
    patterns = [(c["id"], glob_regex(p)) for c in comps for p in c.get("code", [])]
    calls, databases, owner = service_calls(repos, comps, warnings) if multi else ([], {}, {})
    if multi:
        # Un dépôt relié à un composant sans motif code : tout le dépôt est à lui.
        patterned = {cid for cid, _ in patterns}
        patterns += [(cid, glob_regex(f"{name}/**")) for name, cid in owner.items() if cid and cid not in patterned]
    if not patterns:
        errors.append("code : aucun composant n'a de motif code (fichiers du composant)"
                      + (" ni de dépôt relié (component)" if multi else ""))
        return {}
    owners: dict[str, str | None] = {}
    files: dict[str, str | None] = {}
    for node in graph["nodes"]:
        source = (node.get("source_file") or "").replace("\\", "/").removeprefix("./")
        if node.get("file_type", "code") != "code" or not source:
            continue
        if source not in files:
            files[source] = next((cid for cid, rx in patterns if rx.fullmatch(source)), None)
        owners[node["id"]] = files[source]
    deps: dict[tuple[str, str], int] = {}
    for link in graph.get("links", graph.get("edges", [])):
        if link.get("relation") not in DEPENDS or link.get("confidence", "EXTRACTED") != "EXTRACTED":
            continue
        a, b = owners.get(link["source"]), owners.get(link["target"])
        if a and b and a != b:
            deps[(a, b)] = deps.get((a, b), 0) + 1
    declared = {(f["from"], f["to"]) for f in flows}
    role = {c["id"]: c.get("role", "system") for c in comps}
    # Un flux déclaré, dans un sens ou dans l'autre, couvre la dépendance (appel ou réponse) ; un appel par
    # canal est couvert aussi par un passage par une file déclarée (a > file > b).
    queued = {(a, c) for a, b in declared for b2, c in declared if b == b2 and role.get(b) == "queue"}

    def covered(a, b):
        return (a, b) in declared or (b, a) in declared or (a, b) in queued

    undeclared = [(a, b) for (a, b) in deps if not covered(a, b)]
    for a, b in undeclared:
        add("CODE-01", f"{a}>{b}", f"{vault_ontology.count(deps[(a, b)], 'dépendance')} de {a} vers {b} dans le code, aucun flux déclaré")
    for call in calls:
        a, b = call["from"], call["to"]
        if not covered(a, b) and (a, b) not in deps:
            add("CODE-04", f"{a}>{b}", f"{a} appelle {b} ({call['via']}, {call['file']}), aucun flux déclaré")
    ids = [c["id"] for c in comps]
    sync_calls = {(c["from"], c["to"]) for c in calls if c["style"] == "sync"}
    for group in cycles(ids, set(deps) | sync_calls):
        add("CODE-02", ">".join(group + group[:1]), "composants dépendants les uns des autres dans le code"
            + (" ou la configuration" if multi else ""))
    unmapped = sorted(f for f, cid in files.items() if cid is None)
    if unmapped:
        shown = ", ".join(unmapped[:5]) + (" ..." if len(unmapped) > 5 else "")
        add("CODE-03", "code", f"{vault_ontology.count(len(unmapped), 'fichier')} sur {vault_ontology.number(len(files))} : {shown}")
    result = {"files": len(files), "unmapped": len(unmapped), "dependencies": len(deps),
              "undeclared": [f"{a}>{b}" for a, b in undeclared]}
    if not multi:
        return result
    traced = set(deps) | {(c["from"], c["to"]) for c in calls}
    owned = {cid for cid in owner.values() if cid} | {cid for cid, rx in patterns
                                                      if any(rx.fullmatch(f) for f in files)}
    for a, b in sorted(declared, key=lambda e: (ids.index(e[0]) if e[0] in ids else 0, e[1])):
        if a in owned and b in owned and a != b and (a, b) not in traced and (b, a) not in traced:
            add("CODE-05", f"{a}>{b}", f"flux {a} > {b} déclaré, aucun appel trouvé entre leurs dépôts")
    shared = {key: sorted(users) for key, users in databases.items() if len(users) > 1}
    for key, users in sorted(shared.items()):
        add("CODE-06", key, f"{key} citée par {', '.join(users)}")
    for repo in repos:
        name = repo["name"]
        if not owner[name] and not any(cid for f, cid in files.items() if f.startswith(f"{name}/") and cid):
            add("CODE-07", name, f"{name} ({repo['root']}) : ni component, ni motif code qui le vise")
    result.update({"repos": len(repos), "calls": [f"{c['from']}>{c['to']} ({c['via']})" for c in calls],
                   "shared_databases": [f"{k} : {', '.join(v)}" for k, v in sorted(shared.items())]})
    return result


def domain_review(spec: dict, base: Path, comps: list[dict], flows: list[dict], role: dict, add,
                  errors: list[str], warnings: list[str]) -> dict | None:
    """Règles DOM- : composants et flux confrontés au découpage de domain-design (domains)."""
    if not spec.get("domains"):
        return None
    module = load_module("domain-design", "domain_build.py")
    if module is None:
        warnings.append("domains : découpage non contrôlé : " + absent("domain-design", "domain_build.py"))
        return None
    path = from_data(base, spec["domains"])
    described = load_json(path, "domains", errors)
    if described is None:
        return None
    invalid = validate(described, module.__file__)
    if invalid:
        errors += [f"domains : {path.name} : {e}" for e in invalid]
        return None
    found = module.analyse(described, path.parent)
    if found["errors"]:
        errors += [f"domains : {e}" for e in found["errors"]]
        return None
    ctxs = [c["id"] for c in described["contexts"]]
    for i, comp in enumerate(comps):
        for ctx in comp.get("contexts", []):
            if ctx not in ctxs:
                close = difflib.get_close_matches(ctx, ctxs, n=1)
                errors.append(f"components/{i} ({comp['id']})/contexts : contexte inconnu « {ctx} »"
                              + (f" ; vouliez-vous « {close[0]} » ?" if close else f" ({', '.join(ctxs)})"))
    if errors:
        return None
    of = {c["id"]: set(c.get("contexts", [])) for c in comps}
    order = {c: i for i, c in enumerate(ctxs)}
    relations = {(r["upstream"], r["downstream"]) for r in described.get("relations", [])}
    linked = relations | {(b, a) for a, b in relations}
    # Flux effectifs : par une file, du producteur au consommateur.
    edges = [(f["from"], f["to"], f.get("style", "sync")) for f in flows
             if role.get(f["from"]) != "queue" and role.get(f["to"]) != "queue"]
    for q in [c["id"] for c in comps if role[c["id"]] == "queue"]:
        producers = [f["from"] for f in flows if f["to"] == q]
        consumers = [f["to"] for f in flows if f["from"] == q]
        edges += [(a, b, "async") for a in producers for b in consumers if a != b]
    ids = [c["id"] for c in comps]
    for cid in ids:
        if role[cid] == "db":
            users = sorted({a for a, b, _ in edges if b == cid and role.get(a) == "system" and of[a]}
                           | {b for a, b, _ in edges if a == cid and role.get(b) == "system" and of[b]}, key=ids.index)
            if len({frozenset(of[u]) for u in users}) > 1:
                add("DOM-01", cid, "utilisée par " + ", ".join(f"{u} ({', '.join(sorted(of[u]))})" for u in users))
    seen = set()
    for a, b, style in edges:
        if role.get(a) not in APPLICATIVE or role.get(b) not in APPLICATIVE or role.get(b) == "db":
            continue
        ca, cb = of[a], of[b]
        if not ca or not cb or ca & cb:
            continue
        pairs = {(x, y) for x in ca for y in cb}
        if not pairs & linked and (a, b) not in seen:
            seen.add((a, b))
            add("DOM-02", f"{a}>{b}", f"{', '.join(sorted(ca))} vers {', '.join(sorted(cb))}, sans relation déclarée")
        elif style == "sync" and pairs & relations and not {(y, x) for x, y in pairs} & relations:
            add("DOM-03", f"{a}>{b}", f"{a} ({', '.join(sorted(ca))}, amont) attend {b} "
                f"({', '.join(sorted(cb))}, aval)")
    calls = {(x, y) for a, b, style in edges if style == "sync" and role.get(b) != "db"
             for x in of.get(a, ()) for y in of.get(b, ()) if x != y and not of[a] & of[b]}
    for group in cycles(ctxs, calls):
        add("DOM-04", ">".join(group + group[:1]), "appels synchrones en boucle entre contextes")
    for cid in ids:
        if role[cid] in ("system", "db") and not of[cid]:
            add("DOM-05", cid, next(c["label"] for c in comps if c["id"] == cid))
    carried = {x for c in comps for x in of[c["id"]]}
    for ctx in ctxs:
        if ctx not in carried:
            add("DOM-06", ctx, "aucun composant ne le cite dans contexts")
    services = {ctx: [c["id"] for c in comps if role[c["id"]] == "system" and of[c["id"]] == {ctx}] for ctx in ctxs}
    for ctx, items in services.items():
        if len(items) > 3:
            add("DOM-07", ctx, f"{len(items)} services : {', '.join(items)}")
    for cid in ids:
        if role[cid] != "system":
            continue
        targets = {y for a, b, style in edges if a == cid and style == "sync" and role.get(b) == "system"
                   for y in of.get(b, ()) if y not in of[cid]}
        if len(targets) >= 3:
            add("DOM-08", cid, f"appels synchrones vers {len(targets)} contextes ({', '.join(sorted(targets, key=order.get))})")
    # Style : celui retenu par l'utilisateur (decision), sinon la recommandation de la grille.
    style = found["style"]
    chosen = (described.get("decision") or {}).get("style") or style["recommended"]
    extract = set((described.get("decision") or {}).get("extract") or style["extract"])
    deployables = [c["id"] for c in comps if role[c["id"]] == "system" and of[c["id"]]]
    why = f"style {chosen.replace('-', ' ')} (score {style['score']:+d})"
    if chosen == "monolithe-modulaire" and len(deployables) > 1:
        add("DOM-09", ", ".join(deployables), f"{len(deployables)} composants déployables pour un {why}")
    elif chosen == "mixte":
        for cid in deployables:
            if len(of[cid]) == 1 and not of[cid] & extract:
                add("DOM-09", cid, f"contexte {next(iter(of[cid]))} en service séparé, non extrait par la grille ({why})")
    return {"domains": str(path), "style": chosen, "contexts": len(ctxs)}


def draft(path: Path, option_id: str | None, rules: list[dict]) -> dict:
    """Brouillon de revue.json : source (option revue d'options.json), catalogue, un squelette de scénario par
    exigence non fonctionnelle indispensable ou importante et par scénario attendu ; le modèle n'écrit que
    stimulus, réponse et évaluation."""
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(path), "outputs": [], "option": None, "scenarios": 0, "errors": errors,
              "warnings": warnings}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une description")
        return report
    options_path = path.parent / "options.json"
    options = load_json(options_path, "options", errors)
    if options is None:
        return report
    wanted = option_id or (options.get("decision") or {}).get("option") or \
        (options.get("recommendation") or {}).get("option")
    option = next((o for o in options.get("options", []) if o.get("id") == wanted), None)
    if option is None:
        ids = ", ".join(str(o.get("id")) for o in options.get("options", []))
        errors.append(f"--option : option « {wanted} » absente de options.json ({ids})")
        return report
    catalog_path = from_data(path.parent, options.get("requirements", "exigences.json"))
    catalog = load_catalog(catalog_path, errors, warnings) if catalog_path.is_file() else {}
    if errors:
        return report
    stimuli = {}
    for rule in rules:
        stimuli.setdefault(rule["attribute"], rule.get("draft"))
    scenarios = []
    for req in catalog.values():
        category = req.get("category")
        if req.get("status", "retenue") != "retenue" or req.get("priority") not in ("indispensable", "importante") \
                or not category or not (req.get("nature") == "non-fonctionnelle" or req["id"].startswith("ENF")):
            continue
        scenario = {"id": f"QS-{len(scenarios) + 1:02d}", "attribute": category,
                    "importance": "haute" if req["priority"] == "indispensable" else "moyenne",
                    "stimulus": stimuli.pop(category, None) or f"À écrire : {req.get('title', req['id'])}",
                    "response": req.get("text") or req.get("title", req["id"])}
        if req.get("metric"):
            scenario["measure"] = req["metric"]
        scenario["refs"] = [req["id"]]
        used = [c["id"] for c in option.get("components", []) if req["id"] in c.get("refs", [])]
        if used:
            scenario["components"] = used
        scenario["status"] = "a-verifier"
        scenarios.append(scenario)
    for rule in expected(rules, catalog, option.get("components", []), scenarios):
        if rule.get("draft"):
            scenarios.append({"id": f"QS-{len(scenarios) + 1:02d}", "attribute": rule["attribute"],
                              "stimulus": rule["draft"], "response": "À écrire", "status": "a-verifier"})
    spec = {"title": f"Revue : {option.get('name', option['id'])}", "source": {"options": "options.json",
                                                                                "option": option["id"]},
            "scenarios": scenarios, "risks": [], "decisions": [],
            "_draft": "Brouillon de arch_review.py --draft : stimulus, environnement, réponse et mesure à écrire ou "
                      "corriger, puis évaluer chaque scénario (status, note) ; risques et décisions à ajouter."}
    # Découpage de domain-design à côté d'options.json : contrôlé par les règles DOM-.
    if (path.parent / "domaines.json").is_file():
        spec["domains"] = "domaines.json"
    invalid = validate(spec, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], option=option["id"], scenarios=len(scenarios))
    return report


def check_refs(spec: dict, comps: list[dict], flows: list[dict], catalog: dict, has_catalog_path: bool,
               errors: list[str], warnings: list[str]) -> None:
    """Références croisées de la description : une erreur, pas un constat."""
    byid = {c["id"]: c for c in comps}
    scenarios = {s["id"]: s for s in spec.get("scenarios", [])}
    risks = spec.get("risks", [])
    decisions = {d["id"]: d for d in spec.get("decisions", [])}
    layers = spec.get("layers", [])
    for name, items in (("scenarios", spec.get("scenarios", [])), ("risks", risks),
                        ("decisions", spec.get("decisions", []))):
        seen = [i["id"] for i in items]
        errors += [f"{name} : identifiant en double « {i} »" for i in sorted({i for i in seen if seen.count(i) > 1})]

    def known(where, values, pool, kind):
        for value in values:
            if value not in pool:
                close = [p for p in pool if p.lower() == str(value).lower()]
                hint = f" ; vouliez-vous « {close[0]} » ?" if close else ""
                errors.append(f"{where} : {kind} inconnu « {value} »{hint}")

    def known_refs(where, refs):
        if not catalog:
            if refs and not has_catalog_path:
                warnings.append(f"{where} : exigences citées sans catalogue (requirements) : non vérifiées")
            return
        for ref in refs:
            if ref not in catalog:
                errors.append(f"{where} : exigence inconnue {ref}")
            elif catalog[ref].get("status") == "retiree":
                errors.append(f"{where} : {ref} est retirée du catalogue")

    for i, flow in enumerate(flows):
        known(f"flows/{i}", [flow["from"], flow["to"]], byid, "composant")
    for i, comp in enumerate(comps):
        known_refs(f"components/{i} ({comp['id']})", comp.get("refs", []))
        if comp.get("layer") is not None and comp["layer"] not in layers:
            errors.append(f"components/{i} ({comp['id']})/layer : « {comp['layer']} » absente de layers "
                          f"({', '.join(layers) or 'aucune couche déclarée'})")
    for i, sc in enumerate(spec.get("scenarios", [])):
        known(f"scenarios/{i} ({sc['id']})/components", sc.get("components", []), byid, "composant")
        known_refs(f"scenarios/{i} ({sc['id']})/refs", sc.get("refs", []))
    for i, risk in enumerate(risks):
        known(f"risks/{i} ({risk['id']})/scenarios", risk.get("scenarios", []), scenarios, "scénario")
        known(f"risks/{i} ({risk['id']})/components", risk.get("components", []), byid, "composant")
        known_refs(f"risks/{i} ({risk['id']})/refs", risk.get("refs", []))
    for i, dec in enumerate(spec.get("decisions", [])):
        known(f"decisions/{i} ({dec['id']})/components", dec.get("components", []), byid, "composant")
        known_refs(f"decisions/{i} ({dec['id']})/refs", dec.get("refs", []))
    for i, item in enumerate(spec.get("sensitivities", [])):
        known(f"sensitivities/{i}/components", item.get("components", []), byid, "composant")
        known(f"sensitivities/{i}/scenarios", item.get("scenarios", []), scenarios, "scénario")
    for i, item in enumerate(spec.get("tradeoffs", [])):
        if item.get("decision"):
            known(f"tradeoffs/{i}/decision", [item["decision"]], decisions, "décision")


def structure_review(comps: list[dict], flows: list[dict], layers: list[str], scenarios: dict, catalog: dict,
                     role: dict, add) -> None:
    """Règles STR : boucles, base partagée, couches, pivots, chaînes synchrones, points uniques."""
    byid = {c["id"]: c for c in comps}
    ids = list(byid)
    sync_edges = {(f["from"], f["to"]) for f in flows if f.get("style", "sync") == "sync"}
    all_edges = {(f["from"], f["to"]) for f in flows}
    inner = [i for i in ids if role[i] != "person"]
    for group in cycles(inner, {e for e in sync_edges if role[e[0]] != "person"}):
        add("STR-01", ">".join(group + group[:1]), "appels synchrones en boucle entre composants")
    for cid in ids:
        if role[cid] == "db":
            users = sorted({a for a, b in all_edges if b == cid and role[a] == "system"}, key=ids.index)
            if len(users) > 1:
                add("STR-02", cid, f"lue ou écrite par {', '.join(users)}")
    rank = {name: index for index, name in enumerate(layers)}
    for a, b in sorted(all_edges, key=lambda e: (ids.index(e[0]), ids.index(e[1]))):
        la, lb = byid[a].get("layer"), byid[b].get("layer")
        if la in rank and lb in rank and rank[lb] < rank[la]:
            add("STR-03", f"{a}>{b}", f"{a} ({la}) appelle {b} ({lb}), couche au-dessus")
    for cid in inner:
        neighbours = {b for a, b in all_edges if a == cid} | {a for a, b in all_edges if b == cid}
        if role[cid] in APPLICATIVE and len(neighbours) >= HUB:
            add("STR-04", cid, f"relié à {len(neighbours)} composants")
    sync = {i: sorted({b for a, b in sync_edges if a == i}, key=ids.index) for i in ids}
    reach: set[str] = set()  # composants atteints en synchrone depuis un utilisateur
    for person in (i for i in ids if role[i] == "person"):
        todo = [person]
        while todo:
            node = todo.pop()
            for nxt in sync[node]:
                if nxt not in reach:
                    reach.add(nxt)
                    todo.append(nxt)
        chain = longest_sync(person, sync)
        if len(chain) - 1 > CHAIN:
            add("STR-05", ">".join(chain), f"{len(chain) - 1} sauts synchrones depuis {person}")
    for a, b in sorted(sync_edges, key=lambda e: (ids.index(e[0]), ids.index(e[1]))):
        if role[b] == "external" and role[a] in APPLICATIVE and a in reach:
            add("STR-06", f"{a}>{b}", f"le parcours de l'utilisateur attend {b}")
    for cid in ids:
        if not any(cid in e for e in all_edges):
            add("STR-07", cid, "aucun flux n'entre ni ne sort")
    availability = any(s["attribute"] == "disponibilite" for s in scenarios.values()) or any(
        r.get("category") == "disponibilite" and r.get("status", "retenue") == "retenue"
        and r.get("priority") in ("indispensable", "importante") for r in catalog.values())
    if availability:
        for cid in ids:
            if role[cid] in {"system", "db"} and cid in reach and count_of(byid[cid]) < 2:
                add("STR-08", cid, "une seule instance sur le parcours de l'utilisateur, disponibilité exigée")


def trace_review(catalog: dict, gaps: dict, comps: list[dict], decisions: dict, scenarios: dict, role: dict,
                 add) -> dict | None:
    """Règles TRA : exigences portées par un composant, une décision ou un scénario ; None sans catalogue."""
    if not catalog:
        return None
    carried: dict[str, dict[str, list[str]]] = {}
    for kind, items in (("components", comps), ("decisions", decisions.values()),
                        ("scenarios", scenarios.values())):
        for item in items:
            for ref in item.get("refs", []):
                carried.setdefault(ref, {}).setdefault(kind, []).append(item["id"])
    retained = [r for r in catalog.values()
                if r.get("status", "retenue") == "retenue" and r.get("priority") != "hors-perimetre"]
    uncarried, without = [], []
    for req in retained:
        nature = req.get("nature") or {"EF": "fonctionnelle", "ENF": "non-fonctionnelle"}.get(
            req["id"].split("-")[0])
        if req.get("priority") == "indispensable" and (req["id"] not in carried
                                                       or gaps.get(req["id"], {}).get("level") == "non"):
            uncarried.append(req["id"])
            gap = gaps.get(req["id"])
            add("TRA-01", req["id"], f"{req.get('title', req['id'])}"
                + (f" (écart de l'option : {gap['note']})" if gap else " : aucun composant, décision ni scénario"))
        if nature == "non-fonctionnelle" and req.get("priority") in ("indispensable", "importante") \
                and not carried.get(req["id"], {}).get("scenarios"):
            without.append(req["id"])
            add("TRA-02", req["id"], f"{req.get('title', req['id'])} ({req.get('priority')})")
    in_decision = {c for d in decisions.values() for c in d.get("components", [])}
    for comp in comps:
        if role[comp["id"]] in APPLICATIVE and not comp.get("refs") and comp["id"] not in in_decision:
            add("TRA-03", comp["id"], comp["label"])
    return {"requirements": len(retained), "uncarried": uncarried, "without_scenario": without,
            "rows": [(r, carried.get(r["id"], {})) for r in retained]}


def quality_review(spec: dict, comps: list[dict], flows: list[dict], scenarios: dict, decisions: dict,
                   catalog: dict, rules: list[dict], client: list[dict], add) -> None:
    """Règles QUA, PRI, DEC et RSK : scénarios, principes du client, décisions, risques."""
    risks = spec.get("risks", [])
    risked = {s for r in risks for s in r.get("scenarios", [])}
    for sc in scenarios.values():
        if sc["status"] == "non-satisfait" and sc["id"] not in risked:
            add("QUA-01", sc["id"], sc["response"])
        elif sc["status"] == "non-satisfait":
            add("QUA-05", sc["id"], sc["response"], sc.get("importance", "haute"))
        elif sc["status"] == "risque" and sc["id"] not in risked:
            add("QUA-02", sc["id"], sc["response"])
        elif sc["status"] == "a-verifier":
            add("QUA-04", sc["id"], sc["response"])
        if not sc.get("measure"):
            add("QUA-03", sc["id"], sc["response"])
    if catalog:
        for rule in expected(rules, catalog, comps, scenarios.values()):
            add("QUA-06", rule["id"], f"{rule['label']} ({ATTRIBUTES.get(rule['attribute'], rule['attribute'])})")
    for element, message, severity in principles(client, comps, flows):
        add("PRI-01", element, message, severity)
    if not decisions:
        add("DEC-01", "architecture", "aucune décision dans decisions")
    for dec in decisions.values():
        if dec["status"] == "proposee":
            add("DEC-02", dec["id"], dec["title"])
    for i, item in enumerate(spec.get("tradeoffs", [])):
        if not item.get("decision"):
            add("DEC-03", f"compromis {i + 1}", item["text"])
    for risk in risks:
        # Un risque haut sans atténuation est déjà RSK-01 : pas de second constat.
        if risk["severity"] == "haute" and not risk.get("mitigation"):
            add("RSK-01", risk["id"], risk["text"])
        else:
            add("RSK-03", risk["id"], risk["text"], risk["severity"])
        if not risk.get("owner"):
            add("RSK-02", risk["id"], risk["text"])


def cloud_review(spec: dict, base: Path, findings: list[dict], errors: list[str],
                 warnings: list[str]) -> tuple[str | None, int]:
    """Piliers Well-Architected de la description cloud (skill well-architected-review) : fichier revu, règles."""
    if not spec.get("cloud"):
        return None, 0
    wa = load_module("well-architected-review", "wa_check.py")
    if wa is None or wa.MISSING:
        warnings.append("cloud : revue Well-Architected non faite : "
                        + absent("well-architected-review", "wa_check.py") + " (et cloud-architecture)")
        return None, 0
    path = from_data(base, spec["cloud"])
    described = load_json(path, "cloud", errors)
    invalid = wa.validate(described, wa.__file__) if described is not None else []
    errors += [f"cloud : {path.name} : {e}" for e in invalid]
    if described is None or invalid:
        return None, 0
    wa_findings, wa_errors, _ = wa.check(described)
    errors += [f"cloud : {e}" for e in wa_errors]
    for f in wa_findings:
        if f["pillar"] != "conventions":
            findings.append({"rule": f["rule"], "axis": "well-architected", "severity": f["severity"],
                             "element": f["element"], "message": f"{wa.PILLARS[f['pillar']]} : {f['message']}",
                             "fix": f["fix"], "ref": f["ref"], "accepted": None})
    return str(path), sum(1 for v in wa.RULES.values() if v[0] != "conventions")


def review(spec: dict, base: Path, out_dir: Path, rules: list[dict] | None = None,
           client: list[dict] | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    findings: list[dict] = []

    def add(rule, element, message, severity=None):
        axis, default, title, fix, ref = RULES[rule]
        severity = severity or default
        findings.append({"rule": rule, "axis": axis, "severity": severity, "element": element,
                         "message": f"{title} : {message}", "fix": fix, "ref": ref, "accepted": None})

    source = load_source(base, spec, errors, warnings)
    path = from_data(base, spec["requirements"]) if spec.get("requirements") else (source or {}).get("_catalog")
    catalog = load_catalog(path, errors, warnings)
    comps, flows = merge(source, spec)
    if not comps:
        errors.append("components : aucun composant, ni dans la description ni dans source")
    check_refs(spec, comps, flows, catalog, path is not None, errors, warnings)
    if errors:
        return {"errors": errors, "warnings": warnings}

    scenarios = {s["id"]: s for s in spec.get("scenarios", [])}
    decisions = {d["id"]: d for d in spec.get("decisions", [])}
    role = {c["id"]: c.get("role", "system") for c in comps}
    structure_review(comps, flows, spec.get("layers", []), scenarios, catalog, role, add)
    domains = domain_review(spec, base, comps, flows, role, add, errors, warnings)
    trace = trace_review(catalog, (source or {}).get("gaps", {}), comps, decisions, scenarios, role, add)
    quality_review(spec, comps, flows, scenarios, decisions, catalog, rules or [], client or [], add)

    rules = len(RULES) - (0 if spec.get("code") is not None else sum(1 for r in RULES.values() if r[0] == "code")) \
        - (0 if client else 1) + len(client or []) \
        - (0 if domains else sum(1 for r in RULES.values() if r[0] == "domaines"))
    cloud, cloud_rules = cloud_review(spec, base, findings, errors, warnings)
    rules += cloud_rules

    code = None
    if spec.get("code") is not None and not errors:
        repos = code_repos(base, spec, errors)
        found = code_graph(base, spec, repos, out_dir, errors, warnings) if not errors else None
        if found:
            code = {"graph": found[1], **code_review(found[0], comps, flows, repos, add, errors, warnings)}
    return {"findings": findings, "comps": comps, "flows": flows, "scenarios": scenarios, "decisions": decisions,
            "catalog": catalog, "trace": trace, "code": code, "cloud": cloud, "rules": rules,
            "principles": len(client or []),
            "errors": errors, "warnings": warnings}


VERDICTS = {"favorable": "favorable", "favorable avec réserves": "reserves", "défavorable": "defavorable"}


def write_vault(vault: Path, folder: str, spec: dict, found: dict, verdict: str, out: Path,
                errors: list[str], warnings: list[str] | None = None) -> dict | None:
    """Notes typées de la revue dans le vault : revue-architecture, constats et risques, liés aux
    notes d'exigence, d'option et d'ADR déjà écrites par decision-log (vault_sync.py)."""
    notes = vault_ontology.Notes(vault, "architecture-review")
    base = vault_ontology.safe_folder(folder)
    title = vault_ontology.safe_name(spec["title"], "revue")
    review_rel = f"{base}/Revues d'architecture/{title}"
    option = spec.get("source", {}).get("option")
    option_rel = f"{base}/Options/Option {option}" if option else None
    catalog = found["catalog"]

    def about(ids) -> list[tuple[str, str]]:
        rels = [(f"{base}/Exigences/{i}", i) for i in ids if i in catalog and notes.exists(f"{base}/Exigences/{i}")]
        return rels or ([(option_rel, f"Option {option}")] if option_rel else [])

    up = f"Revue : [[{review_rel}|{title}]]"
    v = vault_ontology
    constats_dir, cleanup_c = v.folders_of(base, "Constats", title)
    risques_dir, cleanup_r = v.folders_of(base, "Risques", title)
    severities = ("haute", "moyenne", "basse")
    rank = lambda s: severities.index(s) if s in severities else len(severities)  # noqa: E731
    constats = []
    for f in sorted(found["findings"], key=lambda f: (rank(f["severity"]), f["rule"], f["element"])):
        rel = f"{constats_dir}/{v.safe_name(f['rule'] + ' ' + f['element'])}"
        heading = f"{f['rule']} {v.short(f['message'])}"
        constats.append((rel, f, heading))
        body = [f"# {heading}", ""]
        body += v.callout("warning", "Gravité haute", [f["message"]]) if f["severity"] == "haute" and not f["accepted"] \
            else [f["message"], ""]
        body += [up, "", f"**Correction** : {f['fix']}", "", f"**Référence** : {f['ref']}"] \
            + (["", f"**Accepté** : {f['accepted']}"] if f["accepted"] else [])
        notes.add(rel, "constat", {"id": f"{f['rule']}@{f['element']}", "gravite": f["severity"], "regle": f["rule"],
                                   "statut": "accepte" if f["accepted"] else "ouvert"},
                  {"porte-sur": about([f["element"]]), "issu-de": (review_rel, title)}, body, ["architecture"])
    risques = []
    accepted = {f["element"] for f in found["findings"] if f["rule"] in ("RSK-01", "RSK-03") and f["accepted"]}
    for r in sorted(spec.get("risks", []), key=lambda r: (rank(r["severity"]), r["id"])):
        rel = f"{risques_dir}/{v.safe_name(r['id'])}"
        risques.append((rel, r))
        body = [f"# {r['id']} {r['text']}", ""]
        if r["severity"] == "haute":
            body += v.callout("warning", "Gravité haute", [r["text"]])
        body += [up, ""]
        missing = [label for key, label in (("mitigation", "Atténuation"), ("owner", "Responsable")) if not r.get(key)]
        if missing:
            body += v.callout("question", "À compléter", [f"{', '.join(missing)} : à définir dans la revue."])
        body += [f"**Atténuation** : {r.get('mitigation', 'à définir')}", "",
                 f"**Responsable** : {r.get('owner', 'à désigner')}"]
        if r.get("scenarios"):
            body += ["", "**Scénarios** : " + ", ".join(r["scenarios"])]
        notes.add(rel, "risque", {"id": r["id"], "gravite": r["severity"],
                                  "statut": "accepte" if r["id"] in accepted
                                  else "attenue" if r.get("mitigation") else "ouvert"},
                  {"porte-sur": about(r.get("refs", [])), "issu-de": (review_rel, title)}, body, ["architecture"])
    open_ = [f for _, f, _ in constats if not f["accepted"]]
    high = sum(f["severity"] == "haute" for f in open_)
    report = notes.attach(f"{base}/Rapports/{v.folder_key(title)}/{out.name}", out) if out.is_file() else f"`{out.name}`"
    kind = {"favorable": "success", "favorable avec réserves": "note"}.get(verdict, "danger")
    body = [f"# Revue d'architecture : {spec['title']}", ""]
    body += v.callout(kind, f"Avis : {verdict}", [
        v.count(len(open_), "constat ouvert") + (f", dont {v.number(high)} de gravité haute" if high else "")
        + f" ; {v.count(len(risques), 'risque')}."])
    body += [f"Revue complète : {report}."]
    for label, items in (("Constats ouverts", [c for c in constats if not c[1]["accepted"]]),
                         ("Constats acceptés", [c for c in constats if c[1]["accepted"]])):
        if items:
            body += ["", f"## {label}", ""] + [f"- {v.link(rel, heading)} ({f['severity']}) : {v.detail(f['message'], f['element'])}"
                                              for rel, f, heading in items]
    if risques:
        body += ["", "## Risques", ""] + [f"- {v.link(rel, r['id'] + ' ' + v.short(r['text']))} ({r['severity']})"
                                         for rel, r in risques]
    evalue = [(p, a) for p, a in ((option_rel, f"Option {option}"), (f"{base}/ADR architecture", "ADR")) if p]
    notes.add(review_rel, "revue-architecture", {"avis": VERDICTS[verdict], "date": None}, {"evalue": evalue}, body,
              ["architecture"])
    # Constats et risques d'une revue précédente qui ne sont plus relevés : notes générées retirées.
    result = notes.write(errors, cleanup=cleanup_c + cleanup_r, warnings=warnings)
    return {**result, "folder": base} if result else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, help="fichier Markdown (défaut : <sujet>.revue.md)")
    parser.add_argument("--fail-on", choices=SEVERITIES + ("aucune",), default="haute",
                        help="code de sortie 1 dès un constat non accepté de cette gravité ou plus (défaut : haute)")
    parser.add_argument("--vault", type=Path, help="vault Obsidian où écrire la revue (notes typées)")
    parser.add_argument("--folder", help="dossier des notes dans le vault, celui du workflow (Workflows/<titre>)")
    parser.add_argument("--rules", action="store_true", help="liste les règles, puis s'arrête")
    parser.add_argument("--draft", action="store_true",
                        help="écrire le brouillon de la description depuis options.json et le catalogue voisins")
    parser.add_argument("--option", help="avec --draft : option revue (défaut : décision, sinon recommandation)")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if args.rules:
        print(list_rules())
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    if args.draft:
        rules, _, invalid = workspace.rules("revue", EXPECTED, [args.spec])
        report = draft(args.spec, args.option, rules) if not invalid else \
            {"input": str(args.spec), "outputs": [], "option": None, "scenarios": 0, "errors": invalid, "warnings": []}
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    # Dans une mission (mission.json au-dessus de la description) : son vault et le dossier du workflow par défaut.
    scoped = workspace.vault_args(parser, args, [args.spec])
    if scoped:
        print(json.dumps({"input": str(args.spec), "errors": scoped, "warnings": []}, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    spec, invalid = read_spec(args.spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    # Scénarios attendus : règles livrées, de l'utilisateur et de la mission.
    rules, _, invalid = workspace.rules("revue", EXPECTED, [args.spec])
    # Principes d'architecture du client (mission : references.principes), vérifiés comme des règles en plus.
    client, _, wrong = workspace.rules("principes", None, [args.spec])
    if invalid or wrong:
        print(json.dumps({"input": str(args.spec), "errors": invalid + wrong, "warnings": []}, ensure_ascii=False))
        return 1
    stem = args.spec.name.removesuffix(".json")
    out = args.out or beside(args.spec.with_name(stem + (".md" if stem.endswith("revue") else ".revue.md")))
    found = review(spec, args.spec.parent, out.parent, rules, client)
    if "findings" not in found:
        print(json.dumps({"input": str(args.spec), "errors": found["errors"], "warnings": found["warnings"]},
                         ensure_ascii=False))
        return 1
    findings, errors, warnings = found["findings"], found["errors"], found["warnings"]
    accept(findings, spec.get("accept") or {}, warnings)
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["rule"]))
    open_ = [f for f in findings if not f["accepted"]]
    counts = {s: sum(f["severity"] == s for f in open_) for s in SEVERITIES}
    counts["acceptés"] = len(findings) - len(open_)
    verdict = None if errors else verdict_of(open_)
    trace = {k: v for k, v in found["trace"].items() if k != "rows"} if found["trace"] else None
    result = {"input": str(args.spec), "output": None, "verdict": verdict, "components": len(found["comps"]),
              "flows": len(found["flows"]), "scenarios": len(found["scenarios"]), "risks": len(spec.get("risks", [])),
              "rules": found["rules"], "principles": found["principles"], "counts": counts, "findings": findings, "trace": trace, "code": found["code"],
              "cloud": found["cloud"], "vault": None, "errors": errors, "warnings": warnings}
    if not errors:
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(markdown(spec, found, verdict))
        result["output"] = str(out)
        if args.vault:
            result["vault"] = write_vault(args.vault, args.folder, spec, found, verdict, out, errors,
                                          result["warnings"])
    print(json.dumps(result, ensure_ascii=False))
    limit = SEVERITIES.index(args.fail_on) if args.fail_on in SEVERITIES else -1
    failing = any(SEVERITIES.index(f["severity"]) <= limit for f in open_)
    return 1 if errors or failing else 0


if __name__ == "__main__":
    sys.exit(main())
