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
import json
import re
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import external_skill  # noqa: E402
from skill_paths import absent, load_module, require_module, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")
workspace = require_module("mission-workspace", "lib/workspace.py")

SEVERITIES = ("haute", "moyenne", "basse")
AXES = {"structure": "Structure", "code": "Code et architecture", "tracabilite": "Traçabilité des exigences",
        "qualite": "Scénarios de qualité", "decisions": "Décisions", "risques": "Risques",
        "well-architected": "Well-Architected (cloud)", "principes": "Principes du client"}
ATTRIBUTES = {"performance": "Performance", "disponibilite": "Disponibilité", "securite": "Sécurité",
              "conformite": "Conformité", "exploitabilite": "Exploitabilité", "maintenabilite": "Maintenabilité",
              "evolutivite": "Évolutivité", "interoperabilite": "Interopérabilité", "utilisabilite": "Utilisabilité",
              "portabilite": "Portabilité", "cout": "Coût", "autre": "Autre"}
DECIDED = {"proposee": "proposée", "acceptee": "acceptée", "remplacee": "remplacée"}
STATUS = {"satisfait": "satisfait", "risque": "à risque", "non-satisfait": "non satisfait", "a-verifier": "à vérifier"}
APPLICATIVE = {"system", "db", "queue"}
HUB = 6        # voisins à partir desquels un composant est un pivot
CHAIN = 4      # sauts synchrones au-delà desquels la chaîne est longue
# Relations de graphify qui sont des dépendances (contains, rationale_for, method... n'en sont pas).
DEPENDS = {"calls", "imports", "imports_from", "references", "inherits", "implements", "uses"}

