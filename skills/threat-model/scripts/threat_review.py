# /// script
# requires-python = ">=3.10"
# ///
"""Reporte les décisions sur les menaces dans le modèle STRIDE préparé par stride.py.

Le modèle n'écrit pas le tableau des menaces : il répond par un fichier de
décisions court, une entrée par menace qu'il garde, précise, accepte ou
écarte (identifiants M001... de <sujet>.threats.json). Le script :
- vérifie chaque décision (menace connue, élément cohérent, mesure pour une
  menace traitée, raison pour une menace acceptée ou écartée) ;
- réécrit <sujet>.threats.md depuis <sujet>.threats.json : menace précisée,
  mesure retenue et statut dans le tableau, menaces écartées à part avec
  leur raison ;
- compte les menaces par statut et celles encore à analyser.

    uv run scripts/threat_review.py DECISIONS.json [--out SUJET.threats.md] [--fail-undecided] | --schema
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402

STATUS = {"a-traiter": "à traiter", "traitee": "traitée", "acceptee": "acceptée", "ecartee": "écartée"}
CATEGORIES = {"S": "Usurpation d'identité", "T": "Altération", "R": "Répudiation",
              "I": "Divulgation d'information", "D": "Déni de service", "E": "Élévation de privilèges"}


def cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="décisions (JSON)")
    parser.add_argument("--out", type=Path, help="modèle Markdown réécrit (défaut : celui de model, en .md)")
    parser.add_argument("--fail-undecided", action="store_true", help="erreur s'il reste des menaces à analyser")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON des décisions sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("fichier de décisions JSON attendu")
    report = {"input": str(args.spec), "output": None, "threats": 0, "decided": 0, "undecided": 0,
              "by_status": {s: 0 for s in STATUS}, "errors": [], "warnings": []}

    def stop() -> int:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(f"{args.spec} illisible : {error}")
        return stop()
    report["errors"] = validate(spec, __file__)
    if report["errors"]:
        return stop()
    model_path = (args.spec.parent / spec["model"]).resolve()
    try:
        model = json.loads(model_path.read_text(encoding="utf-8"))
        threats = {t["id"]: t for t in model["threats"]}
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["errors"].append(f"model : {spec['model']} illisible ({error}) ; lancez d'abord stride.py")
        return stop()

    decisions = spec["threats"]
    for key, decision in decisions.items():
        where = f"threats/{key}"
        if key not in threats:
            close = difflib.get_close_matches(key, list(threats), n=1)
            report["errors"].append(f"{where} : menace inconnue" + (f" ; vouliez-vous « {close[0]} » ?" if close
                                                                     else f" ({len(threats)} menaces : M001...)"))
            continue
        if decision.get("element") and decision["element"] != threats[key]["element"]:
            report["errors"].append(f"{where}/element : « {decision['element']} », mais {key} porte sur "
                                    f"« {threats[key]['element']} » : la description a changé, relancez stride.py "
                                    "et revoyez les identifiants")
        if decision["status"] == "traitee" and not decision.get("measure"):
            report["errors"].append(f"{where}/measure : mesure retenue attendue pour une menace traitée")
        if decision["status"] in ("acceptee", "ecartee") and not decision.get("why"):
            report["errors"].append(f"{where}/why : raison attendue pour une menace {STATUS[decision['status']]} "
                                    "(celle de l'utilisateur pour une acceptation)")
    if report["errors"]:
        return stop()

    lines = [model.get("head", "").rstrip(), "", "## Menaces", "",
             "| ID | Élément | STRIDE | Menace | Mesure type | Mesure retenue | Statut |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    dismissed = []
    for key, item in threats.items():
        decision = decisions.get(key)
        if decision and decision["status"] == "ecartee":
            dismissed.append(f"| {key} | {cell(item['element'])} | {cell(item['threat'])} | {cell(decision['why'])} |")
        else:
            measure = cell((decision or {}).get("measure", ""))
            if decision and decision.get("why") and decision["status"] == "acceptee":
                measure = f"{measure} (accepté : {cell(decision['why'])})".strip()
            lines.append(f"| {key} | {cell(item['element'])} | {item['stride']} : {CATEGORIES[item['stride']]} | "
                         f"{cell((decision or {}).get('threat') or item['threat'])} | {cell(item['measure'])} | "
                         f"{measure} | {STATUS[decision['status']] if decision else 'à analyser'} |")
        if decision:
            report["by_status"][decision["status"]] += 1
    if dismissed:
        lines += ["", "## Menaces écartées", "", "| ID | Élément | Menace | Raison |", "| --- | --- | --- | --- |"]
        lines += dismissed
    report["threats"], report["decided"] = len(threats), len(decisions)
    report["undecided"] = len(threats) - len(decisions)
    if report["undecided"]:
        message = f"{report['undecided']} menace(s) encore à analyser"
        (report["errors"] if args.fail_undecided else report["warnings"]).append(message)
    if report["by_status"]["a-traiter"]:
        report["warnings"].append(f"{report['by_status']['a-traiter']} menace(s) à traiter : mesure à décider")
    if report["errors"]:
        return stop()
    out = args.out or model_path.with_suffix(".md")
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    report["output"] = str(out)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
