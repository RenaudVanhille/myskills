# /// script
# requires-python = ">=3.10"
# ///
"""Dessine un processus métier en couloirs (notation BPMN) à partir d'une description JSON.

Le modèle décrit les acteurs (`lanes`), les étapes (`steps` : début, tâche,
décision, attente, fin) et leur enchaînement (`flows`). Le script contrôle
le processus (étape inaccessible, impasse, décision sans libellé, référence
inconnue), le met en page (un couloir par acteur, de gauche à droite), écrit
le `.drawio` aux couleurs de la charte et sa fiche Markdown (déroulé,
passages de main, points de douleur), puis le vérifie comme check_drawio.py.

    uv run scripts/process_build.py PROCESSUS.json [--out PROCESSUS.drawio] [--export png|svg]
    uv run scripts/process_build.py --schema

Avec --export, le schéma est aussi exporté (skill diagram-export) dans le même
appel ; le rapport donne l'image dans `export`. Rien n'est écrit si le
processus a une erreur.
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from drawio_xml import edge, html, new_file, new_page, vertex, waypoints, write  # noqa: E402
from skill_paths import export_image, load_module  # noqa: E402
from spec_schema import print_schema, read_spec, schema_option  # noqa: E402

FONT = "html=1;whiteSpace=wrap;fontColor=#1f2937;"
# Petites formes : libellé dessous, coupé par le script (wrap) et non par la largeur de la forme.
BELOW = "html=1;fontColor=#1f2937;verticalLabelPosition=bottom;verticalAlign=top;labelBackgroundColor=#ffffff;"
EVENT = "shape=mxgraph.bpmn.event;perimeter=ellipsePerimeter;outlineConnect=0;aspect=fixed;" + BELOW + "fontSize=12;"
GATEWAY = ("shape=mxgraph.bpmn.gateway2;perimeter=rhombusPerimeter;outlineConnect=0;outline=none;symbol=none;"
           + BELOW + "fontSize=12;fillColor=#fef3c7;strokeColor=#b45309;")
# Type d'étape -> (style draw.io, largeur, hauteur, nom dans la légende et la fiche).
TYPES = {
    "start": (EVENT + "outline=standard;symbol=general;fillColor=#dcfce7;strokeColor=#15803d;", 40, 40, "Début"),
    "task": ("rounded=1;arcSize=18;" + FONT + "fontSize=13;fillColor=#dbeafe;strokeColor=#1d4ed8;", 150, 70,
             "Tâche"),
    "gateway": (GATEWAY + "gwType=exclusive;", 50, 50, "Décision (un seul chemin)"),
    "parallel": (GATEWAY + "gwType=parallel;", 50, 50, "En parallèle (tous les chemins)"),
    "event": (EVENT + "outline=catching;symbol=timer;fillColor=#f3e8ff;strokeColor=#7e22ce;", 40, 40,
              "Attente ou évènement"),
    "end": (EVENT + "outline=end;symbol=general;fillColor=#fee2e2;strokeColor=#b91c1c;", 40, 40, "Fin"),
}
PAIN = "fillColor=#fee2e2;strokeColor=#b91c1c;"
POOL = ("swimlane;horizontal=0;startSize=40;html=1;whiteSpace=wrap;fontSize=14;fontStyle=1;fontColor=#1f2937;"
        "collapsible=0;swimlaneFillColor=none;")
LANES = {"acteur": "fillColor=#f3f4f6;strokeColor=#6b7280;", "systeme": "fillColor=#dbeafe;strokeColor=#1d4ed8;",
         "externe": "fillColor=#f3f4f6;strokeColor=#6b7280;dashed=1;"}
FLOW = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#374151;fontColor=#1f2937;fontSize=12;"
        "labelBackgroundColor=#ffffff;endArrow=block;endFill=1;")
TITLE = "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;fontColor=#1f2937;"
HEADER, COL, ROW, PAD, TASK_W, TASK_H = 40, 210, 120, 30, 150, 70
SPLITS = ("gateway", "parallel")
MARGIN = 12  # distance au bord du couloir des flèches qui contournent des étapes
MAX_SIMPLE = 15
LABEL_WIDTH = 24


def wrap(text: str, width: int = LABEL_WIDTH) -> str:
    """Coupe un libellé en lignes d'au plus width caractères, sans couper les mots."""
    lines, line = [], ""
    for word in text.split():
        if line and len(line) + 1 + len(word) > width:
            lines.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    return "\n".join(lines + [line])


