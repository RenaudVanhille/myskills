"""Coût IA du développement : jetons consommés par les agents et assistants, en fourchette avec un taux de confiance.

Le volume de jetons d'un lot = jours de l'équipe dans l'hypothèse (avec IA, dev IA natif) x jetons par jour
x poids de la phase x poids de la complexité. Le coût = jetons x prix moyen du million de jetons, pondéré par
la part de chaque niveau de travail (simple, moyen, complexe : un modèle par niveau) et par le mélange
entrée, cache, sortie. Les tarifs sont ceux de references/jetons-ia.json (versionné, daté), jamais lus en
ligne. La fourchette P10-P90 vient d'une simulation à graine fixe (résultat reproductible) : charge de chaque
lot (estimation à trois points), gain de l'hypothèse (commun aux lots) et jetons par jour (communs aux lots).

Utilisé par estimate_build.py (chiffrage) et, par skill_paths.load_module, par spec-pack (livraison.md).
"""
from __future__ import annotations

import json
import math
import random
from datetime import date
from pathlib import Path

LEVELS = ("simple", "moyen", "complexe")
KINDS = ("input", "cache_write", "cache_read", "output")
DRAWS = 2000
SEED = 20261116
STALE_DAYS = 180  # tarifs plus anciens : à revérifier
SIZES = ((5, "faible"), (15, "moyenne"), (40, "elevee"))
CONFIDENCE = {"faible": "grille par défaut, non étalonnée", "moyenne": "valeurs du projet avec leur base",
              "bonne": "jetons par jour mesurés sur un lot pilote"}

# Résumé écrit dans <nom>.ia.json et relu par spec-pack : sa forme est contrôlée ici, une seule fois.
SUMMARY_SCHEMA = {
    "type": "object", "additionalProperties": False,
    "required": ["title", "checked", "confidence", "interval", "currency", "scenarios", "basis"],
    "properties": {
        "title": {"type": "string"}, "checked": {"type": "string"}, "basis": {"type": "string"},
        "confidence": {"enum": list(CONFIDENCE)}, "interval": {"enum": [80]},
        "currency": {"type": ["string", "null"]},
        "scenarios": {"type": "array", "items": {
            "type": "object", "additionalProperties": False,
            "required": ["id", "name", "mtok", "usd", "cost", "usd_per_mtok", "lots"],
            "properties": {
                "id": {"type": "string"}, "name": {"type": "string"},
                "mtok": {"$ref": "#/$defs/range"}, "usd": {"$ref": "#/$defs/range"},
                "cost": {"anyOf": [{"$ref": "#/$defs/range"}, {"type": "null"}]},
                "usd_per_mtok": {"type": "number"},
                "budget_confidence": {"type": "number", "minimum": 0, "maximum": 100},
                "lots": {"type": "array", "items": {
                    "type": "object", "additionalProperties": False,
                    "required": ["id", "name", "days", "mtok", "usd"],
                    "properties": {"id": {"type": "string"}, "name": {"type": "string"}, "days": {"type": "number"},
                                   "mtok": {"$ref": "#/$defs/range"}, "usd": {"$ref": "#/$defs/range"}}}}}}}},
    "$defs": {"range": {"type": "array", "minItems": 3, "maxItems": 3, "items": {"type": "number", "minimum": 0},
                        "description": "P10, P50 (médiane), P90"}},
}


def load(spec: dict, path: Path, errors: list[str], warnings: list[str]) -> dict:
    """Grille par défaut (references/jetons-ia.json), remplacée champ à champ par ai_cost de la description."""
    try:
        grid = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"ai_cost : grille illisible {path.name} ({error})")
        return {}
    from spec_schema import check, input_schema
    schema = input_schema(Path(__file__).resolve().parent.parent / "estimate_build.py")
    invalid = check(grid, schema["$defs"]["ai_grid"], schema) if schema else []
    if invalid:
        errors.extend(f"ai_cost : {path.name} : {e}" for e in invalid[:10])
        return {}
    own = spec.get("ai_cost", {})
    merged = {k: ({**grid[k], **own[k]} if isinstance(grid.get(k), dict) and k in own else own.get(k, grid.get(k)))
              for k in set(grid) | set(own)}
    mine = sorted(k for k in own if k not in ("basis", "measured", "exchange_rate"))
    if mine and "basis" not in own:
        warnings.append("ai_cost : valeurs propres au projet sans base (basis) : mesure d'un lot pilote, rapport "
                        "d'usage de l'outil ou hypothèse à faire valider")
        merged["basis"] = "non donnée pour les valeurs du projet, à faire valider"
    # Fiabilité : les jetons par jour pèsent le plus ; mesurés sur un lot pilote, donnés par le projet ou par défaut.
    merged["confidence"] = ("bonne" if own.get("measured") and "tokens_per_day" in own
                            else "moyenne" if "tokens_per_day" in own else "faible")
    for name, share in merged["levels"].items():
        if abs(sum(share.values()) - 1) > 0.01:
            errors.append(f"ai_cost/levels/{name} : parts des niveaux de somme {sum(share.values()):.2f}, 1 attendu")
    for level, model in merged["models"].items():
        if model not in merged["prices"]:
            errors.append(f"ai_cost/models/{level} : modèle « {model} » sans tarif dans prices "
                          f"(connus : {', '.join(merged['prices'])})")
    if abs(sum(merged["mix"].get(k, 0) for k in KINDS) - 1) > 0.01:
        errors.append("ai_cost/mix : parts entrée, cache et sortie de somme différente de 1")
    try:
        age = (date.today() - date.fromisoformat(merged["checked"])).days
    except ValueError:
        age = STALE_DAYS + 1
    if age > STALE_DAYS:
        warnings.append(f"ai_cost : tarifs relevés le {merged['checked']}, il y a plus de {STALE_DAYS} jours : à "
                        "revérifier (prices, checked)")
    return merged


