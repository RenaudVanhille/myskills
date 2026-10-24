---
name: markdown-publish
description: "Transforme un Markdown (ou une note Obsidian) en fichier Word, PDF, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail, ou en présentation PowerPoint avec le skill markdown-to-pptx installé à part. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt."
---

# markdown-publish

Le chemin `scripts/publish.py` est relatif au dossier de ce skill. Le script
ne publie rien : il produit des fichiers que l'utilisateur importe lui-même.
Pandoc est fourni par le paquet `pypandoc_binary` (`uv run` l'installe), rien
à installer à part.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Markdown ou notes Obsidian, avec leurs images et schémas sources ; Modèle Word ou gabarit PowerPoint .potx (facultatif) ; Vault Obsidian (facultatif).
- **Sorties** : <nom>.docx, <nom>.html, <nom>.xwiki et ses images dans <nom>-xwiki/ ; <nom>.pptx, par le skill externe markdown-to-pptx s'il est installé ; En option : PDF, planches PNG des pages à relire dans .myskills-tmp/<nom>-apercu/.
- **`publish.py`** : Produit Word, HTML ou XWiki à partir d'un Markdown, schémas compris, sans rien publier. Rapport JSON, codes de sortie : 0 tous les documents sont produits ; 1 au moins un document a échoué.
- **`pptx_publish.py`** : Produit une présentation PowerPoint modifiable avec le skill markdown-to-pptx, installé à part et appelé par son seul contrat d'interface : vérifie le Markdown (images en PNG, JPEG ou SVG, textes alternatifs, consignes de visuel connues), lance le skill dans le dossier du Markdown, valide le plan rendu contre le contrat puis rouvre le .pptx (diapositives, images, textes alternatifs). Rapport JSON, codes de sortie : 0 présentation écrite et vérifiée ; 1 Markdown, image ou gabarit invalide, skill markdown-to-pptx introuvable (avec la consigne d'installation), rendu en échec ou présentation incohérente ; aucun .pptx laissé.
- **`make_reference.py`** (maintenance du dépôt) : Régénère references/modele.docx aux couleurs de la charte. Pas de rapport, codes de sortie : 0 modèle écrit.
- **Dépend de** `diagram-export` (`export.py`, obligatoire) : exporter en image les schémas cités par le Markdown (sources .drawio, .excalidraw, .mmd, .c4).
- **Passe la main** au skill `diagram-export` : exporter les schémas (automatique).
- **Passe la main** au skill externe `markdown-to-pptx` (installé à part, contrat `shared/external/markdown-to-pptx.contract.json`) : produire le .pptx (pptx_publish.py le lance).
- **Passe la main** à l'utilisateur : importer les fichiers dans SharePoint, Confluence ou XWiki, ou présenter le .pptx.

## 1. Produire les fichiers

```bash
uv run scripts/publish.py DOC.md [...] --to docx,html,xwiki [--out DOSSIER] \
    [--reference-doc modele.docx] [--toc] [--pdf] [--preview | --preview-all] [--vault VAULT]
```

Avant la conversion, le script :

