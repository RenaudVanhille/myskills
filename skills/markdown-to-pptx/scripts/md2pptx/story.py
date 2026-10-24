"""Deck-level storytelling: parts for long documents, speaker notes, visual variety and
text checks. Runs on the plan after every section has been turned into slides."""
from __future__ import annotations

import re

from .parser import plain_text

# --------------------------------------------------------------------------- #
# parts: group a long run of flat sections into 3–6 chapters
# --------------------------------------------------------------------------- #
MIN_SECTIONS_FOR_PARTS = 12

# theme -> (keywords, English label, French label). Keywords are matched on word starts.
THEMES = {
    "context": (r"contexte|constat|enjeux?|problèmes?|limites?|défis?|situation|pourquoi|état des lieux|"
                r"context|background|challenges?|problems?|pain|current state|why|issues?",
                "Context & challenges", "Contexte & enjeux"),
    "solution": (r"solution|portail|plateforme|passerelle|apports?|fonctionnement|principe|routage|"
                 r"platform|portal|gateway|how it works|routing|proposal",
                 "The solution", "La solution"),
    "models": (r"modèles?|llm|panorama|frontières?|open-?weight|propriétaires?|swe-bench|"
               r"models?|frontier|proprietary|benchmarks?",
               "Models landscape", "Panorama des modèles"),
    "architecture": (r"architecture|déploiement|composants?|conteneurs?|réseau|kubernetes|azure|aws|gcp|"
                     r"deployment|components?|containers?|network|services?",
                     "Architecture & deployment", "Architecture & déploiement"),
    "costs": (r"coûts?|budgets?|rentabilité|prix|tarifs?|capex|opex|roi|économies|financ\w*|€|"
              r"costs?|pricing|prices?|savings|spend\w*|euros?|dollars?",
              "Costs & return", "Coûts & rentabilité"),
    "governance": (r"gouvernance|sécurité|conformité|observabilité|quotas?|clés|pilotage|contrôle|"
                   r"governance|security|compliance|observability|monitoring|audit|controls?",
                   "Governance & security", "Gouvernance & sécurité"),
    "performance": (r"performance|compression|optimisation|gains?|latence|débit|"
                    r"optimi[sz]ation|latency|throughput|speed",
                    "Performance", "Performance & optimisation"),
    "hosting": (r"dimensionnement|hébergement|vram|gpu|h100|h200|cluster|capacité|concurrence|souverain\w*|"
                r"sizing|hosting|capacity|hardware|matériel|on-?prem\w*|sovereign\w*",
                "Infrastructure & sizing", "Hébergement & dimensionnement"),
    "roadmap": (r"feuille de route|plan d'action|prochaines étapes|recommandations?|calendrier|jalons?|"
                r"roadmap|next steps?|action plan|recommendations?|milestones?|timeline",
                "Roadmap", "Feuille de route"),
    "team": (r"équipes?|organisation|rôles?|gouvernance d'équipe|ressources humaines|"
             r"teams?|organi[sz]ation|roles?|people|staffing",
             "Organisation", "Organisation"),
    "results": (r"résultats?|indicateurs?|kpis?|bilan|mesures?|"
                r"results?|metrics?|findings?|outcomes?",
                "Results", "Résultats"),
}
_THEME_RE = {k: re.compile(r"(?<![\w-])(" + v[0] + r")(?![\w-])", re.I) for k, v in THEMES.items()}
_KEYS = list(THEMES)


def _section_text(sec: dict) -> str:
    out = []

    def blocks(bs):
        for b in bs:
            if b["type"] in ("paragraph", "quote"):
                out.append(b["text"])
            elif b["type"] == "list":
                stack = list(b["items"])
                while stack:
                    it = stack.pop()
                    out.append(it["text"])
                    stack.extend(it["children"])
            elif b["type"] == "table":
                out.extend(b["header"])
                out.extend(" ".join(r) for r in b["rows"])
    blocks(sec["blocks"])
    for c in sec["children"]:
        out.append(c["title"])
        blocks(c["blocks"])
    return plain_text(" \n ".join(out))


def _theme_vector(sec: dict) -> list[float]:
    title, body = sec["title"], _section_text(sec)
    v = []
    for k in _KEYS:
        rx = _THEME_RE[k]
        v.append(4 * len(rx.findall(title)) + min(len(rx.findall(body)), 6))
    total = sum(v)
    return [x / total for x in v] if total else [0.0] * len(v)


