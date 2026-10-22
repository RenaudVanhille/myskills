# /// script
# requires-python = ">=3.10"
# ///
"""Lance les cas de test des scripts (tests/cases.json) et affiche un bilan.

Sans modèle ni service en ligne : chaque cas lance les scripts des skills sur
les documents de tests/fixtures/ et vérifie codes de sortie, rapports JSON,
fichiers produits et, si un résultat attendu existe, sa ressemblance avec
tests/expected/. Chaque rapport JSON doit aussi contenir les champs annoncés
dans la section « Contrat » du SKILL.md, et le cas `contrats` vérifie que
chaque script, chaque agent et CATALOG.md sont documentés. Les cas marqués `slow` (gros téléchargements au premier
lancement) ne tournent qu'avec --slow.

Usage :
    uv run tests/run.py [--only ID[,ID]] [--slow] [--keep] [--json]
"""

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
TOKENS = {"{skills}": str(ROOT / "skills"), "{samples}": str(TESTS / "fixtures" / "samples"),
          "{fixtures}": str(TESTS / "fixtures")}
# Ressemblance minimale (0 à 1) entre un fichier produit et son attendu.
MIN_RATIO = 0.9
# Ligne de contrat d'un SKILL.md : - **Rapport `script.py`** (...) : `champ`, ... ; ...
REPORT_LINE = re.compile(r"^- \*\*Rapport `([\w.]+)`\*\*([^:]*):(.*)$", re.M)
MAINTENANCE_LINE = re.compile(r"^- \*\*Maintenance\*\* : `([\w.]+)`", re.M)


def contracts() -> dict:
    """Champs obligatoires du rapport de chaque script, d'après les SKILL.md.

    None pour un script documenté sans rapport JSON (texte, maintenance)."""
    found = {}
    for path in (ROOT / "skills").glob("*/SKILL.md"):
        text = path.read_text(encoding="utf-8")
        for script, kind, fields in REPORT_LINE.findall(text):
            required = fields.split(" ; ")[0]
            found[script] = None if "pas de JSON" in kind else re.findall(r"`(\w+)`", required)
        for script in MAINTENANCE_LINE.findall(text):
            found[script] = None
    return found


CONTRACTS = contracts()


def expand(value: str, out: Path) -> str:
    for token, path in {**TOKENS, "{out}": str(out)}.items():
        value = value.replace(token, path)
    return value


def runner() -> list[str]:
    return ["uv", "run", "--quiet"] if shutil.which("uv") else [sys.executable]


def lookup(data, dotted: str):
    for part in dotted.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def run_step(step: dict, out: Path, failures: list[str]) -> None:
    script = expand(step["script"], out)
    command = runner() + [script] + [expand(arg, out) for arg in step.get("args", [])]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    name = Path(script).name
    if result.returncode != step.get("exit", 0):
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or [""]
        failures.append(f"{name} : code {result.returncode} au lieu de {step.get('exit', 0)} "
                        f"({tail[0][:200]})")
    fields = CONTRACTS.get(name)
    if not (step.get("report") or step.get("report_contains") or fields):
        return
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        failures.append(f"{name} : rapport JSON illisible")
        return
    for item in report if isinstance(report, list) else [report]:
        if isinstance(item, dict) and not item.get("error"):
            missing = [field for field in fields or [] if field not in item]
            if missing:
                failures.append(f"{name} : champs du contrat absents du rapport : {', '.join(missing)}")
    for key, wanted in step.get("report", {}).items():
        try:
            got = lookup(report, key)
        except (KeyError, IndexError, TypeError):
            failures.append(f"{name} : {key} absent du rapport")
            continue
        if got != wanted:
            failures.append(f"{name} : {key} = {got!r}, attendu {wanted!r}")
    for key, text in step.get("report_contains", {}).items():
        try:
            got = lookup(report, key)
        except (KeyError, IndexError, TypeError):
            failures.append(f"{name} : {key} absent du rapport")
            continue
        if text not in json.dumps(got, ensure_ascii=False):
            failures.append(f"{name} : {key} ne contient pas « {text} »")


