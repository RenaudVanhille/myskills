"""Schéma Mermaid des étapes d'un workflow, tiré de sa définition JSON.

Même tracé pour la documentation des workflows (scripts/workflow_docs.py : qui mène chaque étape) et pour
le journal d'un workflow en cours (journal.py, note d'index du vault : avancement de chaque étape). Une
étape facultative a une bordure en tirets ; une flèche relie une étape à celles dont elle dépend (`after`,
sinon l'étape précédente).
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
LEGEND = ("Bordure en tirets : étape facultative. Gris : à faire ; bleu : en cours ; orange : réalisée, "
          "en revue ; vert : validée ; rouge : à reprendre ; blanc : sautée.")


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


def flowchart(stages: list[dict], title: str, detail, classes: list[tuple[str, str, list[str]]]) -> str:
    """Bloc Mermaid : un nœud par étape (numéro, libellé, `detail(stage)` en petit), ses dépendances, puis
    les classes (nom, style, identifiants des étapes)."""
    # Au-delà de 10 étapes, de haut en bas : un schéma trop large devient illisible une fois réduit.
    lines = ["```mermaid", "---", "title: " + json.dumps(title, ensure_ascii=False), "---",
             "flowchart " + ("TD" if len(stages) > 10 else "LR")]
    for i, stage in enumerate(stages, 1):
        label = text(stage.get("label") or stage["id"])
        lines.append(f'  {node(stage["id"])}["{i}. {label}<br/><small>{text(detail(stage))}</small>"]')
    for i, stage in enumerate(stages):
        lines += [f"  {node(need)} --> {node(stage['id'])}" for need in requires(stages, i)]
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
        return f"{kind} · {PROGRESS_LABELS[status[stage['id']]]}" + (f" · {cause}" if cause else "")

    classes = [(name.replace("-", "_"), style, [s["id"] for s in stages if status[s["id"]] == name])
               for name, style in PROGRESS.items()]
    classes.append(("facultative", OPTIONAL.split(" ", 2)[2], [s["id"] for s in stages if s.get("facultative")]))
    return [flowchart(stages, title, detail, classes), "", LEGEND]
