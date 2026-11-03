# /// script
# requires-python = ">=3.10"
# ///
"""Chiffre l'option d'architecture retenue : réalisation, infrastructure, run et coût total.

Entrée : une description JSON courte (`chiffrage.json`) : taux journaliers
par profil, lots de travail (composant de l'option, exigences, charge par
profil en jours, nombre ou estimation à trois points [mini, probable,
maxi]), frais de pilotage en pourcentage, provision pour risques, lignes
d'infrastructure (quantité, prix unitaire, période, base du prix), run
(jours par an ou pourcentage de la réalisation), budget. Le script, et non le
modèle :
- vérifie les profils, les composants de l'option dans options.json
  (architecture-options) et les exigences du catalogue (requirements-catalog) ;
- calcule la charge espérée de chaque lot (PERT : (mini + 4 probable +
  maxi) / 6), la fourchette P10-P90 de la réalisation (loi normale, lots
  indépendants), le pilotage, la provision, l'infrastructure par an et
  ponctuelle, le run par an et le coût total sur l'horizon ;
- refait ces calculs pour trois hypothèses de production : sans IA (charges
  saisies), avec IA et dev IA natif (facteur par phase ou par lot,
  incertitude sur le gain, adoption, licences et jetons, run), avec les
  valeurs de references/hypotheses-ia.json que la description peut remplacer ;
- signale les exigences retenues qu'aucun lot ne porte, les composants de
  l'option sans lot ni ligne d'infrastructure, les postes souvent oubliés
  (tests de sécurité, environnements hors production, réseau, recette, mise
  en production, formation) qu'aucun lot, ligne, hypothèse ni exclusion ne
  cite, les estimations très
  incertaines et les dépassements de budget ;
- écrit `chiffrage.md` (revue), `chiffrage.csv` (lignes détaillées) et
  `chiffrage.hypotheses.csv`, relit les CSV et vérifie que leurs montants
  redonnent les totaux.

L'option chiffrée est `option`, sinon la décision de options.json, sinon sa
recommandation. Les prix d'infrastructure sont des hypothèses saisies avec
leur base : aucun tarif n'est consulté en ligne.

    uv run scripts/estimate_build.py chiffrage.json [--out-dir DOSSIER] [--vault VAULT --folder DOSSIER_DU_VAULT] | --schema

Avec `--draft`, le script écrit d'abord la description à compléter (il ne
réécrit jamais un fichier existant) : un lot par composant de l'option à
construire ou à intégrer, avec ses exigences, les lots transverses (cadrage,
recette, tests de sécurité si des exigences de sécurité existent, mise en
production, formation), pilotage, provision et run aux valeurs usuelles
(`_draft` les liste), budget tiré des exigences de coût et lignes
d'infrastructure de cloud-cost (`--infra <nom>.infra.json`), et les lots des experts
(`--lots`, répétable : frontend de ui_breakdown.py, mockup-to-html ; backend
d'api_breakdown.py, api-contract), qui remplacent le lot global de chaque
composant qu'ils couvrent. Le modèle n'y écrit que les charges (`effort`, vide
dans chaque lot), les taux et ce qu'il corrige.

    uv run scripts/estimate_build.py chiffrage.json --draft [--option ID] [--infra couts.infra.json] [--lots front.lots.json --lots api.lots.json]

Réemploi : un lot qui réutilise un autre lot ou un existant (`reuse` : from,
percent, basis) voit sa charge baisser de la part réutilisée ; le taux de
réemploi est donné. Points à challenger : marges cumulées (pilotage,
provision, asymétrie des trois points), part de la réalisation, lots trop
gros, lots semblables sans réemploi déclaré, jours par exigence, avec les
seuils des abaques donnés avant le lancement (~/.myskills/abaques.json ou
MYSKILLS_ABAQUES, references.abaques de mission.json, --abaques), sinon des
seuils par défaut à calibrer.

Avec `--vault`, le chiffrage va aussi dans le vault Obsidian du workflow, selon
son ontologie : une note chiffrage (coût total, charge, budget, hébergeur ;
relation evalue vers la note de l'option) et une note par lot (porte-sur ses
exigences), vérifiées avant l'écriture.
"""

import argparse
import csv
import difflib
import json
import math
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, require_module, schema_of  # noqa: E402
from spec_schema import check, input_schema, print_schema, validate  # noqa: E402
import workspace  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")

Z90 = 1.2816  # quantile 90 % de la loi normale : fourchette P10-P90
PHASES = {"cadrage": "Cadrage", "conception": "Conception", "realisation": "Réalisation",
          "integration": "Intégration", "tests": "Tests et recette", "deploiement": "Déploiement",
          "migration": "Reprise de données", "conduite-changement": "Conduite du changement",
          "pilotage": "Pilotage"}
PERIODS = {"mois": 12, "an": 1, "unique": 0}
COMPLEXITY = {"faible": "Faible", "moyenne": "Moyenne", "elevee": "Élevée", "tres-elevee": "Très élevée"}
SIZES = ((5, "faible"), (15, "moyenne"), (40, "elevee"))  # jours espérés d'une tâche : complexité déduite
UNCERTAIN = 1.0  # (maxi - mini) / probable au-delà : estimation à découper ou hypothèse à lever
# Catalogue commun des hébergeurs (shared/providers.json, copié par scripts/build.py).
PROVIDERS = Path(__file__).resolve().parent / "lib" / "providers.json"
# Hypothèses de production par défaut : sans IA (charges saisies), avec IA, dev IA natif.
SCENARIOS = Path(__file__).resolve().parent.parent / "references" / "hypotheses-ia.json"
STALE_DAYS = 180  # catalogue des hébergeurs plus ancien : qualifications à revérifier
QUALIFIED_KINDS = ("cloud", "service")  # lignes soumises aux qualifications exigées
# Seuils des points à challenger, à calibrer : remplacés par la section challenge des abaques de
# l'utilisateur ou de la mission (shared/schemas/abaques.schema.json, workspace.abaques).
CHALLENGE = {"max_margin": 35, "realisation_min_share": 0.4, "max_lot_days": 40, "similarity": 0.8}
BUILD_PHASES = ("realisation", "integration")


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def money(value: float, currency: str) -> str:
    return f"{value:,.0f}".replace(",", " ") + f" {currency}"


def pct(share: float) -> str:
    """Part (0 à 1) en pourcentage, à la française."""
    return f"{share * 100:.0f} %"


def days(value: float) -> str:
    return f"{value:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0")


def hint(value: str, choices) -> str:
    close = difflib.get_close_matches(value, list(choices), n=1, cutoff=0.6)
    return f" ; vouliez-vous « {close[0]} » ?" if close else f" (connus : {', '.join(choices)})"


def load_json(base: Path, name: str, field: str, skill: str, script: str,
              errors: list[str], warnings: list[str]) -> dict | None:
    """Fichier d'un autre skill, validé contre le schéma d'entrée de son script s'il est installé."""
    path = base / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{field} : fichier illisible {path} ({error})")
        return None
    schema = schema_of(skill, script)
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent(skill, script))
    invalid = check(data, schema) if schema else []
    if invalid:
        errors.extend(f"{field} : {path.name} : {e}" for e in invalid[:10])
        return None
    return data if isinstance(data, dict) else None


def load_providers(base: Path, spec: dict, errors: list[str], warnings: list[str]) -> tuple[dict, str | None]:
    """Catalogue des hébergeurs du skill, complété par celui du projet (champ providers), validés."""
    schema = input_schema(__file__)
    providers, checked = {}, None
    for path in [PROVIDERS] + ([base / spec["providers"]] if spec.get("providers") else []):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"providers : catalogue illisible {path} ({error})")
            continue
        invalid = check(data, schema["$defs"]["providers"], schema)
        if invalid:
            errors.extend(f"providers : {path.name} : {e}" for e in invalid[:10])
            continue
        providers.update(data["providers"])
        checked = data.get("checked", checked)
    if checked and (date.today() - date.fromisoformat(checked)).days > STALE_DAYS:
        warnings.append(f"catalogue des hébergeurs vérifié le {checked} : revérifier les qualifications "
                        "sur la liste de l'ANSSI")
    return providers, checked


def pick_option(spec: dict, arch: dict, errors: list[str], warnings: list[str]) -> tuple[dict | None, str]:
    options = {o["id"]: o for o in arch.get("options", [])}
    decision, rec = arch.get("decision"), arch.get("recommendation") or {}
    if spec.get("option"):
        wanted, status = spec["option"], "choisie pour ce chiffrage"
        if decision and decision["option"] != wanted:
            warnings.append(f"option {wanted} chiffrée, mais la décision retient l'option {decision['option']}")
    elif decision:
        wanted, status = decision["option"], "retenue"
    else:
        wanted, status = rec.get("option", ""), "recommandée (décision non prise)"
        warnings.append(f"option {wanted} chiffrée sur la recommandation : aucune décision dans options.json")
    if wanted not in options:
        errors.append(f"option : option inconnue « {wanted} »{hint(wanted, options)}")
        return None, status
    return options[wanted], status


# Postes souvent oubliés : règles de complétude livrées (references/postes-attendus.json), complétées par celles
# de l'utilisateur et de la mission (workspace.rules). Textes comparés sans accents ni majuscules.
EXPECTED = Path(__file__).resolve().parent.parent / "references" / "postes-attendus.json"


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def applies(rule: dict, catalog, option: dict, infra: bool) -> bool:
    """Condition (when) d'une règle de complétude : toutes requises, aucune = toujours."""
    when = rule.get("when", {})
    categories = {r.get("category") for r in catalog if r.get("status") != "retiree"}
    roles = {c.get("role", "system") for c in option.get("components", [])}
    return (not when.get("categories") or bool(categories & set(when["categories"]))) \
        and (not when.get("roles") or bool(roles & set(when["roles"]))) \
        and (not when.get("infra") or infra) \
        and (not when.get("cloud") or (bool(option.get("provider")) and infra))


