"""Position des options dans le plan d'occupation des sols (POS) du SI.

Lit le POS existant (description JSON ou inventaire CSV du skill
urbanization-map), vérifie le placement de chaque option (applications
créées, modifiées, remplacées, réutilisées), en tire les impacts
(redondances, flux entre zones) et la description du POS cible de l'option,
à construire avec pos_build.py. Utilisé par options_build.py.
"""

import copy
import csv
import difflib
import json
import unicodedata
from pathlib import Path

CHANGES = {"nouvelle": "à créer", "a-faire-evoluer": "à faire évoluer", "a-remplacer": "à remplacer ou retirer",
           "en-place": "réutilisée telle quelle", "externe": "externe, SaaS"}


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def app_name(app) -> str:
    return app if isinstance(app, str) else app["name"]


def resolve(base: Path, value: str, errors: list[str]) -> Path | None:
    """Chemin du POS : relatif au .json, ou « vault:<chemin> » dans le vault du workflow
    (memory.vault de workflow.json, à côté du .json), quand le POS a été versé au vault."""
    if not value.startswith("vault:"):
        return base / value
    try:
        state = json.loads((base / "workflow.json").read_text(encoding="utf-8"))
        return Path(state["memory"]["vault"]) / value.removeprefix("vault:").lstrip("/\\")
    except (OSError, ValueError, KeyError, TypeError):
        errors.append(f"pos : « {value} » vise le vault, mais {base / 'workflow.json'} n'en déclare pas "
                      "(journal.py init --vault)")
        return None


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


