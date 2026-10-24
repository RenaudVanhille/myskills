"""md2pptx: Markdown -> branded PowerPoint with automatic tables, charts and diagrams."""
from .parser import parse_file, parse_markdown
from .planner import infer_purpose, plan_document
from .render import render_plan

__all__ = ["parse_file", "parse_markdown", "infer_purpose", "plan_document", "render_plan", "convert"]
__version__ = "0.5.1"


def convert(markdown_path, output_path=None, template=None, footer=True, layouts=None, icons=True,
            schemas=True, **plan_options):
    """One-call API: convert(markdown_path, output_path, template='brand.potx')."""
    from pathlib import Path
    src = Path(markdown_path)
    plan = plan_document(parse_file(src), **plan_options)
    out = Path(output_path) if output_path else src.with_suffix(".pptx")
    from .template import load_sidecar
    overrides = {**load_sidecar(template).get("layouts", {}), **(layouts or {})}
    footer_text = plan["title"] if footer is True else (footer or None)
    render_plan(plan, out, template=template, layout_overrides=overrides, base_dir=src.parent,
                footer=footer_text, icons=icons, schemas=schemas)
    return out, plan
