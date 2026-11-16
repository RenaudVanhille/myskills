# Contrôles du chiffrage

Ce que le rapport d'`estimate_build.py` relève, et comment le traiter.

## Avertissements

- **Exigence sans lot** : ajouter un lot ou des `refs`, ou l'exclure avec
  sa raison.
- **Composant sans chiffrage**, **estimation incertaine**, **budget
  dépassé**, **valeur d'hypothèse sans base** : corriger ou justifier dans
  `assumptions`.
- **Poste attendu absent** (`missing`) : tests de sécurité, de charge, hors
  production, réseau, recette, mise en production, formation, sauvegarde,
  supervision, intégration, reprise de données, selon les exigences et les
  composants. Le traiter par un lot, une ligne, une hypothèse ou une
  exclusion.

## Postes attendus

Ce sont des règles de complétude (`references/postes-attendus.json`),
complétées par celles de l'utilisateur (`MYSKILLS_REGLES`, sinon
`~/.myskills/regles.json`) et de la mission (`references.regles` de
mission.json), schéma `shared/schemas/rules.schema.json`. Un oubli relevé
en revue devient une règle (`lessons.py`, skill `decision-log`).

## Missions analogues

Quand `mission.json` désigne des missions passées comparables
(`analogues`), le rapport compare la part de chaque phase à leur fourchette
(`analogy`) : une phase hors fourchette ou absente est un avertissement à
justifier ou à corriger. Seuls les noms des missions sortent ; rien de leur
contenu n'est recopié.

## Points à challenger

`challenge` du rapport, et section du chiffrage : marges cumulées
(pilotage, provision, asymétrie des trois points), part de la réalisation et
de l'intégration, lots trop gros, lots semblables sans réemploi, jours de
lots par exigence. Les seuils viennent des abaques donnés avant le
lancement (section `challenge` de `~/.myskills/abaques.json` ou
`MYSKILLS_ABAQUES`, de `references.abaques` de mission.json, puis
`--abaques`), sinon de valeurs par défaut à calibrer (`calibrated: false`).
Chaque point se justifie (dans `assumptions`) ou se corrige.

## Coût par parcours

Avec `journeys` (parcours utilisateurs : `id`, `title`, `persona`, `refs`,
au besoin `screens`, `work`, `path`, `risks`), le chiffrage donne le coût de
chaque parcours, poste par poste avec ses références. Les postes partagés
sont répartis au prorata et la somme redonne la réalisation (contrôlé) ;
rattachement des lots : `references/champs.md`. Pour une restitution :

```bash
uv run scripts/journeys_view.py chiffrage.parcours.json --out parcours.md --export png
```

Il écrit le workflow, le coût et les points d'attention de chaque parcours,
sans rien recalculer.
