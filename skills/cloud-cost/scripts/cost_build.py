# /// script
# requires-python = ">=3.10"
# ///
"""Estime le coût de fonctionnement mensuel d'options d'architecture cloud et les compare.

Entrée : une description JSON courte (`couts.json`) : pour chaque option,
son hébergeur et ses lignes de consommation (service de la grille, quantité,
environnement, plage horaire), avec au besoin un prix propre et sa base, et
une remise d'engagement. Le script, et non le modèle :
- vérifie hébergeurs (catalogue commun des skills cloud) et services de la
  grille, avec la valeur proche en cas de faute ;
- calcule chaque ligne (prix horaire x heures de la plage, ou prix mensuel x
  quantité), la remise, le coût mensuel par catégorie et par environnement,
  le coût annuel et sur l'horizon, et classe les options ;
- signale les prix pris dans la grille indicative (à vérifier), une grille
  ancienne, les environnements hors production allumés en continu (avec
  l'économie d'un arrêt la nuit et le week-end), les postes souvent oubliés
  (trafic sortant, sauvegardes, journaux) et le budget dépassé ;
- écrit `couts.md` (comparaison) et `couts.csv` (une ligne par
  consommation), relit le CSV et vérifie qu'il redonne les totaux ;
- avec --infra OPTION, écrit aussi les lignes d'infrastructure du chiffrage
  (skill solution-estimate) de cette option, au format de son chiffrage.json.

Les prix livrés (references/prix.json) sont des ordres de grandeur pour
comparer des options : aucun tarif n'est consulté en ligne.

    uv run scripts/cost_build.py couts.json [--out-dir DOSSIER] [--infra OPTION] | --schema
"""

import argparse
import csv
import datetime
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, require_file, schema_of  # noqa: E402
from spec_schema import check, print_schema, read_spec, schema_option  # noqa: E402

HERE = Path(__file__).resolve().parent
GRID = HERE.parent / "references" / "prix.json"
PROVIDERS = require_file("cloud-architecture", "lib/providers.json")
# Heures par mois de chaque plage horaire : en continu, ou 12 h par jour ouvré (22 jours).
SCHEDULES = {"continu": 730, "ouvre": 264}
CATEGORIES = ["calcul", "base de données", "stockage", "réseau", "exploitation"]
# Postes souvent oubliés : service, libellé.
USUAL = [("reseau.sortant", "trafic sortant"), ("sauvegarde", "sauvegardes"), ("journaux", "journaux et supervision")]
GRID_AGE_DAYS = 180


def close(value: str, known) -> str:
    match = difflib.get_close_matches(value, list(known), n=1)
    return f" ; vouliez-vous « {match[0]} » ?" if match else ""


def money(value: float, currency: str) -> str:
    return f"{value:,.0f} {'€' if currency == 'EUR' else currency}".replace(",", " ")


def load_grid(spec: dict, base: Path, errors: list[str]) -> dict | None:
    path = (base / spec["prices"]) if spec.get("prices") else GRID
    try:
        grid = json.loads(path.read_text(encoding="utf-8"))
        grid["services"], grid["providers"]  # noqa: B018 - forme minimale
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"prices : grille {path} illisible ({error})")
        return None
    grid["path"] = path
    return grid


