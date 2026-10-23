"""Fonctions communes à build.py et install.py : lecture des agents sources
(src/agents/) et rendu au format de chaque outil."""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
AGENTS_SRC = REPO / "src" / "agents"


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
    lines = ["---"]
    if flavor == "claude":
        lines += [f"name: {name}", f"description: {desc}",
                  "tools: Read, Write, Edit, Bash, Skill, Agent"]
    elif flavor == "copilot":
        lines += [f"name: {name}", f"description: {desc}",
                  "tools: ['read', 'edit', 'execute', 'agent']"]
    elif flavor == "opencode":
        # Pas d'accès web ; le shell n'accepte que les commandes listées.
        lines += [f"description: {desc}", "mode: primary", "permission:",
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
    lines.append("---")
    return "\n".join(lines) + "\n" + body


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
