# /// script
# requires-python = ">=3.10"
# dependencies = ["pypandoc_binary>=1.13", "playwright>=1.48"]
# ///
"""Publie un Markdown en Word, HTML ou XWiki, schémas compris, sans rien envoyer.

Avant la conversion par Pandoc (fourni par le paquet pypandoc_binary) :
- chaque bloc ```mermaid devient une image PNG ;
- les images qui pointent vers un schéma source (.drawio, .excalidraw, .mmd)
  sont remplacées par leur export PNG ;
- la syntaxe Obsidian est ramenée au Markdown standard (embeds `![[...]]`,
  wikilinks, callouts).
Les exports passent par le script `export.py` du skill `diagram-export`.
Affiche un rapport JSON. Usage :
    uv run scripts/publish.py DOC.md [...] [--to docx,html,xwiki] [--out DOSSIER]
        [--reference-doc modele.docx]
        [--toc] [--vault VAULT]

- docx : Word, import Word de Confluence, Office Importer de XWiki, SharePoint ;
- html : page autonome (images intégrées), à ouvrir ou à coller dans un éditeur ;
- xwiki : syntaxe XWiki 2.1 et images à joindre à la page, dans `<nom>-xwiki/`.
"""

import argparse
import importlib.util
import json
import re
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote

EXPORT_SCRIPT = Path(__file__).resolve().parents[2] / "diagram-export" / "scripts" / "export.py"
MERMAID = re.compile(r"^```mermaid[ \t]*\n(.*?)^```[ \t]*$", re.M | re.S)
IMAGE = re.compile(r"!\[([^\]]*)\]\(<?([^)>\s]+)>?(\s+\"[^\"]*\")?\)")
EMBED = re.compile(r"!\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|([^\]]*))?\]\]")
WIKILINK = re.compile(r"(?<!!)\[\[([^\]|#]+)(?:#([^\]|]*))?(?:\|([^\]]*))?\]\]")
CALLOUT = re.compile(r"^>\s*\[!(\w+)\][+-]?[ \t]*(.*)$", re.M)
CALLOUT_TITLES = {"note": "Note", "info": "Information", "tip": "Astuce", "important": "Important",
                  "warning": "Attention", "caution": "Attention", "danger": "Danger",
                  "example": "Exemple", "question": "Question", "success": "Réussite",
                  "failure": "Échec", "bug": "Anomalie", "quote": "Citation", "abstract": "Résumé"}
TABLE_SEPARATOR = re.compile(r"^\|?[ \t]*:?-{3,}:?[ \t]*(?:\|[ \t]*:?-{3,}:?[ \t]*)*\|?[ \t]*$", re.M)
DIAGRAM_SOURCES = {".drawio", ".excalidraw", ".mmd", ".mermaid"}