def count(n: int, one: str, many: str | None = None) -> str:
    return f"{n} {one if n < 2 else many or one + 's'}"


def near(value: str, choices) -> str:
    found = difflib.get_close_matches(value, list(choices), n=2, cutoff=0.6)
    return f" ; vouliez-vous « {' » ou « '.join(found)} » ?" if found else ""


def analyse(spec: dict, errors: list[str], warnings: list[str]) -> dict:
    """Contrôle le processus et calcule le rang (colonne) de chaque étape."""
    lanes = {}
    for index, lane in enumerate(spec["lanes"]):
        if lane["id"] in lanes:
            errors.append(f"lanes/{index}/id : « {lane['id']} » en double")
        lanes[lane["id"]] = lane
    steps = {}
    for index, step in enumerate(spec["steps"]):
        if step["id"] in steps:
            errors.append(f"steps/{index}/id : « {step['id']} » en double")
        if step["id"] in lanes:
            errors.append(f"steps/{index}/id : « {step['id']} » est déjà l'identifiant d'un couloir")
        if step["lane"] not in lanes:
            errors.append(f"steps/{index}/lane : couloir inconnu « {step['lane']} »{near(step['lane'], lanes)}")
        steps[step["id"]] = step
    after = {sid: [] for sid in steps}
    before = {sid: [] for sid in steps}
    seen = set()
    for index, flow in enumerate(spec["flows"]):
        missing = False
        for end in ("from", "to"):
            if flow[end] not in steps:
                errors.append(f"flows/{index}/{end} : étape inconnue « {flow[end]} »{near(flow[end], steps)}")
                missing = True
        if missing:
            continue
        if (flow["from"], flow["to"]) in seen:
            errors.append(f"flows/{index} : flux {flow['from']} -> {flow['to']} en double")
            continue
        seen.add((flow["from"], flow["to"]))
        after[flow["from"]].append(flow)
        before[flow["to"]].append(flow)
    if errors:
        return {}

    starts = [sid for sid, s in steps.items() if s["type"] == "start"]
    if not starts:
        errors.append("steps : aucun début (type start)")
    if not any(s["type"] == "end" for s in steps.values()):
        errors.append("steps : aucune fin (type end)")
    for sid, step in steps.items():
        kind, outs, ins = step["type"], after[sid], before[sid]
        if kind == "start" and ins:
            errors.append(f"étape {sid} : un début ne reçoit pas de flux ({ins[0]['from']} -> {sid})")
        if kind == "end" and outs:
            errors.append(f"étape {sid} : une fin n'a pas de suite ({sid} -> {outs[0]['to']})")
        if kind != "end" and not outs:
            errors.append(f"étape {sid} : impasse, aucune suite ; ajoutez un flux ou une fin (type end)")
        if kind in SPLITS and len(outs) < 2 and len(ins) < 2:
            errors.append(f"étape {sid} : une décision a au moins deux suites (ou réunit au moins deux flux)")
        if kind == "gateway" and len(outs) > 1:
            blank = [f["to"] for f in outs if not f.get("label")]
            if blank:
                errors.append(f"étape {sid} : décision, libellé manquant sur le flux vers {', '.join(blank)} "
                              "(oui, non, montant > 5 000 €...)")
        if kind in ("task", "event", "start") and len(outs) > 1:
            errors.append(f"étape {sid} : {len(outs)} suites sans décision ; passez par une étape gateway "
                          "(un seul chemin) ou parallel (tous)")

    # Rang : plus long chemin depuis les débuts, les retours en arrière (boucles) mis de côté.
    state, back, order = {}, set(), []

    def visit(sid: str) -> None:
        state[sid] = 1
        for flow in after[sid]:
            if state.get(flow["to"]) == 1:
                back.add((sid, flow["to"]))
            elif flow["to"] not in state:
                visit(flow["to"])
        state[sid] = 2
        order.append(sid)
    for sid in starts:
        if sid not in state:
            visit(sid)
    lost = [sid for sid in steps if sid not in state]
    if lost and starts:
        errors.append(f"étape(s) inaccessible(s) depuis un début : {', '.join(lost)}")
    rank = {sid: 0 for sid in steps}
    for sid in reversed(order):
        for flow in after[sid]:
            if (sid, flow["to"]) not in back:
                rank[flow["to"]] = max(rank[flow["to"]], rank[sid] + 1)
    # Une étape d'où aucune fin n'est atteignable : boucle sans sortie.
    reach = {sid for sid, s in steps.items() if s["type"] == "end"}
    grew = True
    while grew:
        grew = False
        for sid in steps:
            if sid not in reach and any(f["to"] in reach for f in after[sid]):
                reach.add(sid)
                grew = True
    stuck = [sid for sid in steps if sid not in reach and after[sid] and sid not in lost]
    if stuck:
        errors.append(f"boucle sans sortie, aucune fin atteignable depuis : {', '.join(stuck)}")

    used = {s["lane"] for s in steps.values()}
    for lane in lanes:
        if lane not in used:
            warnings.append(f"couloir {lane} sans étape : retirez-le ou placez-y ses étapes")
    if str(spec.get("audience", "")).startswith("non") and len(steps) > MAX_SIMPLE:
        warnings.append(f"{len(steps)} étapes pour un public non technique ({MAX_SIMPLE} au plus) : "
                        "regroupez des tâches ou découpez en sous-processus")
    handoffs = sum(1 for flows in after.values() for f in flows if steps[f["from"]]["lane"] != steps[f["to"]]["lane"])
    return {"lanes": lanes, "steps": steps, "after": after, "rank": rank, "back": back, "handoffs": handoffs}