def forgotten(spec: dict, catalog: dict, option: dict, rules: list[dict]) -> list[dict]:
    """Postes attendus qu'aucun lot de leur phase, ligne d'infrastructure, hypothèse ni exclusion ne cite."""
    texts = [w.get("name", "") for w in spec.get("work", [])] + \
        [f"{i.get('name', '')} {i.get('basis', '')} {i.get('environment', '')}" for i in spec.get("infra", [])] + \
        [str(a) for a in spec.get("assumptions", []) + spec.get("exclusions", [])]
    corpus = plain(" ".join(texts))
    phases = {w.get("phase") for w in spec.get("work", [])}
    return [rule for rule in rules
            if applies(rule, catalog.values(), option, bool(spec.get("infra")))
            and rule.get("phase") not in phases and not re.search(rule["pattern"], corpus)]


DEFAULTS = {"pilotage": 12, "contingency": 10, "run": 15}
MONEY = re.compile(r"(\d[\d  .]*)\s*(?:€|euros?|eur)\s*(?:par|/)\s*(mois|an)", re.I)


def draft(path: Path, option_id: str | None, infra: Path | None, rules: list[dict], lots: list[Path] | None = None) -> dict:
    """Écrit le brouillon de chiffrage.json ; rapport court (lots, charges à estimer)."""
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(path), "outputs": [], "option": None, "lots": 0, "to_estimate": 0,
              "errors": errors, "warnings": warnings}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une description")
        return report
    base = path.parent
    arch = load_json(base, "options.json", "architecture", "architecture-options", "options_build.py", errors, warnings)
    cat = load_json(base, "exigences.json", "requirements", "requirements-catalog", "req_build.py", errors, warnings)
    option, _ = pick_option({"option": option_id} if option_id else {}, arch, errors, warnings) if arch else (None, "")
    lines = []
    if infra:
        try:
            lines = json.loads(infra.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"--infra : {infra} illisible ({error})")
    # Lots des experts (frontend : ui_breakdown.py, backend : api_breakdown.py) : même format, {work: [...]}.
    experts = []
    for file in lots or []:
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"--lots : {file} illisible ({error})")
            continue
        if not isinstance(data, dict) or not isinstance(data.get("work"), list) or not data["work"]:
            errors.append(f"--lots : {file} sans liste work (<nom>.lots.json de ui_breakdown.py ou api_breakdown.py)")
            continue
        experts.append((file, data))
    if errors or not option:
        return report
    catalog = [r for r in (cat or {}).get("requirements", []) if r.get("status") != "retiree"]
    work = []
    for comp in option["components"]:
        if comp.get("role") == "person":
            continue
        external = comp.get("role") == "external"
        work.append({"id": "", "name": f"Intégration avec {comp['label']}" if external else comp["label"],
                     "phase": "integration" if external or comp.get("role") == "queue" else "realisation",
                     "component": comp["id"], "effort": {}})
    # Lots des experts : ils remplacent le lot global de chaque composant qu'ils couvrent.
    known = {c["id"] for c in option["components"]}
    for file, data in experts:
        covered = {data["component"]} if data.get("component") else set()
        covered |= {w["component"] for w in data["work"] if isinstance(w, dict) and w.get("component")}
        unknown = sorted(covered - known)
        if unknown:
            errors += [f"--lots : {file.name} : composant « {u} » absent de l'option {option['id']} "
                       f"({', '.join(sorted(known))})" for u in unknown]
            continue
        work = [w for w in work if w.get("component") not in covered]
        work += [{**w, "_from": (file.name, w.get("id"))} for w in data["work"] if isinstance(w, dict)]
        domain = data.get("domain") or ("frontend" if data["work"][0].get("id", "").startswith("F") else "d'expert")
        warnings.append(f"--lots : {len(data['work'])} lots {domain} repris de {file.name} avec leurs charges "
                        "d'abaque, à relire")
    if errors:
        return report
    work.append({"id": "", "name": "Cadrage et architecture détaillée", "phase": "cadrage", "effort": {}})
    for rule in rules:
        if rule.get("draft") and applies(rule, catalog, option, bool(lines)):
            work.append({"id": "", "name": rule["draft"]["name"], "phase": rule["draft"]["phase"], "effort": {}})
    order = list(PHASES)
    work.sort(key=lambda w: order.index(w["phase"]))
    renamed, owner = {}, {}
    for n, task in enumerate(work, 1):
        if "_from" in task:
            key = task.pop("_from")
            renamed[key], owner[n] = f"L{n}", key[0]
        task["id"] = f"L{n}"
    # Réemploi déclaré par un expert : il vise un lot de son propre fichier, renuméroté ici.
    for n, task in enumerate(work, 1):
        source = task.get("reuse", {}).get("from")
        if source and (owner.get(n), source) in renamed:
            target = renamed[(owner[n], source)]
            task["reuse"] = {**task["reuse"], "from": target,
                             "basis": re.sub(rf"\b{re.escape(source)}\b", target, task["reuse"]["basis"])}
    spec = {"title": f"Chiffrage : {option['name']}", "option": option["id"], "work": work,
            "overheads": [{"id": "P1", "name": "Pilotage", "percent": DEFAULTS["pilotage"],
                           "profile": "chef-de-projet"}],
            "contingency": DEFAULTS["contingency"],
            "run": [{"id": "R1", "name": "Maintenance corrective et évolutive",
                     "percent_of_build": DEFAULTS["run"]}],
            "assumptions": [], "exclusions": [],
            "_draft": f"Brouillon de estimate_build.py --draft : charges (effort) à estimer, taux (rates) à donner ; "
                      f"valeurs usuelles à revoir : pilotage {DEFAULTS['pilotage']} %, provision "
                      f"{DEFAULTS['contingency']} %, run {DEFAULTS['run']} % de la réalisation."}
    if lines:
        spec["infra"] = lines
    budget, refs = {}, []
    for r in catalog:
        if r.get("category") != "cout":
            continue
        for amount, period in MONEY.findall(f"{r.get('metric', '')} {r.get('text', '')}"):
            value = int(re.sub(r"[  .]", "", amount))
            budget.setdefault("monthly" if period.lower() == "mois" else "build", value)
            refs.append(r["id"])
    if budget:
        spec["budget"] = {**budget, "refs": sorted(set(refs))}
    invalid = validate({**spec, "work": [{**w, "effort": w["effort"] or {"x": 1}} for w in work]}, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], option=option["id"], lots=len(work), to_estimate=sum(1 for w in work if not w["effort"]))
    return report


def three_points(value) -> tuple[float, float, float, float, float]:
    """(mini, probable, maxi, espérance, écart type) d'une charge en jours."""
    if isinstance(value, list):
        low, likely, high = value
        return low, likely, high, (low + 4 * likely + high) / 6, (high - low) / 6
    return value, value, value, float(value), 0.0


def apply_reuse(spec: dict, errors: list[str]) -> dict:
    """Réemploi entre fonctionnalités : la charge d'un lot qui réutilise un autre lot (ou un existant) baisse
    de sa part réutilisée. Les charges de la description deviennent nettes ; renvoie le bilan du réemploi."""
    ids = [w["id"] for w in spec["work"]]
    gross = saved = 0.0
    items = []
    for index, task in enumerate(spec["work"]):
        expected = sum(three_points(v)[3] for v in task["effort"].values()
                       if not isinstance(v, list) or len(v) == 3)
        gross += expected
        reuse = task.get("reuse")
        if not reuse:
            continue
        where = f"work/{index} ({task['id']})/reuse"
        source = reuse.get("from")
        if source == task["id"]:
            errors.append(f"{where}/from : un lot ne se réutilise pas lui-même")
            continue
        if source and source not in ids:
            errors.append(f"{where}/from : lot inconnu « {source} »{hint(source, ids)}")
            continue
        keep = 1 - reuse["percent"] / 100
        task["effort"] = {name: [round(x * keep, 2) for x in value] if isinstance(value, list) else round(value * keep, 2)
                          for name, value in task["effort"].items()}
        saved += expected * reuse["percent"] / 100
        items.append({"id": task["id"], "from": source or "", "percent": reuse["percent"], "basis": reuse["basis"],
                      "saved": round(expected * reuse["percent"] / 100, 2)})
    return {"lots": len(items), "gross_days": round(gross, 1), "saved_days": round(saved, 1),
            "rate": round(saved / gross, 3) if gross else 0.0, "items": items}


