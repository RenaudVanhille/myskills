---
name: markdown-to-obsidian
description: "Met un fichier Markdown au format Obsidian : frontmatter, embeds d'images, wikilinks, callouts, pièces jointes copiées dans le vault. À utiliser quand la cible est un vault Obsidian."
---

# markdown-to-obsidian

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script n'a
aucune dépendance (`uv run` ou `python`).

## Contrat

- **Entrées** : notes Markdown (sortie de `doc-to-markdown` ou existantes) et, en option, le dossier du vault.
- **Sorties** : la note au format Obsidian, sur place ou dans `VAULT/<dossier>/`, et ses images dans le dossier de pièces jointes du vault ; avec `--move`, plus rien dans le dossier de travail.
- **Rapport `obsidianize.py`** (liste JSON, un objet par note) : `input`, `output`, `embeds`, `wikilinks`, `callouts`, `attachments_copied`, `missing` ; avec `--classify` : `classification`.
- **Rapport `vault_profile.py`** (objet JSON) : `vault`, `notes`, `tags`, `folders`, `attachments`.
- **Échec sur un fichier** : l'objet ne contient que `input` et `error`.
- **Codes de sortie** : `obsidianize.py` 1 si une note est introuvable ou si une image manque (`missing`) ; `vault_profile.py` 0.
- **Passe la main** : à `doc-to-markdown` (`validate.py --obsidian`) pour la validation ; à `markdown-publish` pour un export Word, HTML ou XWiki.

## 1. Classer et taguer

Avant d'importer, lisez le profil du vault (lecture seule) :

```bash
uv run scripts/vault_profile.py VAULT
```

Le rapport JSON donne les tags existants (du plus utilisé au moins utilisé),
les dossiers de notes avec leurs tags fréquents, et le dossier de pièces
jointes réglé dans Obsidian (`attachments`).

- **Dossier** : choisissez le dossier dont les notes et les tags ressemblent le
  plus au sujet du document, et passez-le à `--folder`. Si aucun ne convient,
  proposez un nouveau dossier à l'utilisateur plutôt que d'en créer un d'office.
- **Tags** : retenez 2 à 4 tags, en reprenant l'orthographe exacte des tags
  existants (`architecture`, pas `archi`). N'en créez un nouveau que si aucun
  tag existant ne couvre le sujet.
- **Pièces jointes** : si `attachments` est renseigné, passez-le à
  `--attachments`.
- **Type et domaine** (optionnel) : `--classify` ajoute au frontmatter les
  propriétés `type` et `domaine`, devinées en local par le modèle Laya (voir
  `classify.py` dans `doc-to-markdown`). Passez les tags principaux du vault
  à `--domains` pour que `domaine` reprenne son vocabulaire. Une valeur
  incertaine n'est pas écrite.
- Les tags et le dossier donnés par l'utilisateur passent toujours avant.
- Indiquez dans le rapport final le dossier et les tags choisis.

## 2. Convertir

```bash
uv run scripts/obsidianize.py NOTE.md [...] --vault VAULT [--folder SOUS-DOSSIER] \
    [--attachments attachments] [--source document.pdf] [--tags tag1,tag2] [--move] \
    [--classify --domains tag1,tag2,tag3]
```

Pour importer un document, convertissez-le d'abord dans un dossier de travail
(`convert.py --out .myskills-tmp`), puis passez `--move` : la note et ses images
quittent le dossier de travail pour le vault, sans laisser de copie.

| Transformation | Avant | Après |
| --- | --- | --- |
| Frontmatter (si absent) | | `title`, `source`, `created`, `tags` (+ `type`, `domaine` avec `--classify`) |
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

## 3. Valider

Avec le script `validate.py` du skill `doc-to-markdown` :

```bash
uv run ../doc-to-markdown/scripts/validate.py VAULT/SOUS-DOSSIER/NOTE.md --obsidian --vault VAULT
```

Un embed introuvable est une erreur ; une note liée absente n'est qu'un
avertissement (Obsidian accepte les liens vers des notes à créer).

## 4. Finir à la main

- **Ancres** : un lien `[[note#section]]` doit reprendre le texte exact du
  titre visé (`[[note#Flux d'un paiement]]`), pas un identifiant web.
- **Encadrés non détectés** : transformez en callout un paragraphe qui est
  clairement une note ou un avertissement.
- Pour aller plus loin (Bases, Canvas, propriétés avancées), le skill
  `obsidian-markdown` de [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)
  documente toute la syntaxe Obsidian.
