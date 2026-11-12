"""Documentation des workflows, tirée de leurs définitions JSON (skills/decision-log/workflows/).

Une page par workflow (docs/workflows/<nom>.md : à quoi il sert, ce qu'il demande au départ, schéma Mermaid
des étapes et de leurs dépendances, tableau des étapes, détail de chacune) et un index avec la carte des
workflows (point de départ, dossier validé repris par les workflows menés dans un sous-dossier). Générée par
build.py, contrôlée à jour par tests/run.py : la définition reste la seule source.
"""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "shared" / "scripts"))
import workflow_chart  # noqa: E402
from workflow_chart import node, requires, text  # noqa: E402,F401

WORKFLOWS = REPO / "skills" / "decision-log" / "workflows"
DOCS = REPO / "docs" / "workflows"
ENGINE = "architecture-workflow"
LEVELS = {"simple": "simple", "moyen": "moyen", "complexe": "complexe"}
# Point de départ d'un workflow : dossier parent lu par une étape, sinon dossier de sa première entrée.
STARTS = {"documents": "Documents du projet", "infra": "Code d'infrastructure", "code": "Code de l'application",
          "maquettes": "Maquettes d'écrans", "..": "Dossier validé"}
# Charte commune (shared/references/style.md) : système, externe, à créer, point de vigilance.
CLASSES = ["classDef moteur fill:#dbeafe,stroke:#1d4ed8,color:#1f2937",
           "classDef agent fill:#ffedd5,stroke:#c2410c,color:#1f2937",
           workflow_chart.OPTIONAL,
           "classDef depart fill:#f3f4f6,stroke:#6b7280,color:#1f2937"]
HEADER = ("<!-- Fichier généré par scripts/build.py depuis skills/decision-log/workflows/{name}.json :"
          " ne pas le modifier à la main. -->")


def definitions() -> list[dict]:
    return [json.loads(p.read_text(encoding="utf-8")) for p in sorted(WORKFLOWS.glob("*.json"))]


def cell(value) -> str:
    if isinstance(value, list):
        value = ", ".join(f"`{v}`" for v in value) if value else "aucun"
    return str(value).replace("|", "\\|").replace("\n", " ")


def waves(stages: list[dict]) -> list[list[str]]:
    """Étapes regroupées par vague : une vague ne dépend que des vagues d'avant."""
    depth: dict[str, int] = {}
    for i, stage in enumerate(stages):
        depth[stage["id"]] = 1 + max((depth[d] for d in requires(stages, i) if d in depth), default=-1)
    out: list[list[str]] = [[] for _ in range(max(depth.values(), default=-1) + 1)]
    for stage in stages:
        out[depth[stage["id"]]].append(stage["id"])
    return out


def start_of(definition: dict) -> str:
    """Point de départ : dossier validé si une étape lit le dossier parent, sinon la première entrée."""
    if any(i.startswith("../") for s in definition["stages"] for i in s.get("inputs", [])):
        return STARTS[".."]
    inputs = definition["stages"][0].get("inputs", [])
    first = (inputs[0] if inputs else "").split("/", 1)[0]
    return STARTS.get(first, "Demande")


def makes_dossier(definition: dict) -> bool:
    """Workflow dont le dossier validé (exigences et options) peut être repris par un workflow mené dans
    son sous-dossier."""
    made = {d for s in definition["stages"] for d in s.get("deliverables", [])}
    return {"exigences.json", "options.json"} <= made


def flowchart(definition: dict) -> str:
    stages = definition["stages"]
    classes = [(c.split(" ", 2)[1], c.split(" ", 2)[2], [s["id"] for s in stages if test(s)])
               for c, test in zip(CLASSES, (lambda s: "agent" not in s, lambda s: "agent" in s,
                                            lambda s: s.get("facultative")))]
    return workflow_chart.flowchart(stages, definition["title"], lambda s: s.get("agent", ENGINE), classes)


def stage_label(stages: list[dict], stage_id: str) -> str:
    index = next(i for i, s in enumerate(stages) if s["id"] == stage_id)
    return f"{index + 1}. {stages[index]['label']}"


