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
| `document-publisher` | Export : transforme un Markdown en Word, PowerPoint, HTML ou XWiki pour SharePoint, Confluence ou XWiki, puis relit le rendu |
| `architecture-workflow` | Moteur de workflow générique : suit une définition JSON (par défaut `architecture` en 4 étapes : documents, exigences avec glossaire, 2 ou 3 architectures situées dans le POS du SI, schémas et matrice de traçabilité ; aussi `cloud-existant` : code d'infrastructure vers schéma cloud, menaces et revue Well-Architected) ; s'arrête après chaque étape pour la revue de l'utilisateur et trace chaque choix et décision |
| `architecture-reviewer` | Revue d'une architecture logicielle ou solution (ATAM : scénarios de qualité, risques, compromis, traçabilité, code comparé à l'architecture, avis calculé) et d'une architecture cloud : modèle de menaces STRIDE relu et revue Well-Architected des piliers, constats ouverts ou acceptés avec leur raison |

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
| `markdown-to-obsidian` | Markdown vers format Obsidian, vérification d'un vault contre l'ontologie commune et export de son graphe typé (`vault_check.py`) |
| `diagram-brief` | Choix du format de schéma : décision courte en JSON validée, format, skill et livraison selon le public et la destination (`brief.py`) |
| `drawio-diagram` | Schémas draw.io et exports |
| `excalidraw-diagram` | Schémas Excalidraw pour publics non techniques |
| `c4-architecture` | Modèle C4 en LikeC4 ou Mermaid |
| `urbanization-map` | Plan d'occupation des sols du SI (zones, quartiers, îlots, applications) en draw.io, depuis une description courte, un inventaire CSV ou une note Markdown ; options d'architecture situées dans le POS (impacts, redondances, POS cible, `pos_impact.py`) |
| `mermaid-diagram` | Schémas Mermaid dans le Markdown |
| `requirements-catalog` | Catalogue des exigences fonctionnelles et non fonctionnelles, citations des sources vérifiées, phrases normatives oubliées signalées, glossaire relié aux exigences, export Markdown et CSV |
| `architecture-options` | 2 ou 3 options d'architecture : écarts aux exigences, score pondéré et rang calculés, recommandation, ADR, matrice de traçabilité, un schéma draw.io par option (et sa description cloud), position de chaque option dans le POS du SI (avec `urbanization-map`), revue Well-Architected des piliers de chaque option cloud (avec `well-architected-review`) |
| `architecture-deck` | Présentation du dossier d'architecture assemblée depuis les fichiers validés du workflow, à rendre en PowerPoint par `markdown-publish` |
| `decision-log` | État d'un workflow à portes de revue (ordre des étapes, validation par l'utilisateur, retour qui invalide la suite), journal des décisions, workflows décrits en JSON, revue différentielle, et mémoire partagée dans un vault Obsidian pilotée par la définition (une note par exigence, terme, option, décision et étape, schémas intégrés) |
| `agent-handoff` | Validation des messages de passage et des rapports finaux des agents (schéma, fichiers cités), notés au journal d'un workflow |
| `cloud-architecture` | Architecture cloud AWS, Azure, GCP, Kubernetes aux icônes officielles : déploiement, réseau et matrice des flux, PRA, pipeline data ou CI/CD, vue des menaces ; description tirée de Terraform, docker-compose ou Kubernetes |
| `threat-model` | Modèle de menaces STRIDE d'une architecture cloud : frontières de confiance, flux qui les traversent, menace et mesure type par catégorie |
| `architecture-review` | Revue d'architecture logicielle ou solution à la manière d'ATAM : arbre d'utilité (scénarios de qualité évalués), risques, sensibilités, compromis, décisions ; structure, traçabilité des exigences et avis calculés par script ; code comparé à l'architecture avec graphify (code analysé en local) ; piliers Well-Architected d'une option cloud |
| `well-architected-review` | Revue Well-Architected (AWS, Azure, Google Cloud) des six piliers et des conventions de schéma des fournisseurs, constats acceptés avec leur raison |
| `diagram-export` | Exports PNG/SVG pour Office et Confluence |
| `markdown-publish` | Markdown vers Word, HTML ou XWiki (SharePoint, Confluence, XWiki), et vers PowerPoint avec le skill externe `markdown-to-pptx` |

### Skills externes

Installés à part et appelés par leur seul contrat d'interface
(`shared/external/<nom>.contract.json` : où le trouver, commande, conventions
d'entrée, schéma de la sortie) ; myskills n'en copie pas le code.

| Skill | Utilisé par | Installation |
| --- | --- | --- |
| `markdown-to-pptx` (md2pptx, Reno) | `markdown-publish` (`pptx_publish.py`) | plugin powerpoint-skill dans votre outil, ou dossier du skill dans `MD2PPTX_SKILL` ; `check-prerequisites` (groupe `publication`) le cherche |
| `graphify` (Graphify Labs, Apache-2.0) | `architecture-review` (`arch_review.py`) : graphe du code, `--code-only` par défaut (analyse locale) ; documents lus, sur demande, par le modèle du harness ou Ollama | `uv tool install graphifyy`, ou chemin de la commande dans `GRAPHIFY_BIN` ; `check-prerequisites` (groupe `revue`) le cherche |

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

Chaque skill, agent et étape de workflow déclare un niveau : **simple**
(commandes, conversions et constructions par script), **moyen** (rédiger une
description JSON, corriger une erreur, intégrer un retour) ou **complexe**
(concevoir et noter des architectures, analyser des menaces, relire un
rendu). [`shared/models.json`](shared/models.json) donne le modèle de
chaque niveau par outil :

| Niveau | Classe | Claude Code | Copilot, OpenCode, Kiro, Hermes |
| --- | --- | --- | --- |
| simple | léger | `haiku` | modèle de la session |
| moyen | standard | `sonnet` | modèle de la session |
| complexe | puissant | `opus` | modèle de la session |

`scripts/build.py` en tire le `model` des agents Claude Code et leur
consigne : chaque agent travaille à son niveau, monte d'un niveau si une
action échoue, et ne confie à un sous-agent qu'un lot ou une étape d'un
autre niveau, avec le modèle de ce niveau. Changer de modèle : modifier
`shared/models.json`, puis `uv run scripts/build.py`. `tests/cost.py`
mesure le coût réel de chaque cas d'agent.

## Ajouter un skill, un agent ou un workflow

- **Skill** : un dossier `skills/<nom>/` avec `SKILL.md` et `contract.json`
  (niveau, scripts et leurs schémas, `requires` pour appeler un autre
  skill), puis `uv run scripts/build.py`.
- **Agent** : `src/agents/<nom>.md` (avec le marqueur `{{niveaux}}`) et
  `<nom>.contract.json` ; les schémas des messages entre agents se mettent
  à jour seuls.
- **Type de note du vault** : une entrée dans `shared/vault-ontology.json`
  (propriétés, facettes, relations), puis `uv run scripts/build.py` ; le
  skill qui l'écrit le déclare dans `vault.writes` de son contrat.
- **Workflow** : une définition JSON dans `skills/decision-log/workflows/`
  (étapes avec niveau, skills, livrables, contrôles, consignes, mémoire du
  vault) ; l'agent `architecture-workflow` la suit sans modification.

Les règles complètes sont dans [`AGENTS.md`](AGENTS.md).

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
| `shared/vault-ontology.json` | Ontologie du vault Obsidian (types de notes, propriétés, relations typées, tags), copiée avec `vault_ontology.py` dans les skills qui déclarent `vault` |
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
