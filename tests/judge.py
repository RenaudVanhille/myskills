# /// script
# requires-python = ">=3.10"
# ///
"""Note les résultats des agents et les descriptions des skills avec un modèle de décision.

Deux juges possibles, qui répondent aux mêmes questions fermées (oui/non,
choix, note) avec des probabilités, sans rédiger de texte :
- `laya` (défaut) : modèle local Laya, rien ne sort du poste. À lancer avec
  `uv run --with laya tests/judge.py ...` (PyTorch et ~1,3 Go de modèle au
  premier lancement) ;
- `decision1` : Microsoft Decision 1 via OpenRouter, si la variable
  OPENROUTER_API_KEY est définie. Les textes jugés partent alors chez
  OpenRouter : n'utilisez que les documents de test, jamais de documents réels.

Ce script sert aux tests du dépôt ; aucun skill livré n'en dépend.

Usage :
    uv run --with laya tests/judge.py triggers [--min-accuracy 0.8]
    uv run --with laya tests/judge.py outputs DOSSIER [--only ID[,ID]]
    uv run tests/judge.py --backend decision1 [--model ID] triggers|outputs ...
    uv run tests/judge.py --backend checks outputs DOSSIER [--only ID[,ID]]

- triggers : pour chaque demande de tests/triggers.json, le juge choisit un
  skill d'après les seules descriptions des SKILL.md. Mesure si les
  descriptions suffisent à déclencher le bon skill.
- outputs : pour chaque cas de tests/agent-cases.json dont le fichier de
  sortie existe dans DOSSIER (le dossier de travail de l'agent), le juge
  vérifie chaque affirmation de la grille et, s'il y a un attendu, la
  fidélité au texte attendu. Les contrôles `checks` du cas (fichier présent,
  texte contenu ou motif, valeur ou nombre d'éléments d'un JSON) se vérifient
  sans modèle ; `--backend checks` ne fait que ceux-là.

La note d'un cas (`score`, de 0 à 1) est la part des contrôles et des
affirmations vérifiés ; tests/cost.py --judge la garde dans costs.csv à côté
du coût, pour suivre la qualité et le coût ensemble.
"""

import argparse
import json
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
OPENROUTER_URL = "https://openrouter.ai/api/alpha/decisions"
# Identifiant à vérifier dans le catalogue OpenRouter (modèles « decisions »).
DEFAULT_DECISION1 = "microsoft/decision-1"
MAX_CHARS = 6000
RUBRIC_THRESHOLD = 0.5
FIDELITY_LEVELS = ["rien ou presque", "une partie du contenu", "l'essentiel du contenu",
                   "tout le contenu"]
FIDELITY_MIN = 2.0
DESCRIPTION = re.compile(r'^description:\s*"?(.*?)"?\s*$', re.M)


