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
| `agents/` | Les deux agents principaux et les trois exécutants, en format source neutre |
| `shared/references/style.md` | Charte graphique commune aux schémas, copiée dans les skills listés dans `shared/targets.txt` |
| `shared/models.conf` | Modèle utilisé par chaque niveau (simple, moyen, complexe), pour chaque outil |
| `scripts/install.sh` | Installe skills et agents pour chaque outil |
| `scripts/doctor.sh` | Vérifie les outils requis (MarkItDown, Docling, draw.io, Mermaid CLI, LikeC4, Playwright, Pandoc) |
| `tests/` | Documents réels et résultats attendus |

### Agents

| Agent | Rôle | Niveau |
| --- | --- | --- |
| `schema-designer` | Choisit le format de schéma selon le contexte, le public et la destination, découpe le travail et valide le rendu | moyen |
| `document-extractor` | Choisit l'outil de conversion selon le document, découpe le travail et valide le Markdown | moyen |
| `executant-simple` | Actions mécaniques : lancer une conversion ou un export, valider un fichier | simple |
| `executant-moyen` | Rédaction courante : schéma Mermaid ou draw.io, PDF à tableaux, format Obsidian | moyen |
| `executant-complexe` | Actions difficiles : vision, modélisation C4, simplification pour non techniques, relecture visuelle | complexe |

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

Les deux agents principaux classent chaque action (grille dans leur fichier)
et la confient à l'exécutant le moins cher qui convient. En cas d'échec, ils
remontent d'un niveau. Le modèle de chaque niveau se règle dans
`shared/models.conf`, puis `scripts/install.sh` le reporte dans les agents :

| Outil | Par défaut | Effet |
| --- | --- | --- |
| Claude Code | `haiku`, `sonnet`, `opus` | Alias résolus par Claude Code vers la dernière version disponible |
| OpenCode | vide | Modèle de la session ; renseignez `fournisseur/modèle` pour activer les niveaux |
| Kiro | vide | Mode Auto de Kiro, qui choisit le modèle selon la tâche |

Une valeur vide laisse toujours l'outil décider. La grille des niveaux reste
utile dans ce cas : elle découpe le travail et décide quand escalader.

À vérifier à l'étape 4 :

- **Claude Code** : un sous-agent ne peut pas lancer d'autres sous-agents.
  Lancez donc l'agent principal comme session (`claude --agent schema-designer`)
  plutôt que comme sous-agent.
- **GitHub Copilot** lit les agents de `.claude/agents` ; reste à confirmer
  qu'il interprète les alias `haiku`, `sonnet`, `opus`. Sinon, il garde le
  modèle de la session.

## Principes

- La logique métier vit dans les skills ; les agents orchestrent et valident.
- La conversion de documents reste locale, sans service en ligne.
- Un skill repris d'un tiers cite sa source et respecte sa licence.
