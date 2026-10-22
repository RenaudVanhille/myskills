# /// script
# requires-python = ">=3.10"
# ///
"""Met un fichier Markdown au format Obsidian.

- ajoute un frontmatter (title, source, created, tags) s'il n'y en a pas ;
  avec --classify, y ajoute aussi `type` et `domaine`, devinés en local par
  le modèle Laya (script classify.py du skill doc-to-markdown) ;
- transforme les images locales en embeds `![[nom.png]]` ;
- transforme les liens vers d'autres .md en wikilinks `[[note|texte]]` ;
- transforme les citations « Note : », « Attention : »... en callouts ;
- avec --vault, copie la note dans le vault et ses images dans le dossier
  de pièces jointes du vault ; avec --move en plus, supprime ensuite la
  note et les images d'origine (et leurs dossiers devenus vides) ;
- vérifie la note produite comme `validate.py --obsidian` du skill
  doc-to-markdown : le résultat est dans `validation` du rapport.

Affiche un rapport JSON. Usage :
    uv run scripts/obsidianize.py NOTE.md [...] [--vault DOSSIER] [--folder SOUS-DOSSIER]
        [--attachments attachments] [--source NOM] [--tags a,b] [--move]
        [--classify [--domains a,b]]
"""

import argparse
import datetime
import importlib.util
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote

CLASSIFY = Path(__file__).resolve().parents[2] / "doc-to-markdown" / "scripts" / "classify.py"
VALIDATE = CLASSIFY.with_name("validate.py")
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


def run_classifier(files: list[Path], domains: str | None) -> tuple[dict, str | None]:
    """Lance classify.py dans son propre environnement (dépendances lourdes)."""
    if not CLASSIFY.is_file():
        return {}, f"Classification impossible : {CLASSIFY} introuvable"
    command = (["uv", "run", "--quiet", str(CLASSIFY)] if shutil.which("uv")
               else [sys.executable, str(CLASSIFY)])
    command += [str(f) for f in files] + (["--domains", domains] if domains else [])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    try:
        reports = json.loads(result.stdout)
    except json.JSONDecodeError:
        lines = (result.stderr or "sortie vide").strip().splitlines()
        return {}, f"Classification impossible : {lines[-1][:300] if lines else '?'}"
    return {Path(r["input"]).resolve(): r for r in reports if "error" not in r}, None


def load_check():
    """Fonction check() de validate.py (skill doc-to-markdown), ou None s'il manque."""
    if not VALIDATE.is_file():
        return None
    spec = importlib.util.spec_from_file_location("validate", VALIDATE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.check


def frontmatter(text: str, path: Path, source: str | None, tags: list[str],
                extra: dict | None = None) -> str:
    if text.startswith("---\n"):
        return text
    match = H1.search(text)
    title = match.group(1).strip() if match else path.stem
    lines = ["---", f"title: {yaml_string(title)}"]
    if source:
        lines.append(f"source: {yaml_string(source)}")
    lines.append(f"created: {datetime.date.today().isoformat()}")
    for key, value in (extra or {}).items():
        lines.append(f"{key}: {yaml_string(value)}")
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


def process(path: Path, args, classification: dict | None = None) -> dict:
    text = path.read_text(encoding="utf-8")
    report = {"input": str(path), "output": None, "embeds": 0, "wikilinks": 0,
              "callouts": 0, "attachments_copied": 0, "missing": []}
    extra = {}
    if classification:
        extra = {key: classification[key] for key in ("type", "domaine") if classification[key]}
        report["classification"] = {key: classification[key] for key in
                                    ("type", "domaine", "method", "warnings")}
        if text.startswith("---\n") and extra:
            report["classification"]["warnings"].append(
                "Frontmatter déjà présent : type et domaine non ajoutés")
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
    text = frontmatter(text, path, args.source, tags, extra)

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
    check = load_check()
    if check:
        result = check(target, obsidian=True, vault=args.vault)
        report["validation"] = {key: result[key] for key in ("ok", "errors", "warnings")}
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
    parser.add_argument("--classify", action="store_true",
                        help="ajouter type et domaine au frontmatter (modèle local Laya)")
    parser.add_argument("--domains", help="avec --classify : domaines possibles, séparés par des virgules")
    args = parser.parse_args()
    if args.vault:
        args.vault = args.vault.resolve()

    reports, failed = [], False
    classifications, classify_warning = {}, None
    if args.classify:
        existing = [path.resolve() for path in args.files if path.is_file()]
        if existing:
            classifications, classify_warning = run_classifier(existing, args.domains)
    for path in args.files:
        if not path.is_file():
            reports.append({"input": str(path), "error": "Fichier introuvable"})
            failed = True
            continue
        reports.append(process(path.resolve(), args, classifications.get(path.resolve())))
        if classify_warning:
            reports[-1]["classification_warning"] = classify_warning
        failed = failed or bool(reports[-1]["missing"])
    # Un objet par ligne : lisible, et sans l'indentation qui coûte des tokens.
    print("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in reports) + "\n]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