def challenge(spec: dict, found: dict, catalog: dict, conf: dict, reuse: dict, sources: list[str],
              warnings: list[str]) -> dict:
    """Points à challenger, pour qu'un relecteur les fasse justifier : marges cumulées, réalisation noyée dans
    les lots transverses, lots trop gros, lots semblables sans réemploi déclaré, jours par exigence."""
    limits = {**CHALLENGE, **conf}
    lots = [x for x in found["lines"] if x["type"] == "lot"]
    expected = sum(x["days"] for x in lots)
    likely = sum(x["likely"] for x in lots)
    skew = (expected - likely) / likely if likely else 0.0
    pilotage = sum(o["percent"] for o in spec.get("overheads", [])) / 100
    contingency = spec.get("contingency", 0) / 100
    total = (1 + pilotage) * (1 + contingency) * (1 + skew) - 1
    size: dict[str, float] = {}
    for line in lots:
        size[line["id"]] = size.get(line["id"], 0.0) + line["days"]
    build = sum(x["days"] for x in lots if x["phase"] in BUILD_PHASES)
    share = build / expected if expected else 0.0
    large = [i for i, d in size.items() if d > limits["max_lot_days"]]
    linked = {(t["id"], t["reuse"]["from"]) for t in spec["work"] if t.get("reuse", {}).get("from")}
    reusing = {t["id"] for t in spec["work"] if t.get("reuse")}
    similar = []
    work = spec["work"]
    for i, a in enumerate(work):
        for b in work[i + 1:]:
            # Deux lots d'un même découpage d'expert : son script a déjà déduit leur réemploi.
            expert = all("abaque" in t.get("note", "") for t in (a, b))
            if expert or a["phase"] != b["phase"] or a.get("component") != b.get("component") \
                    or (a["id"], b["id"]) in linked or (b["id"], a["id"]) in linked or b["id"] in reusing:
                continue
            close = difflib.SequenceMatcher(None, plain(a["name"]), plain(b["name"])).ratio() >= limits["similarity"]
            if close or (a.get("refs") and sorted(a["refs"]) == sorted(b.get("refs", []))):
                similar.append([a["id"], b["id"]])
    retained = sum(1 for r in catalog.values()
                   if r.get("status", "retenue") == "retenue" and r.get("priority") != "hors-perimetre")
    per_req = round(expected / retained, 2) if retained else None
    found_points = []
    if total * 100 > limits["max_margin"]:
        found_points.append(f"marges cumulées {pct(total)} (pilotage {pct(pilotage)}, provision {pct(contingency)}, "
                            f"maxima des trois points {pct(skew)}) au-delà de {limits['max_margin']:g} % : "
                            "une marge par risque, pas une par niveau")
    if expected and share < limits["realisation_min_share"]:
        found_points.append(f"réalisation et intégration à {pct(share)} de la charge des lots, sous "
                            f"{pct(limits['realisation_min_share'])} : lots transverses à justifier")
    if large:
        found_points.append(f"lot(s) de plus de {limits['max_lot_days']:g} j espérés : {', '.join(large)} ; "
                            "les découper pour les estimer")
    if similar:
        found_points.append("lots semblables sans réemploi déclaré : "
                            + ", ".join(f"{a}/{b}" for a, b in similar[:10]) + " ; déclarer reuse ou dire ce qui diffère")
    span = limits.get("days_per_requirement")
    if span and per_req is not None and not span[0] <= per_req <= span[1]:
        found_points.append(f"{days(per_req)} j de lots par exigence retenue, hors de {span[0]:g} à {span[1]:g}")
    warnings += [f"challenge : {text}" for text in found_points]
    return {"margin": {"pilotage": round(pilotage * 100, 1), "contingency": round(contingency * 100, 1),
                       "skew": round(skew * 100, 1), "total": round(total * 100, 1)},
            "realisation_share": round(share, 3), "days_per_requirement": per_req, "large": large,
            "similar": similar, "reuse_rate": reuse["rate"], "points": found_points,
            "limits": {k: v for k, v in limits.items()}, "calibrated": bool(sources), "abaques": sources}


def render_challenge(found: dict) -> list[str]:
    """Section du chiffrage : réemploi et points à challenger, avec les seuils utilisés."""
    ch, reuse = found["challenge"], found["reuse"]
    m, lim = ch["margin"], ch["limits"]
    origin = "abaques fournis" if ch["calibrated"] else "par défaut, à calibrer"
    out = ["## Points à challenger", "", f"Seuils : {origin}.", "", "| Indicateur | Valeur | Seuil |", "| --- | --- | --- |",
           f"| Marges cumulées (pilotage {days(m['pilotage'])} %, provision {days(m['contingency'])} %, maxima des "
           f"trois points {days(m['skew'])} %) | {days(m['total'])} % | {lim['max_margin']:g} % |",
           f"| Part de la réalisation et de l'intégration | {pct(ch['realisation_share'])} | "
           f"au moins {pct(lim['realisation_min_share'])} |",
           f"| Lots de plus de {lim['max_lot_days']:g} j | {', '.join(ch['large']) or 'aucun'} | 0 |",
           f"| Lots semblables sans réemploi | {', '.join('/'.join(p) for p in ch['similar'][:10]) or 'aucun'} | 0 |",
           f"| Taux de réemploi | {pct(reuse['rate'])} ({days(reuse['saved_days'])} j sur {days(reuse['gross_days'])} j bruts) | |"]
    if ch["days_per_requirement"] is not None:
        span = lim.get("days_per_requirement")
        out.append(f"| Jours de lots par exigence retenue | {days(ch['days_per_requirement'])} | "
                   f"{f'{span[0]:g} à {span[1]:g}' if span else 'non fixé'} |")
    out.append("")
    out += [f"- {cell(p)}" for p in ch["points"]] or ["Aucun point au-delà des seuils."]
    if reuse["items"]:
        out += ["", "### Réemploi", "", "| Lot | Réutilise | Part | Jours épargnés | Base |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {r['id']} | {r['from'] or 'existant'} | {r['percent']:g} % | {days(r['saved'])} | {cell(r['basis'])} |"
                for r in reuse["items"]]
    return out + [""]


def phase_shares(spec: dict) -> dict[str, float]:
    """Part de chaque phase dans la charge espérée des lots (0 à 1)."""
    days: dict[str, float] = {}
    for task in spec.get("work", []):
        for value in task.get("effort", {}).values():
            days[task["phase"]] = days.get(task["phase"], 0.0) + three_points(value)[3]
    total = sum(days.values())
    return {k: v / total for k, v in days.items()} if total else {}


def analogy(spec_path: Path, spec: dict, errors: list[str], warnings: list[str]) -> dict | None:
    """Calibration par analogie avec les missions passées désignées dans mission.json (analogues).

    Lecture seule : seuls les noms des missions et les parts par phase sortent, rien de leur contenu."""
    root = workspace.find(spec_path)
    if not root:
        return None
    mission, invalid = workspace.load(root)
    if not mission or not mission.get("analogues"):
        return None
    past: dict[str, dict[str, float]] = {}
    for index, item in enumerate(mission["analogues"]):
        path = Path(item["path"])
        path = path if path.is_absolute() else root / path
        if path.is_dir():
            path = path / "chiffrage.json"
        name = item.get("name") or path.parent.name
        try:
            other = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            warnings.append(f"analogues/{index} : chiffrage illisible « {item['path']} » ({error.__class__.__name__}), ignoré")
            continue
        if validate(other, __file__):
            warnings.append(f"analogues/{index} : « {item['path']} » n'est pas un chiffrage valide, ignoré")
            continue
        shares = phase_shares(other)
        if shares:
            past[name] = shares
    if not past:
        warnings.append("analogues : aucun chiffrage passé exploitable, calibration impossible")
        return None
    current = phase_shares(spec)
    phases, deviations = {}, []
    for phase in [p for p in PHASES if p in current or any(p in s for s in past.values())]:
        values = [s.get(phase, 0.0) for s in past.values()]
        low, high = min(values), max(values)
        share = current.get(phase, 0.0)
        phases[phase] = {"share": round(share, 3), "range": [round(low, 3), round(high, 3)]}
        if not share and low:
            deviations.append(phase)
            warnings.append(f"analogie : phase {phase} absente, présente dans toutes les missions comparées "
                            f"({low:.0%} à {high:.0%})")
        elif share and (share < low * 0.67 or share > high * 1.5):
            deviations.append(phase)
            warnings.append(f"analogie : phase {phase} à {share:.0%} de la charge, {low:.0%} à {high:.0%} "
                            "dans les missions comparées")
    return {"missions": list(past), "phases": phases, "deviations": deviations}


