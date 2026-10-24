"""Brand library: pictograms, ready-made diagrams and the Europe map extracted from the
brand's own PowerPoint libraries (assets/brand-library, built by tools/build_*.py).

Everything here is optional: when the folder is missing, or the template's theme is not the
one the diagrams were drawn for, the renderer falls back to its own drawn shapes.
"""
from __future__ import annotations

import base64
import copy
import gzip
import io
import json
import math
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

from lxml import etree
from pptx.oxml import parse_xml

LIB = Path(__file__).resolve().parents[2] / "assets" / "brand-library"
P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
NS = {"p": P, "a": A, "r": R}
EMU = 914400
DECORATIVE_URI = "{C183D7F6-B498-43B3-948B-1728B52AA6E4}"
ADEC = "http://schemas.microsoft.com/office/drawing/2017/decorative"


# --------------------------------------------------------------------------- #
# text normalisation shared by icon and country matching
# --------------------------------------------------------------------------- #
STOP = set("""a an and are as at be by for from in into is it its of on or our the their this to was we
with your le la les un une des du de d l et ou en au aux pour par sur avec dans est sont nos notre vos
votre ce ces cette son sa ses leur leurs qui que plus new nouveau""".split())


def fold(text: str) -> str:
    text = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in text if not unicodedata.combining(c))


def stems(text: str) -> list[str]:
    words = re.findall(r"[a-z0-9]+", fold(re.sub(r"[*_`]", "", text)))
    out = []
    for w in words:
        if len(w) < 3 or w in STOP:
            continue
        if len(w) > 4 and w.endswith("s"):
            w = w[:-1]
        out.append(w[:6])
    return out


# --------------------------------------------------------------------------- #
# icons
# --------------------------------------------------------------------------- #
class Icons:
    """Keyword index over the pictogram library; draws an icon as native vector shapes."""

    def __init__(self, folder: Path = LIB):
        self.folder = folder
        meta = json.loads((folder / "icons.json").read_text(encoding="utf-8"))
        self.meta = {i["id"]: i for i in meta["icons"]}
        self.keys, self.primary = {}, {}
        df = {}
        for i in meta["icons"]:
            ks = []
            self.primary[i["id"]] = {s for w in (i["en"][:1] + i["fr"][:1]) for s in stems(w)}
            for w in i["en"] + i["fr"]:
                for s in stems(w):
                    if s not in ks:
                        ks.append(s)
            self.keys[i["id"]] = ks
            for s in ks:
                df[s] = df.get(s, 0) + 1
        self.weight = {s: 1.0 / math.log(2 + n) for s, n in df.items()}
        self._xml = None

    @classmethod
    def load(cls):
        return _icons()

    def score(self, text: str) -> list[tuple[float, int]]:
        words = stems(text)
        if not words:
            return []
        hits = []
        for iid, ks in self.keys.items():
            if not self.meta[iid]["auto"]:
                continue
            s, covered = 0.0, set()
            for k in ks:
                if k in words:
                    # the first keyword is what the icon *is*; others are associations
                    s += self.weight[k] * (1.6 if k in self.primary[iid] else 1.0)
                    covered.add(k)
            if s:
                hits.append((s * (len(covered) / len(set(words))) ** 0.5, iid))
        return sorted(hits, key=lambda h: (-h[0], h[1]))

    def pick(self, texts: list[str], min_score: float = 0.35) -> list[int] | None:
        """One distinct icon per text, or None when any text has no convincing match
        (a slide shows icons on every item or on none)."""
        used, out = set(), []
        for t in texts:
            label, _, rest = t.partition("\x00")
            head = " ".join(label.split()[:4])          # a sentence: its opening words say what it is about
            ranked = [h for h in self.score(head) if h[0] >= min_score] or self.score(label) or \
                self.score(label + " " + rest)
            choice = next((iid for s, iid in ranked if s >= min_score and iid not in used), None)
            if choice is None:
                return None
            used.add(choice)
            out.append(choice)
        return out

    def by_name(self, name: str) -> int | None:
        if name.strip().isdigit() and int(name) in self.meta:
            return int(name)
        ranked = self.score(name)
        return ranked[0][1] if ranked else None

    def xml(self, iid: int):
        if self._xml is None:
            with gzip.open(self.folder / "icons.xml.gz", "rb") as f:
                root = etree.fromstring(f.read())
            self._xml = {int(e.get("id")): e[0] for e in root}
        return self._xml[iid]

    def place(self, slide, iid: int, x: int, y: int, size: int, color: str = "accent1",
              name: str | None = None):
        """Draw icon `iid` centred in a size x size square at (x, y), recoloured to a theme
        colour ('accent1'..'accent6', 'bg1', 'tx1'). Marked decorative for screen readers."""
        el = copy.deepcopy(self.xml(iid))
        tag = etree.QName(el).localname
        xfrm = el.find("p:grpSpPr/a:xfrm" if tag == "grpSp" else "p:spPr/a:xfrm", NS)
        ext = xfrm.find("a:ext", NS)
        w, h = int(ext.get("cx")), int(ext.get("cy"))
        k = size / max(w, h)
        nw, nh = int(w * k), int(h * k)
        xfrm.find("a:off", NS).set("x", str(int(x + (size - nw) / 2)))
        xfrm.find("a:off", NS).set("y", str(int(y + (size - nh) / 2)))
        ext.set("cx", str(nw))
        ext.set("cy", str(nh))
        for fill in el.iter(f"{{{A}}}solidFill"):
            for c in list(fill):
                fill.remove(c)
            etree.SubElement(fill, f"{{{A}}}schemeClr", val=color)
        tree = slide.shapes._spTree
        next_id = max([int(i) for i in tree.xpath(".//p:cNvPr/@id")] + [1]) + 1
        for n, c in enumerate(el.iter(f"{{{P}}}cNvPr")):
            c.set("id", str(next_id + n))
            if n == 0:
                c.set("name", name or f"Icon {iid}")
                decorative(c)
        return _adopt(tree, el)


