# /// script
# requires-python = ">=3.10"
# ///
"""Écrit un modèle LikeC4 (C4) à partir d'une description JSON courte ou d'une option d'architecture.

La description donne les éléments (personnes, systèmes, conteneurs,
composants, bases, files, externes), imbriqués par `elements`, les relations
et les vues. Le script, et non le modèle, écrit `model.c4` (identifiants,
guillemets, chemins pointés des relations, vues) et copie
`specification.c4` (types aux couleurs de la charte), puis vérifie le modèle :
identifiants uniques, relations vers des éléments connus, imbrication C4
(composant dans un conteneur, conteneur dans un système), vues de 20
éléments au plus. Si `likec4` est installé, il lance `likec4 validate`.

Avec `--from-options options.json --option A`, la description vient de
l'option d'architecture-options : personnes et externes autour d'un système,
composants en conteneurs, flux en relations ; rien à réécrire.

    uv run scripts/c4_build.py MODELE.json [--out-dir DOSSIER] | --from-options options.json --option ID [--out-dir DOSSIER] | --schema
"""

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

HERE = Path(__file__).resolve().parent
SPECIFICATION = HERE.parent / "references" / "specification.c4"
# Imbrication permise : type -> types parents possibles (None : racine du modèle).
PARENTS = {"person": {None}, "external": {None, "system"}, "system": {None},
           "container": {"system"}, "database": {"system", "container"}, "queue": {"system", "container"},
           "component": {"container"}}
# Rôle d'un composant d'architecture-options -> type C4.
ROLES = {"person": "person", "external": "external", "system": "container", "db": "database", "queue": "queue"}
MAX_VIEW = 20


def quote(text: str) -> str:
    return '"' + str(text).replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def ident(text: str) -> str:
    """Identifiant LikeC4 : lettres, chiffres, tiret bas ; commence par une lettre."""
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_") or "e"
    return value if value[0].isalpha() else "e_" + value


def from_options(path: Path, option_id: str, errors: list[str]) -> dict | None:
    """Description C4 d'une option d'architecture-options (options.json validé contre son schéma)."""
    try:
        spec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"--from-options : {error}")
        return None
    schema = schema_of("architecture-options", "options_build.py")
    if schema is None:
        errors.append("--from-options : " + absent("architecture-options", "options_build.py"))
        return None
    invalid = check(spec, schema, schema)
    if invalid:
        errors.extend(f"--from-options : {e}" for e in invalid[:10])
        return None
    options = {o["id"]: o for o in spec["options"]}
    if option_id not in options:
        errors.append(f"--option : option inconnue « {option_id} » ({', '.join(options)})")
        return None
    option = options[option_id]
    outside = [c for c in option["components"] if c.get("role") in ("person", "external")]
    inside = [c for c in option["components"] if c.get("role") not in ("person", "external")]

    def element(c: dict) -> dict:
        item = {"id": c["id"], "kind": ROLES[c.get("role", "system")], "label": c["label"]}
        if c.get("tech"):
            item["tech"] = c["tech"]
        return item
    system = {"id": "solution", "kind": "system", "label": option["name"], "elements": [element(c) for c in inside]}
    relations = [{"from": f["from"], "to": f["to"], "label": f.get("label") or "utilise",
                  **({"async": True} if f.get("style") == "async" else {})} for f in option.get("flows", [])]
    title = f"Option {option['id']} : {option['name']}"
    return {"title": title, "elements": [element(c) for c in outside] + [system], "relations": relations,
            "views": [{"id": "index", "title": f"{title} (contexte)"},
                      {"id": "solution", "title": f"{title} (conteneurs)", "of": "solution"}]}


