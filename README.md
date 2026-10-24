# myskills

Plugin de skills et d'agents pour l'ingénierie logicielle, utilisable dans
**GitHub Copilot**, **Claude Code**, **Kiro**, **OpenCode** et **Hermes** :

- **Extraction documentaire** : PDF, DOCX, PPTX, XLSX, images vers Markdown ou
  Obsidian.
- **Schémas** : draw.io, Excalidraw, C4, Mermaid, plan d'occupation des sols du SI, adaptés à un public
  technique ou non, pour Markdown, Office et Confluence.
- **Publication** : Markdown vers Word, HTML ou XWiki, schémas compris.
- **Des documents à l'architecture** : exigences fonctionnelles et non
  fonctionnelles tracées jusqu'aux sources, 2 ou 3 architectures comparées,
  schémas, avec une revue humaine à chaque étape, un journal des décisions et
  une mémoire partagée dans le vault Obsidian.

## Installation

| Outil | Commande |
| --- | --- |
| GitHub Copilot CLI | `copilot plugin marketplace add RenaudVanhille/myskills` puis `copilot plugin install myskills@myskills` |
| Claude Code | `/plugin marketplace add RenaudVanhille/myskills` puis `/plugin install myskills@myskills` |
| Kiro | Panneau Powers > Add Custom Power > Import power from GitHub > `https://github.com/RenaudVanhille/myskills` (skills uniquement) |
| OpenCode | Pas d'installation native : `uv run scripts/install.py --tools opencode [--global]` |
| Agents Kiro | Les powers ne transportent pas d'agents : `uv run scripts/install.py --tools kiro [--global]` |
| Hermes | Skills : `hermes skills tap add RenaudVanhille/myskills` puis `hermes skills install RenaudVanhille/myskills/skills/<skill>`. Tout, agents compris : `uv run scripts/install.py --tools hermes [--global]` |

Hermes n'a pas d'agents personnalisés : `install.py` y installe
les agents (`schema-designer`, `document-extractor`, `document-publisher`,
`architecture-workflow`) sous
forme de skills. Hermes ne lit que `~/.hermes/skills` : en projet, `install.py`
affiche la commande `hermes config set skills.external_dirs "<dossier>"` à
lancer une fois (elle remplace les `external_dirs` déjà configurés).

