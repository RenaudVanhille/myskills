# /// script
# requires-python = ">=3.10"
# dependencies = ["pypandoc_binary>=1.13", "python-docx>=1.1"]
# ///
"""Génère le modèle Word par défaut (`references/modele.docx`) aux couleurs de la charte.

Part du modèle de Pandoc et règle : police, couleurs et espacements des titres,
style des tableaux (bordures, ligne d'en-tête), citations, légendes, format A4,
marges et numéros de page. Usage (pour mettre à jour le modèle livré) :
    uv run scripts/make_reference.py [--out references/modele.docx]
"""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

import pypandoc
from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

FONT = "Calibri"
TEXT, ACCENT, MUTED = "1F2937", "1D4ED8", "6B7280"
BORDER, HEADER_FILL, QUOTE_FILL = "D1D5DB", "DBEAFE", "F3F4F6"


def rgb(value: str) -> RGBColor:
    return RGBColor.from_string(value)


def set_font(style, size: float, color: str = TEXT, bold: bool | None = None,
             italic: bool | None = None) -> None:
    font = style.font
    font.name, font.size, font.color.rgb = FONT, Pt(size), rgb(color)
    font.bold, font.italic = bold, italic
    fonts = style.element.get_or_add_rPr().find(qn("w:rFonts"))
    if fonts is None:
        fonts = OxmlElement("w:rFonts")
        style.element.get_or_add_rPr().append(fonts)
    for attr in ("w:ascii", "w:hAnsi", "w:cs", "w:eastAsia"):
        fonts.set(qn(attr), FONT)
    for attr in ("w:asciiTheme", "w:hAnsiTheme", "w:cstheme", "w:eastAsiaTheme"):
        fonts.attrib.pop(qn(attr), None)


def spacing(style, before: float = 0, after: float = 6, line: float = 1.15,
            keep_next: bool = False) -> None:
    fmt = style.paragraph_format
    fmt.space_before, fmt.space_after, fmt.line_spacing = Pt(before), Pt(after), line
    fmt.keep_with_next = keep_next


def border(tag: str, color: str, size: int = 4, space: int = 0) -> OxmlElement:
    element = OxmlElement(tag)
    for key, value in (("w:val", "single"), ("w:sz", str(size)), ("w:space", str(space)),
                       ("w:color", color)):
        element.set(qn(key), value)
    return element


def shading(fill: str) -> OxmlElement:
    element = OxmlElement("w:shd")
    element.set(qn("w:val"), "clear")
    element.set(qn("w:color"), "auto")
    element.set(qn("w:fill"), fill)
    return element


def replace(parent, tag: str, child) -> None:
    for old in parent.findall(qn(tag)):
        parent.remove(old)
    parent.append(child)


def table_style(doc: Document) -> None:
    style = doc.styles["Table"].element
    tbl_pr = style.find(qn("w:tblPr"))
    if tbl_pr is None:
        tbl_pr = OxmlElement("w:tblPr")
        style.append(tbl_pr)
    borders = OxmlElement("w:tblBorders")
    for side in ("top", "left", "bottom", "right", "insideH", "insideV"):
        borders.append(border(f"w:{side}", BORDER))
    replace(tbl_pr, "w:tblBorders", borders)
    margins = OxmlElement("w:tblCellMar")
    for side, width in (("top", 40), ("left", 100), ("bottom", 40), ("right", 100)):
        cell = OxmlElement(f"w:{side}")
        cell.set(qn("w:w"), str(width))
        cell.set(qn("w:type"), "dxa")
        margins.append(cell)
    replace(tbl_pr, "w:tblCellMar", margins)
    for old in style.findall(qn("w:tblStylePr")):
        style.remove(old)
    header = OxmlElement("w:tblStylePr")
    header.set(qn("w:type"), "firstRow")
    run = OxmlElement("w:rPr")
    run.append(OxmlElement("w:b"))
    color = OxmlElement("w:color")
    color.set(qn("w:val"), TEXT)
    run.append(color)
    header.append(run)
    cell_pr = OxmlElement("w:tcPr")
    cell_pr.append(shading(HEADER_FILL))
    header.append(cell_pr)
    row_pr = OxmlElement("w:trPr")
    row_pr.append(OxmlElement("w:tblHeader"))
    header.append(row_pr)
    style.append(header)


