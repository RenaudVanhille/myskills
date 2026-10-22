# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie les outils dont les skills de myskills ont besoin (Windows, macOS,
Linux).

Usage : python scripts/doctor.py [extraction|schemas|publication|tout]
Code de sortie : 0 si tout est présent, 1 sinon.
"""

import importlib.util
import os
import shutil
import sys
from pathlib import Path

DRAWIO_PATHS = [
    Path("/Applications/draw.io.app/Contents/MacOS/draw.io"),
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "draw.io" / "draw.io.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "draw.io" / "draw.io.exe",
]

GROUPS = {
    "extraction": [
        ("MarkItDown", "cmd", "markitdown", 'uv tool install "markitdown[all]"'),
        ("Docling", "cmd", "docling", "uv tool install docling"),
    ],
    "schemas": [
        ("draw.io Desktop", "drawio", None, "https://github.com/jgraph/drawio-desktop/releases"),
        ("Node.js", "cmd", "node", "https://nodejs.org/"),
        ("Mermaid CLI", "cmd", "mmdc", "npm install -g @mermaid-js/mermaid-cli"),
        ("LikeC4", "cmd", "likec4", "npm install -g likec4"),
        ("Playwright", "cmd_or_module", "playwright",
         "uv tool install playwright, puis : playwright install chromium"),
    ],
    "publication": [
        ("Pandoc", "cmd", "pandoc", "https://pandoc.org/installing.html"),
    ],
}

TITLES = {"extraction": "Extraction documentaire", "schemas": "Schémas",
          "publication": "Publication"}


def present(kind: str, target: str | None) -> bool:
    if kind == "cmd":
        return shutil.which(target) is not None
    if kind == "module":
        return importlib.util.find_spec(target) is not None
    if kind == "cmd_or_module":
        return present("cmd", target) or present("module", target)
    if kind == "drawio":
        return shutil.which("drawio") is not None or any(p.is_file() for p in DRAWIO_PATHS)
    raise ValueError(kind)


def main() -> int:
    group = sys.argv[1] if len(sys.argv) > 1 else "tout"
    if group != "tout" and group not in GROUPS:
        print(f"Groupe inconnu : {group} (extraction, schemas, publication, tout)")
        return 2
    missing = False
    for name in GROUPS if group == "tout" else [group]:
        print(TITLES[name])
        for label, kind, target, hint in GROUPS[name]:
            if present(kind, target):
                print(f"  [ok]       {label}")
            else:
                print(f"  [manquant] {label} -> {hint}")
                missing = True
    print("Des outils manquent (voir ci-dessus)." if missing else "Tout est prêt.")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
