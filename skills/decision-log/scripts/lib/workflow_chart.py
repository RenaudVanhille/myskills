"""Schéma Mermaid des étapes d'un workflow, tiré de sa définition JSON.

Même tracé pour la documentation des workflows (scripts/workflow_docs.py : qui mène chaque étape) et pour
le journal d'un workflow en cours (journal.py, note d'index du vault : avancement de chaque étape). Une
étape facultative a une bordure en tirets ; une flèche relie une étape à celles dont elle dépend (`after`,
sinon l'étape précédente). Les étapes qui ont une `phase` sont rangées dans une zone par phase, dans l'ordre de
PHASES.
"""

import json

# Bordure en tirets : étape facultative.
OPTIONAL = "classDef facultative stroke-dasharray:5 5"
# Avancement, couleurs de la charte commune (shared/references/style.md).
PROGRESS = {"a-faire": "fill:#f3f4f6,stroke:#6b7280,color:#1f2937",
            "en-cours": "fill:#dbeafe,stroke:#1d4ed8,color:#1f2937,stroke-width:3px",
            "en-revue": "fill:#ffedd5,stroke:#c2410c,color:#1f2937",
            "validee": "fill:#dcfce7,stroke:#15803d,color:#1f2937",
            "a-reprendre": "fill:#fee2e2,stroke:#b91c1c,color:#1f2937",
            "sautee": "fill:#ffffff,stroke:#d1d5db,color:#6b7280"}
PROGRESS_LABELS = {"a-faire": "à faire", "en-cours": "en cours", "en-revue": "réalisée, en revue",
                   "validee": "validée", "a-reprendre": "à reprendre", "sautee": "sautée"}
# Zones du schéma, dans l'ordre du workflow : identifiant, libellé, fond.
PHASES = [("lecture", "Lecture du dossier", "#f8fafc"), ("cadrage", "Cadrage", "#f0f9ff"),
          ("solutioning", "Solutioning", "#f5f3ff"), ("chiffrage", "Chiffrage", "#fefce8"),
          ("restitution", "Restitution", "#f0fdf4")]
PHASE_RANK = {pid: rank for rank, (pid, _, _) in enumerate(PHASES)}
LEGEND = ("Bordure en tirets : étape facultative. Gris : à faire (à décider pour une facultative) ; bleu : en "
          "cours ; orange : réalisée, en revue ; vert : validée ; rouge : à reprendre ; blanc : sautée.")


def node(stage_id: str) -> str:
    return "s_" + stage_id.replace("-", "_")


def text(value: str) -> str:
    """Libellé Mermaid entre guillemets."""
    return value.replace('"', "#quot;")


def requires(stages: list[dict], index: int) -> list[str]:
    """Étapes dont dépend une étape : son champ `after`, sinon la précédente (comme journal.py)."""
    stage = stages[index]
    if "after" in stage:
        return list(stage["after"])
    return [stages[index - 1]["id"]] if index else []


def phase_errors(stages: list[dict]) -> list[str]:
    """Zones incohérentes : phase sur certaines étapes seulement, ou dépendance vers une zone placée après."""
    if not any(s.get("phase") for s in stages):
        return []
    errors = [f"étape {s['id']} sans phase alors que d'autres en ont une" for s in stages if not s.get("phase")]
    phase = {s["id"]: s.get("phase") for s in stages}
    for i, stage in enumerate(stages):
        for need in requires(stages, i):
            if phase.get(need) in PHASE_RANK and stage.get("phase") in PHASE_RANK \
                    and PHASE_RANK[phase[need]] > PHASE_RANK[stage["phase"]]:
                errors.append(f"étape {stage['id']} ({stage['phase']}) dépend de {need}, d'une zone placée après "
                              f"({phase[need]}) : zones dans l'ordre {', '.join(p for p, _, _ in PHASES)}")
    return errors


