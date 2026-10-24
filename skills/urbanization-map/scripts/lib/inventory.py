"""Lecture d'un POS : description JSON de pos_build.py, inventaire CSV ou note
Markdown avec un tableau (colonnes zone, quartier, ilot, application, statut,
et type facultatif). Une seule lecture pour pos_build.py et pos_impact.py.
"""

import csv
import json
import unicodedata
from pathlib import Path

SUFFIXES = (".json", ".csv", ".md")


def plain(text: str) -> str:
    """Minuscules sans accents ni espaces en trop, pour comparer des noms."""
    text = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def markdown_rows(text: str) -> list[dict]:
    """Lignes du premier tableau Markdown qui a une colonne zone (note Obsidian d'inventaire)."""
    table: list[list[str]] = []
    for line in text.splitlines() + [""]:
        stripped = line.strip()
        if stripped.startswith("|"):
            table.append([c.strip() for c in stripped.strip("|").split("|")])
            continue
        if table and "zone" in [plain(c) for c in table[0]]:
            body = [r for r in table[1:] if not set("".join(r)) <= set("-: ")]
            return [dict(zip(table[0], r)) for r in body]
        table = []
    return []


def rows_to_spec(rows: list[dict], label: str, errors: list[str]) -> dict:
    """Lignes d'inventaire -> description pos_build.py (zones, quartiers, îlots, applications)."""
    columns = {plain(c): c for c in (rows[0].keys() if rows else [])}
    if not rows or "zone" not in columns:
        errors.append(f"{label} : colonnes attendues zone, quartier, ilot, application, statut (en-tête)")
        return {"zones": []}

    def col(row: dict, *names: str) -> str:
        for name in names:
            if name in columns:
                return (row.get(columns[name]) or "").strip()
        return ""

    zones: dict = {}
    for number, row in enumerate(rows, 2):
        zone, quartier = col(row, "zone"), col(row, "quartier") or "—"
        ilot, app = col(row, "ilot", "ilot fonctionnel"), col(row, "application", "app")
        if not zone:
            errors.append(f"{label} ligne {number} : zone vide")
            continue
        z = zones.setdefault(zone, {"name": zone, "quartiers": {}})
        if col(row, "type", "kind"):
            z["kind"] = col(row, "type", "kind")
        q = z["quartiers"].setdefault(quartier, {"name": quartier, "ilots": {}, "apps": []})
        target = q["ilots"].setdefault(ilot, {"name": ilot, "apps": []})["apps"] if ilot else q["apps"]
        if app:
            target.append({"name": app, "status": col(row, "statut", "status") or "en-place"})
    return {"zones": [{**z, "quartiers": [{**q, "ilots": list(q["ilots"].values())}
                                          for q in z["quartiers"].values()]}
                      for z in zones.values()]}


def read_inventory(path: Path, errors: list[str]) -> dict:
    """POS lu depuis un .json, un .csv (UTF-8 ou cp1252 d'Excel) ou une note .md avec son tableau."""
    suffix = path.suffix.lower()
    if suffix not in SUFFIXES:
        errors.append(f"{path.name} n'est pas lisible ({suffix}) : description .json, inventaire .csv "
                      "ou note .md avec le tableau zone, quartier, ilot, application, statut")
        return {"zones": []}
    try:
        if suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            # Excel sous Windows enregistre ses CSV en cp1252 par défaut.
            text = path.read_text(encoding="cp1252")
    except (OSError, ValueError) as error:
        errors.append(f"POS illisible {path} ({error})")
        return {"zones": []}
    if suffix == ".md":
        return rows_to_spec(markdown_rows(text), path.name, errors)
    try:
        dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    return rows_to_spec(list(csv.DictReader(text.splitlines(), dialect=dialect)), "CSV", errors)
