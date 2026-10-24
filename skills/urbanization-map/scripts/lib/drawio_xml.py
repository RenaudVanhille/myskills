"""Écriture du XML draw.io commune aux scripts qui construisent un .drawio.

Les constructeurs (drawio_build.py, cloud_build.py, pos_build.py) ne gardent
que leur mise en page et leurs styles ; la structure du fichier, des pages,
des formes et des flèches, la mesure du texte et l'écriture sont ici.

    mxfile = new_file()
    diagram, root = new_page("p-vue", "Vue")
    vertex(root, "a", "API", style, x, y, w, h)
    node, geometry = edge(root, "f1", "HTTPS", style, "a", "b")
    mxfile.append(diagram); write(mxfile, out)

Source : shared/scripts/drawio_xml.py, copiée dans scripts/lib/ des skills
qui écrivent du draw.io par scripts/build.py. Ne modifiez pas les copies.
"""

import xml.etree.ElementTree as ET
from pathlib import Path

# Largeur moyenne d'un caractère et hauteur de ligne, en fraction de la taille de police.
CHAR_WIDTH, LINE_HEIGHT = 0.6, 1.4


def new_file() -> ET.Element:
    return ET.Element("mxfile", host="myskills")


def new_page(page_id: str, name: str) -> tuple[ET.Element, ET.Element]:
    """Page draw.io (diagram) et sa racine, avec les cellules 0 et 1 attendues par draw.io."""
    diagram = ET.Element("diagram", id=page_id, name=name)
    model = ET.SubElement(diagram, "mxGraphModel", grid="1", gridSize="10", page="0")
    root = ET.SubElement(model, "root")
    ET.SubElement(root, "mxCell", id="0")
    ET.SubElement(root, "mxCell", id="1", parent="0")
    return diagram, root


def vertex(root: ET.Element, cid: str, value: str, style: str, x: float, y: float, w: float, h: float,
           parent: str = "1") -> ET.Element:
    """Forme, conteneur ou texte à la position donnée (relative au parent)."""
    node = ET.SubElement(root, "mxCell", id=cid, value=value, style=style, vertex="1", parent=parent)
    ET.SubElement(node, "mxGeometry", x=f"{x:g}", y=f"{y:g}", width=f"{w:g}", height=f"{h:g}",
                  attrib={"as": "geometry"})
    return node


def edge(root: ET.Element | None, cid: str, value: str, style: str, source: str, target: str,
         parent: str = "1") -> tuple[ET.Element, ET.Element]:
    """Flèche entre deux cellules ; root None la crée sans l'ajouter (pour la placer soi-même)."""
    attrs = {"id": cid, "value": value, "style": style, "edge": "1", "parent": parent,
             "source": source, "target": target}
    node = ET.Element("mxCell", attrs) if root is None else ET.SubElement(root, "mxCell", attrs)
    geometry = ET.SubElement(node, "mxGeometry", relative="1", attrib={"as": "geometry"})
    return node, geometry


def waypoints(geometry: ET.Element, points: list[tuple[float, float]]) -> None:
    """Points de passage d'une flèche."""
    array = ET.SubElement(geometry, "Array", attrib={"as": "points"})
    for px, py in points:
        ET.SubElement(array, "mxPoint", x=f"{px:g}", y=f"{py:g}")


def br(text: str) -> str:
    """Retours à la ligne en <br>, pour une forme en html=1."""
    return text.replace("\n", "<br>")


def html(text: str) -> str:
    """Texte échappé pour une forme en html=1 (& < > affichés tels quels)."""
    return br(text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def text_width(text: str, size: float = 12) -> float:
    """Largeur approchée du texte le plus long de ses lignes."""
    return max((len(line) for line in text.split("\n")), default=0) * size * CHAR_WIDTH


def text_lines(text: str) -> int:
    return len(text.split("\n")) if text else 0


def text_size(text: str, size: float) -> tuple[float, float]:
    """Largeur et hauteur approchées d'un texte de plusieurs lignes."""
    return text_width(text, size), len(text.split("\n")) * size * LINE_HEIGHT


def write(mxfile: ET.Element, out: Path) -> None:
    """Écrit le fichier en XML clair et indenté (diff lisible, modifiable par drawio-diagram)."""
    ET.indent(mxfile)
    ET.ElementTree(mxfile).write(out, encoding="utf-8", xml_declaration=False)
