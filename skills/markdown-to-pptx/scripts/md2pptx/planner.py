"""Document model -> slide plan.

This is where the "autonomous" decisions happen: the planner infers what the
document is for, then decides for every chunk of content whether it becomes a
bullet slide, a table, a chart or a SmartArt-style diagram (process, cycle,
timeline, hierarchy, cards, stats, comparison).

Every decision can be overridden from the markdown with a hint comment placed
under a heading:  <!-- slide: cycle -->   (see README for the list of kinds).
"""
from __future__ import annotations

import re
from collections import Counter

from .parser import plain_text
from .kinds import country_list, gantt, is_matrix, percent
from .story import add_notes, add_variety, capitalize_first, check_titles, plan_parts

DIAGRAM_KINDS = {"process", "cycle", "timeline", "hierarchy", "cards", "stats", "comparison",
                 "pyramid", "funnel", "hub", "rings", "gantt", "matrix", "map", "stairs", "flow"}
ALL_KINDS = DIAGRAM_KINDS | {"bullets", "table", "chart", "code", "quote", "image", "text",
                             "section", "title", "agenda", "closing"}

MAX_BULLET_LINES = 8
_LANG = "en"
SLIDE_OPTIONS = ("icons", "schema", "icon")
VARIANTS = ("grid", "rows")          # looks of a cards slide; <!-- slide: cards rows -->
_VARIANTS = True                     # automatic variant choice (off: grid unless hinted)
_CONT = "(cont.)"
MAX_TABLE_ROWS = 8

# --------------------------------------------------------------------------- #
# purpose inference
# --------------------------------------------------------------------------- #
PURPOSES = {
    "proposal": (["proposition", "recommandation", "investissement", "budget", "coût", "valider", "arbitrage", "proposal", "propose", "recommend", "budget", "investment", "roi", "business case",
                  "funding", "approve", "approval", "cost", "benefit", "option"], "Proposal"),
    "status_report": (["avancement", "jalon", "réalisé", "en cours", "retard", "risque", "indicateur", "comité", "trimestre", "point d'étape", "lancés", "engagé", "status", "progress", "update", "milestone", "completed", "blocker", "risk",
                       "kpi", "sprint", "on track", "delayed", "quarter"], "Status update"),
    "training": (["formation", "tutoriel", "apprendre", "exercice", "bonnes pratiques", "how to", "tutorial", "learn", "guide", "exercise", "lesson", "step", "tip",
                  "example", "practice", "course"], "Guide"),
    "strategy": (["stratégie", "ambition", "objectif", "feuille de route", "transformation", "priorité", "marché", "strategy", "vision", "mission", "goal", "objective", "roadmap", "initiative",
                  "priority", "market", "growth"], "Strategy"),
    "technical": (["architecture", "composant", "déploiement", "infrastructure", "conception technique", "architecture", "api", "component", "service", "database", "deployment",
                   "implementation", "design", "system", "latency", "infrastructure"], "Technical overview"),
    "postmortem": (["incident", "cause racine", "panne", "remédiation", "incident", "root cause", "postmortem", "post-mortem", "outage", "impact",
                    "mitigation", "remediation", "detection"], "Incident review"),
    "research": (["étude", "enquête", "résultats", "analyse", "hypothèse", "research", "study", "finding", "hypothesis", "method", "survey", "results",
                  "analysis", "participants", "insight"], "Findings"),
}

CLOSING = {
    "proposal": "Decision & next steps",
    "status_report": "Questions & discussion",
    "training": "Recap",
    "strategy": "Discussion",
    "technical": "Questions",
    "postmortem": "Questions",
    "research": "Discussion",
    "general": "Thank you",
}


# --------------------------------------------------------------------------- #
# language (generated labels follow the document's language)
# --------------------------------------------------------------------------- #
STRINGS = {
    "en": {"agenda": "Agenda", "overview": "Overview", "cont": _CONT, "questions": "Questions & discussion", "qa": "Q&A",
           "closing": CLOSING, "labels": {k: v[1] for k, v in PURPOSES.items()} | {"general": "Overview"}},
    "fr": {"agenda": "Sommaire", "overview": "Introduction", "cont": "(suite)", "questions": "Questions & échanges", "qa": "Q&R",
           "closing": {"proposal": "Décision & prochaines étapes", "status_report": "Questions & échanges",
                       "training": "Récapitulatif", "strategy": "Échanges", "technical": "Questions",
                       "postmortem": "Questions", "research": "Échanges", "general": "Merci"},
           "labels": {"proposal": "Proposition", "status_report": "Point d'avancement", "training": "Guide",
                      "strategy": "Stratégie", "technical": "Présentation technique",
                      "postmortem": "Retour sur incident", "research": "Résultats", "general": "Présentation"}},
}
_FR = r"\b(le|la|les|des|du|une|est|sont|pour|avec|dans|sur|nous|vous|qui|que|et|au|aux|ces|cette|pas|plus)\b"
_EN = r"\b(the|a|an|is|are|for|with|in|on|we|you|who|that|and|to|of|this|these|not|more)\b"


