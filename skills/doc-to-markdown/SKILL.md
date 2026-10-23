---
name: doc-to-markdown
description: "Convertit un document PDF (y compris scanné, par OCR), DOCX, PPTX, XLSX ou une image en Markdown propre, en local, avec les images extraites dans attachments/. À utiliser pour extraire le texte, les tableaux ou les images d'un document vers du Markdown."
---

# doc-to-markdown

Convertit un document en Markdown sans l'envoyer à un service en ligne. Les
chemins `scripts/...` sont relatifs au dossier de ce skill. Les scripts
installent eux-mêmes leurs dépendances via `uv run` ; à défaut, lancez-les avec
`python` après `pip install "markitdown[docx,pptx,xlsx,pdf]" pypdf`.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Fichiers PDF, DOCX, PPTX, XLSX, XLS, DOC, PPT ; Images PNG, JPG, GIF, BMP, TIFF, WEBP ; Dossiers.
- **Sorties** : DOSSIER/<nom>.md ; DOSSIER/attachments/<nom>-N.<ext>, liées en relatif depuis le Markdown ; DOSSIER/.myskills-tmp/<nom>-pages/page-N.png : pages à transcrire par vision, à supprimer ensuite.
- **`convert.py`** : Convertit les documents en Markdown, en local. Rapport JSON, codes de sortie : 0 tous les fichiers sont convertis ; 1 au moins un fichier a échoué (error dans son résultat, repris dans errors).
- **`validate.py`** : Vérifie un Markdown converti, ou une note Obsidian avec --obsidian. Rapport JSON, codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **`classify.py`** : Classe des documents (type, domaine, moteur conseillé) avec le modèle local Laya, ou par règles. Rapport JSON, codes de sortie : 0 tous les fichiers sont classés ; 1 au moins un fichier a échoué.
- **Passe la main** au skill `markdown-to-obsidian` : la cible est un vault Obsidian.
- **Passe la main** à l'agent `schema-designer` : un schéma en image doit devenir modifiable.

## 0. Trier un lot (optionnel)

Pour un lot de documents, ou quand l'utilisateur veut connaître le type et le
domaine de chacun, classez-les d'abord en local avec le petit modèle de
décision [Laya](https://github.com/NandhaKishorM/laya) (Apache-2.0, CPU) :

```bash
uv run scripts/classify.py DOSSIER|DOCUMENT [...] [--domains a,b,c]
```

Le rapport JSON donne, par fichier, `type` (specification, architecture,
procedure, compte-rendu, presentation, contrat, rapport, autre), `domaine`
(liste par défaut ou `--domains`), `tables` (probabilité de tableaux ou de
colonnes, PDF seulement) et `engine` conseillé. Un type ou un domaine dont la
confiance est sous 0,5 reste vide et le rapport le signale : décidez alors en
lisant le document. Premier lancement long (PyTorch CPU puis ~1,3 Go de
modèle, téléchargés une fois). Si le modèle ne peut pas être chargé, le script
se replie sur des règles simples (`method: regles`) au lieu d'échouer.

Pour ne lancer qu'une commande, passez plutôt `--classify` à `convert.py` :
le classement est ajouté au rapport de conversion et oriente le moteur.

## 1. Convertir

```bash
uv run scripts/convert.py DOCUMENT [DOCUMENT ...] --out DOSSIER
```

Le script choisit le moteur (`--engine auto`, par défaut) :

| Document | Moteur | Pourquoi |
| --- | --- | --- |
| DOCX, PPTX, XLSX | MarkItDown | Rapide, garde titres, tableaux et images |
| PDF avec texte | MarkItDown | Rapide |
| PDF scanné (pages sans texte) | Docling | OCR ; repli sur MarkItDown si Docling échoue |
| Image | Copie dans `attachments/` | Contenu à transcrire par vision (étape 3) |

Avec `--classify`, un PDF que Laya juge riche en tableaux ou en colonnes part
aussi sur Docling. Forcez Docling avec `--engine docling` pour un PDF riche en tableaux ou en
colonnes que MarkItDown a mal rendu. Premier lancement de Docling long
(~2 Go de modèles téléchargés une fois).

Le script écrit `DOSSIER/<nom>.md`, extrait les images dans
`DOSSIER/attachments/` et affiche un rapport JSON par fichier : `engine`,
`pages`, `images`, `needs_vision`, `warnings`, `hints`, `vision_pages` et
`validation`. Lisez-le avant de continuer : il évite de relire tout le
Markdown.

Pour un PDF converti par MarkItDown, le script a déjà réuni les lignes d'un
même paragraphe, recollé les césures et retiré les en-têtes et pieds de page
répétés (à partir de 3 pages). `hints` liste, avec le numéro de ligne, ce
qu'il n'a pas pu trancher : titres probables, mots peut-être coupés.
`--no-clean` garde le texte brut.

Pour relancer sur un lot déjà en partie converti, ajoutez `--skip-existing` :
un Markdown plus récent que son document n'est pas réécrit, les corrections
déjà faites restent.

## 2. Valider

`validation` donne le résultat de `validate.py` sur le Markdown produit :
inutile de le relancer avant d'avoir corrigé. Erreurs (`ok: false`) : image
ou lien introuvable, tableau mal formé, image restée en base64, fichier vide.
Les avertissements (pas de titre, saut de niveau, en-tête de tableau vide,
contenu à transcrire) se corrigent à l'étape 3. Chaque message donne le
numéro de ligne.

## 3. Corriger

Corrigez le Markdown directement, par éditions ciblées aux lignes signalées,
sans relancer la conversion ni réécrire tout le fichier. Ne supprimez
aucun contenu du document : seuls les en-têtes et pieds de page répétés
peuvent partir. Un passage en double se signale, il ne s'efface pas.

- **Pas de titre** (fréquent sur les PDF) : partez des « titre probable » de
  `hints` et transformez les vrais titres en `#`, `##`, `###`, sans sauter de
  niveau. Inutile de lire tout le document pour cela.
- **Mot peut-être coupé** (`hints`, par exemple « cli ent ») : recollez-le
  s'il s'agit d'un seul mot.
- **En-têtes et pieds de page répétés** restants (document de moins de
  3 pages) : supprimez-les.
- **`needs_vision: true`** ou marqueur `<!-- vision ... -->` : ouvrez
  seulement les images listées dans `vision_pages` (pages déjà rendues en
  PNG, ou l'image d'origine), transcrivez le texte, et décrivez un schéma en
  une ou deux phrases sous l'image. Supprimez ensuite `DOSSIER/.myskills-tmp/`.
  Si le schéma doit rester modifiable, proposez de le recréer (agent
  `schema-designer`).
- **Tableau illisible** : relancez avec `--engine docling` ; sinon
  reconstituez-le à partir du document.

Une fois les corrections faites, relancez `validate.py` jusqu'à zéro erreur :

```bash
uv run scripts/validate.py DOSSIER/<nom>.md
```

## 4. Rendre compte

Indiquez à l'utilisateur, en quelques lignes : fichiers produits, moteur
utilisé, nombre de pages et d'images, corrections faites et ce qui n'a pas pu
être converti.
