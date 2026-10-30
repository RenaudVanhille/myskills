# /// script
# requires-python = ">=3.10"
# ///
"""Marque « généré par IA » les fichiers qu'un agent a écrits lui-même (AI Act, art. 50).

Les scripts des skills marquent déjà leurs livrables ; cette commande sert aux
fichiers que le modèle écrit sans script (note, page, code). Jamais sur un
fichier fourni par l'utilisateur. La marque est cachée et propre au format
(frontmatter, meta HTML, commentaire, chunk PNG, propriétés Office) :
voir scripts/lib/ai_mark.py. --check vérifie sans rien écrire.

    uv run scripts/mark_generated.py FICHIER... [--check]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="fichiers générés à marquer")
    parser.add_argument("--check", action="store_true", help="vérifier la marque sans écrire")
    args = parser.parse_args()

    report = {"marked": 0, "already": 0, "unmarked": [], "errors": [], "warnings": []}
    for path in args.files:
        if not path.is_file():
            report["errors"].append(f"{path} : fichier introuvable")
        elif not ai_mark.supported(path):
            report["warnings"].append(f"{path.name} : format {path.suffix or 'sans extension'} sans marque possible")
        elif ai_mark.is_marked(path):
            report["already"] += 1
        elif args.check:
            report["unmarked"].append(str(path))
        else:
            try:
                ai_mark.mark(path)
            except (OSError, UnicodeDecodeError, KeyError, ValueError) as error:
                report["errors"].append(f"{path.name} : marque impossible ({error})")
                continue
            # Sortie vérifiée : la marque est relue dans le fichier écrit.
            if ai_mark.is_marked(path):
                report["marked"] += 1
            else:
                report["errors"].append(f"{path.name} : marque absente à la relecture (fichier illisible ?)")
    report["errors"] += [f"{p} : sans marque « généré par IA »" for p in report["unmarked"]]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
