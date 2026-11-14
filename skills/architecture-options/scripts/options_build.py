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
option dit où elle se place (`placement`) : pos_impact.py (skill
urbanization-map) vérifie les noms dans le POS, compte créations,
évolutions, remplacements, redondances et flux entre zones et écrit le POS
cible de chaque option (`schemas/pos-option-<id>.json`, pour pos_build.py) ;
le script ajoute le critère « urbanisation ».

Avec `hosting` (qualifications exigées : secnumcloud, hds, et les exigences
qui les portent), l'hébergeur de chaque option est comparé au catalogue
commun des hébergeurs (shared/providers.json) : sans la qualification, l'option
ne couvre pas ces exigences (écart ajouté, éliminée si l'une est
indispensable).

Chaque option cloud (`provider`) passe la revue Well-Architected des piliers
(wa_check.py du skill well-architected-review) : constats par pilier dans
`options.md`, détail dans `schemas/option-<id>.wa.md`, constats de l'option
retenue dans l'ADR. Un écart assumé s'accepte avec sa raison (`wa_accept`).

Sans `criteria`, les critères sont les catégories des exigences non
fonctionnelles retenues, pondérées par leur plus haute priorité
(indispensable 3, importante 2, souhaitable 1).

Avec `--draft` (options.json absent), le script écrit un brouillon depuis le
catalogue : critères pondérés, qualifications d'hébergeur exigées par les
exigences (`hosting`), deux options à décrire et la recommandation ; le
rapport liste les hébergeurs du catalogue qui ont ces qualifications et les
exigences indispensables à couvrir. Le modèle n'écrit que les choix.

    uv run scripts/options_build.py options.json [--decision decision.json] [--out-dir DOSSIER] | --schema
    uv run scripts/options_build.py options.json --draft [--requirements exigences.json]
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, load_module, require_file, schema_of  # noqa: E402
from spec_schema import check, input_schema, print_schema, read_spec, schema_option  # noqa: E402
from text_tools import cell  # noqa: E402

# Position des options dans le POS du SI (skill urbanization-map), déclaré dans requires.
POS = load_module("urbanization-map", "pos_impact.py")
WEIGHTS = {"indispensable": 3, "importante": 2, "souhaitable": 1}
CATEGORY_LABELS = {"performance": "Performance", "disponibilite": "Disponibilité", "securite": "Sécurité",
                   "conformite": "Conformité", "exploitabilite": "Exploitabilité",
                   "maintenabilite": "Maintenabilité", "evolutivite": "Évolutivité",
                   "interoperabilite": "Interopérabilité", "utilisabilite": "Utilisabilité",
                   "portabilite": "Portabilité", "cout": "Coût", "autre": "Autre"}
LEVELS = {"partiel": "partielle", "non": "non couverte"}
WA_PILLARS = ("reliability", "security", "operations", "performance", "cost")


def load_wa():
    """wa_check.py du skill well-architected-review (et son cloud_build.py), ou None s'il manque."""
    module = load_module("well-architected-review", "wa_check.py")
    return module if module and not module.MISSING else None


def nature(req: dict) -> str | None:
    """Comme requirements-catalog : champ nature, sinon préfixe EF- ou ENF-."""
    return req.get("nature") or {"EF": "fonctionnelle", "ENF": "non-fonctionnelle"}.get(req["id"].split("-")[0])


def load_catalog(base: Path, spec: dict, errors: list[str], warnings: list[str]) -> dict[str, dict]:
    path = base / spec.get("requirements", "exigences.json")
    try:
        catalog = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"requirements : catalogue illisible {path} ({error})")
        return {}
    # Le catalogue est validé contre le schéma de req_build.py (skill requirements-catalog).
    schema = schema_of("requirements-catalog", "req_build.py")
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent("requirements-catalog", "req_build.py"))
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


QUALIFICATIONS = {"secnumcloud": r"secnum\s*cloud", "hds": r"\bhds\b|h[ée]bergeur de donn[ée]es de sant[ée]"}


