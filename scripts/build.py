# /// script
# requires-python = ">=3.10"
# ///
"""Régénère les fichiers du plugin à partir des sources (src/agents/, shared/).

À lancer après chaque modification d'un agent ou de la charte, puis committer
le résultat : les outils installent le plugin depuis le dépôt.

    agents/*.md                           agents Claude Code
    com.github.copilot/agents/*.agent.md  agents GitHub Copilot
    skills/*/references/style.md          charte graphique (shared/targets.txt)

Usage : uv run scripts/build.py   (ou : python scripts/build.py)
"""

import shutil

from agents_lib import REPO, parse_agent, render_agent, source_agents, write_text


def main() -> None:
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
    targets = (REPO / "shared" / "targets.txt").read_text(encoding="utf-8").split()
    for skill in targets:
        write_text(REPO / "skills" / skill / "references" / "style.md", style)

    print("Plugin régénéré. Pensez à committer agents/, com.github.copilot/ et skills/.")


if __name__ == "__main__":
    main()
