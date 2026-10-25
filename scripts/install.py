# /// script
# requires-python = ">=3.10"
# ///
"""Installe skills et agents pour OpenCode, Kiro et Hermes, qui n'ont pas
d'installation native pour l'ensemble de ce contenu. Claude Code et GitHub
Copilot passent par leur commande plugin (voir le README).

Hermes n'a pas d'agents : chaque agent y est installé comme un skill.

Usage :
    uv run scripts/install.py [--project DIR | --global] [--tools opencode,kiro,hermes] [--models FICHIER] [--dry-run]

--models : fichier JSON des modèles de votre abonnement, par outil puis par
niveau, qui prime sur shared/models.json, par exemple
{"opencode": {"simple": "anthropic/claude-haiku-4-5", "moyen": "anthropic/claude-sonnet-4-5",
"complexe": "anthropic/claude-opus-4-5"}, "kiro": {"moyen": "claude-sonnet-4.6"}}.
Kiro n'a pas de modèle de repli : un identifiant absent de son service fait
échouer l'agent (liste : /model dans Kiro).
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

import agents_lib
from agents_lib import LEVELS, REPO, parse_agent, render_agent, source_agents, write_text


def install_skills(dest: Path, dry: bool) -> None:
    for skill in sorted(p for p in (REPO / "skills").iterdir() if p.is_dir()):
        target = dest / skill.name
        if dry:
            print(f"+ copier {skill} -> {target}")
            continue
        shutil.rmtree(target, ignore_errors=True)
        shutil.copytree(skill, target, ignore=shutil.ignore_patterns(".gitkeep"))
    print(f"Skills -> {dest}")


def install_agents(flavor: str, dest: Path, dry: bool, skills_dir: str = ".kiro/skills") -> None:
    for src in source_agents():
        name = parse_agent(src)[0]["name"]
        target = dest / name / "SKILL.md" if flavor == "hermes" else dest / f"{name}.md"
        if dry:
            print(f"+ écrire {target}")
            continue
        write_text(target, render_agent(src, flavor, skills_dir))
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
    parser.add_argument("--models", type=Path,
                        help="JSON des modèles par outil puis par niveau (simple, moyen, complexe), prioritaire "
                             "sur shared/models.json")
    parser.add_argument("--dry-run", action="store_true",
                        help="afficher sans rien écrire")
    args = parser.parse_args()
    if args.models:
        try:
            overrides = json.loads(args.models.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            sys.exit(f"--models : fichier illisible ({error})")
        bad = [f"{tool}/{level}" for tool, levels in overrides.items() if isinstance(levels, dict)
               for level in levels if level not in LEVELS]
        bad += [tool for tool, levels in overrides.items() if not isinstance(levels, dict)]
        if bad:
            sys.exit(f"--models : clé inattendue {', '.join(bad)} (outil -> {{{', '.join(LEVELS)}}} -> modèle)")
        agents_lib.OVERRIDES.update(overrides)

    tools = {t.strip() for t in args.tools.split(",")}
    home = Path.home()
    root = home if args.global_ else args.project.resolve()

    if "opencode" in tools:
        base = home / ".config" / "opencode" if args.global_ else root / ".opencode"
        install_skills(base / "skills", args.dry_run)
        install_agents("opencode", base / "agents", args.dry_run)

    if "kiro" in tools:
        install_skills(root / ".kiro" / "skills", args.dry_run)
        install_agents("kiro", root / ".kiro" / "agents", args.dry_run,
                       "~/.kiro/skills" if args.global_ else ".kiro/skills")

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
