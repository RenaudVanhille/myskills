#!/usr/bin/env bash
# Régénère les fichiers du plugin à partir des sources (src/agents/, shared/).
# À lancer après chaque modification d'un agent ou de la charte, puis
# committer le résultat : les outils installent le plugin depuis le dépôt.
#
#   agents/*.md                           agents Claude Code
#   com.github.copilot/agents/*.agent.md  agents GitHub Copilot
#   skills/*/references/style.md          charte graphique (shared/targets.txt)
set -euo pipefail
. "$(dirname "${BASH_SOURCE[0]}")/lib.sh"

rm -rf "$REPO/agents" "$REPO/com.github.copilot/agents"
mkdir -p "$REPO/agents" "$REPO/com.github.copilot/agents"

for src in "$REPO"/src/agents/*.md; do
  name="$(field name "$src")"
  render_agent "$src" claude >"$REPO/agents/$name.md"
  render_agent "$src" copilot >"$REPO/com.github.copilot/agents/$name.agent.md"
done

while read -r skill; do
  [ -n "$skill" ] || continue
  mkdir -p "$REPO/skills/$skill/references"
  cp "$REPO/shared/references/style.md" "$REPO/skills/$skill/references/style.md"
done <"$REPO/shared/targets.txt"

echo "Plugin régénéré. Pensez à committer agents/, com.github.copilot/ et skills/."
