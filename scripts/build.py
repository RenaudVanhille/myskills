# /// script
# requires-python = ">=3.10"
# ///
"""Régénère les fichiers du plugin à partir des sources (src/agents/, shared/).

À lancer après chaque modification d'un agent ou de la charte, puis committer
le résultat : les outils installent le plugin depuis le dépôt.

    agents/*.md                           agents Claude Code
    com.github.copilot/agents/*.agent.md  agents GitHub Copilot
    skills/*/references/style.md          charte graphique (shared/targets.txt)
    CATALOG.md                            contrats des agents et des skills

Usage : uv run scripts/build.py   (ou : python scripts/build.py)
"""

import re
import shutil

from agents_lib import REPO, parse_agent, render_agent, source_agents, write_text

FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)
# Dans un agent, le contrat propre s'arrête avant les formats communs de
# passage et de rapport, repris une seule fois en tête du catalogue.
SHARED_START = "Pour passer la main, si ton outil"


def section(body: str, title: str) -> str:
    match = re.search(rf"^## {title}\n(.*?)(?=^## |\Z)", body, re.S | re.M)
    return match.group(1).strip() if match else ""


def skill_meta(path):
    text = path.read_text(encoding="utf-8")
    meta = dict(re.findall(r'^(\w+):\s*"?(.*?)"?\s*$', FRONTMATTER.match(text).group(1), re.M))
    return meta, text[FRONTMATTER.match(text).end():]


def build_catalog() -> str:
    agents = [parse_agent(src) for src in source_agents()]
    shared = section(agents[0][1], "Contrat")
    shared = shared[shared.index(SHARED_START):] if SHARED_START in shared else ""
    lines = ["# Catalogue des agents et des skills", "",
             "Fichier généré par `scripts/build.py` à partir des sections « Contrat » de",
             "`src/agents/*.md` et `skills/*/SKILL.md` : ne pas le modifier à la main.",
             "Un agent ou un outil qui veut appeler myskills y trouve, pour chaque agent",
             "et chaque skill, ce qu'il reçoit, ce qu'il produit, ses rapports et à qui",
             "il passe la main.", "", "## Passage de relais et rapport final des agents", "",
             shared, "", "## Agents", ""]
    for meta, body in agents:
        contract = section(body, "Contrat")
        contract = contract[:contract.index(SHARED_START)].strip() if SHARED_START in contract else contract
        lines += [f"### `{meta['name']}`", "", meta["description"].strip('"'), "",
                  f"**Skills** : {', '.join(f'`{s.strip()}`' for s in meta.get('skills', '').split(','))}",
                  "", contract, ""]
    lines += ["## Skills", ""]
    for path in sorted((REPO / "skills").glob("*/SKILL.md")):
        meta, body = skill_meta(path)
        lines += [f"### `{meta['name']}`", "", meta["description"], "",
                  section(body, "Contrat") or "_Pas de section Contrat._", ""]
    return "\n".join(lines).rstrip() + "\n"


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

    write_text(REPO / "CATALOG.md", build_catalog())

    print("Plugin régénéré. Pensez à committer agents/, com.github.copilot/, skills/ et CATALOG.md.")


if __name__ == "__main__":
    main()