def analyse(spec: dict, catalog: dict, option: dict, providers: dict, checked: str | None,
            errors: list[str], warnings: list[str], rules: list[dict]) -> dict:
    """Contrôles croisés et calculs ; les montants ne sont valables que sans erreur."""
    rates = spec.get("rates")  # sans taux : mode charges, jours et heures seulement
    if rates is not None and not rates:
        errors.append("rates : au moins un profil attendu, ou pas de champ rates pour les charges seules")
    comps = {c["id"]: c for c in option["components"]}
    ids: dict[str, str] = {}

    def unique(item_id: str, where: str) -> None:
        if item_id in ids:
            errors.append(f"{where} : identifiant « {item_id} » déjà pris ({ids[item_id]})")
        ids[item_id] = where

    def profile(name: str, where: str) -> float:
        if rates is None:
            return 0.0
        if name not in rates:
            errors.append(f"{where} : profil inconnu « {name} »{hint(name, rates)}")
            return 0.0
        return rates[name]

    def component(name: str | None, where: str) -> None:
        if name and name not in comps:
            errors.append(f"{where} : composant inconnu « {name} » dans l'option {option['id']}{hint(name, comps)}")

    def refs(values, where: str) -> None:
        for ref in values:
            if catalog and ref not in catalog:
                errors.append(f"{where} : exigence inconnue {ref}")
            elif catalog.get(ref, {}).get("status") == "retiree":
                errors.append(f"{where} : {ref} est retirée du catalogue")

    lines, uncertain = [], []
    work_days = work_var = work_cost = cost_var = 0.0
    for index, task in enumerate(spec["work"]):
        where = f"work/{index} ({task['id']})"
        unique(task["id"], where)
        component(task.get("component"), where)
        refs(task.get("refs", []), f"{where}/refs")
        if not task["effort"]:
            errors.append(f"{where}/effort : charge à estimer, en jours par profil (au moins un)")
        for name, value in task["effort"].items():
            rate = profile(name, f"{where}/effort/{name}")
            low, likely, high, expected, sd = three_points(value)
            if not low <= likely <= high:
                errors.append(f"{where}/effort/{name} : [mini, probable, maxi] attendu dans l'ordre croissant, reçu {value}")
                continue
            if likely and (high - low) / likely > UNCERTAIN and task["id"] not in uncertain:
                uncertain.append(task["id"])
            work_days += expected
            work_var += sd ** 2
            work_cost += expected * rate
            cost_var += (sd * rate) ** 2
            lines.append({"type": "lot", "id": task["id"], "name": task["name"], "phase": task["phase"],
                          "component": task.get("component", ""), "profile": name, "low": low, "likely": likely,
                          "high": high, "days": expected, "rate": rate, "cost": expected * rate,
                          "refs": task.get("refs", []), "sd": sd, "ai": task.get("ai", {}),
                          "complexity": task.get("complexity")})

    over_days = over_cost = 0.0
    for index, item in enumerate(spec.get("overheads", [])):
        where = f"overheads/{index} ({item['id']})"
        unique(item["id"], where)
        rate = profile(item["profile"], f"{where}/profile")
        amount = work_days * item["percent"] / 100
        over_days += amount
        over_cost += amount * rate
        lines.append({"type": "pilotage", "id": item["id"], "name": item["name"], "phase": "pilotage",
                      "component": "", "profile": item["profile"], "low": "", "likely": "", "high": "",
                      "days": amount, "rate": rate, "cost": amount * rate, "refs": [],
                      "percent": item["percent"]})

    infra = []
    for index, item in enumerate(spec.get("infra", [])):
        where = f"infra/{index} ({item['id']})"
        unique(item["id"], where)
        component(item.get("component"), where)
        amount = item.get("quantity", 1) * item["unit_cost"]
        infra.append({**item, "annual": amount * PERIODS[item["period"]],
                      "one_time": amount if item["period"] == "unique" else 0.0})
    hosting = check_hosting(spec, option, infra, providers, checked, errors, warnings)
    refs(spec.get("hosting", {}).get("refs", []), "hosting/refs")

    contingency = spec.get("contingency", 0) / 100
    sd_days, sd_cost = math.sqrt(work_var), math.sqrt(cost_var)
    f_days = over_days / work_days if work_days else 0.0
    f_cost = over_cost / work_cost if work_cost else 0.0
    base_cost = work_cost + over_cost
    build = {"days": round(work_days + over_days, 1),
             "days_low": round(max(work_days - Z90 * sd_days, 0) * (1 + f_days), 1),
             "days_high": round((work_days + Z90 * sd_days) * (1 + f_days), 1),
             "cost": round(base_cost * (1 + contingency)),
             "cost_low": round(max(work_cost - Z90 * sd_cost, 0) * (1 + f_cost) * (1 + contingency)),
             "cost_high": round((work_cost + Z90 * sd_cost) * (1 + f_cost) * (1 + contingency)),
             "contingency": round(base_cost * contingency)}

    run = []
    for index, item in enumerate(spec.get("run", [])):
        where = f"run/{index} ({item['id']})"
        unique(item["id"], where)
        if ("days_per_year" in item) == ("percent_of_build" in item):
            errors.append(f"{where} : donnez soit days_per_year (avec profile), soit percent_of_build")
            continue
        if "days_per_year" in item:
            if "profile" not in item:
                errors.append(f"{where} : champ « profile » manquant avec days_per_year")
                continue
            rate = profile(item["profile"], f"{where}/profile")
            run.append({**item, "rate": rate, "annual": item["days_per_year"] * rate})
        else:
            run.append({**item, "annual": base_cost * item["percent_of_build"] / 100})

    infra_annual = sum(i["annual"] for i in infra)
    infra_once = sum(i["one_time"] for i in infra)
    run_annual = sum(r["annual"] for r in run)
    horizon = spec.get("horizon", 3)
    totals = {"build": build,
              "infra": {"one_time": round(infra_once), "monthly": round(infra_annual / 12),
                        "annual": round(infra_annual)},
              "run": {"annual": round(run_annual)},
              "operate": {"monthly": round((infra_annual + run_annual) / 12)},
              "tco": {"years": horizon,
                      "total": round(build["cost"] + infra_once + horizon * (infra_annual + run_annual))}}

    # Couverture : exigences portées par un lot (refs) ou par un composant chiffré de l'option.
    priced = {t.get("component") for t in spec["work"]} | {i.get("component") for i in spec.get("infra", [])}
    covered = {r for t in spec["work"] for r in t.get("refs", [])}
    covered |= {r for cid in priced if cid in comps for r in comps[cid].get("refs", [])}
    not_delivered = {g for g, gap in option.get("gaps", {}).items() if gap["level"] == "non"}
    unestimated = [rid for rid, req in catalog.items()
                   if req.get("status", "retenue") == "retenue" and req["priority"] != "hors-perimetre"
                   and rid not in covered and rid not in not_delivered]
    uncovered = [cid for cid, c in comps.items()
                 if c.get("role", "system") in ("system", "db", "queue") and cid not in priced]
    if errors:
        unestimated, uncovered, uncertain = [], [], []
    if unestimated:
        warnings.append(f"exigence(s) retenue(s) qu'aucun lot ne porte : {', '.join(unestimated)}")
    if uncovered:
        warnings.append(f"composant(s) de l'option {option['id']} sans lot ni ligne d'infrastructure : "
                        f"{', '.join(uncovered)}")
    if uncertain:
        warnings.append(f"estimation(s) très incertaine(s) (écart mini-maxi supérieur au probable) : "
                        f"{', '.join(uncertain)} ; découper le lot ou lever l'hypothèse")
    if rates is not None and option.get("provider") and not any(i["kind"] == "cloud" for i in infra):
        warnings.append(f"option {option['id']} hébergée chez {option['provider']} sans ligne d'infrastructure cloud")
    if not spec.get("assumptions"):
        warnings.append("aucune hypothèse notée (assumptions)")
    missing = [] if errors else forgotten(spec, catalog, option, rules)
    if missing:
        warnings.append(f"poste(s) souvent oublié(s), absent(s) : {'; '.join(r['label'] for r in missing)} ; "
                        "ajouter un lot ou une ligne, ou le noter dans assumptions ou exclusions")

    budget = spec.get("budget")
    over = []
    if budget:
        refs(budget.get("refs", []), "budget/refs")
        for key, label, value in (("build", "réalisation", build["cost"]),
                                  ("monthly", "fonctionnement par mois", totals["operate"]["monthly"]),
                                  ("tco", f"coût total sur {horizon} an(s)", totals["tco"]["total"])):
            if key in budget and value > budget[key]:
                over.append(key)
                warnings.append(f"budget dépassé, {label} : {value} pour {budget[key]} "
                                f"({', '.join(budget.get('refs', [])) or 'sans exigence citée'})")
    totals["budget"] = None if not budget else {"over": over}
    totals["hosting"] = hosting
    found = {"lines": lines, "infra": infra, "run": run, "totals": totals, "unestimated": unestimated,
             "uncovered": uncovered, "uncertain": uncertain, "missing": [r["id"] for r in missing]}
    found["scenarios"] = scenarios(spec, found, profile, errors, warnings)
    if rates is None and spec.get("infra"):
        warnings.append("infra ignorée : sans rates, seules les charges (jours, heures) sont produites")
    found["charges"] = charges(spec, found, warnings)
    return found


def charges(spec: dict, found: dict, warnings: list[str]) -> dict:
    """Charges sans montant : par tâche (complexité, jours, heures) et par hypothèse de production."""
    hours = spec.get("hours_per_day", 7)
    lots = [x for x in found["lines"] if x["type"] == "lot"]
    size: dict[str, float] = {}
    for line in lots:
        size[line["id"]] = size.get(line["id"], 0.0) + line["days"]
    deduced = []
    for line in lots:
        if not line["complexity"]:
            line["complexity"] = next((c for limit, c in SIZES if size[line["id"]] <= limit), "tres-elevee")
            line["deduced"] = True
            if line["id"] not in deduced:
                deduced.append(line["id"])
    if deduced:
        warnings.append(f"complexité déduite de la charge (au plus 5 j faible, 15 moyenne, 40 élevée) : "
                        f"{', '.join(deduced)} ; donnez complexity si elle tient à autre chose que la taille")
    build_days = found["totals"]["build"]["days"]
    run_days = sum(r["days_per_year"] if "days_per_year" in r else build_days * r["percent_of_build"] / 100
                   for r in found["run"])
    out = {"hours_per_day": hours, "tasks": len(size),
           "by_complexity": {c: sum(1 for i, n in size.items()
                                    if next(x for x in lots if x["id"] == i)["complexity"] == c) for c in COMPLEXITY},
           "run_days_per_year": round(run_days, 1),
           "scenarios": [{"id": sc["id"], "name": sc["name"], "days": sc["build"]["days"],
                          "days_low": sc["build"]["days_low"], "days_high": sc["build"]["days_high"],
                          "hours": round(sc["build"]["days"] * hours)} for sc in found["scenarios"]]}
    return out


def load_scenarios(spec: dict, errors: list[str], warnings: list[str]) -> dict:
    """Hypothèses par défaut du skill, validées, remplacées champ à champ par celles de la description."""
    schema = input_schema(__file__)
    try:
        data = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"scenarios : fichier illisible {SCENARIOS} ({error})")
        return {}
    invalid = check(data, schema["$defs"]["scenarios"], schema)
    if invalid:
        errors.extend(f"scenarios : {SCENARIOS.name} : {e}" for e in invalid[:10])
        return {}
    merged = {}
    for sid, default in data["scenarios"].items():
        own = spec.get("scenarios", {}).get(sid, {})
        mine = sorted(k for k in own if k not in ("name", "description", "basis"))
        if mine and "basis" not in own:
            warnings.append(f"scenarios/{sid} : valeurs propres au projet sans base (basis) : "
                            "mesure de l'équipe, lot pilote ou hypothèse à faire valider")
            own = {**own, "basis": "non donnée pour les valeurs du projet, à faire valider"}
        merged[sid] = {**default, **own, "factors": {**default.get("factors", {}), **own.get("factors", {})},
                       "own": mine}
    return merged


