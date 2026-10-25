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
  l'option sans lot ni ligne d'infrastructure, les estimations très
  incertaines et les dépassements de budget ;
- écrit `chiffrage.md` (revue), `chiffrage.csv` (lignes détaillées) et
  `chiffrage.hypotheses.csv`, relit les CSV et vérifie que leurs montants
  redonnent les totaux.

L'option chiffrée est `option`, sinon la décision de options.json, sinon sa
recommandation. Les prix d'infrastructure sont des hypothèses saisies avec
leur base : aucun tarif n'est consulté en ligne.

    uv run scripts/estimate_build.py chiffrage.json [--out-dir DOSSIER] [--vault VAULT --folder DOSSIER_DU_VAULT] | --schema

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
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, input_schema, print_schema, validate  # noqa: E402
import vault_ontology  # noqa: E402

Z90 = 1.2816  # quantile 90 % de la loi normale : fourchette P10-P90
PHASES = {"cadrage": "Cadrage", "conception": "Conception", "realisation": "Réalisation",
          "integration": "Intégration", "tests": "Tests et recette", "deploiement": "Déploiement",
          "migration": "Reprise de données", "conduite-changement": "Conduite du changement",
          "pilotage": "Pilotage"}
PERIODS = {"mois": 12, "an": 1, "unique": 0}
UNCERTAIN = 1.0  # (maxi - mini) / probable au-delà : estimation à découper ou hypothèse à lever
# Catalogue commun des hébergeurs (shared/providers.json, copié par scripts/build.py).
PROVIDERS = Path(__file__).resolve().parent / "lib" / "providers.json"
# Hypothèses de production par défaut : sans IA (charges saisies), avec IA, dev IA natif.
SCENARIOS = Path(__file__).resolve().parent.parent / "references" / "hypotheses-ia.json"
STALE_DAYS = 180  # catalogue des hébergeurs plus ancien : qualifications à revérifier
QUALIFIED_KINDS = ("cloud", "service")  # lignes soumises aux qualifications exigées


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def money(value: float, currency: str) -> str:
    return f"{value:,.0f}".replace(",", " ") + f" {currency}"


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


def three_points(value) -> tuple[float, float, float, float, float]:
    """(mini, probable, maxi, espérance, écart type) d'une charge en jours."""
    if isinstance(value, list):
        low, likely, high = value
        return low, likely, high, (low + 4 * likely + high) / 6, (high - low) / 6
    return value, value, value, float(value), 0.0