ATAM = "ATAM (SEI)"
# Scénarios attendus selon les exigences : règles livrées, complétées par celles de l'utilisateur et de la mission.
EXPECTED = Path(__file__).resolve().parent.parent / "references" / "scenarios-attendus.json"
# règle -> (axe, gravité, titre, correction, référence)
RULES = {
    "STR-01": ("structure", "moyenne", "Cycle de dépendances synchrones",
               "Casser le cycle : inverser une dépendance, passer un flux en asynchrone ou extraire le code commun.",
               "Principe des dépendances acycliques (R. C. Martin) ; ISO/IEC 25010 : modularité"),
    "STR-02": ("structure", "moyenne", "Base de données partagée",
               "Une base par composant propriétaire ; les autres passent par son API ou ses événements.",
               "Database per service (microservices.io) ; ISO/IEC 25010 : modularité, modifiabilité"),
    "STR-03": ("structure", "moyenne", "Dépendance vers une couche supérieure",
               "Inverser la dépendance (interface dans la couche basse, événement) ou revoir la couche du composant.",
               "Architecture en couches (POSA) ; arc42 §8"),
    "STR-04": ("structure", "basse", "Composant pivot",
               "Découper le composant ou introduire une médiation (événements, passerelle).",
               f"ISO/IEC 25010 : modularité ; {ATAM} : point de sensibilité"),
    "STR-05": ("structure", "moyenne", "Chaîne d'appels synchrones longue",
               "Raccourcir la chaîne (asynchrone, cache, agrégation) ; délai et disjoncteur à chaque saut.",
               "Release It! (M. Nygard) : chaînes d'intégration, disjoncteur"),
    "STR-06": ("structure", "moyenne", "Dépendance synchrone à un système externe sur le parcours utilisateur",
               "Délai, disjoncteur et mode dégradé, ou file asynchrone ; niveau de service du tiers dans les exigences.",
               "Release It! (M. Nygard) : points d'intégration ; ISO/IEC 25010 : disponibilité"),
    "STR-07": ("structure", "basse", "Composant sans flux",
               "Relier le composant ou le retirer de l'architecture.", "arc42 §5 : vue en briques"),
    "STR-08": ("structure", "moyenne", "Point unique de défaillance",
               "Redonder le composant (count 2 ou plus), ou accepter l'écart avec sa raison (service managé...).",
               "ISO/IEC 25010 : disponibilité, tolérance aux pannes"),
    "CODE-01": ("code", "moyenne", "Dépendance du code absente de l'architecture",
                "Déclarer le flux s'il est voulu, sinon supprimer la dépendance du code.",
                "Modèle de réflexion (Murphy, Notkin) : divergence entre code et architecture"),
    "CODE-02": ("code", "moyenne", "Cycle de dépendances entre composants dans le code",
                "Casser le cycle : inverser une dépendance (interface, événement) ou déplacer le code commun.",
                "Principe des dépendances acycliques (R. C. Martin)"),
    "CODE-03": ("code", "basse", "Code non rattaché à un composant",
                "Rattacher les fichiers à un composant (code) ou les exclure (.graphifyignore).",
                "arc42 §5 : correspondance entre briques et code"),
    "CODE-04": ("code", "moyenne", "Appel entre services absent de l'architecture",
                "Déclarer le flux s'il est voulu (style async pour un canal), sinon retirer l'appel de la configuration.",
                "Modèle de réflexion (Murphy, Notkin) : divergence ; microservices.io : communication entre services"),
    "CODE-05": ("code", "basse", "Flux déclaré sans trace dans le code ni la configuration",
                "Vérifier le flux (appel par une adresse calculée, passerelle) ou le retirer de l'architecture.",
                "Modèle de réflexion (Murphy, Notkin) : absence"),
    "CODE-06": ("code", "moyenne", "Base de données partagée par plusieurs services",
                "Une base par service propriétaire ; les autres passent par son API ou ses événements.",
                "Database per service (microservices.io)"),
    "CODE-07": ("code", "basse", "Dépôt rattaché à aucun composant",
                "Relier le dépôt à son composant (component du dépôt ou motifs code <dépôt>/...).",
                "arc42 §5 : correspondance entre briques et code"),
    "TRA-01": ("tracabilite", "haute", "Exigence indispensable sans support",
               "Rattacher l'exigence à un composant (refs), une décision ou un scénario, ou la traiter comme écart.",
               "ISO/IEC/IEEE 42010 : chaque préoccupation est traitée"),
    "TRA-02": ("tracabilite", "moyenne", "Exigence non fonctionnelle sans scénario de qualité",
               "Écrire le scénario (stimulus, réponse, mesure) et l'évaluer.",
               f"{ATAM} : arbre d'utilité ; ISO/IEC 25010"),
    "TRA-03": ("tracabilite", "basse", "Composant sans exigence ni décision",
               "Dire quelle exigence ou décision justifie le composant (refs), ou le retirer.",
               "ISO/IEC/IEEE 42010 : justification de l'architecture"),
    "QUA-01": ("qualite", "haute", "Scénario non satisfait sans risque noté",
               "Noter le risque (risks, scenarios) avec sa mesure d'atténuation, ou changer l'architecture.",
               f"{ATAM} : risques"),
    "QUA-02": ("qualite", "moyenne", "Scénario à risque sans risque noté",
               "Noter le risque (risks, scenarios) avec sa mesure d'atténuation.", f"{ATAM} : risques"),
    "QUA-03": ("qualite", "moyenne", "Scénario sans mesure",
               "Donner une mesure vérifiable de la réponse (« 95 % en moins de 2 s »).",
               f"{ATAM} : scénario de qualité (stimulus, environnement, réponse, mesure)"),
    "QUA-04": ("qualite", "basse", "Scénario à vérifier",
               "Évaluer le scénario : satisfait, à risque ou non satisfait, avec la raison.", f"{ATAM} : analyse"),
    # Gravité variable : l'importance du scénario (haute si non donnée).
    "QUA-05": ("qualite", "importance", "Scénario non satisfait",
               "Changer l'architecture pour satisfaire le scénario, ou faire accepter l'écart (accept) avec sa raison.",
               f"{ATAM} : risques"),
    "QUA-06": ("qualite", "moyenne", "Scénario attendu absent",
               "Écrire ce scénario (stimulus, environnement, réponse, mesure) et l'évaluer, ou accepter l'écart "
               "(accept) avec sa raison.",
               f"{ATAM} : scénarios de croissance et d'exploration ; règles de complétude (references/)"),
    "DEC-01": ("decisions", "moyenne", "Aucune décision d'architecture documentée",
               "Documenter les décisions structurantes (ADR).", "arc42 §9 ; ADR (M. Nygard)"),
    "DEC-02": ("decisions", "basse", "Décision encore proposée",
               "Faire accepter la décision ou la remplacer.", "arc42 §9 ; ADR (M. Nygard)"),
    "DEC-03": ("decisions", "basse", "Compromis sans décision qui l'assume",
               "Rattacher le compromis à sa décision (decision).", f"{ATAM} : compromis ; arc42 §9"),
    "RSK-01": ("risques", "haute", "Risque haut sans mesure d'atténuation",
               "Donner la mesure d'atténuation (mitigation) ou changer l'architecture.", f"arc42 §11 ; {ATAM}"),
    "RSK-02": ("risques", "basse", "Risque sans responsable", "Nommer le responsable (owner).", "arc42 §11"),
    # Gravité variable : celle du principe (references.principes de la mission).
    "PRI-01": ("principes", "gravité du principe", "Principe d'architecture du client non respecté",
               "Respecter le principe, ou faire accepter l'écart (accept) avec la raison du client.",
               "principes d'architecture du client (references.principes de mission.json)"),
    # Gravité variable : celle du risque.
    "RSK-03": ("risques", "gravité du risque", "Risque ouvert",
               "Traiter le risque (changer l'architecture) ou le faire accepter (accept) avec sa raison.",
               f"arc42 §11 ; {ATAM}"),
}
# Ce que la description ne montre pas : à vérifier avec l'équipe.
OFF_DESCRIPTION = {
    "Sécurité applicative": "authentification et droits par rôle, validation des entrées, dépendances vulnérables "
                            "(OWASP ASVS)",
    "Données": "propriétaire de chaque donnée, rétention et purge, données personnelles (RGPD)",
    "Exploitation": "journaux corrélés, métriques et alertes, procédures de reprise testées",
    "Performance": "tests de charge sur les scénarios de performance retenus",
    "Évolution": "versionnement des API et des événements, compatibilité ascendante",
    "Organisation": "équipes et frontières des composants (loi de Conway), compétences à acquérir",
}