def flowchart(stages: list[dict], title: str, detail, classes: list[tuple[str, str, list[str]]]) -> str:
    """Bloc Mermaid : un nœud par étape (numéro, libellé, `detail(stage)` en petit), rangé dans la zone de sa phase
    s'il en a une, ses dépendances, puis les classes (nom, style, identifiants des étapes)."""
    # Au-delà de 10 étapes, de haut en bas : un schéma trop large devient illisible une fois réduit.
    lines = ["```mermaid", "---", "title: " + json.dumps(title, ensure_ascii=False), "---",
             "flowchart " + ("TD" if len(stages) > 10 else "LR")]
    number = {s["id"]: i for i, s in enumerate(stages, 1)}

    def box(stage: dict, indent: str = "  ") -> str:
        label = text(stage.get("label") or stage["id"])
        return f'{indent}{node(stage["id"])}["{number[stage["id"]]}. {label}<br/><small>{text(detail(stage))}</small>"]'

    zones = [(pid, name, fill, [s for s in stages if s.get("phase") == pid]) for pid, name, fill in PHASES]
    zones = [z for z in zones if z[3]]
    for pid, name, fill, members in zones:
        lines += [f'  subgraph z_{pid}["{name}"]'] + [box(s, "    ") for s in members] + ["  end",
                  f"  style z_{pid} fill:{fill},stroke:#94a3b8,color:#0f172a"]
    lines += [box(s) for s in stages if s.get("phase") not in PHASE_RANK]
    for i, stage in enumerate(stages):
        lines += [f"  {node(need)} --> {node(stage['id'])}" for need in requires(stages, i)]
    # Un lien invisible entre deux zones voisines les garde dans l'ordre sans empêcher les flèches de traverser.
    lines += [f"  {node(a[3][-1]['id'])} ~~~ {node(b[3][0]['id'])}" for a, b in zip(zones, zones[1:])]
    lines += [f"  classDef {name} {style}" for name, style, _ in classes]
    lines += [f"  class {','.join(node(i) for i in ids)} {name}" for name, _, ids in classes if ids]
    return "\n".join(lines + ["```"])


def causes(state: dict) -> dict[str, str]:
    """Pourquoi chaque étape à reprendre l'est, d'après sa dernière entrée de retour ou d'invalidation du journal :
    retour de l'utilisateur sur l'étape, ou entrée modifiée par la nouvelle validation d'une étape amont."""
    entries = {e["id"]: e for e in state.get("entries", [])}
    found = {}
    for stage in state.get("stages", []):
        if stage.get("status") != "a-reprendre":
            continue
        last = next((e for e in reversed(state.get("entries", []))
                     if e.get("stage") == stage["id"] and e.get("kind") in ("retour", "invalidation")), None)
        if last is None:
            continue
        if last["kind"] == "retour":
            found[stage["id"]] = f"retour {last['id']}"
            continue
        origin = entries.get((last.get("refs") or [""])[0], {})
        found[stage["id"]] = (f"entrée modifiée : {origin['stage']}" if origin.get("kind") == "validation"
                              else f"après le retour sur {origin['stage']}" if origin.get("stage") else "invalidée")
    return found


def progress_chart(stages: list[dict], status: dict[str, str], title: str,
                   why: dict[str, str] | None = None) -> list[str]:
    """Lignes Markdown du schéma d'avancement : chaque étape obligatoire ou facultative, avec son statut et, pour
    une étape à reprendre, sa cause (`why`, voir causes)."""
    def detail(stage: dict) -> str:
        kind = "facultative" if stage.get("facultative") else "obligatoire"
        cause = (why or {}).get(stage["id"])
        shown = "à décider" if stage.get("facultative") and status[stage["id"]] == "a-faire" \
            else PROGRESS_LABELS[status[stage["id"]]]
        return f"{kind} · {shown}" + (f" · {cause}" if cause else "")

    classes = [(name.replace("-", "_"), style, [s["id"] for s in stages if status[s["id"]] == name])
               for name, style in PROGRESS.items()]
    classes.append(("facultative", OPTIONAL.split(" ", 2)[2], [s["id"] for s in stages if s.get("facultative")]))
    return [flowchart(stages, title, detail, classes), "", LEGEND]


