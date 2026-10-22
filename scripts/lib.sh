# Fonctions communes à build.sh et install.sh. À sourcer, pas à exécuter.

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Lit un champ du frontmatter d'un fichier agent source.
field() { awk -v k="$1" 'NR==1&&/^---$/{f=1;next} f&&/^---$/{exit} f&&index($0,k": ")==1{print substr($0,length(k)+3)}' "$2"; }

# Corps d'un fichier agent source, sans le frontmatter.
body() { awk 'NR==1&&/^---$/{f=1;next} f&&/^---$/{f=0;next} !f' "$1"; }

# Découpe une liste "a, b, c" en lignes.
split_list() { echo "$1" | tr ',' '\n' | sed 's/^ *//; s/ *$//' | grep -v '^$'; }

# Écrit l'agent $1 (fichier source) au format $2 (claude|copilot|opencode|kiro)
# sur la sortie standard. $3 = dossier des skills dans les URI skill:// de Kiro.
render_agent() {
  local src="$1" flavor="$2" kiro_prefix="${3:-.kiro/skills}"
  local name desc skills commands s first
  name="$(field name "$src")"
  desc="$(field description "$src")"
  skills="$(field skills "$src")"
  commands="$(field commands "$src")"
  echo "---"
  case "$flavor" in
    claude)
      echo "name: $name"
      echo "description: $desc"
      echo "tools: Read, Write, Edit, Bash, Skill, Agent"
      ;;
    copilot)
      echo "name: $name"
      echo "description: $desc"
      echo "tools: ['read', 'edit', 'execute', 'agent']"
      ;;
    opencode)
      echo "description: $desc"
      echo "mode: primary"
      echo "permissions:"
      printf '  - action: "*"\n    resource: "*"\n    effect: deny\n'
      for s in read glob edit skill subagent; do
        printf '  - action: %s\n    resource: "*"\n    effect: allow\n' "$s"
      done
      split_list "$commands" | while read -r s; do
        printf '  - action: shell\n    resource: "%s"\n    effect: allow\n' "$s"
      done
      ;;
    kiro)
      first=1
      printf 'name: %s\ndescription: %s\ntools: ["read", "write", "shell", "subagent"]\nresources: [' "$name" "$desc"
      for s in $(split_list "$skills"); do
        [ "$first" = 1 ] || printf ', '
        printf '"skill://%s/%s/SKILL.md"' "$kiro_prefix" "$s"
        first=0
      done
      printf ']\n'
      ;;
  esac
  echo "---"
  body "$src"
}
