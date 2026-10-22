# /// script
# requires-python = ">=3.10"
# ///
"""Construit un schéma draw.io à partir d'une description simplifiée.

Même description JSON que excalidraw_build.py (skill excalidraw-diagram) :
titre, éléments par rôle de la charte, flèches par identifiant. Sortie : un
fichier `.drawio` en XML clair, aux styles de la charte, avec titre et
légende, que l'on ouvre et retouche dans draw.io. Le fichier est ensuite
vérifié comme par check_drawio.py ; le rapport JSON reprend ses erreurs et
avertissements.

Une description peut aussi contenir `pages` : une liste de descriptions
(`name`, `title`, `elements`), une page draw.io par vue.

    uv run scripts/drawio_build.py SCHEMA.json [--out SCHEMA.drawio]
"""

import argparse
import json
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

from check_drawio import check

TEXT, ARROW = "#1f2937", "#374151"
BASE = "whiteSpace=wrap;html=1;fontColor=#1f2937;fontSize=14;"
# Rôle -> (style draw.io de la charte, nom dans la légende).
ROLES = {
    "person": ("shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
               "fillColor=#fef3c7;strokeColor=#b45309;fontColor=#1f2937;fontSize=14;", "Personne"),
    "system": ("rounded=1;" + BASE + "fillColor=#dbeafe;strokeColor=#1d4ed8;", "Notre système"),
    "external": ("rounded=1;dashed=1;" + BASE + "fillColor=#f3f4f6;strokeColor=#6b7280;", "Système externe"),
    "db": ("shape=cylinder3;boundedLbl=1;size=12;" + BASE + "fillColor=#dcfce7;strokeColor=#15803d;", "Stockage"),
    "queue": ("shape=parallelogram;perimeter=parallelogramPerimeter;" + BASE
              + "fillColor=#f3e8ff;strokeColor=#7e22ce;", "File, évènement"),
    "alert": ("rounded=0;" + BASE + "fillColor=#fee2e2;strokeColor=#b91c1c;", "Point de vigilance"),
    "zone": ("rounded=1;dashed=1;whiteSpace=wrap;html=1;fillColor=none;strokeColor=#9ca3af;"
             "verticalAlign=top;align=left;spacingLeft=8;fontColor=#6b7280;fontSize=14;", None),
    "note": ("text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontColor=#1f2937;fontSize=14;", None),
}
SHAPES = {"rectangle": "rounded=1;", "ellipse": "ellipse;", "diamond": "rhombus;"}
EDGE = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#374151;fontSize=12;"
SYNC, ASYNC = EDGE + "endArrow=block;endFill=1;", EDGE + "dashed=1;endArrow=open;"
TITLE = "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;fontColor=#1f2937;"
W, H, GAP_X, GAP_Y = 180, 80, 120, 100


def text_size(text: str, size: int) -> tuple[float, float]:
    lines = text.split("\n")
    return max(len(l) for l in lines) * size * 0.6, len(lines) * size * 1.4


def label(text: str) -> str:
    return text.replace("\n", "<br>")


def cell(root: ET.Element, cid: str, value: str, style: str, x: float, y: float,
         w: float, h: float) -> None:
    node = ET.SubElement(root, "mxCell", id=cid, value=value, style=style, vertex="1", parent="1")
    ET.SubElement(node, "mxGeometry", x=f"{x:g}", y=f"{y:g}", width=f"{w:g}", height=f"{h:g}",
                  attrib={"as": "geometry"})


