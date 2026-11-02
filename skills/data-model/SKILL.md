---
name: data-model
description: "Modèle de données conceptuel et logique tiré des exigences, du glossaire et des interfaces : entités, champs typés, clés, relations 1-1, 1-n, n-n, données personnelles et de santé repérées. Le script contrôle le modèle et écrit le diagramme entité-relation Mermaid, le dictionnaire de données et le schéma PostgreSQL (clés étrangères, tables d'association). À utiliser pour un modèle de données, un MCD ou MLD, un diagramme entité-relation, un dictionnaire de données ou un DDL de départ."
---

# data-model

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décidez des entités, des champs et des cardinalités ; le script contrôle,
dessine et écrit le SQL.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Les exigences (exigences.json de requirements-catalog), le glossaire et, s'il existe, api.json d'api-contract (ressources) ; Description JSON du modèle (model_build.py --schema) : entités, champs typés, clés, données personnelles, relations 1-1, 1-n, n-n.
- **Sorties** : <nom>.mmd : diagramme entité-relation Mermaid (erDiagram) ; <nom>.md : diagramme et dictionnaire de données (champs, types, clés, données personnelles, relations) ; <nom>.sql : schéma PostgreSQL (tables, clés primaires et étrangères, tables d'association des relations n-n).
- **`model_build.py`** : Contrôle noms uniques, une clé par entité, références et extrémités de relations, exigences citées ; signale entité isolée, relation n-n, données personnelles et de santé ; écrit le diagramme Mermaid, le dictionnaire de données et le DDL PostgreSQL, puis relit le diagramme. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Passe la main** au skill `data-protection` : le modèle contient des données personnelles : registre des traitements et AIPD.
- **Passe la main** au skill `diagram-export` : une image du diagramme est demandée (PNG, SVG) : export du .mmd.
- **Passe la main** au skill `api-contract` : les ressources des interfaces doivent suivre le modèle (champs et types).
- **Passe la main** à l'utilisateur : une cardinalité ou la nature d'une donnée n'est pas tranchée par les exigences : la question à poser.

## 1. Décrire le modèle

Partez du glossaire d'`exigences.json` (un terme métier qui n'est pas un
acteur est souvent une entité) et, s'il existe, des ressources
d'`api.json`. Fichier `modele.json` (`uv run scripts/model_build.py
--schema` donne sa forme) :

```json
{
  "title": "Modèle de données du portail sinistres",
  "requirements": "exigences.json",
  "entities": [
    {"name": "Assure", "label": "Assuré", "fields": [
      {"name": "id", "type": "uuid", "key": true},
      {"name": "email", "type": "string", "required": true, "unique": true, "personal": "contact"}]},
    {"name": "Sinistre", "refs": ["EF-001"], "fields": [
      {"name": "id", "type": "uuid", "key": true},
      {"name": "survenu_le", "type": "date", "required": true}]}
  ],
  "relations": [{"from": "Assure", "to": "Sinistre", "kind": "1-n", "label": "déclare", "required": true}]
}
```

- **Une clé** par entité (`key: true`).
- **Relations** : `1-n` se lit « un `from` pour plusieurs `to` » ; la clé
  étrangère est générée côté `to`, sauf si un champ `ref` la porte déjà.
  `n-n` donne une table d'association.
- **Données personnelles** : `personal` avec sa nature (identité, contact,
  santé, financier, localisation) ; la santé est une donnée sensible.

## 2. Construire

```bash
uv run scripts/model_build.py modele.json
```

Corrigez jusqu'à zéro erreur. Les avertissements (entité isolée, données
personnelles) se disent à l'utilisateur ; des données personnelles passent
à `data-protection` (registre, AIPD).

## 3. Livrer

`modele.md` (diagramme et dictionnaire), `modele.mmd` et `modele.sql`. Pour
une image du diagramme, `diagram-export`.