- exporte en PNG chaque bloc ```mermaid ;
- remplace les images qui pointent vers une source de schéma (`.drawio`,
  `.excalidraw`, `.mmd`) par leur export PNG ;
- ramène la syntaxe Obsidian au Markdown standard : `![[image.png]]`,
  `[[note|texte]]` (devient le texte), callouts (`> [!warning]` devient une
  citation qui commence par **Attention**). `--vault` aide à retrouver les
  pièces jointes rangées ailleurs dans le vault.

Les exports de schémas passent par `diagram-export` (outils locaux, voir
`check-prerequisites`).

## 2. Choisir le format

| Outil cible | Format | Comment l'importer |
| --- | --- | --- |
| Word, envoi par mail | `docx` | tel quel |
| SharePoint | `docx` | déposer dans une bibliothèque de documents, ou ouvrir dans Word en ligne |
| Confluence | `docx` | « Importer un document Word » ; ou `html` ouvert dans le navigateur puis copié-collé dans l'éditeur |
| XWiki | `xwiki` | créer la page, coller le contenu de `.xwiki` en mode source (syntaxe XWiki 2.1), joindre les images du dossier |
| XWiki avec Office Importer | `docx` | importer le fichier |
| Lecture seule, archive | `html` | page autonome, images intégrées |
| Présentation, comité | `pptx` (section 3) | ouvrir dans PowerPoint, tout est modifiable |

Sans précision de l'utilisateur, produisez `docx` et `html` : à eux deux, ils
couvrent SharePoint, Confluence et XWiki.

## 3. Présentation PowerPoint

```bash
uv run scripts/pptx_publish.py DOC.md [--out DOSSIER] [--template MARQUE.potx] [--lang fr|en]
```

Le rendu est fait par le skill `markdown-to-pptx`, **installé à part** :
myskills n'en contient pas le code et ne s'appuie que sur son contrat
d'interface, `scripts/lib/markdown-to-pptx.contract.json` (copie de
`shared/external/`). Le script le trouve par la variable `MD2PPTX_SKILL`
ou dans les dossiers d'installation habituels (Claude Code, Copilot,
OpenCode, Kiro, Hermes) ; sinon il s'arrête avec la consigne
d'installation. Il le lance dans le dossier du Markdown, ce qui lui fait
trouver un dossier `.md2pptx/` de gabarit de marque, valide le plan rendu
contre le contrat, puis relit le `.pptx` (diapositives, images, textes
alternatifs).

Le Markdown suit les conventions du contrat (champ `markdown`) : front
matter (`title`, `subtitle`, `purpose`, `lang`), un seul titre `#`, une
section `##` par diapositive avec une consigne `<!-- slide: KIND -->` sous
son titre, une image PNG par section au plus, avec son texte alternatif.
Un schéma source ou un bloc Mermaid s'exporte d'abord en PNG
(`diagram-export`). Pour un dossier d'architecture, `deck_build.py` du
skill `architecture-deck` écrit ce Markdown à partir du workflow.

## 4. Un Word prêt à l'emploi

Le .docx doit pouvoir partir sans retouche. Le script s'en charge :

- **Modèle** : par défaut `references/modele.docx` (Calibri, titres bleus de
  la charte, tableaux à bordures fines avec ligne d'en-tête colorée et
  répétée, citations encadrées, légendes, A4, numéros de page « Page x / y »).
  Si l'utilisateur a un modèle d'entreprise, passez-le avec
  `--reference-doc` : Pandoc en reprend les styles, l'en-tête et le pied de
  page (pas le contenu, donc pas de page de garde).
- **Images** : schémas et captures à leur taille naturelle, réduits pour
  tenir dans la page, centrés. Le texte alternatif devient une légende
  numérotée (« Figure 1 : ... ») : donnez un texte alternatif parlant à
  chaque image (`![Flux d'un paiement](...)`).
- **Tableaux** : pleine largeur, ligne d'en-tête répétée sur chaque page.
- `--toc` ajoute un sommaire ; Word le remplit à l'ouverture (il demande de
  mettre à jour les champs : répondre oui).

Le modèle se régénère avec `uv run scripts/make_reference.py` si la charte
change.

## 5. Relire le rendu

Avec LibreOffice installé (facultatif, détecté aussi hors du PATH, par
exemple dans `C:\Program Files\LibreOffice`) :

- `--preview` ne rend que les pages à relire (une image, un tableau, ou un
  titre seul en bas de page), assemblées par 4 sur des planches PNG dans
  `.myskills-tmp/<nom>-apercu/` à côté du .docx ; `preview_pages` donne
  leurs numéros. **Ouvrez chaque planche** et vérifiez : image trop grande ou
  coupée, tableau qui déborde, titre seul en bas de page, légende manquante.
  Corrigez la source et relancez, puis supprimez le dossier `.myskills-tmp/`.
  `--preview-all` rend chaque page séparément, si l'utilisateur veut tout
  relire.
- `--pdf` livre aussi un PDF.

Sans LibreOffice, le script le signale et produit le .docx quand même.

## 6. Vérifier les comptes

Le rapport JSON donne, par format, le fichier produit et le nombre d'images
et de tableaux trouvés dedans, comparés au Markdown. Un avertissement signale
une image introuvable, un schéma non exporté ou un écart dans les comptes.
Corrigez la source (chemin d'image, schéma invalide) et relancez.

## 7. Livrer

Indiquez les fichiers produits et, pour chacun, en une ligne, comment
l'importer dans l'outil visé (tableau ci-dessus). Pour XWiki, rappelez que
les images du dossier `<nom>-xwiki/` sont à joindre à la page.
