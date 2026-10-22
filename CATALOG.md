# Catalogue des agents et des skills

Fichier généré par `scripts/build.py` : ne pas le modifier à la main. Les
contrats qui font foi sont en JSON : `skills/<nom>/contract.json`,
`src/agents/<nom>.contract.json` et les schémas de `shared/schemas/`. La
version machine de ce catalogue est [`catalog.json`](catalog.json).

## Messages entre agents

- Message de passage : [`shared/schemas/handoff.schema.json`](shared/schemas/handoff.schema.json).
  Champs : `agent` (document-extractor | schema-designer | document-publisher), `objective` (texte), `files` (liste), `audience` (technique | non technique), `destination` (markdown | obsidian | word | powerpoint | confluence | sharepoint | xwiki | html), `output` (texte) ; facultatifs : `constraints`.
- Rapport final : [`shared/schemas/agent-report.schema.json`](shared/schemas/agent-report.schema.json).
  Champs : `agent` (document-extractor | schema-designer | document-publisher), `status` (ok | partiel | echec), `files` (liste), `tools` (texte), `level` (simple | moyen | complexe), `corrections` (liste), `todo` (liste), `next` (objet).

## Agents

### `document-extractor`

Extrait le contenu de documents PDF, DOCX, PPTX, XLSX ou d'images vers Markdown ou Obsidian. Choisit l'outil (MarkItDown, Docling, vision), adapte l'effort de chaque action pour limiter les coûts et valide le résultat avant de le livrer.

**Skills** : `check-prerequisites`, `doc-to-markdown`, `markdown-to-obsidian`

Généré depuis `src/agents/document-extractor.contract.json`, qui fait foi.

- **Reçoit** : Fichiers PDF, DOCX, PPTX, XLSX, images, ou un dossier ; La cible : Markdown ou vault Obsidian ; Un dossier de sortie (défaut : à côté du document).
- **Produit** : Un Markdown par document et ses images dans attachments/ ; Ou des notes rangées dans le vault Obsidian.
- **Ne fait jamais** : Produire du Word, du HTML ou une page de wiki ; Envoyer un document à un service en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | un schéma en image doit devenir modifiable | l'image extraite et le Markdown qui la contient ; le public et la destination |
| `document-publisher` | le Markdown obtenu doit partir en Word, HTML ou XWiki | les Markdown produits ; l'outil cible ; le modèle Word s'il y en a un |

### `document-publisher`

Transforme une documentation Markdown ou Obsidian en fichiers à publier : Word prêt à l'emploi, page HTML autonome ou page XWiki, schémas compris, pour SharePoint, Confluence ou XWiki. Ne publie rien en ligne. Adapte l'effort de chaque action pour limiter les coûts et relit le rendu avant de livrer.

**Skills** : `check-prerequisites`, `markdown-publish`, `diagram-export`

Généré depuis `src/agents/document-publisher.contract.json`, qui fait foi.

- **Reçoit** : Des fichiers Markdown ou des notes Obsidian (et le vault) ; L'outil cible : Word, SharePoint, Confluence ou XWiki ; Un modèle Word, s'il existe.
- **Produit** : Des fichiers .docx, .html, .xwiki et ses images ; En option un PDF.
- **Ne fait jamais** : Publier en ligne : l'utilisateur importe lui-même les fichiers.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | un schéma ne s'exporte pas ou doit être corrigé | le fichier source du schéma ; le message d'erreur ; la destination |
| `document-extractor` | la source n'est pas encore en Markdown (PDF, Office) | le document ; la cible Markdown et le dossier de travail |

### `schema-designer`

Conçoit des schémas d'ingénierie logicielle. Choisit le format (Mermaid, draw.io, Excalidraw, C4 avec LikeC4) selon le contexte, le public et la destination, adapte l'effort de chaque action pour limiter les coûts et valide le résultat avant de le livrer.

**Skills** : `check-prerequisites`, `diagram-brief`, `mermaid-diagram`, `drawio-diagram`, `excalidraw-diagram`, `c4-architecture`, `diagram-export`

Généré depuis `src/agents/schema-designer.contract.json`, qui fait foi.

