"""Markdown -> document model.

The model is plain dicts/lists so it can be dumped to JSON, reviewed or edited
by a human or an AI assistant, and fed back in.

Block types
-----------
paragraph  {"type": "paragraph", "text": <inline md>}
list       {"type": "list", "ordered": bool, "items": [Item]}
           Item = {"text": <inline md>, "children": [Item]}
table      {"type": "table", "header": [<inline md>], "rows": [[<inline md>]]}
code       {"type": "code", "lang": str, "text": str}
quote      {"type": "quote", "text": <inline md>, "attribution": str}
image      {"type": "image", "src": str, "alt": str, "caption": str}
hint       {"type": "hint", "kind": str, "options": {k: v}}   <!-- slide: process -->
notes      {"type": "notes", "text": str}                     <!-- notes: ... -->
part       {"type": "part", "title": str}                     <!-- part: Costs -->
break      {"type": "break"}                                  ---  (horizontal rule)
"""
from __future__ import annotations

import re
from pathlib import Path

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode

_md = MarkdownIt("commonmark", {"html": True}).enable(["table", "strikethrough"])

HINT_RE = re.compile(r"<!--\s*(slide|pptx|notes|part)\s*:\s*(.*?)\s*-->", re.S | re.I)
FRONT_MATTER_RE = re.compile(r"\A---\s*\n(.*?)\n---\s*\n", re.S)
OPEN_FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*(markdown|md|gfm)?\s*$", re.I)


def md_parser() -> MarkdownIt:
    return _md


# --------------------------------------------------------------------------- #
# whole-document code fence (AI tools often wrap their answer in ```markdown)
# --------------------------------------------------------------------------- #
def unwrap_document_fence(text: str) -> str:
    """Strip a ```markdown ... ``` fence wrapping the whole document, if there is one."""
    text = text.lstrip("\ufeff").replace("\r\n", "\n")
    lines = text.split("\n")
    first = next((i for i, l in enumerate(lines) if l.strip()), None)
    last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    if first is None or last is None or last <= first:
        return text
    m = OPEN_FENCE_RE.match(lines[first].strip())
    if not m:
        return text
    fence = m.group(1)
    closing = lines[last].strip()
    if not (closing and set(closing) == {fence[0]} and len(closing) >= len(fence)):
        return text
    inner = lines[first + 1:last]
    # A bare ``` fence only counts when the inside clearly is a Markdown document.
    if not m.group(2) and not any(l.startswith("#") or l.strip() == "---" for l in inner[:5] + inner):
        return text
    return "\n".join(inner) + "\n"


# --------------------------------------------------------------------------- #
# front matter (tiny "key: value" subset of YAML, no dependency needed)
# --------------------------------------------------------------------------- #
def split_front_matter(text: str) -> tuple[dict, str]:
    m = FRONT_MATTER_RE.match(text)
    if not m:
        return {}, text
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.lstrip().startswith("#"):
            key, _, value = line.partition(":")
            meta[key.strip().lower()] = value.strip().strip("'\"")
    return meta, text[m.end():]


# --------------------------------------------------------------------------- #
# block conversion
# --------------------------------------------------------------------------- #
def _inline_src(node: SyntaxTreeNode) -> str:
    """Raw inline markdown of a paragraph / cell / heading node."""
    for child in node.children:
        if child.type == "inline":
            return child.content.strip()
    return (node.content or "").strip()


def _list_items(node: SyntaxTreeNode) -> list[dict]:
    items = []
    for li in node.children:
        text_parts, children = [], []
        for c in li.children:
            if c.type == "paragraph":
                text_parts.append(_inline_src(c))
            elif c.type in ("bullet_list", "ordered_list"):
                children.extend(_list_items(c))
        items.append({"text": " ".join(text_parts), "children": children})
    return items


def _table(node: SyntaxTreeNode) -> dict:
    header, rows, align = [], [], []
    for section in node.children:
        for tr in section.children:
            cells = [_inline_src(td) for td in tr.children]
            if section.type == "thead":
                header = cells
                # |---:| / |:---:| column alignment, as markdown-it reports it
                for td in tr.children:
                    m = re.search(r"text-align:\s*(left|right|center)", str(td.attrs.get("style", "")))
                    align.append(m.group(1) if m else "")
            else:
                rows.append(cells)
    return {"type": "table", "header": header, "rows": rows, "align": align}


