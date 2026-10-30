# /// script
# requires-python = ">=3.10"
# dependencies = ["pypandoc_binary>=1.13", "python-docx>=1.1", "pypdfium2>=4.30", "pillow>=10", "playwright>=1.48"]
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
        [--toc] [--pdf] [--preview | --preview-all] [--vault VAULT]

- docx : Word, import Word de Confluence, Office Importer de XWiki, SharePoint ;
- html : page autonome (images intégrées), à ouvrir ou à coller dans un éditeur ;
- xwiki : syntaxe XWiki 2.1 et images à joindre à la page, dans `<nom>-xwiki/`.

--preview ne rend que les pages à relire (image, tableau, ou titre seul en bas
de page), assemblées par 4 sur des planches PNG ; --preview-all rend chaque
page séparément.
"""

import argparse
import json
import re
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
import local_tools  # noqa: E402
from script_report import print_report  # noqa: E402
from skill_paths import absent, load_module  # noqa: E402

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
REFERENCE_DOC = Path(__file__).resolve().parents[1] / "references" / "modele.docx"
MAX_WIDTH_CM, MAX_HEIGHT_CM = 16.6, 20.0  # zone de texte A4 du modèle
SHEET_PAGES = 4  # pages par planche d'aperçu (2 x 2)
FPDF_PAGEOBJ_PATH, FPDF_PAGEOBJ_IMAGE = 2, 3


def size_attr(path: Path, hidpi: bool) -> str:
    """Taille d'affichage d'un PNG : sa taille naturelle à 96 ppp (ou 192 pour
    les exports de schémas, rendus à l'échelle 2), réduite pour tenir dans la page."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(24)
    except OSError:
        return ""
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return ""
    width, height = struct.unpack(">II", head[16:24])
    cm = 2.54 / (192 if hidpi else 96)
    w, h = width * cm, height * cm
    ratio = min(1.0, MAX_WIDTH_CM / w, MAX_HEIGHT_CM / h)
    return "{width=%.2fcm}" % (w * ratio)


def load_exporter():
    module = load_module("diagram-export", "export.py")
    if module is None:
        raise SystemExit(absent("diagram-export", "export.py"))
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
        return f"![{caption}]({png.as_posix()}){size_attr(png, True)}"

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
        hidpi = path.parent == self.work / "diagrams" or re.search(r"\.(drawio|excalidraw)\.png$", path.name)
        return f"![{alt}](<{path.as_posix()}>){size_attr(path, bool(hidpi))}"

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


def finish_docx(path: Path, toc: bool) -> None:
    """Retouches que Pandoc ne fait pas : légendes numérotées, tableaux pleine
    largeur avec ligne d'en-tête répétée, sommaire mis à jour à l'ouverture."""
    from docx import Document
    from docx.oxml import OxmlElement
    from docx.oxml.ns import qn

    doc = Document(path)
    figure = 0
    for paragraph in doc.paragraphs:
        if paragraph.style.name == "Image Caption" and paragraph.runs:
            figure += 1
            first = paragraph.runs[0]
            first.text = f"Figure {figure} : {first.text}"
    for table in doc.tables:
        tbl_pr = table._tbl.tblPr
        width = tbl_pr.find(qn("w:tblW"))
        if width is None:
            width = OxmlElement("w:tblW")
            tbl_pr.append(width)
        width.set(qn("w:w"), "5000")
        width.set(qn("w:type"), "pct")
        if table.rows:
            tr_pr = table.rows[0]._tr.get_or_add_trPr()
            if tr_pr.find(qn("w:tblHeader")) is None:
                tr_pr.append(OxmlElement("w:tblHeader"))
    if toc:
        settings = doc.settings.element
        if settings.find(qn("w:updateFields")) is None:
            update = OxmlElement("w:updateFields")
            update.set(qn("w:val"), "true")
            settings.append(update)
    doc.save(path)


def soffice_binary() -> str | None:
    return local_tools.soffice_binary()


def pages_to_review(document, headings: set[str]) -> list[int]:
    """Numéros des pages qui contiennent une image, un tableau (traits), ou se
    terminent par un titre du document (titre isolé en bas de page)."""
    flagged = []
    for index in range(len(document)):
        page = document[index]
        kinds = [obj.type for obj in page.get_objects()]
        lines = [l.strip() for l in page.get_textpage().get_text_range().splitlines() if l.strip()]
        # La dernière ligne est le numéro de page du pied de page : on regarde celle d'avant.
        last = lines[-2] if len(lines) > 1 else ""
        if (FPDF_PAGEOBJ_IMAGE in kinds or kinds.count(FPDF_PAGEOBJ_PATH) >= 4
                or last in headings):
            flagged.append(index + 1)
    return flagged


def contact_sheets(images: list, numbers: list[int], folder: Path) -> list[str]:
    """Assemble les pages par SHEET_PAGES sur des planches, numéro de page en haut."""
    from PIL import Image, ImageDraw

    sheets = []
    for start in range(0, len(images), SHEET_PAGES):
        group = images[start:start + SHEET_PAGES]
        w, h = max(i.width for i in group), max(i.height for i in group)
        sheet = Image.new("RGB", (w * 2 + 10, h * ((len(group) + 1) // 2) + 10), "#9ca3af")
        draw = ImageDraw.Draw(sheet)
        for offset, image in enumerate(group):
            x, y = (offset % 2) * (w + 10), (offset // 2) * (h + 10)
            sheet.paste(image, (x, y))
            draw.text((x + 8, y + 6), f"p. {numbers[start + offset]}", fill="#b91c1c")
        target = folder / f"planche-{start // SHEET_PAGES + 1}.png"
        sheet.save(target)
        sheets.append(str(target))
    return sheets


def render_docx(docx: Path, keep_pdf: bool, preview: str | None, headings: set[str]) -> dict:
    """PDF et aperçu des pages avec LibreOffice, pour relire le rendu.
    preview : None, "cible" (pages à relire, en planches) ou "tout" (chaque page)."""
    soffice = soffice_binary()
    if not soffice:
        return {"warning": "LibreOffice introuvable : pas de PDF ni d'aperçu "
                           "(https://www.libreoffice.org/download/)"}
    result = {}
    with tempfile.TemporaryDirectory() as tmp:
        profile = Path(tmp, "profil").as_uri()  # profil isolé : marche même si LibreOffice est ouvert
        try:
            subprocess.run([soffice, f"-env:UserInstallation={profile}", "--headless",
                            "--convert-to", "pdf", "--outdir", tmp, str(docx)],
                           capture_output=True, timeout=300, check=True)
        except (subprocess.SubprocessError, OSError) as error:
            return {"warning": f"LibreOffice : conversion PDF impossible ({error})"}
        pdf = Path(tmp) / f"{docx.stem}.pdf"
        if not pdf.is_file():
            return {"warning": "LibreOffice n'a pas produit de PDF"}
        if preview:
            import pypdfium2 as pdfium

            folder = docx.parent / ".myskills-tmp" / f"{docx.stem}-apercu"
            if folder.exists():
                shutil.rmtree(folder)
            folder.mkdir(parents=True)
            document = pdfium.PdfDocument(str(pdf))
            numbers = (list(range(1, len(document) + 1)) if preview == "tout"
                       else pages_to_review(document, headings))
            images = [document[n - 1].render(scale=1.0).to_pil() for n in numbers]
            document.close()
            if preview == "tout":
                pages = []
                for number, image in zip(numbers, images):
                    page = folder / f"page-{number}.png"
                    image.save(page)
                    pages.append(str(page))
                result["preview"] = pages
            else:
                result["preview"] = contact_sheets(images, numbers, folder)
            result["preview_pages"] = numbers
        if keep_pdf:
            target = docx.with_suffix(".pdf")
            shutil.copy2(pdf, target)
            result["pdf"] = str(target)
    return result


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
        headings = {h.strip() for h in re.findall(r"^#{1,6}\s+(.+)$", text, re.M)}
        for fmt in args.formats:
            extra = list(base)
            rendered = {}
            if fmt == "docx":
                target = out_dir / f"{doc.stem}.docx"
                reference = args.reference_doc.resolve() if args.reference_doc else REFERENCE_DOC
                extra += ["--reference-doc", str(reference)]
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
                pypandoc.convert_file(str(source), FORMATS[fmt], format="gfm+yaml_metadata_block+attributes+implicit_figures",
                                      outputfile=str(target), extra_args=extra)
            except RuntimeError as error:
                report["error"] = f"Pandoc ({fmt}) : {str(error).strip().splitlines()[-1]}"
                return report
            if fmt == "xwiki":
                attach_xwiki_images(target)
            if fmt == "docx":
                finish_docx(target, args.toc)
                if args.pdf or args.preview:
                    rendered = render_docx(target, args.pdf, args.preview, headings)
                    if rendered.get("warning"):
                        report["warnings"].append(rendered.pop("warning"))
            ai_mark.inherit(doc, [target])
            found = check_output(target, fmt)
            report["outputs"].append({"format": fmt, "file": str(target), **found, **rendered})
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
    parser.add_argument("--pdf", action="store_true", help="docx : produire aussi un PDF (LibreOffice)")
    preview = parser.add_mutually_exclusive_group()
    preview.add_argument("--preview", action="store_const", const="cible",
                         help="docx : planches PNG des pages à relire dans .myskills-tmp/ (LibreOffice)")
    preview.add_argument("--preview-all", dest="preview", action="store_const", const="tout",
                         help="docx : aperçu PNG de chaque page dans .myskills-tmp/ (LibreOffice)")
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
    print_report(reports)
    return 1 if any(r.get("error") for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
