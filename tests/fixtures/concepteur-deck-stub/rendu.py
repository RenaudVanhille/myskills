# /// script
# requires-python = ">=3.10"
# dependencies = ["python-pptx>=1.0"]
# ///
"""Doublure de test du rendu de l'agent externe concepteur-deck : respecte son
contrat d'interface (shared/external/concepteur-deck.contract.json) sans être
une copie de l'agent ni du skill markdown-to-pptx. Une diapositive de titre,
puis une par section ## ; une image par section qui en cite une. Écrit l'état
de relecture NOM.review.json dans --preview (verdict --status) et, comme
--autofix, une copie NOM.before-autofix.md à côté du Markdown.
"""
import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

parser = argparse.ArgumentParser()
parser.add_argument("input")
parser.add_argument("-o", "--output", required=True)
parser.add_argument("--preview", required=True)
parser.add_argument("--status", choices=["clean", "fix", "stop"], default="clean")
args = parser.parse_args()
source, output = Path(args.input), Path(args.output)
text = source.read_text(encoding="utf-8")
slides = [{"title": re.search(r"^# (.+)$", text, re.M).group(1)}]
for block in re.split(r"^## ", text, flags=re.M)[1:]:
    image = re.search(r"!\[([^\]]*)\]\(<?([^)>\s]+)>?\)", block)
    slide = {"title": block.splitlines()[0].strip()}
    if image:
        slide.update(src=image.group(2), alt=image.group(1))
    slides.append(slide)
deck = Presentation()
for slide in slides:
    page = deck.slides.add_slide(deck.slide_layouts[5])
    page.shapes.title.text = slide["title"]
    if slide.get("src"):
        picture = page.shapes.add_picture(str(source.parent / slide["src"]), Inches(1), Inches(2), height=Inches(3))
        picture._element.nvPicPr.cNvPr.set("descr", slide["alt"])
output.parent.mkdir(parents=True, exist_ok=True)
deck.save(output)
shutil.copyfile(source, source.with_suffix(".before-autofix.md"))
preview = Path(args.preview)
preview.mkdir(parents=True, exist_ok=True)
issues = 0 if args.status == "clean" else 2
(preview / f"{output.stem}.review.json").write_text(json.dumps(
    {"round": 3 if args.status == "stop" else 1, "md": hashlib.sha1(source.read_bytes()).hexdigest(),
     "issues": issues, "before": None, "status": args.status, "time": 0}), encoding="utf-8")
