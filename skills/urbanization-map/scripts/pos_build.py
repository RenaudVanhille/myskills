# /// script
# requires-python = ">=3.10"
# ///
"""Construit le plan d'occupation des sols (POS) d'un SI en draw.io.

Entrée : une description JSON courte (zones, quartiers, îlots, applications)
ou un inventaire CSV, ou une note Markdown avec son tableau (une ligne par
application : zone, quartier, ilot, application, statut). Le script fait toute la mise en page : zones de
pilotage en haut, opérations au milieu, support en bas, échanges à gauche et
référentiels à droite, blocs imbriqués et alignés, titre et légende aux
couleurs de la charte. Sortie : un `.drawio` en XML clair, dont les blocs
sont des conteneurs (déplacer un quartier déplace ses îlots et ses
applications), vérifié ensuite comme par check_drawio.py s'il est présent.

    uv run scripts/pos_build.py POS.json|POS.csv|POS.md [--out POS.drawio]
        [--title "..."] [--audience technique|"non technique"]
        [--detail zone|quartier|ilot|application] [--zoom] [--vocabulary pos|togaf]

Avec --vocabulary togaf, les niveaux deviennent des capacités TOGAF (niveaux
1 à 3, Business Capability Map) et les applications des composants
applicatifs ; les zones s'empilent dans l'ordre donné.
"""

import argparse
import json
import math
import sys
import unicodedata
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from drawio_xml import br, new_file, new_page, vertex, write  # noqa: E402
from inventory import read_inventory  # noqa: E402
from skill_paths import absent, load_module  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

LEVELS = ["zone", "quartier", "ilot", "application"]
KINDS = ["pilotage", "operations", "support", "referentiel", "echanges"]
# Mots du nom d'une zone qui en donnent le type quand `kind` manque.
KIND_WORDS = {"pilot": "pilotage", "decision": "pilotage", "support": "support",
              "ressource": "support", "referentiel": "referentiel", "donnees partagees": "referentiel",
              "echange": "echanges", "interface": "echanges", "integration": "echanges"}
BASE = "whiteSpace=wrap;html=1;fontColor=#1f2937;"
FRAME = "verticalAlign=top;align=left;container=1;collapsible=0;"
LEAF = "verticalAlign=middle;align=center;"
STYLES = {
    "zone": "rounded=1;arcSize=2;dashed=1;fillColor=none;strokeColor=#9ca3af;fontColor=#6b7280;"
            "fontSize=16;fontStyle=1;spacingLeft=8;" + "whiteSpace=wrap;html=1;",
    "quartier": "rounded=1;arcSize=4;fillColor=#ffffff;strokeColor=#6b7280;fontSize=14;fontStyle=1;"
                "spacingLeft=6;" + BASE,
    "ilot": "rounded=1;arcSize=6;fillColor=#ffffff;strokeColor=#d1d5db;fontSize=13;spacingLeft=6;" + BASE,
}
# Teinte d'une zone selon son type -> (fond de la zone, bordure et titre, fond des quartiers).
# Échanges reprend la couleur des files et bus de la charte, référentiels celle des données.
TINTS = {
    "pilotage": ("#eef2ff", "#4f46e5", "#e0e7ff"),
    "operations": ("#fefce8", "#ca8a04", "#fef9c3"),
    "support": ("#fdf2f8", "#db2777", "#fce7f3"),
    "referentiel": ("#f0fdf4", "#15803d", "#dcfce7"),
    "echanges": ("#faf5ff", "#7e22ce", "#f3e8ff"),
}
# Statut d'une application -> (style, nom dans la légende).
STATUSES = {
    "en-place": ("rounded=1;fillColor=#dbeafe;strokeColor=#1d4ed8;", "En place"),
    "a-faire-evoluer": ("rounded=1;fillColor=#ffedd5;strokeColor=#c2410c;", "À faire évoluer"),
    "a-remplacer": ("rounded=1;fillColor=#fee2e2;strokeColor=#b91c1c;", "À remplacer ou retirer"),
    "nouvelle": ("rounded=1;dashed=1;fillColor=#ccfbf1;strokeColor=#0f766e;", "À créer"),
    "externe": ("rounded=1;dashed=1;fillColor=#f3f4f6;strokeColor=#6b7280;", "Externe, SaaS"),
}
STATUS_WORDS = {"": "en-place", "en place": "en-place", "conserver": "en-place", "maintenir": "en-place",
                "evoluer": "a-faire-evoluer", "a faire evoluer": "a-faire-evoluer",
                "remplacer": "a-remplacer", "a remplacer": "a-remplacer", "retirer": "a-remplacer",
                "decommissionner": "a-remplacer", "a decommissionner": "a-remplacer",
                "nouvelle": "nouvelle", "a creer": "nouvelle", "creer": "nouvelle", "cible": "nouvelle",
                "externe": "externe", "saas": "externe", "partenaire": "externe"}
