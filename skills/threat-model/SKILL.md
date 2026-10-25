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
- **Sorties** : <sujet>.threats.md : frontières de confiance, flux qui les traversent, une menace type par catégorie STRIDE applicable, mesure type et statut à compléter.
- **`stride.py`** : Prépare le modèle de menaces STRIDE à partir de la même description : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable, avec mesure type et statut à compléter. Rapport JSON, codes de sortie : 0 modèle produit sans erreur ; 1 description illisible ou erreur.
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

Les comptes, VPC, sous-réseaux, security groups, clusters, namespaces,
`onprem`, `internet` et `boundary` sont des frontières de confiance
(`"boundary": false` ou `true` pour forcer) ; une entité externe (`user`,
`external`...) est hors frontière. `stride.py` écrit `SUJET.threats.md` :
frontières, flux qui les traversent (en tête, avec chiffrement déclaré ou
non), puis une menace type par catégorie STRIDE applicable à chaque
élément, avec une mesure type et les colonnes « Mesure retenue » et
« Statut » à compléter. Relisez le tableau : gardez les menaces
pertinentes, précisez-les pour le contexte, complétez les mesures. Les
numéros F1, F2... sont les mêmes que sur le schéma `threats`.

## 2. Relire avec l'utilisateur

Une menace sans mesure retenue reste « à traiter ». Notez dans le journal du
workflow (skill `decision-log`) une menace écartée et pourquoi. Pour
compléter la revue, lancez `well-architected-review` sur la même
description.
