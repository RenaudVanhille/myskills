"""Contrôles du chiffrage : postes oubliés, réemploi, points à challenger, hébergement, plan de charge (estimate_build.py)."""
from __future__ import annotations

import difflib
import re
from estimate_common import BUILD_PHASES, CHALLENGE, COMPLEXITY, QUALIFIED_KINDS, SIZES, days, hint, pct, plain


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


def phase_shares(spec: dict) -> dict[str, float]:
    """Part de chaque phase dans la charge espérée des lots (0 à 1)."""
    days: dict[str, float] = {}
    for task in spec.get("work", []):
        for value in task.get("effort", {}).values():
            days[task["phase"]] = days.get(task["phase"], 0.0) + three_points(value)[3]
    total = sum(days.values())
    return {k: v / total for k, v in days.items()} if total else {}


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
