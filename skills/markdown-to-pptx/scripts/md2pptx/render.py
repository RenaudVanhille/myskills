"""Slide plan -> .pptx using python-pptx and the brand template.

All colours are *theme* colours (accent1..6, text/background) and no font
face is hard-coded (except monospace for code), so the output follows whatever
brand the .potx template defines.
"""
from __future__ import annotations

import math
from pathlib import Path

from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.dml import MSO_THEME_COLOR
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE, PP_PLACEHOLDER
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Emu, Inches, Pt

from .brand import Icons, Schema, brand_matches, draw_europe, has_map
from .parser import inline_runs, plain_text
from .template import BODY_TYPES, TITLE_TYPES, Box, Layouts, open_template

ACCENTS = [MSO_THEME_COLOR.ACCENT_1, MSO_THEME_COLOR.ACCENT_2, MSO_THEME_COLOR.ACCENT_3,
           MSO_THEME_COLOR.ACCENT_4, MSO_THEME_COLOR.ACCENT_5, MSO_THEME_COLOR.ACCENT_6]
DARK = MSO_THEME_COLOR.TEXT_1
LIGHT = MSO_THEME_COLOR.BACKGROUND_1
GAP = Inches(0.25)

# --------------------------------------------------------------------------- #
# colour contrast (WCAG 2.1): text colour is chosen from the template's real RGB values
# --------------------------------------------------------------------------- #
THEME_RGB: dict[str, tuple] = {}
_THEME_NAME = {MSO_THEME_COLOR.TEXT_1: "dk1", MSO_THEME_COLOR.BACKGROUND_1: "lt1",
               MSO_THEME_COLOR.TEXT_2: "dk2", MSO_THEME_COLOR.BACKGROUND_2: "lt2",
               **{a: f"accent{i}" for i, a in enumerate(ACCENTS, start=1)}}
SCHEME_VAL = {MSO_THEME_COLOR.TEXT_1: "tx1", MSO_THEME_COLOR.BACKGROUND_1: "bg1",
              MSO_THEME_COLOR.TEXT_2: "tx2", MSO_THEME_COLOR.BACKGROUND_2: "bg2",
              **{a: f"accent{i}" for i, a in enumerate(ACCENTS, start=1)}}


def load_theme_rgb(prs) -> dict:
    import re as _re
    try:
        master = prs.slide_masters[0]
        theme = next(r.target_part for r in master.part.rels.values() if r.reltype.endswith("/theme"))
        xml = theme.blob.decode("utf-8", "ignore")
    except Exception:
        return {}
    out = {}
    for name in ("dk1", "lt1", "dk2", "lt2") + tuple(f"accent{i}" for i in range(1, 7)):
        m = _re.search(rf"<a:{name}>(.*?)</a:{name}>", xml, _re.S)
        v = m and _re.search(r'(?:lastClr|val)="([0-9A-Fa-f]{6})"', m.group(1))
        if v:
            h = v.group(1)
            out[name] = tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))
    return out


def rgb(theme_color, brightness=0.0):
    c = THEME_RGB.get(_THEME_NAME.get(theme_color, ""))
    if c is None:
        return None
    if brightness > 0:
        return tuple(v + (255 - v) * brightness for v in c)
    return tuple(v * (1 + brightness) for v in c)


