"""Doublure de test du skill externe markdown-to-pptx : respecte son contrat
d'interface (shared/external/markdown-to-pptx.contract.json) sans en être une
copie. Une diapositive de titre, puis une par section ## ; une image par
section qui en cite une. MD2PPTX_STUB=plan-invalide écrit un plan non conforme.
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from pptx import Presentation
from pptx.util import Inches

parser = argparse.ArgumentParser()
parser.add_argument("input", nargs="?")
parser.add_argument("-o", "--output")
parser.add_argument("--plan")
parser.add_argument("--template")
parser.add_argument("--lang")
parser.add_argument("--version", action="store_true")
args = parser.parse_args()
if args.version:
    print("md2pptx 0.5.0 (doublure de test)")
    sys.exit(0)
source = Path(args.input)
if not source.is_file():
    parser.error(f"input not found: {source}")
text = source.read_text(encoding="utf-8")
title = re.search(r"^# (.+)$", text, re.M).group(1)
slides = [{"kind": "title", "title": title}]
for block in re.split(r"^## ", text, flags=re.M)[1:]:
    heading = block.splitlines()[0].strip()
    hint = re.search(r"<!--\s*slide:\s*([a-z]+)", block)
    image = re.search(r"!\[([^\]]*)\]\(<?([^)>\s]+)>?\)", block)
    slide = {"kind": "image" if image else (hint.group(1) if hint else "bullets"), "title": heading}
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
deck.save(args.output)
plan = {"title": title, "purpose": {"type": "technical", "label": "Technical"}, "lang": args.lang or "fr",
        "slides": slides}
if os.environ.get("MD2PPTX_STUB") == "plan-invalide":
    del plan["slides"]
Path(args.plan).write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
