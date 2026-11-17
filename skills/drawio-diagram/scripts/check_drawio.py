# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie un fichier draw.io (.drawio) avant export.

Erreurs : XML illisible, identifiants en double, parent ou extrémité de flèche
introuvable, forme sans géométrie. Avertissements : formes qui se chevauchent,
forme sans libellé, flèche sans extrémité, couleur hors charte (sauf
icônes et groupes officiels AWS, Azure, GCP, Kubernetes), pas de titre ; et
lisibilité, estimée sans rendu : libellé trop long pour sa forme, flèches
qui se croisent, flèche qui passe sous une forme. `review_image` dit s'il
faut ouvrir l'image exportée : seulement quand la lisibilité est douteuse.
Lit aussi les diagrammes compressés. Un fichier compressé ou écrit sur une
seule ligne (enregistré par un éditeur, collé à la main) est signalé :
`--pretty` le réécrit en XML clair et indenté, comme les scripts de
construction, et seulement s'il change (`reformatted`) : le même schéma
donne toujours le même fichier, sans écart en diff. Affiche un rapport JSON.
Usage :
    uv run scripts/check_drawio.py [--pretty] SCHEMA.drawio [...]
"""

import io

import base64
import json
import math
import re
import sys
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from script_report import print_report  # noqa: E402

# Couleurs de la charte, extraites de shared/references/style.md par scripts/build.py.
CHARTER = set(json.loads((Path(__file__).resolve().parent / "lib" / "charter.json").read_text(encoding="utf-8"))
              ["colors"]) | {"#000000", "none", "default"}
# Icônes et groupes officiels des fournisseurs cloud (AWS, Azure, GCP, Kubernetes) : leurs couleurs
# sont imposées par le fournisseur, pas par la charte.
VENDOR = ("mxgraph.aws4.", "mxgraph.gcp2.", "mxgraph.kubernetes.", "mxgraph.azure", "image=img/lib/",
          "image=data:image/", "vendor=1")


def style_of(cell: ET.Element) -> dict:
    parts = [p for p in (cell.get("style") or "").split(";") if p]
    return {k: v for k, _, v in (p.partition("=") for p in parts)}


def models(root: ET.Element) -> list[tuple[str, ET.Element]]:
    if root.tag == "mxGraphModel":
        return [("Page-1", root)]
    if root.tag != "mxfile":
        raise ValueError(f"racine inattendue <{root.tag}> (mxfile attendu)")
    found = []
    for diagram in root.findall("diagram"):
        name = diagram.get("name", "?")
        model = diagram.find("mxGraphModel")
        if model is None and (diagram.text or "").strip():
            raw = zlib.decompress(base64.b64decode(diagram.text.strip()), -15)
            model = ET.fromstring(unquote(raw.decode("utf-8")))
        if model is None:
            raise ValueError(f"page « {name} » vide")
        found.append((name, model))
    return found


def box(cell: ET.Element) -> tuple[float, float, float, float] | None:
    geo = cell.find("mxGeometry")
    if geo is None:
        return None
    return tuple(float(geo.get(k, 0)) for k in ("x", "y", "width", "height"))


CHAR = 0.55   # largeur moyenne d'un caractère, en part de la taille de police
LINE = 1.3    # hauteur d'une ligne, en part de la taille de police
SHOWN = 3     # exemples cités par avertissement de lisibilité


def label_fits(label: str, style: dict, w: float, h: float) -> bool:
    """Le libellé tient-il dans la forme (estimation sans rendu) ?"""
    size = float(style.get("fontSize", 12))
    room = max(w - 8, 1)
    if style.get("whiteSpace") != "wrap":
        return len(label) * size * CHAR <= w
    if max((len(word) for word in label.split()), default=0) * size * CHAR > room:
        return False
    return math.ceil(len(label) * size * CHAR / room) * size * LINE <= h + 2


def route(edge: ET.Element, start: tuple, end: tuple) -> list[tuple[float, float]]:
    """Points de la flèche : points de passage donnés, sinon coude orthogonal au milieu (approché)."""
    geo = edge.find("mxGeometry")
    points = [(float(p.get("x", 0)), float(p.get("y", 0)))
              for p in (geo.findall("Array/mxPoint") if geo is not None else [])]
    if points or "orthogonalEdgeStyle" not in (edge.get("style") or ""):
        return [start, *points, end]
    (sx, sy), (tx, ty) = start, end
    if abs(tx - sx) >= abs(ty - sy):
        mid = (sx + tx) / 2
        return [start, (mid, sy), (mid, ty), end]
    mid = (sy + ty) / 2
    return [start, (sx, mid), (tx, mid), end]


def crosses(a, b, c, d) -> bool:
    """Les segments ab et cd se coupent-ils strictement ?"""
    def side(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return side(a, b, c) * side(a, b, d) < 0 and side(c, d, a) * side(c, d, b) < 0


def through(a, b, rect) -> bool:
    """Le segment ab traverse-t-il le rectangle (réduit de 2 px) ?"""
    x, y, w, h = rect[0] + 2, rect[1] + 2, rect[2] - 4, rect[3] - 4
    if w <= 0 or h <= 0:
        return False
    corners = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
    inside = lambda p: x < p[0] < x + w and y < p[1] < y + h  # noqa: E731
    return inside(a) or inside(b) or any(crosses(a, b, corners[i], corners[(i + 1) % 4]) for i in range(4))


def readability(name: str, ids: dict, warnings: list) -> bool:
    """Libellés trop longs, flèches croisées, flèches sous une forme ; vrai si l'image est à relire."""
    absolute: dict[str, tuple] = {}

    def place(cid):
        if cid in absolute:
            return absolute[cid]
        holder, cell = ids[cid]
        geometry = box(cell) or (0, 0, 0, 0)
        par = cell.get("parent")
        ox, oy = place(par)[:2] if par in ids and ids[par][1].get("vertex") == "1" else (0, 0)
        absolute[cid] = (geometry[0] + ox, geometry[1] + oy, geometry[2], geometry[3])
        return absolute[cid]

    parents = {cell.get("parent") for _, cell in ids.values() if cell.get("vertex") == "1"}
    long, leaves = [], {}
    for cid, (holder, cell) in ids.items():
        if cell.get("vertex") != "1" or box(cell) is None:
            continue
        raw = cell.get("style") or ""
        style = style_of(cell)
        if raw.startswith("text") or any(mark in raw for mark in VENDOR) or "image" in style.get("shape", ""):
            continue
        label = holder.get("label") if holder is not cell else cell.get("value")
        label = " ".join(re.sub(r"<[^>]+>", " ", label or "").split())
        x, y, w, h = place(cid)
        outside = style.get("labelPosition", "center") != "center" or \
            style.get("verticalLabelPosition", "middle") != "middle"  # libellé à côté de la forme
        if label and cid not in parents and not outside and not label_fits(label, style, w, h):
            long.append(cid)
        if cid not in parents:
            leaves[cid] = (x, y, w, h)
    edges = []
    for cid, (holder, cell) in ids.items():
        source, target = cell.get("source"), cell.get("target")
        if cell.get("edge") == "1" and source in leaves and target in leaves:
            centre = lambda r: (r[0] + r[2] / 2, r[1] + r[3] / 2)  # noqa: E731
            points = route(cell, centre(leaves[source]), centre(leaves[target]))
            edges.append((cid, {source, target}, list(zip(points, points[1:]))))
    crossing = [f"{a}×{b}" for i, (a, ea, sa) in enumerate(edges) for b, eb, sb in edges[i + 1:]
                if not ea & eb and any(crosses(p, q, r, s) for p, q in sa for r, s in sb)]
    hidden = [f"{e}/{v}" for e, ends, segments in edges for v, rect in leaves.items()
              if v not in ends and any(through(p, q, rect) for p, q in segments)]
    for items, text in ((long, "libellé trop long pour sa forme"), (crossing, "flèches qui se croisent"),
                        (hidden, "flèche qui passe sous une forme")):
        if items:
            more = f" (+{len(items) - SHOWN})" if len(items) > SHOWN else ""
            warnings.append(f"{name} : lisibilité, {text} : {', '.join(items[:SHOWN])}{more}")
    return bool(long or crossing or hidden)


