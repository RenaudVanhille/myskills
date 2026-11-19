# /// script
# requires-python = ">=3.10"
# ///
"""Dimensionne une solution à partir des volumes et des exigences non fonctionnelles : charge, instances, stockage, réseau.

Le modèle ne décrit que les hypothèses (utilisateurs, requêtes par
utilisateur et par heure, facteur de pic, volumes de données et de
fichiers, croissance, disponibilité visée, capacité d'un vCPU par
composant) ; le script, et non le modèle, calcule :

- le débit moyen et de pointe (requêtes par seconde) ;
- les vCPU, la mémoire et le nombre d'instances par composant, avec la
  redondance qu'impose la disponibilité (N+1 dès 99,9 %, une instance par
  zone au moins) ;
- le stockage des données et des fichiers à l'horizon, croissance et
  rétention comprises, les sauvegardes et le trafic sortant par mois ;
- avec --provider et --option, la description des consommations de
  cloud-cost (couts.json), contrôlée contre son schéma.

Écrit <nom>.md (hypothèses et chaque calcul avec sa formule) et
<nom>.result.json.

    uv run scripts/size_build.py DIMENSIONNEMENT.json [--out-dir DOSSIER] [--provider aws --option A [--costs couts.json]] | --schema
"""

import argparse
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, read_spec  # noqa: E402
from text_tools import beside  # noqa: E402

DEFAULT_RPS = {"web": 150, "api": 100, "worker": 20, "db": 300, "cache": 2000, "queue": 1000}
COMPUTE = {"web", "api", "worker"}


def fmt(value: float) -> str:
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",")
    return text.rstrip("0").rstrip(",") if "," in text else text


