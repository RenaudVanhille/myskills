# /// script
# requires-python = ">=3.10"
# ///
"""Mesure la justesse du tri des documents (type, domaine) : modèle léger du harness et, au choix, Laya.

Le jeu étiqueté `fixtures/tri/documents.json` donne le type et le domaine
attendus du début de documents fictifs. Le tri d'un modèle léger
(`documents-haiku.json` : nom du document, type et domaine, écrit par un
sous-agent de niveau simple à partir de --candidates) est comparé à ces
étiquettes sans charger de modèle. Avec --laya, classify.py (skill
doc-to-markdown) trie les mêmes documents avec le modèle local Laya, qui
doit être dans le cache (doctor.py extraction --prefetch) : justesse de
toutes ses réponses, puis des seules réponses retenues au seuil de confiance.

    uv run tests/classify_eval.py [--triage FICHIER] [--laya] [--markdown FICHIER] [--min-accuracy 0.9]
    uv run tests/classify_eval.py --candidates FICHIER
"""

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CLASSIFY = ROOT / "skills" / "doc-to-markdown" / "scripts" / "classify.py"
FIXTURES = ROOT / "tests" / "fixtures" / "tri"
KEYS = ("type", "domaine")
THRESHOLD = 0.5  # --min-confidence par défaut de classify.py


def accuracy(answers: dict, documents: list[dict], key: str) -> dict:
    """Part des documents bien classés ; un document sans étiquette pour cette clé n'est pas compté."""
    labelled = [d for d in documents if d[key] is not None]
    wrong = [f"{d['name']} : {answers.get(d['name'], {}).get(key) or 'sans réponse'} au lieu de {d[key]}"
             for d in labelled if answers.get(d["name"], {}).get(key) != d[key]]
    return {"accuracy": round(1 - len(wrong) / len(labelled), 3), "documents": len(labelled), "wrong": wrong}


def score(answers: dict, documents: list[dict]) -> dict:
    return {key: accuracy(answers, documents, key) for key in KEYS}


def laya_answers(documents: list[dict]) -> tuple[dict, dict, str | None]:
    """Réponses de classify.py : toutes (seuil 0), puis celles retenues au seuil par défaut."""
    with tempfile.TemporaryDirectory() as folder:
        for document in documents:
            Path(folder, document["name"]).write_text(document["text"], encoding="utf-8")
        run = subprocess.run(["uv", "run", str(CLASSIFY), folder, "--min-confidence", "0"],
                             capture_output=True, text=True, encoding="utf-8")
    try:
        results = json.loads(run.stdout)["results"]
    except (ValueError, KeyError):
        return {}, {}, f"classify.py n'a pas rendu de rapport (code {run.returncode}) : {run.stderr[-300:]}"
    if any(not r.get("method", "").startswith("laya") for r in results):
        return {}, {}, "Laya n'a pas été chargé : " + "; ".join(results[0].get("warnings", []))[:300]
    every = {Path(r["input"]).name: {key: r[key] for key in KEYS} for r in results}
    kept = {Path(r["input"]).name: {key: r[key] if (r[f"{key}_confidence"] or 0) >= THRESHOLD else None for key in KEYS}
            for r in results}
    return every, kept, None


def fr(value: float) -> str:
    return f"{round(value * 100)} %"


def markdown(report: dict) -> str:
    lines = [f"# Justesse du tri des documents ({report['documents']} documents)", "",
             "Part des documents dont le type, puis le domaine, est celui attendu.", "",
             "| Tri | Type | Domaine |", "| --- | --- | --- |"]
    for name, label in (("triage", "Modèle léger du harness"), ("laya", "Laya, toutes ses réponses"),
                        ("laya_kept", f"Laya, réponses retenues (confiance d'au moins {THRESHOLD})".replace(".", ","))):
        if report.get(name):
            lines.append(f"| {label} | {fr(report[name]['type']['accuracy'])} | {fr(report[name]['domaine']['accuracy'])} |")
    for name, label in (("triage", "du modèle léger"), ("laya", "de Laya (toutes ses réponses)")):
        wrong = [w for key in KEYS for w in (report.get(name) or {}).get(key, {}).get("wrong", [])]
        if wrong:
            lines += ["", f"## Erreurs {label}", ""] + [f"- {w}" for w in wrong]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--documents", type=Path, default=FIXTURES / "documents.json", help="jeu étiqueté")
    parser.add_argument("--triage", type=Path, default=FIXTURES / "documents-haiku.json",
                        help="tri d'un modèle léger : {nom: {type, domaine}}")
    parser.add_argument("--laya", action="store_true", help="trier aussi avec Laya (classify.py, modèle dans le cache)")
    parser.add_argument("--candidates", type=Path, help="écrit les documents à trier (sans étiquette), puis s'arrête")
    parser.add_argument("--markdown", type=Path, help="écrit aussi le rapport en Markdown")
    parser.add_argument("--min-accuracy", type=float, help="code 1 si le tri du modèle léger est en dessous (type)")
    args = parser.parse_args()

    report = {"documents": 0, "triage": None, "laya": None, "laya_kept": None, "errors": [], "warnings": []}
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
    if args.laya:
        every, kept, problem = laya_answers(documents)
        if problem:
            report["warnings"].append(problem)
        else:
            report["laya"], report["laya_kept"] = score(every, documents), score(kept, documents)
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
