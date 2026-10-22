---
name: doc-to-markdown
description: "Convertit un document PDF, DOCX, PPTX, XLSX ou une image en Markdown propre, en local, avec les images extraites dans attachments/. À utiliser pour extraire le contenu d'un document vers du Markdown."
---

# doc-to-markdown

Convertit un document en Markdown sans l'envoyer à un service en ligne. Les
chemins `scripts/...` sont relatifs au dossier de ce skill. Les scripts
installent eux-mêmes leurs dépendances via `uv run` ; à défaut, lancez-les avec
`python` après `pip install "markitdown[docx,pptx,xlsx,pdf]" pypdf`.

## Contrat

- **Entrées** : fichiers PDF, DOCX, PPTX, XLSX, XLS, DOC, PPT ou images (PNG, JPG, GIF, BMP, TIFF, WEBP) ; dossiers acceptés par `classify.py`.
- **Sorties** : `DOSSIER/<nom>.md` et ses images dans `DOSSIER/attachments/<nom>-N.<ext>`, liées en relatif.
- **Rapport `convert.py`** (liste JSON, un objet par fichier) : `input`, `output`, `type`, `engine`, `pages`, `images`, `needs_vision`, `warnings` ; avec `--classify` : `classification`.
- **Rapport `validate.py`** (liste JSON, un objet par fichier) : `file`, `ok`, `errors`, `warnings`.
- **Rapport `classify.py`** (liste JSON, un objet par fichier) : `input`, `type`, `type_confidence`, `domaine`, `domaine_confidence`, `tables`, `engine`, `method`, `warnings`.
- **Échec sur un fichier** : l'objet ne contient que `input` (ou `file`) et `error`.
- **Codes de sortie** : 0 si tout a réussi ; 1 si un fichier a échoué (`convert.py`, `classify.py`) ou contient une erreur (`validate.py`).
- **Passe la main** : à `markdown-to-obsidian` si la cible est un vault ; à l'agent `schema-designer` pour recréer un schéma modifiable à partir d'une image.

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
`pages`, `images`, `needs_vision`, `warnings`. Lisez-le avant de continuer.

## 2. Valider

```bash
uv run scripts/validate.py DOSSIER/<nom>.md
```

Code de sortie 1 en cas d'erreur : image ou lien introuvable, tableau mal
formé, image restée en base64, fichier vide. Les avertissements (pas de titre,
saut de niveau, en-tête de tableau vide, contenu à transcrire) se corrigent à
l'étape 3.

## 3. Corriger

Corrigez le Markdown directement, sans relancer la conversion. Ne supprimez
aucun contenu du document : seuls les en-têtes et pieds de page répétés
peuvent partir. Un passage en double se signale, il ne s'efface pas.

- **Pas de titre** (fréquent sur les PDF) : transformez les titres visibles du
  document en `#`, `##`, `###`, sans sauter de niveau.
- **Mots coupés en fin de ligne** (`cli` / `ent`) : recollez-les ; réunissez
  les lignes d'un même paragraphe.
- **En-têtes et pieds de page répétés** sur chaque page : supprimez-les.
- **`needs_vision: true`** ou marqueur `<!-- vision ... -->` : ouvrez l'image
  ou la page, transcrivez le texte, et décrivez un schéma en une ou deux
  phrases sous l'image. Si le schéma doit rester modifiable, proposez de le
  recréer (agent `schema-designer`).
- **Tableau illisible** : relancez avec `--engine docling` ; sinon
  reconstituez-le à partir du document.

Relancez `validate.py` jusqu'à zéro erreur.

## 4. Rendre compte

Indiquez à l'utilisateur, en quelques lignes : fichiers produits, moteur
utilisé, nombre de pages et d'images, corrections faites et ce qui n'a pas pu
être converti.