def _adopt(tree, el):
    """Append a plain lxml element to a slide's shape tree as a python-pptx element."""
    el = parse_xml(etree.tostring(el))
    tree.append(el)
    return el


def decorative(cNvPr) -> None:
    """Flag a shape as decorative (PowerPoint's accessibility checker then skips it)."""
    ext_lst = cNvPr.find(f"{{{A}}}extLst")
    if ext_lst is None:
        ext_lst = etree.SubElement(cNvPr, f"{{{A}}}extLst")
    ext = etree.SubElement(ext_lst, f"{{{A}}}ext", uri=DECORATIVE_URI)
    etree.SubElement(ext, f"{{{ADEC}}}decorative", val="1")


@lru_cache(maxsize=1)
def _icons():
    if not (LIB / "icons.json").exists():
        return None
    return Icons(LIB)


# --------------------------------------------------------------------------- #
# ready-made diagrams (schemas)
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _schemas():
    if not (LIB / "schemas.json").exists():
        return None
    meta = json.loads((LIB / "schemas.json").read_text(encoding="utf-8"))
    with gzip.open(LIB / "schemas.xml.gz", "rb") as f:
        root = etree.fromstring(f.read())
    shapes = {e.get("name"): e for e in root if e.tag == "schema"}
    maps = {e.get("name"): e[0] for e in root if e.tag == "map"}
    return meta, shapes, maps


def theme_accents(prs) -> list[str]:
    try:
        theme = next(r.target_part for r in prs.slide_masters[0].part.rels.values()
                     if r.reltype.endswith("/theme"))
        xml = theme.blob.decode("utf-8", "ignore")
    except Exception:
        return []
    out = []
    for i in range(1, 7):
        m = re.search(rf"<a:accent{i}>.*?val=\"(\w+)\"", xml, re.S)
        out.append(m.group(1).upper() if m else "")
    return out


def brand_matches(prs) -> bool:
    lib = _schemas()
    return bool(lib) and theme_accents(prs)[:4] == lib[0]["accents"][:4]


