# Chercher dans la mémoire partagée

Ce guide est destiné à l'utilisateur qui cherche lui-même dans le vault. Un
agent, lui, interroge le vault avec `vault_query.py` (JSON court) et ne lit
pas ce guide.

## Recherche d'Obsidian (cœur, rien à installer)

Les notes générées portent un type, des propriétés et des tags normalisés
tirés de l'ontologie. La recherche les filtre directement :

| Je cherche | Requête |
| --- | --- |
| les risques ouverts | `[type:risque] [statut:ouvert]` |
| les constats graves d'une revue | `tag:#type/constat tag:#gravite/haute` |
| les exigences indispensables | `tag:#priorite/indispensable` |
| ce qui porte sur une exigence | `[porte-sur:SECU-01]` |
| les décisions d'un workflow | `path:"Workflows/Portail sinistres/Décisions"` |
| mes annotations | `"[!question]" OR "[!retour]"` |
| un mot dans les seules notes typées | `paiement [type]` |

`[propriété:valeur]` cherche dans le frontmatter (`[propriété]` : la propriété existe), `tag:#...` dans les tags
(type et facettes : `type/<type>`, `<propriété>/<valeur>`), `path:` dans un
dossier. Les requêtes se combinent (ET par défaut, `OR`, `-` pour exclure).
Une requête utile s'enregistre en l'intégrant dans une note, dans un bloc
de code `query`.

## Tableaux et carte

- `Tableaux.base` (plugin cœur Bases), dans chaque dossier de workflow :
  exigences par priorité, constats et risques ouverts par gravité,
  décisions. Les colonnes se trient et se filtrent dans Obsidian.
- `Carte.canvas` (plugin cœur Canvas), quand elle existe : les liens entre
  exigences, options, revues, constats et risques.
- La vue graphe se filtre de même (`tag:#type/risque`), et
  `vault_check.py VAULT --style` y colore chaque type.

## Omnisearch (facultatif)

[Omnisearch](https://github.com/scambier/obsidian-omnisearch) est un plugin
communautaire de recherche plein texte : tolérant aux fautes de frappe,
classé par pertinence, il lit aussi le texte des PDF et des images si
l'extension Text Extractor est installée. Tout reste local : l'index est
calculé sur la machine. Il n'est ni requis ni installé par myskills ; les
notes n'en dépendent pas. Pour l'ajouter : Réglages, Modules
complémentaires, Parcourir, « Omnisearch ».

## Ce qui est écarté

- **Recherche sémantique (embeddings)**, Smart Connections, Copilot for
  Obsidian : ces outils envoient le contenu à un service, ou téléchargent un
  modèle qui n'est pas épinglé dans `model-sources.json`. Aucun document ne
  doit partir ailleurs que vers les modèles du harness (AGENTS.md, section 5).
- **Dataview** : Bases, le plugin cœur, fait les mêmes tableaux sans
  exécuter de code (DataviewJS exécute du JavaScript dans le vault).
- **Obsidian Sync et Publish** : ce sont des services en ligne. Pour
  partager un vault, utilisez un dépôt git ou un dossier partagé maîtrisé.