def contrast(a, b) -> float:
    def lum(c):
        ch = [v / 255 for v in c]
        ch = [v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4 for v in ch]
        return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2]
    la, lb = sorted((lum(a), lum(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def text_on(fill, brightness=0.0, size=14, bold=False):
    """LIGHT or DARK, whichever is readable on this fill (4.5:1, or 3:1 for large text)."""
    bg = rgb(fill, brightness)
    light, dark = THEME_RGB.get("lt1"), THEME_RGB.get("dk1")
    if bg is None or light is None or dark is None:
        return LIGHT if brightness < 0.4 else DARK
    need = 3.0 if size >= 18.5 or (bold and size >= 14) else 4.5
    if contrast(bg, light) >= need:
        return LIGHT
    return DARK if contrast(bg, dark) >= contrast(bg, light) else LIGHT


def shade_for(color, size=14, bold=False, on=(MSO_THEME_COLOR.BACKGROUND_1, 0.0)) -> float:
    """Darkening (negative brightness) an accent needs to be readable as text on `on`."""
    bg = rgb(*on)
    if bg is None or rgb(color) is None or color in (DARK, MSO_THEME_COLOR.TEXT_2):
        return 0.0
    need = 3.0 if size >= 18.5 or (bold and size >= 14) else 4.5
    for b in (0.0, -0.15, -0.25, -0.35, -0.5):
        if contrast(rgb(color, b), bg) >= need:
            return b
    return -0.5


# --------------------------------------------------------------------------- #
# text fitting (estimate; no font files needed)
# --------------------------------------------------------------------------- #
CHAR_W = 0.55       # average glyph width in em; brand sans fonts (Tahoma, Segoe, DejaVu) run wide


def _lines(text: str, width_emu: int, pt: float, char_w: float = CHAR_W) -> int:
    cpl = max(1, int((width_emu / 12700) / (pt * char_w)))
    total = 0
    for para in (text or " ").split("\n"):
        cur, n = 0, 1
        for word in para.split():
            wl = len(word)
            while wl > cpl:          # very long word wraps hard
                n += 1
                wl -= cpl
            if cur == 0:
                cur = wl
            elif cur + 1 + wl <= cpl:
                cur += 1 + wl
            else:
                n += 1
                cur = wl
        total += n
    return total


def fit_pt(paras: list[str], w: int, h: int, max_pt: float, min_pt: float = 10,
           spacing: float = 1.2, gap: float = 0.35, char_w: float = CHAR_W) -> float:
    w = max(w - Inches(0.2), Inches(0.3))
    h_pt = max(h - Inches(0.1), Inches(0.2)) / 12700
    pt = max_pt
    longest = max((len(part) for p in paras for wd in p.split() for part in wd.split("-")), default=1)
    while pt > min_pt:
        if longest * pt * char_w > w / 12700:   # never break a word in the middle
            pt -= 1
            continue
        need = sum(_lines(p, w, pt, char_w) * pt * spacing for p in paras) + gap * pt * max(len(paras) - 1, 0)
        if need <= h_pt:
            return pt
        pt -= 1
    return min_pt


def fit_each(texts, w, h, max_pt, min_pt=10, **kw) -> float:
    """Largest size at which *each* text (fitted on its own) fits the box."""
    texts = [plain_text(t) for t in texts if t] or ["x"]
    return min(fit_pt([t], w, h, max_pt, min_pt, **kw) for t in texts)


def text_height(paras: list[str], w: int, pt: float, spacing=1.2, gap=0.35, char_w=CHAR_W) -> int:
    w = max(w - Inches(0.2), Inches(0.3))
    lines = sum(_lines(p, w, pt, char_w) for p in paras)
    return int((lines * pt * spacing + gap * pt * max(len(paras) - 1, 0)) * 12700 + Inches(0.15))


# --------------------------------------------------------------------------- #
# low-level shape helpers
# --------------------------------------------------------------------------- #
def add_runs(paragraph, md_text: str, size=None, bold=None, color=None, italic=None):
    for text, fmt in inline_runs(md_text):
        run = paragraph.add_run()
        run.text = text
        f = run.font
        if size:
            f.size = Pt(size)
        if fmt["bold"] or bold:
            f.bold = True
        if fmt["italic"] or italic:
            f.italic = True
        if fmt["code"]:
            f.name = "Courier New"
        if fmt["href"]:
            run.hyperlink.address = fmt["href"]
        if color is not None:
            f.color.theme_color = color
        if fmt["strike"]:
            run.font._rPr.set("strike", "sngStrike")


def set_text(tf, paras, size, color=None, align=None, bold=None, anchor=None, italic=None):
    """paras: list of md strings (or (md, overrides) tuples)."""
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    if anchor is not None:
        tf.vertical_anchor = anchor
    for i, item in enumerate(paras):
        text, over = (item if isinstance(item, tuple) else (item, {}))
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        if align is not None:
            p.alignment = align
        if i:
            p.space_before = Pt(size * 0.35)
        add_runs(p, text, size=over.get("size", size), bold=over.get("bold", bold),
                 color=over.get("color", color), italic=over.get("italic", italic))


def shape(slide, kind, box: Box, fill=ACCENTS[0], brightness=0.0, line=None, text=None,
          size=14, color=None, bold=None, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE,
          margin=Inches(0.08)):
    shp = slide.shapes.add_shape(kind, box.x, box.y, box.w, box.h)
    shp.shadow.inherit = False
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.theme_color = fill
        if brightness:
            shp.fill.fore_color.brightness = brightness
    if line is None:
        shp.line.fill.background()
    else:
        shp.line.color.theme_color = line
        shp.line.width = Pt(1.25)
    if text is not None:
        tf = shp.text_frame
        tf.margin_left = tf.margin_right = margin
        tf.margin_top = tf.margin_bottom = Inches(0.04)
        if color is None:
            color = text_on(fill, brightness, size, bool(bold)) if fill is not None else DARK
        set_text(tf, text if isinstance(text, list) else [text], size, color=color,
                 align=align, bold=bold, anchor=anchor)
    return shp


def textbox(slide, box: Box, paras, size, color=DARK, align=PP_ALIGN.LEFT, bold=None,
            anchor=MSO_ANCHOR.TOP, italic=None, on=(MSO_THEME_COLOR.BACKGROUND_1, 0.0)):
    tb = slide.shapes.add_textbox(box.x, box.y, box.w, box.h)
    set_text(tb.text_frame, paras if isinstance(paras, list) else [paras], size, color=color,
             align=align, bold=bold, anchor=anchor, italic=italic)
    shade = shade_for(color, size, bool(bold), on) if color in ACCENTS else 0.0
    if shade:                       # an accent too light to read as text: darken it
        for p in tb.text_frame.paragraphs:
            for r in p.runs:
                r.font.color.brightness = shade
    return tb


def arrow(slide, x1, y1, x2, y2, color=MSO_THEME_COLOR.TEXT_2, width=1.75, head=True):
    conn = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, int(x1), int(y1), int(x2), int(y2))
    conn.line.color.theme_color = color
    conn.line.color.brightness = 0.35 if color == MSO_THEME_COLOR.TEXT_2 else 0
    conn.line.width = Pt(width)
    if head:
        ln = conn.line._get_or_add_ln()
        ln.append(ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"}))
    return conn


def _item_texts(item: dict) -> tuple[str, list[str]]:
    """Labelled item -> (label, body paragraphs)."""
    body = [t for t in [item.get("text", "")] + item.get("details", []) if t]
    return item.get("label", ""), body


# --------------------------------------------------------------------------- #
# renderer
# --------------------------------------------------------------------------- #
class Renderer:
    def __init__(self, template=None, layout_overrides=None, base_dir: Path | None = None,
                 footer: str | None = None, icons: bool = True, schemas: bool = True):
        self.prs = open_template(template)
        self.layouts = Layouts(self.prs, layout_overrides)
        self.area = self.layouts.content_box()
        self.base_dir = base_dir or Path.cwd()
        self.footer = footer
        self.palette = _distinct_accents(self.prs)
        self.slots = {}
        THEME_RGB.clear()
        THEME_RGB.update(load_theme_rgb(self.prs))
        self.icons = Icons.load() if icons else None
        self.schemas = schemas and brand_matches(self.prs)
        self.lang = "en"

    def pal(self, k):
        """k-th distinct brand accent (templates often repeat colours across accent slots)."""
        return self.palette[k % len(self.palette)]

    # slide scaffolding -----------------------------------------------------------
    def new_slide(self, role: str, title: str = ""):
        layout = self.layouts.get(role)
        slide = self.prs.slides.add_slide(layout)
        slots = self.layouts.slots(layout)
        self.slots[id(slide)] = slots
        if title:
            self.fill(slide, slots["title"] if slots["title"] is not None else slots["body"], title, shrink=True,
                      min_pt=16)
        if self.footer:
            for lph in layout.placeholders:
                if lph.placeholder_format.type == PP_PLACEHOLDER.FOOTER:
                    slide.shapes.clone_placeholder(lph)
                    self.fill(slide, lph.placeholder_format.idx, self.footer)
        return slide

    @staticmethod
    def ph(slide, idx):
        if idx is None:
            return None
        for ph in slide.placeholders:
            if ph.placeholder_format.idx == idx:
                return ph
        return None

    def fill(self, slide, idx, *lines, shrink=False, min_pt=10) -> bool:
        """Write lines into a placeholder, shrinking the inherited font only if the text won't fit
        (display text such as covers always; other placeholders when `shrink` is set)."""
        ph = self.ph(slide, idx)
        if ph is None or not ph.has_text_frame:
            return False
        lines = [l for l in lines if l]
        size = None
        base = _inherited_pt(slide.slide_layout, idx)
        if base and (base >= 28 or shrink) and ph.width and ph.height:
            fitted = fit_pt([plain_text(l) for l in lines], ph.width, ph.height, base, min_pt,
                            spacing=1.2, char_w=0.62)
            size = fitted if fitted < base else None
        tf = ph.text_frame
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            add_runs(p, line, size=size)
        return True

    def slot(self, slide, name):
        return self.slots.get(id(slide), {}).get(name)

    @staticmethod
    def placeholder(slide, types):
        for ph in slide.placeholders:
            if ph.placeholder_format.type in types:
                return ph
        return None

    @staticmethod
    def drop_empty_placeholders(slide):
        for ph in list(slide.placeholders):
            if ph.placeholder_format.type == PP_PLACEHOLDER.PICTURE and not ph._element.xpath(".//a:blip"):
                ph._element.getparent().remove(ph._element)
            elif ph.has_text_frame and not ph.text_frame.text.strip():
                ph._element.getparent().remove(ph._element)

    def lead(self, slide, text: str, box: Box) -> Box:
        """Intro sentence: in the layout's subtitle slot when it has one and the text fits
        on a line, otherwise at the top of the content area. Returns the remaining box."""
        if not text:
            return box
        if len(plain_text(text)) <= 120 and self.fill(slide, self.slot(slide, "subtitle"), text):
            return box
        size = 18 if len(plain_text(text)) < 120 else 16
        h = text_height([plain_text(text)], box.w, size)
        textbox(slide, Box(box.x, box.y, box.w, h), text, size,
                color=MSO_THEME_COLOR.TEXT_1)
        return box.below(h, Inches(0.15))

    def render(self, plan: dict, out: str | Path):
        self.lang = plan.get("lang", "en")
        if plan.get("icons") == "off":
            self.icons = None
        if plan.get("schemas") == "off":
            self.schemas = False
        for spec in plan["slides"]:
            fn = getattr(self, f"s_{spec['kind']}", None)
            if fn is None:
                fn = self.s_bullets
            self._spec = spec
            full = self.area
            bands = self._band_boxes(spec)
            if bands:
                self.area = bands["area"]
            try:
                slide = fn(spec)
            finally:
                self.area = full
            if spec.get("notes"):
                slide.notes_slide.notes_text_frame.text = spec["notes"]
            self.drop_empty_placeholders(slide)
            describe(slide, spec, self.lang)
            if bands:
                self._draw_bands(slide, spec, bands)
        self.prs.core_properties.title = plan.get("title", "")
        self.prs.core_properties.subject = plan.get("purpose", {}).get("label", "")
        self.prs.save(str(out))
        return out

    # key-message bands ---------------------------------------------------------------
    def dark_accent(self):
        """The darkest brand accent: fill for banners and the core of a flow."""
        def lum(c):
            v = rgb(c)
            return sum(v) if v else 0
        return min(self.palette, key=lum) if THEME_RGB else self.pal(0)

    def _band_boxes(self, spec) -> dict | None:
        """Reserve room for a banner above the content area and a takeaway bar below it."""
        banner, take = spec.get("banner", ""), spec.get("takeaway", "")
        if not (banner or take) or spec["kind"] in ("title", "section", "closing", "agenda", "quote"):
            return None
        a, gap = self.area, Inches(0.2)
        out = {}
        if banner:
            size = fit_pt([plain_text(banner)], a.w - Inches(0.6), Inches(0.75), 18, 12)
            h = max(Inches(0.55), text_height([plain_text(banner)], a.w - Inches(0.6), size) + Inches(0.2))
            out["banner"] = (Box(a.x, a.y, a.w, h), size)
            a = a.below(h, gap)
        if take:
            size = fit_pt([plain_text(take)], a.w - Inches(0.6), Inches(0.7), 18, 12)
            h = max(Inches(0.5), text_height([plain_text(take)], a.w - Inches(0.6), size) + Inches(0.16))
            out["takeaway"] = (Box(a.x, a.y + a.h - h, a.w, h), size)
            a = Box(a.x, a.y, a.w, a.h - h - gap)
        out["area"] = a
        return out

    def _draw_bands(self, slide, spec, bands):
        fill = self.dark_accent()
        if "banner" in bands:
            box, size = bands["banner"]
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, box, fill=fill, text=spec["banner"], size=size,
                  bold=True, align=PP_ALIGN.LEFT, margin=Inches(0.3)).adjustments[0] = 0.12
        if "takeaway" in bands:
            box, size = bands["takeaway"]
            shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x, box.y, Inches(0.1), box.h), fill=fill)
            shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x + Inches(0.1), box.y, box.w - Inches(0.1), box.h),
                  fill=fill, brightness=0.85, text=spec["takeaway"], size=size, bold=True,
                  align=PP_ALIGN.LEFT, margin=Inches(0.25))

    # slide kinds -----------------------------------------------------------------
    def s_title(self, spec):
        slide = self.new_slide("title", spec["title"])
        target = self.slot(slide, "subtitle") or self.slot(slide, "body")
        self.fill(slide, target, spec.get("subtitle", ""), spec.get("byline", ""))
        return slide

    def s_section(self, spec, role="section"):
        title = spec["title"]
        layout = self.layouts.get(role)
        slots = self.layouts.slots(layout)
        title_idx = slots["title"] if slots["title"] is not None else slots["body"]
        prompt = next((ph.text_frame.text.strip() for ph in layout.placeholders
                       if ph.placeholder_format.idx == title_idx and ph.has_text_frame), "")
        if spec.get("short_title") and 0 < len(prompt) <= 5:   # e.g. a big "Q&A" back cover
            title = spec["short_title"]
        slide = self.new_slide(role, title)
        if spec.get("number") and self.slot(slide, "number") is not None:
            self.fill(slide, self.slot(slide, "number"), f"{spec['number']:02d}")
        if spec.get("subtitle"):
            used = {title_idx}
            for idx in [self.slot(slide, "subtitle"), self.slot(slide, "body")] + self.slot(slide, "extra"):
                if idx is not None and idx not in used:
                    self.fill(slide, idx, spec["subtitle"])
                    break
        return slide

    def s_closing(self, spec):
        return self.s_section(spec, role="closing")

    def s_agenda(self, spec):
        items = spec["items"]
        # only an exact fit: unused slots would leave the layout's numbering lines behind
        fit = next(((l, pairs) for l, pairs in self.layouts.summary_layouts() if len(pairs) == len(items)), None)
        if fit:                                     # the template's own numbered agenda (Summary_*)
            layout, pairs = fit
            slide = self.prs.slides.add_slide(layout)
            self.slots[id(slide)] = self.layouts.slots(layout)
            title_idx = self.slots[id(slide)]["title"]
            if title_idx is not None:
                self.fill(slide, title_idx, spec["title"], shrink=True)
            for k, ((num_idx, text_idx), text) in enumerate(zip(pairs, items), start=1):
                self.fill(slide, num_idx, f"{k:02d}")
                self.fill(slide, text_idx, text, shrink=True, min_pt=11)
            if self.footer:
                for lph in layout.placeholders:
                    if lph.placeholder_format.type == PP_PLACEHOLDER.FOOTER:
                        slide.shapes.clone_placeholder(lph)
                        self.fill(slide, lph.placeholder_format.idx, self.footer)
            return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.area
        cols = 1 if len(items) <= 5 else 2
        per_col = math.ceil(len(items) / cols)
        col_w = (box.w - GAP * (cols - 1)) // cols
        row_h = min(Inches(0.85), (box.h - Inches(0.12) * (per_col - 1)) // per_col)
        size = fit_each(items, col_w - row_h - Inches(0.4), row_h, 22, 12)
        for i, text in enumerate(items):
            c, r = divmod(i, per_col)
            x = box.x + c * (col_w + GAP)
            y = box.y + r * (row_h + Inches(0.12))
            shape(slide, MSO_SHAPE.OVAL, Box(x, y + row_h * 0.1, int(row_h * 0.8), int(row_h * 0.8)),
                  fill=self.pal(0), text=f"{i + 1}", size=min(20, int(row_h * 0.8 / 12700 * 0.4)), bold=True,
                  margin=0)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE,
                  Box(x + row_h, y, col_w - row_h, row_h), fill=self.pal(0), brightness=0.85,
                  text=text, size=size, align=PP_ALIGN.LEFT, margin=Inches(0.2))
        return slide

    def s_bullets(self, spec):
        if spec.get("style") == "rows":
            return self._bullet_rows(spec)
        slide = self.new_slide("content", spec["title"])
        body = self.ph(slide, self.slot(slide, "body")) or self.placeholder(slide, BODY_TYPES)
        if spec.get("lead") and len(plain_text(spec["lead"])) <= 120 \
                and self.fill(slide, self.slot(slide, "subtitle"), spec["lead"]):
            spec = {**spec, "lead": ""}
        items = spec.get("items", [])
        flat = []

        def walk(its, level):
            for it in its:
                flat.append((it["text"], level))
                walk(it.get("children", []), level + 1)
        walk(items, 0)
        paras = ([plain_text(spec["lead"])] if spec.get("lead") else []) + [plain_text(t) for t, _ in flat]
        box = Box(body.left, body.top, body.width, body.height) if body is not None else self.area
        size = fit_pt(paras, box.w - Inches(0.4), box.h, 26 if len(paras) <= 3 else 24, 12, gap=0.5)
        if body is None:
            textbox(slide, box, [t for t, _ in flat], size)
            return slide
        tf = body.text_frame
        tf.word_wrap = True
        first = True
        if spec.get("lead"):
            p = tf.paragraphs[0]
            add_runs(p, spec["lead"], size=size, color=MSO_THEME_COLOR.TEXT_1)
            _no_bullet(p)
            first = False
        for i, (text, level) in enumerate(flat):
            p = tf.paragraphs[0] if first else tf.add_paragraph()
            first = False
            p.level = min(level, 4)
            label, rest = _split_bold_label(text)
            s = size if level == 0 else max(size - 2, 11)
            if spec.get("plain"):
                _no_bullet(p)
                p.space_after = Pt(size * 0.5)
            if spec.get("ordered") and level == 0:
                _numbered(p)
            add_runs(p, text, size=s)
        tf.auto_size = MSO_AUTO_SIZE.NONE
        _no_autofit(tf)
        if text_height(paras, box.w - Inches(0.4), size, gap=0.5) < box.h * 0.55:
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE      # a short list sits in the middle of the slide
        return slide

    def _bullet_rows(self, spec):
        """A short flat list as highlighted rows (accent bar or step number + text)."""
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        gap = Inches(0.16)
        full = min(Inches(1.2), (box.h - gap * (n - 1)) // n)
        numbered = bool(spec.get("ordered"))
        icons = None if numbered else self.pick_icons(spec, items)
        mark = int(min(full * 0.75, Inches(0.7))) if numbered else Inches(0.12)
        if icons:
            mark = int(min(full * 0.62, Inches(0.6)))
        tx = mark + Inches(0.3) + (Inches(0.1) if icons else 0)
        texts = [it["text"] for it in items]
        size = fit_each(texts, box.w - tx - Inches(0.3), full - Inches(0.12), 24, 12)
        need = max(text_height([plain_text(t)], box.w - tx - Inches(0.3), size) for t in texts)
        rh = min(full, max(need + Inches(0.3), int(full * 0.8), Inches(0.75)))
        top = box.y + (box.h - (rh * n + gap * (n - 1))) * 2 // 5
        for k, text in enumerate(texts):
            y = top + k * (rh + gap)
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x, y, box.w, rh), fill=color, brightness=0.88)
            if numbered:
                shape(slide, MSO_SHAPE.OVAL, Box(box.x + Inches(0.12), y + (rh - mark) // 2, mark, mark),
                      fill=color, text=str(k + 1), size=int(mark / 12700 * 0.45), bold=True, margin=0)
            elif icons:
                shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x, y, Inches(0.08), rh), fill=color)
                self.icon(slide, icons[k], box.x + Inches(0.25), y + (rh - mark) // 2, mark, color)
            else:
                shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x, y, mark, rh), fill=color)
            textbox(slide, Box(box.x + tx, y, box.w - tx - Inches(0.15), rh), text, size,
                    anchor=MSO_ANCHOR.MIDDLE)
        return slide

    def s_text(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        paras = spec["paragraphs"]
        box = self.area.inset(Inches(0.3), 0)
        size = fit_pt([plain_text(p) for p in paras], box.w, box.h, 28, 14, gap=0.6)
        h = min(box.h, text_height([plain_text(p) for p in paras], box.w, size, gap=0.6))
        shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE,
              Box(box.x - Inches(0.3), box.y + (box.h - h) // 2 - Inches(0.2), box.w + Inches(0.6), h + Inches(0.4)),
              fill=self.pal(0), brightness=0.88)
        textbox(slide, Box(box.x, box.y + (box.h - h) // 2, box.w, h), paras, size, anchor=MSO_ANCHOR.MIDDLE)
        return slide

    # --- SmartArt-style diagrams -------------------------------------------------
    def s_process(self, spec):
        slide = self.schema_slide("process", spec, spec["items"])
        if slide is not None:
            return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        if max(len(plain_text(i["label"])) for i in items) > 24 or n > 6:
            return self._process_vertical(slide, box, items)
        has_body = any(_item_texts(i)[1] for i in items)
        overlap = Inches(0.08)
        w = (box.w + overlap * (n - 1)) // n
        head_h = min(Inches(1.1), box.h // (2 if has_body else 1))
        if not has_body:
            head_h = min(Inches(1.6), box.h)
        y = box.y if has_body else box.y + (box.h - head_h) // 2
        labels = [i["label"] for i in items]
        icons = self.pick_icons(spec, items)
        isz = int(min(Inches(0.65), w * 0.3))
        # a chevron's usable text area is roughly its width minus both points
        size = fit_each(labels, int(w * 0.58), head_h, 22, 10, char_w=0.62)
        if size < 13:
            return self._process_vertical(slide, box, items)
        if icons and not has_body:
            head_h = min(head_h, box.h - isz - Inches(0.2))
            y = box.y + (box.h - head_h + isz + Inches(0.2)) // 2
        for k, item in enumerate(items):
            x = box.x + k * (w - overlap)
            kind = MSO_SHAPE.PENTAGON if k == 0 else MSO_SHAPE.CHEVRON
            color = self.pal(0) if k % 2 == 0 else self.pal(1)
            shape(slide, kind, Box(x, y, w, head_h), fill=color,
                  text=item["label"], size=size, bold=True, margin=Inches(0.02))
            if icons and not has_body:
                self.icon(slide, icons[k], x + (w - isz) // 2, y - isz - Inches(0.2), isz, color)
        if has_body:
            body_top = y + head_h + Inches(0.2)
            bh = box.y + box.h - body_top
            bodies = [_item_texts(i)[1] for i in items]
            bsize = min(fit_pt([plain_text(t) for t in b], w - Inches(0.4), bh, 22 if n <= 4 else 18, 10)
                        for b in bodies if b) \
                if any(bodies) else 14
            bh = min(bh, max(max(text_height([plain_text(t) for t in b], w - Inches(0.4), bsize)
                                 for b in bodies if b) + Inches(0.4), int(bh * 0.7)))
            if icons:
                bh = min(box.y + box.h - body_top, bh + isz + Inches(0.2))
            shift = (box.y + box.h - (body_top + bh)) * 2 // 5   # centre the diagram in the free space
            for shp in list(slide.shapes)[-n:]:
                shp.top = shp.top + shift
            body_top += shift
            for k, b in enumerate(bodies):
                if not b and not icons:
                    continue
                x = box.x + k * (w - overlap)
                color = self.pal(0) if k % 2 == 0 else self.pal(1)
                rect = shape(slide, MSO_SHAPE.RECTANGLE, Box(x + Inches(0.05), body_top, w - Inches(0.2), bh),
                             fill=color, brightness=0.88, text=b or [""], size=bsize,
                             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, margin=Inches(0.1))
                if icons:
                    rect.text_frame.margin_top = isz + Inches(0.2)
                    self.icon(slide, icons[k], x + (w - Inches(0.15) - isz) // 2, body_top + Inches(0.1), isz, color)
        return slide

    def _process_vertical(self, slide, box, items):
        """Numbered steps top-to-bottom, for steps described by whole sentences."""
        n = len(items)
        gap = Inches(0.18)
        row_h = min(Inches(0.95), (box.h - gap * (n - 1)) // n)
        texts = [("**" + i["label"] + "**" + (": " + " ".join(_item_texts(i)[1]) if _item_texts(i)[1] else ""))
                 if _item_texts(i)[1] else i["label"] for i in items]
        size = fit_each(texts, box.w - row_h - Inches(0.6), row_h, 22, 11)
        total = n * row_h + (n - 1) * gap
        y0 = box.y + (box.h - total) // 2
        icons = self.pick_icons(self._spec, items)
        isz = int(row_h * 0.6)
        if icons:
            size = min(size, fit_each(texts, box.w - row_h - isz - Inches(0.8), row_h, 22, 11))
        for k, text in enumerate(texts):
            y = y0 + k * (row_h + gap)
            color = self.pal(0) if k % 2 == 0 else self.pal(1)
            shape(slide, MSO_SHAPE.OVAL, Box(box.x, y, row_h, row_h), fill=color, text=str(k + 1),
                  size=int(row_h / 12700 * 0.4), bold=True, margin=0)
            row = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE,
                        Box(box.x + row_h + Inches(0.15), y, box.w - row_h - Inches(0.15), row_h),
                        fill=color, brightness=0.85, text=text, size=size, align=PP_ALIGN.LEFT, margin=Inches(0.2))
            if icons:
                row.text_frame.margin_left = isz + Inches(0.4)
                self.icon(slide, icons[k], box.x + row_h + Inches(0.3), y + (row_h - isz) // 2, isz, color)
            if k < n - 1:
                arrow(slide, box.x + row_h // 2, y + row_h, box.x + row_h // 2, y + row_h + gap, color=color,
                      width=2)
        return slide

    def s_cycle(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        has_body = any(_item_texts(i)[1] for i in items)
        # the circle occupies the left part when there are descriptions, the centre otherwise
        diam = min(box.h, box.w * (0.55 if has_body else 0.9))
        cx = box.x + (diam / 2 if has_body else box.w / 2)
        cy = box.y + box.h / 2
        node = min(Inches(1.6), diam * (0.33 if n <= 4 else 0.29 if n <= 6 else 0.25))
        r = (diam - node) / 2
        rx = r * (1.0 if has_body else 1.35)
        pts = []
        for k in range(n):
            a = -math.pi / 2 + 2 * math.pi * k / n
            pts.append((cx + rx * math.cos(a), cy + r * math.sin(a)))
        # arrows between nodes (drawn first so nodes sit on top)
        for k in range(n):
            (x1, y1), (x2, y2) = pts[k], pts[(k + 1) % n]
            d = math.hypot(x2 - x1, y2 - y1) or 1
            ux, uy = (x2 - x1) / d, (y2 - y1) / d
            pad = node / 2 + Inches(0.08)
            arrow(slide, x1 + ux * pad, y1 + uy * pad, x2 - ux * pad, y2 - uy * pad, width=2.25)
        labels = [i["label"] for i in items]
        size = fit_each(labels, node * 0.62, node * 0.55, 16, 8, char_w=0.64)
        for k, (x, y) in enumerate(pts):
            shape(slide, MSO_SHAPE.OVAL, Box(int(x - node / 2), int(y - node / 2), int(node), int(node)),
                  fill=self.pal(k % 6), text=labels[k], size=size, bold=True, margin=Inches(0.04))
        if has_body:
            lx = int(box.x + diam + GAP * 2)
            lw = box.x + box.w - lx
            rows = [f"**{i['label']}**" + (": " + " ".join(_item_texts(i)[1]) if _item_texts(i)[1] else "")
                    for i in items]
            size = fit_pt([plain_text(r) for r in rows], lw, box.h, 18, 10, gap=0.6)
            textbox(slide, Box(lx, box.y, lw, box.h), rows, size, anchor=MSO_ANCHOR.MIDDLE)
        return slide

    def s_timeline(self, spec):
        items = spec["items"]
        slide = self.schema_slide("timeline", spec, [
            {"label": i["label"], "text": "", "details": [plain_text("\n".join(filter(None, [i.get("text", "")] + i.get("details", []))))]}
            for i in items])
        if slide is not None:
            return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        mid = box.y + box.h // 2
        seg = box.w // n
        arrow(slide, box.x, mid, box.x + box.w, mid, color=self.pal(0), width=3)
        dot = Inches(0.32)
        half = box.h // 2 - dot
        bodies = [" ".join(_item_texts(i)[1]) for i in items]
        bsize = fit_each(bodies, seg - Inches(0.15), half - Inches(0.6), 18, 10)
        lsize = fit_each([i["label"] for i in items], seg - Inches(0.15), Inches(0.45), 20, 10, char_w=0.6)
        for k, item in enumerate(items):
            cx = box.x + seg * k + seg // 2
            shape(slide, MSO_SHAPE.OVAL, Box(cx - dot // 2, mid - dot // 2, dot, dot), fill=self.pal(k % 6))
            up = k % 2 == 0
            lbl_h = Inches(0.45)
            body = bodies[k]
            bh = text_height([plain_text(body)], seg - Inches(0.1), bsize) if body else 0
            # renderers wrap wider than the estimate; leave slack so upper text never reaches the axis
            bh = min(int(bh * 1.2) + Inches(0.1), half - lbl_h)
            if up:
                ly = mid - dot - lbl_h - bh
            else:
                ly = mid + dot
            textbox(slide, Box(cx - seg // 2 + Inches(0.05), ly, seg - Inches(0.1), lbl_h), item["label"],
                    lsize, color=self.pal(k % 6), align=PP_ALIGN.CENTER, bold=True,
                    anchor=MSO_ANCHOR.BOTTOM if up else MSO_ANCHOR.TOP)
            if body:
                textbox(slide, Box(cx - seg // 2 + Inches(0.05), ly + lbl_h, seg - Inches(0.1), bh), body,
                        bsize, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.TOP)
            arrow(slide, cx, mid - dot // 2 if up else mid + dot // 2, cx,
                  mid - dot if up else mid + dot, color=self.pal(k % 6), width=1.5, head=False)
        return slide

    def s_hierarchy(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        root = items[0] if len(items) == 1 else {"text": spec["title"], "children": items}

        def depth(node):
            return 1 + max((depth(c) for c in node["children"]), default=0)

        def leaves(node):
            return sum(leaves(c) for c in node["children"]) or 1

        levels = min(depth(root), 4)
        vgap = Inches(0.45)
        node_h = min(Inches(1.1), (box.h - vgap * (levels - 1)) // levels)
        total_leaves = leaves(root)
        unit = box.w / total_leaves
        node_w = int(min(Inches(3.0), unit - Inches(0.15)))
        # a wide first level with narrow leaves: stack deepest level as a list under its parent
        stack_last = unit < Inches(1.2) and levels >= 3
        if stack_last:
            def trim(node, d=1):
                return {"text": node["text"], "children": [] if d == levels - 1 else
                        [trim(c, d + 1) for c in node["children"]],
                        "list": [c["text"] for c in node["children"]] if d == levels - 1 else []}
            root = trim(root)
            levels -= 1
            total_leaves = leaves(root)
            unit = box.w / total_leaves
            node_w = int(min(Inches(3.0), unit - Inches(0.15)))
            node_h = min(Inches(0.9), (box.h - vgap * levels) // (levels + 1.8))

        def width(node):   # parents may be wider than leaves
            return int(min(Inches(3.0), leaves(node) * unit - Inches(0.15)))

        if not stack_last:                       # centre the tree vertically
            used = levels * node_h + (levels - 1) * vgap
            box = Box(box.x, box.y + (box.h - used) * 2 // 5, box.w, used)

        by_level = {}

        def collect(node, lvl=0):
            by_level.setdefault(lvl, []).append((plain_text(node["text"]), width(node)))
            for c in node["children"]:
                collect(c, lvl + 1)
        collect(root)
        sizes = {lvl: min(fit_pt([t], w - Inches(0.1), node_h, 20 if lvl == 0 else 18, 8, char_w=0.62)
                          for t, w in lbls) for lvl, lbls in by_level.items()}

        def place(node, x0, lvl):
            span = leaves(node) * unit
            cx = x0 + span / 2
            y = box.y + lvl * (node_h + vgap)
            fill = self.pal(min(lvl, 5))
            nw = width(node) if not node.get("list") else node_w
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(int(cx - nw / 2), int(y), nw, int(node_h)),
                  fill=fill, brightness=0 if lvl < 2 else 0.75, text=node["text"], size=sizes.get(lvl, 12),
                  bold=lvl == 0)
            if node.get("list"):
                ly = y + node_h + Inches(0.1)
                lh = box.y + box.h - ly
                ls = fit_pt([plain_text(t) for t in node["list"]], node_w, lh, 13, 8, gap=0.2)
                shape(slide, MSO_SHAPE.RECTANGLE, Box(int(cx - node_w / 2), int(ly), node_w, int(lh)),
                      fill=fill, brightness=0.85, text=node["list"], size=ls, align=PP_ALIGN.LEFT,
                      anchor=MSO_ANCHOR.TOP)
            if node["children"] and lvl + 1 < levels + (1 if stack_last else 0) + 1:
                bottom = y + node_h
                ymid = bottom + vgap / 2
                xs = []
                x = x0
                for c in node["children"]:
                    cspan = leaves(c) * unit
                    xs.append(x + cspan / 2)
                    place(c, x, lvl + 1)
                    x += cspan
                line_color = MSO_THEME_COLOR.TEXT_2
                arrow(slide, cx, bottom, cx, ymid, color=line_color, width=1.25, head=False)
                if len(xs) > 1:
                    arrow(slide, xs[0], ymid, xs[-1], ymid, color=line_color, width=1.25, head=False)
                for cxx in xs:
                    arrow(slide, cxx, ymid, cxx, ymid + vgap / 2, color=line_color, width=1.25, head=False)
        place(root, box.x, 0)
        return slide

    def s_cards(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        if spec.get("variant") == "rows":
            return self._card_rows(slide, box, items)
        n = len(items)
        cols = {1: 1, 2: 2, 3: 3, 4: 2, 5: 3, 6: 3}.get(n, 3)
        rows = math.ceil(n / cols)
        cw = (box.w - GAP * (cols - 1)) // cols
        full = (box.h - GAP * (rows - 1)) // rows
        head = min(Inches(0.65), full // 3)
        bodies = [_item_texts(i)[1] for i in items]
        bsize = min((fit_pt([plain_text(t) for t in b], cw - Inches(0.3), full - head - Inches(0.25), 24, 10)
                     for b in bodies if b), default=16)
        lsize = fit_each([i["label"] for i in items], cw - Inches(0.4), head, 22, 11, char_w=0.6)
        need = max((text_height([plain_text(t) for t in b], cw - Inches(0.3), bsize) for b in bodies if b),
                   default=0)
        # cards take at least two thirds of the height they could have, so the grid fills the slide
        ch = min(full, max(head + need + Inches(0.45), int(full * 0.7), Inches(1.6)))
        top = box.y + (box.h - (ch * rows + GAP * (rows - 1))) * 2 // 5
        icons = self.pick_icons(spec, items)
        isz = int(head * 0.72)
        if icons:
            lsize = min(lsize, fit_each([i["label"] for i in items], cw - Inches(0.4) - isz, head, 22, 11, char_w=0.6))
        for k, item in enumerate(items):
            r, c = divmod(k, cols)
            # centre an incomplete last row
            offset = (cols - (n - r * cols)) * (cw + GAP) // 2 if r == rows - 1 else 0
            x = box.x + offset + c * (cw + GAP)
            y = top + r * (ch + GAP)
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(x, y, cw, ch), fill=color, brightness=0.85)
            hd = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(x, y, cw, head), fill=color,
                       text=item["label"], size=lsize, bold=True, align=PP_ALIGN.LEFT, margin=Inches(0.15))
            if icons:
                hd.text_frame.margin_left = isz + Inches(0.25)
                self.icon(slide, icons[k], x + Inches(0.13), y + (head - isz) // 2, isz,
                          text_on(color, 0, lsize, True))
            if bodies[k]:
                textbox(slide, Box(x + Inches(0.05), y + head + Inches(0.05), cw - Inches(0.1),
                                   ch - head - Inches(0.1)), bodies[k], bsize, anchor=MSO_ANCHOR.MIDDLE)
        return slide

    def _card_rows(self, slide, box, items):
        """Cards as horizontal bands: coloured label on the left, description on the right.
        Used to vary a run of card slides."""
        n = len(items)
        gap = Inches(0.18)
        full = (box.h - gap * (n - 1)) // n
        lw = int(box.w * (0.16 if all(len(plain_text(i["label"])) <= 4 for i in items) else 0.3))
        bw = box.w - lw
        bodies = [_item_texts(i)[1] for i in items]
        lsize = fit_each([i["label"] for i in items], lw - Inches(0.4), full - Inches(0.1), 22, 11, char_w=0.6)
        bsize = min((fit_pt([plain_text(t) for t in b], bw - Inches(0.5), full - Inches(0.1), 22, 10)
                     for b in bodies if b), default=16)
        need = max([text_height([plain_text(t) for t in b], bw - Inches(0.5), bsize) for b in bodies if b]
                   + [text_height([plain_text(i["label"])], lw - Inches(0.4), lsize) for i in items])
        rh = min(full, max(need + Inches(0.25), Inches(0.85)))
        top = box.y + (box.h - (rh * n + gap * (n - 1))) * 2 // 5
        icons = self.pick_icons(self._spec, items)
        isz = int(min(rh * 0.6, Inches(0.6)))
        if icons:
            lsize = min(lsize, fit_each([i["label"] for i in items], lw - Inches(0.5) - isz, rh - Inches(0.1), 22, 11,
                                        char_w=0.6))
        for k, item in enumerate(items):
            y = top + k * (rh + gap)
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x + lw, y, bw, rh), fill=color, brightness=0.85)
            pent = shape(slide, MSO_SHAPE.PENTAGON, Box(box.x, y, lw + Inches(0.25), rh), fill=color,
                         text=item["label"], size=lsize, bold=True, align=PP_ALIGN.LEFT, margin=Inches(0.2))
            if icons:
                pent.text_frame.margin_left = isz + Inches(0.3)
                self.icon(slide, icons[k], box.x + Inches(0.15), y + (rh - isz) // 2, isz,
                          text_on(color, 0, lsize, True))
            if bodies[k]:
                textbox(slide, Box(box.x + lw + Inches(0.4), y, bw - Inches(0.5), rh), bodies[k], bsize,
                        anchor=MSO_ANCHOR.MIDDLE)
        return slide

    def s_stats(self, spec):
        if len(spec["items"]) == 1:
            slide = self._key_figure(spec)
            if slide is not None:
                return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        cw = (box.w - GAP * (n - 1)) // n
        if n == 1:          # a lone figure (no key-figure layout): one centred card, details below
            cw = min(box.w, Inches(6))
            box = Box(box.x + (box.w - cw) // 2, box.y, cw, box.h)
            items = [dict(items[0], text=" ".join([items[0].get("text", "")] + items[0].get("details", [])))]
        longest = max((i["value"] for i in items), key=len)
        vsize = fit_pt([longest], cw, Inches(1.3), 60, 28, spacing=1.0, char_w=0.58)
        # keep each figure on one line ("60% à 95%" must not wrap onto the caption)
        vsize = max(min(vsize, (cw - Inches(0.3)) / 12700 / (max(len(longest), 1) * 0.72)), 20)
        tsize = fit_each([i["text"] for i in items], cw - Inches(0.4), Inches(1.35), 20, 11)
        icons = self.pick_icons(spec, [{"label": i["text"]} for i in items])
        dy = Inches(0.65) if icons else 0
        ch = min(box.h, Inches(3.4) + dy)
        y = box.y + (box.h - ch) // 2
        for k, item in enumerate(items):
            x = box.x + k * (cw + GAP)
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(x, y, cw, ch), fill=color, brightness=0.87)
            if icons:
                self.icon(slide, icons[k], x + (cw - Inches(0.6)) // 2, y + Inches(0.25), Inches(0.6), color)
            textbox(slide, Box(x, y + Inches(0.2) + dy, cw, Inches(1.4)), item["value"], vsize,
                    color=color, align=PP_ALIGN.CENTER, bold=True, anchor=MSO_ANCHOR.MIDDLE, on=(color, 0.87))
            textbox(slide, Box(x + Inches(0.15), y + Inches(1.65) + dy, cw - Inches(0.3), ch - Inches(1.8) - dy),
                    item["text"], tsize, align=PP_ALIGN.CENTER)
        return slide

    def _key_figure(self, spec):
        """One headline number on the template's key-figure layout (e.g. Key_Figure_1):
        the figure and its caption on one side, the explanation on the other."""
        found = self.layouts.key_figure_layout()
        item = spec["items"][0]
        lead = spec.get("lead", "")
        details = item.get("details", [])
        if found is None or not (lead or details) or spec.get("banner") or spec.get("takeaway"):
            return None
        layout, slots = found
        slide = self.prs.slides.add_slide(layout)
        self.slots[id(slide)] = self.layouts.slots(layout)
        self.fill(slide, self.slots[id(slide)]["title"], spec["title"], shrink=True)
        self.fill(slide, slots["figure"], item["value"], shrink=True, min_pt=20)
        self.fill(slide, slots["caption"], item.get("text", ""), shrink=True, min_pt=11)
        if details and lead and slots["heading"] is not None:
            self.fill(slide, slots["heading"], lead, shrink=True, min_pt=12)
            body = details
        else:
            body = [d for d in ([lead] if lead else []) + details if d]
        self.fill(slide, slots["body"], *body, shrink=True, min_pt=12)
        if self.footer:
            for lph in layout.placeholders:
                if lph.placeholder_format.type == PP_PLACEHOLDER.FOOTER:
                    slide.shapes.clone_placeholder(lph)
                    self.fill(slide, lph.placeholder_format.idx, self.footer)
        return slide

    def s_pyramid(self, spec):
        slide = self.schema_slide("pyramid", spec, spec["items"])
        if slide is not None:
            return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        pw = min(box.w * 0.5, box.h * 1.3)
        lh = box.h / n
        size = fit_pt([max((i["label"] for i in items), key=len)], pw * 0.45, lh, 18, 10)
        for k, item in enumerate(items):
            top_w = pw * k / n
            bot_w = pw * (k + 1) / n
            y = box.y + k * lh
            x = box.x + (pw - bot_w) / 2
            shp = shape(slide, MSO_SHAPE.TRAPEZOID if k else MSO_SHAPE.ISOSCELES_TRIANGLE,
                        Box(int(x), int(y), int(bot_w), int(lh - Inches(0.04))), fill=self.pal(k % 6),
                        text=item["label"] if k else "", size=size, bold=True)
            if k:
                shp.adjustments[0] = (bot_w - top_w) / 2 / (lh - Inches(0.04)) if lh else 0.25
            else:
                textbox(slide, Box(int(box.x + pw / 2 - pw / (2 * n)), int(y + lh * 0.45), int(pw / n), int(lh * 0.55)),
                        item["label"], min(size, 14), color=LIGHT, align=PP_ALIGN.CENTER, bold=True)
            body = " ".join(_item_texts(item)[1])
            if body:
                tx = int(box.x + pw + GAP)
                textbox(slide, Box(tx, int(y), box.x + box.w - tx, int(lh)), body,
                        fit_pt([body], box.x + box.w - tx, lh, 16, 10), anchor=MSO_ANCHOR.MIDDLE)
        return slide

    def s_comparison(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        cols = spec["columns"]
        if any(c.get("code") is not None for c in cols):
            return self._code_columns(slide, box, cols)
        n = len(cols)
        cw = (box.w - GAP * (n - 1)) // n
        head = Inches(0.65)
        texts = [[plain_text(c["text"])] * bool(c["text"]) + [plain_text(i["text"]) for i in _flatten(c["items"])]
                 for c in cols]
        size = min(fit_pt(t, cw - Inches(0.5), box.h - head - Inches(0.2), 22, 11) for t in texts)
        need = max(text_height(t, cw - Inches(0.5), size, gap=0.4) for t in texts) + Inches(0.5)
        used = head + Inches(0.1) + min(box.h - head - Inches(0.1), max(need, Inches(2)))
        box = Box(box.x, box.y + (box.h - used) * 2 // 5, box.w, used)
        for k, col in enumerate(cols):
            x = box.x + k * (cw + GAP)
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(x, box.y, cw, head), fill=color,
                  text=col["title"], size=20, bold=True)
            need = max(text_height(t, cw - Inches(0.5), size, gap=0.4) for t in texts) + Inches(0.5)
            bh = min(box.h - head - Inches(0.1), max(need, Inches(2)))
            body = shape(slide, MSO_SHAPE.RECTANGLE, Box(x, box.y + head + Inches(0.1), cw, bh),
                         fill=color, brightness=0.87)
            tf = body.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.TOP
            tf.margin_left = tf.margin_right = Inches(0.2)
            tf.margin_top = Inches(0.15)
            first = True
            if col["text"]:
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT
                add_runs(p, col["text"], size=size, color=DARK, italic=True)
                first = False
            for text, level in _flatten_levels(col["items"]):
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.space_before = Pt(size * 0.4)
                p.alignment = PP_ALIGN.LEFT
                _bullet(p, level)
                add_runs(p, text, size=size if level == 0 else size - 2, color=DARK)
        return slide

    def _code_columns(self, slide, box, cols):
        """Code side by side (e.g. current code / recommended fix): a coloured header per column over a monospace
        panel. One font size for all columns, the largest at which every column fits; long lines wrap, never cut."""
        n = len(cols)
        cw = (box.w - GAP * (n - 1)) // n
        head = Inches(0.55)
        panel_h = box.h - head - Inches(0.1)
        pad = Inches(0.2)
        inner_w_pt = (cw - 2 * pad) / 12700
        inner_h_pt = (panel_h - 2 * pad) / 12700

        def need(col, pt):
            # Courier advances 0.6 em; word wrapping breaks earlier than the character count, so a wrapped line is
            # counted as taking 30% more rows than the plain division says
            per_line = max(int(inner_w_pt / (pt * 0.62)), 10)
            rows = 0.0
            for l in col["code"].split("\n"):
                n = len(l.rstrip())
                rows += 1 if n <= per_line else (n / per_line) * 1.3 + 0.5
            if col.get("text"):
                rows += len(plain_text(col["text"])) / max(int(inner_w_pt / (pt * 0.5)), 10) * 1.2 + 1
            return rows * pt * 1.2

        longest = max((len(l.rstrip()) for c in cols for l in c["code"].split("\n")), default=1)
        # prefer a size at which no line wraps, but not below 10 pt for that (long lines wrap instead); never above 14 pt
        size = min(14.0, max(10.0, inner_w_pt / (max(longest, 1) * 0.62)))
        while size > 7 and any(need(c, size) > inner_h_pt for c in cols):
            size -= 0.5
        used = max(need(c, size) for c in cols) + 2 * pad / 12700
        bh = min(panel_h, max(int(used * 12700), Inches(1.2)))
        for k, col in enumerate(cols):
            x = box.x + k * (cw + GAP)
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(x, box.y, cw, head), fill=color,
                  text=col["title"], size=16, bold=True)
            body = shape(slide, MSO_SHAPE.RECTANGLE, Box(x, box.y + head + Inches(0.1), cw, bh),
                         fill=MSO_THEME_COLOR.TEXT_1, brightness=0.9)
            tf = body.text_frame
            tf.word_wrap = True
            tf.vertical_anchor = MSO_ANCHOR.TOP
            tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = pad
            first = True
            if col.get("text"):
                p = tf.paragraphs[0]
                p.alignment = PP_ALIGN.LEFT
                add_runs(p, col["text"], size=max(size - 1, 7), color=DARK, italic=True)
                first = False
            for line in col["code"].split("\n"):
                p = tf.paragraphs[0] if first else tf.add_paragraph()
                first = False
                p.alignment = PP_ALIGN.LEFT
                run = p.add_run()
                run.text = line.rstrip() or " "
                run.font.name = "Courier New"
                run.font.size = Pt(size)
                run.font.color.theme_color = DARK
        return slide

    def s_stairs(self, spec):
        """Maturity staircase: one step per level, rising left to right, with the level's
        description in the step and its outcome (first sub-item) as a caption under it."""
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        gap = Inches(0.18)
        cw = (box.w - gap * (n - 1)) // n
        captions = [i["details"][0] if i.get("details") else "" for i in items]
        bodies = [[t for t in [i.get("text", "")] + i.get("details", [])[1:] if t] for i in items]
        cap_h = Inches(0.6) if any(captions) else 0
        badge = int(min(Inches(0.5), cw * 0.22))
        base = box.y + box.h - cap_h                     # bottom line of every step
        tallest = box.h - cap_h - badge // 2
        rise = int(tallest * 0.35 / max(n - 1, 1))       # each step rises by this much
        shortest = tallest - rise * (n - 1)
        lsize = fit_each([i["label"] for i in items], cw - Inches(0.3), Inches(0.7), 20, 11, char_w=0.6)
        lh_max = max(text_height([plain_text(i["label"])], cw - Inches(0.3), lsize) for i in items)
        room = shortest - badge // 2 - lh_max - Inches(0.4)
        bsize = min((fit_pt([plain_text(t) for t in b], cw - Inches(0.3), room, 18, 10)
                     for b in bodies if b), default=14)
        csize = fit_each([c for c in captions if c] or ["x"], cw, cap_h or Inches(0.5), 14, 10)
        for k, item in enumerate(items):
            x = box.x + k * (cw + gap)
            h = shortest + rise * k
            y = base - h
            color = self.pal(k % 6)
            shape(slide, MSO_SHAPE.RECTANGLE, Box(x, y, cw, h), fill=color, brightness=0.87)
            shape(slide, MSO_SHAPE.RECTANGLE, Box(x, y, cw, Inches(0.06)), fill=color)
            shape(slide, MSO_SHAPE.OVAL, Box(x + Inches(0.12), y - badge // 2, badge, badge), fill=color,
                  text=str(k + 1), size=int(badge / 12700 * 0.45), bold=True, margin=0)
            ty = y + badge // 2 + Inches(0.12)
            lh = text_height([plain_text(item["label"])], cw - Inches(0.3), lsize) + Inches(0.05)
            textbox(slide, Box(x + Inches(0.15), ty, cw - Inches(0.3), lh), item["label"], lsize,
                    color=color, bold=True, on=(color, 0.87))
            if bodies[k]:
                textbox(slide, Box(x + Inches(0.15), ty + lh + Inches(0.05), cw - Inches(0.3),
                                   base - ty - lh - Inches(0.15)), bodies[k], bsize)
            if captions[k]:
                textbox(slide, Box(x, base + Inches(0.08), cw, cap_h - Inches(0.08)), captions[k], csize,
                        align=PP_ALIGN.CENTER, bold=True)
        return slide

    def s_flow(self, spec):
        """Inputs -> core -> outputs (the case-study one-pager): side boxes on a light tint, the
        core in the dark brand colour, arrows between them, and optional panels underneath."""
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items, panels = spec["items"], spec.get("panels", [])
        n = len(items)
        core = n // 2 if n % 2 else None
        aw = Inches(0.5)                                  # room for each arrow
        weights = [1.45 if k == core else 1.0 for k in range(n)]
        unit = (box.w - aw * (n - 1)) / sum(weights)
        fh = int(box.h * (0.58 if panels else 0.8))
        fy = box.y + (0 if panels else (box.h - fh) * 2 // 5)
        dark = self.dark_accent()
        x = box.x
        # one body size for every box so the three read as one diagram
        bsize = min(fit_pt([plain_text(t) for t in _item_texts(i)[1]] or ["x"], int(unit * weights[k]) - Inches(0.4),
                           fh - Inches(0.7), 15, 9) for k, i in enumerate(items))
        for k, item in enumerate(items):
            w = int(unit * weights[k])
            is_core = k == core
            label, body = _item_texts(item)
            lsize = fit_pt([plain_text(label)], w - Inches(0.4), Inches(0.6), 20 if is_core else 16, 11, char_w=0.6)
            fill, bright = (dark, 0.0) if is_core else (self.pal(0), 0.9)
            shp = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(x, fy, w, fh), fill=fill, brightness=bright)
            shp.adjustments[0] = 0.08
            tf = shp.text_frame
            tf.word_wrap = True
            tf.margin_left = tf.margin_right = Inches(0.2)
            tf.margin_top = tf.margin_bottom = Inches(0.12)
            tf.vertical_anchor = MSO_ANCHOR.MIDDLE if is_core else MSO_ANCHOR.TOP
            align = PP_ALIGN.CENTER if is_core else PP_ALIGN.LEFT
            fg = text_on(fill, bright, bsize)
            set_text(tf, [label] + body, bsize, color=fg, align=align)
            p0 = tf.paragraphs[0]
            for r in p0.runs:
                r.font.size, r.font.bold = Pt(lsize), True
                if not is_core:
                    r.font.color.theme_color = self.pal(0)
                    r.font.color.brightness = shade_for(self.pal(0), lsize, True, (self.pal(0), 0.9))
            for p in tf.paragraphs[1:]:
                p.space_before = Pt(bsize * (0.6 if p is tf.paragraphs[1] else 0.25))
            if k < n - 1:
                ax = x + w + Inches(0.1)
                shape(slide, MSO_SHAPE.CHEVRON, Box(ax, fy + fh // 2 - Inches(0.2), aw - Inches(0.2), Inches(0.4)),
                      fill=self.pal(1))
            x += w + aw
        if panels:
            py = fy + fh + Inches(0.3)
            ph = box.y + box.h - py
            m = len(panels)
            pw = (box.w - GAP * (m - 1)) // m
            lsize = fit_each([p["label"] for p in panels], pw - Inches(0.4), Inches(0.4), 13, 10, char_w=0.62)
            bodies = [_item_texts(p)[1] for p in panels]
            bsize = min([fit_pt([plain_text(t) for t in b], pw - Inches(0.4), ph - Inches(0.6), 14, 9)
                         for b in bodies if b] + [bsize + 1])
            for k, pnl in enumerate(panels):
                px = box.x + k * (pw + GAP)
                shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(px, py, pw, ph), fill=self.pal(2),
                      brightness=0.9).adjustments[0] = 0.08
                textbox(slide, Box(px + Inches(0.2), py + Inches(0.12), pw - Inches(0.4), Inches(0.4)),
                        pnl["label"].upper(), lsize, color=self.pal(2), bold=True, on=(self.pal(2), 0.9))
                if bodies[k]:
                    textbox(slide, Box(px + Inches(0.2), py + Inches(0.55), pw - Inches(0.4), ph - Inches(0.65)),
                            bodies[k], bsize)
        return slide

    # --- brand library helpers ----------------------------------------------------
    @staticmethod
    def _off(spec, key):
        return str(spec.get(key, "")).lower() in ("off", "no", "false", "0", "none")

    def pick_icons(self, spec, items) -> list | None:
        """One icon per item (matched on its label, then its text), or None."""
        if not self.icons or self._off(spec, "icons"):
            return None
        forced = str(spec.get("icons", "")).lower() in ("on", "yes", "true", "1")
        texts = [plain_text(i.get("label") or i.get("text", "")) + "\x00" +
                 plain_text(" ".join(_item_texts(i)[1]) if i.get("label") else "") for i in items]
        return self.icons.pick(texts, 0.25 if forced else 0.35)

    def icon(self, slide, iid, x, y, size, color):
        self.icons.place(slide, iid, int(x), int(y), int(size), SCHEME_VAL.get(color, "accent1"))

    def schema_slide(self, kind, spec, items, root=None):
        """Draw the slide with the brand's own diagram when one exists for this kind and count
        and the text fits; returns the slide or None (caller draws its own)."""
        if not self.schemas or self._off(spec, "schema") or spec.get("banner") or spec.get("takeaway"):
            return None
        sch = Schema.find(kind, len(items), self.prs)
        if sch is None:
            return None
        flat = [{"label": plain_text(i.get("label", "")),
                 "body": plain_text(" ".join(_item_texts(i)[1]))} for i in items]
        rt = None
        if root is not None:
            rt = {"label": plain_text(root.get("label", "")), "body": plain_text(" ".join(_item_texts(root)[1]))}
        if sch.layout(flat, rt) is None:
            return None
        lead = spec.get("lead", "")
        layout = self.layouts.get("title_only")
        if lead and (len(plain_text(lead)) > 120 or self.layouts.slots(layout).get("subtitle") is None):
            return None
        slide = self.new_slide("title_only", spec["title"])
        if lead:
            self.fill(slide, self.slot(slide, "subtitle"), lead)
        sch.fill(slide, flat, rt, alt=alt_text(spec, self.lang))
        return slide

    # --- v0.4 kinds ----------------------------------------------------------------
    def s_funnel(self, spec):
        items = spec["items"]
        slide = self.schema_slide("funnel", spec, items)
        if slide is not None:
            return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        n = len(items)
        fw = int(min(box.w * 0.42, box.h * 1.25))
        lh = box.h // n
        gap = Inches(0.06)
        figures = [i["label"] if _is_num(i["label"]) else str(k + 1) for k, i in enumerate(items)]
        rows = [(" ".join(_item_texts(i)[1]) if _is_num(i["label"]) else
                 f"**{i['label']}**" + (": " + " ".join(_item_texts(i)[1]) if _item_texts(i)[1] else ""))
                for i in items]
        fsize = fit_each(figures, int(fw * 0.25), lh - gap, 24, 10, char_w=0.6)
        tx = box.x + fw + GAP
        rsize = fit_each(rows, box.x + box.w - tx, lh, 20, 10)
        for k in range(n):
            wide = fw * (1 - 0.7 * k / n)
            narrow = fw * (1 - 0.7 * (k + 1) / n)
            y = box.y + k * lh
            x = box.x + (fw - wide) / 2
            color = self.pal(k % 6)
            shp = shape(slide, MSO_SHAPE.TRAPEZOID, Box(int(x), int(y), int(wide), int(lh - gap)), fill=color)
            shp.rotation = 180
            shp.adjustments[0] = (wide - narrow) / 2 / min(wide, lh - gap)
            textbox(slide, Box(int(box.x + fw * 0.2), int(y), int(fw * 0.6), int(lh - gap)), figures[k], fsize,
                    color=text_on(color, 0, fsize, True), align=PP_ALIGN.CENTER, bold=True, anchor=MSO_ANCHOR.MIDDLE)
            arrow(slide, x + wide - (wide - narrow) / 4, y + (lh - gap) / 2, tx - Inches(0.1), y + (lh - gap) / 2,
                  color=color, width=1, head=False)
            textbox(slide, Box(tx, int(y), box.x + box.w - tx, int(lh - gap)), rows[k], rsize,
                    anchor=MSO_ANCHOR.MIDDLE)
        return slide

    def s_hub(self, spec):
        items = spec["items"]
        root = spec.get("root") or {"label": spec["title"], "text": "", "details": []}
        slide = self.schema_slide("hub", spec, items, root)
        if slide is not None:
            return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        n = len(items)
        cx, cy = box.x + box.w / 2, box.y + box.h / 2
        d = min(box.h * 0.5, Inches(2.7))
        cols = 2 if n <= 4 else 3
        cw = int(min(Inches(3.2), (box.w - d - GAP * 2) / 2 - GAP)) if n <= 6 else int(min(Inches(2.7), box.w / 4))
        ch = int(min(Inches(1.3), (box.h - GAP * 3) / (2 if n <= 4 else 3 if n <= 6 else 4)))
        icons = self.pick_icons(spec, items)
        isz = int(min(ch * 0.55, Inches(0.55))) if icons else 0
        texts = [[f"**{i['label']}**"] + _item_texts(i)[1] for i in items]
        size = min(fit_pt([plain_text(t) for t in tx], cw - isz - Inches(0.35), ch - Inches(0.1), 18, 10, gap=0.2)
                   for tx in texts)
        # children around the centre, on an ellipse that keeps every box inside the content area
        rx, ry = box.w / 2 - cw / 2, box.h / 2 - ch / 2
        pts = []
        for k in range(n):
            a = -math.pi / 2 + 2 * math.pi * (k + 0.5 * (n % 2 == 0 and n != 4)) / n if n != 4 else \
                -math.pi / 2 + math.pi / 4 + k * math.pi / 2
            pts.append((cx + rx * math.cos(a), cy + ry * math.sin(a)))
        for (x, y) in pts:
            arrow(slide, cx, cy, x, y, color=MSO_THEME_COLOR.TEXT_2, width=1.5, head=False)
        for k, ((x, y), item) in enumerate(zip(pts, items)):
            color = self.pal(k % 6)
            b = Box(int(x - cw / 2), int(y - ch / 2), cw, ch)
            card = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, b, fill=color, brightness=0.85, text=texts[k], size=size,
                         align=PP_ALIGN.LEFT, margin=Inches(0.15))
            if icons:
                card.text_frame.margin_left = isz + Inches(0.25)
                self.icon(slide, icons[k], b.x + Inches(0.12), b.y + (ch - isz) / 2, isz, color)
        rtext = [f"**{root['label']}**"] + _item_texts(root)[1]
        rsize = fit_pt([plain_text(t) for t in rtext], d * 0.72, d * 0.6, 22, 11, gap=0.2)
        shape(slide, MSO_SHAPE.OVAL, Box(int(cx - d / 2), int(cy - d / 2), int(d), int(d)), fill=self.pal(0),
              text=rtext, size=rsize, margin=Inches(0.1))
        return slide

    def s_rings(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec["items"]
        n = len(items)
        cw = (box.w - GAP * (n - 1)) // n
        d = int(min(cw * 0.72, box.h * 0.55, Inches(2.6)))
        tsize = fit_each([i["text"] for i in items], cw - Inches(0.2), box.h - d - Inches(0.5), 20, 11)
        th = max(text_height([plain_text(i["text"])], cw - Inches(0.2), tsize) for i in items)
        top = box.y + (box.h - d - Inches(0.3) - th) * 2 // 5
        vsize = fit_each([i["value"] for i in items], int(d * 0.62), int(d * 0.4), 40, 14, char_w=0.6)
        for k, item in enumerate(items):
            x = box.x + k * (cw + GAP) + (cw - d) // 2
            color = self.pal(k % 6)
            pct = max(0.0, min(1.0, item.get("percent") or 0))
            ring = shape(slide, MSO_SHAPE.DONUT, Box(x, top, d, d), fill=color, brightness=0.82)
            ring.adjustments[0] = 0.16
            if pct >= 0.999:
                full = shape(slide, MSO_SHAPE.DONUT, Box(x, top, d, d), fill=color)
                full.adjustments[0] = 0.16
            elif pct > 0:
                arc = shape(slide, MSO_SHAPE.BLOCK_ARC, Box(x, top, d, d), fill=color)
                arc.adjustments[0] = 162.0                              # start at 12 o'clock (270°)
                arc.adjustments[1] = ((270 + 360 * pct) % 360) * 0.6     # clockwise to the share
                arc.adjustments[2] = 0.16
            textbox(slide, Box(x, top + int(d * 0.3), d, int(d * 0.4)), item["value"], vsize, color=color,
                    align=PP_ALIGN.CENTER, bold=True, anchor=MSO_ANCHOR.MIDDLE)
            textbox(slide, Box(box.x + k * (cw + GAP) + Inches(0.1), top + d + Inches(0.25), cw - Inches(0.2),
                               box.y + box.h - top - d - Inches(0.25)), item["text"], tsize, align=PP_ALIGN.CENTER)
        return slide

    def s_gantt(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        scale, items = spec["scale"], spec["items"]
        ncol, n = len(scale), len(items)
        lw = int(box.w * 0.26)
        cw = (box.w - lw) / ncol
        head = Inches(0.45)
        rh = int(min(Inches(0.8), (box.h - head - Inches(0.1)) / n))
        h = head + rh * n
        top = box.y + (box.h - h) * 2 // 5
        hsize = fit_each(scale, int(cw - Inches(0.04)), head, 14, 8, char_w=0.6)
        for c, lab in enumerate(scale):
            x = box.x + lw + cw * c
            if c % 2 == 0:
                shape(slide, MSO_SHAPE.RECTANGLE, Box(int(x), top, int(cw), h), fill=MSO_THEME_COLOR.TEXT_1,
                      brightness=0.94)
            textbox(slide, Box(int(x), top, int(cw), head), lab, hsize, color=MSO_THEME_COLOR.TEXT_1,
                    align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, bold=True)
        lsize = fit_each([i["label"] for i in items], lw - Inches(0.2), rh, 18, 10)
        bar_h = int(rh * 0.62)
        rsize = fit_each([i["range"] for i in items], int(cw * 1.6), bar_h, 13, 8, char_w=0.6)
        for k, it in enumerate(items):
            y = top + head + k * rh
            color = self.pal(k % 6)
            textbox(slide, Box(box.x, y, lw - Inches(0.15), rh), it["label"], lsize, anchor=MSO_ANCHOR.MIDDLE,
                    bold=True)
            x0 = box.x + lw + cw * it["start"] + Inches(0.03)
            w = cw * (it["end"] - it["start"] + 1) - Inches(0.06)
            inside = _lines(it["range"], int(w - Inches(0.1)), rsize) == 1
            shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(int(x0), y + (rh - bar_h) // 2, int(w), bar_h), fill=color,
                  text=it["range"] if inside else None, size=rsize, margin=Inches(0.05))
            if not inside:
                after = x0 + w + Inches(1.65) <= box.x + box.w
                tx = x0 + w + Inches(0.05) if after else x0 - Inches(1.65)
                textbox(slide, Box(int(tx), y, Inches(1.6), rh), it["range"], rsize, color=MSO_THEME_COLOR.TEXT_1,
                        anchor=MSO_ANCHOR.MIDDLE, align=PP_ALIGN.LEFT if after else PP_ALIGN.RIGHT)
            if k:
                arrow(slide, box.x, y, box.x + box.w, y, color=MSO_THEME_COLOR.TEXT_2, width=0.5, head=False)
        return slide

    def s_matrix(self, spec):
        from .kinds import rating
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        header, rows = spec["header"], spec["rows"]
        ncols = max([len(header)] + [len(r) for r in rows])
        first = int(min(box.w * 0.34, max(Inches(1.8), box.w / ncols * 1.4)))
        cw = (box.w - first) / (ncols - 1)
        head = Inches(0.7)
        rh = int(min(Inches(0.85), (box.h - head) / max(len(rows), 1)))
        h = head + rh * len(rows)
        top = box.y + (box.h - h) * 2 // 5
        hsize = fit_each(header[1:], int(cw - Inches(0.1)), head, 16, 9)
        lsize = fit_each([r[0] for r in rows], first - Inches(0.2), rh, 18, 10)
        hcolor = self.pal(0)
        shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x, top, box.w, head), fill=hcolor)
        tcol = text_on(hcolor, 0, hsize, True)
        if header and header[0]:
            textbox(slide, Box(box.x + Inches(0.1), top, first - Inches(0.2), head), header[0], hsize, color=tcol,
                    bold=True, anchor=MSO_ANCHOR.MIDDLE)
        for c, lab in enumerate(header[1:]):
            textbox(slide, Box(int(box.x + first + cw * c), top, int(cw), head), lab, hsize, color=tcol,
                    align=PP_ALIGN.CENTER, bold=True, anchor=MSO_ANCHOR.MIDDLE)
        d = int(min(rh * 0.62, Inches(0.5), cw * 0.6))
        texts = [r[c] for r in rows for c in range(1, len(r)) if rating(r[c]) is None]
        csize = fit_each(texts, int(cw - Inches(0.1)), rh, 16, 9) if texts else 14
        for r, row in enumerate(rows):
            y = top + head + r * rh
            if r % 2:
                shape(slide, MSO_SHAPE.RECTANGLE, Box(box.x, y, box.w, rh), fill=hcolor, brightness=0.92)
            textbox(slide, Box(box.x + Inches(0.1), y, first - Inches(0.2), rh), row[0], lsize, bold=True,
                    anchor=MSO_ANCHOR.MIDDLE)
            for c in range(1, ncols):
                cell = row[c] if c < len(row) else ""
                x = box.x + first + cw * (c - 1)
                f = rating(cell)
                if f is None:
                    textbox(slide, Box(int(x), y, int(cw), rh), cell, csize, align=PP_ALIGN.CENTER,
                            anchor=MSO_ANCHOR.MIDDLE)
                    continue
                b = Box(int(x + (cw - d) / 2), y + (rh - d) // 2, d, d)
                ring = shape(slide, MSO_SHAPE.OVAL, b, fill=LIGHT, line=hcolor)
                ring.line.width = Pt(1.5)
                if f >= 0.999:
                    shape(slide, MSO_SHAPE.OVAL, b, fill=hcolor)
                elif f > 0:
                    pie = shape(slide, MSO_SHAPE.PIE, b, fill=hcolor)
                    pie.adjustments[0] = 162.0
                    pie.adjustments[1] = ((270 + 360 * f) % 360) * 0.6
        return slide

    def s_map(self, spec):
        groups = [g for g in spec.get("groups", []) if g["countries"]]
        if not groups or not has_map():
            items = [{"text": t, "children": []} for g in spec.get("groups", []) for t in g["items"]]
            return self.s_bullets({**spec, "kind": "bullets", "items": items})
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        tw = int(box.w * 0.4)
        colors = [self.pal(k % 6) for k in range(len(groups))]
        draw_europe(slide, (box.x + tw + GAP, box.y - Inches(0.3), box.w - tw - GAP, box.h + Inches(0.3)),
                    [(g["countries"], SCHEME_VAL[c]) for g, c in zip(groups, colors)], alt=alt_text(spec, self.lang))
        paras = []
        for g, c in zip(groups, colors):
            if g["label"]:
                paras.append((g["label"], {"bold": True, "color": c}))
            paras += [(t, {}) for t in g["items"]]
        size = fit_pt([plain_text(t) for t, _ in paras], tw - Inches(0.4), box.h, 20, 10, gap=0.4)
        tb = slide.shapes.add_textbox(box.x, box.y, tw, box.h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        for i, (text, over) in enumerate(paras):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.space_after = Pt(size * 0.35)
            if over:
                p.space_before = Pt(size * 0.6) if i else 0
                add_runs(p, "■ ", size=size, color=over["color"])
                add_runs(p, text, size=size, bold=True, color=DARK)
            else:
                _bullet(p, 1 if any(g["label"] for g in groups) else 0)
                add_runs(p, text, size=size - (1 if any(g["label"] for g in groups) else 0))
        _no_autofit(tf)
        return slide

    # --- data -----------------------------------------------------------------
    def s_table(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        header, rows = spec["header"], spec["rows"]
        ncols = max([len(header)] + [len(r) for r in rows])
        # column widths proportional to content length
        lens = [max([len(plain_text(header[c])) if c < len(header) else 0] +
                    [len(plain_text(r[c])) if c < len(r) else 0 for r in rows]) + 4 for c in range(ncols)]
        widths = [max(int(box.w * l / sum(lens)), Inches(0.8)) for l in lens]
        scale = box.w / sum(widths)
        widths = [int(w * scale) for w in widths]
        all_cells = [header] + rows
        size = 22 if len(all_cells) <= 6 else 20
        while size > 10:
            row_heights = [max(_lines(plain_text(r[c]) if c < len(r) else "", widths[c] - Inches(0.2), size)
                               for c in range(ncols)) * size * 1.25 * 12700 + Inches(0.16) for r in all_cells]
            if sum(row_heights) <= box.h:
                break
            size -= 1
        row_heights = [int(max(_lines(plain_text(r[c]) if c < len(r) else "", widths[c] - Inches(0.2), size)
                               for c in range(ncols)) * size * 1.25 * 12700 + Inches(0.16)) for r in all_cells]
        # airier rows on short tables, then centre the table in the free space
        natural = sum(row_heights)
        target = min(box.h, max(natural, int(min(box.h * 0.8, natural * 1.6))))
        extra = (target - natural) // len(row_heights)
        row_heights = [h + extra for h in row_heights]
        top = box.y + (box.h - sum(row_heights)) * 2 // 5
        gt = slide.shapes.add_table(len(all_cells), ncols, box.x, top, box.w, sum(row_heights))
        table = gt.table
        for c, w in enumerate(widths):
            table.columns[c].width = w
        for r, h in enumerate(row_heights):
            table.rows[r].height = h
        numeric = [all(_is_num(row[c]) for row in rows if c < len(row)) and rows for c in range(ncols)]
        # explicit Markdown alignment (|---:|, |:---:|) wins over the numeric guess
        aligns = list(spec.get("align") or []) + [""] * ncols
        explicit = {"left": PP_ALIGN.LEFT, "right": PP_ALIGN.RIGHT, "center": PP_ALIGN.CENTER}
        for r, row in enumerate(all_cells):
            for c in range(ncols):
                cell = table.cell(r, c)
                cell.margin_left = cell.margin_right = Inches(0.1)
                cell.vertical_anchor = MSO_ANCHOR.MIDDLE
                p = cell.text_frame.paragraphs[0]
                if aligns[c] in explicit:
                    p.alignment = explicit[aligns[c]]
                elif numeric[c] and c > 0:
                    p.alignment = PP_ALIGN.RIGHT
                add_runs(p, row[c] if c < len(row) else "", size=size, bold=True if r == 0 else None)
        return slide

    def s_chart(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        cd = spec["chart"]
        data = CategoryChartData()
        data.categories = cd["categories"]
        for s in cd["series"]:
            data.add_series(s["name"], s["values"])
        ctype = {"line": XL_CHART_TYPE.LINE_MARKERS, "column": XL_CHART_TYPE.COLUMN_CLUSTERED,
                 "bar": XL_CHART_TYPE.BAR_CLUSTERED, "pie": XL_CHART_TYPE.PIE}.get(cd.get("chart_type"),
                                                                                  XL_CHART_TYPE.COLUMN_CLUSTERED)
        chart = slide.shapes.add_chart(ctype, box.x, box.y, box.w, box.h, data).chart
        chart.font.size = Pt(14)
        multi = len(cd["series"]) > 1
        chart.has_legend = multi or ctype == XL_CHART_TYPE.PIE
        if chart.has_legend:
            chart.legend.position = XL_LEGEND_POSITION.BOTTOM
            chart.legend.include_in_layout = False
        if not multi and ctype != XL_CHART_TYPE.PIE:
            plot = chart.plots[0]
            plot.has_data_labels = True
            plot.data_labels.font.size = Pt(12)
            plot.data_labels.number_format = '0"%"' if cd.get("percent") else "#,##0.##"
            plot.data_labels.number_format_is_linked = False
            plot.data_labels.position = XL_LABEL_POSITION.OUTSIDE_END if ctype != XL_CHART_TYPE.LINE_MARKERS \
                else XL_LABEL_POSITION.ABOVE
            chart.value_axis.has_major_gridlines = False
            chart.value_axis.visible = False
        if ctype != XL_CHART_TYPE.PIE:
            chart.category_axis.tick_labels.font.size = Pt(12)
        return slide

    def s_code(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        lines = spec["code"].split("\n")
        size = max(9, min(18, int((box.h / 12700) / (len(lines) * 1.25 + 1)),
                          int((box.w / 12700) / (max(map(len, lines)) * 0.62 + 2))))
        h = min(box.h, int(len(lines) * size * 1.2 * 12700 + Inches(0.6)))
        shp = shape(slide, MSO_SHAPE.ROUNDED_RECTANGLE, Box(box.x, box.y, box.w, h), fill=MSO_THEME_COLOR.TEXT_1,
                    brightness=0.9)
        tf = shp.text_frame
        tf.word_wrap = False
        tf.vertical_anchor = MSO_ANCHOR.TOP
        tf.margin_left = tf.margin_top = Inches(0.25)
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.alignment = PP_ALIGN.LEFT
            run = p.add_run()
            run.text = line or " "
            run.font.name = "Courier New"
            run.font.size = Pt(size)
            run.font.color.theme_color = DARK
        return slide

    def s_quote(self, spec):
        if self.layouts.roles.get("quote") is not None:
            slide = self.new_slide("quote", "")
            name, _, role = (spec.get("attribution") or "").partition(",")
            extra = self.slot(slide, "extra")
            if self.fill(slide, self.slot(slide, "body"), spec["quote"]):
                self.fill(slide, self.slot(slide, "subtitle"), name.strip())
                if extra:
                    self.fill(slide, extra[0], role.strip())
                if spec.get("title"):
                    self.fill(slide, self.slot(slide, "title"), spec["title"])
                return slide
        slide = self.new_slide("title_only", spec["title"])
        box = self.area.inset(Inches(0.6), 0)
        size = fit_pt([plain_text(spec["quote"])], box.w, box.h * 0.7, 32, 16)
        textbox(slide, Box(box.x - Inches(0.6), box.y - Inches(0.3), Inches(1.2), Inches(1.4)), "“",
                96, color=self.pal(0), bold=True)
        h = text_height([plain_text(spec["quote"])], box.w, size)
        y = box.y + (box.h - h) // 2 - Inches(0.3)
        textbox(slide, Box(box.x, y, box.w, h), spec["quote"], size, italic=True, anchor=MSO_ANCHOR.MIDDLE)
        if spec.get("attribution"):
            textbox(slide, Box(box.x, y + h + Inches(0.15), box.w, Inches(0.5)), "— " + spec["attribution"],
                    18, color=self.pal(0), align=PP_ALIGN.RIGHT)
        return slide

    def s_image(self, spec):
        slide = self.new_slide("title_only", spec["title"])
        box = self.lead(slide, spec.get("lead", ""), self.area)
        items = spec.get("items") or []
        if items:                                   # text beside the picture
            text_w = int(box.w * 0.45)
            img_left = spec.get("position") == "left"
            tbox = Box(box.x + (box.w - text_w if img_left else 0), box.y, text_w, box.h)
            box = Box(box.x + (0 if img_left else text_w + GAP), box.y, box.w - text_w - GAP, box.h)
            self._side_text(slide, tbox, items, spec)
        caption = plain_text(spec.get("caption") or "").strip()
        if caption and caption.lower() != Path(spec["src"]).name.lower():
            cap_h = Inches(0.45)
            textbox(slide, Box(box.x, box.y + box.h - cap_h, box.w, cap_h), caption, 12,
                    color=MSO_THEME_COLOR.TEXT_1, align=PP_ALIGN.CENTER, italic=True)
            box = Box(box.x, box.y, box.w, box.h - cap_h - Inches(0.05))
        path = self._image_file(spec["src"])
        if path is not None:
            from PIL import Image
            with Image.open(path) as im:
                iw, ih = im.size
            scale = min(box.w / iw, box.h / ih)
            w, h = int(iw * scale), int(ih * scale)
            y = box.y + (box.h - h) // 2 if not caption else box.y + box.h - h
            slide.shapes.add_picture(str(path), box.x + (box.w - w) // 2, y, w, h)
        else:
            shape(slide, MSO_SHAPE.RECTANGLE, box, fill=MSO_THEME_COLOR.TEXT_1, brightness=0.9,
                  text=f"Image: {spec['src']}", size=16)
        return slide

    def _side_text(self, slide, box, items, spec):
        flat = []

        def walk(its, level):
            for it in its:
                flat.append((it["text"], level))
                walk(it.get("children", []), level + 1)
        walk(items, 0)
        size = fit_pt([plain_text(t) for t, _ in flat], box.w - Inches(0.3), box.h, 22, 12, gap=0.5)
        tb = slide.shapes.add_textbox(box.x, box.y, box.w, box.h)
        tf = tb.text_frame
        tf.word_wrap = True
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
        for i, (text, level) in enumerate(flat):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            p.level = min(level, 4)
            p.space_after = Pt(size * 0.5)
            if not spec.get("plain"):
                _bullet(p, level)
                if spec.get("ordered") and level == 0:
                    _numbered(p)
            add_runs(p, text, size=size if level == 0 else max(size - 2, 11))
        _no_autofit(tf)

    def _image_file(self, src: str) -> Path | None:
        """Local path (relative to the Markdown file) or http(s) URL -> a file python-pptx
        can embed, or None with a warning."""
        import sys
        import tempfile
        from urllib.parse import unquote, urlparse
        if not hasattr(self, "_tmp"):
            self._tmp = Path(tempfile.mkdtemp(prefix="md2pptx-img-"))
        name = Path(urlparse(src).path).name or "image"
        if urlparse(src).scheme in ("http", "https"):
            import urllib.request
            path = self._tmp / f"{len(list(self._tmp.iterdir()))}_{name}"
            try:
                req = urllib.request.Request(src, headers={"User-Agent": "md2pptx"})
                with urllib.request.urlopen(req, timeout=15) as r:
                    path.write_bytes(r.read())
            except Exception as e:  # noqa: BLE001
                print(f"warning: image not downloaded ({e}): {src}", file=sys.stderr)
                return None
        else:
            path = Path(unquote(src))
            if not path.is_absolute():
                path = (self.base_dir / path).resolve()
            if not path.exists():
                print(f"warning: image not found, placeholder used: {path}", file=sys.stderr)
                return None
        if path.suffix.lower() in (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff"):
            return path
        out = self._tmp / f"{len(list(self._tmp.iterdir()))}_{path.stem}.png"
        try:
            if path.suffix.lower() == ".svg":
                import cairosvg
                cairosvg.svg2png(url=str(path), write_to=str(out), output_width=1600)
            else:
                from PIL import Image
                with Image.open(path) as im:
                    im.save(out, "PNG")
            return out
        except Exception as e:  # noqa: BLE001
            hint = " (pip install cairosvg for SVG)" if path.suffix.lower() == ".svg" else ""
            print(f"warning: image format not supported{hint}: {path} ({e})", file=sys.stderr)
            return None


# --------------------------------------------------------------------------- #
# paragraph formatting helpers
# --------------------------------------------------------------------------- #
def _flatten(items):
    out = []
    for i in items:
        out.append(i)
        out.extend(_flatten(i.get("children", [])))
    return out


def _flatten_levels(items, level=0):
    for i in items:
        yield i["text"], level
        yield from _flatten_levels(i.get("children", []), level + 1)


def _pPr(p):
    return p._p.get_or_add_pPr()


def _clear_bullets(pPr):
    for tag in ("a:buNone", "a:buChar", "a:buAutoNum", "a:buFont"):
        for el in pPr.findall(qn(tag)):
            pPr.remove(el)


def _no_bullet(p):
    pPr = _pPr(p)
    _clear_bullets(pPr)
    pPr.set("indent", "0")
    pPr.set("marL", "0")
    pPr.append(pPr.makeelement(qn("a:buNone"), {}))


def _numbered(p):
    pPr = _pPr(p)
    _clear_bullets(pPr)
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "+mj-lt"}))
    pPr.append(pPr.makeelement(qn("a:buAutoNum"), {"type": "arabicPeriod"}))


def _bullet(p, level=0):
    pPr = _pPr(p)
    _clear_bullets(pPr)
    indent = Inches(0.25)
    pPr.set("marL", str(int(indent * (level + 1))))
    pPr.set("indent", str(int(-indent)))
    pPr.append(pPr.makeelement(qn("a:buFont"), {"typeface": "Arial"}))
    pPr.append(pPr.makeelement(qn("a:buChar"), {"char": "•" if level == 0 else "–"}))


def _no_autofit(tf):
    bodyPr = tf._txBody.bodyPr
    for tag in ("a:normAutofit", "a:spAutoFit", "a:noAutofit"):
        for el in bodyPr.findall(qn(tag)):
            bodyPr.remove(el)
    bodyPr.append(bodyPr.makeelement(qn("a:noAutofit"), {}))


def _split_bold_label(text):
    return "", text


def _is_num(s):
    from .planner import _num
    return _num(s) is not None


def _inherited_pt(layout, idx) -> float | None:
    """Font size (pt) a layout placeholder gives its first paragraph, if the layout or master says."""
    from pptx.oxml.ns import qn as _qn
    for ph in layout.placeholders:
        if ph.placeholder_format.idx != idx:
            continue
        el = ph._element
        for xp in (".//a:lstStyle/a:lvl1pPr/a:defRPr/@sz", ".//a:p/a:r/a:rPr/@sz", ".//a:endParaRPr/@sz"):
            v = el.xpath(xp)
            if v:
                return int(v[0]) / 100
        # inherit from the master's title/body style
        master = layout.slide_master._element
        style = "p:titleStyle" if ph.placeholder_format.type in TITLE_TYPES else "p:bodyStyle"
        v = master.xpath(f"./p:txStyles/{style}/a:lvl1pPr/a:defRPr/@sz")
        return int(v[0]) / 100 if v else None
    return None


def _distinct_accents(prs) -> list:
    """Theme accent slots with distinct colours, in slot order (falls back to all six)."""
    import re as _re
    try:
        master = prs.slide_masters[0]
        theme = next(r.target_part for r in master.part.rels.values() if r.reltype.endswith("/theme"))
        xml = theme.blob.decode("utf-8", "ignore")
    except Exception:
        return list(ACCENTS)
    seen, out = set(), []
    for i, slot in enumerate(ACCENTS, start=1):
        m = _re.search(rf"<a:accent{i}>.*?val=\"(\w+)\"", xml, _re.S)
        val = m.group(1).upper() if m else f"slot{i}"
        if val not in seen:
            seen.add(val)
            out.append(slot)
    return out or list(ACCENTS)


# --------------------------------------------------------------------------- #
# accessibility: alternative text
# --------------------------------------------------------------------------- #
KIND_NAMES = {
    "en": {"process": "Process diagram", "cycle": "Cycle diagram", "timeline": "Timeline", "hierarchy": "Tree diagram",
           "cards": "Cards", "stats": "Key figures", "comparison": "Comparison", "pyramid": "Pyramid",
           "funnel": "Funnel", "hub": "Hub and spoke diagram", "rings": "Percentage rings", "gantt": "Gantt chart",
           "matrix": "Maturity matrix (Harvey balls)", "map": "Map of Europe", "agenda": "Agenda",
           "stairs": "Maturity staircase", "flow": "Flow from inputs to outputs",
           "bullets": "List", "text": "Text", "table": "Table", "chart": "Chart"},
    "fr": {"process": "Diagramme de processus", "cycle": "Diagramme de cycle", "timeline": "Frise chronologique",
           "hierarchy": "Arborescence", "cards": "Cartes", "stats": "Chiffres clés", "comparison": "Comparaison",
           "pyramid": "Pyramide", "funnel": "Entonnoir", "hub": "Diagramme en étoile", "rings": "Anneaux de pourcentage",
           "gantt": "Diagramme de Gantt", "matrix": "Matrice de maturité (boules de Harvey)",
           "map": "Carte de l'Europe", "agenda": "Sommaire",
           "stairs": "Escalier de maturité", "flow": "Flux des entrées vers les résultats", "bullets": "Liste", "text": "Texte", "table": "Tableau",
           "chart": "Graphique"},
}


def alt_text(spec: dict, lang: str = "en") -> str:
    """A screen-reader description of a diagram slide, built from its content."""
    kind = spec["kind"]
    name = KIND_NAMES.get(lang, KIND_NAMES["en"]).get(kind, kind)
    sep = " : " if lang == "fr" else ": "
    parts = []
    if kind == "hub":
        root = spec.get("root") or {"label": spec["title"]}
        parts.append(plain_text(root.get("label", "")))
    if kind == "map":
        for g in spec.get("groups", []):
            names = ", ".join(plain_text(t).split(":")[0].strip() for t in g["items"])
            parts.append((plain_text(g["label"]) + sep if g["label"] else "") + names)
    elif kind == "gantt":
        parts += [f"{plain_text(i['label'])} ({i['range']})" for i in spec["items"]]
    elif kind == "matrix":
        parts.append(", ".join(plain_text(h) for h in spec["header"]))
        parts += [" ".join(plain_text(c) for c in r) for r in spec["rows"]]
    elif kind in ("stats", "rings"):
        parts += [f"{i['value']} {plain_text(i['text'])}" for i in spec["items"]]
    elif kind == "comparison":
        parts += [f"{plain_text(c['title'])}" + sep + ("; ".join(plain_text(i["text"]) for i in c["items"])
                  or (f"{len(c['code'].splitlines())} lines of code" if c.get("code") is not None else ""))
                  for c in spec["columns"]]
    elif kind == "hierarchy":
        def walk(node):
            kids = node.get("children", [])
            return plain_text(node["text"]) + (" (" + "; ".join(walk(k) for k in kids) + ")" if kids else "")
        parts += [walk(i) for i in spec["items"]]
    elif kind == "agenda":
        parts += [plain_text(t) for t in spec["items"]]
    else:
        for i in spec.get("items", []):
            label = plain_text(i.get("label") or i.get("text", ""))
            body = plain_text(" ".join(_item_texts(i)[1])) if i.get("label") else ""
            parts.append(label + (sep + body if body and body != label else ""))
    for i in spec.get("panels", []):
        parts.append(plain_text(i["label"]) + sep + plain_text(" ".join(_item_texts(i)[1])))
    text = f"{name}{sep}" + "; ".join(p for p in parts if p)
    return text[:1500]


def _descr(el, text):
    c = el.find(".//" + qn("p:cNvPr"))
    if c is not None:
        c.set("descr", text)


def describe(slide, spec, lang):
    """Group a diagram's shapes and give the group alt text; describe tables, charts and pictures."""
    kind = spec["kind"]
    tree = slide.shapes._spTree
    for gf in tree.iterchildren(qn("p:graphicFrame")):
        if gf.find(".//" + qn("p:nvPr") + "/" + qn("p:ph")) is not None:
            continue
        uri = gf.xpath("./a:graphic/a:graphicData/@uri")
        if uri and uri[0].endswith("/table") and kind in ("table",):
            _descr(gf, f"{KIND_NAMES.get(lang, KIND_NAMES['en'])['table']}: "
                       + ", ".join(plain_text(h) for h in spec.get("header", []))
                       + f" ({len(spec.get('rows', []))} rows)")
        elif uri and uri[0].endswith("/chart"):
            cd = spec.get("chart", {})
            _descr(gf, f"{KIND_NAMES.get(lang, KIND_NAMES['en'])['chart']}: "
                       + ", ".join(s["name"] for s in cd.get("series", [])) + " / "
                       + ", ".join(cd.get("categories", [])))
    for pic in tree.iterchildren(qn("p:pic")):
        if pic.find(".//" + qn("p:nvPr") + "/" + qn("p:ph")) is None and spec.get("kind") == "image":
            _descr(pic, plain_text(spec.get("alt") or spec.get("caption") or spec.get("title", "")))
    if kind not in KIND_NAMES["en"] or kind in ("text", "table", "chart") or \
            (kind == "bullets" and spec.get("style") != "rows"):
        return
    # brand diagrams and maps arrive already grouped and described
    loose = [sh for sh in slide.shapes if not sh.is_placeholder and sh.shape_type is not None
             and sh._element.tag in (qn("p:sp"), qn("p:cxnSp"), qn("p:grpSp"))
             and not (sh._element.tag == qn("p:grpSp") and sh._element.find(qn("p:nvGrpSpPr") + "/" + qn("p:cNvPr")).get("descr"))]
    if len(loose) < 2:
        return
    grp = slide.shapes.add_group_shape(loose)
    grp.name = KIND_NAMES["en"].get(kind, kind)
    _descr(grp._element, alt_text(spec, lang))


def render_plan(plan: dict, out, template=None, layout_overrides=None, base_dir=None, footer=None,
                icons: bool = True, schemas: bool = True):
    return Renderer(template, layout_overrides, base_dir, footer, icons=icons, schemas=schemas).render(plan, out)
