# /// script
# requires-python = ">=3.10"
# ///
"""Construit une scène Excalidraw à partir d'une description simplifiée.

Entrée (JSON) : titre, éléments par rôle de la charte, flèches par identifiant.
Sortie : un fichier `.excalidraw` complet (couleurs de la charte, textes centrés,
flèches attachées aux formes, légende), que l'on ouvre dans Excalidraw ou
Obsidian. Affiche un rapport JSON avec les erreurs et avertissements.

    uv run scripts/excalidraw_build.py SCHEMA.json [--out SCHEMA.excalidraw] [--export png|svg]

Avec --export, la scène est aussi exportée (skill diagram-export) dans le même
appel ; le rapport donne l'image dans `export`.
"""

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from skill_paths import export_image  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

ROLES = {
    "person": ("#fef3c7", "#b45309", "ellipse", "solid", "Personne"),
    "system": ("#dbeafe", "#1d4ed8", "rectangle", "solid", "Notre système"),
    "external": ("#f3f4f6", "#6b7280", "rectangle", "dashed", "Système externe"),
    "db": ("#dcfce7", "#15803d", "rectangle", "solid", "Stockage"),
    "queue": ("#f3e8ff", "#7e22ce", "rectangle", "solid", "File, évènement"),
    "alert": ("#fee2e2", "#b91c1c", "rectangle", "solid", "Point de vigilance"),
    "zone": ("transparent", "#9ca3af", "rectangle", "dashed", None),
    "note": ("transparent", "#1f2937", "text", "solid", None),
}
FONTS = {"excalifont": 5, "nunito": 6, "helvetica": 2}
TEXT, ARROW = "#1f2937", "#374151"
W, H, GAP_X, GAP_Y = 180, 80, 120, 100


class Scene:
    def __init__(self, font: int, sober: bool):
        self.elements, self.font, self.rough = [], font, 0 if sober else 1
        self.rng = random.Random(42)

    def base(self, kind: str, eid: str, x: float, y: float, w: float, h: float, **extra) -> dict:
        element = {
            "id": eid, "type": kind, "x": round(x, 2), "y": round(y, 2),
            "width": round(w, 2), "height": round(h, 2), "angle": 0,
            "strokeColor": TEXT, "backgroundColor": "transparent", "fillStyle": "solid",
            "strokeWidth": 2, "strokeStyle": "solid", "roughness": self.rough, "opacity": 100,
            "groupIds": [], "frameId": None, "roundness": None,
            "seed": self.rng.randint(1, 2**31 - 1), "version": 1,
            "versionNonce": self.rng.randint(1, 2**31 - 1), "isDeleted": False,
            "boundElements": [], "updated": 1, "link": None, "locked": False,
        }
        element.update(extra)
        self.elements.append(element)
        return element

    def text(self, eid: str, text: str, x: float, y: float, size: int,
             container: dict | None = None, align: str = "center", color: str = TEXT) -> dict:
        w, h = text_size(text, size)
        if container is not None:
            if container["type"] == "arrow":
                px, py = container["points"][-1]
                x, y = container["x"] + px / 2 - w / 2, container["y"] + py / 2 - h / 2
            else:
                x = container["x"] + (container["width"] - w) / 2
                y = container["y"] + (container["height"] - h) / 2
            container["boundElements"].append({"type": "text", "id": eid})
        return self.base("text", eid, x, y, w, h, strokeColor=color, text=text,
                         originalText=text, fontSize=size, fontFamily=self.font,
                         textAlign=align, verticalAlign="middle",
                         containerId=container["id"] if container else None,
                         lineHeight=1.25, autoResize=True, boundElements=None)


def text_size(text: str, size: int) -> tuple[float, float]:
    lines = text.split("\n")
    return max(len(l) for l in lines) * size * 0.6, len(lines) * size * 1.25


