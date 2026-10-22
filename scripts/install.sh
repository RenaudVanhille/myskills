#!/usr/bin/env bash
# Installe skills et agents pour OpenCode et Kiro, qui n'ont pas
# d'installation native pour ce contenu (Claude Code et GitHub Copilot
# passent par leur commande plugin, voir le README).
#
# Usage :
#   scripts/install.sh [--project DIR | --global] [--tools opencode,kiro] [--dry-run]
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

MODE=project
ROOT="$PWD"
TOOLS="opencode,kiro"
DRY=0

while [ $# -gt 0 ]; do
  case "$1" in
    --project) MODE=project; ROOT="$(cd "$2" && pwd)"; shift 2 ;;
    --global) MODE=global; ROOT="$HOME"; shift ;;
    --tools) TOOLS="$2"; shift 2 ;;
    --dry-run) DRY=1; shift ;;
    -h|--help) sed -n '2,7p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "Option inconnue : $1" >&2; exit 1 ;;
  esac
done

has_tool() { case ",$TOOLS," in *",$1,"*) return 0 ;; *) return 1 ;; esac; }
run() { if [ "$DRY" = 1 ]; then echo "+ $*"; else "$@"; fi; }
write() { if [ "$DRY" = 1 ]; then echo "+ écrire $1"; cat >/dev/null; else cat >"$1"; fi; }

install_skills() {
  local dest="$1" skill name
  run mkdir -p "$dest"
  for skill in "$REPO"/skills/*/; do
    name="$(basename "$skill")"
    run rm -rf "${dest:?}/$name"
    run cp -R "$skill" "$dest/$name"
    [ "$DRY" = 1 ] || find "$dest/$name" -name .gitkeep -delete
  done
  echo "Skills -> $dest"
}

install_agents() {
  local flavor="$1" dest="$2" prefix="$3" src
  run mkdir -p "$dest"
  for src in "$REPO"/src/agents/*.md; do
    render_agent "$src" "$flavor" "$prefix" | write "$dest/$(field name "$src").md"
  done
  echo "Agents ($flavor) -> $dest"
}

if has_tool opencode; then
  if [ "$MODE" = global ]; then
    install_skills "$ROOT/.config/opencode/skills"
    install_agents opencode "$ROOT/.config/opencode/agents" ""
  else
    install_skills "$ROOT/.opencode/skills"
    install_agents opencode "$ROOT/.opencode/agents" ""
  fi
fi

if has_tool kiro; then
  if [ "$MODE" = global ]; then
    install_skills "$ROOT/.kiro/skills"
    install_agents kiro "$ROOT/.kiro/agents" "~/.kiro/skills"
  else
    install_skills "$ROOT/.kiro/skills"
    install_agents kiro "$ROOT/.kiro/agents" ".kiro/skills"
  fi
fi
