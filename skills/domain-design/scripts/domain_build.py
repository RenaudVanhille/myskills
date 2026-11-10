# /// script
# requires-python = ">=3.10"
# ///
"""Contrôle le découpage en domaines (DDD) d'une solution et recommande son style : monolithe modulaire, mixte ou microservices.

Le modèle décrit les sous-domaines (cœur, support, générique), les contextes
bornés (entités possédées et utilisées, exigences portées, équipe, langage,
besoins propres) et la carte des contextes (amont, aval, motifs
d'intégration), puis répond aux facteurs de la grille de style. Le script,
et non le modèle :

- vérifie les références : sous-domaine, contexte, exigence (exigences.json
  de requirements-catalog), entité (description de data-model) ;
- vérifie qu'une entité n'a qu'un contexte propriétaire et qu'un contexte
  n'utilise que des entités possédées ailleurs ;
- calcule la cohésion de chaque contexte et le couplage entre contextes
  (relations du modèle de données et entités utilisées ; sans modèle,
  entités possédées et entités utilisées), repère les
  dépendances absentes de la carte, les cycles, le noyau partagé, les
  exigences fonctionnelles sans contexte ;
- calcule le style recommandé avec la grille (équipes, contextes, besoins
  propres, maturité DevOps, stabilité du domaine, cohérence, délai,
  couplage) et les contextes à extraire en services ;
- écrit <nom>.md (sous-domaines, contextes et langage, carte, couplage,
  grille et recommandation), <nom>.styles.json (composants et flux de chaque
  style, à reprendre dans options.json d'architecture-options) et la carte
  des contextes en draw.io (<nom>.carte.drawio, par drawio_build.py du skill
  drawio-diagram, qui la contrôle ; --export pour l'image).

Avec `--vault`, une note decoupage-domaines et une note contexte-borne par
contexte vont dans le vault Obsidian du workflow, selon son ontologie.

    uv run scripts/domain_build.py DOMAINES.json [--out-dir DOSSIER] [--export png|svg]
                                   [--vault VAULT --folder DOSSIER_DU_VAULT] | --schema
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, find_script, require_module, run_script, schema_of  # noqa: E402
from spec_schema import check, print_schema, read_spec, schema_option  # noqa: E402
from text_tools import near as hint, slash_cell as cell  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")
workspace = require_module("mission-workspace", "lib/workspace.py")

KINDS = {"coeur": "cœur", "support": "support", "generique": "générique"}
PATTERNS = {"partenariat": "partenariat", "client-fournisseur": "client-fournisseur", "conformiste": "conformiste",
            "acl": "couche anticorruption", "open-host": "service hôte ouvert", "langage-publie": "langage publié",
            "noyau-partage": "noyau partagé", "chemins-separes": "chemins séparés"}
NEEDS = {"echelle": "montée en charge propre", "cadence": "déploiements indépendants",
         "isolation": "isolement (pannes, sécurité, conformité)", "technologie": "technologie propre"}
STYLES = {"monolithe-modulaire": "monolithe modulaire", "mixte": "monolithe modulaire et services extraits",
          "microservices": "microservices"}
# Facteur -> valeur -> (effet sur le score, explication). Score positif : vers les microservices.
FACTORS = {
    "devops": {"faible": (-3, "sans intégration et déploiement continus ni observabilité, des services distribués "
                              "ne s'exploitent pas : prérequis absent"),
               "moyenne": (-1, "outillage partiel : chaque service ajouté coûte en exploitation"),
               "forte": (1, "intégration, déploiement et observabilité en place")},
    "stabilite": {"incertaine": (-2, "frontières encore mouvantes : un découpage en services les figerait "
                                     "(monolithe d'abord)"),
                  "connue": (1, "frontières connues et stables")},
    "coherence": {"forte": (-2, "transactions fortes entre contextes : la distribution impose sagas et compensation"),
                  "eventuelle": (1, "cohérence à terme acceptée entre contextes")},
    "delai": {"court": (-1, "délai court : la distribution allonge la mise en place"),
              "normal": (0, "délai sans contrainte particulière")},
}
LABELS = {"devops": "maturité DevOps", "stabilite": "stabilité du domaine", "coherence": "cohérence entre contextes",
          "delai": "délai", "eventuelle": "éventuelle"}
SIZE = 12          # entités au-delà desquelles un contexte est large
COUPLED, LOOSE = 0.5, 0.25  # part des relations entre contextes : couplage fort, faible
MICRO = 4          # score à partir duquel les microservices sont recommandés


def load_json(path: Path, label: str, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{label} : illisible {path} ({error})")
        return None


def load_ref(base: Path, spec: dict, key: str, skill: str, script: str, errors: list[str], warnings: list[str]):
    """Fichier d'un autre skill cité par la description (exigences, modèle de données), validé par son schéma."""
    if not spec.get(key):
        return None
    path = base / spec[key]
    data = load_json(path, key, errors)
    if data is None:
        return None
    schema = schema_of(skill, script)
    if schema is None:
        warnings.append(f"{key} : {path.name} non vérifié : " + absent(skill, script))
        return data
    invalid = check(data, schema)
    if invalid:
        errors += [f"{key} : {path.name} : {e}" for e in invalid[:10]]
        return None
    return data


