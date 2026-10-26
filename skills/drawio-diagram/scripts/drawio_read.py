# /// script
# requires-python = ">=3.10"
# ///
"""Tire d'un schéma draw.io existant la description JSON courte de drawio_build.py.

Pour modifier un schéma existant, le modèle édite une trentaine de lignes de
JSON au lieu de lire le XML ou de refaire le schéma. Le script, et non le
modèle :
- lit chaque page (XML clair ou compressé), titre et légende compris ;
- déduit le rôle de chaque forme de son style (personne, stockage, file,
  système externe en pointillés, conteneur en zone, texte en note...) et sa
  forme (ellipse, losange) ;
- garde l'identifiant, le libellé sans HTML et la position de chaque forme
  (coordonnées absolues), ou une grille approchée (row, col) avec --grid ;
- reprend chaque flèche (de, vers, libellé, asynchrone si en pointillés) et
  signale les flèches sans extrémité, les icônes de fournisseur et les
  formes sans libellé ;
- vérifie la description contre le schéma de drawio_build.py avant de
  l'écrire.

Ensuite : éditer la description, puis `drawio_build.py SCHEMA.json --out
SCHEMA.drawio --export png` reconstruit le schéma aux styles de la charte.

    uv run scripts/drawio_read.py SCHEMA.drawio [--out SCHEMA.json] [--grid] [--force]
"""

import argparse
import html
import json
import re
import sys
import xml.etree.ElementTree as ET
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_drawio import VENDOR, models, style_of  # noqa: E402
from spec_schema import check, input_schema  # noqa: E402

BUILD = Path(__file__).resolve().parent / "drawio_build.py"
# Pas de la grille de drawio_build.py (largeur + écart, hauteur + écart).
STEP_X, STEP_Y = 300, 180
SIMPLE_ID = re.compile(r"^[\w.-]{1,40}$")


def text(value: str | None) -> str:
    """Libellé sans HTML : <br> et <div> en retours à la ligne, entités décodées."""
    value = re.sub(r"<br\s*/?>|</div>|</p>", "\n", value or "", flags=re.I)
    value = html.unescape(re.sub(r"<[^>]+>", "", value)).replace("\xa0", " ")
    return "\n".join(line.strip() for line in value.strip().splitlines() if line.strip())


def role_of(style: dict, raw: str, container: bool) -> tuple[str, str | None]:
    """Rôle de la charte et forme déduits du style draw.io."""
    shape = style.get("shape", "")
    if container or "swimlane" in style or style.get("container") == "1" or "group" in style:
        return "zone", None
    if "text" in style and style.get("fillColor", "none") in ("none", ""):
        return "note", None
    if "umlActor" in shape:
        return "person", None
    if "cylinder" in shape or "datastore" in shape:
        return "db", None
    if "parallelogram" in shape or "queue" in shape:
        return "queue", None
    if style.get("fillColor", "").lower() == "#fee2e2":
        return "alert", None
    form = "ellipse" if "ellipse" in style or shape == "ellipse" else "diamond" if "rhombus" in style else None
    if style.get("dashed") == "1":
        return "external", form
    return "system", form


