# /// script
# requires-python = ">=3.10"
# ///
"""Situe des options d'architecture dans le plan d'occupation des sols (POS) du SI.

Lit le POS existant (description JSON ou inventaire CSV de pos_build.py, ou
note Markdown avec son tableau), vérifie le placement de chaque option
(applications créées, modifiées, remplacées, réutilisées), en tire les
impacts (créations, évolutions, remplacements, redondances, flux entre
zones) et écrit la description du POS cible de chaque option
(`pos-option-<id>.json`, à construire avec pos_build.py).

L'entrée est toute description qui a `pos` et des `options` avec leur
`placement` : `options.json` d'architecture-options convient tel quel. Le
module sert aussi à options_build.py (skill architecture-options), qui
l'appelle par son contrat (`requires`).

    uv run scripts/pos_impact.py OPTIONS.json [--out-dir DOSSIER] | --schema
"""

import argparse
import copy
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from inventory import plain, read_inventory  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

CHANGES = {"nouvelle": "à créer", "a-faire-evoluer": "à faire évoluer", "a-remplacer": "à remplacer ou retirer",
           "en-place": "réutilisée telle quelle", "externe": "externe, SaaS"}


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


def read_pos(path: Path, errors: list[str]) -> dict:
    """POS existant ; les erreurs de lecture sont préfixées par « pos : »."""
    found: list[str] = []
    pos = read_inventory(path, found)
    errors += [f"pos : {e}" for e in found]
    return pos


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
    return {"_source": "généré par pos_impact.py : POS existant et placement de l'option",
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


def analyse(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> tuple[dict | None, dict | None, list]:
    """POS lu, index et impacts de chaque option ; (None, None, []) sans POS."""
    if not spec.get("pos"):
        for i, option in enumerate(spec.get("options", [])):
            if option.get("placement"):
                errors.append(f"options/{i} ({option['id']})/placement : POS absent, ajoutez pos à la description")
        return None, None, []
    path = resolve(base, spec["pos"], errors)
    pos = read_pos(path, errors) if path else {"zones": []}
    idx = index(pos)
    if not idx["apps"] and not errors:
        errors.append(f"pos : aucune application dans {spec['pos']}")
    if errors:  # POS illisible : pas d'erreurs en cascade sur chaque placement
        return pos, {"apps": {}, "places": set(), "unreadable": True}, []
    impacts = []
    for i, option in enumerate(spec.get("options", [])):
        if not option.get("placement"):
            warnings.append(f"options/{i} ({option['id']}) : pas de placement dans le POS")
        impacts.append(check_option(option, idx, errors, warnings))
    return pos, idx, impacts


def write_targets(pos: dict, spec: dict, out_dir: Path) -> list[str]:
    """Description pos_build.py du POS cible de chaque option."""
    written = []
    for option in spec["options"]:
        target = out_dir / f"pos-option-{option['id'].lower()}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(target_pos(pos, option, f"POS cible, option {option['id']} : {option['name']}"),
                      handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        written.append(str(target))
    return written


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description avec pos et options (options.json)")
    parser.add_argument("--out-dir", type=Path, help="dossier des POS cibles (défaut : schemas/ à côté du .json)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    report = {"input": str(args.spec), "pos": None, "apps": 0, "impacts": [], "outputs": [], "errors": [],
              "warnings": []}
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report["errors"] += validate(spec, __file__)
    if not report["errors"]:
        report["pos"] = spec["pos"]
        pos, idx, report["impacts"] = analyse(spec, args.spec.parent, report["errors"], report["warnings"])
        report["apps"] = len(idx["apps"]) if idx else 0
        if not report["errors"]:
            report["outputs"] = write_targets(pos, spec, args.out_dir or args.spec.parent / "schemas")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
