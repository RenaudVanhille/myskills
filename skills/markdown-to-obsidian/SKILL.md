---
name: markdown-to-obsidian
description: "Met un fichier Markdown au format Obsidian : frontmatter, embeds d'images, wikilinks, callouts, pièces jointes copiées dans le vault. À utiliser quand la cible est un vault Obsidian."
---

# markdown-to-obsidian

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script n'a
aucune dépendance (`uv run` ou `python`).

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Notes Markdown (sortie de doc-to-markdown ou existantes) ; Dossier du vault Obsidian (facultatif).
- **Sorties** : Note au format Obsidian, sur place ou dans VAULT/<dossier>/ ; Images dans le dossier de pièces jointes du vault ; Avec --move : rien ne reste dans le dossier de travail ; Avec vault_check.py --graph : graphe typé des notes (JSON node-link NetworkX).
- **`obsidianize.py`** : Met des notes au format Obsidian et les range dans le vault. Rapport JSON (0 succès, 1 erreur).
- **`vault_profile.py`** : Lit le vault (lecture seule) : tags, dossiers, dossier des pièces jointes. Rapport JSON (0 succès, 1 erreur).
- **`vault_check.py`** : Vérifie les notes typées du vault contre l'ontologie (scripts/lib/vault-ontology.json), relit la lisibilité des notes générées et exporte leur graphe typé (lecture seule, sauf --style). Rapport JSON (0 succès, 1 erreur).
- **Dépend de** `doc-to-markdown` (`classify.py`, facultatif : sans lui, avertissement) : classer les documents avant la conversion (--classify).
- **Dépend de** `doc-to-markdown` (`validate.py`, facultatif : sans lui, avertissement) : valider les notes produites.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Vault Obsidian** : écrit les notes de type `document` ; lit les notes typées, selon l'ontologie du vault (`vault_ontology.py` du skill markdown-to-obsidian).
- **Passe la main** au skill `doc-to-markdown` : valider la note avec validate.py --obsidian.
- **Passe la main** au skill `markdown-publish` : exporter la note en Word, HTML ou XWiki.

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
- **Nature et domaine** (optionnel) : `--classify` ajoute au frontmatter les
  propriétés `nature` (type de document) et `domaine`, devinées en local par le modèle Laya (voir
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
| Frontmatter (si absent) | | `type: document`, `title`, `source`, `created`, `tags` normalisés (+ `nature`, `domaine` avec `--classify`) |
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

Le rapport contient aussi `validation` : le résultat de `validate.py
--obsidian` (skill `doc-to-markdown`) sur la note produite. Un embed
introuvable est une erreur ; une note liée absente n'est qu'un avertissement
(Obsidian accepte les liens vers des notes à créer). Après une correction à
la main, revérifiez :

```bash
uv run ../doc-to-markdown/scripts/validate.py VAULT/SOUS-DOSSIER/NOTE.md --obsidian --vault VAULT
```

## 4. Ontologie du vault

Les notes écrites par les skills suivent une ontologie commune
(`scripts/lib/vault-ontology.json`, source unique que les autres skills chargent) :
`type` de note (exigence, option-architecture, decision, adr, document,
constat, risque...), propriétés et valeurs permises, relations typées
écrites en wikilinks entre guillemets (`concerne: ["[[...]]"]`) et tags
normalisés (`type/<type>`, puis une facette par propriété :
`statut/retenue`). Pour écrire ou corriger une note typée à la main,
demandez l'ontologie d'un type plutôt que de lire le fichier :

```bash
uv run scripts/vault_check.py --ontology constat
```

Pour vérifier un vault (ou un dossier) et en tirer le graphe typé :

```bash
uv run scripts/vault_check.py VAULT [--folder DOSSIER] [--graph graphe.json] [--strict]
```

Le rapport compte les notes par type et ne détaille (`results`) que les
notes en erreur : type inconnu (avec le type proche), valeur hors liste,
relation non permise ou vers une note du mauvais type, tag non normalisé
(avec la forme proposée). Une note générée (`genere`) est aussi relue pour
sa lisibilité : avertissements `lisibilité :` (lien libellé par un simple
identifiant, accord « (s) », montant sans séparateur des milliers), bloquants
avec `--strict`. `--graph` écrit le graphe au format node-link de
NetworkX (`nodes` avec type et propriétés, `links` avec `relation`, `lien`
pour un wikilink du corps), à passer tel quel à une revue d'architecture ou
à networkx : ne relisez pas le vault note à note.

Chaque dossier de workflow a aussi son `Tableaux.base` (Obsidian Bases,
plugin cœur) : une vue tableau par entrée `views` de l'ontologie
(exigences par priorité, constats et risques ouverts par gravité...),
réécrit par les scripts à chaque passage et lié depuis la note du workflow.
Un nouveau tableau s'ajoute dans l'ontologie, sans code.

Chaque note générée finit par une section « Mes notes » que les scripts
gardent à chaque réécriture (`vault_ontology.with_user`) : c'est la place de
l'utilisateur. Ses callouts `> [!question]` et `> [!retour]` y sont relus
(`vault_ontology.vault_annotations`), et une note générée obsolète mais
annotée n'est pas supprimée.

Si l'utilisateur le demande, `vault_check.py VAULT --style` colore chaque
type (champ `color` de l'ontologie) dans la vue graphe et sur son tag
`type/<type>` : il écrit dans `.obsidian/` (ses autres réglages gardés),
jamais par défaut. Les constats, risques, lots et rapports d'une revue vont
dans un sous-dossier court (`Constats/Option A/`) ; l'ancien dossier au
titre long est vidé de ses notes générées au passage suivant.

## 5. Finir à la main

- **Ancres** : un lien `[[note#section]]` doit reprendre le texte exact du
  titre visé (`[[note#Flux d'un paiement]]`), pas un identifiant web.
- **Encadrés non détectés** : transformez en callout un paragraphe qui est
  clairement une note ou un avertissement.
- Pour aller plus loin (Bases, Canvas, propriétés avancées), le skill
  `obsidian-markdown` de [kepano/obsidian-skills](https://github.com/kepano/obsidian-skills)
  documente toute la syntaxe Obsidian.