def _image_block(img) -> dict:
    return {"type": "image", "src": img.attrs.get("src", ""), "alt": img.content or "",
            "caption": img.attrs.get("title") or img.content or ""}


def _images(node: SyntaxTreeNode) -> tuple[list[dict], bool]:
    """Images in a paragraph -> (image blocks, paragraph has other content)."""
    inline = node.children[0] if node.children else None
    if inline is None or inline.type != "inline":
        return [], True
    imgs, other = [], False
    for k in inline.children:
        if k.type == "image":
            imgs.append(_image_block(k))
        elif k.type in ("softbreak", "hardbreak") or (k.type == "text" and not k.content.strip()):
            continue
        else:
            other = True
    return imgs, other


_IMG_MD = re.compile(r"!\[[^\]]*\]\([^)]*\)")


def _parse_hint(raw: str) -> list[dict]:
    out = []
    for m in HINT_RE.finditer(raw):
        tag, body = m.group(1).lower(), m.group(2)
        if tag == "notes":
            out.append({"type": "notes", "text": body})
            continue
        if tag == "part":
            out.append({"type": "part", "title": body.strip()})
            continue
        parts = [p.strip() for p in re.split(r"[;,]", body) if p.strip()]
        kind, options = "", {}
        for p in parts:
            if "=" in p:
                k, _, v = p.partition("=")
                options[k.strip().lower()] = v.strip()
            elif not kind:
                kind, *rest = p.lower().split()
                if rest:                                 # "cards rows" == "cards, variant=rows"
                    options.setdefault("variant", rest[0])
        out.append({"type": "hint", "kind": kind, "options": options})
    return out


def _blocks(nodes) -> list[dict]:
    blocks = []
    for node in nodes:
        t = node.type
        if t == "heading":
            blocks.append({"type": "heading", "level": int(node.tag[1]), "text": _inline_src(node)})
        elif t == "paragraph":
            imgs, other = _images(node)
            if imgs and not other:
                blocks.extend(imgs)
            else:
                src = re.sub(r" {2,}", " ", _IMG_MD.sub("", _inline_src(node))).strip() if imgs else _inline_src(node)
                hints = _parse_hint(src)
                if hints and not HINT_RE.sub("", src).strip():
                    blocks.extend(hints)
                elif src:
                    blocks.append({"type": "paragraph", "text": src})
                blocks.extend(imgs)
        elif t in ("bullet_list", "ordered_list"):
            blocks.append({"type": "list", "ordered": t == "ordered_list", "items": _list_items(node)})
        elif t == "table":
            blocks.append(_table(node))
        elif t in ("fence", "code_block"):
            blocks.append({"type": "code", "lang": (node.info or "").strip(), "text": node.content.rstrip("\n")})
        elif t == "blockquote":
            paras = [_inline_src(c) for c in node.children if c.type == "paragraph"]
            attribution = ""
            if len(paras) > 1 and re.match(r"^(—|--|-|~)\s*", paras[-1]):
                attribution = re.sub(r"^(—|--|-|~)\s*", "", paras.pop())
            blocks.append({"type": "quote", "text": " ".join(paras), "attribution": attribution})
        elif t == "html_block":
            blocks.extend(_parse_hint(node.content))
        elif t == "hr":
            blocks.append({"type": "break"})
    return blocks


# --------------------------------------------------------------------------- #
# document structure
# --------------------------------------------------------------------------- #
def _new_section(title: str, level: int) -> dict:
    return {"title": title, "level": level, "blocks": [], "children": []}


