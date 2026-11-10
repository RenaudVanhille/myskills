# /// script
# requires-python = ">=3.10"
# ///
"""Mesure la justesse de Laya sur les exigences en français, face à la regex de req_build.py.

Le jeu étiqueté `fixtures/laya/phrases.json` donne pour chaque phrase la
réponse attendue : exigence ou non, et pour une exigence sa nature et sa
catégorie. Le script pose à Laya les questions de req_build.py --laya (par
`ask_laya`, donc avec le même cache et le même repli), puis compare :
- exigence : précision, rappel et F1 de Laya au seuil de req_build.py
  (LAYA_REQUIREMENT), ceux de la regex NORMATIVE, ceux de la règle de
  req_build.py (regex ou Laya), et le seuil qui donne le meilleur F1 ;
- catégorie : part de bonnes réponses, et désaccords que req_build.py
  signalerait à tort (confiance >= LAYA_DISAGREE) ;
- avec --triage, le tri des phrases par un modèle léger (req_build.py
  --candidates, puis <nom>.tri.json) : précision, rappel et F1, comme Laya.

Laya est gardé dans req_build.py si la règle regex ou Laya dépasse la regex seule.
Premier lancement long (PyTorch CPU puis le modèle, ~1,5 Go) ; les réponses
restent dans le cache. Ce script sert aux tests du dépôt (CI : job laya).

    uv run tests/laya_eval.py [--phrases FICHIER] [--cache FICHIER] [--triage FICHIER] [--markdown FICHIER] [--min-gain 0]
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


def fr(value: float) -> str:
    return str(value).replace(".", ",")


def table(title: str, intro: str, header: list[str], rows: list[list[str]]) -> list[str]:
    if not rows:
        return []
    return [f"## {title} ({len(rows)})", "", intro, "", "| " + " | ".join(header) + " |",
            "| " + " | ".join("---" for _ in header) + " |",
            *("| " + " | ".join(str(c).replace("|", "/") for c in row) + " |" for row in rows), ""]


def markdown(report: dict, min_gain: float | None) -> str:
    """Le rapport en phrases : verdict, comment lire les chiffres, puis les erreurs par nature."""
    e, c, mistakes = report["exigence"], report["categorie"], report["mistakes"]
    seuil, oui_non = fr(e["threshold"]), lambda value: "oui" if value else "non"
    exigence = [m for m in mistakes if m["question"] == "exigence"]
    verdict = ("Laya est utile" if e["gain_f1"] > 0 else "Laya n'apporte rien") + (
        "" if min_gain is None else f", gain minimal demandé {fr(min_gain)} : "
        + ("atteint" if e["gain_f1"] >= min_gain else "**non atteint**"))
    lines = [
        f"# Justesse de Laya sur les exigences ({report['phrases']} phrases, {report['method']})", "",
        f"**{verdict}.** Pour repérer les exigences, la règle de req_build.py (regex ou Laya) obtient un score F1 "
        f"de {fr(e['rule']['f1'])}, contre {fr(e['regex']['f1'])} pour la regex seule (gain {fr(e['gain_f1'])}). "
        f"Laya trouve la bonne catégorie pour {round(c['accuracy'] * 100)} % des {c['labelled']} exigences "
        "étiquetées.", "",
        "## Comment lire ce rapport", "",
        "- Chaque phrase du jeu de test est étiquetée à la main : exigence ou non, et sa catégorie.",
        f"- Laya donne à chaque phrase une probabilité de 0 à 1 d'être une exigence. À partir de {seuil}, "
        "la phrase est prise pour une exigence.",
        "- Précision : parmi les phrases prises pour des exigences, la part qui en sont vraiment. "
        "Rappel : parmi les vraies exigences, la part retrouvée. F1 : la moyenne des deux (1 = sans faute).", "",
        "| Exigence ou non | Laya seul | Regex seule | Regex ou Laya (req_build.py) |", "| --- | --- | --- | --- |",
        *(f"| {label} | {fr(e['laya'][k])} | {fr(e['regex'][k])} | {fr(e['rule'][k])} |"
          for label, k in (("F1", "f1"), ("Précision", "precision"), ("Rappel", "recall"),
                           ("Fausses exigences", "false_positives"), ("Exigences manquées", "false_negatives"))), "",
        f"Le seuil qui donnerait le meilleur F1 à Laya seul est {fr(report['best_threshold']['threshold'])} "
        f"(F1 {fr(report['best_threshold']['f1'])}).", ""]
    if report["triage"]:
        t = report["triage"]
        lines += [f"Tri par un modèle léger ({t['file']}, {t['sorted']} phrases triées) : F1 {fr(t['f1'])}, "
                  f"précision {fr(t['precision'])}, rappel {fr(t['recall'])}.", ""]
    lines += table("Exigences que Laya ne voit pas",
                   f"Ce sont de vraies exigences, mais Laya leur donne une probabilité sous {seuil}. "
                   "Si la regex les reconnaît, req_build.py les garde quand même.",
                   ["Phrase", "Probabilité selon Laya", "Rattrapée par la regex"],
                   [[m["text"], fr(m["laya"]), oui_non(m["regex"])] for m in exigence if m["expected"]])
    lines += table("Phrases que Laya prend à tort pour des exigences",
                   f"Ce ne sont pas des exigences, mais Laya leur donne une probabilité d'au moins {seuil}.",
                   ["Phrase", "Probabilité selon Laya", "Même erreur de la regex"],
                   [[m["text"], fr(m["laya"]), oui_non(m["regex"])] for m in exigence if not m["expected"]])
    lines += table("Catégories mal trouvées par Laya",
                   f"À partir d'une confiance de {fr(c['confidence_threshold'])}, req_build.py signalerait à tort "
                   f"un désaccord avec la catégorie déclarée ({c['false_alarms']} cas).",
                   ["Phrase", "Catégorie attendue", "Catégorie selon Laya", "Confiance", "Fausse alerte"],
                   [[m["text"], m["expected"], m["laya"] or "aucune", fr(m["confidence"] or 0),
                     oui_non(m["laya"] and (m["confidence"] or 0) >= c["confidence_threshold"])]
                    for m in mistakes if m["question"] == "categorie"])
    lines += table("Erreurs du tri par un modèle léger", "Le tri dit si la phrase est une exigence.",
                   ["Phrase", "Exigence attendue", "Réponse du tri"],
                   [[m["text"], oui_non(m["expected"]), "non triée" if m["laya"] is None else oui_non(m["laya"])]
                    for m in mistakes if m["question"] == "tri"])
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--phrases", type=Path, default=ROOT / "tests" / "fixtures" / "laya" / "phrases.json")
    parser.add_argument("--cache", type=Path, default=ROOT / ".myskills-tmp" / "laya-eval.laya.json",
                        help="cache des réponses de Laya (même format que req_build.py --laya-cache)")
    parser.add_argument("--triage", type=Path, default=ROOT / "tests" / "fixtures" / "laya" / "tri-haiku.json",
                        help="tri des phrases par un modèle léger, clé de req_build.triage_key -> booléen")
    parser.add_argument("--markdown", type=Path, help="écrit aussi le résultat en Markdown (résumé de CI)")
    parser.add_argument("--min-gain", type=float,
                        help="code 1 si le F1 de la règle regex ou Laya ne dépasse pas celui de la regex d'au moins cette valeur")
    args = parser.parse_args()

    report = {"phrases": 0, "method": None, "exigence": None, "categorie": None, "triage": None,
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
              for q in ("categorie",) if p.get(q)]
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
    # Règle de req_build.py : phrase signalée si la regex ou Laya y voit une exigence.
    rule = scores([rb.flagged(r, {"probability": x}) for r, x in zip(regex, probability)], expected)
    report["exigence"] = {"threshold": rb.LAYA_REQUIREMENT, "laya": laya, "regex": scores(regex, expected),
                          "rule": rule, "gain_f1": round(rule["f1"] - scores(regex, expected)["f1"], 3)}
    best = max(THRESHOLDS, key=lambda t: (scores([x >= t for x in probability], expected)["f1"], -abs(t - 0.5)))
    report["best_threshold"] = {"threshold": best, **scores([x >= best for x in probability], expected)}
    for p, x, r in zip(phrases, probability, regex):
        if (x >= rb.LAYA_REQUIREMENT) != p["exigence"]:
            report["mistakes"].append({"question": "exigence", "text": p["text"][:100], "expected": p["exigence"],
                                       "laya": x, "regex": r})

    try:
        sorted_as = json.loads(args.triage.read_text(encoding="utf-8")) if args.triage else {}
    except (OSError, ValueError) as error:
        sorted_as = {}
        report["warnings"].append(f"tri illisible : {error}")
    if sorted_as:
        said = [sorted_as.get(rb.triage_key(p["text"])) for p in phrases]
        report["triage"] = {"file": args.triage.name, "sorted": sum(s is not None for s in said),
                            **scores([bool(s) for s in said], expected)}
        report["mistakes"] += [{"question": "tri", "text": p["text"][:100], "expected": p["exigence"], "laya": s}
                               for p, s in zip(phrases, said) if bool(s) != p["exigence"]]

    for question in ("categorie",):
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

    if args.min_gain is not None and report["exigence"]["gain_f1"] < args.min_gain:
        report["errors"].append(f"F1 de la règle {rule['f1']} : gain {report['exigence']['gain_f1']} sur la regex, "
                                f"moins que --min-gain {args.min_gain}")
    if args.markdown:
        args.markdown.write_text(markdown(report, args.min_gain), encoding="utf-8")
    report["mistakes"] = report["mistakes"][:40]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
