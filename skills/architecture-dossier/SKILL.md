---
name: architecture-dossier
description: "Assemble le dossier d'architecture technique (DAT) d'un projet à partir des livrables validés d'un workflow : synthèse, exigences, options, décision (ADR), schémas, revue d'architecture, menaces, Well-Architected, chiffrage et journal, selon un gabarit de sections. Signale les pièces manquantes et vérifie les liens. À utiliser pour préparer un comité d'architecture ou livrer le dossier d'un projet."
---

# architecture-dossier

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le dossier
reprend les livrables déjà validés : vous n'écrivez que la synthèse.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier d'un workflow d'architecture (livrables validés : exigences.md, options.md, ADR, schémas PNG, revue, menaces, Well-Architected, chiffrage, journal) ; synthese.md : la synthèse pour le comité, seule pièce écrite pour le dossier ; Facultatif : un gabarit de sections (JSON) propre à l'organisation.
- **Sorties** : dossier-architecture.md : DAT en un seul Markdown (sommaire, sections numérotées, pièces reprises, schémas intégrés, annexes), liens vérifiés.
- **`dossier_build.py`** : Assemble le DAT d'un dossier de workflow selon un gabarit de sections : pièces Markdown reprises (frontmatter et titre retirés, titres décalés, liens recalés), images intégrées, fichiers listés en annexe ; signale chaque section obligatoire sans pièce avec la commande qui la produit ; relit le dossier produit et vérifie chaque lien et chaque image. Rapport JSON, codes de sortie : 0 dossier produit (sections manquantes et liens cassés en avertissements) ; 1 dossier introuvable, gabarit invalide, ou section obligatoire manquante avec --strict ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** à l'agent `document-publisher` : le dossier doit être livré en Word, PDF, HTML ou XWiki.
- **Passe la main** au skill `decision-log` : le dossier est un livrable d'étape : le soumettre à la revue (journal.py submit).
- **Passe la main** à l'utilisateur : une section obligatoire manque : produire la pièce, ou l'écarter du gabarit avec sa raison.

## 1. Écrire la synthèse

Dans le dossier du workflow, `synthese.md` en une page au plus, pour le
comité : objet du projet, option retenue et pourquoi (reprendre la
décision), avis de la revue s'il existe, coût total et fonctionnement
mensuel si le chiffrage existe, points ouverts et décisions attendues.
Reprenez les chiffres des rapports des scripts, sans relire les livrables.
`contexte.md` (enjeux, périmètre, hors périmètre) est facultatif.

## 2. Assembler

```bash
uv run scripts/dossier_build.py DOSSIER
```

Le gabarit par défaut (`references/gabarit-dat.json`) donne l'ordre des
sections : synthèse, contexte, exigences, options, décision, schémas,
traçabilité, revue, menaces, Well-Architected, chiffrage, pièces sources et
journal en annexe. Une section facultative sans pièce disparaît ; une
section obligatoire sans pièce reste avec « À compléter » et un
avertissement qui donne la commande qui la produit. `--strict` en fait une
erreur, sans fichier produit : à utiliser avant un comité.

`--template avis` donne l'avis d'architecture sur un dossier reçu
(workflow `revue-dossier`) : synthèse et avis, exigences, revue, schémas,
menaces, Well-Architected et documents reçus. Un gabarit propre à l'organisation (autres sections, autre ordre) se passe
avec `--template` ; `--schema` donne sa forme. Ne relisez pas
`dossier-architecture.md` : le rapport donne les sections reprises, les
manquantes et les liens cassés.

## 3. Livrer

Dans un workflow, le dossier est le livrable de l'étape `dossier` :
`journal.py submit`. Pour Word, PDF, HTML ou XWiki, passez la main à
`document-publisher` avec `dossier-architecture.md`.
