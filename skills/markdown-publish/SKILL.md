---
name: markdown-publish
description: "Transforme un Markdown (ou une note Obsidian) en fichier Word, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt."
---

# markdown-publish

Le chemin `scripts/publish.py` est relatif au dossier de ce skill. Le script
ne publie rien : il produit des fichiers que l'utilisateur importe lui-même.
Pandoc est fourni par le paquet `pypandoc_binary` (`uv run` l'installe), rien
à installer à part.

## 1. Produire les fichiers

```bash
uv run scripts/publish.py DOC.md [...] --to docx,html,xwiki [--out DOSSIER] \
    [--reference-doc modele.docx] [--toc] [--vault VAULT]
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

Options :

- `--reference-doc modele.docx` : applique les styles d'un modèle Word
  (polices, couleurs des titres, en-tête et pied de page). Demandez à
  l'utilisateur si un modèle d'entreprise existe.
- `--toc` : ajoute un sommaire.

## 3. Vérifier

Le rapport JSON donne, par format, le fichier produit et le nombre d'images
et de tableaux trouvés dedans, comparés au Markdown. Un avertissement signale
une image introuvable, un schéma non exporté ou un écart dans les comptes.
Corrigez la source (chemin d'image, schéma invalide) et relancez.

Pour un document important, ouvrez le `.html` produit et relisez-le : c'est le
moyen le plus rapide de voir le rendu final.

## 4. Livrer

Indiquez les fichiers produits et, pour chacun, en une ligne, comment
l'importer dans l'outil visé (tableau ci-dessus). Pour XWiki, rappelez que
les images du dossier `<nom>-xwiki/` sont à joindre à la page.