def border_point(box: dict, tx: float, ty: float) -> tuple[float, float]:
    """Point du bord de `box` sur la droite qui va de son centre vers (tx, ty)."""
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    dx, dy = tx - cx, ty - cy
    if dx == 0 and dy == 0:
        return cx, cy
    hw, hh = box["width"] / 2, box["height"] / 2
    if box["type"] == "ellipse":
        k = 1 / ((dx / hw) ** 2 + (dy / hh) ** 2) ** 0.5
    else:
        k = min(hw / abs(dx) if dx else float("inf"), hh / abs(dy) if dy else float("inf"))
    return cx + dx * k, cy + dy * k


def overlaps(a: dict, b: dict) -> bool:
    return not (a["x"] + a["width"] <= b["x"] or b["x"] + b["width"] <= a["x"]
                or a["y"] + a["height"] <= b["y"] or b["y"] + b["height"] <= a["y"])


def build(spec: dict) -> tuple[dict, list[str], list[str]]:
    errors, warnings = [], []
    font = FONTS.get(str(spec.get("font", "excalifont")).lower(), 5)
    scene = Scene(font, sober=font != 5)
    shapes, roles_used = {}, []
    items = spec.get("elements", [])
    nodes = [i for i in items if "from" not in i]
    arrows = [i for i in items if "from" in i]

    for item in nodes:
        eid = str(item.get("id") or f"n{len(shapes) + 1}")
        if eid in shapes:
            errors.append(f"Identifiant en double : {eid}")
            continue
        role = item.get("role", "system")
        if role not in ROLES:
            errors.append(f"{eid} : rôle inconnu « {role} » ({', '.join(ROLES)})")
            role = "system"
        fill, stroke, shape, stroke_style, _ = ROLES[role]
        label = str(item.get("label", ""))
        size = int(item.get("fontSize", 16))
        tw, th = text_size(label, size) if label else (0, 0)
        w = float(item.get("w", max(W, tw + 40)))
        h = float(item.get("h", max(H, th + 30)))
        if "x" in item and "y" in item:
            x, y = float(item["x"]), float(item["y"])
        else:
            x = float(item.get("col", 0)) * (W + GAP_X)
            y = float(item.get("row", 0)) * (H + GAP_Y)
        if role == "note":
            shapes[eid] = scene.text(eid, label, x, y, size, align="left")
            continue
        shape = item.get("shape", shape)
        element = scene.base(shape, eid, x, y, w, h, backgroundColor=fill, strokeColor=stroke,
                             strokeStyle=stroke_style,
                             roundness={"type": 3} if shape == "rectangle" else None)
        shapes[eid] = element
        if role != "zone" and role not in roles_used:
            roles_used.append(role)
        if label:
            if role == "zone":
                scene.text(f"{eid}-label", label, x + 12, y + 8, 14, align="left", color=stroke)
            else:
                scene.text(f"{eid}-label", label, 0, 0, size, container=element)

    # Les zones passent derrière les autres formes.
    zones = {str(n.get("id")) for n in nodes if n.get("role") == "zone"}
    zones |= {f"{z}-label" for z in zones}
    scene.elements.sort(key=lambda e: 0 if e["id"] in zones else 1)

    for index, item in enumerate(arrows, 1):
        eid = str(item.get("id") or f"a{index}")
        start, end = shapes.get(str(item["from"])), shapes.get(str(item.get("to")))
        if not start or not end:
            errors.append(f"Flèche {eid} : forme inconnue ({item.get('from')} -> {item.get('to')})")
            continue
        sx, sy = border_point(start, end["x"] + end["width"] / 2, end["y"] + end["height"] / 2)
        ex, ey = border_point(end, start["x"] + start["width"] / 2, start["y"] + start["height"] / 2)
        dashed = item.get("style") == "async"
        arrow = scene.base("arrow", eid, sx, sy, abs(ex - sx), abs(ey - sy),
                           strokeColor=ARROW, strokeStyle="dashed" if dashed else "solid",
                           roundness={"type": 2}, points=[[0, 0], [round(ex - sx, 2), round(ey - sy, 2)]],
                           lastCommittedPoint=None, startArrowhead=None, endArrowhead="arrow",
                           startBinding={"elementId": start["id"], "focus": 0, "gap": 4},
                           endBinding={"elementId": end["id"], "focus": 0, "gap": 4}, elbowed=False)
        start["boundElements"].append({"type": "arrow", "id": eid})
        end["boundElements"].append({"type": "arrow", "id": eid})
        if item.get("label"):
            scene.text(f"{eid}-label", str(item["label"]), 0, 0, 14, container=arrow)

    boxes = [e for e in scene.elements if e["type"] in ("rectangle", "ellipse", "diamond")
             and e["id"] not in zones]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1:]:
            if overlaps(a, b):
                warnings.append(f"Formes qui se chevauchent : {a['id']} et {b['id']}")
    for zone in [e for e in scene.elements if e["id"] in zones and e["type"] != "text"]:
        for box in boxes:
            inside = (zone["x"] < box["x"] and box["x"] + box["width"] < zone["x"] + zone["width"]
                      and zone["y"] < box["y"] and box["y"] + box["height"] < zone["y"] + zone["height"])
            if overlaps(zone, box) and not inside:
                warnings.append(f"{box['id']} déborde de la zone {zone['id']}")
    count = len([n for n in nodes if n.get("role") not in ("zone", "note")])
    if str(spec.get("audience", "")).startswith("non") and count > 7:
        warnings.append(f"{count} éléments pour un public non technique (7 maximum)")

    shown = [e for e in scene.elements if e["type"] != "arrow"] or [{"x": 0, "y": 0, "width": 0, "height": 0}]
    left = min(e["x"] for e in shown)
    top = min(e["y"] for e in shown)
    right = max(e["x"] + e["width"] for e in shown)
    if spec.get("title"):
        scene.text("title", str(spec["title"]), left, top - 60, 24, align="left")
    else:
        warnings.append("Pas de titre (champ title)")
    legend = spec.get("legend", "auto")
    if legend and (legend is True or len(roles_used) > 1 or any(a.get("style") == "async" for a in arrows)):
        lx, ly = right + 80, top
        scene.text("legend-title", "Légende", lx, ly, 16, align="left")
        for row, role in enumerate(roles_used, 1):
            fill, stroke, shape, style, name = ROLES[role]
            y = ly + row * 36
            scene.base(shape, f"legend-{role}", lx, y, 28, 22, backgroundColor=fill,
                       strokeColor=stroke, strokeStyle=style,
                       roundness={"type": 3} if shape == "rectangle" else None)
            scene.text(f"legend-{role}-label", name, lx + 40, y + 1, 14, align="left")
        if any(a.get("style") == "async" for a in arrows):
            y = ly + (len(roles_used) + 1) * 36 + 11
            scene.base("arrow", "legend-async", lx, y, 28, 0, strokeColor=ARROW, strokeStyle="dashed",
                       roundness={"type": 2}, points=[[0, 0], [28, 0]], lastCommittedPoint=None,
                       startArrowhead=None, endArrowhead="arrow", startBinding=None,
                       endBinding=None, elbowed=False)
            scene.text("legend-async-label", "Asynchrone", lx + 40, y - 9, 14, align="left")

    document = {"type": "excalidraw", "version": 2, "source": "myskills",
                "elements": scene.elements,
                "appState": {"viewBackgroundColor": "#ffffff", "gridSize": 20},
                "files": {}}
    return document, errors, warnings


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, help="fichier .excalidraw (défaut : même nom)")
    parser.add_argument("--export", choices=["png", "svg"],
                        help="exporte aussi l'image (skill diagram-export) : construire et rendre en un appel")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    invalid = validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    document, errors, warnings = build(spec)
    name = args.spec.name.removesuffix(".json").removesuffix(".diagram")
    out = args.out or args.spec.with_name(name + ".excalidraw")
    if not errors:
        ai_mark.write_text(out, json.dumps(document, ensure_ascii=False, indent=2))
    report = {"input": str(args.spec), "output": None if errors else str(out),
              "elements": len(document["elements"]), "errors": errors, "warnings": warnings}
    if args.export and not errors:
        report["export"], failed = export_image(out, args.export)
        errors += failed
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
