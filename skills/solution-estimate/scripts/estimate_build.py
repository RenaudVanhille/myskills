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
import json
import math
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, require_file, require_module, schema_of  # noqa: E402
from spec_schema import check, input_schema, print_schema, read_spec, schema_option, validate  # noqa: E402
from estimate_checks import (  # noqa: E402
    applies,
    apply_reuse,
    challenge,
    charges,
    check_hosting,
    forgotten,
    phase_shares,
    three_points,
)
from estimate_common import BUILD_PHASES, PHASES, days, hint, plain  # noqa: E402
from estimate_render import (  # noqa: E402
    charge_csv,
    csv_rows,
    render_charges,
    render_md,
    scenario_rows,
    verify_charges,
    verify_csv,
    verify_scenarios,
    years,
)

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")
workspace = require_module("mission-workspace", "lib/workspace.py")

Z90 = 1.2816  # quantile 90 % de la loi normale : fourchette P10-P90
PERIODS = {"mois": 12, "an": 1, "unique": 0}
UNCERTAIN = 1.0  # (maxi - mini) / probable au-delà : estimation à découper ou hypothèse à lever
# Catalogue commun des hébergeurs (shared/providers.json), copie unique dans cloud-architecture.
PROVIDERS = require_file("cloud-architecture", "lib/providers.json")
# Hypothèses de production par défaut : sans IA (charges saisies), avec IA, dev IA natif.
SCENARIOS = Path(__file__).resolve().parent.parent / "references" / "hypotheses-ia.json"
STALE_DAYS = 180  # catalogue des hébergeurs plus ancien : qualifications à revérifier


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


DEFAULTS = {"pilotage": 12, "contingency": 10, "run": 15}
# Lot de cadrage du brouillon : % des jours de réalisation et d'intégration [mini, probable, maxi], à calibrer.
CADRAGE = {"name": "Cadrage et architecture détaillée", "phase": "cadrage", "ratio": [8, 10, 15],
           "profile": "architecte"}
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
    # Un poste déjà couvert par un lot d'expert (plan de recette, tests de charge...) n'est pas ajouté une 2e fois.
    names = " ".join(plain(w["name"]) for w in work)
    transverse = [CADRAGE] + [rule["draft"] for rule in rules
                              if rule.get("draft") and applies(rule, catalog, option, bool(lines))
                              and not (rule.get("pattern") and re.search(rule["pattern"], names))]
    # Réalisation et intégration toutes chiffrées (lots des experts) : les lots transverses à ratio en
    # reçoivent une charge de départ, que l'agent relit au lieu de l'estimer.
    build = [w for w in work if w["phase"] in BUILD_PHASES]
    base_days = sum(three_points(v)[3] for w in build for v in w["effort"].values()) \
        if build and all(w["effort"] for w in build) else 0
    prefilled = 0
    for lot in transverse:
        task = {"id": "", "name": lot["name"], "phase": lot["phase"], "effort": {}}
        if base_days and lot.get("ratio") and lot.get("profile"):
            task["effort"] = {lot["profile"]: [round(base_days * r / 100 * 2) / 2 for r in lot["ratio"]]}
            task["note"] = (f"Ratio de {'-'.join(str(r) for r in lot['ratio'])} % des {days(base_days)} jours de "
                            "réalisation et d'intégration, espérance avant réemploi (valeur par défaut, à calibrer)")
            prefilled += 1
        work.append(task)
    if prefilled:
        warnings.append(f"{prefilled} lots transverses chiffrés par ratio des {days(base_days)} jours de réalisation "
                        "et d'intégration (note de chaque lot), à relire")
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