def analyse(spec: dict, grid: dict, providers: dict, errors: list[str], warnings: list[str]) -> list[dict]:
    services, prices = grid["services"], grid["providers"]
    currency = spec.get("currency", grid.get("currency", "EUR"))
    if currency != grid.get("currency", "EUR"):
        warnings.append(f"devise {currency}, grille en {grid.get('currency', 'EUR')} : seuls les prix propres "
                        "(unit_cost) sont dans la devise demandée")
    results, indicative, ids = [], 0, set()
    for index, option in enumerate(spec["options"]):
        where = f"options/{index}"
        if option["id"] in ids:
            errors.append(f"{where}/id : option « {option['id']} » en double")
        ids.add(option["id"])
        provider = option["provider"]
        if provider not in providers:
            errors.append(f"{where}/provider : hébergeur inconnu « {provider} »{close(provider, providers)}")
        table = prices.get(provider, {})
        discount = option.get("discount") or {}
        lines, seen = [], set()
        for number, item in enumerate(option["items"]):
            at = f"{where}/items/{number}"
            if item["id"] in seen:
                errors.append(f"{at}/id : ligne « {item['id']} » en double dans l'option {option['id']}")
            seen.add(item["id"])
            service = item["service"]
            if service not in services:
                errors.append(f"{at}/service : service inconnu « {service} »{close(service, services)}")
                continue
            meta = services[service]
            price = item.get("unit_cost")
            if price is None:
                price = table.get(service)
                if price is None:
                    errors.append(f"{at} : pas de prix de {service} chez {provider} dans la grille : donnez "
                                  "unit_cost et basis")
                    continue
                indicative += 1
            elif not item.get("basis"):
                errors.append(f"{at}/basis : base du prix propre attendue (devis, grille et date)")
            schedule = item.get("schedule", "continu")
            hours = SCHEDULES[schedule] if isinstance(schedule, str) else float(schedule)
            if meta["per"] != "heure":
                hours = 1.0
            gross = item["quantity"] * price * hours
            reduced = gross * (1 - discount.get("percent", 0) / 100) \
                if meta["category"] in discount.get("on", ["calcul", "base de données"]) else gross
            lines.append({"id": item["id"], "service": service, "label": item.get("label") or meta["label"],
                          "category": meta["category"], "environment": item.get("environment", "production"),
                          "component": item.get("component"), "quantity": item["quantity"], "unit": meta["unit"],
                          "per": meta["per"], "unit_cost": price, "hours": hours, "schedule": schedule,
                          "monthly": round(reduced, 2), "gross": round(gross, 2),
                          "basis": item.get("basis") or f"grille indicative {grid.get('checked', '?')}"})
        monthly = round(sum(line["monthly"] for line in lines), 2)
        by_category = {c: round(sum(x["monthly"] for x in lines if x["category"] == c), 2) for c in CATEGORIES}
        by_env = {e: round(sum(x["monthly"] for x in lines if x["environment"] == e), 2)
                  for e in ("production", "hors-production")}
        always_on = [x for x in lines if x["environment"] == "hors-production" and x["per"] == "heure"
                     and x["schedule"] == "continu"]
        saving = round(sum(x["monthly"] * (1 - SCHEDULES["ouvre"] / SCHEDULES["continu"]) for x in always_on), 2)
        if always_on:
            warnings.append(f"option {option['id']} : hors production allumé en continu "
                            f"({', '.join(x['id'] for x in always_on)}) ; arrêt la nuit et le week-end "
                            f"(schedule « ouvre ») : {money(saving, currency)} de moins par mois")
        missing = [label for service, label in USUAL if not any(x["service"] == service for x in lines)]
        if missing:
            warnings.append(f"option {option['id']} : poste(s) souvent oublié(s), absent(s) : {', '.join(missing)}")
        if discount and not discount.get("basis"):
            errors.append(f"{where}/discount/basis : base de la remise attendue (engagement, contrat)")
        horizon = spec.get("horizon_months", 36)
        results.append({"id": option["id"], "name": option.get("name", option["id"]), "provider": provider,
                        "monthly": monthly, "annual": round(monthly * 12, 2), "horizon": round(monthly * horizon, 2),
                        "by_category": by_category, "by_environment": by_env, "saving_monthly": saving,
                        "lines": lines})
    if indicative:
        age = (datetime.date.today() - datetime.date.fromisoformat(grid.get("checked", "2000-01-01"))).days
        warnings.append(f"{indicative} prix pris dans la grille {'indicative' if grid['path'] == GRID else grid['path'].name}"
                        f" du {grid.get('checked', '?')} : à vérifier dans le calculateur du fournisseur"
                        + (f" (grille de plus de {GRID_AGE_DAYS} jours)" if age > GRID_AGE_DAYS else ""))
    budget = spec.get("budget_monthly")
    for result in results:
        if budget is not None and result["monthly"] > budget:
            warnings.append(f"option {result['id']} : {money(result['monthly'], currency)} par mois, budget "
                            f"{money(budget, currency)} dépassé")
    return results


