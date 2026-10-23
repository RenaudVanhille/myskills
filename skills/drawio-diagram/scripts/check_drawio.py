# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie un fichier draw.io (.drawio) avant export.

Erreurs : XML illisible, identifiants en double, parent ou extrémité de flèche
introuvable, forme sans géométrie. Avertissements : formes qui se chevauchent,
forme sans libellé, flèche sans extrémité, couleur hors charte (sauf
icônes et groupes officiels AWS, Azure, GCP, Kubernetes), pas de titre.
Lit aussi les diagrammes compressés. Affiche un rapport JSON. Usage :
    uv run scripts/check_drawio.py SCHEMA.drawio [...]
"""

import base64
import json
import re
import sys
import zlib
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import unquote

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


def check_page(name: str, model: ET.Element, errors: list, warnings: list) -> int:
    root = model.find("root")
    if root is None:
        errors.append(f"{name} : pas d'élément <root>")
        return 0
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
    return len(vertices)


def check(path: Path) -> dict:
    report = {"file": str(path), "pages": 0, "shapes": 0, "errors": [], "warnings": []}
    try:
        pages = models(ET.parse(path).getroot())
    except (ET.ParseError, ValueError, zlib.error, OSError) as error:
        report["errors"].append(f"XML illisible : {error}")
        return report
    report["pages"] = len(pages)
    for name, model in pages:
        report["shapes"] += check_page(name, model, report["errors"], report["warnings"])
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    reports = [check(Path(p)) for p in sys.argv[1:]]
    # Un objet par ligne : lisible, et sans l'indentation qui coûte des tokens.
    print("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in reports) + "\n]")
    return 1 if any(r["errors"] for r in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
