---
name: threat-model
description: "Prépare le modèle de menaces STRIDE d'une architecture décrite en JSON (celle des schémas cloud) : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable avec sa mesure et son statut à compléter. À utiliser pour une analyse de sécurité d'une architecture cloud, d'une option d'architecture ou d'une infrastructure existante."
---

# threat-model

Les chemins `scripts/...` sont relatifs au dossier de ce skill. L'entrée est
la description JSON de `cloud_build.py` (skill `cloud-architecture`, qui
doit être installé à côté) : `--schema` l'affiche. Vous ne décidez que ce
qui demande du jugement : garder, préciser et compléter les menaces.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON de l'architecture, celle de cloud_build.py (skill cloud-architecture) : groupes, services typés, flux avec protocole ; Ou la description cloud d'une option d'architecture-options (schemas/option-<id>.cloud.json).
- **Sorties** : <sujet>.threats.md : frontières de confiance, flux qui les traversent, une menace type par catégorie STRIDE applicable, mesure type ; après threat_review.py, menaces précisées, mesures retenues, statuts et menaces écartées avec leur raison ; <sujet>.threats.json : les mêmes menaces en données, auxquelles le modèle répond par un fichier de décisions.
- **`stride.py`** : Prépare le modèle de menaces STRIDE à partir de la même description : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable, avec mesure type et statut à compléter. Rapport JSON, codes de sortie : 0 modèle produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`threat_review.py`** : Reporte dans le modèle STRIDE les décisions du modèle sur les menaces, données dans un court fichier JSON (statut, mesure retenue, menace précisée, raison) : vérifie chaque décision, réécrit <sujet>.threats.md depuis <sujet>.threats.json, compte les menaces par statut et celles encore à analyser. Rapport JSON, codes de sortie : 0 décisions reportées dans le modèle ; 1 décisions invalides (menace inconnue, mesure ou raison manquante, identifiant décalé) ou modèle illisible.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `cloud-architecture` (`cloud_build.py`, obligatoire) : lire la description comme le schéma : types de services, groupes, frontières et numéros de flux F1, F2....
- **Vault Obsidian** : écrit les notes de type `modele-menaces` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `cloud-architecture` : schéma des menaces (cloud_build.py --view threats), mêmes numéros de flux.
- **Passe la main** au skill `well-architected-review` : contrôler aussi les piliers Well-Architected du fournisseur.
- **Passe la main** à l'utilisateur : compléter avec lui les mesures retenues et les statuts des menaces.

## 1. Préparer le modèle

```bash
uv run scripts/stride.py SUJET.json
uv run ../cloud-architecture/scripts/cloud_build.py SUJET.json --view threats --out SUJET-menaces.drawio
```

Dans un workflow avec un vault Obsidian, ajoutez à `stride.py` `--vault
VAULT --folder DOSSIER [--option ID]` : une note `modele-menaces`
(compteurs, flux à risque) rejoint la mémoire partagée, reliée à l'option.

Les comptes, VPC, sous-réseaux, security groups, clusters, namespaces,
`onprem`, `internet` et `boundary` sont des frontières de confiance
(`"boundary": false` ou `true` pour forcer) ; une entité externe (`user`,
`external`...) est hors frontière. `stride.py` écrit `SUJET.threats.md` :
frontières, flux qui les traversent (en tête, avec chiffrement déclaré ou
non), puis une menace type par catégorie STRIDE applicable à chaque
élément, avec une mesure type et les colonnes « Mesure retenue » et
« Statut » à compléter, et `SUJET.threats.json`, les mêmes menaces en
données. Les numéros F1, F2... sont les mêmes que sur le schéma `threats`.

## 2. Décider, sans réécrire le tableau

Lisez le tableau une fois, puis écrivez seulement vos décisions dans un
court `SUJET.decisions.json` (`threat_review.py --schema`) : une entrée par
menace gardée, précisée, acceptée ou écartée.

```json
{"model": "SUJET.threats.json",
 "threats": {"M001": {"status": "traitee", "measure": "WAF et MFA sur le portail", "threat": "Vol de session d'un assuré"},
             "M004": {"status": "ecartee", "why": "pas de compte administrateur sur ce service"}}}
```

`status` : `traitee` (avec `measure`), `a-traiter`, `acceptee` ou
`ecartee` (avec `why`, celle de l'utilisateur pour une acceptation).
Ensuite :

```bash
uv run scripts/threat_review.py SUJET.decisions.json
```

Il vérifie chaque décision (menace inconnue, mesure ou raison manquante),
réécrit `SUJET.threats.md` (menaces écartées à part) et compte les menaces
encore à analyser. Relancer `stride.py` remet le tableau à blanc :
relancez alors `threat_review.py`, qui signale un identifiant décalé si
vous donnez `element`.

## 3. Relire avec l'utilisateur

Une menace sans mesure retenue reste « à traiter ». Notez dans le journal du
workflow (skill `decision-log`) une menace écartée et pourquoi. Pour
compléter la revue, lancez `well-architected-review` sur la même
description.
