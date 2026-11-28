---
name: markdown-publish
description: "Transforme un Markdown (ou une note Obsidian) en fichier Word, PDF, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail, ou en présentation PowerPoint déléguée à l'agent concepteur-deck installé à part. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt."
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
- **Sorties** : <nom>.docx, <nom>.html, <nom>.xwiki et ses images dans <nom>-xwiki/ ; <nom>.pptx, conçu ou converti par l'agent externe concepteur-deck (installé à part), puis vérifié ; En option : PDF, planches PNG des pages à relire dans .myskills-tmp/<nom>-apercu/.
- **`publish.py`** : Produit Word, HTML ou XWiki à partir d'un Markdown, schémas compris, sans rien publier. Rapport JSON (0 succès, 1 erreur).
- **`pptx_publish.py`** : Délègue la présentation PowerPoint à l'agent externe concepteur-deck, installé à part et appelé par son seul contrat d'interface. Sans --check, vérifie les sources (images en PNG, JPEG ou SVG, textes alternatifs, consignes de visuel connues), écrit en mode convertir la copie de travail dans .myskills-tmp/, trouve l'agent et donne dans le rapport la demande à lui passer (message de passage validé contre le contrat). Avec --check, après l'agent : rouvre le .pptx (diapositives, images, textes alternatifs), valide l'état de relecture contre le contrat, compare le Markdown relu, compte les points [à compléter] et retire les copies .before-*. Rapport JSON (0 succès, 1 erreur).
- **`make_reference.py`** (maintenance du dépôt) : Régénère references/modele.docx aux couleurs de la charte. Pas de rapport (0 succès, 1 erreur).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `diagram-export` (`export.py`, obligatoire) : exporter en image les schémas cités par le Markdown (sources .drawio, .excalidraw, .mmd, .c4).
- **Passe la main** au skill `diagram-export` : exporter les schémas (automatique).
- **Passe la main** à l'agent externe `concepteur-deck` (installé à part, contrat `shared/external/concepteur-deck.contract.json`) : concevoir ou convertir le .pptx : pptx_publish.py prépare la demande, l'agent appelant la lui passe, pptx_publish.py --check vérifie le résultat.
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

La présentation est **déléguée à l'agent externe `concepteur-deck`**
(projet powerpoint-skill, installé à part avec le skill de rendu
`markdown-to-pptx`) : myskills n'en contient rien et ne s'appuie que sur
son contrat, `scripts/lib/concepteur-deck.contract.json` (copie de
`shared/external/`). Un script ne lance pas un agent : trois temps.

```bash
uv run scripts/pptx_publish.py SOURCE.md [--out NOM.pptx] [--mode convertir|concevoir] [--trame NOM] [--template MARQUE.potx]
# passer le champ handoff du rapport, tel quel, à l'agent concepteur-deck
uv run scripts/pptx_publish.py --check NOM.pptx
```

1. **Préparer** : le script vérifie les sources (images PNG, JPEG ou SVG
   avec texte alternatif ; un schéma source ou un bloc Mermaid s'exporte
   d'abord en PNG avec `diagram-export`), trouve l'agent (variable
   `CONCEPTEUR_DECK_AGENT` ou dossiers d'agents de Claude Code, Copilot,
   Kiro, OpenCode ; sinon consigne d'installation) et écrit la demande
   dans `handoff` (message de passage validé contre le contrat).
   - `convertir` (défaut) : un Markdown complet aux conventions du contrat
     (champ `markdown` : front matter, un seul `#`, une section `##` par
     diapositive, consigne `<!-- slide: KIND -->`). L'agent travaille sur
     une copie dans `.myskills-tmp/` : la source reste intacte.
     `presentation.md` de `deck_build.py` (skill `architecture-deck`) suit
     déjà ces conventions.
   - `concevoir` : des sources et un objectif (`--objective`, `--trame`) ;
     l'agent rédige le Markdown du deck à côté du `.pptx` (`NOM.md`).
2. **Déléguer** : passer `handoff` à `concepteur-deck` (sous-agent, ou
   agent à lancer par l'utilisateur si l'outil ne permet pas d'appeler un
   agent). Il génère, relit le rendu (trois tours au plus) et rend ses
   hypothèses et ses points `[à compléter]`.
3. **Vérifier** : `--check` rouvre le `.pptx`, valide l'état de relecture
   (`clean`, `stop` : avertissement, `fix` : erreur) et retire les copies
   `.before-*`. Un `.pptx` non vérifié se signale comme tel.

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
