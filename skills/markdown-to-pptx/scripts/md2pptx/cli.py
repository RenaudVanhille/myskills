"""Command line entry point.

    python scripts/md2pptx.py INPUT.md -o deck.pptx [--template brand.potx]

Run with --help for all options, --guide for the full documentation, --check to
diagnose the installation.
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import __version__
from .parser import parse_file
from .planner import plan_document
from .render import render_plan
from .template import SKILL_DIR, Layouts, load_sidecar, open_template, resolve_template

KINDS = {
    "bullets": "a short flat list as highlighted rows; longer or nested lists as plain bullets",
    "text": "one or two short paragraphs shown as a statement",
    "process": "steps as chevrons, or numbered rows when steps are sentences",
    "cycle": "items around a circle with arrows",
    "timeline": "dated items on a horizontal axis ('Q1 2027: ...')",
    "hierarchy": "nested list, or a decision list ('A → B', Task/Model pairs), drawn as a tree",
    "cards": "'**Label**: text' items as a grid of cards (alternates with bands when repeated)",
    "stats": "1-4 big numbers with a caption ('**42%** of users ...'); one alone uses a key-figure layout",
    "pyramid": "layers, top item first",
    "comparison": "2-3 '###' subsections side by side",
    "funnel": "3-6 stages narrowing down (funnel / entonnoir / conversion heading)",
    "hub": "one centre item with 3-8 satellites (hub / ecosystem / platform heading)",
    "rings": "2-5 percentages as progress rings ('**72%**: of users ...')",
    "gantt": "date ranges as bars on a grid ('Jan–Mar 2026: Build', 'Weeks 1-3: Audit')",
    "matrix": "table of ratings (● ◑ ○, 3/4, ★★☆) drawn as Harvey balls",
    "map": "European countries highlighted on the brand map, list beside it",
    "stairs": "maturity staircase: 3-6 rising levels, outcome (first sub-item) under each step",
    "flow": "inputs -> core -> outputs boxes, with an optional '*' list of 2-4 panels under them",
    "table": "native PowerPoint table (split every 8 rows)",
    "chart": "numeric table as a native chart (line for time series, else columns)",
    "code": "code block in a monospace panel",
    "quote": "blockquote, on the template's quote layout when it has one",
    "image": "picture (local path or URL), with optional text beside it",
}

GUIDES = {
    "skill": SKILL_DIR / "SKILL.md",
    "markdown": SKILL_DIR / "references" / "markdown-guide.md",
    "templates": SKILL_DIR / "references" / "templates.md",
    "plan": SKILL_DIR / "references" / "plan-format.md",
    "troubleshooting": SKILL_DIR / "references" / "troubleshooting.md",
    "brand": SKILL_DIR / "references" / "brand-library.md",
    "authoring": SKILL_DIR / "references" / "authoring-guide.md",
}

EPILOG = """\
examples:
  md2pptx.py notes.md                          -> notes.pptx next to the input
  md2pptx.py notes.md -o deck.pptx -t brand.potx
  md2pptx.py notes.md --plan-only              show the slide decisions as JSON
  md2pptx.py plan.json --from-plan -o deck.pptx render an edited plan
  md2pptx.py --list-layouts -t brand.potx      how the template's layouts are used
  md2pptx.py --check                           diagnose the installation
  md2pptx.py --guide markdown                  how Markdown maps to slides
  md2pptx.py --guide authoring -o guide.md     writing rules to hand to another AI or agent

steer a section by putting a hint on its own line under the heading:
  <!-- slide: cycle -->   <!-- slide: chart; title=Revenue -->   <!-- notes: say this -->
group long decks into chapters with a marker under the first heading of each part:
  <!-- part: Costs -->
  kinds: """ + ", ".join(KINDS) + """

