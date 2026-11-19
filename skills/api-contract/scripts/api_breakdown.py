# /// script
# requires-python = ">=3.10"
# ///
"""Découpe le backend décrit par les interfaces en lots de chiffrage à trois points.

Entrée : la description des interfaces d'api_build.py (api.json : ressources,
opérations REST, événements, option d'architecture citée par `source`). Le
script, et non le modèle :
- fait un lot par ressource (modèle, persistance, migrations ; complexité
  selon le nombre de champs), par opération (complexité selon la méthode,
  montée d'un cran pour une grosse ressource reçue ou beaucoup d'erreurs
  métier), par événement (envoi ou réception) et par système externe relié
  dans l'option (intégration), plus les lots transverses du backend (socle,
  authentification si l'API est sécurisée, messagerie s'il y a des
  événements, observabilité, tests d'intégration par opération) ;
- déclare le réemploi entre fonctionnalités : une opération de même forme
  qu'une précédente (même méthode, même gabarit de chemin) ou sur une
  ressource déjà exposée réutilise ce lot (`reuse`, part épargnée et base) ;
- contrôle les lots contre le schéma des lots de solution-estimate et écrit
  `<base>.lots.json` (repris par `estimate_build.py --draft --lots`) et
  `<base>.md` (découpage pour la revue).

Les jours viennent d'abaques : ceux donnés avant le lancement (section
backend de ~/.myskills/abaques.json ou MYSKILLS_ABAQUES, de references.abaques
de mission.json, puis de --abaques), sinon des valeurs par défaut à calibrer,
signalées comme telles.

    uv run scripts/api_breakdown.py api.json [--out decoupage-back] [--abaques ABAQUES.json] | --schema
"""

import argparse
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import skill_paths  # noqa: E402
from spec_schema import check, input_schema, print_schema  # noqa: E402
from text_tools import beside  # noqa: E402

workspace = skill_paths.require_module("mission-workspace", "lib/workspace.py")

LEVELS = ["faible", "moyenne", "elevee", "tres-elevee"]
# Abaques par défaut, à calibrer : remplacés clé à clé par la section backend des abaques fournis.
DEFAULTS = {
    "profile": "dev-back",
    "days": {"faible": [0.5, 1, 1.5], "moyenne": [1, 2, 3], "elevee": [2, 4, 6], "tres-elevee": [5, 8, 13]},
    "resource": {"moyenne": 8, "elevee": 20},
    "operations": {"GET": "faible", "POST": "moyenne", "PUT": "moyenne", "PATCH": "moyenne", "DELETE": "faible"},
    "escalate": {"request_fields": 10, "errors": 4},
    "events": {"send": "faible", "receive": "moyenne"},
    "integration": "elevee",
    "reuse": {"same_shape": 40, "same_resource": 20},
    "transverse": [
        {"name": "Socle backend : projet, configuration, intégration continue", "phase": "realisation",
         "effort": [2, 3, 5]},
        {"name": "Authentification et habilitations", "phase": "realisation", "effort": [2, 3, 5], "when": "security"},
        {"name": "Messagerie : producteurs, consommateurs, reprise sur erreur", "phase": "realisation",
         "effort": [1, 2, 3], "when": "events"},
        {"name": "Observabilité : journaux, métriques, traces", "phase": "realisation", "effort": [1, 1.5, 2.5]},
        {"name": "Tests d'intégration des API", "phase": "tests", "per_operation": [0.1, 0.25, 0.4]},
    ],
}
GENERIC_ERRORS = {400, 401, 403, 404, 500, 503}  # erreurs techniques : pas de règle métier en plus


def bump(level: str) -> str:
    return LEVELS[min(LEVELS.index(level) + 1, len(LEVELS) - 1)]


def resource_of(kind: str | None) -> str | None:
    return kind.removesuffix("[]") if kind else None


def shape(op: dict) -> str:
    """Forme d'une opération : méthode et gabarit de chemin (segments fixes et paramètres anonymisés)."""
    path = re.sub(r"\{[^}]+\}", "{}", op["path"].rstrip("/"))
    return op["method"] + " " + "/".join("{}" if seg == "{}" else "x" if seg else "" for seg in path.split("/"))