def size(spec: dict, warnings: list[str]) -> dict:
    users, load = spec["users"], spec["load"]
    hours, days = load.get("business_hours", 10), load.get("days_per_month", 22)
    active = users["total"] * users.get("active_share", 1)
    per_hour = active * load["requests_per_user_hour"]
    rps_avg = per_hour / 3600
    rps_peak = rps_avg * load.get("peak_factor", 3)
    per_month = per_hour * hours * days
    avail = spec.get("availability", {})
    target, zones = avail.get("target", 99.5), avail.get("zones", 1)
    redundant = target >= 99.9
    if target >= 99.95 and zones < 2:
        warnings.append(f"disponibilité {fmt(target)} % sur une seule zone : au moins 2 zones attendues")
    if load.get("peak_factor", 3) < 2:
        warnings.append("facteur de pic inférieur à 2 : à justifier (campagne, échéance, incident)")
    calc = [("Utilisateurs actifs", active, f"{fmt(users['total'])} x {fmt(users.get('active_share', 1))}"),
            ("Requêtes par heure", per_hour, f"utilisateurs actifs x {load['requests_per_user_hour']}"),
            ("Débit moyen (req/s)", rps_avg, "requêtes par heure / 3600"),
            ("Débit de pointe (req/s)", rps_peak, f"débit moyen x facteur de pic {load.get('peak_factor', 3)}"),
            ("Requêtes par mois", per_month, f"requêtes par heure x {hours} h x {days} jours")]
    components = []
    for comp in spec.get("components", []):
        kind = comp["kind"]
        rps = comp.get("rps_per_vcpu", DEFAULT_RPS.get(kind))
        vcpu_inst, ram_inst = comp.get("vcpu_per_instance", 2), comp.get("ram_gb_per_instance", 4)
        if kind in ("storage", "queue"):
            components.append({"id": comp["id"], "kind": kind, "instances": 0, "vcpu": 0, "ram_gb": 0,
                               "basis": "service managé, sans instance à dimensionner"})
            continue
        share = comp.get("load_share", 1)
        vcpu = max(1, math.ceil(rps_peak * share / rps))
        instances = max(comp.get("min_instances", 1), math.ceil(vcpu / vcpu_inst))
        basis = f"pointe {fmt(rps_peak * share)} req/s / {rps} req/s par vCPU = {vcpu} vCPU, {vcpu_inst} vCPU par instance"
        if redundant:
            instances = max(instances + 1, zones) if kind != "db" else max(2, zones)
            basis += f" ; redondance pour {fmt(target)} % (" + ("N+1" if kind != "db" else "primaire et réplique") + ")"
        if "rps_per_vcpu" not in comp:
            warnings.append(f"components/{comp['id']} : capacité par vCPU par défaut ({rps} req/s), à mesurer")
        components.append({"id": comp["id"], "kind": kind, "instances": instances, "vcpu": instances * vcpu_inst,
                           "ram_gb": instances * ram_inst, "basis": basis})
    years = spec.get("horizon_years", 3)
    data_gb = 0.0
    for d in spec.get("data", []):
        growth = (1 + d.get("growth_per_year", 0) / 100) ** min(years, d.get("retention_years", years))
        gb = d["records"] * d["record_kb"] * growth / 1024 / 1024
        data_gb += gb
        calc.append((f"Données {d['name']} à {years} ans (Go)", gb,
                     f"{fmt(d['records'])} enreg. x {d['record_kb']} Ko x croissance {fmt(growth)}"))
    files_gb = 0.0
    for f in spec.get("files", []):
        kept = min(years, f.get("retention_years", years)) * 12
        gb = f["count_per_month"] * kept * f["size_mb"] / 1024
        files_gb += gb
        calc.append((f"Fichiers {f['name']} à {years} ans (Go)", gb,
                     f"{fmt(f['count_per_month'])} par mois x {kept} mois x {f['size_mb']} Mo"))
    if not spec.get("data") and not spec.get("files"):
        warnings.append("aucun volume de données ni de fichiers : stockage non dimensionné")
    egress = per_month * load.get("response_kb", 20) / 1024 / 1024
    logs = per_month * load.get("log_kb", 1) / 1024 / 1024
    backup = data_gb * spec.get("backup_copies", 7) * 0.1 + data_gb
    calc += [("Trafic sortant par mois (Go)", egress, f"requêtes par mois x {load.get('response_kb', 20)} Ko"),
             ("Journaux par mois (Go)", logs, f"requêtes par mois x {load.get('log_kb', 1)} Ko"),
             ("Sauvegardes (Go)", backup, f"données + {spec.get('backup_copies', 7)} copies incrémentales à 10 %")]
    return {"rps_avg": round(rps_avg, 2), "rps_peak": round(rps_peak, 2), "requests_per_month": round(per_month),
            "data_gb": round(data_gb, 2), "files_gb": round(files_gb, 2), "egress_gb_month": round(egress, 2),
            "logs_gb_month": round(logs, 2), "backup_gb": round(backup, 2), "redundant": redundant,
            "components": components, "_calc": calc}


def costs(spec: dict, result: dict, provider: str, option: str) -> dict:
    items = []
    for c in result["components"]:
        if c["kind"] in COMPUTE:
            items += [{"id": f"{c['id']}.vcpu", "service": "conteneur.vcpu", "component": c["id"], "quantity": c["vcpu"]},
                      {"id": f"{c['id']}.ram", "service": "conteneur.ram", "component": c["id"], "quantity": c["ram_gb"]}]
        elif c["kind"] == "db":
            items += [{"id": f"{c['id']}.vcpu", "service": "bdd.vcpu", "component": c["id"], "quantity": c["vcpu"]},
                      {"id": f"{c['id']}.stockage", "service": "bdd.stockage", "component": c["id"],
                       "quantity": max(10, round(result["data_gb"] * 1.3, 1))}]
    if result["files_gb"]:
        items.append({"id": "fichiers", "service": "stockage.objet", "quantity": round(result["files_gb"], 1)})
    items += [{"id": "sauvegardes", "service": "sauvegarde", "quantity": max(1, round(result["backup_gb"], 1))},
              {"id": "sortant", "service": "reseau.sortant", "quantity": max(1, round(result["egress_gb_month"], 1))},
              {"id": "journaux", "service": "journaux", "quantity": max(1, round(result["logs_gb_month"], 1))}]
    return {"title": f"Coûts : {spec['title']}", "horizon_months": spec.get("horizon_years", 3) * 12,
            "options": [{"id": option, "provider": provider, "items": items}]}