def draft(path: Path, requirements: str) -> dict:
    """Brouillon d'options.json depuis le catalogue : critères, qualifications exigées, squelette des options."""
    errors, warnings = [], []
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une description")
        return {"input": str(path), "errors": errors, "warnings": warnings}
    catalog = load_catalog(path.parent, {"requirements": requirements}, errors, warnings)
    if errors:
        return {"input": str(path), "errors": errors, "warnings": warnings}
    kept = {k: r for k, r in catalog.items() if r.get("status", "retenue") == "retenue"}
    hosting: dict = {}
    required, refs = [], []
    for ref, req in kept.items():
        text = " ".join(str(req.get(k, "")) for k in ("title", "text", "metric")).lower()
        for name, pattern in QUALIFICATIONS.items():
            if re.search(pattern, text):
                required += [name] if name not in required else []
                refs += [ref] if ref not in refs else []
    if required:
        hosting = {"qualifications": required, "refs": refs}
    providers = [k for k, v in PROVIDERS["providers"].items() if all(q in v["qualifications"] for q in required)]
    criteria = default_criteria(kept)
    skeleton = {"id": "", "name": "À nommer", "summary": "À écrire",
                "components": [{"id": "a-definir", "label": "À définir"}], "flows": [], "gaps": {},
                "scores": {c["id"]: 3 for c in criteria}, "score_notes": {c["id"]: "À justifier" for c in criteria},
                "pros": [], "cons": [], "risks": []}
    spec = {"_draft": "Brouillon de options_build.py --draft : nommer et décrire 2 ou 3 options (composants avec "
                      "refs, flux, provider et type pour une option cloud, écarts), noter chaque critère de 1 à 5 "
                      "avec sa raison, écrire la recommandation, puis retirer cette clé.",
            "title": "Options d'architecture : " + catalog_title(path.parent / requirements),
            "requirements": requirements,
            "criteria": criteria,
            "options": [{**skeleton, "id": "A"}, {**skeleton, "id": "B"}],
            "recommendation": {"option": "A", "why": "À écrire"}}
    if hosting:
        spec["hosting"] = hosting
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(spec, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    must = [k for k, r in kept.items() if r.get("priority") == "indispensable"]
    return {"input": str(path), "draft": str(path), "criteria": [c["id"] for c in criteria],
            "hosting": hosting or None, "providers": providers if required else None,
            "indispensables": must, "errors": errors, "warnings": warnings}


def catalog_title(path: Path) -> str:
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("title") or "projet"
    except (OSError, ValueError):
        return "projet"


def check_refs(where: str, refs, catalog: dict, errors: list[str]) -> None:
    for ref in refs:
        if ref not in catalog:
            errors.append(f"{where} : exigence inconnue {ref}")
        elif catalog[ref].get("status") == "retiree":
            errors.append(f"{where} : {ref} est retirée du catalogue")


def tech_of(comp: dict) -> str:
    """Technologie d'un composant, suivie de sa version si elle est fixée."""
    return comp["tech"] + (f" {comp['version']}" if comp.get("version") else "")


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
        label = comp["label"] + (f"\n({tech_of(comp)})" if comp.get("tech") else "")
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


def cloud_spec(option: dict, qualifications: list[str] | None = None) -> dict:
    """Description cloud_build.py d'une option hébergée chez un fournisseur."""
    items = [{"id": c["id"], "type": c.get("type") or CLOUD_TYPES[c.get("role", "system")], "label": c["label"],
              **({"count": c["count"]} if c.get("count") else {})} for c in option["components"]]
    flows = [{k: f[k] for k in ("from", "to", "label", "style", "protocol") if f.get(k)}
             for f in option.get("flows", [])]
    spec = {"_source": "généré par options_build.py", "title": f"Option {option['id']} : {option['name']}",
            "provider": option["provider"], "items": items, "flows": flows}
    if qualifications:
        spec["qualifications"] = qualifications
    return spec


# Catalogue commun des hébergeurs (shared/providers.json), copie unique dans cloud-architecture.
PROVIDERS = json.loads(require_file("cloud-architecture", "lib/providers.json").read_text(encoding="utf-8"))


def check_hosting(spec: dict, option: dict, where: str, catalog: dict, warnings: list[str]) -> None:
    """Qualifications exigées (hosting) : l'hébergeur de l'option qui ne les a pas ne couvre pas les exigences
    citées (écart « non » ajouté, l'option est éliminée si l'une est indispensable)."""
    hosting = spec.get("hosting") or {}
    required = hosting.get("qualifications") or []
    if not required:
        return
    name = option.get("provider")
    info = PROVIDERS["providers"].get(name or "")
    if not info:
        warnings.append(f"{where} : qualifications {', '.join(required)} non vérifiées (option sans provider "
                        "connu du catalogue des hébergeurs)")
        return
    missing = [q for q in required if q not in info["qualifications"]]
    if not missing:
        return
    pending = [q for q in missing if q in info.get("pending", [])]
    note = f"{info['name']} sans {', '.join(missing)}" + (f" (en cours : {', '.join(pending)})" if pending else "")
    gaps = option.setdefault("gaps", {})
    added = [r for r in hosting.get("refs", []) if r in catalog and r not in gaps]
    for ref in added:
        gaps[ref] = {"level": "non", "note": note + " (catalogue des hébergeurs)"}
    warnings.append(f"option {option['id']} : {note}" + (f", écart ajouté sur {', '.join(added)}" if added else ""))


def wa_review(wa, option: dict, where: str, errors: list[str], warnings: list[str],
              qualifications: list[str] | None = None) -> dict:
    """Revue Well-Architected des piliers d'une option cloud (sans les conventions de schéma)."""
    findings, errs, clouds = wa.check(cloud_spec(option, qualifications))
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
        comps = ", ".join(c["label"] + (f" ({tech_of(c)})" if c.get("tech") else "") for c in option["components"])
        lines.append(f"**Composants** : {comps}.")
        for key, label in (("pros", "Avantages"), ("cons", "Inconvénients"), ("risks", "Risques")):
            if option.get(key):
                lines += ["", f"**{label}**", ""] + [f"- {item}" for item in option[key]]
        if idx and option.get("placement"):
            lines += ["", "**Position dans le SI**", ""] + POS.placement_lines(option, idx)
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
        lines += ["", "## Position dans le SI", ""] + POS.placement_lines(chosen, idx) + \
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
    errors: list[str] = []
    warnings: list[str] = []
    catalog = load_catalog(base, spec, errors, warnings)
    pos_data, idx, impacts = None, None, []
    if POS:
        # Placement de chaque option dans le POS du SI : impacts, redondances, flux entre zones.
        pos_data, idx, impacts = POS.analyse(spec, base, errors, warnings)
    elif spec.get("pos"):
        errors.append("pos : " + absent("urbanization-map", "pos_impact.py"))
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
    ranking, reviews = [], []
    wa = load_wa() if any(o.get("provider") for o in spec["options"]) else None
    if wa is None and any(o.get("provider") for o in spec["options"]):
        warnings.append("revue Well-Architected non faite : "
                        + absent("well-architected-review", "wa_check.py") + " (et cloud-architecture)")
    for index, option in enumerate(spec["options"]):
        where = f"options/{index} ({option['id']})"
        comp_ids = [c["id"] for c in option["components"]]
        if len(set(comp_ids)) != len(comp_ids):
            errors.append(f"{where}/components : identifiant en double")
        errors += [f"{where}/components/{ci}/version : version « {c['version']} » sans technologie (tech)"
                   for ci, c in enumerate(option["components"]) if c.get("version") and not c.get("tech")]
        for fi, flow in enumerate(option.get("flows", [])):
            for end in ("from", "to"):
                if flow[end] not in comp_ids:
                    errors.append(f"{where}/flows/{fi}/{end} : composant inconnu « {flow[end]} »")
        check_refs(f"{where}/gaps", option.get("gaps", {}), catalog, errors)
        check_hosting(spec, option, where, catalog, warnings)
        if wa and option.get("provider"):
            reviews.append(wa_review(wa, option, where, errors, warnings,
                                     (spec.get("hosting") or {}).get("qualifications")))
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
    check_refs("hosting/refs", (spec.get("hosting") or {}).get("refs", []), catalog, errors)
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
    parser.add_argument("--draft", action="store_true",
                        help="écrit un brouillon d'options.json depuis le catalogue d'exigences")
    parser.add_argument("--requirements", default="exigences.json",
                        help="avec --draft : catalogue, relatif au .json (défaut : exigences.json)")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    if args.draft:
        report = draft(args.spec, args.requirements)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    spec, invalid = read_spec(args.spec, __file__)
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
                json.dump(cloud_spec(option, (spec.get("hosting") or {}).get("qualifications")), handle, ensure_ascii=False, indent=2)
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
        report["outputs"] += POS.write_targets(pos_data, spec, out_dir / "schemas")
    if decision:
        adr = out_dir / "adr-architecture.md"
        with open(adr, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_adr(spec, ranking, catalog, idx, reviews, wa))
        report["outputs"].append(str(adr))
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