def quote_style(doc: Document) -> None:
    style = doc.styles["Block Text"]
    set_font(style, 10.5, TEXT, italic=False)
    spacing(style, 6, 6)
    fmt = style.paragraph_format
    fmt.left_indent, fmt.right_indent = Cm(0.4), Cm(0)
    p_pr = style.element.get_or_add_pPr()
    borders = OxmlElement("w:pBdr")
    borders.append(border("w:left", ACCENT, size=18, space=8))
    replace(p_pr, "w:pBdr", borders)
    replace(p_pr, "w:shd", shading(QUOTE_FILL))


def page_setup(doc: Document) -> None:
    for section in doc.sections:
        section.orientation = WD_ORIENT.PORTRAIT
        section.page_width, section.page_height = Cm(21), Cm(29.7)
        for side in ("left_margin", "right_margin"):
            setattr(section, side, Cm(2.2))
        section.top_margin, section.bottom_margin = Cm(2), Cm(2)
        footer = section.footer.paragraphs[0] if section.footer.paragraphs else section.footer.add_paragraph()
        footer.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        for text, field in (("Page ", "PAGE"), (" / ", "NUMPAGES")):
            footer.add_run(text).font.size = Pt(9)
            run = footer.add_run()
            run.font.size = Pt(9)
            for kind in ("begin", None, "end"):
                if kind is None:
                    instr = OxmlElement("w:instrText")
                    instr.set(qn("xml:space"), "preserve")
                    instr.text = f" {field} "
                    run._r.append(instr)
                else:
                    char = OxmlElement("w:fldChar")
                    char.set(qn("w:fldCharType"), kind)
                    run._r.append(char)
        for run in footer.runs:
            run.font.color.rgb = rgb(MUTED)


def build(out: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "reference.docx"
        subprocess.run([pypandoc.get_pandoc_path(), "-o", str(base),
                        "--print-default-data-file", "reference.docx"], check=True)
        doc = Document(base)
    styles = doc.styles
    for name in ("Normal", "Body Text", "First Paragraph", "Compact"):
        set_font(styles[name], 11)
    spacing(styles["Body Text"], 0, 6)
    spacing(styles["First Paragraph"], 0, 6)
    spacing(styles["Compact"], 0, 2)
    set_font(styles["Title"], 26, ACCENT, bold=True)
    spacing(styles["Title"], 0, 12, 1.0)
    styles["Title"].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    set_font(styles["Subtitle"], 14, MUTED)
    for name in ("Author", "Date"):
        set_font(styles[name], 10, MUTED)
        styles[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.LEFT
    for level, (size, color, before) in enumerate(
            [(16, ACCENT, 18), (13, ACCENT, 14), (12, TEXT, 10), (11, TEXT, 8)], 1):
        style = styles[f"Heading {level}"]
        set_font(style, size, color, bold=True)
        spacing(style, before, 6, 1.0, keep_next=True)
    for name in ("Image Caption", "Table Caption"):
        set_font(styles[name], 9, MUTED, italic=True)
        spacing(styles[name], 2, 10)
        styles[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
    for name in ("Figure", "Captioned Figure"):
        styles[name].paragraph_format.alignment = WD_ALIGN_PARAGRAPH.CENTER
        styles[name].paragraph_format.keep_with_next = True
    set_font(styles["TOC Heading"], 16, ACCENT, bold=True)
    quote_style(doc)
    table_style(doc)
    page_setup(doc)
    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parents[1] / "references" / "modele.docx")
    args = parser.parse_args()
    build(args.out)
    print(args.out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
