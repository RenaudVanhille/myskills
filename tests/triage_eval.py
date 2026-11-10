# /// script
# requires-python = ">=3.10"
# ///
"""Mesure la justesse du tri des phrases d'exigence par un modèle léger, face à la regex de req_build.py.

Le jeu étiqueté `fixtures/tri/phrases.json` dit pour chaque phrase si elle
exprime une exigence. Le tri (`<nom>.tri.json`, écrit par un sous-agent de
niveau simple à partir de req_build.py --candidates) est comparé à ces
étiquettes et à la regex NORMATIVE : précision, rappel et F1. Aucun modèle
n'est chargé ; pour mesurer un autre modèle, refaire son tri sur les mêmes
phrases et le passer par --triage.

    uv run tests/triage_eval.py [--phrases FICHIER] [--triage FICHIER] [--markdown FICHIER] [--min-f1 0.9]
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ_BUILD = ROOT / "skills" / "requirements-catalog" / "scripts" / "req_build.py"
FIXTURES = ROOT / "tests" / "fixtures" / "tri"


def load_req_build():
    sys.path.insert(0, str(REQ_BUILD.parent))
    spec = importlib.util.spec_from_file_location("req_build", REQ_BUILD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def scores(predicted: list[bool], expected: list[bool]) -> dict:
    tp = sum(p and e for p, e in zip(predicted, expected))
    fp = sum(p and not e for p, e in zip(predicted, expected))
    fn = sum(e and not p for p, e in zip(predicted, expected))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3),
            "false_positives": fp, "false_negatives": fn}


def fr(value: float) -> str:
    return str(value).replace(".", ",")


def markdown(report: dict) -> str:
    """Le rapport en phrases : verdict, comment lire les chiffres, puis les erreurs du tri."""
    tri, regex = report["triage"], report["regex"]
    oui_non = lambda value: "oui" if value else "non"  # noqa: E731
    lines = [
        f"# Justesse du tri des phrases d'exigence ({report['phrases']} phrases)", "",
        f"Le tri par un modèle léger ({tri['file']}, {tri['sorted']} phrases triées) obtient un score F1 de "
        f"{fr(tri['f1'])}, contre {fr(regex['f1'])} pour la regex seule.", "",
        "- Précision : parmi les phrases prises pour des exigences, la part qui en sont vraiment.",
        "- Rappel : parmi les vraies exigences, la part retrouvée.",
        "- F1 : la moyenne des deux (1 = sans faute).", "",
        "| Exigence ou non | Tri | Regex seule |", "| --- | --- | --- |",
        *(f"| {label} | {fr(tri[k])} | {fr(regex[k])} |"
          for label, k in (("F1", "f1"), ("Précision", "precision"), ("Rappel", "recall"),
                           ("Fausses exigences", "false_positives"), ("Exigences manquées", "false_negatives"))), ""]
    if report["mistakes"]:
        lines += [f"## Erreurs du tri ({len(report['mistakes'])})", "",
                  "| Phrase | Exigence attendue | Réponse du tri |", "| --- | --- | --- |",
                  *(f"| {m['text'].replace('|', '/')} | {oui_non(m['expected'])} | "
                    f"{'non triée' if m['sorted'] is None else oui_non(m['sorted'])} |" for m in report["mistakes"]),
                  ""]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phrases", type=Path, default=FIXTURES / "phrases.json")
    parser.add_argument("--triage", type=Path, default=FIXTURES / "tri-haiku.json",
                        help="tri des phrases par un modèle léger, clé de req_build.triage_key -> booléen")
    parser.add_argument("--markdown", type=Path, help="écrit aussi le résultat en Markdown")
    parser.add_argument("--min-f1", type=float, help="code 1 si le F1 du tri est sous cette valeur")
    args = parser.parse_args()

    report = {"phrases": 0, "triage": None, "regex": None, "mistakes": [], "errors": [], "warnings": []}
    try:
        phrases = json.loads(args.phrases.read_text(encoding="utf-8"))["phrases"]
        sorted_as = json.loads(args.triage.read_text(encoding="utf-8"))
    except (OSError, ValueError, KeyError) as error:
        report["errors"].append(f"fichier illisible : {error}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    rb = load_req_build()
    expected = [p["exigence"] for p in phrases]
    said = [sorted_as.get(rb.triage_key(p["text"])) for p in phrases]
    report.update(
        phrases=len(phrases),
        triage={"file": args.triage.name, "sorted": sum(s is not None for s in said),
                **scores([bool(s) for s in said], expected)},
        regex=scores([bool(rb.NORMATIVE.search(rb.normalize(p["text"]))) for p in phrases], expected),
        mistakes=[{"text": p["text"][:100], "expected": p["exigence"], "sorted": s}
                  for p, s in zip(phrases, said) if bool(s) != p["exigence"]])
    if args.min_f1 is not None and report["triage"]["f1"] < args.min_f1:
        report["errors"].append(f"F1 du tri {report['triage']['f1']}, moins que --min-f1 {args.min_f1}")
    if args.markdown:
        args.markdown.write_text(markdown(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
