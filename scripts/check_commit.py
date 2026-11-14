# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie qu'un titre de PR ou un message de commit suit Conventional Commits.

release-please lit les titres des commits de main (un par PR, fusion en
squash) pour choisir la version suivante et écrire CHANGELOG.md : un titre
hors convention est ignoré, et sa modification n'apparaît pas au journal.

Usage :
    uv run scripts/check_commit.py "feat(cloud-architecture): vue des coûts"
    uv run scripts/check_commit.py --file .git/COMMIT_EDITMSG
    uv run scripts/check_commit.py --schema

Forme : `type(portée)!: description`. La portée (facultative) est un nom en
minuscules avec tirets, en général le skill ou l'agent touché ; `!` ou un pied
`BREAKING CHANGE:` marque une rupture. Rapport JSON sur la sortie standard
(shared/schemas/commit-report.schema.json) : type, portée, rupture et
montée de version induite (`bump`), avec `errors` et `warnings`.

Codes de sortie : 0 titre conforme, 1 titre non conforme ou fichier illisible.
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Type : montée de version induite (une rupture monte la version majeure).
TYPES = {
    "feat": "minor", "fix": "patch", "perf": "patch", "revert": "patch",
    "docs": "none", "refactor": "none", "test": "none", "ci": "none",
    "build": "none", "chore": "none", "style": "none",
}
HEADER = re.compile(r"^(?P<type>[A-Za-z]+)(?:\((?P<scope>[^()]*)\))?(?P<bang>!)?: (?P<desc>.*)$")
SCOPE = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")
MAX_HEADER = 100


def check(message: str) -> dict:
    lines = message.replace("\r\n", "\n").split("\n")
    header = lines[0].strip()
    report = {"title": header, "type": None, "scope": None, "breaking": False, "bump": "none",
              "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]
    if not header:
        errors.append("titre vide : attendu « type(portée): description », par exemple « feat: vue des coûts »")
        return report
    if header.startswith('Revert "'):
        warnings.append("titre de retour en arrière de GitHub : préférez « revert: <titre d'origine> »")
        report.update(type="revert", bump="patch")
        return report
    match = HEADER.match(header)
    if not match:
        hint = "type(portée): description, avec deux-points puis une espace"
        guess = re.match(r"^([A-Za-z]+)", header)
        if guess and guess.group(1).lower() in TYPES:
            hint += f" (« {guess.group(1).lower()}: ... » ?)"
        errors.append(f"titre « {header} » : forme attendue {hint} ; types : {', '.join(TYPES)}")
        return report
    kind, scope, desc = match["type"], match["scope"], match["desc"].strip()
    if kind not in TYPES:
        close = difflib.get_close_matches(kind.lower(), TYPES, n=1)
        suggestion = f" ({close[0]} ?)" if close else ""
        errors.append(f"type « {kind} » inconnu{suggestion} ; types : {', '.join(TYPES)}")
    if scope is not None and not SCOPE.match(scope):
        errors.append(f"portée « {scope} » : nom en minuscules avec tirets attendu (skill ou agent touché)")
    if not desc:
        errors.append("description vide après « : »")
    elif desc.endswith("."):
        warnings.append("description terminée par un point : à retirer")
    if len(header) > MAX_HEADER:
        warnings.append(f"titre de {len(header)} caractères : {MAX_HEADER} au plus, le détail va dans le corps")
    body = "\n".join(lines[1:])
    breaking = bool(match["bang"]) or bool(re.search(r"^BREAKING[ -]CHANGE: \S", body, re.M))
    report.update(type=kind, scope=scope, breaking=breaking)
    if not errors:
        report["bump"] = "major" if breaking else TYPES[kind]
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Vérifie un titre de PR ou un message de commit (Conventional Commits).")
    parser.add_argument("title", nargs="?", help="titre de PR ou première ligne du commit")
    parser.add_argument("--file", type=Path, help="fichier du message de commit (crochet commit-msg)")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma du rapport et s'arrête")
    args = parser.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.schema:
        schema = json.loads((ROOT / "shared" / "schemas" / "commit-report.schema.json").read_text(encoding="utf-8"))
        print(json.dumps(schema, ensure_ascii=False, separators=(",", ":")))
        return 0
    if args.file:
        try:
            text = args.file.read_text(encoding="utf-8")
        except OSError as error:
            report = {"title": "", "type": None, "scope": None, "breaking": False, "bump": "none",
                      "errors": [f"{args.file} illisible : {error.strerror}"], "warnings": []}
            print(json.dumps(report, ensure_ascii=False))
            return 1
        # Lignes de commentaire de git retirées.
        message = "\n".join(line for line in text.splitlines() if not line.startswith("#"))
    else:
        message = args.title or ""
    report = check(message)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