def cell(text) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def count_of(comp: dict) -> int:
    value = comp.get("count", 1)
    if isinstance(value, int):
        return value
    match = re.match(r"\s*(\d+)", str(value))
    return int(match.group(1)) if match else 1


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
        found["_catalog"] = path.parent / options.get("requirements", "exigences.json")
    return found


def merge(source: dict | None, spec: dict) -> tuple[list[dict], list[dict]]:
    """Composants et flux de l'option, complétés ou précisés (même id) par ceux de la description."""
    comps: dict[str, dict] = {c["id"]: dict(c) for c in (source or {}).get("components", [])}
    for comp in spec.get("components", []):
        comps[comp["id"]] = {**comps.get(comp["id"], {}), **comp}
    flows = [dict(f) for f in (source or {}).get("flows", [])] + [dict(f) for f in spec.get("flows", [])]
    return list(comps.values()), flows


def cycles(nodes: list[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    """Composantes fortement connexes de plus d'un nœud (Tarjan), dans l'ordre des nœuds."""
    graph = {n: sorted({b for a, b in edges if a == n and b != n}, key=nodes.index) for n in nodes}
    index, low, stack, on, found, counter = {}, {}, [], set(), [], [0]

    def visit(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on.add(node)
        for nxt in graph[node]:
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            group = []
            while True:
                item = stack.pop()
                on.discard(item)
                group.append(item)
                if item == node:
                    break
            if len(group) > 1:
                found.append(sorted(group, key=nodes.index))

    for node in nodes:
        if node not in index:
            visit(node)
    return sorted(found, key=lambda g: nodes.index(g[0]))


def longest_sync(start: str, sync: dict[str, list[str]]) -> list[str]:
    """Plus long chemin synchrone sans boucle depuis start (graphes de quelques dizaines de composants)."""
    best = [start]

    def walk(path):
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        for nxt in sync.get(path[-1], []):
            if nxt not in path:
                walk(path + [nxt])

    walk([start])
    return best


def glob_regex(pattern: str) -> re.Pattern:
    """Motif de fichiers (src/api/**, *.py) ; un chemin sans joker vaut pour le dossier entier."""
    pattern = pattern.strip("/").removeprefix("./")
    if not any(c in pattern for c in "*?["):
        return re.compile(re.escape(pattern) + r"(/.*)?")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out += {"*": "[^/]*", "?": "[^/]"}.get(pattern[i], re.escape(pattern[i]))
            i += 1
    return re.compile(out)


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


CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".env", ".properties", ".toml", ".ini", ".conf", ".cfg", ".xml", ".tf",
                   ".hcl"}
CONFIG_NAMES = re.compile(r"^(dockerfile|(docker-)?compose[\w.-]*|\.env[\w.-]*)$", re.I)
SKIP_DIRS = {".git", "node_modules", "vendor", "target", "build", "dist", ".venv", "venv", "__pycache__",
             "graphify-out", ".idea", ".vscode", ".terraform"}
URL = re.compile(r"\b(?:jdbc:)?([a-z][a-z0-9+.-]*)://(?:[^\s/@\"'<>]*@)?([A-Za-z0-9_-][A-Za-z0-9_.-]*)(?::\d+)?"
                 r"(/[A-Za-z0-9_.-]*)?", re.I)
DB_SCHEMES = {"postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongodb+srv", "sqlserver", "oracle",
              "cockroachdb"}
ASYNC_SCHEMES = {"amqp", "amqps", "kafka", "nats", "mqtt"}
MAX_FILES, MAX_BYTES = 3000, 512_000


def config_files(root: Path):
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= MAX_FILES:
            return
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]) or not path.is_file():
            continue
        if path.suffix.lower() in CONFIG_SUFFIXES or CONFIG_NAMES.match(path.name):
            if path.stat().st_size <= MAX_BYTES:
                count += 1
                yield path