template order: --template, $MD2PPTX_TEMPLATE, .md2pptx/ folder in this or a parent
directory, the skill's assets/templates/brand/ folder, then the bundled default.
"""


def _layout_overrides(args) -> dict:
    out = {}
    if args.layout_map:
        out.update(json.loads(Path(args.layout_map).read_text(encoding="utf-8")))
    for item in args.layout or []:
        role, _, name = item.partition("=")
        out[role.strip()] = name.strip()
    return out


def _check(template) -> int:
    ok = True
    print(f"md2pptx {__version__}  (skill folder: {SKILL_DIR})")
    print(f"python   {sys.version.split()[0]}  ({sys.executable})")
    for mod, pkg in (("pptx", "python-pptx"), ("markdown_it", "markdown-it-py")):
        try:
            m = __import__(mod)
            print(f"ok       {pkg} {getattr(m, '__version__', '')}")
        except ImportError:
            ok = False
            print(f"MISSING  {pkg}  -> run scripts/md2pptx.py once, it installs dependencies")
    path, source = resolve_template(template)
    print(f"template {path}  (from {source})")
    if not path.exists():
        ok = False
        print("MISSING  template file not found")
    else:
        try:
            layouts = Layouts(open_template(path), load_sidecar(path).get("layouts"))
            for role, layout in layouts.roles.items():
                print(f"         {role:<10} -> {layout.name if layout else '(drawn on content layout)'}")
        except Exception as exc:  # noqa: BLE001 - report any template problem
            ok = False
            print(f"ERROR    cannot read template: {exc}")
    soffice = _find_soffice()
    print(f"preview  {'LibreOffice found: ' + soffice if soffice else 'LibreOffice not found (only needed for --preview)'}")
    print("status   " + ("ready" if ok else "problems found"))
    return 0 if ok else 1


def _find_soffice() -> str | None:
    """LibreOffice on the PATH, else its usual install folder (the Windows installer adds no PATH entry)."""
    found = shutil.which("soffice") or shutil.which("libreoffice")
    if found:
        return found
    for candidate in (Path(r"C:\Program Files\LibreOffice\program\soffice.exe"),
                      Path(r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"),
                      Path("/Applications/LibreOffice.app/Contents/MacOS/soffice")):
        if candidate.exists():
            return str(candidate)
    return None


def _preview(pptx: Path, out_dir: Path) -> Path | None:
    soffice = _find_soffice()
    if not soffice:
        print("preview skipped: LibreOffice (soffice) is not installed", file=sys.stderr)
        return None
    out_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="md2pptx_lo_") as profile:
        subprocess.run([soffice, f"-env:UserInstallation={Path(profile).as_uri()}", "--headless",
                        "--convert-to", "pdf", "--outdir", str(out_dir), str(pptx)],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
    pdf = out_dir / (pptx.stem + ".pdf")
    if not pdf.exists():
        print("preview failed: LibreOffice could not convert the deck", file=sys.stderr)
        return None
    try:
        import pymupdf  # optional: page images for visual checks
        doc = pymupdf.open(str(pdf))
        for i, page in enumerate(doc, start=1):
            page.get_pixmap(dpi=80).save(str(out_dir / f"{pptx.stem}-{i:02d}.png"))
    except ImportError:
        pass
    return pdf


def main(argv=None) -> int:
    # Guides and reports contain → ≤ · etc.; a Windows pipe defaults to cp1252 and would crash.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(
        prog="md2pptx",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Turn a Markdown file into a branded PowerPoint deck. Tables, charts and "
                    "SmartArt-style diagrams are chosen automatically from the content.",
        epilog=EPILOG)
    ap.add_argument("input", nargs="?", help="Markdown file (or a plan .json with --from-plan)")
    ap.add_argument("-o", "--output", help="output .pptx (default: next to the input)")
    ap.add_argument("-t", "--template", help="brand template .potx/.pptx (see 'template order' below)")
    ap.add_argument("--plan", metavar="JSON", help="also write the slide plan to this file")
    ap.add_argument("--plan-only", action="store_true", help="write the plan (to --plan or stdout) and stop")
    ap.add_argument("--from-plan", action="store_true", help="input is a (possibly edited) plan JSON")
    ap.add_argument("--layout", action="append", metavar="ROLE=NAME",
                    help="force a template layout for a role (title, section, content, title_only, "
                         "closing, quote, blank)")
    ap.add_argument("--layout-map", metavar="JSON", help="JSON file mapping roles to layout names")
    ap.add_argument("--agenda", action="store_true", help="always add an agenda slide")
    ap.add_argument("--no-agenda", action="store_true", help="never add an agenda slide")
    ap.add_argument("--no-closing", action="store_true", help="do not add a closing slide")
    ap.add_argument("--no-auto-notes", action="store_true",
                    help="keep only the author's speaker notes (no generated talking points)")
    ap.add_argument("--no-variants", action="store_true",
                    help="no automatic card variants: cards stay a grid unless a hint says rows")
    ap.add_argument("--no-icons", action="store_true", help="do not add pictograms from the brand icon library")
    ap.add_argument("--no-brand-schemas", action="store_true",
                    help="draw every diagram instead of reusing the brand's ready-made ones")
    ap.add_argument("--a11y", action="store_true",
                    help="after writing the deck, list each slide's alt text and any missing description")
    ap.add_argument("--lang", choices=["en", "fr"], help="language of generated labels (default: detected)")
    ap.add_argument("--footer", help="footer text (default: the deck title)")
    ap.add_argument("--no-footer", action="store_true", help="leave layout footers empty")
    ap.add_argument("--preview", metavar="DIR", help="also export a PDF (and PNGs if pymupdf is installed) "
                                                     "with LibreOffice, for a visual check")
    info = ap.add_argument_group("information")
    info.add_argument("--check", action="store_true", help="diagnose dependencies and the template")
    info.add_argument("--list-layouts", action="store_true", help="show the template's layouts and roles")
    info.add_argument("--kinds", action="store_true", help="list the slide kinds and what they draw")
    info.add_argument("--guide", nargs="?", const="skill", choices=list(GUIDES),
                      help="print the documentation (default: the skill overview); "
                           "'authoring' is the rules for whoever writes the Markdown; "
                           "with -o, save it to that file instead")
    info.add_argument("--version", action="version", version=f"md2pptx {__version__}")
    args = ap.parse_args(argv)

    if args.guide:
        text = GUIDES[args.guide].read_text(encoding="utf-8")
        if args.output:
            Path(args.output).write_text(text, encoding="utf-8")
            print(f"wrote {args.output}")
        else:
            print(text)
        return 0
    if args.kinds:
        for k, v in KINDS.items():
            print(f"{k:<11} {v}")
        return 0
    if args.check:
        return _check(args.template)

    template, source = resolve_template(args.template)
    overrides = {**load_sidecar(template).get("layouts", {}), **_layout_overrides(args)}

    if args.list_layouts:
        print(f"template: {template} (from {source})")
        layouts = Layouts(open_template(template), overrides)
        for row in layouts.describe():
            roles = f"  <- {', '.join(row['roles'])}" if row["roles"] else ""
            print(f"{row['name']!r}: {', '.join(row['placeholders'])}{roles}")
        return 0

    if not args.input:
        ap.error("an input Markdown file is required (see --help)")
    src = Path(args.input)
    if not src.exists():
        ap.error(f"input not found: {src}")

    if args.from_plan:
        plan = json.loads(src.read_text(encoding="utf-8"))
        base_dir = Path(plan.get("source") or src).parent
    else:
        doc = parse_file(src)
        agenda = False if args.no_agenda else (True if args.agenda else None)
        plan = plan_document(doc, agenda=agenda, closing=not args.no_closing, lang=args.lang,
                             auto_notes=not args.no_auto_notes, variants=not args.no_variants)
        base_dir = src.parent

    plan_json = json.dumps(plan, indent=2, ensure_ascii=False)
    if args.plan:
        Path(args.plan).write_text(plan_json, encoding="utf-8")
    if args.plan_only:
        if not args.plan:
            print(plan_json)
        return 0

    out = Path(args.output) if args.output else src.with_suffix(".pptx")
    out.parent.mkdir(parents=True, exist_ok=True)
    footer = None if args.no_footer else (args.footer or plan.get("title"))
    render_plan(plan, out, template=template, layout_overrides=overrides, base_dir=base_dir,
                footer=footer, icons=not args.no_icons, schemas=not args.no_brand_schemas)
    kinds = [s["kind"] for s in plan["slides"]]
    summary = ", ".join(f"{k} x{kinds.count(k)}" for k in dict.fromkeys(kinds))
    print(f"Wrote {out} ({len(kinds)} slides: {summary}).\n"
          f"Detected purpose: {plan['purpose']['label']} · language: {plan.get('lang', 'en')} · "
          f"template: {template.name} ({source}).", file=sys.stderr)
    if plan.get("parts"):
        how = "automatic" if any(p.get("auto") for p in plan["parts"]) else "from <!-- part --> markers"
        print(f"Parts ({how}): " + " | ".join(p["title"] for p in plan["parts"]), file=sys.stderr)
    for w in plan.get("warnings", []):
        print(f"warning: {w}", file=sys.stderr)
    if args.a11y:
        _a11y_report(out)
    if args.preview:
        pdf = _preview(out, Path(args.preview))
        if pdf:
            print(f"Preview: {pdf}", file=sys.stderr)
    return 0


def _a11y_report(path: Path) -> None:
    """Print every described object per slide, and pictures, charts or tables left without one."""
    from pptx import Presentation
    from pptx.oxml.ns import qn
    prs = Presentation(str(path))
    missing = 0
    for n, slide in enumerate(prs.slides, start=1):
        title = slide.shapes.title.text_frame.text if slide.shapes.title is not None else ""
        rows = []
        for el in slide.shapes._spTree.iterchildren(qn("p:grpSp"), qn("p:pic"), qn("p:graphicFrame")):
            c = el.find(".//" + qn("p:cNvPr"))
            if el.find(".//" + qn("p:nvPr") + "/" + qn("p:ph")) is not None and el.tag != qn("p:pic"):
                continue
            descr = c.get("descr", "")
            if not descr and el.tag != qn("p:grpSp"):
                missing += 1
                rows.append(f"   MISSING alt text on {c.get('name')}")
            elif descr:
                rows.append(f"   {descr[:160]}")
        if rows:
            print(f"slide {n} · {title}", file=sys.stderr)
            print("\n".join(rows), file=sys.stderr)
    print(f"accessibility: {missing} object(s) without alt text; icons are marked decorative.", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
