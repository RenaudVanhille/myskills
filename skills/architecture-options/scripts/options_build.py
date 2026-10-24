# /// script
# requires-python = ">=3.10"
# ///
"""Compare 2 ou 3 options d'architecture au regard du catalogue d'exigences.

Entrée : une description JSON courte (`options.json`) : critères pondérés,
options (composants, flux, écarts aux exigences, notes par critère, avantages,
inconvénients, risques), recommandation et, après la revue, décision. Le
script, et non le modèle :
- vérifie que chaque exigence citée existe et est retenue dans le catalogue ;
- calcule le score pondéré de chaque option et son rang ; une option qui ne
  couvre pas une exigence indispensable est éliminée ;
- signale une recommandation qui ne suit pas le classement ;
- écrit `options.md` (revue), un schéma par option dans une description
  draw.io à plusieurs pages (`architectures.json`, pour drawio_build.py) et,
  quand la décision est prise, l'ADR `adr-architecture.md`.

Avec `--decision decision.json` (décision de l'utilisateur prise après la
revue), seul l'ADR est écrit : la comparaison déjà validée ne change pas.

Avec `pos` (POS existant du SI, JSON ou CSV de urbanization-map), chaque
option dit où elle se place (`placement`) : le script vérifie les noms dans
le POS, compte créations, évolutions, remplacements, redondances et flux
entre zones, ajoute le critère « urbanisation » et écrit le POS cible de
chaque option (`schemas/pos-option-<id>.json`, pour pos_build.py).

Chaque option cloud (`provider`) passe la revue Well-Architected des piliers
(wa_check.py du skill cloud-architecture) : constats par pilier dans
`options.md`, détail dans `schemas/option-<id>.wa.md`, constats de l'option
retenue dans l'ADR. Un écart assumé s'accepte avec sa raison (`wa_accept`).

Sans `criteria`, les critères sont les catégories des exigences non
fonctionnelles retenues, pondérées par leur plus haute priorité
(indispensable 3, importante 2, souhaitable 1).

    uv run scripts/options_build.py options.json [--decision decision.json] [--out-dir DOSSIER] | --schema
"""

import argparse
import csv
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from pos import check_option, placement_lines, read_pos, resolve, target_pos  # noqa: E402
from pos import index as pos_index  # noqa: E402
from spec_schema import check, input_schema, print_schema, validate  # noqa: E402

WEIGHTS = {"indispensable": 3, "importante": 2, "souhaitable": 1}
CATEGORY_LABELS = {"performance": "Performance", "disponibilite": "Disponibilité", "securite": "Sécurité",
                   "conformite": "Conformité", "exploitabilite": "Exploitabilité",
                   "maintenabilite": "Maintenabilité", "evolutivite": "Évolutivité",
                   "interoperabilite": "Interopérabilité", "utilisabilite": "Utilisabilité",
                   "portabilite": "Portabilité", "cout": "Coût", "autre": "Autre"}
LEVELS = {"partiel": "partielle", "non": "non couverte"}
WA_PILLARS = ("reliability", "security", "operations", "performance", "cost")


def load_wa():
    """wa_check.py du skill cloud-architecture, s'il est installé à côté ; sinon None."""
    scripts = Path(__file__).resolve().parents[2] / "cloud-architecture" / "scripts"
    if not (scripts / "wa_check.py").exists():
        return None
    sys.path.insert(0, str(scripts))
    import wa_check
    return wa_check


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def nature(req: dict) -> str | None:
    """Comme requirements-catalog : champ nature, sinon préfixe EF- ou ENF-."""
    return req.get("nature") or {"EF": "fonctionnelle", "ENF": "non-fonctionnelle"}.get(req["id"].split("-")[0])


def load_catalog(base: Path, spec: dict, errors: list[str]) -> dict[str, dict]:
    path = base / spec.get("requirements", "exigences.json")
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"requirements : catalogue illisible {path} ({error})")
        return {}
    # Le catalogue est validé contre le schéma de req_build.py (skill requirements-catalog), s'il est installé.
    req_build = Path(__file__).resolve().parents[2] / "requirements-catalog" / "scripts" / "req_build.py"
    schema = input_schema(req_build) if (req_build.parent.parent / "contract.json").exists() else None
    invalid = check(catalog, schema) if schema else []
    if invalid:
        errors += [f"requirements : {path.name} : {e}" for e in invalid[:10]]
        return {}
    if not isinstance(catalog, dict) or not isinstance(catalog.get("requirements"), list):
        errors.append(f"requirements : {path.name} sans liste requirements")
        return {}
    return {r["id"]: r for r in catalog["requirements"] if isinstance(r, dict) and "id" in r}


