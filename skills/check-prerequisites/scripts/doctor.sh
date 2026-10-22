#!/usr/bin/env bash
# Vérifie les outils dont les skills de myskills ont besoin.
#
# Usage : doctor.sh [extraction|schemas|publication|tout]   (défaut : tout)
# Code de sortie : 0 si tout est présent, 1 sinon.
set -u

GROUP="${1:-tout}"
MISSING=0

ok()   { printf '  [ok]       %s\n' "$1"; }
miss() { printf '  [manquant] %s -> %s\n' "$1" "$2"; MISSING=1; }

check_cmd() { # nom, commande, aide
  if command -v "$2" >/dev/null 2>&1; then ok "$1"; else miss "$1" "$3"; fi
}

check_py() { # nom, module, aide
  if python3 -c "import $2" >/dev/null 2>&1; then ok "$1"; else miss "$1" "$3"; fi
}

check_drawio() {
  if command -v drawio >/dev/null 2>&1 \
    || [ -x "/Applications/draw.io.app/Contents/MacOS/draw.io" ] \
    || [ -x "/c/Program Files/draw.io/draw.io.exe" ]; then
    ok "draw.io Desktop"
  else
    miss "draw.io Desktop" "https://github.com/jgraph/drawio-desktop/releases"
  fi
}

want() { [ "$GROUP" = tout ] || [ "$GROUP" = "$1" ]; }

check_cmd "Python 3" python3 "https://www.python.org/downloads/"

if want extraction; then
  echo "Extraction documentaire"
  check_cmd "MarkItDown" markitdown "pip install 'markitdown[all]'"
  check_cmd "Docling" docling "pip install docling"
fi

if want schemas; then
  echo "Schémas"
  check_drawio
  check_cmd "Node.js" node "https://nodejs.org/"
  check_cmd "Mermaid CLI" mmdc "npm install -g @mermaid-js/mermaid-cli"
  check_cmd "LikeC4" likec4 "npm install -g likec4"
  check_py "Playwright (Python)" playwright "pip install playwright && playwright install chromium"
fi

if want publication; then
  echo "Publication"
  check_cmd "Pandoc" pandoc "https://pandoc.org/installing.html"
fi

if [ "$MISSING" = 0 ]; then echo "Tout est prêt."; else echo "Des outils manquent (voir ci-dessus)."; fi
exit "$MISSING"
