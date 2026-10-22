# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie un fichier Markdown issu d'une conversion.

Erreurs (code de sortie 1) : fichier vide, image ou lien local introuvable,
tableau mal formé, image restée en base64.
Avertissements : aucun titre, saut de niveau de titre, en-tête de tableau
vide, contenu à transcrire par vision, frontmatter absent (avec --obsidian).

Usage : uv run scripts/validate.py FICHIER.md [...] [--obsidian]
"""

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote

LINK = re.compile(r"!?\[[^\]]*\]\(([^)\s]+)(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+\S")
FENCE = re.compile(r"^(```|~~~)")


def cells(line: str) -> list[str]:
    return line.strip().strip("|").split("|")


def check(path: Path, obsidian: bool) -> dict:
    errors, warnings = [], []
    text = path.read_text(encoding="utf-8")
    lines = text.split("\n")

    if len(text.strip()) < 20:
        errors.append("Fichier vide ou presque vide.")
    if "data:image/" in text:
        errors.append("Image restée en base64 : à extraire dans attachments/.")
    if "<!-- vision" in text:
        warnings.append("Contenu à transcrire par vision (marqueur <!-- vision -->).")
    if obsidian and not text.startswith("---\n"):
        warnings.append("Frontmatter absent (attendu pour Obsidian).")

    in_code, level, has_heading, i = False, 0, False, 0
    while i < len(lines):
        line = lines[i]
        number = i + 1
        if FENCE.match(line.strip()):
            in_code = not in_code
        if in_code:
            i += 1
            continue

        match = HEADING.match(line)
        if match:
            new = len(match.group(1))
            if has_heading and new > level + 1:
                warnings.append(f"Ligne {number} : saut de titre H{level} vers H{new}.")
            has_heading, level = True, new

        for target in LINK.findall(line):
            if re.match(r"^[a-z]+:", target) or target.startswith("#"):
                continue
            local = (path.parent / unquote(target.split("#")[0])).resolve()
            if not local.exists():
                errors.append(f"Ligne {number} : cible introuvable : {target}")

        if line.strip().startswith("|"):
            start = i
            block = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            width = len(cells(block[0]))
            if len(block) < 2 or not set(block[1].replace("|", "").strip()) <= {"-", ":", " "}:
                errors.append(f"Ligne {start + 1} : tableau sans ligne de séparation.")
            for offset, row in enumerate(block):
                if len(cells(row)) != width:
                    errors.append(f"Ligne {start + offset + 1} : {len(cells(row))} colonnes au lieu de {width}.")
            if not "".join(cells(block[0])).strip():
                warnings.append(f"Ligne {start + 1} : en-tête de tableau vide.")
            continue
        i += 1

    if not has_heading:
        warnings.append("Aucun titre : structurer le document avec # et ##.")
    return {"file": str(path), "ok": not errors, "errors": errors, "warnings": warnings}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--obsidian", action="store_true", help="vérifie aussi le frontmatter")
    args = parser.parse_args()
    results = [check(p, args.obsidian) if p.is_file()
               else {"file": str(p), "ok": False, "errors": ["Fichier introuvable."], "warnings": []}
               for p in args.files]
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