def check_outputs(case: dict, out: Path, failures: list[str]) -> None:
    for rel in case.get("files", []):
        if not (out / rel).exists():
            failures.append(f"fichier manquant : {rel}")
    for rel in case.get("absent", []):
        if (out / rel).exists():
            failures.append(f"fichier qui aurait dû disparaître : {rel}")
    for rel, texts in case.get("contains", {}).items():
        path = out / rel
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        failures += [f"{rel} ne contient pas « {text} »" for text in texts if text not in content]
    for rel, expected in case.get("expected", {}).items():
        path = out / rel
        if not path.exists():
            continue
        got = path.read_text(encoding="utf-8").strip()
        want = (TESTS / "expected" / expected).read_text(encoding="utf-8").strip()
        ratio = difflib.SequenceMatcher(None, got, want).ratio()
        if ratio < MIN_RATIO:
            failures.append(f"{rel} ressemble à {ratio:.0%} à expected/{expected} "
                            f"(minimum {MIN_RATIO:.0%})")


def check_contracts() -> dict:
    """Chaque script, chaque agent et le catalogue sont documentés."""
    failures = []
    for script in sorted((ROOT / "skills").glob("*/scripts/*.py")):
        if script.name not in CONTRACTS:
            failures.append(f"{script.parent.parent.name}/{script.name} absent de la section Contrat")
    for skill in sorted((ROOT / "skills").glob("*/SKILL.md")):
        if "\n## Contrat\n" not in skill.read_text(encoding="utf-8"):
            failures.append(f"{skill.parent.name} : pas de section Contrat")
    for agent in sorted((ROOT / "src" / "agents").glob("*.md")):
        if "\n## Contrat\n" not in agent.read_text(encoding="utf-8"):
            failures.append(f"agent {agent.stem} : pas de section Contrat")
    sys.path.insert(0, str(ROOT / "scripts"))
    from build import build_catalog

    catalog = ROOT / "CATALOG.md"
    if not catalog.exists() or catalog.read_text(encoding="utf-8") != build_catalog():
        failures.append("CATALOG.md n'est pas à jour : lancez uv run scripts/build.py")
    return {"id": "contrats", "skill": "tous", "ok": not failures, "failures": failures, "out": None}


def run_case(case: dict, keep: bool) -> dict:
    out = Path(tempfile.mkdtemp(prefix=f"myskills-{case['id']}-"))
    failures: list[str] = []
    try:
        for step in case["steps"]:
            run_step(step, out, failures)
        check_outputs(case, out, failures)
    finally:
        if not keep:
            shutil.rmtree(out, ignore_errors=True)
    return {"id": case["id"], "skill": case["skill"], "ok": not failures,
            "failures": failures, "out": str(out) if keep else None}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="identifiants des cas, séparés par des virgules")
    parser.add_argument("--slow", action="store_true", help="lancer aussi les cas lents")
    parser.add_argument("--keep", action="store_true", help="garder les dossiers de sortie")
    parser.add_argument("--json", action="store_true", help="rapport JSON au lieu du bilan")
    args = parser.parse_args()

    cases = json.loads((TESTS / "cases.json").read_text(encoding="utf-8"))["cases"]
    only = set(args.only.split(",")) if args.only else None
    results, skipped = [], []
    if not only or "contrats" in only:
        results.append(check_contracts())
        if not args.json:
            print(f"{'OK  ' if results[-1]['ok'] else 'ÉCHEC'} contrats (tous)", flush=True)
            for failure in results[-1]["failures"]:
                print(f"      - {failure}")
    for case in cases:
        if only and case["id"] not in only:
            continue
        if case.get("slow") and not args.slow and not only:
            skipped.append(case["id"])
            continue
        results.append(run_case(case, args.keep))
        if not args.json:
            mark = "OK  " if results[-1]["ok"] else "ÉCHEC"
            print(f"{mark} {case['id']} ({case['skill']})", flush=True)
            for failure in results[-1]["failures"]:
                print(f"      - {failure}")
            if results[-1]["out"]:
                print(f"      sortie : {results[-1]['out']}")

    passed = sum(r["ok"] for r in results)
    if args.json:
        print(json.dumps({"results": results, "skipped": skipped}, ensure_ascii=False, indent=2))
    else:
        print(f"\n{passed}/{len(results)} cas réussis"
              + (f", {len(skipped)} lents ignorés (--slow) : {', '.join(skipped)}" if skipped else ""))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