def build_page(spec: dict, name: str, errors: list, warnings: list) -> ET.Element:
    diagram = ET.Element("diagram", id=f"p-{name}", name=name)
    model = ET.SubElement(diagram, "mxGraphModel", grid="1", gridSize="10", page="0")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    items = spec.get("elements", [])
    nodes = [i for i in items if "from" not in i]
    arrows = [i for i in items if "from" in i]
    # Les zones d'abord : draw.io dessine les cellules dans l'ordre, elles restent derrière.
    nodes.sort(key=lambda i: 0 if i.get("role") == "zone" else 1)

    boxes, roles_used = {}, []
    for item in nodes:
        cid = str(item.get("id") or f"n{len(boxes) + 1}")
        if cid in boxes:
            errors.append(f"{name} : identifiant en double « {cid} »")
            continue
        role = item.get("role", "system")
        if role not in ROLES:
            errors.append(f"{name} : {cid}, rôle inconnu « {role} » ({', '.join(ROLES)})")
            role = "system"
        style = ROLES[role][0]
        if item.get("shape") in SHAPES and role not in ("zone", "note"):
            style = SHAPES[item["shape"]] + style.split(";", 1)[1]
        text = str(item.get("label", ""))
        tw, th = text_size(text, 14) if text else (0, 0)
        w = float(item.get("w", max(W, tw + 30)))
        h = float(item.get("h", max(H, th + 20)))
        if role == "person":
            w, h = float(item.get("w", 40)), float(item.get("h", 70))
        if "x" in item and "y" in item:
            x, y = float(item["x"]), float(item["y"])
        else:
            x = float(item.get("col", 0)) * (W + GAP_X)
            y = float(item.get("row", 0)) * (H + GAP_Y)
            if role == "person":
                x, y = x + (W - w) / 2, y
        cell(root, cid, label(text), style, x, y, w, h)
        boxes[cid] = (x, y, w, h)
        if role not in ("zone", "note") and role not in roles_used:
            roles_used.append(role)

    for index, item in enumerate(arrows, 1):
        source, target = str(item["from"]), str(item.get("to"))
        cid = str(item.get("id") or f"{source}-{target}")
        if source not in boxes or target not in boxes:
            errors.append(f"{name} : flèche {cid}, forme inconnue ({source} -> {target})")
            continue
        node = ET.SubElement(root, "mxCell", id=cid, value=label(str(item.get("label", ""))),
                             style=ASYNC if item.get("style") == "async" else SYNC,
                             edge="1", parent="1", source=source, target=target)
        ET.SubElement(node, "mxGeometry", relative="1", attrib={"as": "geometry"})

    count = len([n for n in nodes if n.get("role") not in ("zone", "note")])
    if str(spec.get("audience", "")).startswith("non") and count > 7:
        warnings.append(f"{name} : {count} éléments pour un public non technique (7 maximum)")
    shown = list(boxes.values()) or [(0, 0, 0, 0)]
    left, top = min(b[0] for b in shown), min(b[1] for b in shown)
    right = max(b[0] + b[2] for b in shown)
    if spec.get("title"):
        cell(root, "title", str(spec["title"]), TITLE, left, top - 60, max(400, len(spec["title"]) * 12), 30)
    legend = spec.get("legend", "auto")
    has_async = any(a.get("style") == "async" for a in arrows)
    if legend and (legend is True or len(roles_used) > 1 or has_async):
        lx = right + 80
        cell(root, "legend-title", "Légende", "text;html=1;fontStyle=1;align=left;fontColor=#1f2937;fontSize=14;",
             lx, top, 120, 20)
        side = "labelPosition=right;verticalLabelPosition=middle;align=left;spacingLeft=8;"
        for row, role in enumerate(roles_used, 1):
            style = ROLES[role][0].replace("verticalLabelPosition=bottom;verticalAlign=top;", "")
            cell(root, f"legend-{role}", ROLES[role][1], side + style.replace("fontSize=14;", "fontSize=12;"),
                 lx, top + row * 32, 30, 20)
        if has_async:
            cell(root, "legend-async", "Asynchrone", side + "shape=line;dashed=1;html=1;strokeColor=#374151;"
                 "fontColor=#1f2937;fontSize=12;", lx, top + (len(roles_used) + 1) * 32, 30, 20)
    return diagram


def build(spec: dict) -> tuple[ET.Element, list[str], list[str]]:
    errors, warnings = [], []
    mxfile = ET.Element("mxfile", host="myskills")
    pages = spec.get("pages") or [spec]
    for number, page in enumerate(pages, 1):
        name = str(page.get("name") or page.get("title") or f"Page-{number}")
        mxfile.append(build_page({"audience": spec.get("audience"), **page}, name, errors, warnings))
    return mxfile, errors, warnings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path)
    parser.add_argument("--out", type=Path, help="fichier .drawio (défaut : même nom)")
    args = parser.parse_args()
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)]}, ensure_ascii=False))
        return 1
    mxfile, errors, warnings = build(spec)
    name = args.spec.name.removesuffix(".json").removesuffix(".diagram")
    out = args.out or args.spec.with_name(name + ".drawio")
    report = {"input": str(args.spec), "output": None, "pages": len(mxfile), "shapes": 0,
              "errors": errors, "warnings": warnings}
    if not errors:
        ET.indent(mxfile)
        ET.ElementTree(mxfile).write(out, encoding="utf-8", xml_declaration=False)
        checked = check(out)
        report.update(output=str(out), shapes=checked["shapes"])
        report["errors"] += checked["errors"]
        report["warnings"] += checked["warnings"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
