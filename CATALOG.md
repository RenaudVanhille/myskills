# Catalogue des agents et des skills

Fichier généré par `scripts/build.py` à partir des sections « Contrat » de
`src/agents/*.md` et `skills/*/SKILL.md` : ne pas le modifier à la main.
Un agent ou un outil qui veut appeler myskills y trouve, pour chaque agent
et chaque skill, ce qu'il reçoit, ce qu'il produit, ses rapports et à qui
il passe la main.

## Passage de relais et rapport final des agents

Pour passer la main, si ton outil permet d'appeler un autre agent, envoie-lui
un message avec ces lignes ; sinon, donne ce message à l'utilisateur et
indique-lui l'agent à lancer :

```text
Agent : <nom de l'agent>
Objectif : <ce qu'il faut produire, en une phrase>
Fichiers : <chemins des fichiers d'entrée>
Public : <technique | non technique>
Destination : <Markdown, Obsidian, Word, PowerPoint, Confluence, SharePoint, XWiki>
Sortie : <dossier ou fichier attendu>
Contraintes : <ce qu'il ne faut pas changer, délais, modèle Word...>
```

Ton rapport final suit toujours ce plan, pour qu'un autre agent ou
l'utilisateur le lise de la même façon :

```text
Fichiers produits : <un chemin par ligne>
Outils : <moteur ou format utilisé, et pourquoi en une phrase>
Niveau : <simple | moyen | complexe, le plus haut utilisé>
Corrections : <ce qui a été corrigé>
Reste à faire : <ce qui n'a pas pu être fait, ou « rien »>
Suite : <agent suivant conseillé et message de passage, ou « aucune »>
```

## Agents

### `document-extractor`

Extrait le contenu de documents PDF, DOCX, PPTX, XLSX ou d'images vers Markdown ou Obsidian. Choisit l'outil (MarkItDown, Docling, vision), adapte l'effort de chaque action pour limiter les coûts et valide le résultat avant de le livrer.

**Skills** : `check-prerequisites`, `doc-to-markdown`, `markdown-to-obsidian`

- **Reçoit** : des fichiers PDF, DOCX, PPTX, XLSX ou des images (ou un
  dossier), la cible (Markdown ou vault Obsidian) et un dossier de sortie.
  Les demandes viennent de l'utilisateur ou d'un autre agent, au format de
  passage ci-dessous.
- **Produit** : un Markdown par document, ses images dans `attachments/`, ou
  des notes rangées dans le vault ; jamais de Word, HTML ou page de wiki.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | un schéma en image doit devenir modifiable | l'image extraite, le Markdown qui la contient, le public, la destination |
| `document-publisher` | le Markdown obtenu doit partir en Word, HTML ou XWiki | les Markdown produits, l'outil cible, le modèle Word s'il y en a un |

### `document-publisher`

Transforme une documentation Markdown ou Obsidian en fichiers à publier : Word prêt à l'emploi, page HTML autonome ou page XWiki, schémas compris, pour SharePoint, Confluence ou XWiki. Ne publie rien en ligne. Adapte l'effort de chaque action pour limiter les coûts et relit le rendu avant de livrer.

**Skills** : `check-prerequisites`, `markdown-publish`, `diagram-export`

- **Reçoit** : des fichiers Markdown ou des notes Obsidian (et le vault),
  l'outil cible (Word, SharePoint, Confluence, XWiki) et, s'il existe, un
  modèle Word. Les demandes viennent de l'utilisateur ou d'un autre agent, au
  format de passage ci-dessous.
- **Produit** : des fichiers `.docx`, `.html`, `.xwiki` (et ses images), en
  option un PDF ; rien n'est publié en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | un schéma ne s'exporte pas ou doit être corrigé | le fichier source du schéma, le message d'erreur, la destination |
| `document-extractor` | la source n'est pas encore en Markdown (PDF, Office) | le document, la cible Markdown, le dossier de travail |

### `schema-designer`

Conçoit des schémas d'ingénierie logicielle. Choisit le format (Mermaid, draw.io, Excalidraw, C4 avec LikeC4) selon le contexte, le public et la destination, adapte l'effort de chaque action pour limiter les coûts et valide le résultat avant de le livrer.

**Skills** : `check-prerequisites`, `diagram-brief`, `mermaid-diagram`, `drawio-diagram`, `excalidraw-diagram`, `c4-architecture`, `diagram-export`

- **Reçoit** : un contexte (description, code, ADR, Markdown, image d'un
  schéma existant), et si possible le public, la destination et le dossier de
  sortie. Les demandes viennent de l'utilisateur ou d'un autre agent, au
  format de passage ci-dessous.
- **Produit** : le fichier source du schéma (bloc Mermaid, `.drawio`,
  `.excalidraw` et sa description `.json`, ou modèle LikeC4) et ses exports
  (PNG, SVG, PDF) ; pour Confluence avec draw.io, le `.drawio` et le
  `.drawio.png`.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `document-extractor` | le contexte est un document à convertir d'abord (PDF, Office) | le document, la cible Markdown, le dossier de travail |