Les scripts sont en Python 3.10+ et fonctionnent sous Windows, macOS et
Linux. Lancez-les avec [uv](https://docs.astral.sh/uv/) (`uv run scripts/...`) :
uv installe les dépendances déclarées en tête de chaque script (MarkItDown,
Playwright, Pandoc...). Ceux qui n'en ont pas tournent aussi avec `python`.

Avant une première utilisation, le skill `check-prerequisites` liste les
outils locaux manquants (uv, draw.io Desktop, un navigateur ; Node.js et
LibreOffice en option). Pandoc, les bibliothèques Mermaid et Excalidraw et LikeC4 sont téléchargés à
la demande ; les rendus passent par Playwright.

## Contenu

### Agents

| Agent | Rôle |
| --- | --- |
| `schema-designer` | Choisit le format de schéma selon le contexte, le public et la destination, puis valide le rendu |
| `document-extractor` | Import : convertit PDF, Office et images en Markdown ou Obsidian, puis valide le Markdown |
| `document-publisher` | Export : transforme un Markdown en Word, HTML ou XWiki pour SharePoint, Confluence ou XWiki, puis relit le rendu |
| `architecture-workflow` | Workflow décrit en JSON, par défaut en 4 étapes : documents, exigences (avec glossaire), 2 ou 3 architectures, schémas et matrice de traçabilité ; aussi `cloud-existant` (code d'infrastructure vers schéma cloud et STRIDE) ; s'arrête après chaque étape pour la revue de l'utilisateur et trace chaque choix et décision |

Chaque skill et chaque agent a un **contrat d'interface en JSON**, qui fait
foi :

- `skills/<nom>/contract.json` : entrées, sorties, scripts, options, codes de
  sortie, passages de main, et le **JSON Schema** du rapport de chaque script ;
- `src/agents/<nom>.contract.json` : ce que l'agent reçoit, produit, ne fait
  jamais, et à qui il passe la main avec quoi ;
- `shared/schemas/` : les schémas des contrats, du **message de passage**
  entre agents (`handoff.schema.json`) et du **rapport final** des agents
  (`agent-report.schema.json`), que les agents écrivent en JSON.

`scripts/build.py` en génère la section « Contrat » des SKILL.md et des
agents, [`CATALOG.md`](CATALOG.md) et [`catalog.json`](catalog.json), à
lire par un autre agent ou outil qui appelle myskills.

### Skills

| Skill | Rôle |
| --- | --- |
| `check-prerequisites` | Vérifie les outils locaux et indique comment installer les manquants ; prépare le mode hors ligne (`--prefetch`, empreintes vérifiées) |
| `doc-to-markdown` | Document vers Markdown (MarkItDown, Docling, vision), tri optionnel par type et domaine avec le modèle local Laya |
| `markdown-to-obsidian` | Markdown vers format Obsidian |
| `diagram-brief` | Grille de choix du format de schéma |
| `drawio-diagram` | Schémas draw.io et exports |
| `excalidraw-diagram` | Schémas Excalidraw pour publics non techniques |
| `c4-architecture` | Modèle C4 en LikeC4 ou Mermaid |
| `urbanization-map` | Plan d'occupation des sols du SI (zones, quartiers, îlots, applications) en draw.io, depuis une description courte ou un inventaire CSV |
| `mermaid-diagram` | Schémas Mermaid dans le Markdown |
| `requirements-catalog` | Catalogue des exigences fonctionnelles et non fonctionnelles, citations des sources vérifiées, phrases normatives oubliées signalées, glossaire relié aux exigences, export Markdown et CSV |
| `architecture-options` | 2 ou 3 options d'architecture : écarts aux exigences, score pondéré et rang calculés, recommandation, ADR, matrice de traçabilité, un schéma draw.io par option (et sa description cloud) |
| `decision-log` | État d'un workflow à portes de revue (ordre des étapes, validation par l'utilisateur, retour qui invalide la suite), journal des décisions, workflows décrits en JSON, revue différentielle, passages de main validés, et mémoire partagée dans un vault Obsidian (une note par exigence, terme, option et décision, revue dans Obsidian) |
| `cloud-architecture` | Architecture cloud AWS, Azure, GCP, Kubernetes aux icônes officielles : déploiement, réseau et matrice des flux, PRA, pipeline data ou CI/CD, modèle de menaces STRIDE, revue Well-Architected (AWS, Azure, Google Cloud) et conventions de schéma des fournisseurs ; description tirée de Terraform, docker-compose ou Kubernetes |
| `diagram-export` | Exports PNG/SVG pour Office et Confluence |
| `markdown-publish` | Markdown vers Word, HTML ou XWiki (SharePoint, Confluence, XWiki) |

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
| Kiro | `read, write, shell, subagent`, `web` exclu | Liste `commands` approuvée d'office, les autres sur confirmation |
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
| `AGENTS.md` | Règles que suit tout skill et tout agent, présent ou à venir (lu par Claude Code via `CLAUDE.md`) |
| `plugin.json` | Manifeste [Agent Plugins 1.0](https://vercel.com/kb/guide/agent-plugins), lu par Copilot et Kiro |
| `.claude-plugin/` | Manifeste et marketplace Claude Code |
| `skills/<nom>/SKILL.md` | Skills au format [Agent Skills](https://agentskills.io) |
| `src/agents/` | **Source** des agents, en format neutre (à modifier ici) |
| `agents/` | Agents Claude Code, générés |
| `com.github.copilot/agents/` | Agents Copilot, générés |
| `shared/references/style.md` | Charte graphique, copiée dans les skills listés dans `shared/targets.txt` (règles communes et section du format) |
| `shared/schemas/` | JSON Schema des contrats, du message de passage et du rapport final des agents |
| `CATALOG.md`, `catalog.json` | Contrats de tous les agents et skills, générés |
| `scripts/build.py` | Régénère les fichiers générés ; à lancer avant chaque commit (`uv run scripts/build.py`) |
| `scripts/install.py` | Installation pour OpenCode, Hermes et les agents Kiro |
| `tests/` | Documents de test, résultats attendus, `run.py` (scripts), `judge.py` (agents et déclenchement des skills) et `cost.py` (coût des agents, historique dans `costs.csv`) |

Vérification du plugin Claude Code : `claude plugin validate .`

## Principes

Les règles complètes sont dans [`AGENTS.md`](AGENTS.md) ; `tests/run.py` vérifie
celles qui sont mécaniques (cas `regles`).

- La logique métier vit dans les skills ; les agents orchestrent et valident.
- Tout script de skill est déclaré dans le `contract.json` de son skill ;
  `tests/run.py` valide chaque rapport contre son JSON Schema. On modifie le
  contrat JSON, jamais la section « Contrat » générée.
- La conversion de documents reste locale, sans service en ligne.
- Sobriété en tokens : ce qui est mécanique (nettoyage, styles, rendu, validation)
  est fait par un script ; le modèle ne décide que ce qui demande du jugement,
  sur des rapports courts. `tests/cost.py` mesure l'effet de chaque changement.
- Un skill repris d'un tiers cite sa source et respecte sa licence.

## Licence

[MIT](LICENSE)