def load_exporter():
    spec = importlib.util.spec_from_file_location("myskills_export", EXPORT_SCRIPT)
    if spec is None or not EXPORT_SCRIPT.is_file():
        raise SystemExit(f"Script d'export introuvable : {EXPORT_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Prepared:
    def __init__(self, doc: Path, work: Path, vault: Path | None, exporter):
        self.doc, self.work, self.vault, self.exporter = doc, work, vault, exporter
        self.diagrams, self.images, self.warnings = 0, 0, []
        (work / "diagrams").mkdir(parents=True, exist_ok=True)

    def find(self, name: str) -> Path | None:
        """Retrouve un fichier cité par son nom, comme le fait Obsidian."""
        direct = (self.doc.parent / unquote(name))
        if direct.is_file():
            return direct.resolve()
        for root in filter(None, [self.doc.parent, self.vault]):
            match = next((p for p in root.rglob(Path(name).name) if p.is_file()), None)
            if match:
                return match.resolve()
        return None

    def export(self, src: Path, stem: str) -> Path | None:
        kind = src.suffix.lower()
        out = self.work / "diagrams"
        try:
            files = self.exporter.EXPORTERS[kind](src, out, "png", 2.0, False)
        except self.exporter.ExportError as error:
            self.warnings.append(f"{src.name} : export impossible ({error})")
            return None
        self.diagrams += 1
        target = out / f"{stem}.png"
        files[0].replace(target)
        return target

    def mermaid(self, match: re.Match) -> str:
        index = self.diagrams + 1
        source = self.work / "diagrams" / f"mermaid-{index}.mmd"
        source.write_text(match.group(1), encoding="utf-8")
        png = self.export(source, f"mermaid-{index}")
        if png is None:
            return match.group(0)
        title = re.search(r"^title:\s*(.+)$", match.group(1), re.M)
        caption = title.group(1).strip().strip("\"'") if title else ""
        self.images += 1
        return f"![{caption}]({png.as_posix()})"

    def image(self, alt: str, target: str) -> str:
        if re.match(r"^[a-z]+:", target):
            return f"![{alt}]({target})"
        path = self.find(target)
        if path is None:
            self.warnings.append(f"Image introuvable : {target}")
            return f"![{alt}]({target})"
        if path.suffix.lower() in DIAGRAM_SOURCES:
            png = self.export(path, f"{path.stem}-{self.diagrams + 1}")
            if png is None:
                return f"*[Schéma non exporté : {path.name}]*"
            path = png
        self.images += 1
        return f"![{alt}](<{path.as_posix()}>)"

    def run(self, text: str) -> str:
        # Images standard d'abord : les remplacements suivants n'en produisent
        # que de déjà traitées.
        text = IMAGE.sub(lambda m: self.image(m.group(1), m.group(2)), text)
        text = EMBED.sub(lambda m: self.image((m.group(2) or "").strip(), m.group(1).strip())
                         if not m.group(1).strip().lower().endswith(".md") and "." in m.group(1)
                         else f"*{m.group(1).strip()}*", text)
        text = MERMAID.sub(self.mermaid, text)
        # Le titre du frontmatter sert de titre au document : on retire le H1 identique.
        title = re.match(r"^---\n.*?^title:\s*[\"']?(.+?)[\"']?\s*$.*?^---\n", text, re.S | re.M)
        if title:
            text = re.sub(rf"^#\s+{re.escape(title.group(1))}\s*\n", "", text, count=1, flags=re.M)
        text = WIKILINK.sub(lambda m: (m.group(3) or m.group(2) or m.group(1)).strip(), text)
        return CALLOUT.sub(lambda m: f"> **{m.group(2).strip() or CALLOUT_TITLES.get(m.group(1).lower(), m.group(1).capitalize())}**", text)


FORMATS = {"docx": "docx", "html": "html", "xwiki": "xwiki"}
XWIKI_IMAGE = re.compile(r"\[\[image:([^|\]]+)")


def check_output(path: Path, fmt: str) -> dict:
    if fmt == "docx":
        with zipfile.ZipFile(path) as archive:
            media = [n for n in archive.namelist() if n.startswith("word/media/")]
            body = archive.read("word/document.xml").decode("utf-8")
        return {"images": len(media), "tables": body.count("<w:tbl>")}
    text = path.read_text(encoding="utf-8")
    if fmt == "html":
        return {"images": len(re.findall(r"<img\b", text)), "tables": text.count("<table")}
    return {"images": len(XWIKI_IMAGE.findall(text)),
            "tables": len(re.findall(r"(?:^|\n\n)\|=", text))}


def attach_xwiki_images(page: Path) -> int:
    """Copie les images à côté de la page XWiki et les cite par leur nom (pièces jointes)."""
    text, copied = page.read_text(encoding="utf-8"), {}

    def attach(match: re.Match) -> str:
        source = Path(unquote(match.group(1)))
        if not source.is_file():
            return match.group(0)
        name = copied.setdefault(source, source.name if source.name not in
                                 {p.name for p in copied} else f"{len(copied)}-{source.name}")
        shutil.copy2(source, page.parent / name)
        return f"[[image:{name}"

    page.write_text(XWIKI_IMAGE.sub(attach, text), encoding="utf-8", newline="\n")
    return len(copied)


def publish(doc: Path, args, exporter) -> dict:
    import pypandoc

    report = {"input": str(doc), "outputs": [], "diagrams_exported": 0, "warnings": []}
    out_dir = (args.out or doc.parent).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    text = doc.read_text(encoding="utf-8")
    with tempfile.TemporaryDirectory() as tmp:
        prepared = Prepared(doc, Path(tmp), args.vault, exporter)
        text = prepared.run(text)
        source = Path(tmp) / doc.name
        source.write_text(text, encoding="utf-8")
        report["diagrams_exported"] = prepared.diagrams
        report["warnings"] = prepared.warnings
        tables = sum(1 for line in TABLE_SEPARATOR.findall(text) if "|" in line)
        base = ["--resource-path", f"{doc.parent}{';' if sys.platform == 'win32' else ':'}{tmp}"]
        if not re.search(r"^lang:", text, re.M):
            base += ["--metadata", "lang=fr-FR"]
        if args.toc:
            base += ["--toc", "--toc-depth=3", "--metadata", "toc-title=Sommaire"]
        for fmt in args.formats:
            extra = list(base)
            if fmt == "docx":
                target = out_dir / f"{doc.stem}.docx"
                if args.reference_doc:
                    extra += ["--reference-doc", str(args.reference_doc.resolve())]
            elif fmt == "html":
                target = out_dir / f"{doc.stem}.html"
                extra += ["--standalone", "--embed-resources"]
                if not re.match(r"^---\n.*?^title:", text, re.S | re.M):
                    heading = re.search(r"^#\s+(.+)$", text, re.M)
                    extra += ["--metadata", f"pagetitle={heading.group(1) if heading else doc.stem}"]
            else:
                folder = out_dir / f"{doc.stem}-xwiki"
                folder.mkdir(exist_ok=True)
                target = folder / f"{doc.stem}.xwiki"
            try:
                pypandoc.convert_file(str(source), FORMATS[fmt], format="gfm+yaml_metadata_block",
                                      outputfile=str(target), extra_args=extra)
            except RuntimeError as error:
                report["error"] = f"Pandoc ({fmt}) : {str(error).strip().splitlines()[-1]}"
                return report
            if fmt == "xwiki":
                attach_xwiki_images(target)
            found = check_output(target, fmt)
            report["outputs"].append({"format": fmt, "file": str(target), **found})
            if found["images"] < prepared.images:
                report["warnings"].append(f"{fmt} : {found['images']} image(s), "
                                          f"{prepared.images} attendue(s)")
            if found["tables"] < tables:
                report["warnings"].append(f"{fmt} : {found['tables']} tableau(x), {tables} attendu(s)")
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("docs", nargs="+", type=Path)
    parser.add_argument("--to", default="docx",
                        help="formats séparés par des virgules : docx, html, xwiki (défaut : docx)")
    parser.add_argument("--out", type=Path, help="dossier de sortie (défaut : à côté du Markdown)")
    parser.add_argument("--reference-doc", type=Path, help="modèle Word (styles, en-tête, pied de page)")
    parser.add_argument("--toc", action="store_true", help="ajouter une table des matières")
    parser.add_argument("--vault", type=Path, help="vault Obsidian, pour retrouver les pièces jointes")
    args = parser.parse_args()
    args.formats = [f.strip().lower() for f in args.to.split(",") if f.strip()]
    unknown = [f for f in args.formats if f not in FORMATS]
    if unknown or not args.formats:
        parser.error(f"format inconnu : {', '.join(unknown) or '(vide)'} (docx, html, xwiki)")
    if args.vault:
        args.vault = args.vault.resolve()
    exporter = load_exporter()
    reports = []
    for doc in args.docs:
        if not doc.is_file():
            reports.append({"input": str(doc), "error": "Fichier introuvable"})
            continue
        reports.append(publish(doc.resolve(), args, exporter))
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if any(r.get("error") for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