def _line_count(text, width_in, pt):
    cpl = max(1, int(width_in * 72 / (pt * 0.55)))
    n = 0
    for para in text.split("\n"):
        cur, k = 0, 1
        for w in para.split():
            if cur and cur + 1 + len(w) > cpl:
                k += 1
                cur = len(w)
            else:
                cur += (1 if cur else 0) + len(w)
            if len(w) > cpl:
                return 99
        n += k
    return n


def _fits(paras, sizes, width_in, max_h_in, scale):
    h = 0.0
    for text, pt in zip(paras, sizes):
        if text:
            h += _line_count(text, width_in, pt * scale) * pt * scale * 1.2 / 72
    return h <= max_h_in, h


class Schema:
    """One ready-made diagram. `fill(items)` returns False (and draws nothing) when the text
    would not fit at a readable size."""

    MIN_SCALE = 0.75
    MIN_PT = 10

    def __init__(self, meta: dict, shapes):
        self.meta = meta
        self.shapes = shapes

    @staticmethod
    def find(kind: str, n: int, prs) -> "Schema | None":
        lib = _schemas()
        if not lib or not brand_matches(prs):
            return None
        meta, shapes, _ = lib
        for s in meta["schemas"]:
            if s["kind"] == kind and s["n"] == n:
                return Schema(s, shapes[s["name"]])
        return None

    def _plan(self, slot: dict, label: str, body: str, max_h: float):
        """-> list of (shape_id, [texts], [sizes], width) or None if it does not fit."""
        jobs = []
        if "box" in slot:
            box = slot["box"]
            sizes = (box["sizes"] + [box["sizes"][-1]] * 2)[:2]
            if "label" in slot:                 # label lives elsewhere (timeline year)
                paras = [body.split("\n", 1)[0], body.split("\n", 1)[1] if "\n" in body else ""]
            else:
                paras = [label, body]
            jobs.append((box, paras, sizes, max_h))
            if "label" in slot:
                lb = slot["label"]
                jobs.append((lb, [label, ""], [lb["sizes"][0] if lb["sizes"] else 16, 0], lb["h"] * 1.6))
        else:
            lb, bd = slot["label"], slot["body"]
            ls = lb["sizes"][0] if lb["sizes"] else 12
            bs = bd["sizes"][0] if bd["sizes"] else 11
            jobs.append((lb, [label, ""], [ls, 0], max(lb["h"] * 2.2, 0.45)))
            jobs.append((bd, [body, ""], [bs, 0], max_h))
        out = []
        for box, paras, sizes, mh in jobs:
            for scale in (1.0, 0.92, 0.85, self.MIN_SCALE):
                if min(sz for sz, t in zip(sizes, paras) if t) * scale < self.MIN_PT:
                    continue                    # never shrink brand text below a readable size
                ok, h = _fits(paras, sizes, box["w"], mh, scale)
                if ok:
                    break
            else:
                return None
            out.append((box, paras, [s * scale for s in sizes], h))
        return out

    def layout(self, items: list[dict], root: dict | None = None):
        """Text jobs for every slot, or None when some text would not fit."""
        m = self.meta
        jobs = []
        for slot, it in zip(m["items"], items):
            j = self._plan(slot, it["label"], it["body"], m["max_h"])
            if j is None:
                return None
            jobs += j
        if m.get("root"):
            if not root:
                return None
            j = self._plan(m["root"], root["label"], root["body"], m["root_max_h"])
            if j is None:
                return None
            jobs += j
        return jobs

    def fill(self, slide, items: list[dict], root: dict | None = None, alt: str = "") -> bool:
        m = self.meta
        jobs = self.layout(items, root)
        if jobs is None:
            return False
        # copy the shapes, then write the text
        tree = slide.shapes._spTree
        next_id = max([int(i) for i in tree.xpath(".//p:cNvPr/@id")] + [1]) + 1
        grp = etree.Element(f"{{{P}}}grpSp")
        nv = etree.SubElement(grp, f"{{{P}}}nvGrpSpPr")
        etree.SubElement(nv, f"{{{P}}}cNvPr", id=str(next_id), name=f"Diagram {m['name']}", descr=alt)
        etree.SubElement(nv, f"{{{P}}}cNvGrpSpPr")
        etree.SubElement(nv, f"{{{P}}}nvPr")
        gpr = etree.SubElement(grp, f"{{{P}}}grpSpPr")
        xf = etree.SubElement(gpr, f"{{{A}}}xfrm")
        for t, attrs in (("off", {"x": "0", "y": "0"}), ("ext", {"cx": "12192000", "cy": "6858000"}),
                         ("chOff", {"x": "0", "y": "0"}), ("chExt", {"cx": "12192000", "cy": "6858000"})):
            etree.SubElement(xf, f"{{{A}}}{t}", **attrs)
        rid_map = {}
        for key, media in m.get("media", {}).items():
            _, rid = slide.part.get_or_add_image_part(io.BytesIO(base64.b64decode(media["data"])))
            rid_map[key] = rid
        id_map = {}
        for el in self.shapes:
            el = copy.deepcopy(el)
            for c in el.iter(f"{{{P}}}cNvPr"):
                next_id += 1
                id_map[int(c.get("id"))] = c
                c.set("id", str(next_id))
            for blip in el.iter(f"{{{A}}}blip"):
                blip.set(f"{{{R}}}embed", rid_map[blip.get(f"{{{R}}}embed")])
            for cn in el.iter(f"{{{A}}}stCxn", f"{{{A}}}endCxn"):   # connectors: drop dangling links
                cn.getparent().remove(cn)
            grp.append(el)
        for box, paras, sizes, h in jobs:
            sp = id_map[box["id"]].getparent().getparent()
            _write(sp, paras, sizes)
            _set_height(sp, h, box)
        _adopt(tree, grp)
        return True