class _Refs:
    """Références croisées d'un chiffrage : identifiants uniques, profils, composants et exigences connus."""

    def __init__(self, spec: dict, catalog: dict, option: dict, errors: list[str]):
        self.rates = spec.get("rates")  # sans taux : mode charges, jours et heures seulement
        self.catalog, self.option, self.errors = catalog, option, errors
        self.comps = {c["id"]: c for c in option["components"]}
        self.ids: dict[str, str] = {}

    def unique(self, item_id: str, where: str) -> None:
        if item_id in self.ids:
            self.errors.append(f"{where} : identifiant « {item_id} » déjà pris ({self.ids[item_id]})")
        self.ids[item_id] = where

    def profile(self, name: str, where: str) -> float:
        if self.rates is None:
            return 0.0
        if name not in self.rates:
            self.errors.append(f"{where} : profil inconnu « {name} »{hint(name, self.rates)}")
            return 0.0
        return self.rates[name]

    def component(self, name: str | None, where: str) -> None:
        if name and name not in self.comps:
            self.errors.append(f"{where} : composant inconnu « {name} » dans l'option {self.option['id']}"
                               f"{hint(name, self.comps)}")

    def refs(self, values, where: str) -> None:
        for ref in values:
            if self.catalog and ref not in self.catalog:
                self.errors.append(f"{where} : exigence inconnue {ref}")
            elif self.catalog.get(ref, {}).get("status") == "retiree":
                self.errors.append(f"{where} : {ref} est retirée du catalogue")


def work_lines(spec: dict, known: _Refs) -> tuple[list[dict], list[str], dict]:
    """Une ligne par lot et par profil, les lots très incertains, et les sommes (jours, coût, variances)."""
    lines, uncertain = [], []
    sums = {"days": 0.0, "var": 0.0, "cost": 0.0, "cost_var": 0.0}
    for index, task in enumerate(spec["work"]):
        where = f"work/{index} ({task['id']})"
        known.unique(task["id"], where)
        known.component(task.get("component"), where)
        known.refs(task.get("refs", []), f"{where}/refs")
        if not task["effort"]:
            known.errors.append(f"{where}/effort : charge à estimer, en jours par profil (au moins un)")
        for name, value in task["effort"].items():
            rate = known.profile(name, f"{where}/effort/{name}")
            low, likely, high, expected, sd = three_points(value)
            if not low <= likely <= high:
                known.errors.append(f"{where}/effort/{name} : [mini, probable, maxi] attendu dans l'ordre croissant, "
                                    f"reçu {value}")
                continue
            if likely and (high - low) / likely > UNCERTAIN and task["id"] not in uncertain:
                uncertain.append(task["id"])
            sums["days"] += expected
            sums["var"] += sd ** 2
            sums["cost"] += expected * rate
            sums["cost_var"] += (sd * rate) ** 2
            lines.append({"type": "lot", "id": task["id"], "name": task["name"], "phase": task["phase"],
                          "component": task.get("component", ""), "profile": name, "low": low, "likely": likely,
                          "high": high, "days": expected, "rate": rate, "cost": expected * rate,
                          "refs": task.get("refs", []), "sd": sd, "ai": task.get("ai", {}),
                          "complexity": task.get("complexity")})
    return lines, uncertain, sums


def overhead_lines(spec: dict, known: _Refs, work_days: float) -> tuple[list[dict], float, float]:
    """Lignes de pilotage, en pourcentage des jours des lots ; leurs jours et leur coût."""
    lines, days, cost = [], 0.0, 0.0
    for index, item in enumerate(spec.get("overheads", [])):
        where = f"overheads/{index} ({item['id']})"
        known.unique(item["id"], where)
        rate = known.profile(item["profile"], f"{where}/profile")
        amount = work_days * item["percent"] / 100
        days += amount
        cost += amount * rate
        lines.append({"type": "pilotage", "id": item["id"], "name": item["name"], "phase": "pilotage",
                      "component": "", "profile": item["profile"], "low": "", "likely": "", "high": "",
                      "days": amount, "rate": rate, "cost": amount * rate, "refs": [],
                      "percent": item["percent"]})
    return lines, days, cost


