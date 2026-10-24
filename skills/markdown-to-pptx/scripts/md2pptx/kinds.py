"""Detection helpers for the v0.4 slide kinds: Gantt date ranges, maturity ratings
(Harvey balls), percentages (rings) and country lists (maps)."""
from __future__ import annotations

import re

from .brand import country_code, fold, has_map
from .parser import plain_text

# --------------------------------------------------------------------------- #
# Gantt: "Jan–Mar 2026: Discovery", "Q1-Q3: Build", "Weeks 2-5: Tests", "S3 → S6: Pilot"
# --------------------------------------------------------------------------- #
MONTHS = {
    "jan": 1, "janv": 1, "feb": 2, "fev": 2, "fevr": 2, "mar": 3, "mars": 3, "apr": 4, "avr": 4, "may": 5,
    "mai": 5, "jun": 6, "juin": 6, "jul": 7, "juil": 7, "aug": 8, "aou": 8, "aout": 8, "sep": 9, "sept": 9,
    "oct": 10, "nov": 11, "dec": 12,
}
MONTH_NAMES = {"en": "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split(),
               "fr": "Janv Févr Mars Avr Mai Juin Juil Août Sept Oct Nov Déc".split()}
SEP = r"\s*(?:[-–—→]|->|to|à|au|until|jusqu'?à)\s*"
TOKEN = (r"(?:[QT][1-4]|H[12]|S[12](?=\b)|(?:Weeks?|Semaines?|Sprints?|Phases?|Months?|Mois|Wk|W|S|M)\s*\d{1,2}|"
         r"[A-Za-zéûÉ]{3,9}\.?)(?:\s+\d{4}|\s*['’]\d{2})?")
RANGE_RE = re.compile(rf"^\s*(\*\*)?(?P<a>{TOKEN}|\d{{1,2}})(?:{SEP}(?P<b>{TOKEN}|\d{{1,2}}))?(\*\*)?\s*[:—–]\s*(?P<rest>.+)$",
                      re.I)


def _unit(tok: str):
    """-> (unit, index, year) or None. Index is 0-based within the year for months/quarters."""
    t = fold(tok).strip().rstrip(".")
    year = None
    m = re.search(r"(\d{4})$|['’](\d{2})$", t)
    if m:
        year = int(m.group(1) or ("20" + m.group(2)))
        t = t[:m.start()].strip()
    if re.fullmatch(r"[qt][1-4]", t):
        return "quarter", int(t[1]) - 1, year
    if re.fullmatch(r"h[12]", t):
        return "half", int(t[1]) - 1, year
    m = re.fullmatch(r"(w|wk|weeks?|semaines?|s)\s*(\d{1,2})", t)
    if m:
        return "week", int(m.group(2)), year
    m = re.fullmatch(r"(sprints?)\s*(\d{1,2})", t)
    if m:
        return "sprint", int(m.group(2)), year
    m = re.fullmatch(r"(phases?)\s*(\d{1,2})", t)
    if m:
        return "phase", int(m.group(2)), year
    m = re.fullmatch(r"(mois|months?|m)\s*(\d{1,2})", t)
    if m:
        return "month_n", int(m.group(2)), year
    key = t[:4] if t[:4] in MONTHS else t[:3]
    if key in MONTHS and (len(t) <= 9):
        return "month", MONTHS[key] - 1, year
    return None


