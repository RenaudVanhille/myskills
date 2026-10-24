# /// script
# requires-python = ">=3.10"
# ///
"""Régénère les fichiers du plugin à partir des sources (src/agents/, shared/).

À lancer après chaque modification d'un agent ou de la charte, puis committer
le résultat : les outils installent le plugin depuis le dépôt.

    agents/*.md                           agents Claude Code
    com.github.copilot/agents/*.agent.md  agents GitHub Copilot
    skills/*/references/style.md          charte : règles communes + section du format (shared/targets.txt)
    skills/*/scripts/lib/spec_schema.py   validateur des descriptions JSON (shared/scripts/), si un script a un `input`
    skills/*/scripts/lib/local_tools.py   emplacements des outils locaux (shared/scripts/), skills de LIB_USERS
    skills/*/scripts/lib/skill_paths.py   accès aux scripts des autres skills, si le contrat a un `requires`
    skills/*/contract.json : input.schema  copie du schéma du script nommé dans input.same_as
    shared/schemas/*.schema.json          liste des agents permis (enum), depuis src/agents/*.contract.json
    agents : champ model                  depuis le niveau du contrat et shared/models.json
    skills/drawio-diagram/scripts/lib/charter.json  couleurs de la charte (shared/references/style.md)
    sections « Contrat »                  SKILL.md et src/agents/*.md, depuis les contract.json
    CATALOG.md, catalog.json              catalogue des agents et des skills
    .claude-plugin/*.json                 manifestes Claude Code, depuis plugin.json (version comprise)

Usage : uv run scripts/build.py   (ou : python scripts/build.py)
"""

import re
import shutil

from agents_lib import REPO, parse_agent, render_agent, source_agents, write_text
from contracts_lib import (agent_contracts, agent_enums, build_catalog_json, build_catalog_md, generated_libs,
                           plugin_manifests, render_agent as render_agent_contract, render_skill, replace_section,
                           shared_inputs, skill_contracts)


def write_contract_sections() -> None:
    """Réécrit la section « Contrat » des SKILL.md et des agents sources
    à partir des contract.json."""
    for name, contract in skill_contracts().items():
        path = REPO / "skills" / name / "SKILL.md"
        write_text(path, replace_section(path.read_text(encoding="utf-8"), render_skill(contract)))
    for name, contract in agent_contracts().items():
        path = REPO / "src" / "agents" / f"{name}.md"
        text = replace_section(path.read_text(encoding="utf-8"), render_agent_contract(contract), "## Déroulé")
        write_text(path, text)


def style_for(style: str, section: str) -> str:
    """Charte réduite aux règles communes et à la section « Par format » du skill :
    chaque skill ne charge que ce qui le concerne."""
    common, _, formats = style.partition("\n## Par format\n")
    parts = re.split(r"^### ", formats, flags=re.M)
    kept = [p for p in parts[1:] if p.split("\n", 1)[0].strip() == section]
    if not kept:
        return common.rstrip() + "\n"
    return common.rstrip() + "\n\n## " + kept[0].rstrip() + "\n"


def main() -> None:
    # D'abord la liste des agents dans les schémas des messages : le reste en dépend.
    for path, text in {**agent_enums(), **shared_inputs()}.items():
        write_text(path, text)
    write_contract_sections()
    claude_dir = REPO / "agents"
    copilot_dir = REPO / "com.github.copilot" / "agents"
    for folder in (claude_dir, copilot_dir):
        shutil.rmtree(folder, ignore_errors=True)
        folder.mkdir(parents=True)

    for src in source_agents():
        name = parse_agent(src)[0]["name"]
        write_text(claude_dir / f"{name}.md", render_agent(src, "claude"))
        write_text(copilot_dir / f"{name}.agent.md", render_agent(src, "copilot"))

    style = (REPO / "shared" / "references" / "style.md").read_text(encoding="utf-8")
    for line in (REPO / "shared" / "targets.txt").read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            skill, _, section = line.strip().partition(" ")
            write_text(REPO / "skills" / skill / "references" / "style.md", style_for(style, section))

    for path, text in {**generated_libs(), **plugin_manifests()}.items():
        write_text(path, text)

    agents_meta = {parse_agent(src)[0]["name"]: parse_agent(src)[0] for src in source_agents()}
    write_text(REPO / "CATALOG.md", build_catalog_md(agents_meta))
    write_text(REPO / "catalog.json", build_catalog_json(agents_meta))

    print("Plugin régénéré. Pensez à committer agents/, com.github.copilot/, skills/, src/agents/, .claude-plugin/, CATALOG.md et catalog.json.")


if __name__ == "__main__":
    main()