| `document-publisher` | le schéma doit être intégré dans un Word, une page HTML ou XWiki | le Markdown qui référence le schéma, la source et l'export, l'outil cible |

## Skills

### `c4-architecture`

Modélise une architecture logicielle selon le modèle C4 (contexte, conteneurs, composants) avec LikeC4, valide le modèle et exporte une image par vue. À utiliser pour les schémas d'architecture.

- **Entrées** : la décision de `diagram-brief`, et le code, la configuration ou la description de l'architecture.
- **Sorties** : un dossier de modèle LikeC4 (`specification.c4`, `model.c4`) et un PNG par vue.
- **Rapport** : aucun script propre ; la validation et les exports passent par `diagram-export` (`export.py DOSSIER`).
- **Passe la main** : à `diagram-export` pour valider et exporter ; à `excalidraw-diagram` pour une vue destinée à un public non technique.

### `check-prerequisites`

Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (MarkItDown, Docling, draw.io Desktop, Node.js, navigateur) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable.

- **Entrées** : un groupe, `extraction`, `schemas`, `publication` ou `tout` (défaut).
- **Sorties** : aucun fichier.
- **Rapport `doctor.py`** (texte, pas de JSON) : une ligne par outil, `[ok]`, `[manquant]` ou `[facultatif]`, suivie de la commande d'installation.
- **Codes de sortie** : 0 si tous les outils obligatoires sont présents, 1 sinon.
- **Passe la main** : à l'utilisateur, qui installe lui-même l'outil manquant ; rien n'est installé sans son accord.

### `diagram-brief`

Grille de choix du format de schéma (Mermaid, draw.io, Excalidraw, C4) selon le public, la destination (Markdown, Obsidian, Word, PowerPoint, Confluence) et le type de schéma. À utiliser avant de produire un schéma.

- **Entrées** : le contexte du schéma (description, code, ADR, Markdown, image) et ce que l'on sait du public et de la destination.
- **Sorties** : aucun fichier. Une décision : public, destination, type de schéma, format, skill à appliquer, et la phrase « message principal, 3 à 7 éléments, ce qu'on laisse de côté ».
- **Rapport** : aucun script.
- **Passe la main** : au skill du format choisi, `mermaid-diagram`, `drawio-diagram`, `excalidraw-diagram` ou `c4-architecture`.

### `diagram-export`

Exporte un schéma (draw.io, Mermaid, Excalidraw, LikeC4) en PNG, SVG ou PDF pour Word, PowerPoint, Confluence ou un Markdown, ou vérifie seulement qu'il se rend. À utiliser pour intégrer un schéma dans un document ou valider sa syntaxe.