def default_criteria(catalog: dict[str, dict]) -> list[dict]:
    criteria: dict[str, dict] = {}
    for req in catalog.values():
        if nature(req) == "non-fonctionnelle" and req.get("status", "retenue") == "retenue" \
                and req.get("category") and req["priority"] in WEIGHTS:
            item = criteria.setdefault(req["category"], {"id": req["category"],
                                                         "name": CATEGORY_LABELS.get(req["category"], req["category"]),
                                                         "weight": 0, "refs": []})
            item["weight"] = max(item["weight"], WEIGHTS[req["priority"]])
            item["refs"].append(req["id"])
    return list(criteria.values())


def check_refs(where: str, refs, catalog: dict, errors: list[str]) -> None:
    for ref in refs:
        if ref not in catalog:
            errors.append(f"{where} : exigence inconnue {ref}")
        elif catalog[ref].get("status") == "retiree":
            errors.append(f"{where} : {ref} est retirée du catalogue")


def layout(option: dict) -> list[dict]:
    """Description draw.io d'une option : colonnes par profondeur des flux, de gauche à droite."""
    ids = [c["id"] for c in option["components"]]
    depth = {i: 0 for i in ids}
    for _ in range(len(ids)):  # plus long chemin, borné : un cycle ne boucle pas
        for flow in option.get("flows", []):
            if flow["from"] in depth and flow["to"] in depth and flow["to"] != flow["from"]:
                depth[flow["to"]] = max(depth[flow["to"]], min(depth[flow["from"]] + 1, len(ids) - 1))
    rows: dict[int, int] = {}
    elements = []
    for comp in option["components"]:
        col = depth[comp["id"]]
        label = comp["label"] + (f"\n({comp['tech']})" if comp.get("tech") else "")
        elements.append({"id": comp["id"], "role": comp.get("role", "system"), "label": label,
                         "row": rows.get(col, 0), "col": col})
        rows[col] = rows.get(col, 0) + 1
    for flow in option.get("flows", []):
        edge = {"from": flow["from"], "to": flow["to"]}
        if flow.get("label"):
            edge["label"] = flow["label"]
        if flow.get("style"):
            edge["style"] = flow["style"]
        elements.append(edge)
    return elements


# Rôle d'un composant -> type générique de cloud_build.py, quand le composant n'a pas de type.
CLOUD_TYPES = {"person": "user", "system": "service", "external": "external", "db": "db", "queue": "queue"}


def cloud_spec(option: dict) -> dict:
    """Description cloud_build.py d'une option hébergée chez un fournisseur."""
    items = [{"id": c["id"], "type": c.get("type") or CLOUD_TYPES[c.get("role", "system")], "label": c["label"],
              **({"count": c["count"]} if c.get("count") else {})} for c in option["components"]]
    flows = [{k: f[k] for k in ("from", "to", "label", "style", "protocol") if f.get(k)}
             for f in option.get("flows", [])]
    return {"_source": "généré par options_build.py", "title": f"Option {option['id']} : {option['name']}",
            "provider": option["provider"], "items": items, "flows": flows}


def wa_review(wa, option: dict, where: str, errors: list[str], warnings: list[str]) -> dict:
    """Revue Well-Architected des piliers d'une option cloud (sans les conventions de schéma)."""
    findings, errs, clouds = wa.check(cloud_spec(option))
    errors += [f"{where}/components : {e}" for e in errs]
    findings = [f for f in findings if f["pillar"] != "conventions"]
    unused: list[str] = []
    wa.accept(findings, option.get("wa_accept", {}), unused)
    warnings += [f"{where}/wa_accept : {w}" for w in unused]
    findings.sort(key=lambda f: (wa.SEVERITIES.index(f["severity"]), f["rule"]))
    open_ = [f for f in findings if not f["accepted"]]
    high = sorted({f"{f['rule']}@{f['element']}" for f in open_ if f["severity"] == "haute"})
    if high:
        warnings.append(f"option {option['id']} : constat(s) Well-Architected de gravité haute à traiter : "
                        f"{', '.join(high)} (composant à ajouter, ou wa_accept avec la raison)")
    counts = {s: sum(f["severity"] == s for f in open_) for s in wa.SEVERITIES}
    counts["acceptés"] = len(findings) - len(open_)
    return {"option": option["id"], "counts": counts,
            "open": [f"{f['rule']}@{f['element']}" for f in open_], "findings": findings, "clouds": clouds}


