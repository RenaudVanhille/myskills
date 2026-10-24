"""Brand template (.potx / .pptx) loading and layout discovery."""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from pathlib import Path

from pptx import Presentation
from pptx.enum.shapes import PP_PLACEHOLDER
from pptx.util import Emu

SKILL_DIR = Path(__file__).resolve().parent.parent.parent          # skills/markdown-to-pptx
TEMPLATES_DIR = SKILL_DIR / "assets" / "templates"
DEFAULT_TEMPLATE = TEMPLATES_DIR / "default.potx"
BRAND_DIR = TEMPLATES_DIR / "brand"
TEMPLATE_EXT = (".potx", ".pptx", ".potm")


def _single_template(folder: Path):
    if not folder.is_dir():
        return None
    found = sorted(p for p in folder.iterdir() if p.suffix.lower() in TEMPLATE_EXT and not p.name.startswith("~$"))
    return found[0] if found else None


def resolve_template(explicit=None, start: Path | None = None) -> tuple[Path, str]:
    """Pick the brand template. Order:
    1. --template / explicit path
    2. $MD2PPTX_TEMPLATE
    3. a .md2pptx/ folder in the current directory or any parent (per-project brand)
    4. assets/templates/brand/ inside the skill (organisation brand shipped with the skill)
    5. assets/templates/default.potx (neutral fallback)
    """
    import os
    if explicit:
        return Path(explicit), "--template"
    if os.environ.get("MD2PPTX_TEMPLATE"):
        return Path(os.environ["MD2PPTX_TEMPLATE"]), "$MD2PPTX_TEMPLATE"
    here = (start or Path.cwd()).resolve()
    for d in [here, *here.parents]:
        t = _single_template(d / ".md2pptx")
        if t:
            return t, f"project folder {d / '.md2pptx'}"
    t = _single_template(BRAND_DIR)
    if t:
        return t, "skill brand folder"
    return DEFAULT_TEMPLATE, "bundled default"

_TEMPLATE_CT = b"application/vnd.openxmlformats-officedocument.presentationml.template.main+xml"
_MACRO_TEMPLATE_CT = b"application/vnd.ms-powerpoint.template.macroEnabled.main+xml"
_PRES_CT = b"application/vnd.openxmlformats-officedocument.presentationml.presentation.main+xml"

TITLE_TYPES = {PP_PLACEHOLDER.TITLE, PP_PLACEHOLDER.CENTER_TITLE}
BODY_TYPES = {PP_PLACEHOLDER.BODY, PP_PLACEHOLDER.OBJECT}
META_TYPES = {PP_PLACEHOLDER.DATE, PP_PLACEHOLDER.FOOTER, PP_PLACEHOLDER.SLIDE_NUMBER}


def _as_presentation_bytes(path: Path) -> bytes:
    """python-pptx refuses .potx content types; rewrite them to a plain .pptx in memory."""
    data = path.read_bytes()
    src = zipfile.ZipFile(io.BytesIO(data))
    ct = src.read("[Content_Types].xml")
    if _TEMPLATE_CT not in ct and _MACRO_TEMPLATE_CT not in ct:
        return data
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            blob = src.read(info.filename)
            if info.filename == "[Content_Types].xml":
                blob = blob.replace(_TEMPLATE_CT, _PRES_CT).replace(_MACRO_TEMPLATE_CT, _PRES_CT)
            dst.writestr(info, blob)
    return out.getvalue()


def open_template(path: str | Path | None = None, keep_slides: bool = False):
    path = Path(path) if path else resolve_template()[0]
    prs = Presentation(io.BytesIO(_as_presentation_bytes(path)))
    if not keep_slides:
        sld_ids = prs.slides._sldIdLst
        for sld_id in list(sld_ids):
            prs.part.drop_rel(sld_id.rId)
            sld_ids.remove(sld_id)
    return prs


def _ph_types(layout) -> list:
    return [ph.placeholder_format.type for ph in layout.placeholders
            if ph.placeholder_format.type not in META_TYPES]


@dataclass
class Box:
    x: int
    y: int
    w: int
    h: int

    def inset(self, dx=0, dy=0) -> "Box":
        return Box(self.x + dx, self.y + dy, self.w - 2 * dx, self.h - 2 * dy)

    def below(self, used: int, gap: int = 0) -> "Box":
        return Box(self.x, self.y + used + gap, self.w, self.h - used - gap)