def layout(spec: dict, model: dict) -> tuple[dict, dict, float]:
    """Position de chaque étape dans son couloir et hauteur de chaque couloir."""
    cells: dict[tuple[str, int], list[str]] = {}
    for step in spec["steps"]:
        cells.setdefault((step["lane"], model["rank"][step["id"]]), []).append(step["id"])
    rows = {lane: max([len(ids) for (name, _), ids in cells.items() if name == lane] or [1])
            for lane in model["lanes"]}
    heights = {lane: rows[lane] * ROW + 20 for lane in model["lanes"]}
    places = {}
    for (lane, rank), ids in cells.items():
        top = (heights[lane] - len(ids) * ROW) / 2
        for index, sid in enumerate(ids):
            _, w, h, _ = TYPES[model["steps"][sid]["type"]]
            places[sid] = (HEADER + PAD + rank * COL + (TASK_W - w) / 2, top + index * ROW + (ROW - h) / 2, w, h)
    width = HEADER + 2 * PAD + (max(model["rank"].values(), default=0) + 1) * COL - (COL - TASK_W)
    return places, heights, width


def draw(spec: dict, model: dict):
    diagram, root = new_page("p-processus", "Processus")
    places, heights, width = layout(spec, model)
    vertex(root, "title", html(spec["title"]), TITLE, 0, 0, max(400, len(spec["title"]) * 12), 30)
    y = 50
    tops = {}
    for lane_id, lane in model["lanes"].items():
        tops[lane_id] = y
        vertex(root, lane_id, html(lane["name"]), POOL + LANES[lane.get("kind", "acteur")], 0, y, width,
               heights[lane_id])
        y += heights[lane_id]
    kinds = []
    for step in spec["steps"]:
        style, _, _, _ = TYPES[step["type"]]
        if step.get("pain"):
            style = style.replace("fillColor=#dbeafe;strokeColor=#1d4ed8;", PAIN)
        label = step["name"] + (f"\n({step['system']})" if step.get("system") and step["type"] == "task" else "")
        if step["type"] != "task":
            label = wrap(label)
        vertex(root, step["id"], html(label), style, *places[step["id"]], parent=step["lane"])
        if step["type"] not in kinds:
            kinds.append(step["type"])
    order = list(model["lanes"])
    top, bottom, left = "X=0.5;{0}Y=0;", "X=0.5;{0}Y=1;", "X=0;{0}Y=0.5;"

    def side(where: str, end: str) -> str:
        return end + where.format(end)
    for flow in spec["flows"]:
        source, target = model["steps"][flow["from"]], model["steps"][flow["to"]]
        drop = order.index(target["lane"]) - order.index(source["lane"])
        gap = model["rank"][flow["to"]] - model["rank"][flow["from"]]
        style = FLOW
        (sx, _, sw, _), (tx, _, tw, _) = places[flow["from"]], places[flow["to"]]
        detour = None
        if (flow["from"], flow["to"]) in model["back"]:
            # Retour en arrière, en tirets : par le dessous dans un même couloir ou vers un couloir du dessus,
            # par le dessus vers un couloir du dessous, sans traverser les étapes.
            where = top if drop > 0 else bottom
            style += "dashed=1;" + side(where, "exit") + side(where, "entry")
            detour = tops[source["lane"]] + (MARGIN if drop > 0 else heights[source["lane"]] - MARGIN)
        elif drop and source["type"] in SPLITS:
            # Une décision part vers un autre couloir par sa pointe, et arrive par la gauche.
            style += side(top if drop < 0 else bottom, "exit") + (side(left, "entry") if gap > 0 else "")
        elif not drop and gap > 1:
            # Saut par-dessus des étapes du même couloir : par le dessus (les libellés sont dessous).
            style += side(top, "exit") + side(top, "entry")
            detour = tops[source["lane"]] + MARGIN
        _, geometry = edge(root, f"{flow['from']}--{flow['to']}", html(flow.get("label", "")), style,
                           flow["from"], flow["to"])
        if detour is not None:
            # Trajet fixé dans la marge du couloir : le même à l'écran et pour le contrôle de lisibilité.
            waypoints(geometry, [(sx + sw / 2, detour), (tx + tw / 2, detour)])
        if flow.get("label"):
            geometry.set("x", "-0.6")
    if spec.get("legend", True):
        beside = "labelPosition=right;verticalLabelPosition=middle;align=left;verticalAlign=middle;spacingLeft=8;"
        vertex(root, "legend-title", "Légende", "text;html=1;fontStyle=1;align=left;fontColor=#1f2937;fontSize=14;",
               0, y + 30, 120, 20)
        entries = [(f"legend-{kind}", TYPES[kind][3], TYPES[kind][0], 24 if kind != "task" else 36)
                   for kind in TYPES if kind in kinds]
        if any(step.get("pain") for step in spec["steps"]):
            entries.append(("legend-pain", "Point de douleur", "rounded=1;html=1;fontColor=#1f2937;" + PAIN, 36))
        if model["back"]:
            entries.append(("legend-back", "Retour en arrière", "shape=line;dashed=1;html=1;strokeColor=#374151;"
                            "fontColor=#1f2937;", 36))
        x = 0
        for cid, label, style, w in entries:
            style = style.replace("fontSize=13;", "").replace("fontSize=12;", "").replace("whiteSpace=wrap;", "")
            for part in BELOW.split(";")[2:]:
                style = style.replace(part + ";", "") if part else style
            vertex(root, cid, label, style + beside + "fontSize=12;", x, y + 60, w, 24)
            x += w + 30 + len(label) * 7.5
    return diagram