def detect_language(doc: dict) -> str:
    lang = (doc["meta"].get("lang") or doc["meta"].get("language") or "").lower()[:2]
    if lang in STRINGS:
        return lang
    text = _all_text(doc)
    fr, en = len(re.findall(_FR, text)), len(re.findall(_EN, text))
    return "fr" if fr > en * 1.2 else "en"


def _all_text(doc: dict) -> str:
    parts = [doc["title"], doc.get("subtitle", "")]

    def walk_blocks(blocks):
        for b in blocks:
            if b["type"] == "paragraph":
                parts.append(b["text"])
            elif b["type"] == "list":
                stack = list(b["items"])
                while stack:
                    it = stack.pop()
                    parts.append(it["text"])
                    stack.extend(it["children"])
            elif b["type"] == "table":
                parts.extend(b["header"])
                for r in b["rows"]:
                    parts.extend(r)
            elif b["type"] == "quote":
                parts.append(b["text"])

    def walk(sec):
        parts.append(sec["title"])
        walk_blocks(sec["blocks"])
        for c in sec["children"]:
            walk(c)

    walk_blocks(doc["intro"])
    for s in doc["sections"]:
        walk(s)
    return plain_text(" \n ".join(parts)).lower()


def infer_purpose(doc: dict) -> dict:
    if doc["meta"].get("purpose"):
        p = doc["meta"]["purpose"].lower().replace(" ", "_")
        return {"type": p, "label": PURPOSES.get(p, ([], p.replace("_", " ").title()))[1],
                "confidence": 1.0, "source": "front matter"}
    text = _all_text(doc)
    # the title and the opening sentence say the most about purpose: they weigh extra
    lead = next((b["text"] for b in doc["intro"] if b["type"] == "paragraph"), "")
    title = plain_text(" ".join([doc["title"], doc.get("subtitle", ""), lead])).lower()
    scores = Counter()
    for key, (words, _) in PURPOSES.items():
        for w in words:
            n = len(re.findall(r"\b" + re.escape(w), text))
            scores[key] += n + (3 if w in title else 0)
    if not scores or scores.most_common(1)[0][1] < 3:
        return {"type": "general", "label": "Overview", "confidence": 0.0, "source": "heuristics"}
    (best, s1), *rest = scores.most_common(2) + [(None, 0)]
    s2 = rest[0][1] if rest else 0
    return {"type": best, "label": PURPOSES[best][1],
            "confidence": round(min(1.0, (s1 - s2) / max(s1, 1) + 0.3), 2),
            "source": "heuristics", "scores": dict(scores.most_common(4))}


# --------------------------------------------------------------------------- #
# list classification
# --------------------------------------------------------------------------- #
KW = {
    "cycle": r"\b(boucle|cyclique|itérati\w*|amélioration continue|cycle|cyclic|loop|lifecycle|life cycle|iterat\w*|continuous|recurring|flywheel|pdca|feedback loop|circular)\b",
    "process": r"\b(étapes?|processus|démarche|déroulement|parcours|méthode|steps?|process|workflow|pipeline|procedure|how it works|how to|stages?|phases?|flow|onboarding|method|approach|getting started)\b",
    "timeline": r"\b(calendrier|planning|jalons?|feuille de route|historique|chronologie|timeline|roadmap|milestones?|schedule|history|plan for|calendar|chronolog\w*)\b",
    "hierarchy": r"\b(organigramme|gouvernance|équipes?|arborescence|composants|organi[sz]ation|org chart|structure|hierarchy|team|teams|architecture|breakdown|taxonomy|components|tree|governance|reporting line)\b",
    "comparison": r"\b(avant|après|comparaison|comparatif|avantages|inconvénients|vs\.?|versus|compar\w*|pros|cons|before|after|options?|alternatives?|trade-?offs?)\b",
    "pyramid": r"\b(pyramid|pyramide|layers?|levels?|tiers?|maslow|foundation|niveaux|couches)\b",
    "funnel": r"\b(funnel|entonnoir|tunnel|conversion|pipeline commercial|sales pipeline|acquisition|lead\w*|prospects?)\b",
    "hub": r"\b(hub|écosystème|ecosystem|au cœur|au centre|at the (centre|center|heart)|autour de|around|central|pivot|plateforme|platform|piliers?|pillars?)\b",
    "chart": r"\b(tendances?|évolution|croissance|répartition|chiffre d'affaires|mensuel\w*|trimestriel\w*|annuel\w*|trends?|growth|growing|over time|evolution|chart|graph|distribution|revenue|sales|volume|share|monthly|quarterly|yearly|annual|(month|quarter|year) over (month|quarter|year)|per (month|quarter|year)|by (month|quarter|year))\b",
    "stairs": r"\b(maturit\w*|staircase|escalier|paliers?|montée en (puissance|maturité|compétences?)|step[- ]?up|crawl,? walk,? run|niveaux? de maturité)\b",
    "actions": r"\b(prochaines étapes|actions?|décisions?|recommandations?|next steps?|action items?|to-?dos?|asks?|decisions? (needed|required)|recommendations?)\b",
}

