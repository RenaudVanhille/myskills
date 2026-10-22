#!/usr/bin/env bash
# Installe les skills et les agents de myskills pour Claude, GitHub Copilot,
# OpenCode et Kiro, à partir d'une source unique (skills/, agents/, shared/).
#
# Usage :
#   scripts/install.sh [--project DIR | --global] [--tools LISTE] [--dry-run]
#
#   --project DIR  installe dans le projet DIR (défaut : dossier courant)
#   --global       installe dans le dossier personnel (~)
#   --tools LISTE  outils ciblés, séparés par des virgules
#                  (défaut : claude,copilot,opencode,kiro)
#   --dry-run      affiche ce qui serait fait sans rien écrire
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE=project
ROOT="$PWD"
TOOLS="claude,copilot,opencode,kiro"
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --project) MODE=project; ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --global) MODE=global; ROOT="$HOME"; shift ;;
    --tools) TOOLS="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; exit 1 ;;
  esac
done

has_tool() { case ",$TOOLS," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }

run() {
  if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi
}

# Écrit stdin dans le fichier $1 (ou l'affiche en dry-run).
write() {
  if [ "$DRY" = 1 ]; then echo "+ écrire $1"; cat >/dev/null; else cat >"$1"; fi
}

# Lit un champ du frontmatter d'un fichier agent source.
field() { awk -v k="$1" 'NR==1&&/^---$/{f=1;next} f&&/^---$/{exit} f&&index($0,k": ")==1{print substr($0,length(k)+3)}' "$2"; }

# Corps d'un fichier agent source, sans le frontmatter.
body() { awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{f=0;next} !f' "$1"; }

install_skills() {
  local dest="$1" skill name
  run mkdir -p "$dest"
  for skill in "$REPO"/skills/*/; do
    name="$(basename "$skill")"
    run rm -rf "${dest:?}/$name"
    run cp -R "$skill" "$dest/$name"
    if grep -qx "$name" "$REPO/shared/targets.txt"; then
      run cp "$REPO/shared/references/style.md" "$dest/$name/references/style.md"
    fi
    [ "$DRY" = 1 ] || find "$dest/$name" -name .gitkeep -delete
  done
  echo "Skills -> $dest"
}

# Modèle configuré dans shared/models.conf pour l'outil $1 et le niveau $2.
model_for() { awk -F= -v k="$1.$2" '$1==k{print $2}' "$REPO/shared/models.conf"; }

# Génère les agents pour un outil : $1 = claude|opencode|kiro, $2 = dossier.
install_agents() {
  local flavor="$1" dest="$2" src name desc skills role tier model doctor resources tools s
  run mkdir -p "$dest"
  if [ "$MODE" = global ]; then doctor="~/.myskills/doctor.sh"; else doctor=".myskills/doctor.sh"; fi
  for src in "$REPO"/agents/*.md; do
    name="$(field name "$src")"
    desc="$(field description "$src")"
    skills="$(field skills "$src")"
    role="$(field role "$src")"
    tier="$(field tier "$src")"
    model="$(model_for "$flavor" "$tier")"
    {
      echo "---"
      case "$flavor" in
        claude)
          echo "name: $name"
          echo "description: $desc"
          [ -n "$model" ] && echo "model: $model"
          echo "skills: $skills"
          ;;
        opencode)
          echo "description: $desc"
          if [ "$role" = coordinateur ]; then echo "mode: primary"; else echo "mode: subagent"; fi
          [ -n "$model" ] && echo "model: $model"
          ;;
        kiro)
          resources=""
          for s in $(echo "$skills" | tr ',' ' '); do
            if [ "$MODE" = global ]; then s="skill://~/.kiro/skills/$s/SKILL.md"; else s="skill://.kiro/skills/$s/SKILL.md"; fi
            resources="$resources${resources:+, }\"$s\""
          done
          tools='"read", "write", "shell"'
          [ "$role" = coordinateur ] && tools="$tools, \"subagent\""
          echo "name: $name"
          echo "description: $desc"
          [ -n "$model" ] && echo "model: $model"
          echo "tools: [$tools]"
          echo "resources: [$resources]"
          ;;
      esac
      echo "---"
      body "$src" | sed "s#scripts/doctor.sh#$doctor#g"
    } | write "$dest/$name.md"
  done
  echo "Agents ($flavor) -> $dest"
}

if [ "$MODE" = global ]; then
  CLAUDE_SKILLS="$ROOT/.claude/skills"; KIRO_SKILLS="$ROOT/.kiro/skills"; COPILOT_SKILLS="$ROOT/.copilot/skills"
  CLAUDE_AGENTS="$ROOT/.claude/agents"; OPENCODE_AGENTS="$ROOT/.config/opencode/agents"; KIRO_AGENTS="$ROOT/.kiro/agents"
else
  # En projet, Copilot et OpenCode lisent aussi .claude/skills.
  CLAUDE_SKILLS="$ROOT/.claude/skills"; KIRO_SKILLS="$ROOT/.kiro/skills"; COPILOT_SKILLS=""
  CLAUDE_AGENTS="$ROOT/.claude/agents"; OPENCODE_AGENTS="$ROOT/.opencode/agents"; KIRO_AGENTS="$ROOT/.kiro/agents"
fi

if has_tool claude || has_tool opencode || { has_tool copilot && [ -z "$COPILOT_SKILLS" ]; }; then
  install_skills "$CLAUDE_SKILLS"
fi
if has_tool copilot && [ -n "$COPILOT_SKILLS" ]; then install_skills "$COPILOT_SKILLS"; fi
if has_tool kiro; then install_skills "$KIRO_SKILLS"; fi

# Copilot lit le format Claude dans .claude/agents.
if has_tool claude || has_tool copilot; then install_agents claude "$CLAUDE_AGENTS"; fi
if has_tool opencode; then install_agents opencode "$OPENCODE_AGENTS"; fi
if has_tool kiro; then install_agents kiro "$KIRO_AGENTS"; fi

run mkdir -p "$ROOT/.myskills"
run cp "$REPO/scripts/doctor.sh" "$ROOT/.myskills/doctor.sh"
echo "Vérification des prérequis -> $ROOT/.myskills/doctor.sh"
