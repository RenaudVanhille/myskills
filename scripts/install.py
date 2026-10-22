# /// script
# requires-python = ">=3.10"
# ///
"""Installe skills et agents pour OpenCode, Kiro et Hermes, qui n'ont pas
d'installation native pour l'ensemble de ce contenu. Claude Code et GitHub
Copilot passent par leur commande plugin (voir le README).

Hermes n'a pas d'agents : chaque agent y est installé comme un skill.

Usage :
    uv run scripts/install.py [--project DIR | --global] [--tools opencode,kiro,hermes] [--dry-run]
"""

import argparse
import shutil
from pathlib import Path

from agents_lib import REPO, parse_agent, render_agent, source_agents, write_text


def install_skills(dest: Path, dry: bool) -> None:
    for skill in sorted(p for p in (REPO / "skills").iterdir() if p.is_dir()):
        target = dest / skill.name
        if dry:
            print(f"+ copier {skill} -> {target}")
            continue
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(skill, target, ignore=shutil.ignore_patterns(".gitkeep"))
    print(f"Skills -> {dest}")


def install_agents(flavor: str, dest: Path, dry: bool) -> None:
    for src in source_agents():
        name = parse_agent(src)[0]["name"]
        target = dest / name / "SKILL.md" if flavor == "hermes" else dest / f"{name}.md"
        if dry:
            print(f"+ écrire {target}")
            continue
        write_text(target, render_agent(src, flavor))
    print(f"Agents ({flavor}) -> {dest}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--project", type=Path, default=Path.cwd(),
                       help="dossier du projet (défaut : dossier courant)")
    where.add_argument("--global", dest="global_", action="store_true",
                       help="installer dans le dossier personnel")
    parser.add_argument("--tools", default="opencode,kiro,hermes",
                        help="outils ciblés, séparés par des virgules")
    parser.add_argument("--dry-run", action="store_true",
                        help="afficher sans rien écrire")
    args = parser.parse_args()

    tools = {t.strip() for t in args.tools.split(",")}
    home = Path.home()
    root = home if args.global_ else args.project.resolve()

    if "opencode" in tools:
        base = home / ".config" / "opencode" if args.global_ else root / ".opencode"
        install_skills(base / "skills", args.dry_run)
        install_agents("opencode", base / "agents", args.dry_run)

    if "kiro" in tools:
        install_skills(root / ".kiro" / "skills", args.dry_run)
        install_agents("kiro", root / ".kiro" / "agents", args.dry_run)

    if "hermes" in tools:
        skills = root / ".hermes" / "skills"
        install_skills(skills, args.dry_run)
        install_agents("hermes", skills, args.dry_run)
        if not args.global_:
            # Hermes ne lit que ~/.hermes/skills et les dossiers de skills.external_dirs.
            print("Pour que Hermes charge ces skills, lancez une fois :\n"
                  f'  hermes config set skills.external_dirs "{skills.resolve()}"\n'
                  "(la valeur remplace les external_dirs déjà configurés)")


if __name__ == "__main__":
    main()
