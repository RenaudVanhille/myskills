# /// script
# requires-python = ">=3.10"
# ///
"""Met un fichier Markdown au format Obsidian.

- ajoute un frontmatter (title, source, created, tags) s'il n'y en a pas ;
- transforme les images locales en embeds `![[nom.png]]` ;
- transforme les liens vers d'autres .md en wikilinks `[[note|texte]]` ;
- transforme les citations « Note : », « Attention : »... en callouts ;
- avec --vault, copie la note dans le vault et ses images dans le dossier
  de pièces jointes du vault ; avec --move en plus, supprime ensuite la
  note et les images d'origine (et leurs dossiers devenus vides).

Affiche un rapport JSON. Usage :
    uv run scripts/obsidianize.py NOTE.md [...] [--vault DOSSIER] [--folder SOUS-DOSSIER]
        [--attachments attachments] [--source NOM] [--tags a,b] [--move]
"""

import argparse
import datetime
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import unquote

IMAGE = re.compile(r"!\[([^\]]*)\]\(([^)\s]+)\)")
MD_LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+\.md)(#[^)]*)?\)")
H1 = re.compile(r"^#\s+(.+)$", re.M)
# Mot-clé en tête de citation -> type de callout Obsidian.
CALLOUTS = {
    "note": "note", "remarque": "note", "info": "info", "information": "info",
    "astuce": "tip", "conseil": "tip", "tip": "tip",
    "important": "important", "attention": "warning", "avertissement": "warning",
    "warning": "warning", "danger": "danger", "exemple": "example", "example": "example",
}
QUOTE_KEYWORD = re.compile(r"^>\s*\**(" + "|".join(CALLOUTS) + r")\**\s*:\s*(.*)$", re.I)


def yaml_string(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def frontmatter(text: str, path: Path, source: str | None, tags: list[str]) -> str:
    if text.startswith("---\n"):
        return text
    match = H1.search(text)
    title = match.group(1).strip() if match else path.stem
    lines = ["---", f"title: {yaml_string(title)}"]
    if source:
        lines.append(f"source: {yaml_string(source)}")
    lines.append(f"created: {datetime.date.today().isoformat()}")
    if tags:
        lines.append("tags:")
        lines += [f"  - {tag}" for tag in tags]
    lines.append("---")
    return "\n".join(lines) + "\n\n" + text.lstrip()


def callouts(text: str) -> tuple[str, int]:
    out, count = [], 0
    for line in text.split("\n"):
        match = QUOTE_KEYWORD.match(line)
        if match:
            kind = CALLOUTS[match.group(1).lower()]
            out.append(f"> [!{kind}]")
            body = match.group(2).strip()
            if body:
                out.append(f"> {body[0].upper()}{body[1:]}")
            count += 1
        else:
            out.append(line)
    return "\n".join(out), count


def process(path: Path, args) -> dict:
    text = path.read_text(encoding="utf-8")
    report = {"input": str(path), "output": None, "embeds": 0, "wikilinks": 0,
              "callouts": 0, "attachments_copied": 0, "missing": []}
    images: list[Path] = []

    def embed(match: re.Match) -> str:
        alt, target = match.groups()
        if re.match(r"^[a-z]+:", target):
            return match.group(0)
        local = (path.parent / unquote(target)).resolve()
        if not local.exists():
            report["missing"].append(target)
        images.append(local)
        report["embeds"] += 1
        name = local.name
        return f"![[{name}]]" if not alt or alt == name else f"![[{name}|{alt}]]"

    def wikilink(match: re.Match) -> str:
        label, target, anchor = match.group(1), match.group(2), match.group(3) or ""
        if re.match(r"^[a-z]+:", target):
            return match.group(0)
        report["wikilinks"] += 1
        note = Path(unquote(target)).stem + anchor
        return f"[[{note}]]" if label == Path(target).stem else f"[[{note}|{label}]]"

    text = IMAGE.sub(embed, text)
    text = MD_LINK.sub(wikilink, text)
    text, report["callouts"] = callouts(text)
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    text = frontmatter(text, path, args.source, tags)

    if args.vault:
        note_dir = args.vault / (args.folder or "")
        attach_dir = args.vault / args.attachments
        target = note_dir / path.name
        for image in images:
            if image.exists():
                attach_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(image, attach_dir / image.name)
                report["attachments_copied"] += 1
    else:
        target = path
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.rstrip() + "\n")
    report["output"] = str(target)
    if args.vault and args.move and target.resolve() != path:
        for image in images:
            if image.exists() and image.parent.resolve() != (args.vault / args.attachments).resolve():
                image.unlink()
                remove_if_empty(image.parent)
        path.unlink()
        remove_if_empty(path.parent)
    return report


def remove_if_empty(folder: Path) -> None:
    try:
        folder.rmdir()
    except OSError:
        pass


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--vault", type=Path, help="vault Obsidian de destination")
    parser.add_argument("--folder", help="sous-dossier du vault pour les notes")
    parser.add_argument("--attachments", default="attachments",
                        help="dossier des pièces jointes dans le vault (défaut : attachments)")
    parser.add_argument("--source", help="nom du document d'origine, pour le frontmatter")
    parser.add_argument("--tags", help="tags séparés par des virgules")
    parser.add_argument("--move", action="store_true",
                        help="avec --vault : supprimer la note et les images d'origine")
    args = parser.parse_args()
    if args.vault:
        args.vault = args.vault.resolve()

    reports, failed = [], False
    for path in args.files:
        if not path.is_file():
            reports.append({"input": str(path), "error": "Fichier introuvable"})
            failed = True
            continue
        reports.append(process(path.resolve(), args))
        failed = failed or bool(reports[-1]["missing"])
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