def _write(sp, paras, sizes):
    body = sp.find("p:txBody", NS)
    tmpl = [p for p in body.findall("a:p", NS) if "".join(p.itertext()).strip()] or body.findall("a:p", NS)
    for p in body.findall("a:p", NS):
        body.remove(p)
    for k, (text, pt) in enumerate(zip(paras, sizes)):
        if not text:
            continue
        src = tmpl[min(k, len(tmpl) - 1)]
        p = etree.SubElement(body, f"{{{A}}}p")
        ppr = src.find("a:pPr", NS)
        if ppr is not None:
            p.append(copy.deepcopy(ppr))
        r0 = src.find("a:r/a:rPr", NS)
        r = etree.SubElement(p, f"{{{A}}}r")
        rpr = copy.deepcopy(r0) if r0 is not None else etree.Element(f"{{{A}}}rPr", lang="fr-FR")
        rpr.set("sz", str(int(round(pt * 2)) * 50))
        r.append(rpr)
        etree.SubElement(r, f"{{{A}}}t").text = text


def _set_height(sp, h_in, box):
    """Text boxes are auto-fit in PowerPoint but only resize once edited: give them the height
    the text needs now, keeping their centre (middle-anchored) or top."""
    xf = sp.find("p:spPr/a:xfrm", NS)
    if xf is None or h_in <= box["h"]:
        return
    off, ext = xf.find("a:off", NS), xf.find("a:ext", NS)
    old = int(ext.get("cy"))
    new = int(h_in * EMU) + 20000
    anchor = sp.find("p:txBody/a:bodyPr", NS).get("anchor", "t")
    if anchor == "ctr":
        off.set("y", str(int(off.get("y")) - (new - old) // 2))
    ext.set("cy", str(new))


# --------------------------------------------------------------------------- #
# maps
# --------------------------------------------------------------------------- #
COUNTRIES = {
    "AD": "andorra andorre", "AL": "albania albanie", "AT": "austria autriche", "AX": "aland",
    "BA": "bosnia bosnie", "BE": "belgium belgique", "BG": "bulgaria bulgarie", "BY": "belarus bielorussie",
    "CH": "switzerland suisse", "CZ": "czechia czech tcheque tchequie", "DE": "germany allemagne",
    "DK": "denmark danemark", "EE": "estonia estonie", "ES": "spain espagne", "FI": "finland finlande",
    "FO": "faroe feroe", "FR": "france", "GB": "united_kingdom uk britain royaume-uni royaume_uni angleterre england scotland ecosse wales",
    "GG": "guernsey guernesey", "GI": "gibraltar", "GR": "greece grece", "HR": "croatia croatie",
    "HU": "hungary hongrie", "IE": "ireland irlande", "IM": "isle_of_man", "IS": "iceland islande",
    "IT": "italy italie", "JE": "jersey", "XK": "kosovo", "LI": "liechtenstein", "LT": "lithuania lituanie",
    "LU": "luxembourg", "LV": "latvia lettonie", "MC": "monaco", "MD": "moldova moldavie",
    "ME": "montenegro", "MK": "macedonia macedoine", "MT": "malta malte", "NL": "netherlands pays-bas pays_bas holland hollande",
    "NO": "norway norvege", "PL": "poland pologne", "PT": "portugal", "RO": "romania roumanie",
    "RS": "serbia serbie", "SE": "sweden suede", "SI": "slovenia slovenie", "SK": "slovakia slovaquie",
    "SM": "san_marino saint-marin", "TR": "turkey turkiye turquie", "UA": "ukraine", "VA": "vatican",
}
_NAME_TO_CODE = {}
for _code, _names in COUNTRIES.items():
    for _n in _names.split():
        _NAME_TO_CODE[_n.replace("_", " ").replace("-", " ")] = _code


def country_code(text: str) -> str | None:
    """'France', '**Germany**: 12 offices', 'Royaume-Uni (Londres)' -> ISO code."""
    t = fold(re.sub(r"[*_`]", "", text)).replace("-", " ")
    t = re.split(r"[:—–(,]", t)[0].strip()
    t = re.sub(r"^(the|la|le|les|l')\s*", "", t).strip()
    if t.upper() in COUNTRIES and len(t) == 2:
        return t.upper()
    return _NAME_TO_CODE.get(t)


def has_map() -> bool:
    lib = _schemas()
    return bool(lib and "europe" in lib[2])


def draw_europe(slide, box, groups: list[tuple[list[str], str]], base="bg2", alt=""):
    """Draw the Europe map fitted into `box` (x, y, w, h in EMU). `groups` = [(codes, theme colour)]."""
    _, _, maps = _schemas()
    grp = copy.deepcopy(maps["europe"])
    xf = grp.find("p:grpSpPr/a:xfrm", NS)
    ext = xf.find("a:ext", NS)
    w, h = int(ext.get("cx")), int(ext.get("cy"))
    k = min(box[2] / w, box[3] / h)
    nw, nh = int(w * k), int(h * k)
    xf.find("a:off", NS).set("x", str(int(box[0] + (box[2] - nw) / 2)))
    xf.find("a:off", NS).set("y", str(int(box[1] + (box[3] - nh) / 2)))
    ext.set("cx", str(nw))
    ext.set("cy", str(nh))
    colour = {}
    for codes, col in groups:
        for c in codes:
            colour[c] = col
    for sp in grp.findall("p:sp", NS):
        code = sp.find(".//p:cNvPr", NS).get("name").split()[-1]
        sppr = sp.find("p:spPr", NS)
        for f in sppr.findall("a:solidFill", NS) + sppr.findall("a:noFill", NS) + sppr.findall("a:grpFill", NS):
            sppr.remove(f)
        fill = etree.Element(f"{{{A}}}solidFill")
        clr = etree.SubElement(fill, f"{{{A}}}schemeClr", val=colour.get(code, base))
        if code not in colour and base == "bg2":
            etree.SubElement(clr, f"{{{A}}}lumMod", val="90000")
        geom = sppr.find("a:custGeom", NS)
        (geom if geom is not None else sppr.find("a:xfrm", NS)).addnext(fill)
    tree = slide.shapes._spTree
    next_id = max([int(i) for i in tree.xpath(".//p:cNvPr/@id")] + [1]) + 1
    for n, c in enumerate(grp.iter(f"{{{P}}}cNvPr")):
        c.set("id", str(next_id + n))
    top = grp.find("p:nvGrpSpPr/p:cNvPr", NS)
    top.set("name", "Map of Europe")
    top.set("descr", alt)
    return _adopt(tree, grp)
