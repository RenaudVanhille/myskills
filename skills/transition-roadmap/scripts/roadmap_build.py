# /// script
# requires-python = ">=3.10"
# ///
"""Calcule la feuille de route de transition d'une description JSON : dates, chemin critique, diagramme de Gantt.

Le modèle décrit les chantiers (durée en semaines, prédécesseurs, date au
plus tôt, lot, responsable) et les jalons (durée 0) ; il peut reprendre
les vagues de migration de migration-assessment (`waves.file`), chaque
vague devenant un chantier dont la durée est celle de sa plus longue
application. Le script, et non le modèle, calcule et contrôle :

- prédécesseurs connus et sans cycle ;
- dates au plus tôt de chaque chantier, fin du programme, marge et chemin
  critique ;
- échéance dépassée (`deadline`), chantier de plus de 26 semaines à
  découper, date imposée avant le début du programme.

Écrit <nom>.md (synthèse, tableau, diagramme de Gantt Mermaid) et
<nom>.csv.

    uv run scripts/roadmap_build.py FEUILLE.json [--out-dir DOSSIER] | --schema
"""

import argparse
import csv
import difflib
import json
import re
import sys
from datetime import date, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

LONG = 26


def close(name: str, known) -> str:
    match = difflib.get_close_matches(name, list(known), n=1)
    return f" ; vouliez-vous « {match[0]} » ?" if match else ""