def scenarios(spec: dict, found: dict, profile, errors: list[str], warnings: list[str]) -> list[dict]:
    """Mêmes calculs que la réalisation et le run, avec le facteur de chaque phase ou lot de l'hypothèse."""
    defs = load_scenarios(spec, errors, warnings)
    lots = [x for x in found["lines"] if x["type"] == "lot"]
    base_days = sum(x["days"] for x in lots)
    base_cost = sum(x["cost"] for x in lots)
    avg_rate = base_cost / base_days if base_days else 0.0
    t = found["totals"]
    build0 = t["build"]["cost"] / (1 + spec.get("contingency", 0) / 100)  # réalisation hors provision, sans IA
    results = []
    for sid, scen in defs.items():
        # Écart type : celui des lots (indépendants), plus l'incertitude sur le gain, commune à tous les lots.
        rows, w_days, w_var, w_cost, c_var, g_days, g_cost = [], 0.0, 0.0, 0.0, 0.0, 0.0, 0.0
        for line in lots:
            factor = line["ai"].get(sid, scen["factors"].get(line["phase"], 1))
            sd = line["sd"] * factor
            gain_sd = line["days"] * abs(1 - factor) * scen.get("gain_uncertainty", 0)
            w_days += line["days"] * factor
            w_var += sd ** 2
            w_cost += line["days"] * factor * line["rate"]
            c_var += (sd * line["rate"]) ** 2
            g_days += gain_sd
            g_cost += gain_sd * line["rate"]
            rows.append({"type": "lot", "id": line["id"], "name": line["name"], "phase": line["phase"],
                         "profile": line["profile"], "factor": factor, "days": line["days"] * factor,
                         "rate": line["rate"], "cost": line["days"] * factor * line["rate"], "annual": 0})
        setup_days = base_days * scen.get("setup_percent", 0) / 100
        setup_rate = profile(scen["setup_profile"], f"scenarios/{sid}/setup_profile") \
            if scen.get("setup_profile") else avg_rate
        if setup_days:
            rows.append({"type": "adoption", "id": "A", "name": "Adoption : outillage, garde-fous, formation",
                         "phase": "", "profile": scen.get("setup_profile", "taux moyen"), "factor": "",
                         "days": setup_days, "rate": setup_rate, "cost": setup_days * setup_rate, "annual": 0})
        over_days = over_cost = 0.0
        for item in spec.get("overheads", []):
            rate = next(x["rate"] for x in found["lines"] if x["id"] == item["id"])
            amount = (w_days + setup_days) * item["percent"] / 100
            over_days, over_cost = over_days + amount, over_cost + amount * rate
            rows.append({"type": "pilotage", "id": item["id"], "name": item["name"], "phase": "pilotage",
                         "profile": item["profile"], "factor": "", "days": amount, "rate": rate,
                         "cost": amount * rate, "annual": 0})
        per_day = scen.get("tooling_per_day", 0)
        tooling = per_day * (w_days + setup_days)
        if tooling:
            rows.append({"type": "outillage", "id": "O", "name": "Outillage IA : licences et jetons", "phase": "",
                         "profile": "", "factor": "", "days": "", "rate": per_day, "cost": tooling, "annual": 0})
        contingency = scen.get("contingency", spec.get("contingency", 0)) / 100
        sd_days, sd_cost = math.sqrt(w_var + g_days ** 2), math.sqrt(c_var + g_cost ** 2)
        fixed_days, fixed_cost = setup_days, setup_days * setup_rate + tooling
        f_days = over_days / (w_days + setup_days) if w_days + setup_days else 0.0
        f_cost = over_cost / (w_cost + setup_days * setup_rate) if w_cost + setup_days * setup_rate else 0.0
        base = w_cost + fixed_cost + over_cost
        low_c = max(w_cost - Z90 * sd_cost, 0) + setup_days * setup_rate
        high_c = w_cost + Z90 * sd_cost + setup_days * setup_rate
        build = {"days": round(w_days + setup_days + over_days, 1),
                 "days_low": round((max(w_days - Z90 * sd_days, 0) + fixed_days) * (1 + f_days), 1),
                 "days_high": round((w_days + Z90 * sd_days + fixed_days) * (1 + f_days), 1),
                 "cost": round(base * (1 + contingency)),
                 "cost_low": round((low_c * (1 + f_cost) + per_day * (max(w_days - Z90 * sd_days, 0) + fixed_days))
                                   * (1 + contingency)),
                 "cost_high": round((high_c * (1 + f_cost) + per_day * (w_days + Z90 * sd_days + fixed_days))
                                    * (1 + contingency)),
                 "contingency": round(base * contingency), "setup": round(setup_days * setup_rate),
                 "tooling": round(tooling)}
        run_annual = run_tooling = 0.0
        for item in found["run"]:
            factor = scen.get("run_factor", 1)
            if "days_per_year" in item:
                amount = item["days_per_year"] * factor * item["rate"]
                run_tooling += item["days_per_year"] * factor * per_day
            else:
                amount = build0 * item["percent_of_build"] / 100 * factor
            run_annual += amount
            rows.append({"type": "run", "id": item["id"], "name": item["name"], "phase": "",
                         "profile": item.get("profile", ""), "factor": factor,
                         "days": item["days_per_year"] * factor if "days_per_year" in item else "",
                         "rate": item.get("rate", ""), "cost": 0, "annual": amount})
        if run_tooling:
            rows.append({"type": "outillage", "id": "O-run", "name": "Outillage IA du run", "phase": "", "profile": "",
                         "factor": "", "days": "", "rate": per_day, "cost": 0, "annual": run_tooling})
            run_annual += run_tooling
        horizon = t["tco"]["years"]
        infra_annual, infra_once = t["infra"]["annual"], t["infra"]["one_time"]
        tco = round(build["cost"] + infra_once + horizon * (infra_annual + run_annual))
        budget, over = spec.get("budget") or {}, []
        values = {"build": build["cost"], "monthly": round((infra_annual + run_annual) / 12), "tco": tco}
        over = [k for k in ("build", "monthly", "tco") if k in budget and values[k] > budget[k]]
        results.append({"id": sid, "name": scen["name"], "build": build,
                        "run": {"annual": round(run_annual), "tooling": round(run_tooling)},
                        "operate": {"monthly": values["monthly"]}, "tco": {"total": tco}, "budget_over": over,
                        "rows": rows, "scenario": scen})
    ref = results[0]["tco"]["total"] if results else 0
    for item in results:
        item["delta"] = round((item["tco"]["total"] - ref) / ref * 100, 1) if ref else 0.0
    return results


def check_hosting(spec: dict, option: dict, infra: list[dict], providers: dict, checked: str | None,
                  errors: list[str], warnings: list[str]) -> dict | None:
    """Hébergeur de chaque ligne (ligne, hosting, sinon provider de l'option), qualifications exigées."""
    hosting = spec.get("hosting", {})
    default = hosting.get("provider")
    unknown = [(f"hosting/provider", default)] if default and default not in providers else []
    unknown += [(f"infra/{index} ({item['id']})/provider", item["provider"]) for index, item in enumerate(infra)
                if item.get("provider") and item["provider"] not in providers]
    if unknown:
        errors.extend(f"{where} : hébergeur inconnu « {name} »{hint(name, providers)}" for where, name in unknown)
        return None
    if not default and option.get("provider") in providers:
        default = option["provider"]
    elif default and option.get("provider") and option["provider"] != default:
        warnings.append(f"option {option['id']} décrite chez {option['provider']}, chiffrée chez {default} : "
                        "revoir l'option dans options.json (schéma, revue Well-Architected)")
    if not default and not hosting and not any(i.get("provider") for i in infra):
        return None
    required = hosting.get("qualifications", [])
    noncompliant, by_provider = [], {}
    to_check = set()
    for item in infra:
        name = item.get("provider") or default
        item["host"] = name or ""
        total = by_provider.setdefault(name or "non-precise", {"annual": 0.0, "one_time": 0.0})
        total["annual"] += item["annual"]
        total["one_time"] += item["one_time"]
        if item["kind"] not in QUALIFIED_KINDS or not required:
            continue
        held = providers.get(name, {}).get("qualifications", [])
        missing = [q for q in required if q not in held]
        if not missing:
            to_check.add(name)
        else:
            noncompliant.append(item["id"])
            pending = [q for q in missing if q in providers.get(name, {}).get("pending", [])]
            warnings.append(f"infra {item['id']} : " + (f"{providers[name]['name']} sans {', '.join(missing)}"
                            if name else "hébergeur non précisé")
                            + (f" (qualification en cours : {', '.join(pending)})" if pending else "")
                            + f", exigé par {', '.join(hosting.get('refs', [])) or 'hosting'}")
    for name in sorted(to_check):
        if providers[name].get("note"):
            warnings.append(f"{providers[name]['name']} : {providers[name]['note']}")
    return {"provider": default, "required": required, "noncompliant": noncompliant,
            "providers": {k: {"annual": round(v["annual"]), "one_time": round(v["one_time"])}
                          for k, v in by_provider.items()},
            "checked": checked}


def render_hosting(spec: dict, found: dict, providers: dict) -> list[str]:
    host, cur = found["totals"]["hosting"], spec.get("currency", "€")
    if not host:
        return []
    out = ["## Hébergement", ""]
    if host["required"]:
        out += [f"Qualifications exigées : {', '.join(host['required'])}"
                + (f" ({', '.join(spec['hosting']['refs'])})" if spec.get("hosting", {}).get("refs") else "") + ".", ""]
    out += ["| Hébergeur | Juridiction | Qualifications | Par an | Ponctuel | Note |", "| --- | --- | --- | --- | --- | --- |"]
    for name, total in host["providers"].items():
        info = providers.get(name, {"name": "non précisé", "jurisdiction": "", "qualifications": []})
        quals = (", ".join(info["qualifications"]) or "aucune") + (f" (en cours : {', '.join(info['pending'])})"
                                                                   if info.get("pending") else "")
        out.append(f"| {info['name']} | {info['jurisdiction']} | {quals} | {money(total['annual'], cur)} | "
                   f"{money(total['one_time'], cur)} | {cell(info.get('note', ''))} |")
    out += ["", "Lignes non conformes aux qualifications exigées : "
            + (", ".join(host["noncompliant"]) if host["noncompliant"] else "aucune") + ".",
            f"Qualifications selon le catalogue des hébergeurs vérifié le {host['checked'] or 'non daté'} : "
            "une qualification porte sur une offre, à confirmer sur la liste de l'ANSSI.", ""]
    return out