def infra_lines(spec: dict, known: _Refs) -> list[dict]:
    infra = []
    for index, item in enumerate(spec.get("infra", [])):
        where = f"infra/{index} ({item['id']})"
        known.unique(item["id"], where)
        known.component(item.get("component"), where)
        amount = item.get("quantity", 1) * item["unit_cost"]
        infra.append({**item, "annual": amount * PERIODS[item["period"]],
                      "one_time": amount if item["period"] == "unique" else 0.0})
    return infra


def build_totals(spec: dict, sums: dict, over_days: float, over_cost: float) -> dict:
    """Réalisation : jours et coût attendus, fourchette à 90 % et provision."""
    work_days, work_cost = sums["days"], sums["cost"]
    contingency = spec.get("contingency", 0) / 100
    sd_days, sd_cost = math.sqrt(sums["var"]), math.sqrt(sums["cost_var"])
    f_days = over_days / work_days if work_days else 0.0
    f_cost = over_cost / work_cost if work_cost else 0.0
    base_cost = work_cost + over_cost
    return {"days": round(work_days + over_days, 1),
            "days_low": round(max(work_days - Z90 * sd_days, 0) * (1 + f_days), 1),
            "days_high": round((work_days + Z90 * sd_days) * (1 + f_days), 1),
            "cost": round(base_cost * (1 + contingency)),
            "cost_low": round(max(work_cost - Z90 * sd_cost, 0) * (1 + f_cost) * (1 + contingency)),
            "cost_high": round((work_cost + Z90 * sd_cost) * (1 + f_cost) * (1 + contingency)),
            "contingency": round(base_cost * contingency)}


def run_lines(spec: dict, known: _Refs, base_cost: float) -> list[dict]:
    """Lignes de fonctionnement : jours par an d'un profil, ou pourcentage du coût de réalisation."""
    run = []
    for index, item in enumerate(spec.get("run", [])):
        where = f"run/{index} ({item['id']})"
        known.unique(item["id"], where)
        if ("days_per_year" in item) == ("percent_of_build" in item):
            known.errors.append(f"{where} : donnez soit days_per_year (avec profile), soit percent_of_build")
            continue
        if "days_per_year" in item:
            if "profile" not in item:
                known.errors.append(f"{where} : champ « profile » manquant avec days_per_year")
                continue
            rate = known.profile(item["profile"], f"{where}/profile")
            run.append({**item, "rate": rate, "annual": item["days_per_year"] * rate})
        else:
            run.append({**item, "annual": base_cost * item["percent_of_build"] / 100})
    return run


def coverage(spec: dict, known: _Refs, infra: list[dict], uncertain: list[str], rules: list[dict],
             warnings: list[str]) -> tuple[list[str], list[str], list[str], list[dict]]:
    """Exigences sans lot, composants sans ligne, lots incertains et postes oubliés, chacun signalé."""
    catalog, option, comps, errors = known.catalog, known.option, known.comps, known.errors
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
    if known.rates is not None and option.get("provider") and not any(i["kind"] == "cloud" for i in infra):
        warnings.append(f"option {option['id']} hébergée chez {option['provider']} sans ligne d'infrastructure cloud")
    if not spec.get("assumptions"):
        warnings.append("aucune hypothèse notée (assumptions)")
    missing = [] if errors else forgotten(spec, catalog, option, rules)
    if missing:
        warnings.append(f"poste(s) souvent oublié(s), absent(s) : {'; '.join(r['label'] for r in missing)} ; "
                        "ajouter un lot ou une ligne, ou le noter dans assumptions ou exclusions")
    return unestimated, uncovered, uncertain, missing