def cycles(nodes: list[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    """Composantes fortement connexes de plus d'un nœud (Tarjan), dans l'ordre des nœuds."""
    index, low, stack, on, found, counter = {}, {}, [], set(), [], [0]

    def visit(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on.add(node)
        for a, b in sorted(edges):
            if a != node:
                continue
            if b not in index:
                visit(b)
                low[node] = min(low[node], low[b])
            elif b in on:
                low[node] = min(low[node], index[b])
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
    return found


def analyse(spec: dict, base: Path) -> dict:
    """Contrôles, couplage et grille de style d'une description validée. Sert aussi à architecture-review."""
    errors: list[str] = []
    warnings: list[str] = []
    subs = {s["id"]: s for s in spec["subdomains"]}
    ctxs = {c["id"]: c for c in spec["contexts"]}
    order = list(ctxs)
    for name, items in (("subdomains", spec["subdomains"]), ("contexts", spec["contexts"])):
        seen = [i["id"] for i in items]
        errors += [f"{name} : identifiant en double « {i} »" for i in sorted({i for i in seen if seen.count(i) > 1})]

    catalog = load_ref(base, spec, "requirements", "requirements-catalog", "req_build.py", errors, warnings)
    reqs = {r["id"]: r for r in (catalog or {}).get("requirements", [])}
    model = load_ref(base, spec, "model", "data-model", "model_build.py", errors, warnings)
    entities = [e["name"] for e in (model or {}).get("entities", [])]

    owner: dict[str, str] = {}
    for i, ctx in enumerate(spec["contexts"]):
        where = f"contexts/{i} ({ctx['id']})"
        if ctx["subdomain"] not in subs:
            errors.append(f"{where}/subdomain : sous-domaine inconnu « {ctx['subdomain']} »" + hint(ctx["subdomain"], subs))
        for name in ctx.get("entities", []):
            if model is not None and name not in entities:
                errors.append(f"{where}/entities : entité « {name} » absente du modèle de données" + hint(name, entities))
            if name in owner and owner[name] != ctx["id"]:
                errors.append(f"{where}/entities : entité « {name} » déjà possédée par « {owner[name]} » : un seul "
                              "contexte propriétaire, l'autre la cite dans uses et la lit par l'API ou les événements "
                              "du propriétaire (ou deux entités distinctes, une par contexte)")
            owner.setdefault(name, ctx["id"])
        if catalog is not None:
            for ref in ctx.get("refs", []):
                if ref not in reqs:
                    errors.append(f"{where}/refs : exigence inconnue « {ref} »" + hint(ref, reqs))
        elif ctx.get("refs") and not spec.get("requirements"):
            warnings.append(f"{where}/refs : exigences citées sans catalogue (requirements) : non vérifiées")
    for i, ctx in enumerate(spec["contexts"]):
        for name in ctx.get("uses", []):
            if name in ctx.get("entities", []):
                errors.append(f"contexts/{i} ({ctx['id']})/uses : « {name} » est déjà possédée par ce contexte")
            elif name not in owner:
                errors.append(f"contexts/{i} ({ctx['id']})/uses : entité « {name} » possédée par aucun contexte"
                              + hint(name, owner))
    pairs, declared = set(), {}
    for i, rel in enumerate(spec.get("relations", [])):
        where = f"relations/{i}"
        for end in ("upstream", "downstream"):
            if rel[end] not in ctxs:
                errors.append(f"{where}/{end} : contexte inconnu « {rel[end]} »" + hint(rel[end], ctxs))
        if rel["upstream"] == rel["downstream"]:
            errors.append(f"{where} : un contexte ne dépend pas de lui-même ({rel['upstream']})")
        key = frozenset((rel["upstream"], rel["downstream"]))
        if key in pairs:
            errors.append(f"{where} : relation en double entre {rel['upstream']} et {rel['downstream']} "
                          "(un seul lien, avec tous ses motifs dans patterns)")
        pairs.add(key)
        declared[key] = rel
    decision = spec.get("decision") or {}
    for ref in decision.get("extract", []):
        if ref not in ctxs:
            errors.append(f"decision/extract : contexte inconnu « {ref} »" + hint(ref, ctxs))
    if errors:
        return {"errors": errors, "warnings": warnings}

    # Propriété des entités et couplage.
    if model is not None:
        lost = [e for e in entities if e not in owner]
        if lost:
            warnings.append(f"{vault_ontology.count(len(lost), 'entité')} du modèle sans contexte propriétaire : "
                            + ", ".join(lost))
    links: dict[frozenset, int] = {}
    stats = {c: {"internal": 0, "external": 0} for c in order}
    for rel in (model or {}).get("relations", []):
        a, b = owner.get(rel["from"]), owner.get(rel["to"])
        if not a or not b:
            continue
        if a == b:
            stats[a]["internal"] += 1
        else:
            stats[a]["external"] += 1
            stats[b]["external"] += 1
            links[frozenset((a, b))] = links.get(frozenset((a, b)), 0) + 1
    if model is None:
        # Sans modèle de données (cas d'un projet neuf : domaines d'abord, modèle par contexte ensuite),
        # chaque entité possédée compte comme un lien interne à son contexte.
        for ctx in spec["contexts"]:
            stats[ctx["id"]]["internal"] += len(ctx.get("entities", []))
    # Une entité utilisée compte comme lien quand le modèle ne relie pas déjà les deux contextes.
    for ctx in spec["contexts"]:
        for name in ctx.get("uses", []):
            key = frozenset((ctx["id"], owner[name]))
            if model is None or key not in links:
                links[key] = links.get(key, 0) + 1
                stats[ctx["id"]]["external"] += 1
    total = sum(s["internal"] for s in stats.values()) + sum(links.values())
    cross = sum(links.values())
    ratio = round(cross / total, 2) if total else 0.0
    for key in sorted(links, key=lambda k: sorted(k, key=order.index)):
        if key not in declared:
            a, b = sorted(key, key=order.index)
            warnings.append(f"dépendance entre {a} et {b} ({vault_ontology.count(links[key], 'lien')} de données) "
                            "absente de la carte des contextes : déclarer la relation (amont, aval, motif)")

    # Carte des contextes : cycles, noyau partagé.
    edges = {(r["downstream"], r["upstream"]) for r in spec.get("relations", [])
             if "chemins-separes" not in r["patterns"]}
    loops = cycles(order, edges)
    for group in loops:
        warnings.append(f"cycle entre contextes {' > '.join(group + group[:1])} : l'un doit être en amont de "
                        "l'autre (événements, ou fusion des contextes)")
    for rel in spec.get("relations", []):
        if "noyau-partage" in rel["patterns"]:
            warnings.append(f"noyau partagé entre {rel['upstream']} et {rel['downstream']} : couplage fort, à garder "
                            "petit et dans une même équipe")
        if "chemins-separes" in rel["patterns"] and len(rel["patterns"]) > 1:
            warnings.append(f"relation {rel['upstream']} > {rel['downstream']} : chemins séparés exclut tout autre motif")

    # Sous-domaines et contextes.
    for sid, sub in subs.items():
        if not any(c["subdomain"] == sid for c in ctxs.values()):
            warnings.append(f"sous-domaine {sid} sans contexte borné")
    for cid, ctx in ctxs.items():
        if not ctx.get("entities") and not ctx.get("refs"):
            warnings.append(f"contexte {cid} sans entité ni exigence : à justifier ou retirer")
        if len(ctx.get("entities", [])) > SIZE:
            warnings.append(f"contexte {cid} large ({len(ctx['entities'])} entités) : sous-contextes possibles")
        if subs[ctx["subdomain"]]["kind"] == "coeur" and not ctx.get("team"):
            warnings.append(f"contexte {cid} du cœur de métier sans équipe (team)")
    if catalog is not None:
        carried = {r for c in ctxs.values() for r in c.get("refs", [])}
        functional = [r["id"] for r in reqs.values()
                      if (r.get("nature") or {"EF": "fonctionnelle"}.get(r["id"].split("-")[0])) == "fonctionnelle"
                      and r.get("status", "retenue") == "retenue" and r.get("priority") != "hors-perimetre"]
        missing = [r for r in functional if r not in carried]
        if missing:
            warnings.append(f"{vault_ontology.count(len(missing), 'exigence fonctionnelle')} sans contexte (refs) : "
                            + ", ".join(missing[:10]) + (" ..." if len(missing) > 10 else ""))

    style = grid(spec, ctxs, ratio, loops, warnings)
    if decision.get("style") and decision["style"] != style["recommended"]:
        warnings.append(f"decision : style {STYLES[decision['style']]} retenu contre la recommandation "
                        f"({STYLES[style['recommended']]}) : raison à noter au journal")
    return {"errors": errors, "warnings": warnings, "owner": owner, "links": links, "stats": stats,
            "coupling": {"relations": total, "cross": cross, "ratio": ratio,
                         "basis": "modele" if model is not None else "contextes"}, "cycles": loops, "style": style,
            "catalog": reqs, "model": model}


def grid(spec: dict, ctxs: dict, ratio: float, loops: list, warnings: list[str]) -> dict:
    """Score de la grille (positif : microservices) et style recommandé, avec chaque raison."""
    reasons, missing = [], []
    teams = {c["team"] for c in ctxs.values() if c.get("team")}
    if not teams:
        missing.append("equipes")
    else:
        effect = -2 if len(teams) == 1 else 1 if len(teams) <= 3 else 2
        reasons.append(("équipes", vault_ontology.number(len(teams)), effect,
                        "une seule équipe : la distribution n'apporte pas d'autonomie" if len(teams) == 1 else
                        "équipes qui gagnent à livrer chacune leurs contextes"))
    n = len(ctxs)
    effect = -2 if n < 3 else 0 if n <= 6 else 1
    reasons.append(("contextes", vault_ontology.number(n), effect,
                    "trop peu de contextes pour des services" if n < 3 else
                    "nombre de contextes neutre" if n <= 6 else "domaine large, découpé en nombreux contextes"))
    needy = [cid for cid, c in ctxs.items() if c.get("needs")]
    effect = min(len(needy), 3) if needy else -1
    reasons.append(("besoins propres", ", ".join(needy) or "aucun", effect,
                    "contextes aux besoins propres : " + "; ".join(
                        f"{cid} ({', '.join(NEEDS[k] for k in ctxs[cid]['needs'])})" for cid in needy)
                    if needy else "aucun contexte n'a de besoin de charge, de cadence ou d'isolement propre"))
    factors = spec.get("factors", {})
    for key, values in FACTORS.items():
        if key not in factors:
            missing.append(key)
            continue
        effect, text = values[factors[key]["value"]]
        value = factors[key]["value"]
        reasons.append((LABELS[key], LABELS.get(value, value), effect, f"{text} ({factors[key]['why']})"))
    effect = -2 if ratio > COUPLED else 1 if ratio < LOOSE else 0
    reasons.append(("couplage", vault_ontology.number(ratio, 2), effect,
                    "contextes très liés : découpage à revoir, ou à garder dans un même déployable" if ratio > COUPLED
                    else "contextes peu liés entre eux" if ratio < LOOSE else "couplage moyen entre contextes"))
    if loops:
        reasons.append(("cycles", vault_ontology.number(len(loops)), -1, "dépendances circulaires entre contextes"))
    score = sum(r[2] for r in reasons)
    blocked = factors.get("devops", {}).get("value") == "faible"
    if score >= MICRO and not blocked:
        recommended = "microservices"
    elif needy and not blocked:
        recommended = "mixte"
    else:
        recommended = "monolithe-modulaire"
    extract = needy if recommended == "mixte" else []
    confidence = "faible" if len(missing) >= 2 else "moyenne" if missing else "bonne"
    if missing:
        warnings.append("grille incomplète, facteurs non renseignés : " + ", ".join(missing)
                        + f" (confiance {confidence})")
    if blocked and needy:
        warnings.append("maturité DevOps faible : aucun service extrait, malgré les besoins propres de "
                        + ", ".join(needy))
    return {"recommended": recommended, "score": score, "extract": extract, "confidence": confidence,
            "missing": missing, "reasons": [{"factor": f, "value": str(v), "effect": e, "why": w}
                                            for f, v, e, w in reasons]}


def styles(spec: dict, found: dict) -> dict:
    """Composants et flux de chaque style, au format d'options.json (architecture-options)."""
    ctxs = spec["contexts"]
    relations = [r for r in spec.get("relations", []) if "chemins-separes" not in r["patterns"]]
    refs = lambda items: sorted({r for c in items for r in c.get("refs", [])})  # noqa: E731

    def distributed(services: list[dict], module: list[dict]) -> dict:
        comps, flows = [], []
        home = {}
        if module:
            comps += [{"id": "app", "label": "Application (monolithe modulaire)", "tech": "modules : "
                       + ", ".join(c["id"] for c in module), "refs": refs(module), "contexts": [c["id"] for c in module]},
                      {"id": "db-app", "label": "Base de l'application", "role": "db",
                       "contexts": [c["id"] for c in module]}]
            flows.append({"from": "app", "to": "db-app", "label": "un schéma par module"})
            home.update({c["id"]: "app" for c in module})
        for c in services:
            comps += [{"id": f"svc-{c['id']}", "label": f"Service {c['name']}", "refs": c.get("refs", []),
                       "contexts": [c["id"]]},
                      {"id": f"db-{c['id']}", "label": f"Base {c['name']}", "role": "db", "contexts": [c["id"]]}]
            flows.append({"from": f"svc-{c['id']}", "to": f"db-{c['id']}"})
            home[c["id"]] = f"svc-{c['id']}"
        events = False
        for r in relations:
            up, down = home[r["upstream"]], home[r["downstream"]]
            if up == down:
                continue
            if r.get("integration", "sync") == "async":
                events = True
                flows += [{"from": up, "to": "bus", "label": "publie", "style": "async"},
                          {"from": "bus", "to": down, "label": "événements", "style": "async"}]
            else:
                flows.append({"from": down, "to": up, "label": r.get("label") or "API", "style": "sync"})
        if events:
            comps.append({"id": "bus", "label": "Bus d'événements", "role": "queue"})
        unique = []
        for f in flows:
            if f not in unique:
                unique.append(f)
        return {"components": comps, "flows": unique}

    extract = set(found["style"]["extract"]) or {c["id"] for c in ctxs if c.get("needs")}
    return {
        "monolithe-modulaire": {"name": "Monolithe modulaire", "summary": "Un déployable, un module par contexte borné, "
                                "frontières tenues dans le code et un schéma de base par module.",
                                **distributed([], ctxs)},
        "mixte": {"name": "Monolithe modulaire et services extraits",
                  "summary": "Modules dans un déployable ; services séparés pour les contextes aux besoins propres : "
                             + (", ".join(sorted(extract)) or "aucun"),
                  **distributed([c for c in ctxs if c["id"] in extract], [c for c in ctxs if c["id"] not in extract])},
        "microservices": {"name": "Microservices", "summary": "Un service et une base par contexte borné, "
                          "intégrés selon la carte des contextes.", **distributed(ctxs, [])},
    }


def carte(spec: dict) -> dict:
    """Description drawio_build.py de la carte : une colonne par sous-domaine, ses contextes l'un sous l'autre."""
    subs = {s["id"]: s for s in spec["subdomains"]}
    cols = {s["id"]: i for i, s in enumerate(spec["subdomains"])}
    rows: dict[str, int] = {}
    elements = []
    for c in spec["contexts"]:
        sub = subs[c["subdomain"]]
        row = rows.get(sub["id"], 0)
        rows[sub["id"]] = row + 1
        label = f"{c['name']}\n{sub['name']} ({KINDS[sub['kind']]})" + (f"\n{c['team']}" if c.get("team") else "")
        elements.append({"id": c["id"], "role": "alert" if c.get("needs") else "system", "label": label,
                         "col": cols[sub["id"]], "row": row})
    for r in spec.get("relations", []):
        if "chemins-separes" in r["patterns"]:
            continue
        label = ", ".join(PATTERNS[p] for p in r["patterns"])
        elements.append({"from": r["upstream"], "to": r["downstream"], "label": f"{label} (amont > aval)",
                         "style": "async" if r.get("integration") == "async" else "sync"})
    return {"title": f"Carte des contextes : {spec['title']}", "audience": "technique", "legend": True,
            "_légende": "Point de vigilance : contexte aux besoins propres (service à extraire).",
            "elements": elements}


def markdown(spec: dict, found: dict) -> str:
    v = vault_ontology
    style, ctxs = found["style"], spec["contexts"]
    lines = [f"# {spec['title']}", ""]
    if spec.get("context"):
        lines += [spec["context"], ""]
    lines += ["## Style recommandé", "",
              f"**{STYLES[style['recommended']].capitalize()}** (score {style['score']:+d}, confiance "
              f"{style['confidence']})" + (f" ; contextes à extraire en services : {', '.join(style['extract'])}"
                                           if style["extract"] else "") + ".", ""]
    decision = spec.get("decision")
    if decision:
        lines += [f"Style retenu : **{STYLES[decision['style']]}**, {decision['why']}", ""]
    lines += ["| Facteur | Valeur | Effet | Raison |", "| --- | --- | --- | --- |"]
    lines += [f"| {r['factor']} | {cell(r['value'])} | {r['effect']:+d} | {cell(r['why'])} |" for r in style["reasons"]]
    if style["missing"]:
        lines += ["", "Facteurs non renseignés : " + ", ".join(style["missing"]) + "."]
    lines += ["", "Score positif : vers les microservices ; à partir de "
              f"{MICRO}, microservices ; en dessous, monolithe modulaire, avec extraction des contextes aux besoins "
              "propres (mixte) ; jamais de services sans maturité DevOps.", "", "## Sous-domaines", "",
              "| Sous-domaine | Nature | Contextes | Pourquoi |", "| --- | --- | --- | --- |"]
    for sub in spec["subdomains"]:
        inside = [c["name"] for c in ctxs if c["subdomain"] == sub["id"]]
        lines.append(f"| {cell(sub['name'])} | {KINDS[sub['kind']]} | {cell(', '.join(inside))} | "
                     f"{cell(sub.get('why', ''))} |")
    if any(s["kind"] == "generique" for s in spec["subdomains"]):
        lines += ["", "Un sous-domaine générique s'achète ou se réutilise (progiciel, service managé) plutôt que de "
                  "se développer."]
    lines += ["", "## Contextes bornés"]
    stats = found["stats"]
    for c in ctxs:
        lines += ["", f"### {c['name']} (`{c['id']}`)", ""]
        if c.get("description"):
            lines += [c["description"], ""]
        inner, outer = stats[c["id"]]["internal"], stats[c["id"]]["external"]
        cohesion = f"{round(100 * inner / (inner + outer))} %" if inner + outer else "sans relation"
        sub = next(s for s in spec["subdomains"] if s["id"] == c["subdomain"])
        lines += [f"- **Sous-domaine** : {sub['name']} ({KINDS[sub['kind']]})",
                  f"- **Équipe** : {c.get('team', 'à désigner')}",
                  f"- **Entités possédées** : {', '.join(c.get('entities', [])) or 'aucune'}",
                  f"- **Entités utilisées** : {', '.join(c.get('uses', [])) or 'aucune'}",
                  f"- **Exigences** : {', '.join(c.get('refs', [])) or 'aucune'}",
                  f"- **Cohésion** : {cohesion} des relations de ses entités restent dans le contexte"]
        if c.get("needs"):
            lines += ["- **Besoins propres** : " + "; ".join(f"{NEEDS[k]} : {w}" for k, w in c["needs"].items())]
        if c.get("terms"):
            lines += ["", "| Terme | Sens dans ce contexte |", "| --- | --- |"]
            lines += [f"| {cell(t)} | {cell(d)} |" for t, d in c["terms"].items()]
    lines += ["", "## Carte des contextes", ""]
    if spec.get("relations"):
        lines += ["| Amont | Aval | Motifs | Intégration | Objet |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {r['upstream']} | {r['downstream']} | {', '.join(PATTERNS[p] for p in r['patterns'])} | "
                  f"{r.get('integration', 'sync')} | {cell(r.get('label', ''))} |" for r in spec["relations"]]
    else:
        lines.append("Aucune relation entre contextes.")
    coupling = found["coupling"]
    lines += ["", "## Couplage", "",
              f"{v.count(coupling['cross'], 'lien')} de données entre contextes sur {v.number(coupling['relations'])} "
              f"(part {v.number(coupling['ratio'], 2)} ; fort au-delà de {v.number(COUPLED, 2)}), "
              + ("relations du modèle de données et entités utilisées." if coupling["basis"] == "modele" else
                 "entités possédées et entités utilisées, sans modèle de données : le modèle de chaque contexte "
                 "vient après le découpage (data-model, champ context)."), ""]
    if found["links"]:
        lines += ["| Contextes | Liens de données |", "| --- | --- |"]
        order = [c["id"] for c in ctxs]
        lines += [f"| {' et '.join(sorted(k, key=order.index))} | {n} |" for k, n in found["links"].items()]
    if found["warnings"]:
        lines += ["", "## Points d'attention", ""] + [f"- {w}" for w in found["warnings"]]
    return "\n".join(lines) + "\n"


def write_vault(vault: Path, folder: str, spec: dict, found: dict, out: Path, errors: list[str],
                warnings: list[str] | None = None) -> dict | None:
    """Note decoupage-domaines et une note contexte-borne par contexte, liées aux exigences du workflow."""
    v = vault_ontology
    notes = v.Notes(vault, "domain-design")
    base = v.safe_folder(folder)
    title = v.safe_name(spec["title"], "domaines")
    main_rel = f"{base}/Domaines/{title}"
    subs = {s["id"]: s for s in spec["subdomains"]}
    rels = {c["id"]: f"{base}/Contextes/{v.safe_name(c['name'], c['id'])}" for c in spec["contexts"]}
    style = found["style"]
    for c in spec["contexts"]:
        names = {x["id"]: x["name"] for x in spec["contexts"]}
        ups = [(rels[r["upstream"]], "Contexte " + names[r["upstream"]]) for r in spec.get("relations", [])
               if r["downstream"] == c["id"]]
        body = [f"# Contexte {c['name']}", "", f"Découpage : {v.link(main_rel, spec['title'])}.", ""]
        if c["id"] in style["extract"]:
            body += v.callout("note", "Service à extraire", ["; ".join(f"{NEEDS[k]} : {w}" for k, w in c["needs"].items())])
        body += [f"**Sous-domaine** : {subs[c['subdomain']]['name']} ({KINDS[subs[c['subdomain']]['kind']]})", "",
                 f"**Entités possédées** : {', '.join(c.get('entities', [])) or 'aucune'}", "",
                 f"**Entités utilisées** : {', '.join(c.get('uses', [])) or 'aucune'}"]
        if c.get("terms"):
            body += ["", "## Langage du contexte", "", "| Terme | Sens |", "| --- | --- |"]
            body += [f"| {cell(t)} | {cell(d)} |" for t, d in c["terms"].items()]
        couvre = [(f"{base}/Exigences/{r}", r) for r in c.get("refs", [])]
        notes.add(rels[c["id"]], "contexte-borne",
                  {"id": c["id"], "sous-domaine": c["subdomain"], "nature": subs[c["subdomain"]]["kind"],
                   **({"equipe": c["team"]} if c.get("team") else {}), "entites": len(c.get("entities", [])),
                   "extraire": "oui" if c["id"] in style["extract"] else "non"},
                  {"decoupage": (main_rel, spec["title"]), "depend-de": ups, "couvre": couvre}, body, ["architecture"])
    detail = notes.attach(f"{base}/Rapports/{v.folder_key(title)}/{out.name}", out) if out.is_file() else f"`{out.name}`"
    body = [f"# Domaines : {spec['title']}", ""]
    body += v.callout("success" if not found["warnings"] else "warning",
                      f"Style recommandé : {STYLES[style['recommended']]}",
                      [f"Score {style['score']:+d}, confiance {style['confidence']} ; "
                       f"{v.count(len(spec['contexts']), 'contexte')}, part des liens entre contextes "
                       f"{v.number(found['coupling']['ratio'], 2)}."]
                      + ([v.count(len(found["warnings"]), "point") + " d'attention dans le détail."]
                         if found["warnings"] else []))
    body += ["## Contextes", ""] + [f"- {v.link(rels[c['id']], 'Contexte ' + c['name'])} ({c['subdomain']})"
                                    for c in spec["contexts"]]
    body += ["", f"Détail, carte et grille : {detail}."]
    notes.add(main_rel, "decoupage-domaines", {"style": style["recommended"], "contextes": len(spec["contexts"]),
                                               "score": style["score"]}, {}, body, ["architecture"])
    result = notes.write(errors, cleanup=(f"{base}/Contextes",), warnings=warnings)
    return {**result, "folder": base} if result else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description DOMAINES.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui de la description)")
    parser.add_argument("--export", choices=["png", "svg"], help="exporter aussi la carte en image (diagram-export)")
    parser.add_argument("--vault", type=Path, help="vault Obsidian où écrire les notes du découpage")
    parser.add_argument("--folder", help="dossier des notes dans le vault, celui du workflow (Workflows/<titre>)")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.spec), "outputs": [], "subdomains": 0, "contexts": 0, "relations": 0,
              "coupling": None, "style": None, "vault": None, "errors": [], "warnings": []}
    errors = report["errors"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.spec:
        errors.append("description DOMAINES.json attendue")
        return done(1)
    errors += workspace.vault_args(parser, args, [args.spec])
    if errors:
        return done(1)
    spec, invalid = read_spec(args.spec, __file__)
    errors += invalid
    if spec is None or errors:
        return done(1)
    found = analyse(spec, args.spec.parent)
    errors += found["errors"]
    report["warnings"] += found["warnings"]
    if errors:
        return done(1)
    report.update({"subdomains": len(spec["subdomains"]), "contexts": len(spec["contexts"]),
                   "relations": len(spec.get("relations", [])), "coupling": found["coupling"],
                   "style": {k: found["style"][k] for k in ("recommended", "score", "extract", "confidence", "missing")}})

    # Squelettes de composants vérifiés contre le schéma d'options.json (architecture-options).
    skeletons = styles(spec, found)
    target = schema_of("architecture-options", "options_build.py")
    if target is None:
        report["warnings"].append("styles non vérifiés : " + absent("architecture-options", "options_build.py"))
    else:
        item = target["properties"]["options"]["items"]
        for name, skeleton in skeletons.items():
            option = {"id": "A", "scores": {}, **skeleton}
            errors += [f"styles/{name} : {e}" for e in check(option, item, target)]
    if errors:
        return done(1)

    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md = out_dir / f"{stem}.md"
    md.write_text(markdown(spec, found), encoding="utf-8")
    data = out_dir / f"{stem}.styles.json"
    data.write_text(json.dumps({"recommended": found["style"]["recommended"], "styles": skeletons},
                               ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report["outputs"] += [str(md), str(data)]

    # Carte des contextes : construite et contrôlée par drawio_build.py (drawio-diagram).
    if find_script("drawio-diagram", "drawio_build.py") is None:
        report["warnings"].append("carte des contextes non dessinée : " + absent("drawio-diagram", "drawio_build.py"))
    else:
        desc = out_dir / f"{stem}.carte.json"
        desc.write_text(json.dumps(carte(spec), ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        built = run_script("drawio-diagram", "drawio_build.py",
                           [desc, "--out", out_dir / f"{stem}.carte.drawio"] + (["--export", args.export]
                                                                                 if args.export else []))
        errors += [f"carte : {e}" for e in built.get("errors", [])]
        report["warnings"] += [f"carte : {w}" for w in built.get("warnings", [])]
        if built.get("output"):
            report["outputs"] += [str(desc), built["output"]] + (built.get("export") or {}).get("outputs", [])
            report["warnings"] += [f"carte : {w}" for w in (built.get("export") or {}).get("warnings", [])]
    if errors:
        return done(1)
    if args.vault:
        report["vault"] = write_vault(args.vault, args.folder, spec, found, md, errors, report["warnings"])
    return done(1 if errors else 0)


if __name__ == "__main__":
    sys.exit(main())
