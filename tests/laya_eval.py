# /// script
# requires-python = ">=3.10"
# ///
"""Mesure la justesse de Laya sur les exigences en français, face à la regex de req_build.py.

Le jeu étiqueté `fixtures/laya/phrases.json` donne pour chaque phrase la
réponse attendue : exigence ou non, et pour une exigence sa nature et sa
catégorie. Le script pose à Laya les questions de req_build.py --laya (par
`ask_laya`, donc avec le même cache et le même repli), puis compare :
- exigence : précision, rappel et F1 de Laya au seuil de req_build.py
  (LAYA_REQUIREMENT), ceux de la regex NORMATIVE, et le seuil qui donne le
  meilleur F1 ;
- nature et catégorie : part de bonnes réponses, et part des désaccords que
  req_build.py signalerait à tort (confiance >= LAYA_DISAGREE).

Laya est gardé dans req_build.py si son F1 dépasse celui de la regex.
Premier lancement long (PyTorch CPU puis le modèle, ~1,5 Go) ; les réponses
restent dans le cache. Ce script sert aux tests du dépôt (CI : job laya).

    uv run tests/laya_eval.py [--phrases FICHIER] [--cache FICHIER] [--markdown FICHIER] [--min-gain 0]
"""

import argparse
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REQ_BUILD = ROOT / "skills" / "requirements-catalog" / "scripts" / "req_build.py"
THRESHOLDS = [round(0.05 * i, 2) for i in range(4, 19)]


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


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phrases", type=Path, default=ROOT / "tests" / "fixtures" / "laya" / "phrases.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".myskills-tmp" / "laya-eval.laya.json",
                        help="cache des réponses de Laya (même format que req_build.py --laya-cache)")
    parser.add_argument("--markdown", type=Path, help="écrit aussi le résultat en Markdown (résumé de CI)")
    parser.add_argument("--min-gain", type=float,
                        help="code 1 si le F1 de Laya ne dépasse pas celui de la regex d'au moins cette valeur")
    args = parser.parse_args()

    report = {"phrases": 0, "method": None, "exigence": None, "nature": None, "categorie": None,
              "best_threshold": None, "mistakes": [], "errors": [], "warnings": []}
    try:
        phrases = json.loads(args.phrases.read_text(encoding="utf-8"))["phrases"]
    except (OSError, ValueError, KeyError) as error:
        report["errors"].append(f"{args.phrases} illisible : {error}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    rb = load_req_build()
    key = rb.laya_key
    asked = [{"key": key("exigence", p["text"]), "question": "exigence", "text": p["text"]} for p in phrases]
    asked += [{"key": key(q, p["text"]), "question": q, "text": p["text"]} for p in phrases
              for q in ("nature", "categorie") if p.get(q)]
    answers, method = rb.ask_laya(asked, args.cache, report["warnings"])
    report["phrases"], report["method"] = len(phrases), method
    if method == "regles":
        report["errors"].append("Laya n'a rien répondu : " + "; ".join(report["warnings"][:1]))
        print(json.dumps(report, ensure_ascii=False))
        return 1

    expected = [p["exigence"] for p in phrases]
    probability = [answers.get(key("exigence", p["text"]), {}).get("probability", 0.0) for p in phrases]
    regex = [bool(rb.NORMATIVE.search(rb.normalize(p["text"]))) for p in phrases]
    laya = scores([x >= rb.LAYA_REQUIREMENT for x in probability], expected)
    report["exigence"] = {"threshold": rb.LAYA_REQUIREMENT, "laya": laya, "regex": scores(regex, expected),
                          "gain_f1": round(laya["f1"] - scores(regex, expected)["f1"], 3)}
    best = max(THRESHOLDS, key=lambda t: (scores([x >= t for x in probability], expected)["f1"], -abs(t - 0.5)))
    report["best_threshold"] = {"threshold": best, **scores([x >= best for x in probability], expected)}
    for p, x, r in zip(phrases, probability, regex):
        if (x >= rb.LAYA_REQUIREMENT) != p["exigence"]:
            report["mistakes"].append({"question": "exigence", "text": p["text"][:100], "expected": p["exigence"],
                                       "laya": x, "regex": r})

    for question in ("nature", "categorie"):
        labelled = [p for p in phrases if p.get(question)]
        said = [answers.get(key(question, p["text"]), {}) for p in labelled]
        right = sum(s.get("choice") == p[question] for p, s in zip(labelled, said))
        false_alarms = sum(s.get("choice") not in (None, p[question]) and s.get("confidence", 0) >= rb.LAYA_DISAGREE
                           for p, s in zip(labelled, said))
        report[question] = {"labelled": len(labelled), "accuracy": round(right / len(labelled), 3) if labelled else 0,
                            "false_alarms": false_alarms, "confidence_threshold": rb.LAYA_DISAGREE}
        report["mistakes"] += [{"question": question, "text": p["text"][:100], "expected": p[question],
                                "laya": s.get("choice"), "confidence": s.get("confidence")}
                               for p, s in zip(labelled, said) if s.get("choice") != p[question]]

    if args.markdown:
        e = report["exigence"]
        lines = [f"# Justesse de Laya sur les exigences ({len(phrases)} phrases, {method})", "",
                 "| Question | Laya | Regex |", "| --- | --- | --- |",
                 f"| exigence, F1 (seuil {e['threshold']}) | {e['laya']['f1']} | {e['regex']['f1']} |",
                 f"| exigence, précision | {e['laya']['precision']} | {e['regex']['precision']} |",
                 f"| exigence, rappel | {e['laya']['recall']} | {e['regex']['recall']} |",
                 f"| nature, bonnes réponses | {report['nature']['accuracy']} | (déclarée) |",
                 f"| catégorie, bonnes réponses | {report['categorie']['accuracy']} | (déclarée) |", "",
                 f"Meilleur seuil pour exigence : {best} (F1 {report['best_threshold']['f1']}). "
                 f"Fausses alertes de req_build.py : nature {report['nature']['false_alarms']}, "
                 f"catégorie {report['categorie']['false_alarms']}.", "", "## Erreurs de Laya", "",
                 "| Question | Phrase | Attendu | Laya |", "| --- | --- | --- | --- |"]
        lines += [f"| {m['question']} | {m['text'].replace('|', '/')} | {m['expected']} | {m['laya']} |"
                  for m in report["mistakes"]]
        args.markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    if args.min_gain is not None and report["exigence"]["gain_f1"] < args.min_gain:
        report["errors"].append(f"F1 de Laya {laya['f1']} : gain {report['exigence']['gain_f1']} sur la regex, "
                                f"moins que --min-gain {args.min_gain}")
    report["mistakes"] = report["mistakes"][:40]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