def render_wa(reviews: list[dict], wa) -> list[str]:
    names = [wa.PILLARS[p] for p in WA_PILLARS]
    lines = ["", "## Revue Well-Architected", "",
             "Constats ouverts par pilier, calculés par `wa_check.py` sur les composants et les flux de chaque option "
             "cloud (h : gravité haute). Ils doivent se retrouver dans les notes et la recommandation.", "",
             "| Option | " + " | ".join(names) + " | Acceptés | Détail |", "| --- | " + "--- | " * len(names) + "--- | --- |"]
    for review in reviews:
        cells = []
        for pillar in WA_PILLARS:
            mine = [f for f in review["findings"] if f["pillar"] == pillar and not f["accepted"]]
            high = sum(f["severity"] == "haute" for f in mine)
            cells.append(f"{len(mine)}" + (f" ({high} h)" if high else ""))
        lines.append(f"| {review['option']} | " + " | ".join(cells) + f" | {review['counts']['acceptés']} | "
                     f"`schemas/option-{review['option'].lower()}.wa.md` |")
    return lines


def wa_lines(review: dict, wa) -> list[str]:
    lines = []
    for f in review["findings"]:
        status = f" (accepté : {f['accepted']})" if f["accepted"] else ""
        lines.append(f"- {f['rule']} {wa.PILLARS[f['pillar']]}, {f['severity']} : {f['message']}{status}")
    return lines or ["- aucun constat"]


def traceability(spec: dict, catalog: dict) -> tuple[list[list[str]], dict]:
    """Matrice exigence x option (couverture) et composants de l'option retenue, ou recommandée."""
    target = (spec.get("decision") or spec["recommendation"])["option"]
    chosen = next(o for o in spec["options"] if o["id"] == target)
    uses_refs = any(c.get("refs") for c in chosen["components"])
    header = ["Exigence", "Titre", "Priorité"] + [f"Option {o['id']}" for o in spec["options"]] + \
        [f"Composants de {target}"]
    rows, uncovered, unassigned = [header], [], []
    for rid, req in catalog.items():
        if req.get("status", "retenue") != "retenue":
            continue
        cover = []
        for option in spec["options"]:
            gap = option.get("gaps", {}).get(rid)
            cover.append(LEVELS[gap["level"]] if gap else "couverte")
        comps = [c["label"] for c in chosen["components"] if rid in c.get("refs", [])]
        level = chosen.get("gaps", {}).get(rid, {}).get("level")
        if level == "non" and req["priority"] == "indispensable":
            uncovered.append(rid)
        if uses_refs and level != "non" and not comps and req["priority"] != "hors-perimetre":
            unassigned.append(rid)
        rows.append([rid, req.get("title", ""), req["priority"], *cover, ", ".join(comps)])
    return rows, {"uncovered": uncovered, "unassigned": unassigned}


def render_trace(rows: list[list[str]], target: str) -> str:
    lines = ["# Matrice de traçabilité", "",
             f"Fichier généré par `options_build.py`. Couverture de chaque exigence retenue par chaque option, "
             f"et composants de l'option {target} qui la portent (champ refs des composants).", "",
             "| " + " | ".join(rows[0]) + " |", "| " + " | ".join("---" for _ in rows[0]) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row) + " |" for row in rows[1:]]
    return "\n".join(lines) + "\n"


def render_pos(impacts: list[dict]) -> list[str]:
    lines = ["", "## Position dans le SI (POS)", "",
             "Impacts calculés par le script depuis le POS existant et le placement de chaque option.", "",
             "| Option | À créer | À faire évoluer | À remplacer | Réutilisées | Redondances possibles | Flux entre zones |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {i['option']} | {i['new']} | {i['evolve']} | {i['replace']} | {i['reuse']} | "
              f"{cell('; '.join(i['redundancies']) or '-')} | {i['cross_zone']} |" for i in impacts]
    return lines


