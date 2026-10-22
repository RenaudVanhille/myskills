---
name: markdown-publish
description: "Transforme un Markdown (ou une note Obsidian) en fichier Word, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt."
---

# markdown-publish

Le chemin `scripts/publish.py` est relatif au dossier de ce skill. Le script
ne publie rien : il produit des fichiers que l'utilisateur importe lui-même.
Pandoc est fourni par le paquet `pypandoc_binary` (`uv run` l'installe), rien
à installer à part.

## Contrat

- **Entrées** : fichiers Markdown ou notes Obsidian, avec leurs images et leurs schémas sources ; en option un modèle Word (`--reference-doc`) et le vault (`--vault`).
- **Sorties** : dans `--out`, `<nom>.docx`, `<nom>.html` et `<nom>.xwiki` avec ses images dans `<nom>-xwiki/` ; en option un PDF et un aperçu PNG par page dans `.myskills-tmp/<nom>-apercu/`.
- **Rapport `publish.py`** (liste JSON, un objet par document) : `input`, `outputs`, `diagrams_exported`, `warnings` ; si un format échoue : `error`. Chaque élément de `outputs` contient `format`, `file`, `images`, `tables`, et selon les options `pdf` ou `preview`.
- **Codes de sortie** : `publish.py` 1 si un document échoue, 0 sinon.
- **Maintenance** : `make_reference.py` régénère `references/modele.docx` ; pas de rapport JSON.
- **Passe la main** : à `diagram-export` pour les schémas (automatique) ; à l'utilisateur, qui importe lui-même les fichiers dans SharePoint, Confluence ou XWiki.

## 1. Produire les fichiers

```bash
uv run scripts/publish.py DOC.md [...] --to docx,html,xwiki [--out DOSSIER] \
    [--reference-doc modele.docx] [--toc] [--pdf] [--preview] [--vault VAULT]
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

Sans précision de l'utilisateur, produisez `docx` et `html` : à eux deux, ils
couvrent SharePoint, Confluence et XWiki.

## 3. Un Word prêt à l'emploi

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

## 4. Relire le rendu

Avec LibreOffice installé (facultatif, détecté aussi hors du PATH, par
exemple dans `C:\Program Files\LibreOffice`) :

- `--preview` produit une image PNG par page dans
  `.myskills-tmp/<nom>-apercu/` à côté du .docx. **Ouvrez chaque page** et
  vérifiez : image trop grande ou coupée, tableau qui déborde, titre seul en
  bas de page, légende manquante. Corrigez la source et relancez, puis
  supprimez le dossier `.myskills-tmp/`.
- `--pdf` livre aussi un PDF.

Sans LibreOffice, le script le signale et produit le .docx quand même.

## 5. Vérifier les comptes

Le rapport JSON donne, par format, le fichier produit et le nombre d'images
et de tableaux trouvés dedans, comparés au Markdown. Un avertissement signale
une image introuvable, un schéma non exporté ou un écart dans les comptes.
Corrigez la source (chemin d'image, schéma invalide) et relancez.

## 6. Livrer

Indiquez les fichiers produits et, pour chacun, en une ligne, comment
l'importer dans l'outil visé (tableau ci-dessus). Pour XWiki, rappelez que
les images du dossier `<nom>-xwiki/` sont à joindre à la page.
