<!-- Fichier généré par scripts/build.py depuis skills/decision-log/workflows/ : ne pas le modifier à la main. -->

# Workflows

Un workflow est une définition JSON (`skills/decision-log/workflows/`) que suit le moteur `architecture-workflow` : des étapes à portes de revue, chacune avec ses skills, ses livrables, ses contrôles par script et, au besoin, un agent spécialisé. Chaque page ci-dessous est tirée de sa définition.

## Carte

```mermaid
---
title: Workflows et leur point de départ
---
flowchart LR
  d0(["Documents du projet"])
  d1(["Code d'infrastructure"])
  d2(["Dossier validé"])
  d3(["Maquettes d'écrans"])
  d4(["Code de l'application"])
  w_architecture["architecture"]
  w_avant_vente["avant-vente"]
  w_cadrage["cadrage"]
  w_cloud_existant["cloud-existant"]
  w_conformite["conformite"]
  w_documentation["documentation"]
  w_evolution["evolution"]
  w_maquettes["maquettes"]
  w_migration_cloud["migration-cloud"]
  w_restitution["restitution"]
  w_retro_documentation["retro-documentation"]
  w_revue_dossier["revue-dossier"]
  d0 --> w_architecture
  d0 --> w_avant_vente
  d0 --> w_cadrage
  d0 --> w_conformite
  d0 --> w_documentation
  d0 --> w_migration_cloud
  d0 --> w_revue_dossier
  d1 --> w_cloud_existant
  d2 --> w_evolution
  d2 --> w_restitution
  d3 --> w_maquettes
  d4 --> w_retro_documentation
  w_architecture -.-> d2
  w_avant_vente -.-> d2
  w_cadrage -.-> d2
  classDef moteur fill:#dbeafe,stroke:#1d4ed8,color:#1f2937
  classDef depart fill:#f3f4f6,stroke:#6b7280,color:#1f2937
  class w_architecture,w_avant_vente,w_cadrage,w_cloud_existant,w_conformite,w_documentation,w_evolution,w_maquettes,w_migration_cloud,w_restitution,w_retro_documentation,w_revue_dossier moteur
  class d0,d1,d2,d3,d4 depart
```

En pointillés : les workflows dont le dossier validé (exigences et options) est repris ensuite par les workflows menés dans son sous-dossier (`evolution`, `restitution`).

## Liste

| Workflow | Étapes | Point de départ |
| --- | --- | --- |
| [Des documents du projet aux schémas d'architecture](architecture.md) (`architecture`) | 8 | Documents du projet |
| [Réponse à un appel d'offres, des documents reçus à l'offre](avant-vente.md) (`avant-vente`) | 15 | Documents du projet |
| [Cadrage d'un projet : ateliers, exigences, données, dimensionnement, interfaces et recette](cadrage.md) (`cadrage`) | 9 | Documents du projet |
| [Schémas et menaces d'une infrastructure existante](cloud-existant.md) (`cloud-existant`) | 3 | Code d'infrastructure |
| [Conformité d'une architecture : sécurité, RGPD et hébergement](conformite.md) (`conformite`) | 5 | Documents du projet |
| [Des documents en vrac à une documentation : notes du vault, synthèse, schémas et document](documentation.md) (`documentation`) | 5 | Documents du projet |
| [Évolution d'une solution validée : écarts, impacts, décision et chiffrage du changement](evolution.md) (`evolution`) | 8 | Dossier validé |
| [Maquettes d'écrans vers pages HTML, revue UX et chiffrage frontend](maquettes.md) (`maquettes`) | 4 | Maquettes d'écrans |
| [Migration d'un portefeuille d'applications vers le cloud](migration-cloud.md) (`migration-cloud`) | 6 | Documents du projet |
| [Restitution d'une architecture retenue au comité ou aux décideurs](restitution.md) (`restitution`) | 4 | Dossier validé |
| [Rétro-documentation et modernisation d'une application existante](retro-documentation.md) (`retro-documentation`) | 8 | Code de l'application |
| [Instruction d'un dossier d'architecture reçu](revue-dossier.md) (`revue-dossier`) | 4 | Documents du projet |
