# /// script
# requires-python = ">=3.10"
# ///
"""Écrit un diagramme Mermaid (flux ou séquence) à partir d'une description JSON courte.

Le modèle décrit les nœuds et les liens (flowchart) ou les participants et
les messages (séquence) ; le script, et non le modèle, écrit la syntaxe :
identifiants sûrs (pas de mot réservé `end`), libellés entre guillemets,
formes et `classDef` de la charte, sous-graphes, flèches synchrones ou
asynchrones, blocs alt/opt/loop, `autonumber`. Il vérifie les références
(lien ou message vers un nœud inconnu, avec la valeur proche) et le nombre
de nœuds (20 au plus). Le rendu se vérifie ensuite avec diagram-export
(`export.py FICHIER --check`).

Avec `--from-options options.json --option A`, le flowchart vient de
l'option d'architecture-options (composants et flux), sans rien réécrire.

    uv run scripts/mermaid_build.py SCHEMA.json [--out SCHEMA.md|.mmd] | --from-options options.json --option ID [--out F] | --schema
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

# Formes et classes de la charte (shared/references/style.md, section Mermaid).
SHAPES = {"person": ("([", "])"), "system": ("[", "]"), "external": ("[", "]"), "db": ("[(", ")]"),
          "queue": ("[/", "/]"), "alert": ("[", "]")}
CLASSDEFS = {"person": "fill:#fef3c7,stroke:#b45309,color:#1f2937",
             "system": "fill:#dbeafe,stroke:#1d4ed8,color:#1f2937",
             "external": "fill:#f3f4f6,stroke:#6b7280,color:#1f2937,stroke-dasharray:4 3",
             "db": "fill:#dcfce7,stroke:#15803d,color:#1f2937",
             "queue": "fill:#f3e8ff,stroke:#7e22ce,color:#1f2937",
             "alert": "fill:#fee2e2,stroke:#b91c1c,color:#1f2937"}
ARROWS = {"call": "->>", "reply": "-->>", "async": "-)"}
RESERVED = {"end", "graph", "subgraph", "class", "classdef", "style", "click", "linkstyle", "direction"}
MAX_NODES = 20


def label(text: str) -> str:
    return '"' + str(text).replace('"', "#quot;").replace("\n", "<br>") + '"'


def safe_id(text: str) -> str:
    value = re.sub(r"[^A-Za-z0-9_]+", "_", str(text)).strip("_") or "n"
    return value + "_" if value.lower() in RESERVED else value


def from_options(path: Path, option_id: str, errors: list[str]) -> dict | None:
    """Flowchart d'une option d'architecture-options (options.json validé contre son schéma)."""
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
    nodes = [{"id": c["id"], "label": c["label"] + (f" ({c['tech']})" if c.get("tech") else ""),
              "kind": c.get("role", "system")} for c in option["components"]]
    edges = [{"from": f["from"], "to": f["to"], **({"label": f["label"]} if f.get("label") else {}),
              **({"async": True} if f.get("style") == "async" else {})} for f in option.get("flows", [])]
    return {"title": f"Option {option['id']} : {option['name']}", "type": "flowchart", "direction": "LR",
            "nodes": nodes, "edges": edges}


def unknown(where: str, value: str, known, errors: list[str]) -> bool:
    if value in known:
        return False
    close = difflib.get_close_matches(value, list(known), n=1)
    errors.append(f"{where} : « {value} » inconnu" + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
    return True


def flowchart(spec: dict, errors: list[str], warnings: list[str]) -> tuple[list[str], dict]:
    nodes = {n["id"]: n for n in spec.get("nodes", [])}
    if len(nodes) != len(spec.get("nodes", [])):
        errors.append("nodes : identifiant en double")
    if len(nodes) > MAX_NODES:
        warnings.append(f"{len(nodes)} nœuds (au plus {MAX_NODES} pour rester lisible : faites deux schémas)")
    lines = [f"flowchart {spec.get('direction', 'LR')}"]
    grouped = set()
    for index, group in enumerate(spec.get("groups", [])):
        lines.append(f"  subgraph g{index + 1}[{label(group['label'])}]")
        for nid in group["nodes"]:
            if not unknown(f"groups/{index}/nodes", nid, nodes, errors):
                grouped.add(nid)
                lines.append("    " + node_line(nodes[nid]))
        lines.append("  end")
    lines += ["  " + node_line(n) for nid, n in nodes.items() if nid not in grouped]
    for index, edge in enumerate(spec.get("edges", [])):
        bad = [unknown(f"edges/{index}/{end}", edge[end], nodes, errors) for end in ("from", "to")]
        if any(bad):
            continue
        if not edge.get("label"):
            warnings.append(f"edges/{index} : lien {edge['from']} -> {edge['to']} sans verbe (label)")
        arrow = "-.->" if edge.get("async") else "-->"
        text = f"|{label(edge['label'])}|" if edge.get("label") else ""
        lines.append(f"  {safe_id(edge['from'])} {arrow}{text} {safe_id(edge['to'])}")
    used = sorted({n.get("kind", "system") for n in nodes.values()})
    lines += [f"  classDef {k} {CLASSDEFS[k]}" for k in used]
    for kind in used:
        members = [safe_id(i) for i, n in nodes.items() if n.get("kind", "system") == kind]
        lines.append(f"  class {','.join(members)} {kind}")
    return lines, {"nodes": len(nodes), "links": len(spec.get("edges", []))}


def node_line(node: dict) -> str:
    left, right = SHAPES[node.get("kind", "system")]
    return f"{safe_id(node['id'])}{left}{label(node['label'])}{right}"


def sequence(spec: dict, errors: list[str], warnings: list[str]) -> tuple[list[str], dict]:
    people = {p["id"]: p for p in spec.get("participants", [])}
    if len(people) != len(spec.get("participants", [])):
        errors.append("participants : identifiant en double")
    lines = ["sequenceDiagram", "  autonumber"]
    boxes: dict[str, list[dict]] = {}
    for p in people.values():
        boxes.setdefault(p.get("box", ""), []).append(p)
    for box, members in boxes.items():
        pad = "    " if box else "  "
        if box:
            lines.append(f"  box {box}")
        for p in members:
            kind = "actor" if p.get("actor") else "participant"
            lines.append(f"{pad}{kind} {safe_id(p['id'])} as {str(p['label']).replace(chr(10), ' ')}")
        if box:
            lines.append("  end")
    count = [0]

    def steps(items: list[dict], where: str, depth: int) -> None:
        pad = "  " * depth
        for index, step in enumerate(items):
            at = f"{where}/{index}"
            if "note" in step:
                over = [p for p in step.get("over", []) if not unknown(f"{at}/over", p, people, errors)]
                if over:
                    lines.append(f"{pad}Note over {','.join(safe_id(p) for p in over)}: {step['note']}")
                continue
            if "block" in step:
                for b, branch in enumerate(step["branches"]):
                    word = step["block"] if b == 0 else "else"
                    lines.append(f"{pad}{word} {branch.get('when', '')}".rstrip())
                    steps(branch["messages"], f"{at}/branches/{b}/messages", depth + 1)
                lines.append(f"{pad}end")
                continue
            bad = [unknown(f"{at}/{end}", step[end], people, errors) for end in ("from", "to")]
            if any(bad):
                continue
            count[0] += 1
            text = str(step.get("label", "")).replace("\n", " ").replace(";", ",")
            lines.append(f"{pad}{safe_id(step['from'])}{ARROWS[step.get('kind', 'call')]}{safe_id(step['to'])}: {text}")
    steps(spec.get("messages", []), "messages", 1)
    return lines, {"nodes": len(people), "links": count[0]}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description SCHEMA.json")
    parser.add_argument("--from-options", type=Path, help="options.json d'architecture-options, au lieu de SCHEMA.json")
    parser.add_argument("--option", help="identifiant de l'option, avec --from-options")
    parser.add_argument("--out", type=Path, help="fichier .md (bloc ```mermaid avec titre) ou .mmd "
                                                 "(défaut : <nom>.md à côté de l'entrée)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if bool(args.spec) == bool(args.from_options) or bool(args.from_options) != bool(args.option):
        parser.error("SCHEMA.json, ou --from-options options.json --option ID")
    source = args.spec or args.from_options
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(source), "output": None, "type": None, "nodes": 0, "links": 0,
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
    body, counts = (sequence if spec["type"] == "sequence" else flowchart)(spec, errors, warnings)
    report.update(counts, type=spec["type"])
    if not errors:
        stem = f"option-{args.option.lower()}" if args.from_options else source.name.removesuffix(".json")
        out = args.out or source.with_name(f"{stem}.md")
        # Titre en chaîne JSON : un « : » dans le titre ne casse pas l'en-tête YAML.
        head = ["---", f"title: {json.dumps(spec['title'], ensure_ascii=False)}", "---"]
        if out.suffix == ".mmd":
            text = "\n".join(head + body) + "\n"
        else:
            text = "\n".join([f"# {spec['title']}", "", "```mermaid", *head, *body, "```"]) + "\n"
        ai_mark.write_text(out, text)
        report["output"] = str(out)
        warnings.append(f"rendu à vérifier : uv run ../diagram-export/scripts/export.py {out.name} --check")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
