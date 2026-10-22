# myskills

Skills et agents pour l'ingénierie logicielle, utilisables dans **GitHub
Copilot**, **Claude**, **OpenCode** et **Kiro** à partir d'une source unique :

- **Extraction documentaire** : PDF, DOCX, PPTX, XLSX, images vers Markdown ou
  Obsidian.
- **Schémas** : draw.io, Excalidraw, C4, Mermaid, adaptés à un public
  technique ou non, pour Markdown, Office et Confluence.

## Contenu

| Dossier | Rôle |
| --- | --- |
| `skills/<nom>/SKILL.md` | Un skill au format [Agent Skills](https://agentskills.io), avec `references/` et `scripts/` |
| `agents/` | Les deux agents, en format source neutre |
| `shared/references/style.md` | Charte graphique commune aux schémas, copiée dans les skills listés dans `shared/targets.txt` |
| `scripts/install.sh` | Installe skills et agents pour chaque outil |
| `scripts/doctor.sh` | Vérifie les outils requis (MarkItDown, Docling, draw.io, Mermaid CLI, LikeC4, Playwright, Pandoc) |
| `tests/` | Documents réels et résultats attendus |

### Agents

| Agent | Rôle |
| --- | --- |
| `schema-designer` | Choisit le format de schéma selon le contexte, le public et la destination, puis valide le rendu |
| `document-extractor` | Choisit l'outil de conversion selon le document, puis valide le Markdown |

### Skills

| Skill | Rôle |
| --- | --- |
| `doc-to-markdown` | Document vers Markdown (MarkItDown, Docling, vision) |
| `markdown-to-obsidian` | Markdown vers format Obsidian |
| `diagram-brief` | Grille de choix du format de schéma |
| `drawio-diagram` | Schémas draw.io et exports |
| `excalidraw-diagram` | Schémas Excalidraw pour publics non techniques |
| `c4-architecture` | Modèle C4 en LikeC4 ou Mermaid |
| `mermaid-diagram` | Schémas Mermaid dans le Markdown |
| `diagram-export` | Exports PNG/SVG pour Office et Confluence |
| `markdown-publish` | Markdown vers Confluence ou Word |

## Installation

```bash
# Dans un projet (défaut : dossier courant)
scripts/install.sh --project ~/code/mon-projet

# Pour tous vos projets
scripts/install.sh --global

# Seulement certains outils, en simulation
scripts/install.sh --tools copilot,kiro --dry-run

# Vérifier les prérequis
scripts/doctor.sh            # ou : extraction | schemas | publication
```

### Où chaque outil trouve les fichiers

| Outil | Skills (projet) | Agents (projet) | Global |
| --- | --- | --- | --- |
| Claude | `.claude/skills` | `.claude/agents` | `~/.claude/...` |
| GitHub Copilot | `.claude/skills` | `.claude/agents` | `~/.copilot/skills`, `~/.claude/agents` |
| OpenCode | `.claude/skills` | `.opencode/agents` | `~/.claude/skills`, `~/.config/opencode/agents` |
| Kiro | `.kiro/skills` | `.kiro/agents` (skills déclarés en `skill://`) | `~/.kiro/...` |

Sur claude.ai, importez un skill en zippant son dossier `skills/<nom>/`.

## Niveaux et coûts

Aucun modèle n'est imposé : chaque outil garde le modèle de la session (ou
son mode automatique, comme Auto dans Kiro). Pour limiter les coûts, chaque
agent classe ses actions en trois niveaux (simple, moyen, complexe) avec une
grille, et adapte son effort en conséquence. Quand l'outil permet de lancer un
sous-agent sur un autre modèle (par exemple `haiku` ou `opus` dans Claude
Code), l'agent l'utilise pour les actions simples ou complexes.

## Principes

- La logique métier vit dans les skills ; les agents orchestrent et valident.
- La conversion de documents reste locale, sans service en ligne.
- Un skill repris d'un tiers cite sa source et respecte sa licence.