def label_of(state: dict, stage_id: str) -> str:
    """Libellé d'une étape (sa définition), sinon son identifiant."""
    found = next((s for s in (state.get("definition") or {}).get("stages", []) if s["id"] == stage_id), {})
    return found.get("label") or stage_id


def optional(state: dict, stage_id: str) -> bool:
    return any(s["id"] == stage_id and s.get("facultative") for s in (state.get("definition") or {}).get("stages", []))


def shown_status(state: dict, stage: dict) -> str:
    """Statut lisible : une étape facultative pas encore choisie est « à décider », pas « à faire »."""
    if stage["status"] == "a-faire" and optional(state, stage["id"]):
        return "à décider"
    return PROGRESS_LABELS[stage["status"]].replace("réalisée, ", "")


def next_steps(state: dict) -> list[dict]:
    """Ce qui fait avancer le workflow maintenant, dans l'ordre des étapes : qui (« vous » ou « agent »), l'étape et
    une phrase courte. Une étape ne compte que si toutes celles dont elle dépend sont validées ou sautées."""
    definitions = {d["id"]: d for d in (state.get("definition") or {}).get("stages", [])}
    stages = [{**definitions.get(s["id"], {}), "id": s["id"]} for s in state.get("stages", [])]
    status = {s["id"]: s["status"] for s in state.get("stages", [])}
    needs = {s["id"]: requires(stages, i) for i, s in enumerate(stages)}

    def free(stage_id: str, seen: frozenset = frozenset()) -> bool:
        return all(status.get(n) in ("validee", "sautee") and n not in seen and free(n, seen | {stage_id})
                   for n in needs.get(stage_id, []))

    why = causes(state)
    steps = []
    for stage in state.get("stages", []):
        name, current = stage["id"], stage["status"]
        label = f"« {label_of(state, name)} »"
        if current == "en-revue":
            steps.append({"who": "vous", "stage": name, "text": f"relire et valider {label}"})
        elif current == "en-cours":
            steps.append({"who": "agent", "stage": name, "text": f"produire {label}"})
        elif current in ("a-faire", "a-reprendre") and free(name):
            if current == "a-reprendre":
                cause = f" ({why[name]})" if name in why else ""
                steps.append({"who": "agent", "stage": name, "text": f"reprendre {label}{cause}"})
            elif optional(state, name):
                steps.append({"who": "vous", "stage": name, "text": f"dire si vous voulez l'étape facultative {label}"})
            else:
                steps.append({"who": "agent", "stage": name, "text": f"démarrer {label}"})
    entries = state.get("entries", [])
    answered = {r for e in entries if e.get("kind") == "reponse" for r in e.get("refs", [])}
    waiting = sum(1 for e in entries if e.get("kind") == "question" and e["id"] not in answered)
    if waiting:
        steps.append({"who": "vous", "stage": None, "text": "répondre à " + (
            "la question ouverte" if waiting == 1 else f"{waiting} questions ouvertes")})
    return steps


def steps_lines(steps: list[dict], link=None) -> list[str]:
    """Liste Markdown des prochaines étapes, celles de l'utilisateur d'abord ; `link(step)` peut remplacer le
    texte d'une étape (note de revue, fichiers soumis)."""
    if not steps:
        return ["- Workflow terminé : toutes les étapes sont validées ou sautées."]
    ordered = [s for s in steps if s["who"] == "vous"] + [s for s in steps if s["who"] != "vous"]
    return [f"- **{'À vous' if s['who'] == 'vous' else 'Agent'}** : {(link(s) if link else None) or s['text']}"
            for s in ordered]
