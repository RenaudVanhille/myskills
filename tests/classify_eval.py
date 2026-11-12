# /// script
# requires-python = ">=3.10"
# ///
"""Mesure la justesse du tri des documents (type, domaine) fait par un modèle léger du harness.

Le jeu étiqueté `fixtures/tri/documents.json` donne le type et le domaine
attendus du début de documents fictifs. Le tri d'un modèle léger
(`documents-haiku.json` : nom du document, type et domaine, écrit par un
sous-agent de niveau simple à partir de --candidates) est comparé à ces
étiquettes sans charger de modèle. Pour mesurer un autre modèle : --candidates,
tri par ce modèle, puis --triage.

Mesure du 2026-11-11 sur ce jeu : modèle léger 100 % (type) et 90 % (domaine) ;
le modèle local Laya, que classify.py chargeait jusque-là, 57 % et 55 %, d'où
son retrait.

    uv run tests/classify_eval.py [--triage FICHIER] [--markdown FICHIER] [--min-accuracy 0.9]
    uv run tests/classify_eval.py --candidates FICHIER
"""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures" / "tri"
KEYS = ("type", "domaine")


def accuracy(answers: dict, documents: list[dict], key: str) -> dict:
    """Part des documents bien classés ; un document sans étiquette pour cette clé n'est pas compté."""
    labelled = [d for d in documents if d[key] is not None]
    wrong = [f"{d['name']} : {answers.get(d['name'], {}).get(key) or 'sans réponse'} au lieu de {d[key]}"
             for d in labelled if answers.get(d["name"], {}).get(key) != d[key]]
    return {"accuracy": round(1 - len(wrong) / len(labelled), 3), "documents": len(labelled), "wrong": wrong}


def score(answers: dict, documents: list[dict]) -> dict:
    return {key: accuracy(answers, documents, key) for key in KEYS}


def fr(value: float) -> str:
    return f"{round(value * 100)} %"


def markdown(report: dict) -> str:
    lines = [f"# Justesse du tri des documents ({report['documents']} documents)", "",
             "Part des documents dont le type, puis le domaine, est celui attendu.", "",
             "| Tri | Type | Domaine |", "| --- | --- | --- |"]
    if report.get("triage"):
        triage = report["triage"]
        lines.append(f"| Modèle léger du harness | {fr(triage['type']['accuracy'])} | {fr(triage['domaine']['accuracy'])} |")
        wrong = [w for key in KEYS for w in triage[key]["wrong"]]
        if wrong:
            lines += ["", "## Erreurs du modèle léger", ""] + [f"- {w}" for w in wrong]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--documents", type=Path, default=FIXTURES / "documents.json", help="jeu étiqueté")
    parser.add_argument("--triage", type=Path, default=FIXTURES / "documents-haiku.json",
                        help="tri d'un modèle léger : {nom: {type, domaine}}")
    parser.add_argument("--candidates", type=Path, help="écrit les documents à trier (sans étiquette), puis s'arrête")
    parser.add_argument("--markdown", type=Path, help="écrit aussi le rapport en Markdown")
    parser.add_argument("--min-accuracy", type=float, help="code 1 si le tri du modèle léger est en dessous (type)")
    args = parser.parse_args()

    report = {"documents": 0, "triage": None, "errors": [], "warnings": []}
    try:
        documents = json.loads(args.documents.read_text(encoding="utf-8"))["documents"]
    except (OSError, ValueError, KeyError) as error:
        report["errors"].append(f"{args.documents} : jeu illisible ({error})")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report["documents"] = len(documents)
    if args.candidates:
        args.candidates.write_text(json.dumps(
            [{"name": d["name"], "text": d["text"]} for d in documents], ensure_ascii=False, indent=1) + "\n",
            encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    try:
        triage = json.loads(args.triage.read_text(encoding="utf-8"))
        report["triage"] = {"file": args.triage.name, **score(triage, documents)}
    except (OSError, ValueError) as error:
        report["errors"].append(f"{args.triage} : tri illisible ({error})")
    if args.min_accuracy is not None and report["triage"] \
            and report["triage"]["type"]["accuracy"] < args.min_accuracy:
        report["errors"].append(f"tri du modèle léger : {report['triage']['type']['accuracy']} sur le type, "
                                f"sous le minimum {args.min_accuracy}")
    if args.markdown:
        args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