def read_page(model: ET.Element, name: str, grid: bool, warnings: list[str]) -> dict:
    cells = {c.get("id"): c for c in model.iter("mxCell")}
    parents = {c.get("parent") for c in cells.values()}
    page: dict = {"name": name}
    nodes, arrows, ids, vendor = [], [], {}, []

    def origin(cell: ET.Element) -> tuple[float, float]:
        """Position absolue : celle d'une forme dans un conteneur est relative à lui."""
        x = y = 0.0
        while cell is not None and cell.get("vertex") == "1":
            geo = cell.find("mxGeometry")
            if geo is not None:
                x, y = x + float(geo.get("x", 0)), y + float(geo.get("y", 0))
            cell = cells.get(cell.get("parent"))
        return x, y

    for cid, cell in cells.items():
        if cell.get("vertex") != "1":
            continue
        raw, style, label = cell.get("style") or "", style_of(cell), text(cell.get("value"))
        if cid == "title" or (not page.get("title") and "text" in style and float(style.get("fontSize", 12)) >= 18):
            page["title"] = label
            continue
        if cid.startswith("legend") or label == "Légende":
            continue
        if any(v in raw for v in VENDOR):
            vendor.append(cid)
        role, form = role_of(style, raw, cid in parents)
        if not label and role not in ("zone", "note"):
            warnings.append(f"{name} : forme {cid} sans libellé")
        new_id = cid if SIMPLE_ID.match(cid) else f"n{len(ids) + 1}"
        ids[cid] = new_id
        geo = cell.find("mxGeometry")
        x, y = origin(cell)
        w, h = (float(geo.get("width", 0)), float(geo.get("height", 0))) if geo is not None else (0.0, 0.0)
        item = {"id": new_id, "role": role, "label": label}
        if form:
            item["shape"] = form
        item.update({"x": round(x), "y": round(y), "w": round(w) or 1, "h": round(h) or 1})
        nodes.append(item)
    if vendor:
        warnings.append(f"{name} : {len(vendor)} icône(s) de fournisseur ({', '.join(vendor[:5])}"
                        f"{'...' if len(vendor) > 5 else ''}) : décrivez ce schéma avec cloud-architecture "
                        "(cloud_build.py), qui garde les icônes ; drawio_build.py les remplace par la charte")
    if grid and nodes:
        left, top = min(n["x"] for n in nodes), min(n["y"] for n in nodes)
        for n in nodes:
            if n["role"] != "zone":
                n["row"], n["col"] = round((n["y"] - top) / STEP_Y), round((n["x"] - left) / STEP_X)
                for key in ("x", "y", "w", "h"):
                    n.pop(key)
    for cid, cell in cells.items():
        if cell.get("edge") != "1":
            continue
        source, target = cell.get("source"), cell.get("target")
        if source not in ids or target not in ids:
            warnings.append(f"{name} : flèche {cid} sans forme à une extrémité, ignorée")
            continue
        arrow = {"from": ids[source], "to": ids[target]}
        label = text(cell.get("value"))
        if label:
            arrow["label"] = label
        if style_of(cell).get("dashed") == "1":
            arrow["style"] = "async"
        arrows.append(arrow)
    page["elements"] = nodes + arrows
    return page


def compact(spec: dict) -> str:
    """JSON lisible et court : un élément par ligne."""
    def elements(items: list, indent: str) -> str:
        return "[\n" + ",\n".join(indent + "  " + json.dumps(e, ensure_ascii=False) for e in items) + "\n" + indent + "]"

    def page(value: dict, indent: str) -> str:
        parts = [f'{indent}  "{k}": ' + (elements(v, indent + "  ") if k == "elements" else
                                         "[\n" + ",\n".join(page(p, indent + "    ") for p in v) + "\n" + indent + "  ]"
                                         if k == "pages" else json.dumps(v, ensure_ascii=False))
                 for k, v in value.items()]
        return indent + "{\n" + ",\n".join(parts) + "\n" + indent + "}"
    return page(spec, "")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("drawio", type=Path)
    parser.add_argument("--out", type=Path, help="description JSON (défaut : SCHEMA.json à côté du .drawio)")
    parser.add_argument("--grid", action="store_true",
                        help="grille approchée (row, col) au lieu des coordonnées : drawio_build.py refait la mise en page")
    parser.add_argument("--force", action="store_true", help="remplacer une description existante")
    args = parser.parse_args()
    out = args.out or args.drawio.with_name(args.drawio.name.removesuffix(".drawio") + ".json")
    report = {"input": str(args.drawio), "output": None, "pages": 0, "elements": 0, "arrows": 0,
              "errors": [], "warnings": []}
    try:
        pages = models(ET.parse(args.drawio).getroot())
    except (ET.ParseError, ValueError, zlib.error, OSError) as error:
        report["errors"].append(f"{args.drawio} illisible : {error}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    if out.exists() and not args.force:
        report["errors"].append(f"{out} existe déjà : --force pour le remplacer, ou --out")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    read = [read_page(model, name, args.grid, report["warnings"]) for name, model in pages]
    if len(read) == 1:
        spec = {k: v for k, v in read[0].items() if k != "name"}
    else:
        spec = {"title": read[0].get("title", args.drawio.stem), "pages": read}
    items = [e for p in read for e in p["elements"]]
    report["pages"] = len(read)
    report["arrows"] = sum("from" in e for e in items)
    report["elements"] = len(items) - report["arrows"]
    schema = input_schema(BUILD)
    report["errors"] = [e.replace("description", "description produite", 1) for e in check(spec, schema, schema)]
    if not items:
        report["errors"].append("aucune forme lue : schéma vide")
    if report["errors"]:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    out.write_text(compact(spec) + "\n", encoding="utf-8")
    report["output"] = str(out)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