_STOP = set("""avec dans pour sur des les une par vers entre sans sous plus moins votre notre leurs
with from into over under this that their about between versus""".split())


def _title_words(t: str) -> set[str]:
    words = re.findall(r"[\w.-]+", plain_text(t).lower())
    return {w.strip(".-") for w in words if len(w.strip(".-")) >= 4 and w not in _STOP}


def _cut_penalty(sections: list[dict]) -> list[float]:
    """Cost of starting a new part at section i: high when its title shares a word with the
    previous one ("Focus sur …" / "Focus sur …", "… GLM-5.2" / "… GLM-5.2")."""
    pen = [0.0]
    for a, b in zip(sections, sections[1:]):
        wa, wb = _title_words(a["title"]), _title_words(b["title"])
        first_a = plain_text(a["title"]).lower().split()[:1]
        first_b = plain_text(b["title"]).lower().split()[:1]
        shared = len(wa & wb) + (first_a == first_b and len(first_a[0]) >= 4)
        pen.append(1.2 if shared else 0.0)
    return pen


def _segment(vectors: list[list[float]], k: int, cut: list[float] | None = None) -> tuple[float, list[int]]:
    """Best split of the section sequence into k contiguous groups (dynamic programming).
    The cost of a group is how far its sections are from the group's dominant theme.
    Returns (cost, start indexes)."""
    n = len(vectors)
    cap = max(4, -(-n // 4))

    def cost(i, j):          # sections i..j-1
        sums = [sum(vectors[s][t] for s in range(i, j)) for t in range(len(_KEYS))]
        dom = max(range(len(sums)), key=sums.__getitem__)
        c = sum(1 - vectors[s][dom] if any(vectors[s]) else 0.6 for s in range(i, j))
        size = j - i
        if size == 1:
            # a lone section only makes a part when it is clearly the wrap-up
            c += -0.3 if dom == _KEYS.index("roadmap") and j == n else 2.5
        elif size > cap:
            c += 0.7 * (size - cap)
        return c

    INF = float("inf")
    best = [[INF] * (n + 1) for _ in range(k + 1)]
    back = [[0] * (n + 1) for _ in range(k + 1)]
    best[0][0] = 0
    for g in range(1, k + 1):
        for j in range(1, n + 1):
            for i in range(g - 1, j):
                if best[g - 1][i] == INF:
                    continue
                c = best[g - 1][i] + cost(i, j) + (cut[i] if cut else 0)
                if c < best[g][j]:
                    best[g][j], back[g][j] = c, i
    starts, j = [], n
    for g in range(k, 0, -1):
        i = back[g][j]
        starts.append(i)
        j = i
    return best[k][n], sorted(starts)


def _short(title: str, limit: int = 48) -> str:
    t = re.split(r"\s*[:(–—]\s*", title)[0].strip()
    return t if len(t) <= limit else t[:limit].rsplit(" ", 1)[0] + "…"


def plan_parts(sections: list[dict], lang: str) -> list[dict] | None:
    """[{"title", "start", "end"}] (end exclusive), or None when the deck needs no parts.

    `<!-- part: Title -->` markers always win. Without markers, a long run of flat sections
    (12 or more `##` headings, most without `###`) is grouped automatically by theme."""
    n = len(sections)
    marks = [s.get("part") for s in sections]
    if any(marks):
        if not marks[0]:
            marks[0] = sections[0]["title"]
        starts = [i for i, m in enumerate(marks) if m]
        return [{"title": marks[s], "start": s, "end": (starts[k + 1] if k + 1 < len(starts) else n),
                 "auto": False} for k, s in enumerate(starts)]
    if n < MIN_SECTIONS_FOR_PARTS or sum(len(s["children"]) >= 2 for s in sections) >= 2:
        return None
    vectors = [_theme_vector(s) for s in sections]
    cut = _cut_penalty(sections)
    options = []
    for k in range(3, min(7, n // 3) + 1):
        c, starts = _segment(vectors, k, cut)
        options.append((c + 0.5 * k, k, starts))
    _, k, starts = min(options)
    parts, used = [], set()
    for g, s in enumerate(starts):
        e = starts[g + 1] if g + 1 < len(starts) else n
        sums = [sum(vectors[i][t] for i in range(s, e)) for t in range(len(_KEYS))]
        ranked = sorted(range(len(_KEYS)), key=lambda t: -sums[t])
        title = None
        for t in ranked[:2]:
            share = sums[t] / (e - s)
            if share >= 0.3 and _KEYS[t] not in used:
                title = THEMES[_KEYS[t]][2 if lang == "fr" else 1]
                used.add(_KEYS[t])
                break
        parts.append({"title": title or _short(sections[s]["title"]), "start": s, "end": e, "auto": True})
    return parts


# --------------------------------------------------------------------------- #
# speaker notes
# --------------------------------------------------------------------------- #
NOTE_WORDS = {
    "en": {"key": "Key message", "points": "Talking points", "next": "Next", "covers": "This part covers",
           "agenda": "Walk through the outline", "open": "Goal of this talk", "close":
           "Thank the audience, recap the decision you need, then open the floor.",
           "table": "Walk the table row by row; columns", "chart": "Highlight", "highest": "highest value",
           "compare": "Compare", "quote": "Let the quote land, then say why it matters.",
           "code": "Explain what the snippet does before reading it line by line.",
           "image": "Describe what the picture shows", "rows": "rows"},
    "fr": {"key": "Message clé", "points": "Points à développer", "next": "Transition", "covers":
           "Cette partie couvre", "agenda": "Annoncer le déroulé", "open": "Objectif de la présentation",
           "close": "Remercier, rappeler la décision attendue, puis ouvrir les échanges.",
           "table": "Lire le tableau ligne par ligne ; colonnes", "chart": "Mettre en avant",
           "highest": "valeur la plus haute", "compare": "Comparer",
           "quote": "Laisser la citation se lire, puis expliquer pourquoi elle compte.",
           "code": "Expliquer ce que fait l'extrait avant de le détailler ligne par ligne.",
           "image": "Décrire ce que montre l'image", "rows": "lignes"},
}


def _p(t) -> str:
    return plain_text(t or "").strip()


def _sentence(t: str) -> str:
    t = _p(t)
    return t if not t or t[-1] in ".!?:;…" else t + "."


def _item_line(it: dict) -> str:
    if "value" in it:                                   # key figure: "38% of users …"
        return " ".join(x for x in (_p(it["value"]), _p(it.get("text", ""))) if x)
    label, text = _p(it.get("label", "")), _p(it.get("text", ""))
    details = "; ".join(_p(d) for d in it.get("details", []) if d)
    body = " ".join(x for x in (text, details) if x)
    return f"{label}: {body}" if label and body else (label or body)


def _tree_lines(items, depth=0, out=None):
    out = [] if out is None else out
    for it in items:
        out.append("  " * depth + "- " + _p(it["text"]))
        _tree_lines(it.get("children", []), depth + 1, out)
    return out


def speaker_notes(s: dict, nxt: dict | None, W: dict, purpose: str) -> str:
    kind = s["kind"]
    lines: list[str] = []
    lead = _p(s.get("lead") or "")
    if kind == "title":
        lines.append(f"{W['open']}: {_sentence(s.get('subtitle') or purpose)}")
    elif kind == "agenda":
        lines.append(f"{W['agenda']}: " + "; ".join(_p(i) for i in s["items"]) + ".")
    elif kind == "section":
        if s.get("covers"):
            lines.append(f"{W['covers']}: " + "; ".join(_p(c) for c in s["covers"]) + ".")
        elif s.get("subtitle"):
            lines.append(_sentence(s["subtitle"]))
    elif kind == "closing":
        lines.append(W["close"])
    else:
        if lead:
            lines.append(f"{W['key']}: {_sentence(lead)}")
        if kind in ("cards", "process", "cycle", "timeline", "pyramid", "stats"):
            pts = [_item_line(i) for i in s.get("items", [])]
            if pts:
                if not lead:
                    lines.append(f"{W['key']}: {_sentence(pts[0])}")
                lines.append(f"{W['points']}:")
                lines += [f"- {p}" for p in pts]
        elif kind in ("bullets", "hierarchy"):
            tree = _tree_lines(s.get("items", []))
            if tree:
                if not lead and tree[0].lstrip(" -") != _p(s.get("title")):
                    lines.append(f"{W['key']}: {_sentence(tree[0].lstrip(' -'))}")
                lines.append(f"{W['points']}:")
                lines += tree
        elif kind == "comparison":
            cols = [c["title"] for c in s.get("columns", [])]
            lines.append(f"{W['compare']}: " + " / ".join(_p(c) for c in cols) + ".")
        elif kind == "table":
            lines.append(f"{W['table']}: " + ", ".join(_p(h) for h in s.get("header", [])) +
                         f" ({len(s.get('rows', []))} {W['rows']}).")
        elif kind == "chart":
            ch = s.get("chart", {})
            if ch.get("series") and ch["series"][0]["values"]:
                vals = ch["series"][0]["values"]
                top = max(range(len(vals)), key=vals.__getitem__)
                lines.append(f"{W['chart']}: {ch['categories'][top]} ({W['highest']}, "
                             f"{vals[top]:g} {ch['series'][0]['name']}).")
        elif kind == "quote":
            lines.append(W["quote"])
        elif kind == "code":
            lines.append(W["code"])
        elif kind == "image":
            lines.append(f"{W['image']}: {_sentence(s.get('caption') or s.get('alt') or '')}")
        elif kind == "text":
            lines.append(f"{W['key']}: {_sentence(s['paragraphs'][0])}")
    if nxt is not None and kind not in ("closing",) and nxt["kind"] not in ("closing",) \
            and nxt.get("title") and not nxt["title"].startswith(s.get("title", "\0")):
        lines.append(f"{W['next']}: {_p(nxt['title'])}")
    return "\n".join(l for l in lines if l.strip())


def add_notes(slides: list[dict], lang: str, purpose_label: str) -> None:
    W = NOTE_WORDS.get(lang, NOTE_WORDS["en"])
    for k, s in enumerate(slides):
        gen = speaker_notes(s, slides[k + 1] if k + 1 < len(slides) else None, W, purpose_label)
        if lang == "fr":                                # French typography: "Message clé : …"
            gen = re.sub(r"(?<=[^\s:]):(?=\s)", " :", gen)
        own = s.get("notes", "")
        s["notes"] = "\n\n".join(x for x in (own, gen) if x)


# --------------------------------------------------------------------------- #
# variety and text checks
# --------------------------------------------------------------------------- #
def add_variety(slides: list[dict], auto: bool = True) -> None:
    """Consecutive slides of the same diagram kind alternate their look so a run of
    card slides doesn't read as one slide repeated. With auto off, cards stay a grid
    unless a hint chose otherwise."""
    prev = None
    for s in slides:
        if s["kind"] == "cards" and "variant" not in s:
            if auto and prev is not None and prev["kind"] == "cards" and prev.get("variant", "grid") == "grid" \
                    and len(s["items"]) <= 5:
                s["variant"] = "rows"
            else:
                s["variant"] = "grid"
        prev = s


TITLE_MAX = 60


def check_titles(slides: list[dict]) -> list[str]:
    """Tidy titles (trailing punctuation, first letter) and report the ones that are too long."""
    warnings = []
    for n, s in enumerate(slides, start=1):
        t = s.get("title") or ""
        fixed = re.sub(r"\s*[.:;,]\s*$", "", t.strip())
        fixed = capitalize_first(fixed)
        if fixed != t:
            s["title"] = fixed
        if s["kind"] not in ("title", "closing") and len(plain_text(fixed)) > TITLE_MAX:
            warnings.append(f"slide {n}: title has {len(plain_text(fixed))} characters "
                            f"(over {TITLE_MAX}, it is shrunk to fit): {plain_text(fixed)!r}")
    return warnings


_SKIP_CAP = re.compile(r"^(\W*)(`|https?://|www\.|[a-z]+[A-Z0-9_./])")


def capitalize_first(text: str) -> str:
    """Upper-case the first letter of a sentence fragment, keeping words such as iPhone,
    npm-style identifiers, code spans and URLs untouched."""
    if not text or _SKIP_CAP.match(text):
        return text
    m = re.match(r"^([\s*_\"'«(\[]*)([a-zà-ÿ])", text)
    if not m:
        return text
    return text[:m.end(1)] + m.group(2).upper() + text[m.end(2):]