def render_md(spec: dict, criteria: list[dict], ranking: list[dict], catalog: dict,
              impacts: list[dict] | None = None, idx: dict | None = None, reviews: list[dict] | None = None,
              wa=None) -> str:
    options = {o["id"]: o for o in spec["options"]}
    lines = [f"# {spec.get('title') or 'Options d’architecture'}", "",
             "Fichier généré par `options_build.py` depuis `options.json`, qui fait foi. "
             "Scores calculés par le script : somme des notes (1 à 5) pondérées, en pourcentage du maximum.", "",
             "## Synthèse", "", "| Rang | Option | Score | Écarts | Statut |", "| --- | --- | --- | --- | --- |"]
    for rank, item in enumerate(ranking, 1):
        option = options[item["option"]]
        gaps = len(option.get("gaps", {}))
        status = "éliminée : " + ", ".join(item["blocking"]) if item["blocking"] else "recevable"
        lines.append(f"| {rank} | **{item['option']}** {cell(option['name'])} | {item['score']} % | {gaps} | {status} |")
    lines += ["", "## Critères et notes", "",
              "| Critère | Poids | Exigences | " + " | ".join(options) + " |",
              "| --- | --- | --- | " + " | ".join("---" for _ in options) + " |"]
    for crit in criteria:
        notes = " | ".join(str(o["scores"].get(crit["id"], "-")) + (f" : {cell(o['score_notes'][crit['id']])}"
                           if crit["id"] in o.get("score_notes", {}) else "") for o in spec["options"])
        lines.append(f"| {cell(crit['name'])} | {crit['weight']} | {', '.join(crit.get('refs', []))} | {notes} |")
    gap_ids = sorted({g for o in spec["options"] for g in o.get("gaps", {})})
    if gap_ids:
        lines += ["", "## Écarts aux exigences", "",
                  "Une exigence absente du tableau est couverte par toutes les options.", "",
                  "| Exigence | Priorité | " + " | ".join(options) + " |",
                  "| --- | --- | " + " | ".join("---" for _ in options) + " |"]
        for gid in gap_ids:
            row = []
            for option in spec["options"]:
                gap = option.get("gaps", {}).get(gid)
                row.append(f"{LEVELS[gap['level']]} : {cell(gap['note'])}" if gap else "couverte")
            title = catalog.get(gid, {}).get("title", "")
            lines.append(f"| {gid} {cell(title)} | {catalog.get(gid, {}).get('priority', '')} | " + " | ".join(row) + " |")
    if impacts:
        lines += render_pos(impacts)
    if reviews:
        lines += render_wa(reviews, wa)
    for option in spec["options"]:
        lines += ["", f"## Option {option['id']} : {option['name']}", "", option["summary"], ""]
        comps = ", ".join(c["label"] + (f" ({c['tech']})" if c.get("tech") else "") for c in option["components"])
        lines.append(f"**Composants** : {comps}.")
        for key, label in (("pros", "Avantages"), ("cons", "Inconvénients"), ("risks", "Risques")):
            if option.get(key):
                lines += ["", f"**{label}**", ""] + [f"- {item}" for item in option[key]]
        if idx and option.get("placement"):
            lines += ["", "**Position dans le SI**", ""] + placement_lines(option, idx)
        lines += ["", f"Schéma : page « Option {option['id']} » de `schemas/architectures.drawio`."]
        if idx:
            lines[-1] += f" POS cible : `schemas/pos-option-{option['id'].lower()}.drawio`."
    rec = spec["recommendation"]
    lines += ["", "## Recommandation", "", f"Option **{rec['option']}** : {rec['why']}"]
    if rec.get("refs"):
        lines.append(f"Exigences déterminantes : {', '.join(rec['refs'])}.")
    if spec.get("decision"):
        dec = spec["decision"]
        lines += ["", "## Décision", "", f"Option **{dec['option']}**, décidée par {dec['by']}"
                  + (f" le {dec['date']}" if dec.get("date") else "") + f" : {dec['why']}"]
    return "\n".join(lines) + "\n"


