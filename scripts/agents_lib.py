"""Fonctions communes à build.py et install.py : lecture des agents sources
(src/agents/) et rendu au format de chaque outil.

Le modèle de chaque agent et la consigne « niveaux et modèles » (ligne
`{{niveaux}}` de l'agent source) viennent du niveau de son contrat et de
shared/models.json : changer un modèle se fait là, pour tous les agents."""

import json
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_SRC = REPO / "src" / "agents"
MODELS = REPO / "shared" / "models.json"
LEVELS = ("simple", "moyen", "complexe")
MARKER = "{{niveaux}}"
# Ligne d'un agent source remplacée par la façon de lancer un sous-agent dans chaque outil (agent orientation).
DELEGATION = "{{delegation}}"


# Modèles donnés à l'installation (install.py --models), par outil puis par niveau : priment sur shared/models.json.
OVERRIDES: dict[str, dict[str, str | list[str] | None]] = {}


def models() -> dict:
    return json.loads(MODELS.read_text(encoding="utf-8"))["levels"]


def agent_level(name: str) -> str:
    """Niveau par défaut de l'agent, dans son contrat."""
    contract = json.loads((AGENTS_SRC / f"{name}.contract.json").read_text(encoding="utf-8"))
    return contract["level"]


def model_for(level: str, flavor: str) -> str | list[str] | None:
    """Modèle du niveau pour l'outil : un nom, une liste de replis dans l'ordre, ou None (modèle de la session)."""
    if level in OVERRIDES.get(flavor, {}):
        return OVERRIDES[flavor][level]
    return models()[level]["models"].get(flavor)


def model_name(model: str | list[str] | None) -> str | None:
    return model[0] if isinstance(model, list) else model


def model_yaml(model: str | list[str]) -> str:
    return "[" + ", ".join(f"'{m}'" for m in model) + "]" if isinstance(model, list) else model


def levels_text(level: str, flavor: str) -> str:
    """Consigne commune des niveaux, avec les modèles de l'outil (shared/models.json)."""
    names = {lvl: model_name(model_for(lvl, flavor)) for lvl in LEVELS}
    if all(names.values()):
        choice = ("avec le modèle du niveau du lot : "
                  + ", ".join(f"{lvl} `{names[lvl]}`" for lvl in LEVELS) + ".")
    else:
        choice = "l'outil lui donne le modèle de la session (ou son mode automatique)."
    return "\n".join([
        "Pour chaque action, commence au niveau le plus bas qui convient et monte",
        "d'un niveau si elle échoue :", "",
        "- **simple** : exécute directement, sans réflexion approfondie.",
        "- **moyen** : traite l'action toi-même, normalement.",
        "- **complexe** : prends le temps de raisonner et de vérifier.", "",
        f"Ton niveau est **{level}**. Un sous-agent repart de zéro (instructions,",
        "outils, relecture des fichiers) : il coûte plus qu'une commande lancée",
        "toi-même. Ne lui confie qu'un lot (au moins 5 fichiers à traiter de la",
        "même façon, plusieurs pages à transcrire par la vision) ou une étape",
        f"entière d'un autre niveau que le tien ; {choice}", "",
        "Un skill s'ouvre par l'outil de skill de ton outil, qui donne son dossier :",
        "ses scripts sont dans son `scripts/`, lancés par ce chemin. Ne les cherche",
        "pas sur le disque (`find`, `which`) et ne lis pas leur code pour deviner un",
        "format : `--schema` le donne. Donne à un sous-agent les chemins des scripts",
        "dont il a besoin.", "",
        "Écris ce chemin en entier dans chaque commande, entre guillemets et avec des",
        "`/` (`uv run \"C:/.../scripts/journal.py\" start ...`) : chaque appel repart",
        "d'un shell neuf, une variable ou une fonction d'un appel précédent y est",
        "vide. Lis le rapport JSON tel quel, sans tube vers un autre programme : le",
        "tube masque le code de sortie et l'erreur du script."])


