---
name: api-contract
description: "Écrit les contrats d'interface d'une solution, OpenAPI 3.1 pour les opérations REST et AsyncAPI 3.0 pour les événements, à partir d'une description JSON courte : ressources, opérations, événements, composant porteur et exigences. Le script écrit le YAML, contrôle doublons, types, ressources, exigences et composants de l'option d'architecture, et relit chaque contrat. À utiliser pour concevoir ou documenter une API, un contrat d'interface, des échanges par événements ou les interfaces de l'option retenue."
---

# api-contract

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
choisissez les ressources, les opérations et les événements ; le script
écrit les contrats et les contrôle.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Description JSON courte des interfaces (api_build.py --schema) : ressources, opérations REST, événements ; Facultatif : exigences.json (requirements-catalog) et options.json avec l'option retenue (architecture-options) ; Pour le chiffrage backend : abaques donnés avant le lancement (shared/schemas/abaques.schema.json, section backend) : ~/.myskills/abaques.json ou MYSKILLS_ABAQUES, references.abaques de mission.json, --abaques ; sans eux, valeurs par défaut à calibrer.
- **Sorties** : <nom>.openapi.yaml : contrat OpenAPI 3.1 des opérations REST ; <nom>.asyncapi.yaml : contrat AsyncAPI 3.0 des événements ; <nom>.api.md : tableaux des opérations, événements et ressources, couverture des exigences ; <base>.lots.json et <base>.md (api_breakdown.py) : lots backend à trois points au format de solution-estimate, avec le réemploi déduit, et leur découpage pour la revue.
- **`api_build.py`** : Écrit les contrats OpenAPI 3.1 et AsyncAPI 3.0 d'une description courte et les contrôle : noms uniques, une opération par méthode et chemin, types et ressources connus, champs obligatoires déclarés, pas de corps pour GET et DELETE, exigences citées présentes, composant porteur présent dans l'option, exigence fonctionnelle indispensable sans interface et écriture sans sécurité signalées ; relit chaque YAML écrit et résout chaque $ref. Rapport JSON, codes de sortie : 0 contrats écrits et relus (avertissements possibles : exigence sans interface, écriture sans sécurité, ressource inutilisée) ; 1 description invalide, type ou ressource inconnus, doublon, exigence ou composant absents, relecture en échec ; aucun fichier produit sauf en cas d'échec de relecture.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`api_breakdown.py`** : Découpe le backend décrit par les interfaces en lots de chiffrage à trois points : un lot par ressource (modèle, persistance, migrations ; complexité selon le nombre de champs), par opération (selon la méthode, montée d'un cran pour une grosse ressource reçue ou beaucoup d'erreurs métier), par événement et par système externe relié dans l'option (intégration), plus les lots transverses du backend (socle, authentification si l'API est sécurisée, messagerie s'il y a des événements, observabilité, tests d'intégration par opération) ; déclare le réemploi entre fonctionnalités (opération de même forme qu'une précédente, ou sur une ressource déjà exposée : reuse avec sa part et sa base) ; contrôle les lots contre le schéma de solution-estimate et écrit les lots et leur découpage. Jours tirés des abaques donnés avant le lancement (utilisateur, mission, --abaques), sinon de valeurs par défaut à calibrer, signalées. Rapport JSON, codes de sortie : 0 lots et découpage écrits (avertissements possibles : abaques par défaut, option non citée) ; 1 description ou abaques invalides, ressource inconnue, option introuvable, lots hors du schéma de solution-estimate ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et reprendre les composants de l'option.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : contrôler les lots backend contre le schéma des lots du chiffrage.
- **Passe la main** au skill `architecture-review` : les interfaces doivent être revues avec l'architecture (traçabilité, dépendances synchrones).
- **Passe la main** à l'agent `document-publisher` : les contrats doivent être livrés dans un dossier Word, HTML ou XWiki.
- **Passe la main** à l'utilisateur : une exigence fonctionnelle indispensable n'a pas d'interface : l'ajouter ou dire qu'elle est hors API.
- **Passe la main** à l'agent `backend-estimator` : un chiffrage du backend est demandé : découper et estimer les lots depuis les interfaces.

## 1. Décrire

Fichier `api.json` (`uv run scripts/api_build.py --schema` donne sa forme
sur une ligne) :

- `resources` : les objets échangés, chacun avec ses champs et leur type
  simple (`string`, `integer`, `number`, `boolean`, `date`, `date-time`,
  `uuid`, `email`, `uri`, `binary`), une autre ressource ou une liste
  `X[]` ; `required` et `enums` au besoin ;
- `operations` : une opération REST par action de l'utilisateur ou d'un
  système (`id` en camelCase, `method`, `path` avec `{id}`, `summary`,
  `request` et `response`, `errors` utiles), avec `component` (le
  composant de l'option qui la porte) et `refs` (les exigences) ;
- `events` : un événement par échange asynchrone (file, bus), avec
  `channel`, `payload`, `action` (`send` ou `receive`), `component` et
  `refs` ;
- `security` (`oidc`, `oauth2`, `bearer`, `apikey`) ; une opération ouverte
  sans authentification porte `public`.

Avec `requirements` (exigences.json) et `source` (`options.json` et l'option
retenue), les exigences et les composants cités sont vérifiés. Partez des
flux de l'option : un flux synchrone appelé par un acteur donne des
opérations, un flux `async` vers une file donne un événement. N'inventez
pas de champ que les exigences ou les documents ne justifient pas.

## 2. Construire

```bash
uv run scripts/api_build.py api.json
```

Corrigez jusqu'à zéro erreur. Le rapport donne les fichiers, les
compteurs et `uncovered` : les exigences fonctionnelles indispensables
qu'aucune interface ne porte ; présentez-les à l'utilisateur (opération à
ajouter, ou exigence hors API). Ne relisez pas les YAML : le script les
relit et résout chaque `$ref`. `api.api.md` résume les interfaces pour la
revue.

## 3. Livrer

Les contrats se versionnent avec le code ; `api.api.md` entre dans le
dossier d'architecture (section annexe des pièces). Pour une revue des
interfaces avec l'architecture, passez à `architecture-review`.

## 4. Découper pour le chiffrage

Pour chiffrer le backend (agent `backend-estimator`, ou `solution-estimator`
sans sous-agent) :

```bash
uv run scripts/api_breakdown.py api.json [--out decoupage-back] [--abaques ABAQUES.json]
```

Un lot à trois points par ressource, opération, événement et système externe
relié dans l'option, plus les lots transverses du backend ; une opération de
même forme qu'une précédente, ou sur une ressource déjà exposée, la réutilise
(`reuse`). `decoupage-back.lots.json` va à `estimate_build.py --draft --lots`
(skill `solution-estimate`) ; `decoupage-back.md` sert à la relecture.

Les jours viennent des abaques donnés avant le lancement, section `backend`
de `~/.myskills/abaques.json` (ou `MYSKILLS_ABAQUES`), puis de
`references.abaques` de `mission.json`, puis de `--abaques` ;
leur forme est `scripts/lib/abaques.schema.json`. Sans eux, les valeurs par
défaut sont à calibrer et le rapport le dit (`calibrated: false`). Ajustez un
lot que l'abaque ne voit pas (règle métier lourde, existant à reprendre,
système mal documenté) dans le `.lots.json`, raison dans `note`.