LABEL_RE = re.compile(r"^\s*\*\*(?P<label>[^*]{1,60}?)\*\*\s*[:：—–-]?\s*(?P<rest>.*)$")
COLON_LABEL_RE = re.compile(r"^\s*(?P<label>[^:*`\[\]]{1,40}?)\s*[:：—–]\s+(?P<rest>.+)$")
STAT_RE = re.compile(
    r"^\s*(\*\*)?(?P<num>[~≈+\-]?[$€£¥]?\d[\d.,\s]*\s?(%|x|×|k|K|m|M|bn|B|pts?|h|ms|s|days?|weeks?)?\+?)(\*\*)?\s*[:—–-]?\s*(?P<rest>.+)$")
# A bold figure keeps its whole bold span as the value ("**60% à 95%**", "**1,00 €**").
BOLD_STAT_RE = re.compile(r"^\s*\*\*(?P<num>[~≈+\-]?[$€£¥]?\d[^*]{0,18}?)\*\*\s*[:—–-]?\s*(?P<rest>.+)$")


def stat_match(text: str):
    return BOLD_STAT_RE.match(text) or STAT_RE.match(text)
DATE_RE = re.compile(
    r"^\s*(\*\*)?(?P<label>([QT][1-4]\s*['’]?\d{2,4}|H[12]\s*\d{2,4}|FY\s?\d{2,4}|\d{4}(-\d{2}(-\d{2})?)?|"
    r"(Jan(uary)?|Feb(ruary)?|Mar(ch)?|Apr(il)?|May|June?|July?|Aug(ust)?|Sept?(ember)?|Oct(ober)?|Nov(ember)?|Dec(ember)?|janv(ier)?|f[ée]v(r(ier)?)?|mars|avr(il)?|mai|juin|juil(let)?|ao[uû]t|sept(embre)?|oct(obre)?|nov(embre)?|d[ée]c(embre)?)\.?(?![a-zà-ÿ])(\s+\d{1,2})?(,?\s+\d{4})?|"
    r"(Week|Month|Day|Sprint|Phase|Year|Wave|Release|Semaine|Mois|Jour|Étape|Vague|Lot)\s*\d+[a-z]?(\s*[-–]\s*\d+)?|v?\d+\.\d+(\.\d+)?))(\*\*)?\s*[:—–-]\s*(?P<rest>.+)$",
    re.I)


def split_label(text: str) -> tuple[str, str]:
    """'**Label**: rest' or 'Label: rest' -> (label, rest); ('', text) otherwise."""
    m = LABEL_RE.match(text)
    if m and m.group("rest"):
        return m.group("label").strip(), m.group("rest").strip()
    m = COLON_LABEL_RE.match(text)
    if m and "http" not in m.group("label") and len(m.group("label").split()) <= 5:
        return m.group("label").strip(), m.group("rest").strip()
    return "", text


def _depth(items) -> int:
    return 1 + max((_depth(i["children"]) for i in items if i["children"]), default=0) if items else 0


def _leaves(items) -> int:
    return sum(_leaves(i["children"]) if i["children"] else 1 for i in items)


def _count_lines(items) -> int:
    return sum(1 + _count_lines(i["children"]) for i in items)


def _kw(kind: str, text: str) -> bool:
    return re.search(KW[kind], text, re.I) is not None


def _plain_len(items) -> float:
    return sum(len(plain_text(i["text"])) for i in items) / max(len(items), 1)