def page(definition: dict) -> str:
    stages = definition["stages"]
    name = definition["name"]
    lines = [HEADER.format(name=name), "", f"# {definition['title']}", "",
             f"Workflow `{name}` : {len(stages)} étapes, dont {sum(1 for s in stages if s.get('facultative'))} "
             f"facultatives. Point de départ : {start_of(definition).lower()}. "
             "[Tous les workflows](README.md).", "", "## À quoi il sert", "", definition["description"], ""]
    if definition.get("ask"):
        lines += ["## Ce que le moteur demande au départ", ""] + [f"- {a[0].upper()}{a[1:]}" for a in definition["ask"]]
        lines.append("")
    lines += ["## Déroulé", "", flowchart(definition), "",
              "En bleu, les étapes menées par le moteur `architecture-workflow` ; en orange, celles qu'il confie à "
              "un agent spécialisé ; en tirets, les étapes facultatives (l'utilisateur peut les passer). "
              "Chaque étape s'arrête pour la revue de l'utilisateur avant la suite.", ""]
    parallel = [w for w in waves(stages) if len(w) > 1]
    if parallel:
        lines.append("Étapes prêtes en même temps, menées en parallèle :")
        lines += ["- " + ", ".join(stage_label(stages, s) for s in wave) for wave in parallel]
        lines.append("")
    lines += ["## Étapes", "", "| Étape | Niveau | Menée par | Skills | Livrables | Après |",
              "| --- | --- | --- | --- | --- | --- |"]
    for i, stage in enumerate(stages):
        after = ", ".join(stage_label(stages, d).split(".")[0] for d in requires(stages, i)) or "début"
        label = f"{i + 1}. {stage['label']}" + (" (facultative)" if stage.get("facultative") else "")
        lines.append(f"| {cell(label)} | {LEVELS.get(stage['level'], stage['level'])} | "
                     f"`{stage.get('agent', ENGINE)}` | {cell(stage.get('skills', []))} | "
                     f"{cell(stage.get('deliverables', []))} | {after} |")
    lines.append("")
    for i, stage in enumerate(stages):
        lines += [f"### {i + 1}. {stage['label']}", ""]
        if stage.get("inputs"):
            lines += [f"- **Entrées** : {cell(stage['inputs'])}"]
        lines += [f"- **Livrables** : {cell(stage.get('deliverables', []))}"]
        if stage.get("optional"):
            lines += [f"- **Livrables possibles** : {cell(stage['optional'])}"]
        for check in stage.get("checks", []):
            lines.append(f"- **Contrôle** : {cell(check)}")
        if stage.get("instructions"):
            lines += ["", cell(stage["instructions"])]
        lines.append("")
    if definition.get("memory"):
        lines += ["## Mémoire partagée", "",
                  "Fichiers que le moteur reporte dans le vault Obsidian, quand le workflow en a un :", ""]
        lines += [f"- {key} : `{value}`" for key, value in definition["memory"].items()]
        lines.append("")
    return "\n".join(lines)


def index(defs: list[dict]) -> str:
    lines = ["<!-- Fichier généré par scripts/build.py depuis skills/decision-log/workflows/ :"
             " ne pas le modifier à la main. -->", "", "# Workflows", "",
             "Un workflow est une définition JSON (`skills/decision-log/workflows/`) que suit le moteur "
             "`architecture-workflow` : des étapes à portes de revue, chacune avec ses skills, ses livrables, ses "
             "contrôles par script et, au besoin, un agent spécialisé. Chaque page ci-dessous est tirée de sa "
             "définition.", "", "## Carte", "", "```mermaid", "---", "title: Workflows et leur point de départ",
             "---", "flowchart LR"]
    starts = {}
    for d in defs:
        starts.setdefault(start_of(d), []).append(d)
    for i, label in enumerate(starts):
        lines.append(f'  d{i}(["{text(label)}"])')
    for d in defs:
        lines.append(f'  w_{d["name"].replace("-", "_")}["{text(d["name"])}"]')
    validated = list(starts).index("Dossier validé") if "Dossier validé" in starts else None
    for i, (label, group) in enumerate(starts.items()):
        for d in group:
            lines.append(f"  d{i} --> w_{d['name'].replace('-', '_')}")
    if validated is not None:
        for d in defs:
            if makes_dossier(d) and start_of(d) != "Dossier validé":
                lines.append(f"  w_{d['name'].replace('-', '_')} -.-> d{validated}")
    lines += [f"  {CLASSES[0]}", f"  {CLASSES[3]}",
              "  class " + ",".join(f"w_{d['name'].replace('-', '_')}" for d in defs) + " moteur",
              "  class " + ",".join(f"d{i}" for i in range(len(starts))) + " depart", "```", "",
              "En pointillés : les workflows dont le dossier validé (exigences et options) est repris ensuite par "
              "les workflows menés dans son sous-dossier ("
              + ", ".join(f"`{d['name']}`" for d in starts.get(STARTS[".."], [])) + ").", "", "## Liste", "", "| Workflow | Étapes | Point de départ |", "| --- | --- | --- |"]
    for d in defs:
        lines.append(f"| [{cell(d['title'])}]({d['name']}.md) (`{d['name']}`) | {len(d['stages'])} | "
                     f"{start_of(d)} |")
    return "\n".join(lines + [""])


def workflow_docs() -> dict[Path, str]:
    defs = definitions()
    files = {DOCS / "README.md": index(defs)}
    files.update({DOCS / f"{d['name']}.md": page(d) for d in defs})
    return files
