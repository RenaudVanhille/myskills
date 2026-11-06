# /// script
# requires-python = ">=3.10"
# ///
"""Compare deux versions d'api.json : ruptures de contrat et ajouts compatibles, version à monter.

Pour une évolution, le contrat validé reste la référence et sa copie de
travail reçoit les changements. Le script, et non le modèle :

- avec --start, copie la référence dans la copie de travail si elle n'existe
  pas encore, puis s'arrête ;
- valide les deux descriptions contre le schéma d'api_build.py ;
- classe chaque écart : rupture (opération retirée, méthode ou chemin
  changé, champ retiré ou de type changé, champ rendu obligatoire dans une
  ressource reçue, valeur d'énumération retirée, événement retiré ou de
  canal ou de charge changés, sécurité changée) ou compatible (opération,
  champ facultatif, valeur, événement ajoutés) ;
- vérifie que la version majeure monte s'il y a une rupture ;
- écrit l'écart en Markdown (--out).

    uv run scripts/api_diff.py REFERENCE.json COPIE.json [--start] [--schema] [--out ecarts-api.md]
"""

import argparse
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import check, input_schema, print_schema, schema_option  # noqa: E402


def load(path: Path, label: str, schema: dict, errors: list[str]) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{label} : {path} illisible ({error})")
        return None
    invalid = check(data, schema)
    if invalid:
        errors += [f"{label} : {path.name} : {e}" for e in invalid[:10]]
        return None
    return data


def base(kind: str | None) -> str | None:
    return kind[:-2] if kind and kind.endswith("[]") else kind


def major(version: str | None) -> int | None:
    match = re.match(r"\D*(\d+)", version or "")
    return int(match.group(1)) if match else None


def compare(old: dict, new: dict) -> tuple[list[dict], list[dict]]:
    breaking, compatible = [], []

    def add(target, where, what):
        target.append({"where": where, "change": what})

    if old.get("security", "none") != new.get("security", "none"):
        add(breaking, "security", f"sécurité {old.get('security', 'none')} devenue {new.get('security', 'none')}")
    ops_old = {o["id"]: o for o in old.get("operations", [])}
    ops_new = {o["id"]: o for o in new.get("operations", [])}
    by_route = {(o["method"], o["path"]): o for o in new.get("operations", [])}
    for oid, op in ops_old.items():
        if oid not in ops_new:
            moved = by_route.get((op["method"], op["path"]))
            if moved:
                add(compatible, f"operations/{oid}", f"renommée {moved['id']} (même {op['method']} {op['path']})")
            else:
                add(breaking, f"operations/{oid}", f"{op['method']} {op['path']} retirée")
            continue
        now = ops_new[oid]
        if (op["method"], op["path"]) != (now["method"], now["path"]):
            add(breaking, f"operations/{oid}", f"{op['method']} {op['path']} devenue {now['method']} {now['path']}")
        for key, label in (("request", "requête"), ("response", "réponse")):
            if op.get(key) != now.get(key):
                add(breaking, f"operations/{oid}/{key}", f"{label} {op.get(key, 'aucune')} devenue {now.get(key, 'aucune')}")
        if op.get("public") and not now.get("public"):
            add(breaking, f"operations/{oid}", "opération publique devenue authentifiée")
    for oid, op in ops_new.items():
        if oid not in ops_old and not any((o["method"], o["path"]) == (op["method"], op["path"])
                                          for o in old.get("operations", [])):
            add(compatible, f"operations/{oid}", f"{op['method']} {op['path']} ajoutée")
    # Ressources : reçues (requête, événement reçu) ou rendues (réponse, événement publié).
    received = {base(o.get("request")) for o in new.get("operations", [])} | \
        {base(e["payload"]) for e in new.get("events", []) if e.get("action") == "receive"}
    res_old = {r["name"]: r for r in old["resources"]}
    res_new = {r["name"]: r for r in new["resources"]}
    for name, res in res_old.items():
        if name not in res_new:
            add(breaking, f"resources/{name}", "ressource retirée")
            continue
        now = res_new[name]
        for field, kind in res["fields"].items():
            if field not in now["fields"]:
                add(breaking, f"resources/{name}/{field}", "champ retiré")
            elif now["fields"][field] != kind:
                add(breaking, f"resources/{name}/{field}", f"type {kind} devenu {now['fields'][field]}")
        for field, kind in now["fields"].items():
            if field not in res["fields"]:
                needed = field in now.get("required", [])
                add(breaking if needed and name in received else compatible, f"resources/{name}/{field}",
                    f"champ {kind} ajouté" + (", obligatoire dans une ressource reçue" if needed and name in received
                                              else ", obligatoire" if needed else ""))
        newly = [f for f in now.get("required", []) if f in res["fields"] and f not in res.get("required", [])]
        for field in newly:
            add(breaking if name in received else compatible, f"resources/{name}/{field}",
                "champ devenu obligatoire" + (" dans une ressource reçue" if name in received else ""))
        for field, values in res.get("enums", {}).items():
            after = now.get("enums", {}).get(field, values)
            for value in values:
                if value not in after:
                    add(breaking, f"resources/{name}/{field}", f"valeur « {value} » retirée")
            for value in after:
                if value not in values:
                    add(compatible, f"resources/{name}/{field}", f"valeur « {value} » ajoutée")
    for name in res_new:
        if name not in res_old:
            add(compatible, f"resources/{name}", "ressource ajoutée")
    ev_old = {e["name"]: e for e in old.get("events", [])}
    ev_new = {e["name"]: e for e in new.get("events", [])}
    for name, ev in ev_old.items():
        if name not in ev_new:
            add(breaking, f"events/{name}", f"événement retiré ({ev['channel']})")
            continue
        for key, label in (("channel", "canal"), ("payload", "charge"), ("action", "sens")):
            if ev.get(key) != ev_new[name].get(key):
                add(breaking, f"events/{name}", f"{label} {ev.get(key)} devenu {ev_new[name].get(key)}")
    for name, ev in ev_new.items():
        if name not in ev_old:
            add(compatible, f"events/{name}", f"événement ajouté ({ev['channel']})")
    return breaking, compatible


