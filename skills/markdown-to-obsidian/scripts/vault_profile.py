# /// script
# requires-python = ">=3.10"
# ///
"""Résume un vault Obsidian pour classer et taguer une nouvelle note.

Lit toutes les notes du vault (sans les modifier) et affiche un rapport JSON :
- tags : tags existants (frontmatter et #tags dans le texte), du plus utilisé
  au moins utilisé ;
- folders : dossiers de notes avec leur nombre de notes et leurs tags les plus
  fréquents ;
- attachments : dossier des pièces jointes réglé dans `.obsidian/app.json`.

Usage :
    uv run scripts/vault_profile.py VAULT [--top 50]
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

SKIP_DIRS = {".obsidian", ".trash", ".git", ".myskills-tmp", "node_modules"}
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---\n", re.S)
INLINE_TAG = re.compile(r"(?<![\w&/#])#([A-Za-zÀ-ÿ][\w\-/À-ÿ]*)")
CODE = re.compile(r"```.*?```|`[^`\n]*`", re.S)


def frontmatter_tags(block: str) -> list[str]:
    tags, in_list = [], False
    for line in block.split("\n"):
        match = re.match(r"^(tags|tag)\s*:\s*(.*)$", line)
        if match:
            value = match.group(2).strip()
            in_list = not value
            if value:
                tags += [t for t in re.split(r"[,\s]+", value.strip("[]")) if t]
            continue
        if in_list:
            item = re.match(r"^\s*-\s*(.+)$", line)
            if item:
                tags.append(item.group(1))
            elif line.strip():
                in_list = False
    return [t.strip("'\"").lstrip("#") for t in tags if t.strip("'\"")]


def note_tags(text: str) -> list[str]:
    tags = []
    match = FRONTMATTER.match(text.replace("\r\n", "\n"))
    if match:
        tags += frontmatter_tags(match.group(1))
        text = text[match.end():]
    tags += INLINE_TAG.findall(CODE.sub("", text))
    return [t.lower() for t in tags]


def attachments_folder(vault: Path) -> str | None:
    try:
        settings = json.loads((vault / ".obsidian" / "app.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return settings.get("attachmentFolderPath")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("vault", type=Path)
    parser.add_argument("--top", type=int, default=50, help="nombre de tags listés (défaut : 50)")
    args = parser.parse_args()
    vault = args.vault.resolve()
    if not vault.is_dir():
        print(json.dumps({"error": f"Vault introuvable : {vault}"}, ensure_ascii=False))
        return 2

    tags, folders = Counter(), {}
    notes = 0
    for path in sorted(vault.rglob("*.md")):
        relative = path.relative_to(vault)
        if any(part in SKIP_DIRS for part in relative.parts[:-1]):
            continue
        notes += 1
        found = note_tags(path.read_text(encoding="utf-8", errors="replace"))
        tags.update(found)
        folder = relative.parent.as_posix() if relative.parent != Path(".") else ""
        entry = folders.setdefault(folder, {"notes": 0, "tags": Counter()})
        entry["notes"] += 1
        entry["tags"].update(found)

    report = {
        "vault": str(vault),
        "notes": notes,
        "tags": dict(tags.most_common(args.top)),
        "folders": {
            name or ".": {"notes": e["notes"], "top_tags": [t for t, _ in e["tags"].most_common(5)]}
            for name, e in sorted(folders.items())
        },
        "attachments": attachments_folder(vault),
    }
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
