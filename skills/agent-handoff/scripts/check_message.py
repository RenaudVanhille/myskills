# /// script
# requires-python = ">=3.10"
# ///
"""Valide un message de passage entre agents ou le rapport final d'un agent.

Contrôle le message contre son schéma (handoff.schema.json ou
agent-report.schema.json, copiés de shared/schemas/), puis vérifie que
chaque fichier cité existe. Dans le dossier d'un workflow (workflow.json),
le note au journal par le skill decision-log. Le rapport est court : un
autre agent ou le modèle n'a qu'à lire `errors`.

    uv run scripts/check_message.py handoff|report DOSSIER --json '{...}' | --file MESSAGE.json
"""

import argparse
import json
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent / "lib"
sys.path.insert(0, str(LIB))
import ai_mark  # noqa: E402
from skill_paths import absent, load_module  # noqa: E402
from spec_schema import check  # noqa: E402


def schema(kind: str) -> dict:
    handoff = json.loads((LIB / "handoff.schema.json").read_text(encoding="utf-8"))
    if kind == "handoff":
        return handoff
    report = json.loads((LIB / "agent-report.schema.json").read_text(encoding="utf-8"))
    report["$defs"] = {"handoff.schema.json": handoff}
    return report


def errors_of(kind: str, message, folder: Path) -> list[str]:
    """Erreurs de schéma, puis fichiers cités introuvables (relatifs au dossier ou absolus)."""
    errors = check(message, schema(kind))
    if errors or not isinstance(message, dict):
        return errors
    files = list(message["files"])
    if kind == "report" and message.get("next"):
        files += message["next"]["files"]
    return [f"files : {f} introuvable" for f in dict.fromkeys(files)
            if not (Path(f).exists() or (folder / f).exists())]


def unmarked(files: list[str], folder: Path) -> list[str]:
    """Fichiers livrés sans la marque « généré par IA » de leur format (AI Act, art. 50)."""
    found = [Path(f) if Path(f).exists() else folder / f for f in files]
    return [f"files : {p.name} sans marque « généré par IA » ; s'il est généré (pas fourni par "
            f"l'utilisateur) : mark_generated.py {p}" for p in found
            if p.is_file() and ai_mark.supported(p) and not ai_mark.is_marked(p)]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("kind", choices=["handoff", "report"], help="message de passage ou rapport final")
    parser.add_argument("folder", type=Path, help="dossier de travail (ou du workflow)")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--file", type=Path, help="message en JSON")
    source.add_argument("--json", help="message en JSON sur une ligne")
    args = parser.parse_args()

    report = {"kind": args.kind, "agent": None, "workflow": None, "entry": None, "errors": [], "warnings": []}
    try:
        message = json.loads(args.file.read_text(encoding="utf-8") if args.file else args.json)
    except (OSError, ValueError) as error:
        report["errors"].append(f"message illisible ({error})")
        message = None
    if message is not None:
        report["errors"] += errors_of(args.kind, message, args.folder)
        if isinstance(message, dict) and isinstance(message.get("agent"), str):
            report["agent"] = message["agent"]
        if args.kind == "report" and not report["errors"]:
            report["warnings"] += unmarked(message["files"], args.folder)
    # Hors d'un dossier de workflow, rien à tracer : la validation suffit.
    if not report["errors"] and (args.folder / "workflow.json").is_file():
        journal = load_module("decision-log", "journal.py")
        if journal is None:
            report["warnings"].append("message valide, non tracé : " + absent("decision-log", "journal.py"))
        else:
            traced = journal.trace(args.folder, args.kind, message)
            report.update(workflow=str(args.folder / "workflow.json"), entry=traced["entry"])
            report["errors"] += traced["errors"]
            report["warnings"] += traced["warnings"]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
