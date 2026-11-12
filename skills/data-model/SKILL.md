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
- **Entrées** : Les exigences (exigences.json de requirements-catalog), le glossaire, le découpage en domaines s'il existe (domaines.json de domain-design : un modèle par contexte borné) et, s'il existe, api.json d'api-contract (ressources) ; Description JSON du modèle (model_build.py --schema) : entités, champs typés, clés, données personnelles, relations 1-1, 1-n, n-n ; Pour un existant : le schéma SQL de la base actuelle (CREATE TABLE), lu par model_import.py.
- **Sorties** : <nom>.mmd : diagramme entité-relation Mermaid (erDiagram) ; <nom>.md : diagramme et dictionnaire de données (champs, types, clés, données personnelles, relations) ; <nom>.sql : schéma PostgreSQL (tables, clés primaires et étrangères, tables d'association des relations n-n ; avec le découpage, un schéma par contexte et aucune clé étrangère entre contextes) ; modele.json : brouillon du modèle actuel tiré du schéma SQL (model_import.py), à relire puis construire.
- **`model_build.py`** : Contrôle noms uniques, une clé par entité, références et extrémités de relations, exigences citées ; avec le découpage (domains), contexte de chaque entité connu et conforme au propriétaire du découpage, liens entre contextes signalés avec la relation de la carte qui les porte ; signale entité isolée, relation n-n, données personnelles et de santé ; écrit le diagramme Mermaid, le dictionnaire de données et le DDL PostgreSQL (un schéma par contexte, référence sans clé étrangère entre contextes), puis relit le diagramme. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`model_import.py`** : Écrit le brouillon de modele.json depuis le schéma SQL d'une base existante : une entité par table, un champ par colonne au type simple, une référence par clé étrangère (en ligne ou en contrainte de table), table d'association en relation n-n, données personnelles devinées par le nom des colonnes ; instruction illisible signalée avec sa ligne, clé primaire composée ou absente et clé étrangère vers une table absente signalées ; brouillon validé contre le schéma de model_build.py avant d'être écrit, jamais par-dessus une description existante. Rapport JSON (0 succès, 1 erreur).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `domain-design` (`domain_build.py`, facultatif : sans lui, avertissement) : valider le découpage en domaines (domains) contre son schéma.
- **Passe la main** au skill `domain-design` : lien entre deux contextes qu'aucune relation de la carte ne porte, ou entité sans contexte propriétaire : revoir le découpage.
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

### Modèle d'une base existante

Pour un existant, ne réécrivez pas le modèle : `uv run
scripts/model_import.py schema.sql --out modele.json` en tire le brouillon
(tables, colonnes, clés, tables d'association en n-n, données personnelles
devinées). Relisez les avertissements et les libellés, puis construisez.

### Un modèle par contexte borné

Quand un découpage en domaines existe (`domaines.json` de `domain-design`),
le modèle vient après lui : `"domains": "domaines.json"` et, sur chaque
entité, son `context` (le contexte qui la possède dans le découpage). Le
script en fait un schéma PostgreSQL par contexte et ne crée aucune clé
étrangère entre deux contextes : le lien reste un identifiant de
référence, lu par l'API ou les événements de l'amont. Chaque lien entre
contextes est signalé (`cross_context`) ; s'il n'a pas de relation dans la
carte des contextes, revoir le découpage plutôt que le modèle.

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