def build(spec: dict, errors: list[str], warnings: list[str]) -> tuple[str, dict]:
    paths: dict[str, str] = {}      # id -> chemin pointé LikeC4
    kinds: dict[str, str] = {}
    parent_of: dict[str, str | None] = {}
    lines = ["model {"]

    def walk(items: list[dict], parent: str | None, depth: int) -> None:
        pad = "  " * depth
        for index, item in enumerate(items):
            eid = item["id"]
            where = f"elements/{eid}"
            if eid in paths:
                errors.append(f"{where} : identifiant en double")
                continue
            kind = item["kind"]
            parent_kind = kinds.get(parent) if parent else None
            if parent_kind not in PARENTS[kind]:
                allowed = ", ".join("racine" if p is None else p for p in sorted(PARENTS[kind], key=str))
                errors.append(f"{where} : {kind} dans {parent_kind or 'la racine'} (permis : {allowed})")
            name = ident(eid)
            paths[eid] = f"{paths[parent]}.{name}" if parent else name
            kinds[eid], parent_of[eid] = kind, parent
            head = f"{pad}{name} = {kind} {quote(item['label'])}"
            if item.get("description"):
                head += f" {quote(item['description'])}"
            body = []
            if item.get("tech"):
                body.append(f"{pad}  technology {quote(item['tech'])}")
            if item.get("elements"):
                lines.append(head + " {")
                lines.extend(body)
                walk(item["elements"], eid, depth + 1)
                lines.append(f"{pad}}}")
            elif body:
                lines.extend([head + " {", *body, f"{pad}}}"])
            else:
                lines.append(head)
    walk(spec["elements"], None, 1)
    lines.append("")
    seen = set()
    for index, rel in enumerate(spec.get("relations", [])):
        where = f"relations/{index}"
        ends = []
        for end in ("from", "to"):
            if rel[end] not in paths:
                close = difflib.get_close_matches(rel[end], list(paths), n=1)
                errors.append(f"{where}/{end} : élément inconnu « {rel[end]} »"
                              + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            ends.append(paths.get(rel[end]))
        if None in ends:
            continue
        if not rel.get("label"):
            warnings.append(f"{where} : relation {rel['from']} -> {rel['to']} sans verbe (label)")
        key = (rel["from"], rel["to"], rel.get("label"))
        if key in seen:
            warnings.append(f"{where} : relation en double {rel['from']} -> {rel['to']}")
        seen.add(key)
        arrow = "-[async]->" if rel.get("async") else "->"
        text = f"  {ends[0]} {arrow} {ends[1]}"
        if rel.get("label"):
            text += f" {quote(rel['label'])}"
        if rel.get("tech"):
            text += f" {{\n    technology {quote(rel['tech'])}\n  }}"
        lines.append(text)
    lines += ["}", "", "views {"]
    views = spec.get("views") or [{"id": "index", "title": spec.get("title", "Contexte")}] + \
        [{"id": ident(e["id"]), "title": f"{e['label']} : conteneurs", "of": e["id"]}
         for e in spec["elements"] if e["kind"] == "system" and e.get("elements")]
    view_ids = set()
    for index, view in enumerate(views):
        vid = ident(view["id"])
        if vid in view_ids:
            errors.append(f"views/{index} : vue en double « {vid} »")
        view_ids.add(vid)
        target = view.get("of")
        if target and target not in paths:
            errors.append(f"views/{index}/of : élément inconnu « {target} »")
            continue
        shown = [e for e, p in parent_of.items() if p == target] if target else \
            [e for e, p in parent_of.items() if p is None]
        if len(shown) > MAX_VIEW:
            warnings.append(f"vue {vid} : {len(shown)} éléments (au plus {MAX_VIEW} pour rester lisible)")
        lines += [f"  view {vid}" + (f" of {paths[target]}" if target else "") + " {",
                  f"    title {quote(view.get('title') or spec.get('title', vid))}", "    include *", "  }"]
    lines.append("}")
    counts = {"elements": len(paths), "relations": len(spec.get("relations", [])), "views": len(views)}
    return "\n".join(lines) + "\n", counts


def likec4_validate(folder: Path, warnings: list[str]) -> list[str]:
    """likec4 validate s'il est installé ; sinon, la commande à lancer pour valider et exporter."""
    tool = shutil.which("likec4")
    if not tool:
        warnings.append("modèle non validé par LikeC4 (likec4 absent) : uv run ../diagram-export/scripts/export.py "
                        f"{folder} --check")
        return []
    done = subprocess.run([tool, "validate", str(folder)], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")
    if done.returncode == 0:
        return []
    return [f"likec4 validate : {line}" for line in (done.stdout + done.stderr).splitlines() if line.strip()][:10]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description MODELE.json")
    parser.add_argument("--from-options", type=Path, help="options.json d'architecture-options, au lieu de MODELE.json")
    parser.add_argument("--option", help="identifiant de l'option, avec --from-options")
    parser.add_argument("--out-dir", type=Path, help="dossier LikeC4 (défaut : <nom>-c4 à côté de l'entrée)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if bool(args.spec) == bool(args.from_options) or bool(args.from_options) != bool(args.option):
        parser.error("MODELE.json, ou --from-options options.json --option ID")
    source = args.spec or args.from_options
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(source), "output": None, "elements": 0, "relations": 0, "views": 0,
              "errors": errors, "warnings": warnings}
    if args.spec:
        try:
            spec = json.loads(args.spec.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(str(error))
            spec = None
    else:
        spec = from_options(args.from_options, args.option, errors)
    if spec is not None:
        # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
        errors += validate(spec, __file__)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    text, counts = build(spec, errors, warnings)
    report.update(counts)
    if not errors:
        stem = source.name.removesuffix(".json")
        if args.from_options:
            stem = f"option-{args.option.lower()}"
        folder = args.out_dir or source.with_name(f"{stem}-c4")
        folder.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SPECIFICATION, folder / "specification.c4")
        with open(folder / "model.c4", "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        report["output"] = str(folder)
        errors += likec4_validate(folder, warnings)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