def render_adr(spec: dict, ranking: list[dict], catalog: dict, idx: dict | None = None,
               reviews: list[dict] | None = None, wa=None) -> str:
    options = {o["id"]: o for o in spec["options"]}
    dec = spec["decision"]
    chosen = options[dec["option"]]
    key = [r for r in catalog.values() if r.get("status", "retenue") == "retenue" and r["priority"] == "indispensable"]
    lines = [f"# ADR : architecture retenue, option {dec['option']} ({chosen['name']})", "",
             "Fichier généré par `options_build.py` depuis `options.json`.", "",
             f"- **Statut** : acceptée" + (f", le {dec['date']}" if dec.get("date") else ""),
             f"- **Décidée par** : {dec['by']}", "", "## Contexte", "",
             spec.get("context") or "Choisir l'architecture qui répond au catalogue d'exigences.", "",
             "Exigences indispensables : " + ", ".join(f"{r['id']} {r['title']}" for r in key) + ".", "",
             "## Options envisagées", ""]
    for item in ranking:
        option = options[item["option"]]
        status = f", éliminée ({', '.join(item['blocking'])})" if item["blocking"] else ""
        lines.append(f"- **{item['option']}** {option['name']} : score {item['score']} %{status}. {option['summary']}")
    lines += ["", "## Décision", "", f"Option {dec['option']} : {dec['why']}"]
    if dec["option"] != spec["recommendation"]["option"]:
        lines += ["", f"La recommandation était l'option {spec['recommendation']['option']} : "
                      f"{spec['recommendation']['why']}"]
    if idx and chosen.get("placement"):
        lines += ["", "## Position dans le SI", ""] + placement_lines(chosen, idx) + \
                 ["", f"POS cible : `schemas/pos-option-{dec['option'].lower()}.drawio`."]
    review = next((r for r in reviews or [] if r["option"] == dec["option"]), None)
    if review:
        lines += ["", "## Revue Well-Architected", "",
                  f"Constats de `wa_check.py` sur l'option {dec['option']} ; détail dans "
                  f"`schemas/option-{dec['option'].lower()}.wa.md`.", ""] + wa_lines(review, wa)
    lines += ["", "## Conséquences", ""]
    lines += [f"- {item}" for item in chosen.get("cons", []) + chosen.get("risks", [])] or ["- aucune notée"]
    for gid, gap in chosen.get("gaps", {}).items():
        lines.append(f"- {gid} {LEVELS[gap['level']]} : {gap['note']}")
    refs = sorted(set(spec["recommendation"].get("refs", [])) | set(dec.get("refs", [])) | set(chosen.get("gaps", {})))
    if refs:
        lines += ["", "## Exigences liées", "", ", ".join(refs)]
    return "\n".join(lines) + "\n"