TITLE = "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;fontColor=#1f2937;"
# Noms des niveaux dans la légende : urbanisation (POS) ou capacités TOGAF.
VOCABULARIES = {"pos": {"zone": "Zone", "quartier": "Quartier", "ilot": "Îlot", "app": "Application"},
                "togaf": {"zone": "Capacité niveau 1", "quartier": "Capacité niveau 2",
                          "ilot": "Capacité niveau 3", "app": "Composant applicatif"}}
APP_W, APP_H, LEAF_SIZE = 160, 44, {"zone": (220, 90), "quartier": (180, 70), "ilot": (160, 50)}
GAP, PAD, HEADER, LINE = 12, 12, 30, 18


def plain(text: str) -> str:
    """Minuscules sans accents, pour comparer des mots-clés."""
    text = unicodedata.normalize("NFD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c)).replace("-", " ").replace("_", " ").strip()


def wrap_lines(text: str, width: float, size: int) -> int:
    per_line = max(4, int((width - 12) / (size * 0.58)))
    lines = 0
    for part in text.split("\n"):
        words, current = part.split(), 0
        lines += 1
        for word in words:
            if current and current + 1 + len(word) > per_line:
                lines, current = lines + 1, len(word)
            else:
                current += len(word) + (1 if current else 0)
    return lines


class Node:
    def __init__(self, level: str, name: str, children: list | None = None, status: str = "en-place",
                 kind: str = ""):
        self.level, self.name, self.children = level, name, children or []
        self.status, self.kind = status, kind
        self.x = self.y = self.w = self.h = 0.0
        self.leaf = False
        self.rows: list[list[Node]] = []
        self.tint = TINTS["operations"]


def parse_app(item, where: str, errors: list) -> Node:
    if isinstance(item, str):
        return Node("application", item)
    name = str(item.get("name", "")).strip()
    raw = plain(str(item.get("status", "")))
    status = item.get("status") if item.get("status") in STATUSES else STATUS_WORDS.get(raw)
    if not name:
        errors.append(f"{where} : application sans nom")
    if status is None:
        errors.append(f"{where} : {name}, statut inconnu « {item.get('status')} » ({', '.join(STATUSES)})")
        status = "en-place"
    return Node("application", name, status=status)


def zone_kind(zone: dict, errors: list) -> str:
    kind = plain(str(zone.get("kind", "")))
    if kind:
        if kind not in KINDS:
            errors.append(f"zone {zone.get('name')} : type inconnu « {zone['kind']} » ({', '.join(KINDS)})")
            return "operations"
        return kind
    name = plain(str(zone.get("name", "")))
    return next((k for word, k in KIND_WORDS.items() if word in name), "operations")


def parse_spec(spec: dict, errors: list) -> list[Node]:
    zones = []
    for z in spec.get("zones", []):
        zname = str(z.get("name", "")).strip() or "Zone"
        quartiers = []
        for q in z.get("quartiers", []):
            qname = str(q.get("name", "")).strip()
            where = f"{zname} / {qname}"
            ilots = [Node("ilot", str(i.get("name", "")).strip(),
                          [parse_app(a, f"{where} / {i.get('name')}", errors) for a in i.get("apps", [])])
                     for i in q.get("ilots", [])]
            if q.get("apps"):
                # Applications posées directement dans le quartier : un îlot sans cadre.
                ilots.append(Node("ilot", "", [parse_app(a, where, errors) for a in q["apps"]]))
            quartiers.append(Node("quartier", qname, ilots))
        zones.append(Node("zone", zname, quartiers, kind=zone_kind(z, errors)))
    return zones


# --- Mise en page --------------------------------------------------------------------------

def measure(node: Node, depth: int) -> None:
    """Taille naturelle de chaque bloc, des feuilles vers les zones."""
    if node.level == "application":
        node.w, node.h = APP_W, max(APP_H, wrap_lines(node.name, APP_W, 14) * LINE + 14)
        node.leaf = True
        return
    visible = node.children if LEVELS.index(node.level) < depth else []
    if node.level == "quartier" and depth == 2:
        # Sans les applications, un îlot sans nom n'a rien à montrer.
        visible = node.children = [c for c in visible if c.name]
    if not visible:
        node.leaf = True
        w, h = LEAF_SIZE[node.level]
        node.w, node.h = w, max(h, wrap_lines(node.name, w, 14) * LINE + 20)
        node.children = []
        return
    for child in visible:
        measure(child, depth)
    if node.level == "ilot":
        # Applications en grille : une colonne jusqu'à 3, deux jusqu'à 8, trois au-delà.
        n = len(visible)
        cols = 1 if n <= 3 else 2 if n <= 8 else 3
        pack(node, cols * APP_W + (cols - 1) * GAP)
    elif node.level == "quartier":
        best_width(node, 1.3)
    else:
        best_width(node, 2.0 if node.kind in ("pilotage", "support", "operations") else 0.4)


def header(node: Node) -> float:
    return 0 if node.level == "ilot" and not node.name else HEADER


def pack(node: Node, max_inner: float) -> None:
    """Range les enfants en lignes de largeur max_inner ; même hauteur dans une ligne."""
    rows, row, width = [], [], 0.0
    for child in node.children:
        if row and width + GAP + child.w > max_inner:
            rows.append(row)
            row, width = [], 0.0
        width += (GAP if row else 0) + child.w
        row.append(child)
    if row:
        rows.append(row)
    node.rows = rows
    inner_w = max(sum(c.w for c in r) + GAP * (len(r) - 1) for r in rows)
    inner_h = sum(max(c.h for c in r) for r in rows) + GAP * (len(rows) - 1)
    node.w, node.h = inner_w + 2 * PAD, inner_h + 2 * PAD + header(node)


def best_width(node: Node, ratio: float) -> None:
    """Essaie plusieurs largeurs et garde celle dont le rapport largeur / hauteur est le plus proche."""
    widths = sorted({c.w for c in node.children})
    lo, hi = max(widths), sum(c.w for c in node.children) + GAP * (len(node.children) - 1)
    best = None
    for step in range(25):
        candidate = lo + (hi - lo) * step / 24
        pack(node, candidate)
        score = abs(math.log(node.w / node.h / ratio))
        if best is None or score < best[0] - 1e-9:
            best = (score, candidate)
    pack(node, best[1])


def place(node: Node, w: float, h: float) -> None:
    """Fixe la taille finale et étire les enfants : chaque ligne remplit la largeur,
    la dernière ligne remplit la hauteur restante."""
    node.w, node.h = w, h
    if not node.rows:
        return
    inner_w = w - 2 * PAD
    y = PAD + header(node)
    heights = [max(c.h for c in r) for r in node.rows]
    spare = (h - PAD) - (y + sum(heights) + GAP * (len(heights) - 1))
    if node.rows[0][0].level != "application":
        # Les blocs se partagent la hauteur en trop ; des applications restent groupées en haut.
        heights = [height + spare / len(heights) for height in heights]
    # Les applications gardent leur taille ; leur grille est centrée dans le bloc.
    grid_w = max(sum(c.w for c in r) + GAP * (len(r) - 1) for r in node.rows)
    for row, row_h in zip(node.rows, heights):
        apps = row[0].level == "application"
        x = PAD + ((inner_w - grid_w) / 2 if apps else 0)
        extra = 0 if apps else inner_w - (sum(c.w for c in row) + GAP * (len(row) - 1))
        for child in row:
            child.x, child.y = x, y
            place(child, child.w + extra / len(row), child.h if apps else row_h)
            x += child.w + GAP
        y += row_h + GAP


def layout(zones: list[Node], depth: int) -> tuple[float, float]:
    """Disposition du POS : échanges | (pilotage / opérations / support) | référentiels."""
    for zone in zones:
        measure(zone, depth)
    left = [z for z in zones if z.kind == "echanges"]
    right = [z for z in zones if z.kind == "referentiel"]
    center = sorted([z for z in zones if z.kind in ("pilotage", "operations", "support")],
                    key=lambda z: ("pilotage", "operations", "support").index(z.kind))
    center_w = max([z.w for z in center], default=0)
    center_h = sum(z.h for z in center) + GAP * 2 * max(len(center) - 1, 0)
    side_h = lambda col: sum(z.h for z in col) + GAP * 2 * max(len(col) - 1, 0)
    total_h = max(center_h, side_h(left), side_h(right))

    def column(col: list[Node], x: float, width: float) -> None:
        # La hauteur qui manque va à la première zone d'opérations, sinon à la dernière zone.
        stretch = next((z for z in col if z.kind == "operations"), col[-1])
        rest = total_h - side_h(col)
        y = 0.0
        for zone in col:
            zone.x, zone.y = x, y
            place(zone, width, zone.h + (rest if zone is stretch else 0))
            y += zone.h + GAP * 2

    x = 0.0
    if left:
        width = max(z.w for z in left)
        column(left, x, width)
        x += width + GAP * 2
    if center:
        column(center, x, center_w)
        x += center_w + GAP * 2
    if right:
        width = max(z.w for z in right)
        column(right, x, width)
        x += width
    else:
        x -= GAP * 2 if zones else 0
    return x, total_h


# --- Écriture ------------------------------------------------------------------------------

def emit(root: ET.Element, node: Node, parent: str, ids: dict, origin: tuple = (0, 0)) -> None:
    if node.level == "ilot" and not node.name:
        # Îlot sans nom : ses applications vont directement dans le quartier.
        for row in node.rows:
            for child in row:
                emit(root, child, parent, ids, (node.x, node.y))
        return
    base = plain(node.name).replace(" ", "-") or node.level
    cid = f"{node.level[0]}-{base}"
    ids[cid] = ids.get(cid, 0) + 1
    if ids[cid] > 1:
        cid = f"{cid}-{ids[cid]}"
    if node.level == "application":
        style = STATUSES[node.status][0] + BASE + "fontSize=14;" + LEAF
    else:
        style = STYLES[node.level] + (LEAF if node.leaf else FRAME)
        fill, stroke, light = node.tint
        if node.level == "zone":
            style = style.replace("fillColor=none;strokeColor=#9ca3af;fontColor=#6b7280;",
                                  f"fillColor={fill};strokeColor={stroke};fontColor={stroke};")
        elif node.level == "quartier":
            style = style.replace("fillColor=#ffffff;strokeColor=#6b7280;",
                                  f"fillColor={light};strokeColor={stroke};")
    vertex(root, cid, br(node.name), style, node.x + origin[0], node.y + origin[1], node.w, node.h, parent)
    for row in node.rows:
        for child in row:
            emit(root, child, cid, ids)


def statuses_used(zones: list[Node]) -> list[str]:
    found = set()

    def walk(n: Node) -> None:
        if n.level == "application":
            found.add(n.status)
        for c in n.children:
            walk(c)

    for z in zones:
        walk(z)
    return [s for s in STATUSES if s in found]


def build_page(name: str, title: str, zones: list[Node], depth: int, legend,
               vocabulary: str = "pos") -> ET.Element:
    diagram, root = new_page(f"p-{plain(name).replace(' ', '-')}", name)
    width, _ = layout(zones, depth)
    if title:
        vertex(root, "title", title, TITLE, 0, -60, max(400, len(title) * 12), 30)
    ids: dict = {}
    for zone in zones:
        emit(root, zone, "1", ids)
    used = statuses_used(zones)
    levels = LEVELS[:min(depth, 3) + 1] if depth < 3 else LEVELS[:3]
    if legend is True or (legend and (len(levels) > 1 or len(used) > 1)):
        lx = width + 60
        vertex(root, "legend-title", "Légende", "text;html=1;fontStyle=1;align=left;fontColor=#1f2937;"
                  "fontSize=14;", lx, 0, 120, 20)
        side = "labelPosition=right;verticalLabelPosition=middle;align=left;spacingLeft=8;fontSize=12;"
        row = 1
        names = VOCABULARIES[vocabulary]
        for level in levels:
            style = STYLES[level].replace("whiteSpace=wrap;", "").replace("fontStyle=1;", "").replace("fontSize=16;", "").replace("fontSize=14;", "").replace(
                "fontSize=13;", "").replace("fontColor=#6b7280;", "fontColor=#1f2937;")
            vertex(root, f"legend-{level}", names[level], side + style, lx, row * 32, 30, 20)
            row += 1
        for status in used:
            text = STATUSES[status][1] if used != ["en-place"] else names["app"]
            vertex(root, f"legend-{status}", text,
                      side + STATUSES[status][0] + "html=1;fontColor=#1f2937;", lx, row * 32, 30, 20)
            row += 1
    return diagram


def count(zones: list[Node]) -> dict:
    totals = {"zones": len(zones), "quartiers": 0, "ilots": 0, "applications": 0}

    def walk(n: Node) -> None:
        for c in n.children:
            if c.level == "quartier":
                totals["quartiers"] += 1
            elif c.level == "ilot" and c.name:
                totals["ilots"] += 1
            elif c.level == "application":
                totals["applications"] += 1
            walk(c)

    for z in zones:
        walk(z)
    return totals


def check_spec(zones: list[Node], audience: str, depth: int, zoom: bool, totals: dict, warnings: list,
               errors: list) -> None:
    seen: dict = {}
    for z in zones:
        if not z.children:
            warnings.append(f"zone {z.name} : aucun quartier")
        for q in z.children:
            if not q.name:
                errors.append(f"zone {z.name} : quartier sans nom")
            for i in q.children:
                for a in i.children:
                    seen.setdefault(plain(a.name), []).append(f"{q.name}/{i.name or '-'}")
    for name, places in seen.items():
        if len(places) > 1:
            warnings.append(f"application « {name} » rangée {len(places)} fois ({', '.join(places)}) : "
                            "une application appartient en principe à un seul îlot")
    non_tech = audience.startswith("non")
    if non_tech and depth >= 3 and totals["applications"] > 30:
        warnings.append(f"{totals['applications']} applications pour un public non technique : "
                        "préférez detail quartier, avec --zoom pour le détail")
    if not non_tech and depth >= 3 and totals["applications"] > 120 and not zoom:
        warnings.append(f"{totals['applications']} applications sur une page : ajoutez --zoom "
                        "(une page par zone) ou baissez le niveau de détail")


def paint(zones: list[Node], vocabulary: str) -> list[Node]:
    """Teinte de chaque zone et de ses quartiers : selon le type de zone pour un POS,
    une teinte par capacité de niveau 1, dans l'ordre, pour TOGAF."""
    order = list(TINTS)
    for index, zone in enumerate(zones):
        tint = TINTS[order[index % len(order)]] if vocabulary == "togaf" else TINTS[zone.kind]
        for node in [zone, *zone.children]:
            node.tint = tint
    return zones


def find_checker():
    """check_drawio.py du skill drawio-diagram, s'il est installé à côté."""
    module = load_module("drawio-diagram", "check_drawio.py")
    return module.check if module else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, help="description .json, inventaire .csv ou note .md avec son tableau",
                        nargs="?")
    parser.add_argument("--out", type=Path, help="fichier .drawio (défaut : même nom)")
    parser.add_argument("--title", help="titre (remplace celui de la description)")
    parser.add_argument("--audience", help="technique ou non technique")
    parser.add_argument("--detail", choices=LEVELS, help="niveau le plus fin affiché")
    parser.add_argument("--zoom", action="store_true", help="ajoute une page détaillée par zone")
    parser.add_argument("--vocabulary", choices=list(VOCABULARIES),
                        help="pos (défaut) ou togaf : capacités de niveau 1 à 3, zones empilées sans disposition imposée")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    errors, warnings = [], []
    try:
        if args.spec.suffix.lower() in (".csv", ".md"):
            spec = read_inventory(args.spec, errors)
        else:
            spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    invalid = args.spec.suffix.lower() not in (".csv", ".md") and validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    audience = str(args.audience or spec.get("audience") or "technique")
    detail = args.detail or spec.get("detail") or ("quartier" if audience.startswith("non") else "application")
    if detail not in LEVELS:
        errors.append(f"detail inconnu « {detail} » ({', '.join(LEVELS)})")
        detail = "application"
    depth = LEVELS.index(detail)
    zoom = bool(args.zoom or spec.get("zoom"))
    title = args.title or spec.get("title") or ""
    legend = spec.get("legend", "auto")
    vocabulary = args.vocabulary or spec.get("vocabulary") or "pos"
    if vocabulary not in VOCABULARIES:
        errors.append(f"vocabulary inconnu « {vocabulary} » ({', '.join(VOCABULARIES)})")
        vocabulary = "pos"

    zones = parse_spec(spec, errors)
    paint(zones, vocabulary)
    if vocabulary == "togaf":
        # TOGAF n'impose pas de disposition : les capacités de niveau 1 s'empilent dans l'ordre donné.
        for zone in zones:
            zone.kind = "operations"
    if not zones:
        errors.append("aucune zone")
    totals = count(zones)
    check_spec(zones, audience, depth, zoom, totals, warnings, errors)
    name = args.spec.name.removesuffix(".json").removesuffix(".csv").removesuffix(".pos")
    out = args.out or args.spec.with_name(name + ".drawio")
    report = {"input": str(args.spec), "output": None, "pages": 0, **totals, "detail": detail,
              "vocabulary": vocabulary,
              "errors": errors, "warnings": warnings}
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    mxfile = new_file()
    mxfile.append(build_page("Vue d'ensemble", title, zones, depth, legend, vocabulary))
    if zoom and depth < 3:
        prefix = "capacité" if vocabulary == "togaf" else "zone"
        for zone in paint(parse_spec(spec, []), vocabulary):
            mxfile.append(build_page(zone.name, f"{title}, {prefix} {zone.name}" if title else zone.name,
                                     [zone], 3, legend, vocabulary))
    write(mxfile, out)
    report.update(output=str(out), pages=len(mxfile))
    checker = find_checker()
    if checker:
        checked = checker(out)
        report["errors"] += checked["errors"]
        report["warnings"] += checked["warnings"]
    else:
        report["warnings"].append("fichier non vérifié : " + absent("drawio-diagram", "check_drawio.py"))
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