class Judge:
    def __init__(self, backend: str, model: str | None):
        self.backend = backend
        if backend == "checks":
            return
        if backend == "laya":
            os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
            try:
                from laya import Router
            except ImportError:
                sys.exit("Laya n'est pas installé : lancez `uv run --with laya tests/judge.py ...`.")
            self.router = Router()
        else:
            self.key = os.environ.get("OPENROUTER_API_KEY")
            if not self.key:
                sys.exit("OPENROUTER_API_KEY n'est pas définie (nécessaire pour decision1).")
            self.model = model or DEFAULT_DECISION1

    def ask(self, state: dict, questions: dict) -> dict:
        if self.backend == "laya":
            return self.router.predict(state, questions, max_len=4096)["answers"]
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        request = urllib.request.Request(OPENROUTER_URL, data=body, headers={
            "Authorization": f"Bearer {self.key}", "Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))["answers"]


def skill_descriptions() -> dict:
    skills = {}
    for path in sorted((ROOT / "skills").glob("*/SKILL.md")):
        match = DESCRIPTION.search(path.read_text(encoding="utf-8"))
        if match:
            skills[path.parent.name] = match.group(1)
    return skills


def run_triggers(judge: Judge, min_accuracy: float) -> int:
    skills = skill_descriptions()
    cases = json.loads((TESTS / "triggers.json").read_text(encoding="utf-8"))["cases"]
    question = {"skill": {"type": "choice", "criteria": skills, "instructions":
                          "Quel skill faut-il utiliser pour répondre à cette demande ?"}}
    results = []
    for case in cases:
        answer = judge.ask({"demande": case["prompt"]}, question)["skill"]
        results.append({"prompt": case["prompt"], "attendu": case["skill"],
                        "choisi": answer["choice"], "ok": answer["choice"] == case["skill"],
                        "confiance": round(float(answer.get("confidence", 0)), 3)})
    accuracy = sum(r["ok"] for r in results) / len(results)
    print(json.dumps({"precision": round(accuracy, 3), "erreurs": [r for r in results if not r["ok"]],
                      "resultats": results}, ensure_ascii=False, indent=2))
    return 0 if accuracy >= min_accuracy else 1


def readable(path: Path) -> str:
    """Texte à juger : le fichier, ou un résumé lisible pour un schéma."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if path.suffix == ".drawio":
        try:
            cells = ET.fromstring(text).iter("mxCell")
        except ET.ParseError:
            return text[:MAX_CHARS]
        names, lines = {}, []
        cells = list(cells)
        for cell in cells:
            if cell.get("vertex") == "1":
                names[cell.get("id")] = re.sub(r"<[^>]+>", " ", cell.get("value") or "").strip()
                style = cell.get("style") or ""
                kind = "Texte" if style.startswith("text") else "Forme"
                dashed = " (bordure en tirets)" if "dashed=1" in style else ""
                lines.append(f"{kind} : {names[cell.get('id')]}{dashed}")
        for cell in cells:
            if cell.get("edge") == "1":
                lines.append(f"Flèche : {names.get(cell.get('source'), '?')} -> "
                             f"{names.get(cell.get('target'), '?')} {cell.get('value') or ''}".strip())
        return "\n".join(lines)[:MAX_CHARS]
    if path.suffix == ".excalidraw":
        elements = json.loads(text).get("elements", [])
        labels = {e.get("containerId"): " ".join((e.get("text") or "").split())
                  for e in elements if e.get("type") == "text"}
        lines = [f"Forme : {labels[e['id']]}" + (" (bordure en tirets)"
                 if e.get("strokeStyle") == "dashed" else "") for e in elements
                 if e.get("type") in ("rectangle", "ellipse", "diamond") and labels.get(e["id"])]
        lines += [f"Texte : {e.get('text')}" for e in elements
                  if e.get("type") == "text" and not e.get("containerId")]
        for e in elements:
            if e.get("type") == "arrow":
                start = labels.get((e.get("startBinding") or {}).get("elementId"), "?")
                end = labels.get((e.get("endBinding") or {}).get("elementId"), "?")
                lines.append(f"Flèche : {start} -> {end} {labels.get(e['id']) or ''}".strip())
        return "\n".join(lines)[:MAX_CHARS]
    if path.suffix in (".html", ".htm"):
        text = re.sub(r"<(style|script)\b.*?</\1>", "", text, flags=re.S | re.I)
        text = re.sub(r"data:[^\"')]+", "data:...", text)
    return text[:MAX_CHARS]


def lookup(data, path: str):
    for key in path.split(".") if path else []:
        data = data[int(key)] if isinstance(data, list) else data[key]
    return data


def run_checks(case: dict, folder: Path) -> list[dict]:
    """Contrôles sans modèle du cas : chacun {file, contains | matches | json + equals | min}."""
    results = []
    for check in case.get("checks", []):
        path = folder / check["file"]
        ok, detail = path.is_file(), ""
        if not ok:
            detail = "absent"
        elif "contains" in check or "matches" in check:
            text = path.read_text(encoding="utf-8", errors="replace")
            missing = [c for c in check.get("contains", []) if c.lower() not in text.lower()]
            if "matches" in check and not re.search(check["matches"], text, re.I | re.M):
                missing.append(check["matches"])
            ok, detail = not missing, "; ".join(f"« {m} » absent" for m in missing)
        elif "json" in check:
            try:
                value = lookup(json.loads(path.read_text(encoding="utf-8")), check["json"])
            except (ValueError, KeyError, IndexError, TypeError) as error:
                ok, detail = False, f"{check['json']} illisible ({error})"
            else:
                if "equals" in check:
                    ok, detail = value == check["equals"], f"{check['json']} = {value!r}"
                if "min" in check:
                    size = len(value) if isinstance(value, (list, dict, str)) else value
                    ok = ok and isinstance(size, (int, float)) and size >= check["min"]
                    detail = f"{check['json']} : {size}"
        results.append({"check": check, "ok": ok, "detail": detail})
    return results


def score_case(judge: Judge, case: dict, folder: Path) -> dict:
    """Note d'un cas : contrôles sans modèle, puis grille et fidélité si le juge est un modèle."""
    result = {"id": case["id"], "agent": case["agent"]}
    checks = run_checks(case, folder)
    passed, total = sum(c["ok"] for c in checks), len(checks)
    if checks:
        result["controles"] = checks
    output = folder / case["output"]
    ok = all(c["ok"] for c in checks)
    if judge.backend != "checks" and output.is_file():
        state = {"obtenu": readable(output)}
        questions = {f"r{i + 1}": {"type": "noul", "instructions": statement}
                     for i, statement in enumerate(case["rubric"])}
        if case.get("expected"):
            state["attendu"] = (TESTS / "expected" / case["expected"]).read_text(encoding="utf-8")
            questions["fidelite"] = {"type": "score", "criteria": FIDELITY_LEVELS, "instructions":
                                     "Quelle part du contenu du texte attendu se retrouve dans le texte obtenu ?"}
        answers = judge.ask(state, questions)
        grid = [{"affirmation": statement, "p": round(float(answers[f"r{i + 1}"]["noul"]), 3)}
                for i, statement in enumerate(case["rubric"])]
        result["grille"] = grid
        passed += sum(c["p"] >= RUBRIC_THRESHOLD for c in grid)
        total += len(grid)
        ok = ok and all(c["p"] >= RUBRIC_THRESHOLD for c in grid)
        if "fidelite" in answers:
            result["fidelite"] = round(float(answers["fidelite"]["score"]), 2)
            ok = ok and result["fidelite"] >= FIDELITY_MIN
    result["score"] = round(passed / total, 2) if total else None
    result["ok"] = ok and output.is_file()
    return result


def run_outputs(judge: Judge, folder: Path, only: set | None) -> int:
    cases = json.loads((TESTS / "agent-cases.json").read_text(encoding="utf-8"))["cases"]
    results, failed = [], False
    for case in cases:
        if only and case["id"] not in only:
            continue
        output = folder / case["output"]
        if not output.is_file():
            results.append({"id": case["id"], "ok": None, "detail": f"{case['output']} absent"})
            continue
        result = score_case(judge, case, folder)
        failed = failed or not result["ok"]
        results.append(result)
    judged = [r for r in results if r["ok"] is not None]
    print(json.dumps({"reussis": sum(bool(r["ok"]) for r in judged), "notes": len(judged),
                      "absents": [r["id"] for r in results if r["ok"] is None],
                      "resultats": results}, ensure_ascii=False, indent=2))
    return 1 if failed or not judged else 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=["laya", "decision1", "checks"], default="laya",
                        help="checks : contrôles sans modèle seulement")
    parser.add_argument("--model", help="avec decision1 : identifiant OpenRouter du modèle")
    sub = parser.add_subparsers(dest="mode", required=True)
    triggers = sub.add_parser("triggers", help="le bon skill se déclenche-t-il ?")
    triggers.add_argument("--min-accuracy", type=float, default=0.8)
    outputs = sub.add_parser("outputs", help="noter les fichiers produits par les agents")
    outputs.add_argument("folder", type=Path, help="dossier de travail de l'agent")
    outputs.add_argument("--only", help="identifiants des cas, séparés par des virgules")
    args = parser.parse_args()

    judge = Judge(args.backend, args.model)
    if args.mode == "triggers":
        return run_triggers(judge, args.min_accuracy)
    return run_outputs(judge, args.folder.resolve(), set(args.only.split(",")) if args.only else None)


if __name__ == "__main__":
    sys.exit(main())