def usd_per_mtok(grid: dict, sid: str) -> float:
    """Prix moyen d'un million de jetons de l'hypothèse : niveaux x modèles x mélange entrée, cache, sortie."""
    total = 0.0
    for level, share in grid["levels"].get(sid, {}).items():
        price = grid["prices"][grid["models"][level]]
        total += share * sum(grid["mix"].get(k, 0) * price[k] for k in KINDS)
    return total


def _quantiles(values: list[float]) -> list[float]:
    ordered = sorted(values)
    pick = lambda q: ordered[min(len(ordered) - 1, int(q * len(ordered)))]  # noqa: E731
    return [pick(0.1), pick(0.5), pick(0.9)]


def _complexity(task: dict, expected: float) -> str:
    return task.get("complexity") or next((name for limit, name in SIZES if expected <= limit), "tres-elevee")


def estimate(spec: dict, lots: list[dict], defs: dict, grid: dict, rate: float | None,
             warnings: list[str]) -> dict:
    """Jetons et coût de chaque hypothèse avec IA, par lot et au total (P10, P50, P90).

    lots : lignes « lot » du chiffrage (une par lot et par profil : days, sd, phase, ai, complexity).
    defs : hypothèses de production fusionnées (factors, gain_uncertainty).
    rate : unités de la devise du chiffrage pour un dollar, ou None (coût en dollars seulement).
    """
    by_lot: dict[str, dict] = {}
    for line in lots:
        lot = by_lot.setdefault(line["id"], {"id": line["id"], "name": line["name"], "phase": line["phase"],
                                             "ai": line["ai"], "days": 0.0, "var": 0.0,
                                             "complexity": line.get("complexity")})
        lot["days"] += line["days"]
        lot["var"] += line["sd"] ** 2
    tasks = {t["id"]: t for t in spec["work"]}
    rng = random.Random(SEED)
    budget = (spec.get("budget") or {}).get("ai")
    result = []
    for sid, scen in defs.items():
        triangle = grid["tokens_per_day"].get(sid)
        if not triangle:
            continue
        low, mode, high = triangle
        price = usd_per_mtok(grid, sid)
        gain_sd = scen.get("gain_uncertainty", 0)
        items = []
        for lot in by_lot.values():
            factor = lot["ai"].get(sid, scen["factors"].get(lot["phase"], 1))
            weight = grid["phases"].get(lot["phase"], 1) * grid["complexity"][
                _complexity(tasks.get(lot["id"], {}), lot["days"])]
            items.append((lot, factor, weight, math.sqrt(lot["var"])))
        totals, per_lot = [], [[] for _ in items]
        for _ in range(DRAWS):
            per_day = rng.triangular(low, high, mode)
            gain = max(0.0, rng.gauss(1, gain_sd))
            total = 0.0
            for index, (lot, factor, weight, sd) in enumerate(items):
                days = max(0.0, rng.gauss(lot["days"], sd)) if sd else lot["days"]
                applied = min(3.0, max(0.05, 1 - (1 - factor) * gain))
                tokens = days * applied * weight * per_day
                per_lot[index].append(tokens)
                total += tokens
            totals.append(total)
        mtok = _quantiles(totals)
        usd = [round(v * price, 2) for v in mtok]
        entry = {"id": sid, "name": scen["name"], "mtok": [round(v, 1) for v in mtok], "usd": usd,
                 "cost": [round(v * rate, 2) for v in usd] if rate is not None else None,
                 "usd_per_mtok": round(price, 4),
                 "lots": [{"id": lot["id"], "name": lot["name"], "days": round(lot["days"] * factor, 1),
                           "mtok": [round(v, 2) for v in q], "usd": [round(v * price, 2) for v in q]}
                          for (lot, factor, _, _), q in ((item, _quantiles(v)) for item, v in zip(items, per_lot))]}
        if budget is not None and rate is not None:
            entry["budget_confidence"] = round(100 * sum(t * price * rate <= budget for t in totals) / DRAWS, 1)
            if entry["budget_confidence"] < 50:
                warnings.append(f"budget/ai : {scen['name']}, coût IA médian {usd[1] * rate:.0f} au-delà du budget "
                                f"IA {budget:.0f} (confiance de le tenir : {entry['budget_confidence']:.0f} %)")
        result.append(entry)
    return {"title": spec.get("title") or "Chiffrage", "checked": grid["checked"], "confidence": grid["confidence"],
            "interval": 80, "currency": spec.get("currency", "€") if rate is not None else None,
            "basis": grid["basis"], "scenarios": result}