def delegation_text(flavor: str) -> str:
    """Comment lancer soi-même l'agent choisi, avec le modèle du niveau recommandé, dans l'outil cible.
    Sources : docs Claude Code (sub-agents), VS Code (custom agents, agents/runSubagent), OpenCode (agents,
    mode all), Kiro (custom-agents/subagents), Hermes (delegation), vérifiées le 2026-11-16."""
    names = {lvl: model_name(model_for(lvl, flavor)) for lvl in LEVELS}
    table = ", ".join(f"{lvl} `{names[lvl]}`" for lvl in LEVELS) if all(names.values()) else None
    own = (f"Il prend le modèle de son niveau, écrit dans son fichier ({table})." if table else
           "Il prend le modèle écrit dans son fichier (`install.py --models`), sinon celui de la session.")
    if flavor == "claude":
        return ("Lance-le avec l'outil `Agent` : `subagent_type` `myskills:<agent>` (`<agent>` seul s'il est "
                "installé hors plugin), `model` celui du niveau recommandé"
                + (f" ({table})" if table else "") + ", et pour consigne le dossier de travail et le "
                "message de `passage.json`.")
    if flavor == "copilot":
        return ("Lance-le avec l'outil `agent` (sous-agent nommé `<agent>` ; `task` dans Copilot CLI), avec "
                "pour consigne le dossier de travail et le message de `passage.json`. " + own)
    if flavor == "opencode":
        return ("Lance-le avec l'outil `task` (`subagent` en V2), agent `<agent>`, avec pour consigne le dossier "
                "de travail et le message de `passage.json`. " + own)
    if flavor == "kiro":
        return ("Lance-le avec l'outil `subagent` en nommant l'agent `<agent>`, avec pour consigne le dossier "
                "de travail et le message de `passage.json`. " + own)
    if flavor == "hermes":
        return ("Lance-le avec l'outil `delegate_task` : `goal` « charge le skill <agent> et traite le message "
                "de passage », `context` le dossier de travail et le message de `passage.json`. Hermes ne choisit "
                "pas de modèle par appel : le sous-agent prend `delegation.model` de sa configuration.")
    raise ValueError(f"Format inconnu : {flavor}")


def parse_agent(path: Path) -> tuple[dict[str, str], str]:
    """Renvoie (frontmatter, corps) d'un fichier agent source."""
    text = path.read_text(encoding="utf-8")
    _, head, body = text.split("---\n", 2)
    meta = {}
    for line in head.splitlines():
        key, sep, value = line.partition(": ")
        if sep:
            meta[key] = value
    return meta, body


def split_list(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def source_agents() -> list[Path]:
    return sorted(AGENTS_SRC.glob("*.md"))


def render_agent(path: Path, flavor: str, skills_dir: str = ".kiro/skills") -> str:
    """Rend l'agent source au format claude, copilot, opencode, kiro ou
    hermes (Hermes n'a pas d'agents : l'agent devient un skill). Pour Kiro,
    skills_dir est le dossier des skills installés (.kiro/skills en projet,
    ~/.kiro/skills en global)."""
    meta, body = parse_agent(path)
    name, desc = meta["name"], meta["description"]
    level = agent_level(name)
    body = body.replace(MARKER, levels_text(level, flavor)).replace(DELEGATION, delegation_text(flavor))
    model = model_for(level, flavor)
    lines = ["---"]
    if flavor == "claude":
        lines += [f"name: {name}", f"description: {desc}",
                  "tools: Read, Write, Edit, Bash, Skill, Agent"]
    elif flavor == "copilot":
        lines += [f"name: {name}", f"description: {desc}",
                  "tools: ['read', 'edit', 'execute', 'agent']"]
    elif flavor == "opencode":
        # Pas d'accès web ; le shell n'accepte que les commandes listées.
        # all : agent principal, et sous-agent que l'agent orientation peut lancer (outil task).
        lines += [f"description: {desc}", "mode: all", "permission:",
                  "  webfetch: deny", "  websearch: deny", "  codesearch: deny",
                  "  bash:", '    "*": deny']
        lines += [f'    "{command}": allow' for command in split_list(meta.get("commands", ""))]
    elif flavor == "kiro":
        # Référence des agents Kiro (https://kiro.dev/docs/custom-agents/configuration-reference/) :
        # skill:// prend le chemin du SKILL.md ; pas d'accès web ; les commandes listées
        # passent sans confirmation (permissions.rules).
        lines += [f"name: {name}", f"description: {desc}",
                  'tools: ["read", "write", "shell", "subagent"]',
                  'excludedTools: ["web"]', "resources:"]
        lines += [f"  - skill://{skills_dir}/{skill}/SKILL.md" for skill in split_list(meta.get("skills", ""))]
        lines += ["permissions:", "  rules:", "    - capability: shell", "      match:"]
        lines += [f'        - "{command}"' for command in split_list(meta.get("commands", ""))]
        lines += ["      effect: allow"]
    elif flavor == "hermes":
        lines += [f"name: {name}", f"description: {desc}"]
    else:
        raise ValueError(f"Format inconnu : {flavor}")
    if model and flavor != "hermes":
        # Liste de replis : Copilot la lit telle quelle ; les autres outils prennent le premier modèle.
        lines.append(f"model: {model_yaml(model) if flavor == 'copilot' else model_name(model)}")
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