def classify_list(block: dict, context: str) -> tuple[str, dict]:
    """Pick the best visual for a list. Returns (kind, extra-data)."""
    items = block["items"]
    n = len(items)
    depth = _depth(items)
    texts = [i["text"] for i in items]

    tree = decision_tree(items, context.split("\x00")[-1])
    if tree:
        return "hierarchy", {"items": [tree], "decision": True}

    plan = gantt(items, _LANG)
    if plan:
        return "gantt", plan

    # a funnel keyword wins over figures: "10,000 visitors -> 85 contracts" is a funnel
    if _kw("funnel", context) and 3 <= n <= 6 and depth <= 2 and re.search(r"\b(funnel|entonnoir|tunnel|conversion)\b", context, re.I):
        return "funnel", {"items": [_labelled(i, *split_label(i["text"])) for i in items]}

    stats = [stat_match(t) for t in texts]
    if 2 <= n <= 5 and all(stats) and depth == 1 and all(percent(m.group("num")) is not None for m in stats):
        # shares of a whole read best as rings
        return "rings", {"items": [{"value": m.group("num").strip(), "text": m.group("rest").strip(),
                                    "percent": percent(m.group("num"))} for m in stats]}
    if (2 <= n <= 4 and all(stats) and depth == 1) or (n == 1 and stats[0] and depth <= 2):
        # one figure alone is a headline number; its sub-items explain it
        return "stats", {"items": [{"value": m.group("num").strip(), "text": m.group("rest").strip(),
                                    "details": [capitalize_first(c["text"]) for c in i["children"]]}
                                   for m, i in zip(stats, items)]}

    geo = country_list(items, context)
    if geo:
        return "map", geo

    if is_flow(items):
        return "flow", {"items": [_labelled(i, *split_label(i["text"])) for i in items]}

    dates = [DATE_RE.match(t) for t in texts]
    if 3 <= n <= 8 and depth <= 2 and (all(dates) or (_kw("timeline", context) and sum(map(bool, dates)) >= n - 1)):
        return "timeline", {"items": [_labelled(i, m.group("label").strip() if m else "", m.group("rest") if m else i["text"])
                                      for i, m in zip(items, dates)]}

    if n == 1 and 3 <= len(items[0]["children"]) <= 8 and depth == 2 and _kw("hub", context):
        root = items[0]
        return "hub", {"root": _labelled({"children": []}, *split_label(root["text"])),
                       "items": [_labelled(c, *split_label(c["text"])) for c in root["children"]]}

    if _kw("cycle", context) and 3 <= n <= 8 and depth <= 2:
        return "cycle", {"items": [_labelled(i, *split_label(i["text"])) for i in items]}

    if depth >= 2 and _leaves(items) <= 14 and (_kw("hierarchy", context) or (n == 1 and items[0]["children"])):
        return "hierarchy", {"items": items}

    if _kw("pyramid", context) and 3 <= n <= 6 and depth == 1 and re.search(r"\bpyramid\b", context, re.I):
        return "pyramid", {"items": [_labelled(i, *split_label(i["text"])) for i in items]}

    labelled = [split_label(t) for t in texts]
    has_labels = all(lbl for lbl, _ in labelled)
    short = _plain_len(items) <= 110

    if _kw("stairs", context) and 3 <= n <= 6 and depth <= 2:
        return "stairs", {"items": [_labelled(i, *split_label(i["text"])) for i in items]}

    if 3 <= n <= 7 and depth <= 2 and not _kw("actions", context.split("\x00")[-1]) and (
            (block["ordered"] and (short or has_labels)) or (_kw("process", context) and short and has_labels)):
        return "process", {"items": [_labelled(i, *split_label(i["text"])) for i in items]}

    if 2 <= n <= 6 and depth <= 2 and has_labels:
        data = {"items": [_labelled(i, lbl, rest) for i, (lbl, rest) in zip(items, labelled)]}
        if _VARIANTS and n >= 3 and all(CODE_RE.match(lbl) for lbl, _ in labelled):
            data["variant"] = "rows"      # P0..P3, T1..T3: tags read best as a ranked list of bands
        return "cards", data

    return "bullets", {"items": items}


CODE_RE = re.compile(r"^[A-Z]{1,3}\s?\d{1,2}$")
FLOW_IN = re.compile(r"\b(entrants?|entrées?|inputs?|sources?|existant|patrimoine|contexte|besoins?|données|data|"
                     r"context|as[- ]is|current|today|aujourd'hui|amont|upstream)\b", re.I)
FLOW_OUT = re.compile(r"\b(livrables?|sorties?|outputs?|résultats?|deliverables?|results?|outcomes?|bénéfices?|"
                      r"benefits?|services?|valeur|value|to[- ]be|impacts?|aval|downstream|mvp)\b", re.I)


def is_flow(items: list) -> bool:
    """Three labelled boxes that read inputs -> core -> outputs (a case-study one-pager)."""
    if len(items) != 3 or _depth(items) > 2:
        return False
    labels = [split_label(i["text"]) for i in items]
    if not all(lbl for lbl, _ in labels):
        return False
    first, last = (plain_text(" ".join(x)) for x in (labels[0], labels[2]))
    return bool(FLOW_IN.search(first) and FLOW_OUT.search(last))


def _labelled(item: dict, label: str, rest: str) -> dict:
    """Normalise to {"label", "text", "children"}; plain items get label=text."""
    if not label:
        label, rest = rest, ""
    detail = [capitalize_first(c["text"]) for c in item["children"]]
    return {"label": capitalize_first(label), "text": capitalize_first(rest), "details": detail}


ARROW_RE = re.compile(r"\s*(?:→|->|=>|⇒|⟶)\s*")


def decision_tree(items: list, title: str) -> dict | None:
    """A flat list that encodes a decision: either "condition → outcome" lines, or a
    repeating pattern such as Task / Model / Task / Model (optionally after one header
    line). Returns the root of a tree for the hierarchy diagram, or None."""
    n = len(items)
    if n < 3 or _depth(items) != 1:
        return None
    texts = [plain_text(i["text"]).strip() for i in items]
    if max(map(len, texts)) > 90:
        return None
    node = lambda t, kids=(): {"text": capitalize_first(t), "children": list(kids)}
    pairs = [ARROW_RE.split(t, maxsplit=1) for t in texts]
    arrows = [p for p in pairs if len(p) == 2 and all(x.strip() for x in p)]
    if len(arrows) >= 2 and len(arrows) >= n - 1:
        root = next((i["text"] for i, p in zip(items, pairs) if len(p) != 2), title)
        return node(root, [node(a, [node(b)]) for a, b in arrows])
    first = [re.sub(r"\W+$", "", t.split()[0].lower()) if t.split() else "" for t in texts]
    for lead in (0, 1):
        body = first[lead:]
        for p in (2, 3):
            if len(body) % p or len(body) // p < 2:
                continue
            heads = body[:p]
            if len(set(heads)) < p or any(len(h) < 3 for h in heads):
                continue
            if all(body[k] == heads[k % p] for k in range(len(body))):
                its = items[lead:]
                kids = [node(its[g]["text"], [node(x["text"]) for x in its[g + 1:g + p]])
                        for g in range(0, len(its), p)]
                return node(items[0]["text"] if lead else title, kids)
    return None