def load_option(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> dict | None:
    """Option d'architecture citée par source (api.json), validée si architecture-options est installé."""
    source = spec.get("source")
    if not source:
        warnings.append("pas de source dans la description : intégrations avec les systèmes externes non découpées")
        return None
    try:
        data = json.loads((base / source["options"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"source : {source['options']} illisible ({error})")
        return None
    schema = skill_paths.schema_of("architecture-options", "options_build.py")
    if schema is None:
        warnings.append("options.json non validé : " + skill_paths.absent("architecture-options", "options_build.py"))
    else:
        errors += [f"source ({source['options']}) : {e}" for e in check(data, schema)][:10]
    option = next((o for o in data.get("options", []) if o.get("id") == source["option"]), None)
    if option is None:
        errors.append(f"source/option : « {source['option']} » absente de {source['options']}")
    return option


def breakdown(spec: dict, option: dict | None, rules: dict) -> list[dict]:
    """Lots au format de solution-estimate (work), avec leur réemploi."""
    days, work = rules["days"], []
    fields = {r["name"]: len(r["fields"]) for r in spec["resources"]}
    ops, events = spec.get("operations", []), spec.get("events", [])

    def lot(name, phase, level, points, note, component=None, refs=None, reuse=None):
        entry = {"id": f"B{len(work) + 1}", "name": name, "phase": phase, "effort": {rules["profile"]: points},
                 "complexity": level, "note": note}
        if component:
            entry["component"] = component
        if refs:
            entry["refs"] = sorted(set(refs))
        if reuse:
            entry["reuse"] = reuse
        work.append(entry)
        return entry["id"]

    # Composant principal du backend : celui qui porte le plus d'opérations (lots transverses, ressources
    # seulement imbriquées).
    owners = [o["component"] for o in ops if o.get("component")] or [e["component"] for e in events if e.get("component")]
    main = max(set(owners), key=owners.count) if owners else None
    # Ressources : composant de la première opération ou du premier événement qui l'emploie.
    for res in spec["resources"]:
        users = [o for o in ops if res["name"] in (resource_of(o.get("request")), resource_of(o.get("response")))]
        users += [e for e in events if resource_of(e["payload"]) == res["name"]]
        count = fields[res["name"]]
        level = "elevee" if count >= rules["resource"]["elevee"] else \
            "moyenne" if count >= rules["resource"]["moyenne"] else "faible"
        lot(f"Ressource {res['name']} : modèle, persistance, migrations", "realisation", level, days[level],
            f"{count} champ(s) ; abaque {level}", next((u["component"] for u in users if u.get("component")), main))
    # Opérations : première de sa forme au plein, suivantes en réemploi.
    first_shape: dict[str, str] = {}
    first_resource: dict[str, str] = {}
    for op in ops:
        level = rules["operations"][op["method"]]
        why = [f"{op['method']} : {level}"]
        request = resource_of(op.get("request"))
        if request and fields.get(request, 0) >= rules["escalate"]["request_fields"]:
            level, why = bump(level), why + [f"{fields[request]} champs reçus"]
        business = [e for e in op.get("errors", []) if e not in GENERIC_ERRORS]
        if len(business) >= rules["escalate"]["errors"]:
            level, why = bump(level), why + [f"{len(business)} erreurs métier"]
        reuse = None
        kind, res = shape(op), resource_of(op.get("response")) or request
        if kind in first_shape:
            reuse = {"from": first_shape[kind], "percent": rules["reuse"]["same_shape"],
                     "basis": f"même forme que {first_shape[kind]} ({kind}) : contrôleur, service et tests repris"}
        elif res and res in first_resource:
            reuse = {"from": first_resource[res], "percent": rules["reuse"]["same_resource"],
                     "basis": f"ressource {res} déjà exposée par {first_resource[res]} : modèle et accès aux données repris"}
        if reuse and not reuse["percent"]:
            reuse = None
        lid = lot(f"Opération {op['id']} ({op['method']} {op['path']})", "realisation", level, days[level],
                  "abaque " + ", ".join(why), op.get("component"), op.get("refs"), reuse)
        first_shape.setdefault(kind, lid)
        if res:
            first_resource.setdefault(res, lid)
    for event in events:
        action = event.get("action", "send")
        level = rules["events"][action]
        lot(f"Événement {event['name']} ({'envoi' if action == 'send' else 'réception'}, {event['channel']})",
            "realisation", level, days[level], f"abaque {level}", event.get("component"), event.get("refs"))
    # Intégrations : systèmes externes de l'option reliés à un composant de la solution.
    if option:
        comps = {c["id"]: c for c in option.get("components", [])}
        externals = []
        for flow in option.get("flows", []):
            for end, other in ((flow["to"], flow["from"]), (flow["from"], flow["to"])):
                if comps.get(end, {}).get("role") == "external" and comps.get(other, {}).get("role") != "person" \
                        and end not in externals:
                    externals.append(end)
        for cid in externals:
            level = rules["integration"]
            lot(f"Intégration avec {comps[cid].get('label', cid)}", "integration", level, days[level],
                f"système externe de l'option ; abaque {level}", cid, comps[cid].get("refs"))
    secured = spec.get("security", "none") != "none"
    for item in rules["transverse"]:
        if item.get("when") == "security" and not secured or item.get("when") == "events" and not events:
            continue
        points = item.get("effort") or [round(v * max(len(ops), 1), 2) for v in item.get("per_operation", [0, 0, 0])]
        lot(item["name"], item["phase"], "moyenne", points,
            "lot transverse" + (f", {len(ops)} opération(s)" if item.get("per_operation") else ""), main)
    return work


def net(task: dict) -> list[float]:
    keep = 1 - task.get("reuse", {}).get("percent", 0) / 100
    return [v * keep for v in next(iter(task["effort"].values()))]


def write(spec: dict, work: list[dict], base: Path, sources: list[str], meta: dict) -> list[Path]:
    total = [round(sum(net(w)[i] for w in work), 2) for i in range(3)]
    lots, md = base.with_name(base.name + ".lots.json"), beside(base.with_name(base.name + ".md"))
    lots.write_text(json.dumps({"domain": "backend", "source": meta["input"], "abaques": sources,
                                "work": work}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    origin = "abaques fournis (" + ", ".join(Path(s).name for s in sources) + ")" if sources \
        else "abaques par défaut, à calibrer"
    out = [f"# Découpage backend : {spec['title']}", "",
           f"{len(work)} lots, {total[0]:g} à {total[2]:g} jours (probable {total[1]:g}), réemploi déduit ; "
           f"{origin}.", "", "| Lot | Phase | Composant | Complexité | Mini | Probable | Maxi | Réemploi | Base |",
           "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for w in work:
        low, likely, high = net(w)
        reuse = f"{w['reuse']['percent']:g} % de {w['reuse']['from']}" if w.get("reuse") else ""
        out.append(f"| {w['id']} {w['name']} | {w['phase']} | {w.get('component', '')} | {w['complexity']} | "
                   f"{low:g} | {likely:g} | {high:g} | {reuse} | {w['note']} |")
    md.write_text("\n".join(out) + "\n", encoding="utf-8")
    return [lots, md]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("api", type=Path, nargs="?", help="description des interfaces (api.json d'api_build.py)")
    parser.add_argument("--out", type=Path, help="chemin des fichiers produits, sans extension")
    parser.add_argument("--abaques", type=Path, help="abaques propres, après ceux de l'utilisateur et de la mission")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma de la description sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.api), "outputs": [], "resources": 0, "operations": 0, "events": 0,
              "integrations": 0, "lots": 0, "reused": 0, "days": [], "abaques": [], "calibrated": False,
              "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.api:
        errors.append("description des interfaces attendue (api.json d'api_build.py)")
        return done(1)
    try:
        spec = json.loads(args.api.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{args.api} illisible ({error})")
        return done(1)
    errors += check(spec, input_schema(__file__))
    if not spec.get("operations") and not spec.get("events") and not errors:
        errors.append("ni opération ni événement : rien à découper")
    abaques, sources, invalid = workspace.abaques([args.api], args.abaques)
    errors += invalid
    if errors:
        return done(1)
    own = abaques.get("backend", {})
    rules = {k: ({**v, **own[k]} if isinstance(v, dict) and k in own else own.get(k, v)) for k, v in DEFAULTS.items()}
    names = {r["name"] for r in spec["resources"]}
    for index, op in enumerate(spec.get("operations", [])):
        for key in ("request", "response"):
            if op.get(key) and resource_of(op[key]) not in names:
                errors.append(f"operations/{index}/{key} : ressource inconnue « {op[key]} »")
    option = load_option(spec, args.api.parent, errors, warnings)
    if errors:
        return done(1)
    work = breakdown(spec, option, rules)
    estimate = skill_paths.schema_of("solution-estimate", "estimate_build.py")
    if estimate is None:
        warnings.append("lots non contrôlés : " + skill_paths.absent("solution-estimate", "estimate_build.py"))
    else:
        item = {**estimate["properties"]["work"]["items"], "$defs": estimate.get("$defs", {})}
        for w in work:
            errors += [f"lots/{w['id']} : {e}" for e in check(w, item)]
    if option:
        known = {c["id"] for c in option.get("components", [])}
        errors += [f"lots/{w['id']} : composant « {w['component']} » absent de l'option {option['id']}"
                   for w in work if w.get("component") and w["component"] not in known]
    if errors:
        return done(1)
    base = args.out or args.api.parent / "decoupage-back"
    base.parent.mkdir(parents=True, exist_ok=True)
    report["outputs"] = [str(p) for p in write(spec, work, base, sources, report)]
    report.update(resources=len(spec["resources"]), operations=len(spec.get("operations", [])),
                  events=len(spec.get("events", [])),
                  integrations=sum(1 for w in work if w["phase"] == "integration"), lots=len(work),
                  reused=sum(1 for w in work if w.get("reuse")),
                  days=[round(sum(net(w)[i] for w in work), 2) for i in range(3)], abaques=sources,
                  calibrated=bool(own))
    if not own:
        warnings.append("abaques backend par défaut, à calibrer : donnez les vôtres avant le lancement "
                        "(~/.myskills/abaques.json, references.abaques de la mission ou --abaques)")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
