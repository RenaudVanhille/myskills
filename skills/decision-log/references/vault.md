# Mémoire partagée dans Obsidian : détail

À lire seulement pour choisir le dossier du vault, expliquer une note à
l'utilisateur ou comprendre une note gardée et signalée.

## Notes écrites

Avec `init --vault VAULT` (et `--folder`, défaut `Workflows/<titre>`),
chaque commande réécrit dans le vault une note par exigence
(`Exigences/EF-001`, liée à son document source : relation `extrait-de` et
lien vers la section citée), par document des sources (`Documents/`), par
terme du glossaire (`Glossaire/Sinistre`), par option (`Options/Option A`),
par entrée du journal (`Décisions/D-001`), l'ADR et une note d'index,
reliées par des wikilinks. Le frontmatter suit l'ontologie du vault (skill
markdown-to-obsidian) : `type`, propriétés (`priorite`, `etape`, `par`...),
relations typées en wikilinks (`workflow`, `concerne`, `termes`, `ecarts`,
`option`...) et tags normalisés (`type/exigence`, `priorite/indispensable`) ;
une note hors ontologie bloque l'écriture.

Pour choisir le dossier, lisez d'abord le profil du vault
(`vault_profile.py` du skill `markdown-to-obsidian`).

## Notes de l'utilisateur

Une étape soumise a sa note de revue (`Revues/Revue <étape>`) : l'utilisateur
y met la propriété `revue` à `validée` ou `retour` et écrit son retour sous
« Votre retour » ; `review --from-vault` la lit et trace la décision comme
prise dans Obsidian.

Les autres notes sont générées (`genere: decision-log`) et réécrites à chaque
passage, sauf leur section « Mes notes », toujours gardée : l'utilisateur y
écrit, et chaque callout `> [!question]` ou `> [!retour]` qui s'y trouve
devient, à la commande suivante, une entrée `question` ou `annotation` du
journal (champ `annotations` du rapport). Une note générée devenue inutile
mais annotée est gardée et signalée. Les autres notes du vault ne sont
jamais touchées.