def exchange_rate(spec: dict, grid: dict, warnings: list[str]) -> float | None:
    """Unités de la devise du chiffrage pour un dollar : ai_cost.exchange_rate, sinon la grille."""
    currency = spec.get("currency", "€")
    rate = spec.get("ai_cost", {}).get("exchange_rate", grid.get("exchange_rates", {}).get(currency))
    if rate is None:
        warnings.append(f"ai_cost : devise « {currency} » sans taux de change (ai_cost.exchange_rate) : coût IA en "
                        "dollars seulement, hors coût total")
    return rate


def _mtok(value: float) -> str:
    return (f"{value:,.1f}" if value < 100 else f"{value:,.0f}").replace(",", " ").replace(".", ",").removesuffix(",0")


def _money(value: float, unit: str) -> str:
    return f"{value:,.0f}".replace(",", " ") + f" {unit}"


def _range(values: list[float], fmt) -> str:
    return f"{fmt(values[1])} ({fmt(values[0])} à {fmt(values[2])})"


def markdown(summary: dict, level: str = "##", per_lot: bool = True) -> list[str]:
    """Section Markdown du coût IA du développement, pour le chiffrage, le plan de charge et spec-pack."""
    items = summary["scenarios"]
    if not items:
        return []
    cur = summary["currency"]
    out = [f"{level} Coût IA du développement", "",
           "Jetons consommés par les assistants et les agents pour développer la solution (pas son exploitation), "
           "médiane et fourchette P10-P90 : 80 % de chances que le coût réel y tombe si les hypothèses tiennent. "
           f"Fiabilité des hypothèses : **{summary['confidence']}** ({CONFIDENCE[summary['confidence']]}). Tarifs "
           f"de la grille relus le {summary['checked']}.", "",
           "| Hypothèse | Millions de jetons | Coût en dollars | " + (f"Coût en {cur} |" if cur else "") + " $ par million |",
           "| --- | --- | --- | " + ("--- | " if cur else "") + "--- |"]
    for item in items:
        out.append(f"| {item['name']} | {_range(item['mtok'], _mtok)} | {_range(item['usd'], lambda v: _money(v, '$'))} | "
                   + (f"{_range(item['cost'], lambda v: _money(v, cur))} | " if cur and item["cost"] else "")
                   + f"{item['usd_per_mtok']:.2f} |".replace(".", ","))
    held = [i for i in items if "budget_confidence" in i]
    if held:
        out += ["", "Confiance de tenir le budget IA : " + ", ".join(
            f"{i['name']} {i['budget_confidence']:.0f} %" for i in held) + "."]
    if per_lot:
        names = [i["name"] for i in items]
        out += ["", f"{level}# Par lot (médiane)", "",
                "| Lot | " + " | ".join(f"{n} : jours, Mjetons, $" for n in names) + " |",
                "| --- |" + " --- |" * len(names)]
        for index, lot in enumerate(items[0]["lots"]):
            cells = [f"{str(i['lots'][index]['days']).replace('.', ',')} j, {_mtok(i['lots'][index]['mtok'][1])}, "
                     f"{_money(i['lots'][index]['usd'][1], '$')}" for i in items]
            out.append(f"| {lot['id']} {lot['name']} | " + " | ".join(cells) + " |")
    out += ["", f"Base : {summary['basis']}. La somme des médianes par lot n'est pas la médiane du total.", ""]
    return out


def verify(path: Path) -> list[str]:
    """Relit le résumé écrit : forme attendue (SUMMARY_SCHEMA) et fourchettes ordonnées."""
    from spec_schema import check
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{path.name} illisible : {error}"]
    errors = [f"{path.name} : {e}" for e in check(data, SUMMARY_SCHEMA, SUMMARY_SCHEMA)]
    for item in data.get("scenarios", []):
        for key in ("mtok", "usd"):
            if sorted(item[key]) != item[key]:
                errors.append(f"{path.name} : {item['id']}/{key} : P10, P50, P90 non ordonnés {item[key]}")
    return errors