def render_scenarios(spec: dict, found: dict) -> list[str]:
    """Comparaison des trois hypothèses de production, facteurs par phase et base de chaque hypothèse."""
    cur, items = spec.get("currency", "€"), found["scenarios"]
    if not items:
        return []
    horizon = found["totals"]["tco"]["years"]
    head = "| Poste | " + " | ".join(i["name"] for i in items) + " |"
    rule = "| --- |" + " --- |" * len(items)

    def row(label: str, value) -> str:
        return f"| {label} | " + " | ".join(value(i) for i in items) + " |"

    out = ["## Hypothèses de production", "",
           "Même périmètre chiffré trois fois : sans IA (charges saisies), avec IA (développement assisté) et "
           "dev IA natif (agents qui écrivent le code, l'équipe spécifie et valide). Les gains réduisent la charge "
           "et sont eux-mêmes incertains (incertitude sur le gain, commune à tous les lots, ajoutée à la fourchette) : "
           "ils restent à confirmer sur un lot pilote.", "", head, rule,
           row("Réalisation, charge", lambda i: f"{days(i['build']['days'])} j ({days(i['build']['days_low'])} à "
                                                f"{days(i['build']['days_high'])})"),
           row("Réalisation, coût", lambda i: f"{money(i['build']['cost'], cur)} ({money(i['build']['cost_low'], cur)}"
                                              f" à {money(i['build']['cost_high'], cur)})"),
           row("dont adoption de l'IA", lambda i: money(i["build"]["setup"], cur)),
           row("dont outillage IA (licences, jetons)", lambda i: money(i["build"]["tooling"], cur)),
           row("Run par an", lambda i: money(i["run"]["annual"], cur)),
           row("Fonctionnement par mois", lambda i: money(i["operate"]["monthly"], cur)),
           row(f"**Coût total sur {horizon} an(s)**", lambda i: f"**{money(i['tco']['total'], cur)}**"),
           row("Écart avec sans IA", lambda i: "référence" if i["id"] == "sans-ia"
               else f"{i['delta']:+.1f} %".replace(".", ","))]
    if spec.get("budget"):
        out.append(row("Budget", lambda i: ("dépassé : " + ", ".join(i["budget_over"])) if i["budget_over"] else "tenu"))
    phases = [p for p in PHASES if any(line["phase"] == p for line in found["lines"] if line["type"] == "lot")]
    out += ["", "### Facteurs appliqués à la charge sans IA", "",
            "| Phase | " + " | ".join(i["name"] for i in items[1:]) + " |", "| --- |" + " --- |" * (len(items) - 1)]
    out += [f"| {PHASES[p]} | " + " | ".join(num(i["scenario"]["factors"].get(p, 1)) for i in items[1:]) + " |"
            for p in phases]
    for label, key, fmt in (("Incertitude sur le gain (écart type relatif)", "gain_uncertainty", num),
                            ("Adoption, % de la charge des lots", "setup_percent", num),
                            (f"Outillage IA par jour travaillé ({cur})", "tooling_per_day", num),
                            ("Facteur du run", "run_factor", num)):
        out.append(f"| {label} | " + " | ".join(fmt(i["scenario"].get(key, 0 if key in ("setup_percent", "tooling_per_day", "gain_uncertainty") else 1))
                                              for i in items[1:]) + " |")
    lots = [t for t in spec["work"] if t.get("ai")]
    if lots:
        out += ["", "Facteurs propres à un lot : " + " ; ".join(
            f"{t['id']} " + ", ".join(f"{k} {num(v)}" for k, v in t["ai"].items())
            + (f" ({cell(t['note'])})" if t.get("note") else "") for t in lots) + "."]
    out += [""] + [f"- **{i['name']}** : {cell(i['scenario']['description'])} Base : {cell(i['scenario']['basis'])}"
                   + (f" (valeurs du projet : {', '.join(i['scenario']['own'])})" if i["scenario"]["own"] else "")
                   + "." for i in items] + [""]
    return out