# --------------------------------------------------------------------------- #
# table helpers
# --------------------------------------------------------------------------- #
NUM_RE = re.compile(r"^\s*[~≈]?[-+]?[$€£¥]?\s?\d[\d,.\s]*\s?(%|k|K|m|M|bn|B)?\s*$")


def _num(s: str) -> float | None:
    s = plain_text(s)
    if not NUM_RE.match(s):
        return None
    mult = {"k": 1e3, "K": 1e3, "m": 1e6, "M": 1e6, "bn": 1e9, "B": 1e9}
    unit = re.search(r"(k|K|m|M|bn|B)\s*$", s)
    digits = re.sub(r"[^\d.\-]", "", s.replace(",", ""))
    try:
        v = float(digits)
    except ValueError:
        return None
    return v * mult[unit.group(1)] if unit else v


def table_is_chartable(table: dict) -> bool:
    rows = table["rows"]
    if not (2 <= len(rows) <= 16) or len(table["header"]) < 2:
        return False
    return all(_num(r[c]) is not None for r in rows for c in range(1, len(table["header"])) if c < len(r))


def chart_data(table: dict) -> dict:
    cats = [plain_text(r[0]) for r in table["rows"]]
    series = []
    for c, name in enumerate(table["header"][1:], start=1):
        series.append({"name": plain_text(name), "values": [_num(r[c]) or 0 for r in table["rows"]]})
    timeish = sum(bool(DATE_RE.match(c + ": x")) for c in cats) >= len(cats) - 1
    pct = all("%" in r[c] for r in table["rows"] for c in range(1, len(r)))
    return {"categories": cats, "series": series,
            "chart_type": "line" if timeish and len(cats) >= 4 else "column",
            "percent": pct}


# --------------------------------------------------------------------------- #
# planning
# --------------------------------------------------------------------------- #
def _slide(kind: str, title: str, **kw) -> dict:
    d = {"kind": kind, "title": title}
    d.update({k: v for k, v in kw.items() if v not in (None, "", [], {})})
    return d