def markdown(title: str, report: dict) -> str:
    lines = [f"# Écart de contrat : {title}", "",
             f"Version {report['versions']['reference'] or 'non donnée'} vers "
             f"{report['versions']['copy'] or 'non donnée'} : {len(report['breaking'])} rupture(s), "
             f"{len(report['compatible'])} ajout(s) compatible(s).", ""]
    for key, label in (("breaking", "Ruptures"), ("compatible", "Compatibles")):
        if report[key]:
            lines += [f"## {label}", "", "| Élément | Écart |", "| --- | --- |"]
            lines += [f"| {c['where']} | {c['change'].replace('|', '/')} |" for c in report[key]]
            lines.append("")
    if not (report["breaking"] or report["compatible"]):
        lines += ["Aucun écart.", ""]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", type=Path, nargs="?", help="api.json validé (référence)")
    parser.add_argument("copy", type=Path, nargs="?", help="copie de travail qui reçoit les changements")
    parser.add_argument("--start", action="store_true", help="copie la référence dans COPIE.json si elle manque")
    parser.add_argument("--out", type=Path, help="écart en Markdown")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if args.copy is None:
        parser.error("REFERENCE.json et COPIE.json attendus")
    errors: list[str] = []
    warnings: list[str] = []
    report = {"reference": str(args.reference), "copy": str(args.copy), "output": None,
              "versions": {"reference": None, "copy": None}, "breaking": [], "compatible": [],
              "errors": errors, "warnings": warnings}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    schema = input_schema(Path(__file__).with_name("api_build.py"))
    if args.start:
        if args.copy.exists():
            warnings.append(f"{args.copy} existe déjà : copie de travail gardée telle quelle")
        elif load(args.reference, "référence", schema, errors) is not None:
            args.copy.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(args.reference, args.copy)
            report["output"] = str(args.copy)
        return done(1 if errors else 0)
    old = load(args.reference, "référence", schema, errors)
    new = load(args.copy, "copie", schema, errors)
    if errors:
        return done(1)
    report["versions"] = {"reference": old.get("version"), "copy": new.get("version")}
    report["breaking"], report["compatible"] = compare(old, new)
    before, after = major(old.get("version")), major(new.get("version"))
    if report["breaking"]:
        if before is None or after is None:
            warnings.append(f"{len(report['breaking'])} rupture(s) de contrat sans version comparable : "
                            "donner version dans les deux descriptions")
        elif after <= before:
            warnings.append(f"{len(report['breaking'])} rupture(s) de contrat : version majeure à monter "
                            f"({old.get('version')} vers {before + 1}.0.0), ou garder l'ancienne version en parallèle")
    elif report["compatible"] and old.get("version") == new.get("version"):
        warnings.append("ajouts compatibles : version mineure à monter")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown(new["title"], report), encoding="utf-8")
        report["output"] = str(args.out)
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
