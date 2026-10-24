# /// script
# requires-python = ">=3.10"
# dependencies = ["python-pptx>=1.0", "markdown-it-py>=3.0"]
# ///
"""Construit une présentation PowerPoint (.pptx) modifiable depuis un Markdown.

Le moteur md2pptx (scripts/md2pptx/, repris du skill markdown-to-pptx de Reno)
lit le document, en déduit l'objet et la langue, choisit pour chaque section
un visuel (processus, cycle, frise, cartes, chiffres clés, tableau, graphique
natif...) et applique un gabarit .potx. Ce script vérifie ensuite le fichier
produit : il le rouvre, compte les diapositives, signale une diapositive vide
et un objet sans texte alternatif, puis affiche un rapport JSON.

    uv run scripts/pptx_build.py DOCUMENT.md [--out DOC.pptx] [--template MARQUE.potx] [--plan PLAN.json]
    uv run scripts/pptx_build.py --md2pptx ARGS...   (commande md2pptx d'origine : --check, --list-layouts,
                                                      --plan-only, --from-plan... ; sortie en texte)
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def verify(path: Path, expected: int) -> tuple[int, int, list[str], list[str]]:
    """Rouvre le .pptx : diapositives, objets sans texte alternatif, diapositives vides."""
    from pptx import Presentation
    from pptx.oxml.ns import qn
    errors, warnings, missing = [], [], 0
    try:
        prs = Presentation(str(path))
    except Exception as error:  # noqa: BLE001 - fichier illisible, quel que soit le motif
        return 0, 0, [f"{path.name} illisible : {error}"], []
    slides = len(prs.slides)
    if slides != expected:
        errors.append(f"{slides} diapositive(s) écrite(s) pour {expected} prévue(s)")
    for number, slide in enumerate(prs.slides, start=1):
        text = " ".join(shape.text_frame.text for shape in slide.shapes if shape.has_text_frame).strip()
        if not text and not any(shape.shape_type == 13 for shape in slide.shapes):  # 13 : image
            warnings.append(f"diapositive {number} vide")
        for element in slide.shapes._spTree.iterchildren(qn("p:pic"), qn("p:graphicFrame")):
            props = element.find(".//" + qn("p:cNvPr"))
            if element.find(".//" + qn("p:nvPr") + "/" + qn("p:ph")) is not None and element.tag != qn("p:pic"):
                continue
            if not props.get("descr"):
                missing += 1
                warnings.append(f"diapositive {number} : {props.get('name')} sans texte alternatif")
    return slides, missing, errors, warnings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:2] == ["--md2pptx"]:
        from md2pptx.cli import main as md2pptx_main
        return md2pptx_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("source", type=Path, help="document Markdown")
    parser.add_argument("--out", type=Path, help="fichier .pptx (défaut : même nom que le Markdown)")
    parser.add_argument("--template", type=Path, help="gabarit .potx ou .pptx de la marque")
    parser.add_argument("--plan", type=Path, help="écrit aussi le plan des diapositives (JSON) dans ce fichier")
    parser.add_argument("--lang", choices=["fr", "en"], help="langue des libellés générés (défaut : détectée)")
    args = parser.parse_args()
    report = {"input": str(args.source), "output": None, "template": None, "template_source": None,
              "purpose": None, "lang": None, "slides": 0, "kinds": {}, "parts": [], "missing_alt": 0,
              "errors": [], "warnings": []}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.source.is_file():
        report["errors"].append(f"fichier introuvable : {args.source}")
        return done(1)
    if args.source.suffix.lower() not in (".md", ".markdown"):
        report["errors"].append(f"{args.source.name} : Markdown attendu (.md)")
        return done(1)
    if args.template and not args.template.is_file():
        report["errors"].append(f"gabarit introuvable : {args.template}")
        return done(1)

    from md2pptx.parser import parse_file
    from md2pptx.planner import plan_document
    from md2pptx.render import render_plan
    from md2pptx.template import load_sidecar, resolve_template

    template, source = resolve_template(args.template, start=args.source.resolve().parent)
    report["template"], report["template_source"] = template.name, source
    try:
        plan = plan_document(parse_file(args.source), lang=args.lang)
    except Exception as error:  # noqa: BLE001 - Markdown que le moteur ne sait pas lire
        report["errors"].append(f"plan impossible : {error}")
        return done(1)
    kinds = [s["kind"] for s in plan["slides"]]
    report.update(purpose=plan["purpose"]["label"], lang=plan.get("lang", "en"),
                  kinds={k: kinds.count(k) for k in dict.fromkeys(kinds)},
                  parts=[p["title"] for p in plan.get("parts", [])])
    report["warnings"] += [f"plan : {w}" for w in plan.get("warnings", [])]
    if args.plan:
        args.plan.write_text(json.dumps(plan, indent=2, ensure_ascii=False), encoding="utf-8")
    out = args.out or args.source.with_suffix(".pptx")
    out.parent.mkdir(parents=True, exist_ok=True)
    try:
        render_plan(plan, out, template=template, layout_overrides=load_sidecar(template).get("layouts", {}),
                    base_dir=args.source.parent, footer=plan.get("title"))
    except Exception as error:  # noqa: BLE001 - gabarit ou contenu que le moteur refuse
        report["errors"].append(f"rendu impossible : {error}")
        out.unlink(missing_ok=True)
        return done(1)
    slides, missing, errors, warnings = verify(out, len(kinds))
    report.update(slides=slides, missing_alt=missing)
    report["errors"] += errors
    report["warnings"] += warnings
    if errors:
        out.unlink(missing_ok=True)
        return done(1)
    report["output"] = str(out)
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