def markdown(spec: dict, result: dict) -> str:
    lines = [f"# {spec['title']}", "", f"Disponibilité visée {fmt(spec.get('availability', {}).get('target', 99.5))} %, "
             f"horizon {spec.get('horizon_years', 3)} ans" + (f", exigences {', '.join(spec['refs'])}" if spec.get("refs") else "")
             + ".", "", "## Calculs", "", "| Grandeur | Valeur | Formule |", "| --- | --- | --- |"]
    lines += [f"| {name} | {fmt(value)} | {formula} |" for name, value, formula in result["_calc"]]
    if result["components"]:
        lines += ["", "## Composants", "", "| Composant | Type | Instances | vCPU | Mémoire (Go) | Base |",
                  "| --- | --- | --- | --- | --- | --- |"]
        lines += [f"| {c['id']} | {c['kind']} | {c['instances']} | {c['vcpu']} | {c['ram_gb']} | {c['basis']} |"
                  for c in result["components"]]
    if spec.get("assumptions"):
        lines += ["", "## Hypothèses", "", *[f"- {a}" for a in spec["assumptions"]]]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description DIMENSIONNEMENT.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui de la description)")
    parser.add_argument("--provider", help="hébergeur de cloud-cost (aws, azure, gcp, ovhcloud, scaleway...)")
    parser.add_argument("--option", help="identifiant de l'option (celui d'options.json), avec --provider")
    parser.add_argument("--costs", type=Path, help="description cloud-cost écrite (défaut : <nom>.couts.json)")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma de la description sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.spec), "outputs": [], "rps_peak": 0, "instances": 0, "vcpu": 0, "storage_gb": 0,
              "costs": None, "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.spec:
        errors.append("description DIMENSIONNEMENT.json attendue")
        return done(1)
    if bool(args.provider) != bool(args.option):
        errors.append("--provider et --option vont ensemble")
        return done(1)
    spec, invalid = read_spec(args.spec, __file__)
    errors += invalid
    if spec is None:
        return done(1)
    ids = [c["id"] for c in spec.get("components", [])] if not errors else []
    errors += [f"components : « {i} » en double" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if errors:
        return done(1)
    result = size(spec, warnings)
    out_dir = args.out_dir or args.spec.parent
    stem = args.spec.name.removesuffix(".json")
    files = {}
    if args.provider:
        described = costs(spec, result, args.provider, args.option)
        target = schema_of("cloud-cost", "cost_build.py")
        if target is None:
            warnings.append(f"couts.json non contrôlé : {absent('cloud-cost', 'cost_build.py')}")
        else:
            errors += [f"couts.json : {e}" for e in check(described, target)]
        files[args.costs or out_dir / f"{stem}.couts.json"] = json.dumps(described, ensure_ascii=False, indent=1) + "\n"
    if errors:
        return done(1)
    calc = result.pop("_calc")
    files[beside(out_dir / f"{stem}.md")] = markdown(spec, {**result, "_calc": calc})
    files[out_dir / f"{stem}.result.json"] = json.dumps(result, ensure_ascii=False, indent=1) + "\n"
    out_dir.mkdir(parents=True, exist_ok=True)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    if args.provider:
        report["costs"] = str(next(iter(files)))
    report.update(outputs=[str(p) for p in files], rps_peak=result["rps_peak"],
                  instances=sum(c["instances"] for c in result["components"]),
                  vcpu=sum(c["vcpu"] for c in result["components"]),
                  storage_gb=round(result["data_gb"] + result["files_gb"], 2))
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