def _chunk_items(items: list, max_lines: int) -> list[list]:
    total = _count_lines(items)
    if total > max_lines:           # balance the slides instead of leaving an orphan
        max_lines = -(-total // -(-total // max_lines))
    chunks, cur, lines = [], [], 0
    for it in items:
        n = 1 + _count_lines(it["children"])
        if cur and lines + n > max_lines:
            chunks.append(cur)
            cur, lines = [], 0
        cur.append(it)
        lines += n
    if cur:
        chunks.append(cur)
    return chunks


def plan_chunk(title: str, blocks: list[dict], context: str = "") -> list[dict]:
    """Turn one heading's blocks into one or more slides."""
    hint = next((b for b in blocks if b["type"] == "hint"), None)
    notes = [b["text"] for b in blocks if b["type"] == "notes"]
    blocks = [b for b in blocks if b["type"] not in ("hint", "notes")]

    # explicit slide breaks ("---") split the chunk
    groups, cur = [], []
    for b in blocks:
        if b["type"] == "break":
            groups.append(cur)
            cur = []
        else:
            cur.append(b)
    groups.append(cur)
    groups = [g for g in groups if g] or [[]]
    if len(groups) > 1:
        slides = []
        for g in groups:
            slides += plan_chunk(title, g + ([hint] if hint else []), context)
        if notes and slides:
            slides[0]["notes"] = "\n".join(filter(None, [slides[0].get("notes", "")] + notes))
        return slides

    ctx = f"{context}\x00{title}"
    paragraphs = [b for b in blocks if b["type"] == "paragraph"]
    visuals = [b for b in blocks if b["type"] != "paragraph"]
    slides: list[dict] = []

    # lead = first short paragraph that precedes the first visual
    lead = ""
    extra_notes = []
    for b in blocks:
        if b["type"] != "paragraph":
            break
        if not lead and len(plain_text(b["text"])) <= 260 and visuals:
            lead = b["text"]
        else:
            extra_notes.append(b["text"])
    # paragraphs after visuals go to notes (full content never lost)
    seen_visual = False
    for b in blocks:
        if b["type"] != "paragraph":
            seen_visual = True
        elif seen_visual:
            extra_notes.append(b["text"])

    forced = hint["kind"] if hint and hint["kind"] in ALL_KINDS else None

    if not visuals:
        if not paragraphs:
            return [_slide("section", title)] if forced != "text" else []
        texts = [p["text"] for p in paragraphs]
        total = sum(len(plain_text(t)) for t in texts)
        if forced in ("bullets",) or len(texts) > 2 or total > 420:
            items = [{"text": t, "children": []} for t in texts]
            for i, chunk in enumerate(_chunk_items(items, 6)):
                slides.append(_slide("bullets", title if i == 0 else f"{title} {_CONT}",
                                     items=chunk, plain=True))
        else:
            slides.append(_slide("text", title, paragraphs=texts))
        if notes:
            slides[0]["notes"] = "\n".join(notes)
        return slides

    # one image + short text under the same heading -> one slide, text beside the picture
    images = [b for b in visuals if b["type"] == "image"]
    if forced == "image" and not images:
        forced = None
    if len(images) == 1 and forced in (None, "image"):
        img, others = images[0], [b for b in visuals if b["type"] != "image"]
        opts = hint["options"] if hint else {}
        side = {"position": opts.get("position", "right")}
        texts = [p["text"] for p in paragraphs]
        side_items = None
        if not others and texts and sum(len(plain_text(x)) for x in texts) <= 600:
            side_items = [{"text": x, "children": []} for x in texts]
            side["plain"] = True
            lead, extra_notes = "", [n for n in extra_notes if n not in texts]
        elif len(others) == 1 and others[0]["type"] == "list" and _count_lines(others[0]["items"]) <= 7:
            kind0, _ = classify_list(others[0], ctx)
            if kind0 == "bullets" or forced == "image":
                side_items = others[0]["items"]
                side["ordered"] = others[0]["ordered"]
        if side_items:
            visuals = [dict(img, side_items=side_items, **side)]

    # a short blockquote beside a diagram is its key message: a banner above the diagram when
    # it comes first, a takeaway bar under it when it comes after, not a slide of its own
    banner = takeaway = ""
    main = [b for b in visuals if b["type"] != "quote"]
    if forced != "quote" and main:
        first = visuals.index(main[0])
        for qi, b in enumerate(list(visuals)):
            if b["type"] != "quote" or b.get("attribution") or len(plain_text(b["text"])) > 200:
                continue
            if qi < first and not banner:
                banner = b["text"]
            elif qi > first and not takeaway:
                takeaway = b["text"]
            else:
                continue
            visuals = [v for v in visuals if v is not b]

    used = set()
    for vi, b in enumerate(visuals):
        if vi in used:
            continue
        t = title if vi == 0 else f"{title} {_CONT}"
        this_lead = lead if vi == 0 else ""
        kind = forced if (forced and vi == 0) else None
        if b["type"] == "list":
            auto_kind, data = classify_list(b, ctx)
            if kind and kind != auto_kind:
                data = _force_list(kind, b)
            kind = kind or auto_kind
            if kind == "bullets":
                items_ = [dict(i, text=capitalize_first(i["text"])) for i in data["items"]]
                chunks = _chunk_items(items_, MAX_BULLET_LINES - (2 if this_lead else 0))
                # a short flat list (no hint asking for plain bullets) is drawn as highlighted rows
                boxed = forced != "bullets" and len(chunks) == 1 and 2 <= len(items_) <= 6 \
                    and _depth(items_) == 1 and max(len(plain_text(i["text"])) for i in items_) <= 160
                for ci, chunk in enumerate(chunks):
                    slides.append(_slide("bullets", t if ci == 0 else f"{title} {_CONT}",
                                         lead=this_lead if ci == 0 else "", items=chunk,
                                         ordered=b["ordered"], style="rows" if boxed else None))
            else:
                if kind == "flow":
                    data["panels"] = _flow_panels(visuals[vi + 1] if vi + 1 < len(visuals) else None)
                    if data["panels"]:
                        used.add(vi + 1)
                slides.append(_slide(kind, t, lead=this_lead, **data))
        elif b["type"] == "table":
            if kind == "matrix" or (kind is None and is_matrix(b) and len(b["rows"]) <= 10):
                slides.append(_slide("matrix", t, lead=this_lead, header=b["header"], rows=b["rows"]))
            elif kind == "chart" or (kind is None and table_is_chartable(b) and (
                    _kw("chart", ctx) or chart_data(b)["chart_type"] == "line")):
                slides.append(_slide("chart", t, lead=this_lead, chart=chart_data(b)))
            else:
                rows = b["rows"]
                for ri in range(0, max(len(rows), 1), MAX_TABLE_ROWS):
                    slides.append(_slide("table", t if ri == 0 else f"{title} {_CONT}",
                                         lead=this_lead if ri == 0 else "",
                                         header=b["header"], rows=rows[ri:ri + MAX_TABLE_ROWS],
                                         align=b.get("align", [])))
        elif b["type"] == "code":
            slides.append(_slide("code", t, lead=this_lead, code=b["text"], lang=b["lang"]))
        elif b["type"] == "quote":
            slides.append(_slide("quote", t, quote=b["text"], attribution=b["attribution"]))
        elif b["type"] == "image":
            slides.append(_slide("image", t, lead=this_lead, src=b["src"], alt=b["alt"],
                                 caption=b.get("caption"), items=b.get("side_items"),
                                 plain=b.get("plain"), ordered=b.get("ordered"),
                                 position=b.get("position") if b.get("side_items") else None))

    if slides and banner:
        slides[0]["banner"] = banner
    if slides and takeaway:
        slides[-1]["takeaway"] = takeaway
    if hint and hint["options"].get("title") and slides:
        slides[0]["title"] = hint["options"]["title"]
    if hint:
        for s_ in slides:
            s_.update({k: v for k, v in hint["options"].items() if k in SLIDE_OPTIONS})
            if s_["kind"] == "cards" and hint["options"].get("variant", "").lower() in VARIANTS:
                s_["variant"] = hint["options"]["variant"].lower()     # an explicit hint beats auto
    all_notes = [n for n in extra_notes + notes if n]
    if all_notes and slides:
        slides[0]["notes"] = "\n\n".join(plain_text(n) if not n.startswith("<!--") else n for n in all_notes)
    return slides


def _flow_panels(block: dict | None) -> list:
    """The list right after a flow (context, stakes, success factors...) becomes 2-4 panels under it."""
    if not block or block["type"] != "list" or not 2 <= len(block["items"]) <= 4 or _depth(block["items"]) > 2:
        return []
    return [_labelled(i, *split_label(i["text"])) for i in block["items"]]


def _force_list(kind: str, block: dict) -> dict:
    items = block["items"]
    if kind == "stats":
        out = []
        for i in items:
            m = stat_match(i["text"])
            out.append({"value": m.group("num").strip(), "text": m.group("rest")} if m
                       else {"value": "", "text": i["text"]})
        return {"items": out}
    if kind == "timeline":
        out = []
        for i in items:
            m = DATE_RE.match(i["text"])
            out.append(_labelled(i, m.group("label"), m.group("rest")) if m else _labelled(i, *split_label(i["text"])))
        return {"items": out}
    if kind == "hierarchy":
        tree = decision_tree(items, "")
        return {"items": [tree] if tree and tree["text"] else items}
    if kind == "bullets":
        return {"items": items}
    if kind == "gantt":
        return gantt(items, _LANG) or _force_list("timeline", block)
    if kind == "rings":
        out = []
        for i in items:
            m = stat_match(i["text"])
            v = m.group("num").strip() if m else ""
            out.append({"value": v, "text": m.group("rest") if m else i["text"], "percent": percent(v) or 0})
        return {"items": out}
    if kind == "map":
        return country_list(items, "map") or {"groups": []}
    if kind == "hub":
        if len(items) == 1 and items[0]["children"]:
            return {"root": _labelled({"children": []}, *split_label(items[0]["text"])),
                    "items": [_labelled(c, *split_label(c["text"])) for c in items[0]["children"]]}
        return {"root": None, "items": [_labelled(i, *split_label(i["text"])) for i in items]}
    return {"items": [_labelled(i, *split_label(i["text"])) for i in items]}


def _comparison(section: dict, forced: bool = False) -> dict | None:
    """Two or three subsections that are each a short list (or each one code block) -> comparison slide. With a
    `<!-- slide: comparison -->` hint under the `##`, 2-4 subsections become columns."""
    kids = section["children"]
    if not (2 <= len(kids) <= (4 if forced else 3)):
        return None
    titles = " ".join(k["title"] for k in kids)
    if not (forced or _kw("comparison", section["title"]) or _kw("comparison", titles)):
        return None
    lead = next((b["text"] for b in section["blocks"] if b["type"] == "paragraph"), "")
    # code side by side (current code vs recommended fix): each subsection holds one code block
    code_cols = []
    for k in kids:
        codes = [b for b in k["blocks"] if b["type"] == "code"]
        rest = [b for b in k["blocks"] if b["type"] not in ("code", "paragraph", "hint", "notes")]
        if len(codes) != 1 or rest:
            code_cols = None
            break
        paras = [b["text"] for b in k["blocks"] if b["type"] == "paragraph"]
        code_cols.append({"title": k["title"], "text": " ".join(paras), "code": codes[0]["text"],
                          "lang": codes[0]["lang"], "items": []})
    if code_cols:
        return _slide("comparison", section["title"], lead=lead, columns=code_cols)
    columns = []
    for k in kids:
        lists = [b for b in k["blocks"] if b["type"] == "list"]
        others = [b for b in k["blocks"] if b["type"] not in ("list", "paragraph", "hint", "notes")]
        if len(lists) != 1 or others or _count_lines(lists[0]["items"]) > 7:
            return None
        paras = [b["text"] for b in k["blocks"] if b["type"] == "paragraph"]
        columns.append({"title": k["title"], "text": " ".join(paras), "items": lists[0]["items"]})
    lead = next((b["text"] for b in section["blocks"] if b["type"] == "paragraph"), "")
    return _slide("comparison", section["title"], lead=lead, columns=columns)


def _attach_part_markers(doc: dict) -> None:
    """`<!-- part: X -->` directly under a `##` opens a part at that section; written
    anywhere else (e.g. just above the next `##`) it opens the part at the next section.
    Markers are removed from the blocks and stored as section["part"]."""
    sections = doc["sections"]
    pending = None

    def take(blocks):
        """Remove the markers; return (opens_here, title) for each one: a marker opens the part
        at this section when nothing but hints or notes comes before it."""
        found, content = [], False
        for b in blocks:
            if b["type"] == "part":
                found.append((not content, b["title"]))
            elif b["type"] not in ("hint", "notes"):
                content = True
        blocks[:] = [b for b in blocks if b["type"] != "part"]
        return found

    for b in take(doc["intro"]):
        pending = b[1]
    for sec in sections:
        here = None
        if pending:
            here, pending = pending, None
        for opens_here, t in take(sec["blocks"]):
            if opens_here:
                here = t
            else:
                pending = t
        for c in sec["children"]:
            for _, t in take(c["blocks"]):
                pending = t
        if here:
            sec["blocks"].insert(0, {"type": "part", "title": here})
            sec["part"] = here


def plan_document(doc: dict, *, agenda: bool | None = None, closing: bool = True,
                  lang: str | None = None, auto_notes: bool = True, variants: bool = True) -> dict:
    purpose = infer_purpose(doc)
    lang = lang if lang in STRINGS else detect_language(doc)
    T = STRINGS[lang]
    purpose["label"] = T["labels"].get(purpose["type"], purpose["label"])
    global _CONT, _LANG, _VARIANTS
    _CONT = T["cont"]
    _LANG = lang
    # front matter `variants: off` or --no-variants: every cards slide is a grid unless hinted
    _VARIANTS = variants and str(doc["meta"].get("variants", "")).lower() not in ("off", "no", "false", "0")
    slides = []

    subtitle = doc.get("subtitle") or ""
    intro = list(doc["intro"])
    # a short first intro paragraph doubles as the subtitle
    if not subtitle and intro and intro[0]["type"] == "paragraph" and len(plain_text(intro[0]["text"])) <= 140:
        subtitle = plain_text(intro.pop(0)["text"])
    byline = " · ".join(filter(None, [doc["meta"].get("author"), doc["meta"].get("date")]))
    slides.append(_slide("title", doc["title"], subtitle=subtitle or purpose["label"], byline=byline))

    if intro:
        slides += plan_chunk(T["overview"], intro, doc["title"])

    sections = doc["sections"]
    _attach_part_markers(doc)
    parts = plan_parts(sections, lang) if len(sections) > 1 else None
    for sec in sections:
        sec["blocks"] = [b for b in sec["blocks"] if b["type"] != "part"]
    if agenda is None:
        agenda = len(sections) >= 3
    if agenda:
        items = [p["title"] for p in parts] if parts else [s["title"] for s in sections]
        slides.append(_slide("agenda", doc["meta"].get("agenda_title", T["agenda"]), items=items))

    starts = {p["start"]: (k, p) for k, p in enumerate(parts or [], start=1)}
    for idx, sec in enumerate(sections, start=1):
        if idx - 1 in starts:
            k, part = starts[idx - 1]
            covers = [s["title"] for s in sections[part["start"]:part["end"]]]
            slides.append(_slide("section", part["title"], number=k, covers=covers, part=True))
        hints = [b for b in sec["blocks"] if b["type"] == "hint"]
        if not hints:
            comp = _comparison(sec)
        elif hints[0]["kind"] == "comparison":
            comp = _comparison(sec, forced=True)
            if comp and hints[0]["options"].get("title"):
                comp["title"] = hints[0]["options"]["title"]
        else:
            comp = None
        if comp:
            slides.append(comp)
            continue
        own = [b for b in sec["blocks"]]
        kids = sec["children"]
        if kids and (len(kids) >= 2 or not own) and len(sections) > 1:
            lead = next((plain_text(b["text"]) for b in own if b["type"] == "paragraph"
                         and len(plain_text(b["text"])) <= 180), "")
            # inside a part the part divider carries the number; sections get a plain divider
            slides.append(_slide("section", sec["title"], subtitle=lead, number=None if parts else idx))
            own = [b for b in own if not (b["type"] == "paragraph" and plain_text(b["text"]) == lead)]
        if any(b["type"] not in ("hint", "notes") for b in own):
            slides += plan_chunk(sec["title"], own, doc["title"])
        elif not kids:
            slides += plan_chunk(sec["title"], own, doc["title"])
        for k in kids:
            slides += plan_chunk(k["title"], k["blocks"], f"{doc['title']} {sec['title']}")

    last = sections[-1]["title"] if sections else ""
    if closing and not re.search(r"\b(thank|questions?|q&a)\b", last, re.I):
        wrapped_up = re.search(r"\b(next steps?|decision|conclusions?|summary|recap|wrap-?up|prochaines étapes|synthèse|récapitulatif|décision)\b", last, re.I)
        title = T["questions"] if wrapped_up else T["closing"].get(purpose["type"], T["closing"]["general"])
        slides.append(_slide("closing", title, subtitle=doc["title"], short_title=T["qa"]))

    warnings = check_titles(slides)
    add_variety(slides, auto=_VARIANTS)
    if auto_notes:
        add_notes(slides, lang, purpose["label"])
    plan = {"title": doc["title"], "purpose": purpose, "source": doc.get("source", ""),
            "lang": lang, "slides": slides}
    for key in ("icons", "schemas"):            # front matter: icons: off / schemas: off
        if str(doc["meta"].get(key, "")).lower() in ("off", "no", "false", "0"):
            plan[key] = "off"
    if not _VARIANTS:
        plan["variants"] = "off"
    if parts:
        plan["parts"] = [{"title": p["title"], "sections": [s["title"] for s in sections[p["start"]:p["end"]]],
                          "auto": p["auto"]} for p in parts]
    if warnings:
        plan["warnings"] = warnings
    return plan