def read_pos(path: Path, errors: list[str]) -> dict:
    """POS en JSON (format de pos_build.py), en CSV ou en note Markdown avec un tableau
    (colonnes zone, quartier, ilot, application, statut)."""
    suffix = path.suffix.lower()
    if suffix not in (".json", ".csv", ".md"):
        errors.append(f"pos : {path.name} n'est pas lisible ({suffix}) ; donnez la description .json, "
                      "l'inventaire .csv ou une note .md avec le tableau zone, quartier, ilot, application, statut")
        return {"zones": []}
    try:
        if suffix == ".json":
            return json.loads(path.read_text(encoding="utf-8"))
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeDecodeError:
            text = path.read_text(encoding="cp1252")
    except (OSError, ValueError) as error:
        errors.append(f"pos : POS illisible {path} ({error})")
        return {"zones": []}
    if suffix == ".md":
        rows = markdown_rows(text)
    else:
        try:
            dialect = csv.Sniffer().sniff(text.split("\n", 1)[0], delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        rows = list(csv.DictReader(text.splitlines(), dialect=dialect))
    columns = {plain(c): c for c in (rows[0].keys() if rows else [])}
    if "zone" not in columns:
        errors.append(f"pos : colonnes attendues zone, quartier, ilot, application, statut dans {path}")
        return {"zones": []}

    def col(row: dict, *names: str) -> str:
        for name in names:
            if name in columns:
                return (row.get(columns[name], "") or "").strip()
        return ""

    zones: dict = {}
    for row in rows:
        zone = col(row, "zone")
        if not zone:
            continue
        z = zones.setdefault(zone, {"name": zone, "quartiers": {}})
        q = z["quartiers"].setdefault(col(row, "quartier") or "—", {"name": col(row, "quartier") or "—",
                                                                    "ilots": {}, "apps": []})
        ilot, app = col(row, "ilot"), col(row, "application", "app")
        target = q["ilots"].setdefault(ilot, {"name": ilot, "apps": []})["apps"] if ilot else q["apps"]
        if app:
            target.append({"name": app, "status": col(row, "statut", "status") or "en-place"})
    return {"zones": [{**z, "quartiers": [{**q, "ilots": list(q["ilots"].values())}
                                          for q in z["quartiers"].values()]} for z in zones.values()]}


def index(pos: dict) -> dict:
    """Application (nom normalisé) -> (nom, zone, quartier, îlot) ; et lieux connus."""
    apps, places = {}, set()
    for zone in pos.get("zones", []):
        places.add((zone["name"], None, None))
        for quartier in zone.get("quartiers", []):
            places.add((zone["name"], quartier["name"], None))
            for app in quartier.get("apps", []):
                apps[plain(app_name(app))] = (app_name(app), zone["name"], quartier["name"], None)
            for ilot in quartier.get("ilots", []):
                places.add((zone["name"], quartier["name"], ilot["name"]))
                for app in ilot.get("apps", []):
                    apps[plain(app_name(app))] = (app_name(app), zone["name"], quartier["name"], ilot["name"])
    return {"apps": apps, "places": places}


def close(name: str, names) -> str:
    match = difflib.get_close_matches(name, list(names), n=1, cutoff=0.5)
    return f" ; vouliez-vous « {match[0]} » ?" if match else ""


def check_option(option: dict, idx: dict, errors: list[str], warnings: list[str]) -> dict:
    """Vérifie le placement d'une option ; renvoie ses impacts."""
    where = f"options ({option['id']})/placement"
    comps = {c["id"] for c in option["components"]}
    located, impact = {}, {"option": option["id"], "new": 0, "evolve": 0, "replace": 0, "reuse": 0,
                           "redundancies": [], "cross_zone": 0}
    replaced = {plain(p["app"]) for p in option.get("placement", []) if p["change"] == "a-remplacer"}
    for i, place in enumerate(option.get("placement", [])):
        here = f"{where}/{i} ({place['app']})"
        if place.get("component") and place["component"] not in comps:
            errors.append(f"{here}/component : composant inconnu « {place['component']} »")
        known = idx["apps"].get(plain(place["app"]))
        if place["change"] == "nouvelle":
            if known:
                errors.append(f"{here} : déjà dans le POS ({known[1]} / {known[2]}) : a-faire-evoluer ou en-place")
                continue
            spot = (place.get("zone"), place.get("quartier"), place.get("ilot"))
            if not place.get("zone") or not place.get("quartier"):
                errors.append(f"{here} : zone et quartier attendus pour une nouvelle application")
                continue
            if (spot[0], spot[1], None) not in idx["places"]:
                names = [f"{z} / {q}" for z, q, i_ in idx["places"] if q and not i_]
                errors.append(f"{here} : quartier « {spot[0]} / {spot[1]} » absent du POS"
                              + close(f"{spot[0]} / {spot[1]}", names))
                continue
            if spot[2] and spot not in idx["places"]:
                warnings.append(f"{here} : îlot « {spot[2]} » absent du POS, créé dans le POS cible")
            neighbours = [name for name, z, q, il in idx["apps"].values()
                          if (z, q, il) == spot and plain(name) not in replaced]
            if neighbours and spot[2] and not place.get("coexists"):
                impact["redundancies"].append(f"{place['app']} / {', '.join(neighbours)}")
                warnings.append(f"option {option['id']} : redondance possible, {place['app']} rejoint "
                                f"l'îlot {spot[2]} déjà occupé par {', '.join(neighbours)}")
            impact["new"] += 1
            location = spot
        else:
            if not known:
                errors.append(f"{here} : application absente du POS"
                              + close(place["app"], [a[0] for a in idx["apps"].values()]))
                continue
            impact[{"a-faire-evoluer": "evolve", "a-remplacer": "replace"}.get(place["change"], "reuse")] += 1
            location = known[1:]
        if place.get("component"):
            located[place["component"]] = location
    impact["cross_zone"] = sum(1 for f in option.get("flows", []) if f["from"] in located and f["to"] in located
                               and located[f["from"]][0] != located[f["to"]][0])
    return impact


def target_pos(pos: dict, option: dict, title: str) -> dict:
    """Description pos_build.py du POS cible : statuts des applications touchées, nouvelles ajoutées."""
    target = copy.deepcopy(pos)
    target = {k: v for k, v in target.items() if k in ("zones", "vocabulary")}
    changes = {plain(p["app"]): p for p in option.get("placement", []) if p["change"] != "nouvelle"}
    for zone in target["zones"]:
        for quartier in zone.get("quartiers", []):
            for holder in [quartier, *quartier.get("ilots", [])]:
                holder["apps"] = [
                    {"name": app_name(a), "status": changes[plain(app_name(a))]["change"]}
                    if plain(app_name(a)) in changes else a for a in holder.get("apps", [])]
    for place in option.get("placement", []):
        if place["change"] != "nouvelle":
            continue
        zone = next(z for z in target["zones"] if z["name"] == place["zone"])
        quartier = next(q for q in zone["quartiers"] if q["name"] == place["quartier"])
        holder = quartier
        if place.get("ilot"):
            holder = next((i for i in quartier.setdefault("ilots", []) if i["name"] == place["ilot"]), None)
            if holder is None:
                holder = {"name": place["ilot"], "apps": []}
                quartier["ilots"].append(holder)
        holder.setdefault("apps", []).append({"name": place["app"], "status": "nouvelle"})
    return {"_source": "généré par options_build.py : POS existant et placement de l'option",
            "title": title, "detail": "application", **target}


def placement_lines(option: dict, idx: dict) -> list[str]:
    """Tableau Markdown du placement d'une option."""
    lines = ["| Application | Changement | Emplacement |", "| --- | --- | --- |"]
    for place in option.get("placement", []):
        known = idx["apps"].get(plain(place["app"]))
        spot = known[1:] if known and place["change"] != "nouvelle" else \
            (place.get("zone"), place.get("quartier"), place.get("ilot"))
        note = f" (coexiste : {place['coexists']})" if place.get("coexists") else ""
        lines.append(f"| {place['app']} | {CHANGES[place['change']]} | {' / '.join(s for s in spot if s)}{note} |")
    return lines