def parse_markdown(text: str, source_name: str = "") -> dict:
    """Parse markdown text into {"meta", "title", "subtitle", "intro", "sections"}."""
    meta, body = split_front_matter(unwrap_document_fence(text))
    tree = SyntaxTreeNode(_md.parse(body))
    blocks = _blocks(tree.children)

    levels = [b["level"] for b in blocks if b["type"] == "heading"]
    title = meta.get("title", "")
    top = min(levels) if levels else 1

    # A single top-level heading that opens the document is the deck title.
    if levels and levels.count(top) == 1 and blocks[0]["type"] == "heading" \
            and blocks[0]["level"] == top:
        title = title or blocks[0]["text"]
        blocks = blocks[1:]
        remaining = [lv for lv in levels if lv > top]
        section_level = min(remaining) if remaining else top + 1
    else:
        section_level = top

    # No H1: a first section that is only a short intro paragraph acts as the title slide.
    heads = [i for i, b in enumerate(blocks) if b["type"] == "heading"]
    if not title and heads and heads[0] == 0 and blocks[0]["level"] == section_level:
        nxt = heads[1] if len(heads) > 1 else len(blocks)
        body = blocks[1:nxt]
        if len(body) <= 1 and all(b["type"] == "paragraph" and len(plain_text(b["text"])) <= 200 for b in body):
            title = blocks[0]["text"]
            if body and not meta.get("subtitle"):
                meta["subtitle"] = plain_text(body[0]["text"])
            blocks = blocks[nxt:]

    if not title:
        title = Path(source_name).stem.replace("_", " ").replace("-", " ").title() if source_name else "Presentation"

    doc = {"meta": meta, "title": _strip_md(title), "subtitle": meta.get("subtitle", ""),
           "intro": [], "sections": []}
    current = None       # section (level == section_level)
    current_sub = None   # subsection (level == section_level + 1)
    for b in blocks:
        if b["type"] == "heading" and b["level"] <= section_level + 1:
            if b["level"] <= section_level:
                current = _new_section(_strip_md(b["text"]), section_level)
                doc["sections"].append(current)
                current_sub = None
            else:
                if current is None:
                    current = _new_section(doc["title"], section_level)
                    doc["sections"].append(current)
                current_sub = _new_section(_strip_md(b["text"]), section_level + 1)
                current["children"].append(current_sub)
            continue
        if b["type"] == "heading":  # deeper heading -> bold paragraph
            b = {"type": "paragraph", "text": f"**{b['text']}**"}
        target = current_sub or current
        (target["blocks"] if target else doc["intro"]).append(b)
    return doc


def parse_file(path: str | Path) -> dict:
    path = Path(path)
    doc = parse_markdown(path.read_text(encoding="utf-8"), path.name)
    doc["source"] = str(path)
    return doc


# --------------------------------------------------------------------------- #
# inline helpers
# --------------------------------------------------------------------------- #
def _strip_md(text: str) -> str:
    return plain_text(text)


def inline_runs(text: str) -> list[tuple[str, dict]]:
    """Inline markdown -> [(text, {"bold","italic","code","strike","href"})]."""
    tokens = _md.parseInline(text or "")
    runs: list[tuple[str, dict]] = []
    state = {"bold": 0, "italic": 0, "strike": 0, "href": None}
    for tok in (tokens[0].children if tokens else []) or []:
        tt = tok.type
        if tt == "text":
            runs.append((tok.content, _fmt(state)))
        elif tt == "code_inline":
            runs.append((tok.content, {**_fmt(state), "code": True}))
        elif tt in ("softbreak", "hardbreak"):
            runs.append((" " if tt == "softbreak" else "\n", _fmt(state)))
        elif tt == "strong_open":
            state["bold"] += 1
        elif tt == "strong_close":
            state["bold"] -= 1
        elif tt == "em_open":
            state["italic"] += 1
        elif tt == "em_close":
            state["italic"] -= 1
        elif tt == "s_open":
            state["strike"] += 1
        elif tt == "s_close":
            state["strike"] -= 1
        elif tt == "link_open":
            state["href"] = tok.attrs.get("href")
        elif tt == "link_close":
            state["href"] = None
        elif tt == "image":
            runs.append((tok.content or "", _fmt(state)))
        elif tt == "html_inline":
            continue
    # merge adjacent runs with identical formatting
    merged: list[tuple[str, dict]] = []
    for text_, fmt in runs:
        if merged and merged[-1][1] == fmt:
            merged[-1] = (merged[-1][0] + text_, fmt)
        else:
            merged.append((text_, fmt))
    return merged


def _fmt(state: dict) -> dict:
    return {"bold": state["bold"] > 0, "italic": state["italic"] > 0,
            "strike": state["strike"] > 0, "href": state["href"], "code": False}


def plain_text(text: str) -> str:
    return "".join(t for t, _ in inline_runs(text)).strip()
