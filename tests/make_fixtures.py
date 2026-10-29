# /// script
# requires-python = ">=3.10"
# dependencies = ["python-docx", "python-pptx", "pillow", "reportlab"]
# ///
"""Génère des documents d'exemple synthétiques dans tests/fixtures/samples/.

Ils servent aux tests automatiques des skills ; vos documents réels vont
directement dans tests/fixtures/.

Usage : uv run tests/make_fixtures.py
"""

from pathlib import Path

from docx import Document
from docx.shared import Inches
from PIL import Image, ImageDraw, ImageFont
from pptx import Presentation
from pptx.util import Inches as PptInches
from reportlab.lib.pagesizes import A4
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent / "fixtures" / "samples"
MOCKUPS = Path(__file__).resolve().parent / "fixtures" / "maquettes"

TITLE = "Architecture du service de paiement"
PARAGRAPH = ("Le service de paiement reçoit les commandes, appelle la banque "
             "et notifie le client. Ce document décrit ses composants.")
ROWS = [("Composant", "Rôle", "Technologie"),
        ("API", "Reçoit les commandes", "Java 21"),
        ("Worker", "Appelle la banque", "Python 3.13"),
        ("Base", "Stocke les paiements", "PostgreSQL")]


def font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def make_diagram(path: Path) -> None:
    """Petit schéma en image : trois boîtes reliées par des flèches."""
    img = Image.new("RGB", (900, 300), "white")
    draw = ImageDraw.Draw(img)
    for i, label in enumerate(["API", "Worker", "Banque"]):
        x = 40 + i * 300
        draw.rectangle([x, 100, x + 220, 200], outline="black", width=3)
        draw.text((x + 70, 135), label, fill="black", font=font(28))
        if i < 2:
            draw.line([x + 220, 150, x + 300, 150], fill="black", width=3)
            draw.polygon([(x + 300, 150), (x + 285, 140), (x + 285, 160)], fill="black")
    img.save(path)


def make_mockup(path: Path) -> None:
    """Maquette d'écran d'un appel d'offres fictif : en-tête, bandeau, trois cartes, pied de page."""
    navy, orange, line, grey = "#0b3d91", "#f97316", "#e2e8f0", "#f1f5f9"
    img = Image.new("RGB", (1280, 900), "white")
    draw = ImageDraw.Draw(img)
    draw.rectangle([0, 63, 1280, 64], fill=line)
    draw.rectangle([40, 14, 76, 50], fill=navy)
    draw.text((88, 20), "Assur'Plus", fill="#0f172a", font=font(24))
    for i, label in enumerate(["Mes contrats", "Mes sinistres", "Aide"]):
        draw.text((420 + i * 150, 22), label, fill="#0f172a", font=font(18))
    draw.rounded_rectangle([1010, 12, 1240, 52], radius=8, fill=orange)
    draw.text((1030, 22), "Déclarer un sinistre", fill="white", font=font(17))
    draw.rectangle([0, 65, 1280, 384], fill=navy)
    draw.text((80, 150), "Déclarez votre sinistre en ligne", fill="white", font=font(40))
    draw.text((80, 215), "Suivi en temps réel, réponse sous 48 heures.", fill="#dbeafe", font=font(20))
    draw.rounded_rectangle([80, 270, 300, 318], radius=8, fill=orange)
    draw.text((104, 283), "Commencer", fill="white", font=font(20))
    for i, (title, text) in enumerate([("Auto", "Accident, bris de glace"), ("Habitation", "Dégât des eaux, vol"),
                                       ("Santé", "Remboursements")]):
        x = 80 + i * 380
        draw.rounded_rectangle([x, 440, x + 350, 700], radius=16, fill="white", outline=line, width=2)
        draw.text((x + 24, 470), title, fill="#0f172a", font=font(24))
        draw.text((x + 24, 515), text, fill="#64748b", font=font(18))
    draw.rectangle([0, 780, 1280, 900], fill=grey)
    draw.text((80, 825), "© Assur'Plus, mentions légales", fill="#64748b", font=font(16))
    img.save(path)


def make_docx(path: Path, diagram: Path) -> None:
    doc = Document()
    doc.add_heading(TITLE, level=1)
    doc.add_paragraph(PARAGRAPH)
    doc.add_heading("Composants", level=2)
    table = doc.add_table(rows=len(ROWS), cols=3)
    for r, row in enumerate(ROWS):
        for c, value in enumerate(row):
            table.cell(r, c).text = value
    doc.add_heading("Flux", level=2)
    doc.add_picture(str(diagram), width=Inches(6))
    doc.add_paragraph("Figure 1 : flux d'un paiement.")
    doc.save(path)


def make_pptx(path: Path, diagram: Path) -> None:
    prs = Presentation()
    slide = prs.slides.add_slide(prs.slide_layouts[1])
    slide.shapes.title.text = TITLE
    slide.placeholders[1].text = PARAGRAPH
    slide = prs.slides.add_slide(prs.slide_layouts[5])
    slide.shapes.title.text = "Flux d'un paiement"
    slide.shapes.add_picture(str(diagram), PptInches(0.5), PptInches(2), width=PptInches(9))
    prs.save(path)


def make_text_pdf(path: Path) -> None:
    pdf = canvas.Canvas(str(path), pagesize=A4)
    for page in (1, 2):
        pdf.setFont("Helvetica-Bold", 18)
        pdf.drawString(72, 770, f"{TITLE} - page {page}")
        pdf.setFont("Helvetica", 11)
        pdf.drawString(72, 740, PARAGRAPH[:80])
        pdf.drawString(72, 725, PARAGRAPH[80:])
        y = 690
        for row in ROWS:
            for c, value in enumerate(row):
                pdf.drawString(72 + c * 150, y, value)
            y -= 18
        pdf.showPage()
    pdf.save()


def make_scanned_pdf(path: Path) -> None:
    """PDF sans couche texte : une page rendue comme une image."""
    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    draw.text((100, 100), TITLE, fill="black", font=font(40))
    draw.text((100, 200), PARAGRAPH[:60], fill="black", font=font(28))
    draw.text((100, 245), PARAGRAPH[60:], fill="black", font=font(28))
    pdf = canvas.Canvas(str(path), pagesize=A4)
    pdf.drawImage(ImageReader(img), 0, 0, *A4)
    pdf.showPage()
    pdf.save()


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    diagram = OUT / "schema-flux.png"
    make_diagram(diagram)
    make_docx(OUT / "architecture.docx", diagram)
    make_pptx(OUT / "presentation.pptx", diagram)
    make_text_pdf(OUT / "rapport-texte.pdf")
    make_scanned_pdf(OUT / "rapport-scanne.pdf")
    MOCKUPS.mkdir(parents=True, exist_ok=True)
    make_mockup(MOCKUPS / "accueil.png")
    print(f"Exemples générés dans {OUT}")


if __name__ == "__main__":
    main()
