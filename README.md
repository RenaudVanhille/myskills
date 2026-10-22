# myskills

Plugin de skills et d'agents pour l'ingénierie logicielle, utilisable dans
**GitHub Copilot**, **Claude Code**, **Kiro**, **OpenCode** et **Hermes** :

- **Extraction documentaire** : PDF, DOCX, PPTX, XLSX, images vers Markdown ou
  Obsidian.
- **Schémas** : draw.io, Excalidraw, C4, Mermaid, adaptés à un public
  technique ou non, pour Markdown, Office et Confluence.

## Installation

| Outil | Commande |
| --- | --- |
| GitHub Copilot CLI | `copilot plugin install RenaudVanhille/myskills` |
| Claude Code | `/plugin marketplace add RenaudVanhille/myskills` puis `/plugin install myskills@myskills` |
| Kiro | Panneau Powers > Add Custom Power > Import power from GitHub > `https://github.com/RenaudVanhille/myskills` (skills uniquement) |
| OpenCode | Pas d'installation native : `uv run scripts/install.py --tools opencode [--global]` |
| Agents Kiro | Les powers ne transportent pas d'agents : `uv run scripts/install.py --tools kiro [--global]` |
| Hermes | Skills : `hermes skills tap add RenaudVanhille/myskills` puis `hermes skills install RenaudVanhille/myskills/<skill>`. Tout, agents compris : `uv run scripts/install.py --tools hermes [--global]` |

Hermes n'a pas d'agents personnalisés : `install.py` y installe
`schema-designer` et `document-extractor` sous forme de skills. En projet,
lancez ensuite `hermes skills trust` pour que Hermes charge `.hermes/skills`.

Les scripts sont en Python sans dépendance et fonctionnent sous Windows,
macOS et Linux. Lancez-les avec [uv](https://docs.astral.sh/uv/)
(`uv run scripts/...`) ou directement avec `python`.

Avant une première utilisation, le skill `check-prerequisites` liste les
outils locaux manquants (MarkItDown, Docling, draw.io Desktop, Node.js, un
navigateur). Pandoc, Mermaid CLI et LikeC4 sont téléchargés à la demande.

## Contenu

### Agents

| Agent | Rôle |
| --- | --- |
| `schema-designer` | Choisit le format de schéma selon le contexte, le public et la destination, puis valide le rendu |
| `document-extractor` | Choisit l'outil de conversion selon le document, puis valide le Markdown |

### Skills

| Skill | Rôle |
| --- | --- |
| `check-prerequisites` | Vérifie les outils locaux et indique comment installer les manquants |
| `doc-to-markdown` | Document vers Markdown (MarkItDown, Docling, vision) |
| `markdown-to-obsidian` | Markdown vers format Obsidian |
| `diagram-brief` | Grille de choix du format de schéma |
| `drawio-diagram` | Schémas draw.io et exports |
| `excalidraw-diagram` | Schémas Excalidraw pour publics non techniques |
| `c4-architecture` | Modèle C4 en LikeC4 ou Mermaid |
| `mermaid-diagram` | Schémas Mermaid dans le Markdown |
| `diagram-export` | Exports PNG/SVG pour Office et Confluence |
| `markdown-publish` | Markdown vers Confluence ou Word |

## Outils autorisés

Chaque agent n'a que le strict nécessaire : lecture et écriture de fichiers,
le shell pour les commandes de conversion et d'export, et le lancement d'un
sous-agent (pour les niveaux de coût, ci-dessous). Aucun accès web : la
conversion reste locale.

| Outil | Outils de l'agent | Commandes shell |
| --- | --- | --- |
| Claude Code | `Read, Write, Edit, Bash, Skill, Agent` | Toutes (Claude Code ne filtre pas les commandes au niveau de l'agent) |
| GitHub Copilot | `read, edit, execute, agent` | Toutes |
| OpenCode | `read, glob, edit, skill, subagent` + `shell` filtré | Seulement la liste `commands` de l'agent |
| Kiro | `read, write, shell, subagent` | Toutes |
| Hermes | Outils de la session (pas d'agents) | Toutes |

La liste des commandes autorisées se trouve dans le champ `commands` de
chaque agent source (`src/agents/`).

## Niveaux et coûts

Aucun modèle n'est imposé : chaque outil garde le modèle de la session (ou
son mode automatique, comme Auto dans Kiro). Pour limiter les coûts, chaque
agent classe ses actions en trois niveaux (simple, moyen, complexe) avec une
grille, et adapte son effort en conséquence. Quand l'outil permet de lancer un
sous-agent sur un autre modèle (par exemple `haiku` ou `opus` dans Claude
Code), l'agent l'utilise pour les actions simples ou complexes.

## Organisation du dépôt

| Chemin | Rôle |
| --- | --- |
| `plugin.json` | Manifeste [Agent Plugins 1.0](https://vercel.com/kb/guide/agent-plugins), lu par Copilot et Kiro |
| `.claude-plugin/` | Manifeste et marketplace Claude Code |
| `skills/<nom>/SKILL.md` | Skills au format [Agent Skills](https://agentskills.io) |
| `src/agents/` | **Source** des agents, en format neutre (à modifier ici) |
| `agents/` | Agents Claude Code, générés |
| `com.github.copilot/agents/` | Agents Copilot, générés |
| `shared/references/style.md` | Charte graphique, copiée dans les skills listés dans `shared/targets.txt` |
| `scripts/build.py` | Régénère les fichiers générés ; à lancer avant chaque commit (`uv run scripts/build.py`) |
| `scripts/install.py` | Installation pour OpenCode, Hermes et les agents Kiro |
| `tests/` | Documents réels et résultats attendus |

Vérification du plugin Claude Code : `claude plugin validate .`

## Principes

- La logique métier vit dans les skills ; les agents orchestrent et valident.
- La conversion de documents reste locale, sans service en ligne.
- Un skill repris d'un tiers cite sa source et respecte sa licence.

## Licence

[MIT](LICENSE)
