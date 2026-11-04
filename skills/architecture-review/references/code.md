# Comparer le code à l'architecture

Détail de la section 2 du `SKILL.md`, à lire seulement quand le code
existe.

Si le code existe, `"code": {"root": "../src"}` et un motif `code` par
composant (`src/api/**`, un dossier, `*.py`). Le script lance
`graphify extract RACINE --code-only` (skill externe graphify, installé à
part, `uv tool install graphifyy`) : analyse locale par tree-sitter, sans
modèle ; le graphe reste dans `graphify-out/` à côté de
la revue, réutilisé aux relances. Avec un graphe déjà produit, donnez
`"graph"`. Le script signale les dépendances du code entre composants sans
flux déclaré, les cycles entre composants et les fichiers non rattachés.
Par défaut, seul le code est lu. Pour enrichir le graphe avec les documents
du dossier (README, `docs/`, ADR), `"semantic": "claude"` les fait lire par
le modèle du harness (`ANTHROPIC_MODEL` pour un modèle léger : c'est un
travail de niveau simple) et `"semantic": "ollama"` par un modèle local ;
aucun autre fournisseur. Dans Copilot ou Kiro, lancez plutôt le skill
graphify de l'outil (ses sous-agents au niveau simple) puis donnez le
`graph.json` obtenu. Les liens tirés des documents (INFERRED) ne changent
pas les contrôles du code.