def asyncapi_channels(doc: dict) -> tuple[set[str], set[str]]:
    """Canaux envoyés et reçus d'un document AsyncAPI 2 (subscribe : l'application envoie) ou 3 (action)."""
    sends, receives = set(), set()
    channels = doc.get("channels") or {}
    if str(doc.get("asyncapi", "")).startswith("2"):
        for name, channel in channels.items():
            if isinstance(channel, dict):
                (sends if "subscribe" in channel else set()).add(name)
                (receives if "publish" in channel else set()).add(name)
        return sends, receives
    for operation in (doc.get("operations") or {}).values():
        if not isinstance(operation, dict):
            continue
        ref = ((operation.get("channel") or {}).get("$ref") or "").rsplit("/", 1)[-1]
        channel = channels.get(ref) or {}
        name = channel.get("address") or ref
        if name:
            (sends if operation.get("action") == "send" else receives).add(name)
    return sends, receives


def service_calls(repos: list[dict], comps: list[dict], warnings: list[str]) -> tuple[list[dict], dict, dict]:
    """Appels entre services lus dans la configuration et les contrats de chaque dépôt : URL vers un autre
    service ou un composant (hôte = dépôt, alias ou identifiant de composant), canaux AsyncAPI ; bases de
    données citées. Rend les appels, les bases (clé -> dépôts) et le composant de chaque dépôt."""
    ids = {c["id"].lower(): c["id"] for c in comps}
    owner = {}
    for repo in repos:
        owner[repo["name"]] = repo.get("component") or ids.get(repo["name"].lower())
    names: dict[str, str] = dict(ids)
    for repo in repos:
        if owner[repo["name"]]:
            for alias in [repo["name"], *repo.get("aliases", [])]:
                names[alias.lower()] = owner[repo["name"]]
    try:
        import yaml
    except ImportError:
        yaml = None
        warnings.append("code : pyyaml absent, canaux AsyncAPI non lus (uv run installe pyyaml)")
    calls: dict[tuple, dict] = {}
    databases: dict[str, set[str]] = {}
    sends: dict[str, set[str]] = {}
    receives: dict[str, set[str]] = {}
    for repo in repos:
        root = Path(repo["root"])
        if not root.is_dir():
            continue
        source = owner[repo["name"]]
        for path in config_files(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            where = f"{repo['name']}/{path.relative_to(root).as_posix()}"
            for match in URL.finditer(text):
                scheme, host, base_path = match.group(1).lower(), match.group(2).lower(), match.group(3) or ""
                if scheme in DB_SCHEMES:
                    databases.setdefault(f"{host}{base_path}", set()).add(repo["name"])
                target = names.get(host) or names.get(host.split(".")[0])
                if source and target and target != source:
                    style = "async" if scheme in ASYNC_SCHEMES else "sync"
                    calls.setdefault((source, target), {"from": source, "to": target, "style": style,
                                                        "via": f"{scheme}://{host}", "file": where})
            if yaml is not None and path.suffix.lower() in (".yaml", ".yml", ".json") and "asyncapi" in text[:2000]:
                try:
                    doc = yaml.safe_load(text)
                except yaml.YAMLError:
                    continue
                if isinstance(doc, dict) and doc.get("asyncapi"):
                    out, inn = asyncapi_channels(doc)
                    for name in out:
                        sends.setdefault(name, set()).add(repo["name"])
                    for name in inn:
                        receives.setdefault(name, set()).add(repo["name"])
    for channel, producers in sorted(sends.items()):
        for producer in sorted(producers):
            for consumer in sorted(receives.get(channel, set())):
                a, b = owner.get(producer), owner.get(consumer)
                if a and b and a != b:
                    calls.setdefault((a, b), {"from": a, "to": b, "style": "async", "via": f"canal {channel}",
                                              "file": f"{producer} > {consumer}"})
    return list(calls.values()), databases, owner


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


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def count_of(comp: dict) -> int:
    """Nombre d'instances d'un composant : count (2, « 2-10 » : le minimum), 1 par défaut."""
    found = re.match(r"\s*(\d+)", str(comp.get("count", 1)))
    return int(found.group(1)) if found else 1


def fits(item: dict, field: str, value) -> bool:
    if field == "count_min":
        return count_of(item) >= value
    if field == "style":
        return item.get("style", "sync") == value
    return bool(re.search(value, plain(item.get(field, ""))))


def said(item: dict, field: str, value, required: bool) -> str:
    """Écart à un principe, en clair : ce qui est exigé ou interdit, et ce que l'élément a."""
    if field == "count_min":
        return f"{value} instances au moins, {count_of(item)} décrite(s)"
    if field == "style":
        return f"flux {value} " + ("exigé" if required else "interdit")
    have = item.get(field) or "absent"
    return f"{field} « {have} » " + (f"hors de « {value} »" if required else f"interdit (« {value} »)")


def principles(rules: list[dict], comps: list[dict], flows: list[dict]) -> list[tuple[str, str, str]]:
    """(principe/élément, message, gravité) des écarts aux principes d'architecture du client."""
    roles = {c["id"]: c.get("role", "system") for c in comps}
    broken = []
    for rule in rules:
        select = rule.get("select", {})
        if rule["target"] == "composants":
            items = [(c["id"], c) for c in comps
                     if (not select.get("roles") or c.get("role", "system") in select["roles"])]
        else:
            items = [(f"{f['from']}>{f['to']}", f) for f in flows
                     if (not select.get("from_roles") or roles.get(f["from"]) in select["from_roles"])
                     and (not select.get("to_roles") or roles.get(f["to"]) in select["to_roles"])
                     and (not select.get("style") or f.get("style", "sync") == select["style"])]
        for element, item in items:
            if any(not fits(item, key, select[key]) for key in ("tech", "label") if select.get(key)):
                continue
            why = [said(item, k, v, True) for k, v in rule.get("require", {}).items() if not fits(item, k, v)]
            why += [said(item, k, v, False) for k, v in rule.get("forbid", {}).items() if fits(item, k, v)]
            if why:
                broken.append((f"{rule['id']}/{element}", f"{rule['label']} ({', '.join(why)})",
                               rule.get("severity", "moyenne")))
    return broken


def expected(rules: list[dict], catalog: dict, comps: list[dict], scenarios) -> list[dict]:
    """Règles de scénario attendu qui s'appliquent (exigence non fonctionnelle indispensable ou importante de
    la catégorie, rôle de composant) et qu'aucun scénario de leur attribut ne suit."""
    categories = {r.get("category") for r in catalog.values()
                  if r.get("status", "retenue") == "retenue" and r.get("priority") in ("indispensable", "importante")
                  and (r.get("nature") == "non-fonctionnelle" or r["id"].startswith("ENF"))}
    roles = {c.get("role", "system") for c in comps}
    missing = []
    for rule in rules:
        when = rule.get("when", {})
        if (when.get("categories") and not categories & set(when["categories"])) \
                or (when.get("roles") and not roles & set(when["roles"])):
            continue
        texts = [plain(f"{s['stimulus']} {s.get('environment', '')} {s['response']}")
                 for s in scenarios if s["attribute"] == rule["attribute"]]
        if not any(re.search(rule["pattern"], text) for text in texts):
            missing.append(rule)
    return missing


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
    catalog_path = path.parent / options.get("requirements", "exigences.json")
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
    invalid = validate(spec, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], option=option["id"], scenarios=len(scenarios))
    return report


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
    path = base / spec["requirements"] if spec.get("requirements") else (source or {}).get("_catalog")
    catalog = load_catalog(path, errors, warnings)
    comps, flows = merge(source, spec)
    if not comps:
        errors.append("components : aucun composant, ni dans la description ni dans source")
    byid = {c["id"]: c for c in comps}
    ids = list(byid)
    scenarios = {s["id"]: s for s in spec.get("scenarios", [])}
    risks = spec.get("risks", [])
    decisions = {d["id"]: d for d in spec.get("decisions", [])}
    layers = spec.get("layers", [])

    # Références croisées : une erreur, pas un constat.
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
            if refs and path is None:
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
    if errors:
        return {"errors": errors, "warnings": warnings}

    # Structure.
    role = {c["id"]: c.get("role", "system") for c in comps}
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
    reach: set[str] = set()
    persons = [i for i in ids if role[i] == "person"]
    for person in persons:
        todo = [person]
        while todo:
            node = todo.pop()
            for nxt in sync[node]:
                if nxt not in reach:
                    reach.add(nxt)
                    todo.append(nxt)
        path = longest_sync(person, sync)
        if len(path) - 1 > CHAIN:
            add("STR-05", ">".join(path), f"{len(path) - 1} sauts synchrones depuis {person}")
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

    # Traçabilité des exigences.
    trace = None
    if catalog:
        carried: dict[str, dict[str, list[str]]] = {}
        for kind, items in (("components", comps), ("decisions", decisions.values()),
                            ("scenarios", scenarios.values())):
            for item in items:
                for ref in item.get("refs", []):
                    carried.setdefault(ref, {}).setdefault(kind, []).append(item["id"])
        gaps = (source or {}).get("gaps", {})
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
        trace = {"requirements": len(retained), "uncarried": uncarried, "without_scenario": without,
                 "rows": [(r, carried.get(r["id"], {})) for r in retained]}
    in_decision = {c for d in decisions.values() for c in d.get("components", [])}
    if catalog:
        for comp in comps:
            if role[comp["id"]] in APPLICATIVE and not comp.get("refs") and comp["id"] not in in_decision:
                add("TRA-03", comp["id"], comp["label"])

    # Scénarios, décisions, risques.
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
        for rule in expected(rules or [], catalog, comps, scenarios.values()):
            add("QUA-06", rule["id"], f"{rule['label']} ({ATTRIBUTES.get(rule['attribute'], rule['attribute'])})")
    for element, message, severity in principles(client or [], comps, flows):
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

    rules = len(RULES) - (0 if spec.get("code") is not None else sum(1 for r in RULES.values() if r[0] == "code")) \
        - (0 if client else 1) + len(client or [])
    # Piliers Well-Architected de la description cloud (skill well-architected-review).
    cloud = None
    if spec.get("cloud"):
        wa = load_module("well-architected-review", "wa_check.py")
        if wa is None or wa.MISSING:
            warnings.append("cloud : revue Well-Architected non faite : "
                            + absent("well-architected-review", "wa_check.py") + " (et cloud-architecture)")
        else:
            path = base / spec["cloud"]
            described = load_json(path, "cloud", errors)
            invalid = wa.validate(described, wa.__file__) if described is not None else []
            errors += [f"cloud : {path.name} : {e}" for e in invalid]
            if described is not None and not invalid:
                wa_findings, wa_errors, _ = wa.check(described)
                errors += [f"cloud : {e}" for e in wa_errors]
                for f in wa_findings:
                    if f["pillar"] != "conventions":
                        findings.append({"rule": f["rule"], "axis": "well-architected", "severity": f["severity"],
                                         "element": f["element"],
                                         "message": f"{wa.PILLARS[f['pillar']]} : {f['message']}",
                                         "fix": f["fix"], "ref": f["ref"], "accepted": None})
                rules += sum(1 for v in wa.RULES.values() if v[0] != "conventions")
                cloud = str(path)

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
                errors: list[str]) -> dict | None:
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
    severities = ("haute", "moyenne", "basse")
    rank = lambda s: severities.index(s) if s in severities else len(severities)  # noqa: E731
    constats = []
    for f in sorted(found["findings"], key=lambda f: (rank(f["severity"]), f["rule"], f["element"])):
        rel = f"{base}/Constats/{title}/{v.safe_name(f['rule'] + ' ' + f['element'])}"
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
        rel = f"{base}/Risques/{title}/{v.safe_name(r['id'])}"
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
    report = notes.attach(f"{base}/Rapports/{title}/{out.name}", out) if out.is_file() else f"`{out.name}`"
    kind = {"favorable": "success", "favorable avec réserves": "note"}.get(verdict, "danger")
    body = [f"# Revue d'architecture : {spec['title']}", ""]
    body += v.callout(kind, f"Avis : {verdict}", [
        v.count(len(open_), "constat ouvert") + (f", dont {v.number(high)} de gravité haute" if high else "")
        + f" ; {v.count(len(risques), 'risque')}."])
    body += [f"Revue complète : {report}."]
    for label, items in (("Constats ouverts", [c for c in constats if not c[1]["accepted"]]),
                         ("Constats acceptés", [c for c in constats if c[1]["accepted"]])):
        if items:
            body += ["", f"## {label}", ""] + [f"- {v.link(rel, heading)} ({f['severity']}) : {f['element']}"
                                              for rel, f, heading in items]
    if risques:
        body += ["", "## Risques", ""] + [f"- {v.link(rel, r['id'] + ' ' + v.short(r['text']))} ({r['severity']})"
                                         for rel, r in risques]
    evalue = [(p, a) for p, a in ((option_rel, f"Option {option}"), (f"{base}/ADR architecture", "ADR")) if p]
    notes.add(review_rel, "revue-architecture", {"avis": VERDICTS[verdict], "date": None}, {"evalue": evalue}, body,
              ["architecture"])
    # Constats et risques d'une revue précédente qui ne sont plus relevés : notes générées retirées.
    result = notes.write(errors, cleanup=(f"{base}/Constats/{title}", f"{base}/Risques/{title}"))
    return {**result, "folder": base} if result else None