def analyse(spec: dict, base: Path) -> dict:
    """Contrôles croisés, POS, revue Well-Architected, scores et classement (partagés avec deck_build.py)."""
    pos_data = None
    errors: list[str] = []
    warnings: list[str] = []
    catalog = load_catalog(base, spec, errors)
    idx = None
    if spec.get("pos"):
        pos_path = resolve(base, spec["pos"], errors)
        pos_data = read_pos(pos_path, errors) if pos_path else {"zones": []}
        idx = pos_index(pos_data)
        if not idx["apps"] and not errors:
            errors.append(f"pos : aucune application dans {spec['pos']}")
        if errors:  # POS illisible : pas d'erreurs en cascade sur chaque placement
            idx = {"apps": {}, "places": set(), "unreadable": True}
    criteria = spec.get("criteria") or default_criteria(catalog)
    if idx and not spec.get("criteria"):
        criteria.append({"id": "urbanisation", "name": "Urbanisation (POS)", "weight": 2, "refs": []})
    if not criteria:
        errors.append("criteria : aucun critère, ni donné ni déduit des exigences non fonctionnelles")
    crit_ids = [c["id"] for c in criteria]
    if len(set(crit_ids)) != len(crit_ids):
        errors.append("criteria : identifiant en double")
    for index, crit in enumerate(spec.get("criteria", [])):
        check_refs(f"criteria/{index}", crit.get("refs", []), catalog, errors)

    option_ids = [o["id"] for o in spec["options"]]
    if len(set(option_ids)) != len(option_ids):
        errors.append("options : identifiant en double")
    ranking, impacts, reviews = [], [], []
    wa = load_wa() if any(o.get("provider") for o in spec["options"]) else None
    if wa is None and any(o.get("provider") for o in spec["options"]):
        warnings.append("revue Well-Architected non faite : skill cloud-architecture (wa_check.py) absent")
    for index, option in enumerate(spec["options"]):
        if idx is not None and not idx.get("unreadable"):
            if not option.get("placement"):
                warnings.append(f"options/{index} ({option['id']}) : pas de placement dans le POS")
            impacts.append(check_option(option, idx, errors, warnings))
        elif option.get("placement") and idx is None:
            errors.append(f"options/{index} ({option['id']})/placement : POS absent, ajoutez pos à la description")
        where = f"options/{index} ({option['id']})"
        comp_ids = [c["id"] for c in option["components"]]
        if len(set(comp_ids)) != len(comp_ids):
            errors.append(f"{where}/components : identifiant en double")
        for fi, flow in enumerate(option.get("flows", [])):
            for end in ("from", "to"):
                if flow[end] not in comp_ids:
                    errors.append(f"{where}/flows/{fi}/{end} : composant inconnu « {flow[end]} »")
        check_refs(f"{where}/gaps", option.get("gaps", {}), catalog, errors)
        if wa and option.get("provider"):
            reviews.append(wa_review(wa, option, where, errors, warnings))
        elif option.get("wa_accept"):
            warnings.append(f"{where}/wa_accept : ignoré, l'option n'a pas de provider")
        for ci, comp in enumerate(option["components"]):
            check_refs(f"{where}/components/{ci}/refs", comp.get("refs", []), catalog, errors)
        missing = [c for c in crit_ids if c not in option["scores"]]
        if missing:
            errors.append(f"{where}/scores : note manquante pour {', '.join(missing)}")
        unjustified = [c for c in crit_ids if c in option["scores"] and c not in option.get("score_notes", {})]
        if unjustified:
            warnings.append(f"{where} : note sans justification (score_notes) pour {', '.join(unjustified)}")
        unknown = [c for c in [*option["scores"], *option.get("score_notes", {})] if c not in crit_ids]
        if unknown:
            errors.append(f"{where}/scores : critère inconnu {', '.join(unknown)} (critères : {', '.join(crit_ids)})")
        total = sum(c["weight"] * option["scores"].get(c["id"], 0) for c in criteria)
        best = sum(c["weight"] * 5 for c in criteria) or 1
        blocking = [g for g, gap in option.get("gaps", {}).items()
                    if gap["level"] == "non" and catalog.get(g, {}).get("priority") == "indispensable"]
        ranking.append({"option": option["id"], "score": round(100 * total / best), "blocking": blocking})
    # Classement stable : recevables d'abord, puis score décroissant, puis ordre de la description.
    ranking.sort(key=lambda r: (bool(r["blocking"]), -r["score"]))

    rec = spec["recommendation"]
    check_refs("recommendation", rec.get("refs", []), catalog, errors)
    if rec["option"] not in option_ids:
        errors.append(f"recommendation/option : option inconnue « {rec['option']} » ({', '.join(option_ids)})")
    elif ranking and not errors:
        top = ranking[0]
        picked = next(r for r in ranking if r["option"] == rec["option"])
        if picked["blocking"]:
            warnings.append(f"recommandation de l'option {rec['option']}, éliminée ({', '.join(picked['blocking'])})")
        elif picked is not top and picked["score"] < top["score"]:
            warnings.append(f"recommandation de l'option {rec['option']} ({picked['score']} %) et non de "
                            f"{top['option']} ({top['score']} %) : la justification doit l'expliquer")
    decision = spec.get("decision")
    if decision:
        check_refs("decision", decision.get("refs", []), catalog, errors)
        if decision["option"] not in option_ids:
            errors.append(f"decision/option : option inconnue « {decision['option']} »")
    for option in spec["options"]:
        if not option.get("cons") and not option.get("risks"):
            warnings.append(f"option {option['id']} : ni inconvénient ni risque noté")

    return {"criteria": criteria, "ranking": ranking, "catalog": catalog, "idx": idx, "pos_data": pos_data,
            "impacts": impacts, "reviews": reviews, "wa": wa, "errors": errors, "warnings": warnings}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description options.json")
    parser.add_argument("--decision", type=Path, help="décision de l'utilisateur (JSON) : n'écrit que l'ADR")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    invalid = validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1

    if args.decision:
        try:
            spec["decision"] = json.loads(args.decision.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            print(json.dumps({"input": str(args.decision), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
            return 1
        invalid = [f"décision : {e}" for e in check(spec["decision"], input_schema(__file__)["properties"]["decision"])]
        if invalid:
            print(json.dumps({"input": str(args.decision), "errors": invalid, "warnings": []}, ensure_ascii=False))
            return 1

    found = analyse(spec, args.spec.parent)
    criteria, ranking, catalog, idx, pos_data, impacts, reviews, wa, errors, warnings = (
        found[k] for k in ("criteria", "ranking", "catalog", "idx", "pos_data", "impacts", "reviews", "wa",
                           "errors", "warnings"))
    rec, decision = spec["recommendation"], spec.get("decision")
    report = {"input": str(args.spec), "outputs": [], "options": len(spec["options"]), "criteria": len(criteria),
              "ranking": ranking, "recommended": rec["option"], "decided": decision["option"] if decision else None,
              "pos": impacts if idx is not None else None,
              "wa": [{k: r[k] for k in ("option", "counts", "open")} for r in reviews] if wa else None,
              "trace": None,
              "errors": errors, "warnings": warnings}
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    rows, report["trace"] = traceability(spec, catalog)
    target = (decision or rec)["option"]
    if report["trace"]["uncovered"]:
        warnings.append(f"option {target} : exigence(s) indispensable(s) non couverte(s) : "
                        f"{', '.join(report['trace']['uncovered'])}")
    if report["trace"]["unassigned"]:
        warnings.append(f"option {target} : exigence(s) couverte(s) sans composant (refs) : "
                        f"{', '.join(report['trace']['unassigned'])}")
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    trace_md, trace_csv = out_dir / "tracabilite.md", out_dir / "tracabilite.csv"
    with open(trace_md, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_trace(rows, target))
    with open(trace_csv, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    if args.decision:
        adr = out_dir / "adr-architecture.md"
        with open(adr, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_adr(spec, ranking, catalog, idx, reviews, wa))
        report["outputs"] = [str(adr), str(trace_md), str(trace_csv)]
        print(json.dumps(report, ensure_ascii=False))
        return 0
    (out_dir / "schemas").mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md, diagrams = out_dir / f"{stem}.md", out_dir / "schemas" / "architectures.json"
    with open(md, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_md(spec, criteria, ranking, catalog, impacts, idx, reviews, wa))
    pages = [{"name": f"Option {o['id']}", "title": f"Option {o['id']} : {o['name']}", "elements": layout(o)}
             for o in spec["options"]]
    with open(diagrams, "w", encoding="utf-8", newline="\n") as handle:
        json.dump({"_source": f"généré par options_build.py depuis {args.spec.name}",
                   "audience": spec.get("audience", "technique"), "pages": pages}, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    report["outputs"] = [str(md), str(diagrams), str(trace_md), str(trace_csv)]
    for option in spec["options"]:
        if option.get("provider"):
            target_cloud = out_dir / "schemas" / f"option-{option['id'].lower()}.cloud.json"
            with open(target_cloud, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(cloud_spec(option), handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            report["outputs"].append(str(target_cloud))
    for review in reviews:
        option = next(o for o in spec["options"] if o["id"] == review["option"])
        target_wa = out_dir / "schemas" / f"option-{review['option'].lower()}.wa.md"
        rules = sum(1 for v in wa.RULES.values() if v[0] != "conventions")
        with open(target_wa, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(wa.markdown(f"Option {option['id']} : {option['name']}", review["findings"],
                                     review["clouds"], rules))
        report["outputs"].append(str(target_wa))
    if idx is not None:
        for option in spec["options"]:
            target_file = out_dir / "schemas" / f"pos-option-{option['id'].lower()}.json"
            with open(target_file, "w", encoding="utf-8", newline="\n") as handle:
                json.dump(target_pos(pos_data, option, f"POS cible, option {option['id']} : {option['name']}"),
                          handle, ensure_ascii=False, indent=2)
                handle.write("\n")
            report["outputs"].append(str(target_file))
    if decision:
        adr = out_dir / "adr-architecture.md"
        with open(adr, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_adr(spec, ranking, catalog, idx, reviews, wa))
        report["outputs"].append(str(adr))
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