def card(spec: dict, model: dict) -> str:
    """Fiche Markdown du processus : synthèse, acteurs, déroulé, points de douleur."""
    steps, lanes, after = model["steps"], model["lanes"], model["after"]
    ordered = sorted(spec["steps"], key=lambda s: (model["rank"][s["id"]], list(lanes).index(s["lane"])))
    number = {step["id"]: index for index, step in enumerate(ordered, 1)}
    decisions = sum(1 for s in ordered if s["type"] in SPLITS and len(after[s["id"]]) > 1)
    pains = [s for s in ordered if s.get("pain")]
    tasks = sum(1 for s in ordered if s["type"] == "task")
    lines = [f"# {spec['title']}", "",
             f"{count(tasks, 'tâche')}, {count(len(lanes), 'acteur')}, {count(decisions, 'décision')}, "
             f"{count(model['handoffs'], 'passage de main', 'passages de main')}, "
             f"{count(len(pains), 'point de douleur', 'points de douleur')}.", "",
             "## Acteurs", "", "| Acteur | Tâches |", "| --- | --- |"]
    for lane_id, lane in lanes.items():
        own = sum(1 for s in ordered if s["lane"] == lane_id and s["type"] == "task")
        lines.append(f"| {lane['name']} | {own} |")
    lines += ["", "## Déroulé", "", "| N° | Étape | Acteur | Nature | Outil | Suite |",
              "| --- | --- | --- | --- | --- | --- |"]
    for step in ordered:
        nexts = " ; ".join((f"{f['label']} : " if f.get("label") else "") + f"{number[f['to']]}. {steps[f['to']]['name']}"
                           for f in after[step["id"]]) or "-"
        cells = [str(number[step["id"]]), step["name"], lanes[step["lane"]]["name"], TYPES[step["type"]][3],
                 step.get("system") or "-", nexts]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    if pains:
        lines += ["", "## Points de douleur", ""]
        lines += [f"- **{number[s['id']]}. {s['name']}** ({lanes[s['lane']]['name']}) : {s['pain']}" for s in pains]
    notes = [s for s in ordered if s.get("note")]
    if notes:
        lines += ["", "## Précisions", ""] + [f"- **{number[s['id']]}. {s['name']}** : {s['note']}" for s in notes]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description JSON du processus")
    parser.add_argument("--out", type=Path, help="fichier .drawio (défaut : même nom)")
    parser.add_argument("--export", choices=["png", "svg"],
                        help="exporte aussi l'image (skill diagram-export) : construire et rendre en un appel")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    spec, invalid = read_spec(args.spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    errors, warnings = [], []
    report = {"input": str(args.spec), "output": None, "markdown": None, "lanes": len(spec["lanes"]),
              "steps": len(spec["steps"]), "flows": len(spec["flows"]), "decisions": 0, "handoffs": 0, "pains": 0,
              "loops": 0, "errors": errors, "warnings": warnings}
    model = analyse(spec, errors, warnings)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report.update(decisions=sum(1 for s in spec["steps"] if s["type"] in SPLITS and len(model["after"][s["id"]]) > 1),
                  handoffs=model["handoffs"], pains=sum(1 for s in spec["steps"] if s.get("pain")),
                  loops=len(model["back"]))
    out = args.out or args.spec.with_name(args.spec.name.removesuffix(".json") + ".drawio")
    mxfile = new_file()
    mxfile.append(draw(spec, model))
    out.parent.mkdir(parents=True, exist_ok=True)
    write(mxfile, out)
    note = out.with_name(out.name.removesuffix(".drawio") + ".processus.md")
    note.write_text(card(spec, model), encoding="utf-8")
    report.update(output=str(out), markdown=str(note))
    checker = load_module("drawio-diagram", "check_drawio.py")
    if checker:
        checked = checker.check(out)
        errors += checked["errors"]
        warnings += checked["warnings"]
        report["review_image"] = checked["review_image"]
    else:
        warnings.append("skill drawio-diagram absent : .drawio non vérifié (check_drawio.py)")
    if args.export and not errors:
        report["export"], failed = export_image(out, args.export)
        errors += failed
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