def render(spec: dict, results: list[dict], currency: str) -> str:
    horizon = spec.get("horizon_months", 36)
    ranked = sorted(results, key=lambda r: r["monthly"])
    lines = [f"# Coût de fonctionnement : {spec['title']}", "",
             f"Coûts mensuels hors taxes, en {currency}, calculés par `cost_build.py`. Prix de la grille indicative "
             "sauf base indiquée : à vérifier avant tout engagement.", "",
             "## Comparaison", "",
             "| Option | Hébergeur | Par mois | Par an | Sur " + f"{horizon} mois | Production | Hors production |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for r in ranked:
        lines.append(f"| {r['id']} {r['name']} | {r['provider']} | {money(r['monthly'], currency)} | "
                     f"{money(r['annual'], currency)} | {money(r['horizon'], currency)} | "
                     f"{money(r['by_environment']['production'], currency)} | "
                     f"{money(r['by_environment']['hors-production'], currency)} |")
    lines += ["", "## Par catégorie, par mois", "", "| Catégorie | " + " | ".join(r["id"] for r in ranked) + " |",
              "| --- |" + " --- |" * len(ranked)]
    for category in CATEGORIES:
        lines.append(f"| {category} | " + " | ".join(money(r["by_category"][category], currency) for r in ranked) + " |")
    for r in ranked:
        lines += ["", f"## Option {r['id']} : {r['name']}", "",
                  "| Ligne | Service | Env. | Quantité | Prix unitaire | Heures | Par mois | Base |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for x in r["lines"]:
            per = "/h" if x["per"] == "heure" else "/mois"
            lines.append(f"| {x['id']} | {x['label']} | {x['environment']} | {x['quantity']:g} {x['unit']} | "
                         f"{x['unit_cost']:g}{per} | {x['hours']:g} | {money(x['monthly'], currency)} | {x['basis']} |")
    return "\n".join(lines) + "\n"


COLUMNS = ["option", "ligne", "service", "categorie", "environnement", "quantite", "unite", "prix_unitaire",
           "heures", "mensuel", "base"]


def write_csv(path: Path, results: list[dict]) -> None:
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(COLUMNS)
        for r in results:
            for x in r["lines"]:
                writer.writerow([r["id"], x["id"], x["service"], x["category"], x["environment"], x["quantity"],
                                 x["unit"], x["unit_cost"], x["hours"], f"{x['monthly']:.2f}", x["basis"]])


def verify_csv(path: Path, results: list[dict]) -> list[str]:
    with open(path, encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    errors = []
    for r in results:
        total = round(sum(float(row["mensuel"]) for row in rows if row["option"] == r["id"]), 2)
        if abs(total - r["monthly"]) > 0.05:
            errors.append(f"{path.name} : option {r['id']}, total {total} au lieu de {r['monthly']}")
    return errors


def infra_lines(result: dict, currency: str) -> list[dict]:
    """Lignes d'infrastructure du chiffrage (solution-estimate), une par environnement et catégorie."""
    lines = []
    for env in ("production", "hors-production"):
        for category in CATEGORIES:
            cost = round(sum(x["monthly"] for x in result["lines"]
                             if x["environment"] == env and x["category"] == category), 2)
            if cost:
                lines.append({"id": f"C-{result['id']}-{len(lines) + 1}", "name": f"{category.capitalize()} ({env})",
                              "environment": env, "kind": "cloud", "provider": result["provider"], "quantity": 1,
                              "unit_cost": cost, "period": "mois",
                              "basis": f"cost_build.py, option {result['id']} ({currency} par mois)"})
    return lines


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description couts.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--infra", metavar="OPTION",
                        help="écrire aussi <nom>.infra.json : lignes infra du chiffrage de cette option")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    report = {"input": str(args.spec), "outputs": [], "options": [], "cheapest": None, "errors": [], "warnings": []}

    def stop() -> int:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    spec, report["errors"] = read_spec(args.spec, __file__)
    if report["errors"]:
        return stop()
    grid = load_grid(spec, args.spec.parent, report["errors"])
    providers = json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]
    if grid is None:
        return stop()
    results = analyse(spec, grid, providers, report["errors"], report["warnings"])
    if args.infra and args.infra not in [r["id"] for r in results]:
        report["errors"].append(f"--infra : option inconnue « {args.infra} »{close(args.infra, [r['id'] for r in results])}")
    currency = spec.get("currency", grid.get("currency", "EUR"))
    lines = []
    if args.infra and not report["errors"]:
        lines = infra_lines(next(r for r in results if r["id"] == args.infra), currency)
        # Sortie vérifiée contre le schéma du chiffrage, si solution-estimate est installé.
        estimate = schema_of("solution-estimate", "estimate_build.py")
        if estimate is None:
            report["warnings"].append("lignes --infra non vérifiées : " + absent("solution-estimate", "estimate_build.py"))
        else:
            report["errors"] += [f"--infra : {e}" for e in check(lines, estimate["properties"]["infra"], estimate, "infra")]
    if report["errors"]:
        return stop()
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md, table = out_dir / f"{stem}.md", out_dir / f"{stem}.csv"
    md.write_text(render(spec, results, currency), encoding="utf-8")
    write_csv(table, results)
    report["errors"] = verify_csv(table, results)
    report["outputs"] = [str(md), str(table)]
    if args.infra:
        infra = out_dir / f"{stem}.infra.json"
        infra.write_text(json.dumps(lines, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report["outputs"].append(str(infra))
    report["options"] = [{k: r[k] for k in ("id", "provider", "monthly", "annual", "horizon", "saving_monthly")}
                         | {"by_category": r["by_category"]} for r in results]
    report["cheapest"] = min(results, key=lambda r: r["monthly"])["id"] if results else None
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