def analyse(spec: dict, catalog: dict, option: dict, providers: dict, checked: str | None,
            errors: list[str], warnings: list[str]) -> dict:
    """Contrôles croisés et calculs ; les montants ne sont valables que sans erreur."""
    rates = spec["rates"]
    if not rates:
        errors.append("rates : au moins un profil attendu")
    comps = {c["id"]: c for c in option["components"]}
    ids: dict[str, str] = {}

    def unique(item_id: str, where: str) -> None:
        if item_id in ids:
            errors.append(f"{where} : identifiant « {item_id} » déjà pris ({ids[item_id]})")
        ids[item_id] = where

    def profile(name: str, where: str) -> float:
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
            errors.append(f"{where}/effort : au moins un profil attendu")
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
                          "refs": task.get("refs", []), "sd": sd, "ai": task.get("ai", {})})

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
    if option.get("provider") and not any(i["kind"] == "cloud" for i in infra):
        warnings.append(f"option {option['id']} hébergée chez {option['provider']} sans ligne d'infrastructure cloud")
    if not spec.get("assumptions"):
        warnings.append("aucune hypothèse notée (assumptions)")

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
             "uncovered": uncovered, "uncertain": uncertain}
    found["scenarios"] = scenarios(spec, found, profile, errors, warnings)
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
    for lot in lots.values():
        exigences = [(f"{base}/Exigences/{r}", r) for r in lot["refs"]]
        notes.add(f"{base}/Lots/{title}/{vault_ontology.safe_name(lot['id'])}", "lot",
                  {"id": lot["id"], "charge": round(lot["days"], 1), "phase": lot["phase"],
                   "composant": lot["component"] or None},
                  {"porte-sur": exigences or [(option_rel, f"Option {option['id']}")], "issu-de": (rel, title)},
                  [f"# {lot['id']} {lot['name']}", "", up, "", f"Charge : {round(lot['days'], 1)} jours (espérance)."])
    budget = "non-fixe" if not totals["budget"] else ("depasse" if totals["budget"]["over"] else "respecte")
    host = totals["hosting"]["provider"]
    body = [f"# Chiffrage : {spec['title']}", "",
            f"Coût total sur {totals['tco']['years']} an(s) : **{totals['tco']['total']} {currency}** ; "
            f"réalisation {totals['build']['cost']} {currency} ({totals['build']['cost_low']} à "
            f"{totals['build']['cost_high']}), {totals['build']['days']} jours.", "",
            f"Chiffrage complet : `{md.name}`.", "", "## Lots", ""]
    body += [f"- [[{base}/Lots/{title}/{vault_ontology.safe_name(i)}|{i}]] {lots[i]['name']}" for i in lots]
    body += ["", "## Hypothèses de production", ""] + [
        f"- {s['name']} : {s['tco']['total']} {currency} sur {totals['tco']['years']} an(s), réalisation "
        f"{s['build']['cost']} {currency}" for s in found["scenarios"]]
    if spec.get("assumptions"):
        body += ["", "## Hypothèses", ""] + [f"- {a}" for a in spec["assumptions"]]
    notes.add(rel, "chiffrage", {"total": totals["tco"]["total"], "devise": currency,
                                 "horizon": totals["tco"]["years"], "charge": totals["build"]["days"],
                                 "budget": budget, "hebergeur": host},
              {"evalue": [(option_rel, f"Option {option['id']}")]}, body)
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
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
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
    arch = load_json(base, spec.get("architecture", "options.json"), "architecture",
                     "architecture-options", "options_build.py", errors, warnings)
    cat = load_json(base, spec.get("requirements", "exigences.json"), "requirements",
                    "requirements-catalog", "req_build.py", errors, warnings)
    catalog = {r["id"]: r for r in (cat or {}).get("requirements", []) if isinstance(r, dict) and "id" in r}
    option, status = pick_option(spec, arch, errors, warnings) if arch else (None, "")
    providers, checked = load_providers(base, spec, errors, warnings)
    found = analyse(spec, catalog, option, providers, checked, errors, warnings) if option else None
    if args.vault and not args.vault.is_dir():
        errors.append(f"--vault : dossier introuvable {args.vault}")
    report = {"input": str(args.spec), "outputs": [], "option": option["id"] if option else None,
              "currency": spec.get("currency", "€"), "vault": None, "errors": errors, "warnings": warnings}
    if errors or not found:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report.update({k: found["totals"][k] for k in ("build", "infra", "run", "operate", "tco", "budget", "hosting")})
    report["scenarios"] = [{k: v for k, v in s.items() if k not in ("rows", "scenario")} for s in found["scenarios"]]
    report.update({"lots": sum(1 for x in found["lines"] if x["type"] == "lot"),
                   "unestimated": found["unestimated"], "uncovered": found["uncovered"],
                   "uncertain": found["uncertain"]})

    out_dir = args.out_dir or base
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md, table, hypo = out_dir / f"{stem}.md", out_dir / f"{stem}.csv", out_dir / f"{stem}.hypotheses.csv"
    with open(md, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_md(spec, option, status, found, providers))
    with open(table, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(csv_rows(found))
    with open(hypo, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(scenario_rows(found))
    errors += verify_csv(table, found["totals"], spec.get("contingency", 0) / 100)
    errors += verify_scenarios(hypo, found, spec)
    report["outputs"] = [str(md), str(table), str(hypo)]
    if args.vault and not errors:
        report["vault"] = write_vault(args.vault, args.folder, spec, option, found, md, errors)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