def check_page(name: str, model: ET.Element, errors: list, warnings: list) -> int:
    root = model.find("root")
    if root is None:
        errors.append(f"{name} : pas d'élément <root>")
        return 0, False
    ids = {}
    for parent in root:
        cell = parent if parent.tag == "mxCell" else parent.find("mxCell")
        cid = parent.get("id") if parent.tag != "mxCell" else cell.get("id")
        if cell is None or not cid:
            continue
        if cid in ids:
            errors.append(f"{name} : identifiant en double « {cid} »")
        ids[cid] = (parent, cell)
    vertices, has_title = [], False
    for cid, (holder, cell) in ids.items():
        par = cell.get("parent")
        if par and par not in ids:
            errors.append(f"{name} : {cid} a un parent introuvable « {par} »")
        style = style_of(cell)
        label = holder.get("label") if holder is not cell else cell.get("value")
        label = re.sub(r"<[^>]+>", " ", label or "").strip()
        vendor = any(mark in (cell.get("style") or "") for mark in VENDOR)
        for key in ("fillColor", "strokeColor", "fontColor") if not vendor else ():
            color = style.get(key, "").lower()
            if color and color not in CHARTER:
                warnings.append(f"{name} : {cid} utilise {key}={color}, hors charte")
        if cell.get("edge") == "1":
            for end in ("source", "target"):
                ref = cell.get(end)
                if ref and ref not in ids:
                    errors.append(f"{name} : flèche {cid}, {end} introuvable « {ref} »")
                elif not ref:
                    warnings.append(f"{name} : flèche {cid} sans {end} (non attachée)")
        elif cell.get("vertex") == "1":
            geometry = box(cell)
            if geometry is None:
                errors.append(f"{name} : forme {cid} sans mxGeometry")
                continue
            if "text" in (cell.get("style") or "").split(";")[:1]:
                if float(style.get("fontSize", 12)) >= 18:
                    has_title = True
                continue
            if not label and "image" not in style.get("shape", "") and "image" not in style:
                warnings.append(f"{name} : forme {cid} sans libellé")
            vertices.append((cid, par, geometry))
    for i, (a, pa, (ax, ay, aw, ah)) in enumerate(vertices):
        for b, pb, (bx, by, bw, bh) in vertices[i + 1:]:
            if pa != pb:
                continue
            inter = ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah
            contains = (ax <= bx and ay <= by and bx + bw <= ax + aw and by + bh <= ay + ah) or \
                       (bx <= ax and by <= ay and ax + aw <= bx + bw and ay + ah <= by + bh)
            if inter and not contains:
                warnings.append(f"{name} : {a} et {b} se chevauchent")
    if not has_title:
        warnings.append(f"{name} : pas de titre (texte de 18 px ou plus)")
    overlap = any("se chevauchent" in w for w in warnings)
    review = readability(name, ids, warnings) or overlap
    return len(vertices), review