def import_waves(spec: dict, base: Path, errors: list[str]) -> list[dict]:
    """Une vague de migration-assessment devient un chantier, après la vague précédente."""
    waves = spec.get("waves")
    if not waves:
        return []
    try:
        data = json.loads((base / waves["file"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"waves/file : {waves['file']} illisible ({error}) ; assess_build.py l'écrit (<nom>.waves.json)")
        return []
    weeks = waves.get("weeks", {"S": 2, "M": 4, "L": 8, "XL": 16})
    items = []
    for i, wave in enumerate(data.get("waves", [])):
        efforts = [a.get("effort") for a in wave.get("applications", [])]
        unknown = sorted({e for e in efforts if e not in weeks})
        if unknown:
            errors.append(f"waves/weeks : effort sans durée {', '.join(map(str, unknown))} ({', '.join(weeks)})")
            continue
        names = ", ".join(a["id"] for a in wave["applications"])
        items.append({"id": wave["id"], "name": f"Vague {i + 1} : {names}", "lot": waves.get("lot", "Migration"),
                      "weeks": max((weeks[e] for e in efforts), default=0),
                      "after": [data["waves"][i - 1]["id"]] if i else list(waves.get("after", []))})
    return items


def schedule(items: list[dict], start: date, errors: list[str], warnings: list[str]) -> dict:
    by_id = {it["id"]: it for it in items}
    ids = [it["id"] for it in items]
    errors += [f"items : identifiant en double « {i} »" for i in sorted({i for i in ids if ids.count(i) > 1})]
    for it in items:
        for dep in it.get("after", []):
            if dep not in by_id:
                errors.append(f"items/{it['id']}/after : chantier inconnu « {dep} »{close(dep, by_id)}")
    if len(by_id) != len(ids):
        return {}
    early: dict[str, tuple[date, date]] = {}
    visiting: set[str] = set()

    def dates(item_id: str, path: list[str]) -> tuple[date, date] | None:
        if item_id in early:
            return early[item_id]
        if item_id in visiting:
            errors.append(f"prédécesseurs en cycle : {' -> '.join(path[path.index(item_id):] + [item_id])}")
            return None
        visiting.add(item_id)
        it = by_id[item_id]
        begin = start
        if it.get("start"):
            fixed = date.fromisoformat(it["start"])
            if fixed < start:
                warnings.append(f"items/{item_id}/start : {fixed} avant le début du programme ({start})")
            begin = max(begin, fixed)
        for dep in [d for d in it.get("after", []) if d in by_id]:
            got = dates(dep, path + [item_id])
            if got is None:
                return None
            begin = max(begin, got[1])
        early[item_id] = (begin, begin + timedelta(days=round(it["weeks"] * 7)))
        visiting.discard(item_id)
        return early[item_id]

    for item_id in ids:
        if dates(item_id, []) is None or errors:
            return {}
    finish = max(end for _, end in early.values())
    # Passe arrière : fin au plus tard sans retarder le programme ; marge nulle = chemin critique.
    late: dict[str, date] = {}

    def latest(item_id: str) -> date:
        if item_id not in late:
            successors = [s for s in items if item_id in s.get("after", [])]
            late[item_id] = min((latest(s["id"]) - timedelta(days=round(s["weeks"] * 7)) for s in successors),
                                default=finish)
        return late[item_id]

    for item_id in ids:
        latest(item_id)
    critical = [i for i in sorted(ids, key=lambda i: early[i]) if late[i] == early[i][1]]
    for it in items:
        if it["weeks"] > LONG:
            warnings.append(f"items/{it['id']} : {it['weeks']} semaines, à découper en chantiers plus courts "
                            f"(au plus {LONG})")
    return {"early": early, "late": late, "finish": finish, "critical": critical}


def label(text: str) -> str:
    """Libellé sans les caractères qui cassent une ligne de Gantt Mermaid."""
    return re.sub(r"[;#]", "", re.sub(r"\s*:\s*", " - ", text)).strip()


def write(spec: dict, items: list[dict], plan: dict, out_dir: Path, stem: str) -> list[str]:
    early, late, critical = plan["early"], plan["late"], set(plan["critical"])
    rows = sorted(items, key=lambda it: (early[it["id"]][0], it["id"]))
    start = date.fromisoformat(spec["start"])
    weeks = round((plan["finish"] - start).days / 7, 1)
    lines = [f"# Feuille de route : {spec['title']}", "",
             f"Du {start} au {plan['finish']} ({weeks:g} semaines) ; {len(items)} chantiers et jalons ; "
             f"chemin critique : {' -> '.join(plan['critical'])}."]
    if spec.get("deadline"):
        lines.append(f"Échéance : {spec['deadline']}.")
    lines += ["", "| Id | Chantier | Lot | Début | Fin | Semaines | Marge (sem.) | Responsable | Critique |",
              "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for it in rows:
        begin, end = early[it["id"]]
        slack = round((late[it["id"]] - end).days / 7, 1)
        lines.append(f"| {it['id']} | {it['name']} | {it.get('lot', '')} | {begin} | {end} | {it['weeks']:g} "
                     f"| {slack:g} | {it.get('owner', '')} | {'oui' if it['id'] in critical else ''} |")
    lines += ["", "## Diagramme de Gantt", "", "```mermaid", "gantt", f"  title {label(spec['title'])}",
              "  dateFormat YYYY-MM-DD", "  axisFormat %m/%Y"]
    lots = list(dict.fromkeys(it.get("lot", "Programme") for it in rows))
    for lot in lots:
        lines.append(f"  section {label(lot)}")
        for it in rows:
            if it.get("lot", "Programme") != lot:
                continue
            tags = [t for t, on in (("milestone", it["weeks"] == 0), ("crit", it["id"] in critical)) if on]
            ident = re.sub(r"\W", "_", it["id"])
            days = round(it["weeks"] * 7)
            lines.append(f"  {label(it['name'])} :{', '.join(tags + [ident])}, {early[it['id']][0]}, {days}d")
    lines += ["```", ""]
    md = out_dir / f"{stem}.md"
    ai_mark.write_text(md, "\n".join(lines))
    path = out_dir / f"{stem}.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id", "chantier", "lot", "debut", "fin", "semaines", "responsable", "critique"])
        for it in rows:
            begin, end = early[it["id"]]
            writer.writerow([it["id"], it["name"], it.get("lot", ""), begin, end, it["weeks"], it.get("owner", ""),
                             "oui" if it["id"] in critical else ""])
    return [str(md), str(path)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description FEUILLE.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.spec), "outputs": [], "items": 0, "start": None, "end": None, "weeks": 0,
              "critical_path": [], "late_weeks": 0, "errors": errors, "warnings": warnings}
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        spec = None
    if spec is not None:
        # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
        errors += validate(spec, __file__)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    items = import_waves(spec, args.spec.resolve().parent, errors) + spec.get("items", [])
    if not items and not errors:
        errors.append("ni items ni waves : aucun chantier à planifier")
    plan = schedule(items, date.fromisoformat(spec["start"]), errors, warnings) if not errors else {}
    report["items"] = len(items)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    start = date.fromisoformat(spec["start"])
    report.update(start=str(start), end=str(plan["finish"]), weeks=round((plan["finish"] - start).days / 7, 1),
                  critical_path=plan["critical"])
    if spec.get("deadline"):
        over = (plan["finish"] - date.fromisoformat(spec["deadline"])).days
        if over > 0:
            report["late_weeks"] = round(over / 7, 1)
            warnings.append(f"échéance du {spec['deadline']} dépassée de {report['late_weeks']:g} semaine(s) : "
                            f"raccourcir le chemin critique ({', '.join(plan['critical'])}) ou décaler l'échéance")
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report["outputs"] = write(spec, items, plan, out_dir, args.spec.name.removesuffix(".json"))
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
