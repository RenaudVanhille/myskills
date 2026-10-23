# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie les outils locaux dont les skills de myskills ont besoin (Windows,
macOS, Linux) et affiche un rapport JSON.

MarkItDown, Pandoc et Playwright sont fournis par uv aux scripts qui les
utilisent (dépendances PEP 723), Docling par `uvx` : seul uv est alors
obligatoire, leur installation à part est facultative.

Usage : uv run scripts/doctor.py [extraction|schemas|publication|tout]
Code de sortie : 0 si tous les outils obligatoires sont présents, 1 sinon
(ou groupe inconnu).
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import local_tools  # noqa: E402

UV = ("uv", "obligatoire", lambda: shutil.which("uv") is not None, "https://docs.astral.sh/uv/")
# (outil, obligatoire ou facultatif, test, commande ou page d'installation)
GROUPS = {
    "extraction": [
        UV,
        ("MarkItDown installé à part (sinon fourni par uv)", "facultatif",
         lambda: shutil.which("markitdown") is not None, 'uv tool install "markitdown[all]"'),
        ("Docling installé à part (sinon lancé par uvx, ~2 Go au premier lancement)", "facultatif",
         lambda: shutil.which("docling") is not None, "uv tool install docling"),
    ],
    "schemas": [
        UV,
        ("draw.io Desktop", "obligatoire", lambda: local_tools.drawio_binary() is not None,
         "https://github.com/jgraph/drawio-desktop/releases"),
        ("Navigateur pour Playwright (Edge, Chrome ou Chromium)", "obligatoire", local_tools.browser_available,
         "uvx playwright install chromium"),
        ("Node.js (LikeC4 via npx)", "facultatif", lambda: shutil.which("node") is not None, "https://nodejs.org/"),
        ("LikeC4 installé (plus rapide que npx)", "facultatif", lambda: shutil.which("likec4") is not None,
         "npm install -g likec4"),
    ],
    "publication": [
        UV,
        ("LibreOffice (PDF et relecture visuelle des .docx)", "facultatif",
         lambda: local_tools.soffice_binary() is not None, "https://www.libreoffice.org/download/"),
    ],
}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    group = sys.argv[1] if len(sys.argv) > 1 else "tout"
    if group != "tout" and group not in GROUPS:
        print(json.dumps({"group": group, "tools": [], "missing": [],
                          "errors": [f"groupe inconnu « {group} » (extraction, schemas, publication, tout)"],
                          "warnings": []}, ensure_ascii=False))
        return 1
    tools, seen = [], set()
    for name in GROUPS if group == "tout" else [group]:
        for label, need, test, install in GROUPS[name]:
            if label in seen:
                continue
            seen.add(label)
            status = "ok" if test() else ("manquant" if need == "obligatoire" else "absent")
            tools.append({"name": label, "group": name, "status": status,
                          **({"install": install} if status != "ok" else {})})
    missing = [t["name"] for t in tools if t["status"] == "manquant"]
    report = {"group": group, "tools": tools, "missing": missing,
              "errors": [f"{t['name']} manquant : {t['install']}" for t in tools if t["status"] == "manquant"],
              "warnings": [f"{t['name']} absent (facultatif) : {t['install']}" for t in tools
                           if t["status"] == "absent"]}
    print(json.dumps(report, ensure_ascii=False))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