class Layouts:
    """Finds the template layouts to use for each slide role.

    Roles: title, section, content, title_only, closing, quote, blank.
    Layouts are matched by name (English/French and common corporate naming such
    as Cover_*, Chapter_*, Text_1Column_*, Back_Cover_*) and by placeholder
    structure. `overrides` maps a role to a layout name for templates that
    can't be recognised automatically (see --list-layouts).
    """

    ROLES = ("title", "section", "content", "title_only", "closing", "quote", "blank")
    NAME_HINTS = {
        "title": r"^title( slide)?$|title slide|cover|couverture|titre de pr|^titre$",
        "section": r"section|divider|chapter|chapitre|intercalaire",
        "content": r"title (and|&|\+) (content|text)|^content$|titre et contenu|^text$|one content|1.?column|one.?column",
        "title_only": r"title only|titre seul",
        "closing": r"back.?cover|closing|end.?slide|^fin$|q ?& ?[ar]|thank|merci|conclusion",
        "quote": r"quote|citation|testimon|verbatim",
        "blank": r"blank|vide",
    }
    FALLBACK = {"section": "title", "title_only": "content", "blank": "title_only",
                "content": "title_only", "closing": "section", "quote": None}

    def __init__(self, prs, overrides: dict | None = None):
        self.prs = prs
        self.layouts = [l for m in prs.slide_masters for l in m.slide_layouts]
        self.slide_area = prs.slide_width * prs.slide_height
        self.roles = {}
        overrides = {k: v.lower() for k, v in (overrides or {}).items()}
        for role in self.ROLES:
            chosen = None
            if role in overrides:
                chosen = next((l for l in self.layouts if l.name.lower() == overrides[role]), None)
                if chosen is None:
                    raise ValueError(f"Layout '{overrides[role]}' for role '{role}' not found. "
                                     f"Available: {[l.name for l in self.layouts]}")
            self.roles[role] = chosen or self._find(role)

    def _find(self, role, depth=0):
        by_name = [l for l in self.layouts if re.search(self.NAME_HINTS[role], l.name.strip(), re.I)]
        structural = sorted((l for l in self.layouts if self._fits(role, l)), key=self._simplicity)
        both = [l for l in structural if l in by_name]
        if both:
            return both[0]
        if role in ("closing", "quote"):   # optional roles: only a clear name match counts
            fits = [l for l in by_name if self._usable(l)]
            return sorted(fits, key=self._simplicity)[0] if fits else (
                self._find(self.FALLBACK[role]) if self.FALLBACK[role] else None)
        if structural:
            return structural[0]
        if by_name:
            return by_name[0]
        fb = self.FALLBACK.get(role)
        return self._find(fb, depth + 1) if fb and depth < 3 else self.layouts[0]

    @staticmethod
    def _simplicity(layout):
        types = [ph.placeholder_format.type for ph in layout.placeholders]
        return (PP_PLACEHOLDER.PICTURE in types, len(types))

    @staticmethod
    def _usable(layout) -> bool:
        return any(ph.placeholder_format.type not in META_TYPES for ph in layout.placeholders)

    def _big(self, ph) -> bool:
        return ph.width * ph.height > self.slide_area * 0.2

    def _fits(self, role, layout) -> bool:
        phs = [ph for ph in layout.placeholders if ph.placeholder_format.type not in META_TYPES]
        types = [ph.placeholder_format.type for ph in phs]
        has_title = any(t in TITLE_TYPES for t in types)
        bodies = [ph for ph in phs if ph.placeholder_format.type in BODY_TYPES]
        big = [ph for ph in bodies if self._big(ph)]
        if role == "title":
            return PP_PLACEHOLDER.CENTER_TITLE in types and PP_PLACEHOLDER.SUBTITLE in types
        if role == "section":
            return (has_title or bodies) and not big and len(phs) <= 3
        if role == "content":
            # a title, one large body, optionally small bodies (e.g. a subtitle line)
            return has_title and len(big) == 1 and PP_PLACEHOLDER.PICTURE not in types and len(bodies) <= 2
        if role == "title_only":
            return has_title and len(phs) == 1
        if role == "blank":
            return not phs
        return False

    def get(self, role):
        return self.roles[role] or self.roles["content"]

    # placeholder slots -------------------------------------------------------
    def slots(self, layout) -> dict:
        """Classify a layout's placeholders by idx: title, subtitle, body, number, extra."""
        out = {"title": None, "subtitle": None, "body": None, "number": None, "extra": []}
        phs = [ph for ph in layout.placeholders if ph.placeholder_format.type not in META_TYPES
               and ph.placeholder_format.type != PP_PLACEHOLDER.PICTURE]
        texts = []
        for ph in phs:
            t = ph.placeholder_format.type
            prompt = ph.text_frame.text.strip() if ph.has_text_frame else ""
            if t in TITLE_TYPES and out["title"] is None:
                out["title"] = ph.placeholder_format.idx
            elif t == PP_PLACEHOLDER.SUBTITLE and out["subtitle"] is None:
                out["subtitle"] = ph.placeholder_format.idx
            elif re.fullmatch(r"(XX|\d{1,2})\.?", prompt):
                out["number"] = ph.placeholder_format.idx
            else:
                texts.append(ph)
        texts.sort(key=lambda ph: -(ph.width * ph.height))
        if out["title"] is None and texts and not any(self._big(ph) for ph in texts[:1]):
            out["title"] = texts.pop(0).placeholder_format.idx          # e.g. chapter layouts
        if texts and self._big(texts[0]):
            out["body"] = texts.pop(0).placeholder_format.idx
        if texts and out["subtitle"] is None:
            texts.sort(key=lambda ph: ph.top)
            out["subtitle"] = texts.pop(0).placeholder_format.idx
        out["extra"] = [ph.placeholder_format.idx for ph in sorted(texts, key=lambda ph: (ph.top, ph.left))]
        return out

    # numbered agenda and key-figure layouts --------------------------------------
    _NUM_PROMPT = re.compile(r"(XX|0?\d{1,2})\.?")

    def summary_layouts(self) -> list[tuple]:
        """Agenda layouts with numbered slots (e.g. Summary_*: "01" + chapter title), as
        [(layout, [(number_idx, title_idx), ...])], smallest capacity first."""
        out = []
        for l in self.layouts:
            if not re.search(r"summary|sommaire|agenda|contents|table des mati", l.name, re.I):
                continue
            phs = [ph for ph in l.placeholders if ph.placeholder_format.type not in META_TYPES
                   and ph.placeholder_format.type != PP_PLACEHOLDER.PICTURE]
            nums = [ph for ph in phs if ph.has_text_frame
                    and self._NUM_PROMPT.fullmatch(ph.text_frame.text.strip())]
            if len(nums) < 3:
                continue
            others = [ph for ph in phs if ph not in nums and ph.placeholder_format.type not in TITLE_TYPES]
            third = self.prs.slide_width / 3
            pairs, used = [], set()
            for n in sorted(nums, key=lambda p: (round(p.left / third), p.top, p.left)):
                def beside(o):      # text slot to the right of the number, on the same row
                    return o.left >= n.left + n.width * 0.5 and o.top < n.top + n.height and o.top + o.height > n.top

                def under(o):       # text slot below the number, in the same column
                    return o.top >= n.top + n.height * 0.5 and o.left < n.left + n.width and o.left + o.width > n.left
                cands = [o for o in others if o.placeholder_format.idx not in used and (beside(o) or under(o))]
                if not cands:
                    continue
                best = min(cands, key=lambda o: abs(o.left - n.left) + abs(o.top - n.top))
                used.add(best.placeholder_format.idx)
                pairs.append((n.placeholder_format.idx, best.placeholder_format.idx))
            if len(pairs) >= 3:
                out.append((l, pairs))
        return sorted(out, key=lambda x: len(x[1]))

    def key_figure_layout(self):
        """A layout built around one big number (e.g. Key_Figure_*: "XX%"), as
        (layout, {"figure", "caption", "body", "heading"}) or None."""
        for l in self.layouts:
            if not re.search(r"key.?fig|chiffre|big.?number|kpi", l.name, re.I):
                continue
            phs = [ph for ph in l.placeholders if ph.placeholder_format.type not in META_TYPES
                   and ph.placeholder_format.type != PP_PLACEHOLDER.PICTURE and ph.has_text_frame]
            if not any(ph.placeholder_format.type in TITLE_TYPES for ph in phs):
                continue
            figs = [ph for ph in phs if re.fullmatch(r"XX\s*%?", ph.text_frame.text.strip())]
            if len(figs) != 1:
                continue
            fig = figs[0]
            slots = self.slots(l)
            rest = [ph for ph in phs if ph is not fig and ph.placeholder_format.idx not in
                    (slots["title"], slots["subtitle"]) and ph.text_frame.text.strip() not in ("%", "")]
            if len(rest) < 2:
                continue

            def dist(o):
                return abs(o.left + o.width / 2 - fig.left - fig.width / 2) + abs(o.top + o.height / 2 - fig.top - fig.height / 2)
            caption = min(rest, key=dist)
            rest.remove(caption)
            body = max(rest, key=lambda o: o.width * o.height)
            rest.remove(body)
            heading = min(rest, key=lambda o: abs(o.left - body.left) + abs(o.top - body.top)) if rest else None
            return l, {"figure": fig.placeholder_format.idx, "caption": caption.placeholder_format.idx,
                       "body": body.placeholder_format.idx,
                       "heading": heading.placeholder_format.idx if heading is not None else None}
        return None

    # geometry ----------------------------------------------------------------
    def content_box(self) -> Box:
        """Area available for body content, taken from the content layout's main body placeholder."""
        layout = self.roles["content"]
        idx = self.slots(layout)["body"]
        for ph in layout.placeholders:
            if ph.placeholder_format.idx == idx and ph.width:
                return Box(ph.left, ph.top, ph.width, ph.height)
        sw, sh = self.prs.slide_width, self.prs.slide_height
        return Box(int(sw * 0.06), int(sh * 0.22), int(sw * 0.88), int(sh * 0.68))

    def describe(self) -> list[dict]:
        out = []
        for l in self.layouts:
            out.append({"name": l.name,
                        "placeholders": [f"{ph.placeholder_format.type}".split(" ")[0]
                                         for ph in l.placeholders],
                        "roles": [r for r, v in self.roles.items() if v is l]})
        return out


def load_sidecar(template) -> dict:
    """Optional '<template>.md2pptx.json' next to the template: {"layouts": {role: name}, ...}."""
    p = Path(template) if template else resolve_template()[0]
    side = p.with_name(p.stem + ".md2pptx.json")
    if side.exists():
        import json
        return json.loads(side.read_text(encoding="utf-8"))
    return {}


def emu(v) -> int:
    return int(Emu(v))