- **Entrées** : fichiers `.drawio`, `.mmd`, `.mermaid`, `.md` (blocs ```mermaid), `.excalidraw`, `.c4` ou un dossier LikeC4.
- **Sorties** : les images à côté de la source ou dans `--out` (voir le tableau ci-dessus) ; rien avec `--check`.
- **Rapport `export.py`** (liste JSON, un objet par source) : `source`, `format`, `outputs`, `error` ; si le rendu a réussi : `rendered`.
- **Codes de sortie** : 1 si une source échoue, 0 sinon.
- **Passe la main** : à `check-prerequisites` (groupe `schemas`) si un outil manque ; au skill du format pour corriger une erreur de syntaxe.

### `doc-to-markdown`

Convertit un document PDF, DOCX, PPTX, XLSX ou une image en Markdown propre, en local, avec les images extraites dans attachments/. À utiliser pour extraire le contenu d'un document vers du Markdown.

- **Entrées** : fichiers PDF, DOCX, PPTX, XLSX, XLS, DOC, PPT ou images (PNG, JPG, GIF, BMP, TIFF, WEBP) ; dossiers acceptés par `classify.py`.
- **Sorties** : `DOSSIER/<nom>.md` et ses images dans `DOSSIER/attachments/<nom>-N.<ext>`, liées en relatif.
- **Rapport `convert.py`** (liste JSON, un objet par fichier) : `input`, `output`, `type`, `engine`, `pages`, `images`, `needs_vision`, `warnings` ; avec `--classify` : `classification`.
- **Rapport `validate.py`** (liste JSON, un objet par fichier) : `file`, `ok`, `errors`, `warnings`.
- **Rapport `classify.py`** (liste JSON, un objet par fichier) : `input`, `type`, `type_confidence`, `domaine`, `domaine_confidence`, `tables`, `engine`, `method`, `warnings`.
- **Échec sur un fichier** : l'objet ne contient que `input` (ou `file`) et `error`.
- **Codes de sortie** : 0 si tout a réussi ; 1 si un fichier a échoué (`convert.py`, `classify.py`) ou contient une erreur (`validate.py`).
- **Passe la main** : à `markdown-to-obsidian` si la cible est un vault ; à l'agent `schema-designer` pour recréer un schéma modifiable à partir d'une image.

### `drawio-diagram`

Crée ou modifie un schéma draw.io (.drawio), le vérifie et l'exporte en PNG, SVG ou PDF modifiables. À utiliser pour les schémas destinés à Word, PowerPoint ou Confluence, ou qui demandent une mise en page précise.

- **Entrées** : la décision de `diagram-brief` et le contenu à représenter, ou un `.drawio` existant à modifier.
- **Sorties** : un fichier `.drawio` en XML clair ; après export, `<nom>.drawio.png` (ou `.svg`, `.pdf`).
- **Rapport `check_drawio.py`** (liste JSON, un objet par fichier) : `file`, `pages`, `shapes`, `errors`, `warnings`.
- **Codes de sortie** : `check_drawio.py` 1 si un fichier contient une erreur, 0 sinon.
- **Passe la main** : à `diagram-export` pour l'export et la relecture de l'image.

### `excalidraw-diagram`

Crée un schéma Excalidraw au style dessiné à la main à partir d'une description simple, le rend en PNG ou SVG et le relit. À utiliser pour les publics non techniques, les ateliers et les vues d'ensemble.

- **Entrées** : la décision de `diagram-brief`, puis une description JSON du schéma (`title`, `audience`, `elements`).
- **Sorties** : `<sujet>.excalidraw`, à côté de sa description `<sujet>.json` ; après export, `<sujet>.excalidraw.png` ou `.svg`.
- **Rapport `excalidraw_build.py`** (objet JSON) : `input`, `output`, `elements`, `errors`, `warnings`.
- **Codes de sortie** : `excalidraw_build.py` 1 si la description est illisible ou contient une erreur, 0 sinon.
- **Passe la main** : à `diagram-export` pour le rendu et la relecture de l'image.

### `markdown-publish`

Transforme un Markdown (ou une note Obsidian) en fichier Word, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt.

- **Entrées** : fichiers Markdown ou notes Obsidian, avec leurs images et leurs schémas sources ; en option un modèle Word (`--reference-doc`) et le vault (`--vault`).
- **Sorties** : dans `--out`, `<nom>.docx`, `<nom>.html` et `<nom>.xwiki` avec ses images dans `<nom>-xwiki/` ; en option un PDF et un aperçu PNG par page dans `.myskills-tmp/<nom>-apercu/`.
- **Rapport `publish.py`** (liste JSON, un objet par document) : `input`, `outputs`, `diagrams_exported`, `warnings` ; si un format échoue : `error`. Chaque élément de `outputs` contient `format`, `file`, `images`, `tables`, et selon les options `pdf` ou `preview`.
- **Codes de sortie** : `publish.py` 1 si un document échoue, 0 sinon.
- **Maintenance** : `make_reference.py` régénère `references/modele.docx` ; pas de rapport JSON.
- **Passe la main** : à `diagram-export` pour les schémas (automatique) ; à l'utilisateur, qui importe lui-même les fichiers dans SharePoint, Confluence ou XWiki.

### `markdown-to-obsidian`

Met un fichier Markdown au format Obsidian : frontmatter, embeds d'images, wikilinks, callouts, pièces jointes copiées dans le vault. À utiliser quand la cible est un vault Obsidian.

- **Entrées** : notes Markdown (sortie de `doc-to-markdown` ou existantes) et, en option, le dossier du vault.
- **Sorties** : la note au format Obsidian, sur place ou dans `VAULT/<dossier>/`, et ses images dans le dossier de pièces jointes du vault ; avec `--move`, plus rien dans le dossier de travail.
- **Rapport `obsidianize.py`** (liste JSON, un objet par note) : `input`, `output`, `embeds`, `wikilinks`, `callouts`, `attachments_copied`, `missing` ; avec `--classify` : `classification`.
- **Rapport `vault_profile.py`** (objet JSON) : `vault`, `notes`, `tags`, `folders`, `attachments`.
- **Échec sur un fichier** : l'objet ne contient que `input` et `error`.
- **Codes de sortie** : `obsidianize.py` 1 si une note est introuvable ou si une image manque (`missing`) ; `vault_profile.py` 0.
- **Passe la main** : à `doc-to-markdown` (`validate.py --obsidian`) pour la validation ; à `markdown-publish` pour un export Word, HTML ou XWiki.

### `mermaid-diagram`

Écrit des schémas Mermaid (flux, séquence, états, classes, modèle de données) dans un Markdown ou un fichier .mmd et vérifie qu'ils se rendent. À utiliser pour la documentation dans un dépôt ou Obsidian.

- **Entrées** : la décision de `diagram-brief` et le contenu à représenter.
- **Sorties** : un bloc ```mermaid dans un Markdown existant, ou un fichier `.mmd`.
- **Rapport** : aucun script propre ; la validation passe par `diagram-export` (`export.py --check`).
- **Passe la main** : à `diagram-export` pour vérifier le rendu et pour les exports PNG ou SVG destinés à Word, PowerPoint ou Confluence.
