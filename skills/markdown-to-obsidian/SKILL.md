---
name: markdown-to-obsidian
description: "Met un fichier Markdown au format Obsidian : frontmatter, embeds d'images, wikilinks, callouts, pièces jointes copiées dans le vault. À utiliser quand la cible est un vault Obsidian."
---

# markdown-to-obsidian

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script n'a
aucune dépendance (`uv run` ou `python`).

## 1. Convertir

```bash
uv run scripts/obsidianize.py NOTE.md [...] --vault VAULT [--folder SOUS-DOSSIER] \
    [--attachments attachments] [--source document.pdf] [--tags tag1,tag2] [--move]
```

Pour importer un document, convertissez-le d'abord dans un dossier de travail
(`convert.py --out .myskills-tmp`), puis passez `--move` : la note et ses images
quittent le dossier de travail pour le vault, sans laisser de copie.

| Transformation | Avant | Après |
| --- | --- | --- |
| Frontmatter (si absent) | | `title`, `source`, `created`, `tags` |
| Image locale | `![alt](attachments/a.png)` | `![[a.png\|alt]]` |
| Lien vers une note | `[texte](autre.md)` | `[[autre\|texte]]` |
| Citation avec mot-clé | `> Attention : ...` | `> [!warning]` puis le texte |

Mots-clés reconnus pour les callouts : note, remarque, info, astuce, conseil,
important, attention, avertissement, danger, exemple.

Avec `--vault`, la note est écrite dans `VAULT/SOUS-DOSSIER/` et ses images
sont copiées dans `VAULT/attachments/` (ou le dossier indiqué par
`--attachments`, à aligner sur le réglage « Default location for new
attachments » du vault). Sans `--vault`, la note est modifiée sur place. Le
script peut être relancé sans risque : il ne refait pas ce qui est déjà fait.

Le rapport JSON indique, par note, le nombre d'embeds, de wikilinks et de
callouts créés, et les images introuvables (`missing`, code de sortie 1).

## 2. Valider

Avec le script `validate.py` du skill `doc-to-markdown` :

```bash
uv run ../doc-to-markdown/scripts/validate.py VAULT/SOUS-DOSSIER/NOTE.md --obsidian --vault VAULT
```

Un embed introuvable est une erreur ; une note liée absente n'est qu'un
avertissement (Obsidian accepte les liens vers des notes à créer).

## 3. Finir à la main

- **Ancres** : un lien `[[note#section]]` doit reprendre le texte exact du
  titre visé (`[[note#Flux d'un paiement]]`), pas un identifiant web.
- **Tags** : proposez 2 à 4 tags tirés du sujet du document si l'utilisateur
  n'en a pas donné.
- **Encadrés non détectés** : transformez en callout un paragraphe qui est
  clairement une note ou un avertissement.
- Pour aller plus loin (Bases, Canvas, propriétés avancées), le skill
  `obsidian-markdown` de [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)
  documente toute la syntaxe Obsidian.