def gantt(items: list, lang: str = "en") -> dict | None:
    """Flat list whose labels are date ranges on one scale -> Gantt rows, else None."""
    if not (2 <= len(items) <= 10) or any(i["children"] for i in items):
        return None
    rows, units, ranges = [], set(), 0
    for it in items:
        m = RANGE_RE.match(it["text"])
        if not m:
            return None
        a = _unit(m.group("a")) if not m.group("a").isdigit() else None
        b = (_unit(m.group("b")) if m.group("b") and not m.group("b").isdigit() else None)
        if a is None:
            return None
        if m.group("b") and m.group("b").isdigit():      # "Week 2-5"
            b = (a[0], int(m.group("b")), a[2])
        if m.group("b") and b is None:
            return None
        b = b or a
        ranges += a != b
        if a[0] != b[0]:
            return None
        units.add(a[0])
        rows.append({"a": a, "b": b, "range": plain_text(m.group(0).split(":")[0]).strip(" *—–"),
                     "text": plain_text(m.group("rest")).strip()})
    if len(units) != 1 or ranges < max(1, len(rows) // 2):
        return None
    unit = units.pop()
    per_year = {"month": 12, "quarter": 4, "half": 2}.get(unit)
    years = [r[k][2] for r in rows for k in "ab" if r[k][2]]
    base_year = min(years) if years else None

    def pos(u, start=True):
        _, idx, year = u
        if per_year:
            y = year if year else base_year
            return (y - base_year if base_year and y else 0) * per_year + idx
        return idx

    for r in rows:      # a range without a year inherits the end's year ("Nov–Feb 2027")
        if per_year and r["b"][2] and not r["a"][2]:
            r["a"] = (r["a"][0], r["a"][1], r["b"][2] - (1 if r["a"][1] > r["b"][1] else 0))
    spans = [(pos(r["a"]), pos(r["b"])) for r in rows]
    if any(e < s for s, e in spans):
        return None
    lo, hi = min(s for s, _ in spans), max(e for _, e in spans)
    if hi - lo + 1 > 24:
        return None
    labels = []
    for k in range(lo, hi + 1):
        if unit == "month":
            y, mth = divmod(k, 12)
            name = MONTH_NAMES.get(lang, MONTH_NAMES["en"])[mth]
            labels.append(name + (f" {str((base_year or 0) + y)[2:]}" if base_year and (mth == 0 or k == lo) else ""))
        elif unit == "quarter":
            y, q = divmod(k, 4)
            labels.append(("T" if lang == "fr" else "Q") + str(q + 1) + (f" {str((base_year or 0) + y)[2:]}" if base_year else ""))
        elif unit == "half":
            y, h = divmod(k, 2)
            labels.append(("S" if lang == "fr" else "H") + str(h + 1) + (f" {str((base_year or 0) + y)[2:]}" if base_year else ""))
        else:
            short = {"week": "S" if lang == "fr" else "W", "sprint": "Sprint ", "phase": "Phase ",
                     "month_n": "M"}[unit]
            labels.append(f"{short}{k}")
    return {"scale": labels, "items": [{"label": r["text"], "range": r["range"], "start": s - lo, "end": e - lo}
                                       for r, (s, e) in zip(rows, spans)]}


# --------------------------------------------------------------------------- #
# maturity matrix: table cells rated ●◕◑◔○, 0-4, 3/4, ★★☆, "high/medium/low"
# --------------------------------------------------------------------------- #
BALLS = {"○": 0, "◔": 1, "◑": 2, "◐": 2, "◒": 2, "◓": 2, "◕": 3, "●": 4}
WORDS = {"none": 0, "aucun": 0, "aucune": 0, "low": 1, "faible": 1, "basic": 1, "medium": 2, "moyen": 2,
         "moyenne": 2, "partial": 2, "partiel": 2, "high": 3, "eleve": 3, "elevee": 3, "fort": 3, "forte": 3,
         "full": 4, "complete": 4, "complet": 4, "total": 4}


def rating(cell: str) -> float | None:
    """Cell -> fill fraction 0..1 or None when it is not a rating."""
    t = plain_text(cell).strip()
    if not t:
        return None
    if t in BALLS:
        return BALLS[t] / 4
    if re.fullmatch(r"[★☆]{1,5}", t):
        return t.count("★") / len(t)
    m = re.fullmatch(r"(\d(?:[.,]\d)?)\s*/\s*([45])", t)
    if m:
        return min(1.0, float(m.group(1).replace(",", ".")) / int(m.group(2)))
    if re.fullmatch(r"[0-4]", t):
        return int(t) / 4
    w = WORDS.get(fold(t))
    return None if w is None else w / 4


def is_matrix(table: dict) -> bool:
    rows = table["rows"]
    cells = [c for r in rows for c in r[1:]]
    if len(table["header"]) < 2 or not rows or not cells:
        return False
    rated = sum(rating(c) is not None for c in cells)
    # bare digits or words ("high") alone are too ambiguous: one symbol (●, ★, 3/4) is required,
    # or a <!-- slide: matrix --> hint
    symbolic = any(plain_text(c).strip() in BALLS or re.search(r"[★☆]|\d\s*/\s*[45]\b", c) for c in cells)
    return rated >= 0.8 * len(cells) and symbolic


# --------------------------------------------------------------------------- #
# percentages -> rings
# --------------------------------------------------------------------------- #
def percent(value: str) -> float | None:
    m = re.fullmatch(r"\s*[~≈+]?(\d{1,3}(?:[.,]\d+)?)\s*%\s*", plain_text(value))
    if not m:
        return None
    v = float(m.group(1).replace(",", "."))
    return v / 100 if 0 <= v <= 100 else None


# --------------------------------------------------------------------------- #
# country lists -> map
# --------------------------------------------------------------------------- #
MAP_KW = re.compile(r"\b(pays|implantations?|présence|presence|countries|country|map|carte|europe\w*|"
                    r"footprint|locations?|offices|bureaux|filiales?|subsidiaries|marchés|markets)\b", re.I)


def country_list(items: list, context: str) -> dict | None:
    """Items naming European countries (flat, or grouped under non-country headings) -> map data."""
    if not has_map():
        return None
    flat = all(not i["children"] for i in items)
    if flat:
        codes = [country_code(i["text"]) for i in items]
        hits = sum(map(bool, codes))
        if hits >= 3 and hits >= 0.8 * len(items) or (hits >= 2 and hits == len(items) and MAP_KW.search(context)):
            return {"groups": [{"label": "", "countries": [c for c in codes if c],
                                "items": [i["text"] for i in items]}]}
        return None
    groups = []
    for g in items:
        if country_code(g["text"]) or not g["children"]:
            return None
        codes = [country_code(c["text"]) for c in g["children"]]
        if not all(codes):
            return None
        groups.append({"label": g["text"], "countries": codes, "items": [c["text"] for c in g["children"]]})
    if 1 <= len(groups) <= 4 and sum(len(g["countries"]) for g in groups) >= 2:
        return {"groups": groups}
    return None