def accept(findings: list[dict], accepted: dict, warnings: list[str]) -> None:
    used = set()
    for finding in findings:
        for key in (f"{finding['rule']}@{finding['element']}", finding["rule"]):
            if key in accepted:
                finding["accepted"] = accepted[key]
                used.add(key)
                break
    warnings += [f"acceptation « {k} » sans constat correspondant" for k in accepted if k not in used]


def verdict_of(open_: list[dict]) -> str:
    if any(f["severity"] == "haute" for f in open_):
        return "défavorable"
    if any(f["severity"] == "moyenne" for f in open_):
        return "favorable avec réserves"
    return "favorable"


def markdown(spec: dict, found: dict, verdict: str) -> str:
    findings, scenarios = found["findings"], found["scenarios"]
    open_ = [f for f in findings if not f["accepted"]]
    lines = [f"# Revue d'architecture : {spec['title']}", ""]
    if spec.get("context"):
        lines += [spec["context"], ""]
    if spec.get("source"):
        lines += [f"Option revue : {spec['source']['option']} (`{spec['source']['options']}`).", ""]
    lines += [f"**Avis : {verdict}** ({sum(f['severity'] == 'haute' for f in open_)} constat(s) haut(s), "
              f"{sum(f['severity'] == 'moyenne' for f in open_)} moyen(s), "
              f"{sum(f['severity'] == 'basse' for f in open_)} bas ouverts ; "
              f"{len(findings) - len(open_)} accepté(s)).", "",
              f"Contrôle par `arch_review.py` ({found['rules']} règles) de la description écrite pour la revue : "
              f"{len(found['comps'])} composants, {len(found['flows'])} flux, {len(scenarios)} scénarios de qualité. "
              "Les points hors de la description sont listés à la fin.", "",
              "## Synthèse", "", "| Axe | Haute | Moyenne | Basse | Acceptés |", "| --- | --- | --- | --- | --- |"]
    for key, name in AXES.items():
        mine = [f for f in findings if f["axis"] == key]
        if key in ("code", "well-architected") and not mine and not found[{"code": "code", "well-architected": "cloud"}[key]]:
            continue
        still = [f for f in mine if not f["accepted"]]
        lines.append(f"| {name} | " + " | ".join(str(sum(f["severity"] == s for f in still)) for s in SEVERITIES)
                     + f" | {len(mine) - len(still)} |")

    lines += ["", "## Arbre d'utilité", ""]
    if not scenarios:
        lines.append("Aucun scénario de qualité.")
    for attr, name in ATTRIBUTES.items():
        mine = [s for s in scenarios.values() if s["attribute"] == attr]
        if not mine:
            continue
        lines += [f"### {name}", "", "| ID | Scénario | Mesure | Importance / difficulté | Exigences | Évaluation |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for s in mine:
            text = s["stimulus"] + (f" ({s['environment']})" if s.get("environment") else "") + f" : {s['response']}"
            weight = f"{s.get('importance', '-')} / {s.get('difficulty', '-')}"
            status = STATUS[s["status"]] + (f" : {s['note']}" if s.get("note") else "")
            lines.append(f"| {s['id']} | {cell(text)} | {cell(s.get('measure', '-'))} | {weight} | "
                         f"{', '.join(s.get('refs', [])) or '-'} | {cell(status)} |")
        lines.append("")
    if lines[-1] == "":
        lines.pop()

    lines += ["", "## Constats", ""]
    if not findings:
        lines.append("Aucun constat.")
    else:
        lines += ["| ID | Règle | Axe | Gravité | Élément | Constat | Correction | Référence | Statut |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for index, f in enumerate(findings, 1):
            status = f"accepté : {f['accepted']}" if f["accepted"] else "à traiter"
            lines.append(f"| C{index:02d} | {f['rule']} | {AXES[f['axis']]} | {f['severity']} | {cell(f['element'])} | "
                         f"{cell(f['message'])} | {cell(f['fix'])} | {cell(f['ref'])} | {cell(status)} |")

    lines += ["", "## Risques", ""]
    if not spec.get("risks"):
        lines.append("Aucun risque noté.")
    else:
        accepted = {f["element"]: f["accepted"] for f in findings if f["rule"] in ("RSK-01", "RSK-03")}
        lines += ["| ID | Risque | Gravité | Scénarios | Atténuation | Responsable | Statut |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in spec["risks"]:
            status = f"accepté : {accepted[r['id']]}" if accepted.get(r["id"]) else "ouvert"
            lines.append(f"| {r['id']} | {cell(r['text'])} | {r['severity']} | {', '.join(r.get('scenarios', [])) or '-'} | "
                         f"{cell(r.get('mitigation', 'à définir'))} | {cell(r.get('owner', 'à désigner'))} | "
                         f"{cell(status)} |")
    if spec.get("sensitivities") or spec.get("tradeoffs"):
        lines += ["", "## Points de sensibilité et compromis", ""]
        for item in spec.get("sensitivities", []):
            where = ", ".join(item.get("components", []) + item.get("scenarios", []))
            lines.append(f"- Sensibilité : {item['text']}" + (f" ({where})" if where else ""))
        for item in spec.get("tradeoffs", []):
            names = " contre ".join(ATTRIBUTES[a] for a in item["attributes"])
            lines.append(f"- Compromis {names} : {item['text']}"
                         + (f" (décision {item['decision']})" if item.get("decision") else " (sans décision)"))
    lines += ["", "## Décisions", ""]
    if not found["decisions"]:
        lines.append("Aucune décision documentée.")
    else:
        lines += ["| ID | Décision | Statut | Exigences | Composants |", "| --- | --- | --- | --- | --- |"]
        for d in found["decisions"].values():
            title = d["title"] + (f" (`{d['file']}`)" if d.get("file") else "")
            lines.append(f"| {d['id']} | {cell(title)} | {DECIDED[d['status']]} | {', '.join(d.get('refs', [])) or '-'} | "
                         f"{', '.join(d.get('components', [])) or '-'} |")
    if found["trace"]:
        lines += ["", "## Traçabilité des exigences", "",
                  "| Exigence | Titre | Priorité | Composants | Décisions | Scénarios |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for req, by in found["trace"]["rows"]:
            lines.append(f"| {req['id']} | {cell(req.get('title', ''))} | {req.get('priority', '-')} | "
                         + " | ".join(", ".join(by.get(k, [])) or "-" for k in ("components", "decisions", "scenarios"))
                         + " |")
    if found["code"]:
        code = found["code"]
        lines += ["", "## Code et architecture", "",
                  f"Graphe du code par graphify (analyse locale du code ; seuls les liens extraits du code comptent) : "
                  f"`{code['graph']}`. "
                  f"{code['files']} fichier(s), dont {code['unmapped']} non rattaché(s) ; "
                  f"{code['dependencies']} dépendance(s) entre composants, dont {len(code['undeclared'])} "
                  "absente(s) de l'architecture."]
        if "repos" in code:
            lines += ["", f"{code['repos']} dépôt(s). Appels entre services lus dans la configuration et les contrats "
                      f"(URL d'un autre service, canaux AsyncAPI) : {len(code['calls'])}.", ""]
            lines += [f"- {cell(c)}" for c in code["calls"]] or ["- aucun"]
            if code["shared_databases"]:
                lines += ["", "Bases citées par plusieurs dépôts :", ""] + [f"- {cell(s)}" for s in code["shared_databases"]]
    lines += ["", "## À vérifier hors de la description", ""]
    lines += [f"- **{k}** : {v}." for k, v in OFF_DESCRIPTION.items()]
    return "\n".join(lines) + "\n"


def list_rules() -> str:
    return "\n".join(f"{rule} {AXES[a]} ({s}) : {title}" for rule, (a, s, title, _, _) in RULES.items())


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
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
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
    args.vault, args.folder, scoped = workspace.vault_target(args.vault, args.folder, [args.spec])
    if scoped:
        print(json.dumps({"input": str(args.spec), "errors": scoped, "warnings": []}, ensure_ascii=False))
        return 1
    if bool(args.vault) != bool(args.folder):
        parser.error("--vault et --folder vont ensemble")
    if args.vault and not args.vault.is_dir():
        print(json.dumps({"input": str(args.spec), "errors": [f"--vault : dossier introuvable {args.vault}"],
                          "warnings": []}, ensure_ascii=False))
        return 1
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    invalid = validate(spec, __file__)
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
    out = args.out or args.spec.with_name(stem + (".md" if stem.endswith("revue") else ".revue.md"))
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
            result["vault"] = write_vault(args.vault, args.folder, spec, found, verdict, out, errors)
    print(json.dumps(result, ensure_ascii=False))
    limit = SEVERITIES.index(args.fail_on) if args.fail_on in SEVERITIES else -1
    failing = any(SEVERITIES.index(f["severity"]) <= limit for f in open_)
    return 1 if errors or failing else 0


if __name__ == "__main__":
    sys.exit(main())