def unreadable(path: Path) -> str | None:
    """Pourquoi le fichier est illisible en texte : page compressée ou formes sur une même ligne ; None sinon."""
    text = path.read_text(encoding="utf-8", errors="replace")
    if re.search(r"<diagram\b[^>]*>\s*[A-Za-z0-9+/=]{16,}\s*</diagram>", text):
        return "diagramme compressé"
    if any(line.count("<mxCell") > 1 for line in text.splitlines()):
        return "XML sur une seule ligne"
    return None


def prettify(path: Path) -> bool:
    """Réécrit le fichier en XML clair et indenté (pages décompressées), seulement s'il change ; rend s'il a changé."""
    root = ET.parse(path).getroot()
    for name, model in models(root):
        diagram = next((d for d in root.findall("diagram") if d.get("name", "?") == name), None)
        if diagram is not None and diagram.find("mxGraphModel") is None:
            diagram.text = None
            diagram.append(model)
    ET.indent(root)
    buffer = io.BytesIO()
    ET.ElementTree(root).write(buffer, encoding="utf-8", xml_declaration=False)
    if buffer.getvalue() == path.read_bytes():
        return False
    path.write_bytes(buffer.getvalue())
    return True


def check(path: Path, pretty: bool = False) -> dict:
    report = {"file": str(path), "pages": 0, "shapes": 0, "review_image": False, "errors": [], "warnings": []}
    try:
        if pretty:
            report["reformatted"] = prettify(path)
        pages = models(ET.parse(path).getroot())
    except (ET.ParseError, ValueError, zlib.error, OSError) as error:
        report["errors"].append(f"XML illisible : {error}")
        return report
    reason = unreadable(path)
    if reason:
        report["warnings"].append(f"{reason} : illisible en diff ; check_drawio.py --pretty le réécrit en XML indenté")
    report["pages"] = len(pages)
    for name, model in pages:
        shapes, review = check_page(name, model, report["errors"], report["warnings"])
        report["shapes"] += shapes
        report["review_image"] = report["review_image"] or review
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    pretty = "--pretty" in args
    files = [a for a in args if a != "--pretty"]
    if not files:
        print_report([], ["aucun fichier : uv run scripts/check_drawio.py [--pretty] SCHEMA.drawio [...]"])
        return 1
    reports = [check(Path(p), pretty) for p in files]
    print_report(reports)
    return 1 if any(r["errors"] for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
