---
genere: decision-log
type: "option-architecture"
id: "option-A"
retenue: true
workflow: "[[Projets/Sinistres/Portail sinistres]]"
aliases:
  - "Option A : Application web dans le cloud européen"
ontologie: 1
tags:
  - type/option-architecture
  - architecture
---

# Option A : Application web dans le cloud européen

Portail web et API en conteneurs managés, file de messages vers l'outil de gestion.

Workflow : [[Projets/Sinistres/Portail sinistres|Portail sinistres]]

## Composants

- Assuré
- Portail web (React)
- API déclarations (conteneurs managés)
- File de déclarations
- Outil de gestion des sinistres
- Annuaire des assurés

## Avantages

- absorbe les pics après tempête

## Inconvénients

- compétences conteneurs à acquérir

## Risques

- coût variable pendant les pics

## Mes notes

%% myskills : écrivez sous ce titre, la section est gardée à chaque passage ; un callout > [!question] ou > [!retour] est relu par l'agent %%

Mon avis : à comparer avec le progiciel.

> [!question] Le coût des pics
> est-il plafonné ?

> [!retour] Préférer un hébergement en France