- **Reçoit** : Un contexte : description, code, ADR, Markdown ou image d'un schéma existant ; Si possible le public, la destination et le dossier de sortie.
- **Produit** : La source du schéma : bloc Mermaid, .drawio, .excalidraw et sa description .json, ou modèle LikeC4 ; Ses exports PNG, SVG ou PDF ; pour Confluence avec draw.io, le .drawio et le .drawio.png.
- **Ne fait jamais** : Modifier un fichier qu'il n'a pas créé, sauf le schéma à corriger ; Envoyer un schéma à un service en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `document-extractor` | le contexte est un document à convertir d'abord (PDF, Office) | le document ; la cible Markdown et le dossier de travail |
| `document-publisher` | le schéma doit être intégré dans un Word, une page HTML ou XWiki | le Markdown qui référence le schéma ; la source et l'export ; l'outil cible |

## Skills

### `c4-architecture`

Modélise une architecture logicielle selon le modèle C4 (contexte, conteneurs, composants) avec LikeC4, valide le modèle et exporte une image par vue. À utiliser pour les schémas d'architecture.

Généré depuis [`contract.json`](skills/c4-architecture/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Décision de diagram-brief ; Code, configuration ou description de l'architecture.
- **Sorties** : Dossier LikeC4 : specification.c4 et model.c4 ; Un PNG par vue (après export).
- **Scripts** : aucun ; la validation passe par le skill suivant.
- **Passe la main** au skill `diagram-export` : valider le modèle et exporter les vues.
- **Passe la main** au skill `excalidraw-diagram` : une vue est destinée à un public non technique.

### `check-prerequisites`

Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (MarkItDown, Docling, draw.io Desktop, Node.js, navigateur) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable.

Généré depuis [`contract.json`](skills/check-prerequisites/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Un groupe : extraction, schemas, publication ou tout (défaut).
- **Sorties** : Aucun fichier.
- **`doctor.py`** : Vérifie les outils locaux et affiche la commande d'installation des manquants.
  - Rapport (texte) : Une ligne par outil : [ok], [manquant] ou [facultatif], suivie de la commande d'installation.
  - Codes de sortie : 0 tous les outils obligatoires sont présents ; 1 au moins un outil manque.
- **Passe la main** à l'utilisateur : un outil manque : il l'installe lui-même, rien n'est installé sans son accord.

### `diagram-brief`

Grille de choix du format de schéma (Mermaid, draw.io, Excalidraw, C4) selon le public, la destination (Markdown, Obsidian, Word, PowerPoint, Confluence) et le type de schéma. À utiliser avant de produire un schéma.

Généré depuis [`contract.json`](skills/diagram-brief/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Contexte du schéma : description, code, ADR, Markdown ou image ; Ce que l'on sait du public et de la destination.
- **Sorties** : Aucun fichier : une décision (public, destination, type, format, skill) et la phrase message principal / 3 à 7 éléments / ce qu'on laisse de côté.
- **Scripts** : aucun ; la validation passe par le skill suivant.
- **Passe la main** au skill `mermaid-diagram` : séquence, états, classes, données, ou flux simple dans un dépôt ou Obsidian.
- **Passe la main** au skill `drawio-diagram` : public technique, Word, PowerPoint ou Confluence, mise en page précise.
- **Passe la main** au skill `excalidraw-diagram` : public non technique, atelier, vue d'ensemble.
- **Passe la main** au skill `c4-architecture` : architecture logicielle à plusieurs vues ou niveaux.

### `diagram-export`

Exporte un schéma (draw.io, Mermaid, Excalidraw, LikeC4) en PNG, SVG ou PDF pour Word, PowerPoint, Confluence ou un Markdown, ou vérifie seulement qu'il se rend. À utiliser pour intégrer un schéma dans un document ou valider sa syntaxe.

Généré depuis [`contract.json`](skills/diagram-export/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Fichiers .drawio, .mmd, .mermaid, .md (blocs mermaid), .excalidraw, .c4 ou dossier LikeC4.
- **Sorties** : Images à côté de la source ou dans --out : <nom>.drawio.png, <nom>-1.png, <nom>.excalidraw.svg, un PNG par vue LikeC4 ; Rien avec --check.
- **`export.py`** : Exporte les schémas en PNG, SVG ou PDF, ou vérifie leur rendu.
  - Rapport (liste JSON) : Un objet par source ; error vaut null si tout va bien.
  - Champs : `source` (texte), `format` (png | svg | pdf), `outputs` (liste), `error` (texte ou null) ; facultatifs : `rendered`.
  - Codes de sortie : 0 toutes les sources sont rendues ; 1 au moins une source échoue.
- **Passe la main** au skill `check-prerequisites` : un outil de rendu manque (groupe schemas).

### `doc-to-markdown`

Convertit un document PDF, DOCX, PPTX, XLSX ou une image en Markdown propre, en local, avec les images extraites dans attachments/. À utiliser pour extraire le contenu d'un document vers du Markdown.

Généré depuis [`contract.json`](skills/doc-to-markdown/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Fichiers PDF, DOCX, PPTX, XLSX, XLS, DOC, PPT ; Images PNG, JPG, GIF, BMP, TIFF, WEBP ; Dossiers (classify.py seulement).
- **Sorties** : DOSSIER/<nom>.md ; DOSSIER/attachments/<nom>-N.<ext>, liées en relatif depuis le Markdown.
- **`convert.py`** : Convertit les documents en Markdown, en local.
  - Rapport (liste JSON) : Un objet par fichier.
  - Champs : `input` (texte), `output` (texte), `type` (image | pdf | office | autre), `engine` (copie | markitdown | docling), `pages` (entier ou null), `images` (entier), `needs_vision` (booléen), `warnings` (liste) ; facultatifs : `classification`.
  - Ou, en cas d'échec : `input` (texte), `error` (texte).
  - Codes de sortie : 0 tous les fichiers sont convertis ; 1 au moins un fichier a échoué (objet avec error).
- **`validate.py`** : Vérifie un Markdown converti, ou une note Obsidian avec --obsidian.
  - Rapport (liste JSON) : Un objet par fichier ; un fichier introuvable donne ok false.
  - Champs : `file` (texte), `ok` (booléen), `errors` (liste), `warnings` (liste).
  - Codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **`classify.py`** : Classe des documents (type, domaine, moteur conseillé) avec le modèle local Laya, ou par règles.
  - Rapport (liste JSON) : Un objet par fichier ; type et domaine valent null sous le seuil de confiance.
  - Champs : `input` (texte), `type` (specification | architecture | procedure | compte-rendu | presentation | contrat | rapport | autre | null), `type_confidence` (nombre ou null), `domaine` (texte ou null), `domaine_confidence` (nombre ou null), `tables` (nombre ou null), `engine` (markitdown | docling), `method` (texte), `warnings` (liste).
  - Ou, en cas d'échec : `input` (texte), `error` (texte).
  - Codes de sortie : 0 tous les fichiers sont classés ; 1 au moins un fichier a échoué.
- **Passe la main** au skill `markdown-to-obsidian` : la cible est un vault Obsidian.
- **Passe la main** à l'agent `schema-designer` : un schéma en image doit devenir modifiable.

### `drawio-diagram`

Crée ou modifie un schéma draw.io (.drawio), le vérifie et l'exporte en PNG, SVG ou PDF modifiables. À utiliser pour les schémas destinés à Word, PowerPoint ou Confluence, ou qui demandent une mise en page précise.

Généré depuis [`contract.json`](skills/drawio-diagram/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Décision de diagram-brief et contenu à représenter ; Ou un .drawio existant à modifier.
- **Sorties** : <nom>.drawio en XML clair ; Après export : <nom>.drawio.png, .svg ou .pdf.
- **`check_drawio.py`** : Vérifie un fichier draw.io avant export.
  - Rapport (liste JSON) : Un objet par fichier.
  - Champs : `file` (texte), `pages` (entier), `shapes` (entier), `errors` (liste), `warnings` (liste).
  - Codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.

### `excalidraw-diagram`

Crée un schéma Excalidraw au style dessiné à la main à partir d'une description simple, le rend en PNG ou SVG et le relit. À utiliser pour les publics non techniques, les ateliers et les vues d'ensemble.

Généré depuis [`contract.json`](skills/excalidraw-diagram/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Décision de diagram-brief ; Description JSON du schéma : title, audience, elements.
- **Sorties** : <sujet>.excalidraw, à côté de sa description <sujet>.json ; Après export : <sujet>.excalidraw.png ou .svg.
- **`excalidraw_build.py`** : Construit la scène Excalidraw à partir de la description JSON.
  - Rapport (objet JSON) : Un objet ; si la description est illisible, seulement input et errors.
  - Champs : `input` (texte), `output` (texte), `elements` (entier), `errors` (liste), `warnings` (liste).
  - Ou, en cas d'échec : `input` (texte), `errors` (liste).
  - Codes de sortie : 0 scène produite sans erreur ; 1 description illisible ou erreur.
- **Passe la main** au skill `diagram-export` : rendre et relire l'image.

### `markdown-publish`

Transforme un Markdown (ou une note Obsidian) en fichier Word, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt.

Généré depuis [`contract.json`](skills/markdown-publish/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Markdown ou notes Obsidian, avec leurs images et schémas sources ; Modèle Word (facultatif) ; Vault Obsidian (facultatif).
- **Sorties** : <nom>.docx, <nom>.html, <nom>.xwiki et ses images dans <nom>-xwiki/ ; En option : PDF, aperçu PNG par page dans .myskills-tmp/<nom>-apercu/.
- **`publish.py`** : Produit Word, HTML ou XWiki à partir d'un Markdown, schémas compris, sans rien publier.
  - Rapport (liste JSON) : Un objet par document.
  - Champs : `input` (texte), `outputs` (liste), `diagrams_exported` (entier), `warnings` (liste) ; facultatifs : `error`.
  - Ou, en cas d'échec : `input` (texte), `error` (texte).
  - Codes de sortie : 0 tous les documents sont produits ; 1 au moins un document a échoué.
- **`make_reference.py`** (maintenance du dépôt) : Régénère references/modele.docx aux couleurs de la charte.
  - Codes de sortie : 0 modèle écrit.
- **Passe la main** au skill `diagram-export` : exporter les schémas (automatique).
- **Passe la main** à l'utilisateur : importer les fichiers dans SharePoint, Confluence ou XWiki.

### `markdown-to-obsidian`

Met un fichier Markdown au format Obsidian : frontmatter, embeds d'images, wikilinks, callouts, pièces jointes copiées dans le vault. À utiliser quand la cible est un vault Obsidian.

Généré depuis [`contract.json`](skills/markdown-to-obsidian/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Notes Markdown (sortie de doc-to-markdown ou existantes) ; Dossier du vault Obsidian (facultatif).
- **Sorties** : Note au format Obsidian, sur place ou dans VAULT/<dossier>/ ; Images dans le dossier de pièces jointes du vault ; Avec --move : rien ne reste dans le dossier de travail.
- **`obsidianize.py`** : Met des notes au format Obsidian et les range dans le vault.
  - Rapport (liste JSON) : Un objet par note.
  - Champs : `input` (texte), `output` (texte), `embeds` (entier), `wikilinks` (entier), `callouts` (entier), `attachments_copied` (entier), `missing` (liste) ; facultatifs : `classification`, `classification_warning`.
  - Ou, en cas d'échec : `input` (texte), `error` (texte).
  - Codes de sortie : 0 toutes les notes sont traitées ; 1 une note est introuvable ou une image manque (missing).
- **`vault_profile.py`** : Lit le vault (lecture seule) : tags, dossiers, dossier des pièces jointes.
  - Rapport (objet JSON) : Un objet ; tags donne le nombre de notes par tag.
  - Champs : `vault` (texte), `notes` (entier), `tags` (objet), `folders` (objet), `attachments` (texte ou null).
  - Ou, en cas d'échec : `error` (texte).
  - Codes de sortie : 0 profil produit ; 2 vault introuvable.
- **Passe la main** au skill `doc-to-markdown` : valider la note avec validate.py --obsidian.
- **Passe la main** au skill `markdown-publish` : exporter la note en Word, HTML ou XWiki.

### `mermaid-diagram`

Écrit des schémas Mermaid (flux, séquence, états, classes, modèle de données) dans un Markdown ou un fichier .mmd et vérifie qu'ils se rendent. À utiliser pour la documentation dans un dépôt ou Obsidian.

Généré depuis [`contract.json`](skills/mermaid-diagram/contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Décision de diagram-brief ; Contenu à représenter.
- **Sorties** : Bloc ```mermaid dans un Markdown, ou fichier .mmd.
- **Scripts** : aucun ; la validation passe par le skill suivant.
- **Passe la main** au skill `diagram-export` : vérifier le rendu (--check) ou exporter en PNG ou SVG.