def render_md(spec: dict, option: dict, status: str, found: dict, providers: dict) -> str:
    cur, t = spec.get("currency", "€"), found["totals"]
    build, horizon = t["build"], t["tco"]["years"]
    out = [f"# {spec.get('title') or 'Chiffrage'}", ""]
    if spec.get("context"):
        out += [spec["context"], ""]
    out += [f"Option {option['id']} : {option['name']}, {status}. Fourchette P10-P90 calculée sur les "
            "estimations à trois points (lots indépendants). Prix d'infrastructure : hypothèses saisies "
            "avec leur base, aucun tarif consulté en ligne.", "",
            "## Synthèse", "", "| Poste | Montant |", "| --- | --- |",
            f"| Réalisation, charge | {days(build['days'])} j (de {days(build['days_low'])} à {days(build['days_high'])} j) |",
            f"| Réalisation, coût | {money(build['cost'], cur)} (de {money(build['cost_low'], cur)} à "
            f"{money(build['cost_high'], cur)}), dont provision {money(build['contingency'], cur)} |",
            f"| Infrastructure ponctuelle | {money(t['infra']['one_time'], cur)} |",
            f"| Infrastructure récurrente | {money(t['infra']['annual'], cur)} par an "
            f"({money(t['infra']['monthly'], cur)} par mois) |",
            f"| Maintenance et exploitation | {money(t['run']['annual'], cur)} par an |",
            f"| Fonctionnement (infrastructure et run) | {money(t['operate']['monthly'], cur)} par mois |",
            f"| **Coût total sur {horizon} an(s)** | **{money(t['tco']['total'], cur)}** |", ""]
    budget = spec.get("budget")
    if budget:
        values = {"build": build["cost"], "monthly": t["operate"]["monthly"], "tco": t["tco"]["total"]}
        labels = {"build": "Réalisation", "monthly": "Fonctionnement par mois", "tco": f"Coût total sur {horizon} an(s)"}
        out += ["### Budget", "", "| Poste | Budget | Chiffré | Écart |", "| --- | --- | --- | --- |"]
        for key in ("build", "monthly", "tco"):
            if key in budget:
                gap = values[key] - budget[key]
                verdict = f"dépassé de {money(gap, cur)}" if gap > 0 else "tenu"
                out.append(f"| {labels[key]} | {money(budget[key], cur)} | {money(values[key], cur)} | {verdict} |")
        if budget.get("refs"):
            out.append(f"\nExigences : {', '.join(budget['refs'])}.")
        out.append("")

    out += render_scenarios(spec, found)
    tasks = [line for line in found["lines"] if line["type"] == "lot"]
    out += ["## Réalisation par lot", "",
            "| Lot | Phase | Composant | Exigences | Profil | Mini | Probable | Maxi | Espérés | Coût |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for line in tasks:
        out.append(f"| {line['id']} {cell(line['name'])} | {PHASES[line['phase']]} | {line['component']} | "
                   f"{', '.join(line['refs'])} | {line['profile']} | {days(line['low'])} | {days(line['likely'])} | "
                   f"{days(line['high'])} | {days(line['days'])} | {money(line['cost'], cur)} |")
    for line in (x for x in found["lines"] if x["type"] == "pilotage"):
        out.append(f"| {line['id']} {cell(line['name'])} | Pilotage |  |  | {line['profile']} | "
                   f"{line['percent']} % |  |  | {days(line['days'])} | {money(line['cost'], cur)} |")
    out.append("")

    by_phase: dict[str, list[float]] = {}
    by_profile: dict[str, list[float]] = {}
    for line in found["lines"]:
        by_phase.setdefault(line["phase"], [0.0, 0.0])
        by_profile.setdefault(line["profile"], [0.0, 0.0])
        for target in (by_phase[line["phase"]], by_profile[line["profile"]]):
            target[0] += line["days"]
            target[1] += line["cost"]
    out += ["### Par phase", "", "| Phase | Jours | Coût |", "| --- | --- | --- |"]
    out += [f"| {PHASES[k]} | {days(v[0])} | {money(v[1], cur)} |" for k, v in
            sorted(by_phase.items(), key=lambda kv: list(PHASES).index(kv[0]))]
    out += ["", "### Par profil", "", "| Profil | Taux journalier | Jours | Coût |", "| --- | --- | --- | --- |"]
    out += [f"| {k} | {money(spec['rates'][k], cur)} | {days(v[0])} | {money(v[1], cur)} |"
            for k, v in by_profile.items()]
    if build["contingency"]:
        out += ["", f"Provision pour risques : {spec['contingency']} % du coût de réalisation, "
                f"{money(build['contingency'], cur)}."]
    out.append("")

    if found["infra"]:
        out += ["## Infrastructure", "",
                "| Ligne | Composant | Hébergeur | Environnement | Nature | Quantité | Prix unitaire | Période | Par an | Ponctuel | Base du prix |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for item in found["infra"]:
            out.append(f"| {item['id']} {cell(item['name'])} | {item.get('component', '')} | {item.get('host', '')} | "
                       f"{item.get('environment', 'production')} | {item['kind']} | {item.get('quantity', 1)} | "
                       f"{money(item['unit_cost'], cur)} | {item['period']} | {money(item['annual'], cur)} | "
                       f"{money(item['one_time'], cur)} | {cell(item['basis'])} |")
        out.append("")
    out += render_hosting(spec, found, providers)
    if found["run"]:
        out += ["## Maintenance et exploitation", "", "| Poste | Base | Par an |", "| --- | --- | --- |"]
        for item in found["run"]:
            base = (f"{days(item['days_per_year'])} j par an, {item['profile']}" if "days_per_year" in item
                    else f"{item['percent_of_build']} % de la réalisation hors provision")
            out.append(f"| {item['id']} {cell(item['name'])} | {base} | {money(item['annual'], cur)} |")
        out.append("")

    yearly = t["infra"]["annual"] + t["run"]["annual"]
    out += [f"## Coût total sur {horizon} an(s)", "", "| Année | Réalisation | Infrastructure | Run | Total |",
            "| --- | --- | --- | --- | --- |",
            f"| 0 | {money(build['cost'], cur)} | {money(t['infra']['one_time'], cur)} |  | "
            f"{money(build['cost'] + t['infra']['one_time'], cur)} |"]
    out += [f"| {year} |  | {money(t['infra']['annual'], cur)} | {money(t['run']['annual'], cur)} | "
            f"{money(yearly, cur)} |" for year in range(1, horizon + 1)]
    out += [f"| **Total** | | | | **{money(t['tco']['total'], cur)}** |", ""]

    out += render_challenge(found)
    out += ["## Couverture", ""]
    out.append("- Exigences retenues qu'aucun lot ne porte : "
               + (", ".join(found["unestimated"]) if found["unestimated"] else "aucune") + ".")
    out.append("- Composants de l'option sans lot ni ligne d'infrastructure : "
               + (", ".join(found["uncovered"]) if found["uncovered"] else "aucun") + ".")
    if found["uncertain"]:
        out.append(f"- Estimations très incertaines : {', '.join(found['uncertain'])}.")
    out.append("")
    for key, label in (("assumptions", "Hypothèses"), ("exclusions", "Exclusions")):
        if spec.get(key):
            out += [f"## {label}", ""] + [f"- {cell(x)}" for x in spec[key]] + [""]
    return "\n".join(out)


CSV_HEAD = ["type", "id", "libellé", "phase", "composant", "profil", "mini", "probable", "maxi", "jours",
            "taux", "par an", "ponctuel", "coût réalisation", "exigences", "base", "hébergeur"]


def num(value) -> str:
    """Nombre du CSV avec la virgule décimale (séparateur point-virgule, tableurs en français)."""
    return value if isinstance(value, str) else str(round(value, 2)).replace(".", ",").removesuffix(",0")


def csv_rows(found: dict) -> list[list]:
    rows = [CSV_HEAD]
    for line in found["lines"]:
        rows.append([line["type"], line["id"], line["name"], line["phase"], line["component"], line["profile"],
                     line["low"], line["likely"], line["high"], line["days"], line["rate"], 0, 0,
                     line["cost"], " ".join(line["refs"]), "", ""])
    for item in found["infra"]:
        rows.append(["infra", item["id"], item["name"], "", item.get("component", ""), "", "", "", "", "",
                     item["unit_cost"], item["annual"], item["one_time"], 0, "", item["basis"], item.get("host", "")])
    for item in found["run"]:
        rows.append(["run", item["id"], item["name"], "", "", item.get("profile", ""), "", "", "",
                     item.get("days_per_year", ""), item.get("rate", ""), item["annual"], 0, 0, "", "", ""])
    return [[num(v) if isinstance(v, (int, float)) else v for v in row] for row in rows]


def hrs(value: float, per_day: float) -> str:
    return f"{round(value * per_day):,}".replace(",", " ")


def render_charges(spec: dict, option: dict, status: str, found: dict) -> str:
    """Plan de charge sans montant : tâches, complexité, jours et heures, par hypothèse de production."""
    ch, scen = found["charges"], found["scenarios"]
    per_day = ch["hours_per_day"]
    names = [x["name"] for x in scen[1:]]
    out = [f"# Charges : {spec.get('title') or 'Chiffrage'}", ""]
    if spec.get("context"):
        out += [spec["context"], ""]
    out += [f"Option {option['id']} : {option['name']}, {status}. Charges en jours et en heures ({num(per_day)} h "
            "par jour), sans taux journalier : la valorisation se fait à part. Fourchette P10-P90 calculée sur les "
            "estimations à trois points.", "", "## Synthèse", "",
            "| Hypothèse | Jours | Fourchette P10-P90 | Heures |", "| --- | --- | --- | --- |"]
    out += [f"| {x['name']} | {days(x['days'])} | {days(x['days_low'])} à {days(x['days_high'])} | {hrs(x['days'], per_day)} |"
            for x in ch["scenarios"]]
    out += ["", f"{ch['tasks']} tâches : " + ", ".join(f"{n} {COMPLEXITY[c].lower()}" for c, n in ch["by_complexity"].items()
                                                        if n) + "."]
    if ch["run_days_per_year"]:
        out.append(f"Maintenance et exploitation : {days(ch['run_days_per_year'])} j par an sans IA "
                   f"({hrs(ch['run_days_per_year'], per_day)} h).")
    out += ["", "## Détail par tâche", "",
            "| Tâche | Phase | Composant | Complexité | Profil | Mini | Probable | Maxi | Jours | Heures | "
            + " | ".join(f"{n} (j)" for n in names) + " |", "| --- " * (10 + len(names)) + "|"]
    for row in charge_rows(found):
        if row["type"] == "adoption":
            continue
        complexity = COMPLEXITY.get(row["complexity"], "") + (" (déduite)" if row.get("deduced") else "")
        out.append(f"| {row['id']} {cell(row['name'])} | {PHASES.get(row['phase'], '')} | {row['component']} | "
                   f"{complexity} | {row['profile']} | {days(row['low']) if row['low'] != '' else ''} | "
                   f"{days(row['likely']) if row['likely'] != '' else str(row.get('percent', '')) + ' %'} | "
                   f"{days(row['high']) if row['high'] != '' else ''} | {days(row['days'])} | {hrs(row['days'], per_day)} | "
                   + " | ".join(days(v) for v in row["by_scenario"][1:]) + " |")
    setup = [next((r["days"] for r in x["rows"] if r["type"] == "adoption"), 0) for x in scen]
    if any(setup):
        out.append("| Adoption de l'IA : outillage, garde-fous, formation |  |  |  |  |  |  |  |  |  | "
                   + " | ".join(days(v) for v in setup[1:]) + " |")
    for label, key in (("Par phase", "phase"), ("Par profil", "profile")):
        groups: dict[str, list[float]] = {}
        for row in charge_rows(found):
            if row["type"] != "adoption":
                acc = groups.setdefault(row[key], [0.0] * len(scen))
                for i, v in enumerate(row["by_scenario"]):
                    acc[i] += v
        out += ["", f"### {label}", "", f"| {label[4:].capitalize()} | Jours | Heures | " + " | ".join(f"{n} (j)" for n in names)
                + " |", "| --- " * (3 + len(names)) + "|"]
        out += [f"| {PHASES.get(k, k)} | {days(v[0])} | {hrs(v[0], per_day)} | " + " | ".join(days(x) for x in v[1:]) + " |"
                for k, v in groups.items()]
    out.append("")
    out += render_challenge(found)
    for key, label in (("assumptions", "Hypothèses"), ("exclusions", "Exclusions")):
        if spec.get(key):
            out += [f"## {label}", ""] + [f"- {cell(x)}" for x in spec[key]] + [""]
    return "\n".join(out)


def charge_rows(found: dict) -> list[dict]:
    """Lignes de charge (tâche par profil, pilotage, adoption) avec leurs jours dans chaque hypothèse."""
    scen = found["scenarios"]
    rows = []
    for index, line in enumerate(x for x in found["lines"] if x["type"] in ("lot", "pilotage")):
        mine = [[r for r in x["rows"] if r["type"] in ("lot", "pilotage")][index]["days"] for x in scen]
        rows.append({**line, "complexity": line.get("complexity") or "", "by_scenario": mine})
    setup = [next((r["days"] for r in x["rows"] if r["type"] == "adoption"), 0.0) for x in scen]
    if any(setup):
        rows.append({"type": "adoption", "id": "A", "name": "Adoption de l'IA", "phase": "", "component": "",
                     "complexity": "", "profile": "", "low": "", "likely": "", "high": "", "days": 0.0,
                     "by_scenario": setup})
    return rows


CHARGE_HEAD = ["type", "id", "tâche", "phase", "composant", "complexité", "profil", "mini", "probable", "maxi",
               "jours", "heures"]


def charge_csv(found: dict) -> list[list]:
    per_day, scen = found["charges"]["hours_per_day"], found["scenarios"]
    rows = [CHARGE_HEAD + [f"jours {x['id']}" for x in scen[1:]]]
    for r in charge_rows(found):
        rows.append([r["type"], r["id"], r["name"], r["phase"], r["component"], r["complexity"], r["profile"],
                     r["low"], r["likely"], r["high"], r["days"], r["days"] * per_day] + r["by_scenario"][1:])
    return [[num(v) if isinstance(v, (int, float)) else v for v in row] for row in rows]


def verify_charges(path: Path, found: dict) -> list[str]:
    """Relit le CSV des charges : chaque colonne de jours redonne la charge de son hypothèse."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    errors = []
    for item in found["scenarios"]:
        column = "jours" if item["id"] == "sans-ia" else f"jours {item['id']}"
        got = sum(float(r[column].replace(",", ".") or 0) for r in rows)
        if abs(got - item["build"]["days"]) > 0.2:
            errors.append(f"{path.name} : {item['id']}, total {round(got, 1)} j au lieu de {item['build']['days']}")
    return errors


SCENARIO_HEAD = ["hypothèse", "type", "id", "libellé", "phase", "profil", "facteur", "jours", "taux",
                 "coût réalisation", "par an"]


def scenario_rows(found: dict) -> list[list]:
    rows = [SCENARIO_HEAD]
    for item in found["scenarios"]:
        rows += [[item["id"], r["type"], r["id"], r["name"], r["phase"], r["profile"], r["factor"], r["days"],
                  r["rate"], r["cost"], r["annual"]] for r in item["rows"]]
    return [[num(v) if isinstance(v, (int, float)) else v for v in row] for row in rows]


def verify_scenarios(path: Path, found: dict, spec: dict) -> list[str]:
    """Relit le CSV des hypothèses : chaque hypothèse redonne sa réalisation et son run."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    errors = []
    for item in found["scenarios"]:
        mine = [r for r in rows if r["hypothèse"] == item["id"]]
        contingency = item["scenario"].get("contingency", spec.get("contingency", 0)) / 100
        build = sum(float(r["coût réalisation"].replace(",", ".") or 0) for r in mine) * (1 + contingency)
        annual = sum(float(r["par an"].replace(",", ".") or 0) for r in mine)
        for label, got, want in (("réalisation", build, item["build"]["cost"]), ("run", annual, item["run"]["annual"])):
            if abs(got - want) > 1:
                errors.append(f"{path.name} : {item['id']}, total {label} {round(got)} au lieu de {want}")
    return errors


def verify_csv(path: Path, totals: dict, contingency: float) -> list[str]:
    """Relit le CSV écrit et vérifie que ses montants redonnent les totaux du rapport."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    def total(column: str) -> float:
        return sum(float(r[column].replace(",", ".") or 0) for r in rows)

    build, annual, once = total("coût réalisation") * (1 + contingency), total("par an"), total("ponctuel")
    expected = (totals["build"]["cost"], totals["infra"]["annual"] + totals["run"]["annual"],
                totals["infra"]["one_time"])
    labels = ("réalisation", "par an", "ponctuel")
    return [f"{path.name} : total {label} {round(got)} au lieu de {want}"
            for label, got, want in zip(labels, (build, annual, once), expected) if abs(got - want) > 1]


def write_vault(vault: Path, folder: str, spec: dict, option: dict, found: dict, md: Path,
                errors: list[str]) -> dict | None:
    """Notes typées du chiffrage : chiffrage (évalue l'option), un lot par tâche (porte sur ses exigences)."""
    notes = vault_ontology.Notes(vault, "solution-estimate")
    base = vault_ontology.safe_folder(folder)
    title = vault_ontology.safe_name(spec["title"], "chiffrage")
    rel = f"{base}/Chiffrages/{title}"
    totals, currency = found["totals"], spec.get("currency", "€")
    option_rel = f"{base}/Options/Option {option['id']}"
    lots: dict[str, dict] = {}
    for line in found["lines"]:
        if line["type"] == "lot":
            lot = lots.setdefault(line["id"], {**line, "days": 0.0})
            lot["days"] += line["days"]
    up = f"Chiffrage : [[{rel}|{title}]]"
    v = vault_ontology
    onto = notes.onto

    def days(value) -> str:
        return v.count(round(value, 1), "jour")

    def cost(value) -> str:
        return f"{v.number(round(value))} {currency}"
    for lot in lots.values():
        exigences = [(f"{base}/Exigences/{r}", r) for r in lot["refs"]]
        body = [f"# {lot['id']} {lot['name']}", "", up, "",
                f"Charge : **{days(lot['days'])}** (espérance), phase {v.label(onto, lot['phase'])}, "
                f"complexité {v.label(onto, lot['complexity'])}."]
        if lot["refs"]:
            body += ["", "## Exigences", ""] + [
                f"- {v.link(f'{base}/Exigences/{r}', notes.title(f'{base}/Exigences/{r}', r))}"
                if notes.exists(f"{base}/Exigences/{r}") else f"- {r}" for r in lot["refs"]]
        notes.add(f"{base}/Lots/{title}/{v.safe_name(lot['id'])}", "lot",
                  {"id": lot["id"], "charge": round(lot["days"], 1), "phase": lot["phase"],
                   "composant": lot["component"] or None, "complexite": lot["complexity"]},
                  {"porte-sur": exigences or [(option_rel, f"Option {option['id']}")], "issu-de": (rel, title)}, body)
    priced = spec.get("rates") is not None
    budget = "non-fixe" if not totals["budget"] else ("depasse" if totals["budget"]["over"] else "respecte")
    host = (totals["hosting"] or {}).get("provider")
    years = v.count(totals["tco"]["years"], "an")
    body = [f"# Chiffrage : {spec['title']}", ""]
    if priced:
        head = f"Coût total sur {years} : {cost(totals['tco']['total'])}"
        lines = [f"Réalisation {cost(totals['build']['cost'])} ({cost(totals['build']['cost_low'])} à "
                 f"{cost(totals['build']['cost_high'])}), {days(totals['build']['days'])}."]
        if budget != "non-fixe":
            lines.append(f"Budget {v.label(onto, budget)}.")
        body += v.callout("warning" if budget == "depasse" else "abstract", head, lines)
    else:
        body += v.callout("abstract", f"Charge de réalisation : {days(totals['build']['days'])}", [
            f"De {v.number(totals['build']['days_low'])} à {days(totals['build']['days_high'])}, "
            "sans taux journalier."])
    detail = notes.attach(f"{base}/Rapports/{title}/{md.name}", md) if md.is_file() else f"`{md.name}`"
    body += [f"Chiffrage complet : {detail}.", "", "## Lots", ""]
    body += [f"- {v.link(f'{base}/Lots/{title}/{v.safe_name(i)}', i + ' ' + lots[i]['name'])} : "
             f"{days(lots[i]['days'])}" for i in lots]
    body += ["", "## Hypothèses de production", ""] + [
        f"- {s['name']} : {cost(s['tco']['total'])} sur {years}, réalisation {cost(s['build']['cost'])}, "
        f"{days(s['build']['days'])}" if priced
        else f"- {s['name']} : {days(s['build']['days'])} ({v.number(s['build']['days_low'])} à "
             f"{v.number(s['build']['days_high'])})"
        for s in found["scenarios"]]
    if spec.get("assumptions"):
        body += ["", "## Hypothèses", ""] + [f"- {a}" for a in spec["assumptions"]]
    props = {"charge": totals["build"]["days"], "hebergeur": host}
    if priced:
        props.update({"total": totals["tco"]["total"], "devise": currency, "horizon": totals["tco"]["years"],
                      "budget": budget})
    notes.add(rel, "chiffrage", props, {"evalue": [(option_rel, f"Option {option['id']}")]}, body)
    result = notes.write(errors, cleanup=(f"{base}/Lots/{title}",))
    return {**result, "folder": base} if result else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description chiffrage.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--vault", type=Path, help="vault Obsidian où écrire le chiffrage (notes typées)")
    parser.add_argument("--folder", help="dossier des notes dans le vault, celui du workflow (Workflows/<titre>)")
    parser.add_argument("--draft", action="store_true",
                        help="écrire le brouillon de la description (lots, transverses, budget), charges à estimer")
    parser.add_argument("--option", help="avec --draft : option à chiffrer (défaut : décision, sinon recommandation)")
    parser.add_argument("--infra", type=Path, help="avec --draft : lignes d'infrastructure de cost_build.py --infra")
    parser.add_argument("--lots", type=Path, action="append", default=[],
                        help="avec --draft : lots d'un expert (ui_breakdown.py, api_breakdown.py), répétable")
    parser.add_argument("--frontend", type=Path, help="avec --draft : comme --lots, lots de ui_breakdown.py")
    parser.add_argument("--abaques", type=Path, help="abaques propres (seuils des points à challenger), après ceux "
                                                     "de l'utilisateur et de la mission")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    # Postes attendus : règles livrées, de l'utilisateur et de la mission.
    rules, _, invalid = workspace.rules("chiffrage", EXPECTED, [args.spec])
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    if args.draft:
        report = draft(args.spec, args.option, args.infra, rules, args.lots + ([args.frontend] if args.frontend else []))
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    # Dans une mission (mission.json au-dessus de la description) : son vault et le dossier du workflow par défaut.
    args.vault, args.folder, scoped = workspace.vault_target(args.vault, args.folder, [args.spec])
    if scoped:
        print(json.dumps({"input": str(args.spec), "errors": scoped, "warnings": []}, ensure_ascii=False))
        return 1
    if bool(args.vault) != bool(args.folder):
        parser.error("--vault et --folder vont ensemble")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    invalid = validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    base = args.spec.parent
    # Abaques donnés avant le lancement (utilisateur, mission, --abaques) : seuils des points à challenger.
    abaques, sources, invalid = workspace.abaques([args.spec], args.abaques)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    reuse = apply_reuse(spec, errors)
    arch = load_json(base, spec.get("architecture", "options.json"), "architecture",
                     "architecture-options", "options_build.py", errors, warnings)
    cat = load_json(base, spec.get("requirements", "exigences.json"), "requirements",
                    "requirements-catalog", "req_build.py", errors, warnings)
    catalog = {r["id"]: r for r in (cat or {}).get("requirements", []) if isinstance(r, dict) and "id" in r}
    option, status = pick_option(spec, arch, errors, warnings) if arch else (None, "")
    providers, checked = load_providers(base, spec, errors, warnings)
    found = analyse(spec, catalog, option, providers, checked, errors, warnings, rules) if option else None
    if found and not errors:
        found["reuse"] = reuse
        found["challenge"] = challenge(spec, found, catalog, abaques.get("challenge", {}), reuse, sources, warnings)
    if args.vault and not args.vault.is_dir():
        errors.append(f"--vault : dossier introuvable {args.vault}")
    report = {"input": str(args.spec), "outputs": [], "option": option["id"] if option else None,
              "currency": spec.get("currency", "€"), "vault": None, "errors": errors, "warnings": warnings}
    if errors or not found:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    priced = spec.get("rates") is not None
    report["mode"] = "chiffrage" if priced else "charges"
    if priced:
        report.update({k: found["totals"][k] for k in ("build", "infra", "run", "operate", "tco", "budget", "hosting")})
        report["scenarios"] = [{k: v for k, v in s.items() if k not in ("rows", "scenario")} for s in found["scenarios"]]
    else:
        del report["currency"]
    report.update({"lots": sum(1 for x in found["lines"] if x["type"] == "lot"), "charges": found["charges"],
                   "unestimated": found["unestimated"], "uncovered": found["uncovered"],
                   "uncertain": found["uncertain"], "missing": found["missing"],
                   "reuse": {k: v for k, v in reuse.items() if k != "items"},
                   "challenge": {k: v for k, v in found["challenge"].items() if k not in ("limits", "abaques")},
                   "abaques": sources})
    report["analogy"] = analogy(args.spec, spec, errors, warnings)

    out_dir = args.out_dir or base
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md, table, hypo = out_dir / f"{stem}.md", out_dir / f"{stem}.csv", out_dir / f"{stem}.hypotheses.csv"
    charge_md, charge_table = out_dir / f"{stem}.charges.md", out_dir / f"{stem}.charges.csv"
    if priced:
        with open(md, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(render_md(spec, option, status, found, providers))
        with open(table, "w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle, delimiter=";").writerows(csv_rows(found))
        with open(hypo, "w", encoding="utf-8-sig", newline="") as handle:
            csv.writer(handle, delimiter=";").writerows(scenario_rows(found))
        errors += verify_csv(table, found["totals"], spec.get("contingency", 0) / 100)
        errors += verify_scenarios(hypo, found, spec)
        report["outputs"] = [str(md), str(table), str(hypo)]
    with open(charge_md, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_charges(spec, option, status, found))
    with open(charge_table, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(charge_csv(found))
    errors += verify_charges(charge_table, found)
    report["outputs"] += [str(charge_md), str(charge_table)]
    if args.vault and not errors:
        report["vault"] = write_vault(args.vault, args.folder, spec, option, found,
                                      md if report["mode"] == "chiffrage" else charge_md, errors)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