def budget_check(spec: dict, known: _Refs, totals: dict, warnings: list[str]) -> dict | None:
    """Plafonds du budget dépassés (réalisation, fonctionnement, coût total), signalés avec leur exigence."""
    budget = spec.get("budget")
    if not budget:
        return None
    over, horizon = [], totals["tco"]["years"]
    known.refs(budget.get("refs", []), "budget/refs")
    for key, label, value in (("build", "réalisation", totals["build"]["cost"]),
                              ("monthly", "fonctionnement par mois", totals["operate"]["monthly"]),
                              ("tco", f"coût total sur {years(horizon)}", totals["tco"]["total"])):
        if key in budget and value > budget[key]:
            over.append(key)
            warnings.append(f"budget dépassé, {label} : {value} pour {budget[key]} "
                            f"({', '.join(budget.get('refs', [])) or 'sans exigence citée'})")
    return {"over": over}


def analyse(spec: dict, catalog: dict, option: dict, providers: dict, checked: str | None,
            errors: list[str], warnings: list[str], rules: list[dict]) -> dict:
    """Contrôles croisés et calculs ; les montants ne sont valables que sans erreur."""
    known = _Refs(spec, catalog, option, errors)
    if known.rates is not None and not known.rates:
        errors.append("rates : au moins un profil attendu, ou pas de champ rates pour les charges seules")
    lines, uncertain, sums = work_lines(spec, known)
    overheads, over_days, over_cost = overhead_lines(spec, known, sums["days"])
    lines += overheads
    infra = infra_lines(spec, known)
    hosting = check_hosting(spec, option, infra, providers, checked, errors, warnings)
    known.refs(spec.get("hosting", {}).get("refs", []), "hosting/refs")
    build = build_totals(spec, sums, over_days, over_cost)
    run = run_lines(spec, known, sums["cost"] + over_cost)

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
    unestimated, uncovered, uncertain, missing = coverage(spec, known, infra, uncertain, rules, warnings)
    totals["budget"] = budget_check(spec, known, totals, warnings)
    totals["hosting"] = hosting
    found = {"lines": lines, "infra": infra, "run": run, "totals": totals, "unestimated": unestimated,
             "uncovered": uncovered, "uncertain": uncertain, "missing": [r["id"] for r in missing]}
    found["scenarios"] = scenarios(spec, found, known.profile, errors, warnings)
    if known.rates is None and spec.get("infra"):
        warnings.append("infra ignorée : sans rates, seules les charges (jours, heures) sont produites")
    found["charges"] = charges(spec, found, warnings)
    return found


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


def write_vault(vault: Path, folder: str, spec: dict, option: dict, found: dict, md: Path,
                errors: list[str], warnings: list[str] | None = None) -> dict | None:
    """Notes typées du chiffrage : chiffrage (évalue l'option), un lot par tâche (porte sur ses exigences)."""
    notes = vault_ontology.Notes(vault, "solution-estimate")
    base = vault_ontology.safe_folder(folder)
    title = vault_ontology.safe_name(spec["title"], "chiffrage")
    rel = f"{base}/Chiffrages/{title}"
    lots_dir, cleanup = vault_ontology.folders_of(base, "Lots", title)
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
        notes.add(f"{lots_dir}/{v.safe_name(lot['id'])}", "lot",
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
    detail = notes.attach(f"{base}/Rapports/{v.folder_key(title)}/{md.name}", md) if md.is_file() else f"`{md.name}`"
    body += [f"Chiffrage complet : {detail}.", "", "## Lots", ""]
    body += [f"- {v.link(f'{lots_dir}/{v.safe_name(i)}', i + ' ' + lots[i]['name'])} : "
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
    result = notes.write(errors, cleanup=cleanup, warnings=warnings)
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
    schema_option(parser)
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
    scoped = workspace.vault_args(parser, args, [args.spec])
    if scoped:
        print(json.dumps({"input": str(args.spec), "errors": scoped, "warnings": []}, ensure_ascii=False))
        return 1
    spec, invalid = read_spec(args.spec, __file__)
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
                                      md if report["mode"] == "chiffrage" else charge_md, errors, report["warnings"])
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
