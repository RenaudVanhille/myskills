---
name: bmad-export
description: "Exporte une mission (exigences, option d'architecture retenue, domaines, modèle de données, API, plan de recette) vers les artefacts de planification de BMAD Method v6 : product brief, PRD, architecture, ébauche d'epics et de stories, dans _bmad-output/planning-artifacts, prêts pour les agents BMAD. À utiliser pour passer du cadrage ou de l'avant-vente au développement avec BMAD, ou quand l'utilisateur demande un PRD, des epics ou des stories au format BMAD à partir d'un dossier déjà produit."
---

# bmad-export

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script
écrit tout depuis les livrables validés ; vous n'écrivez, au besoin, que
`bmad.json`. Format visé : [BMAD Method](https://github.com/bmad-code-org/BMAD-METHOD)
6.12 (licence MIT, BMad Code, LLC), dont les titres de section sont repris
de ses gabarits ; rien de BMAD n'est installé ni appelé par ce skill.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Le dossier d'un workflow ou d'une mission : exigences.json (obligatoire) et, s'ils existent, options.json, decision.json, domaines.json, modele.json, api.json, recette.json, registre.json ; Facultatif : bmad.json, ce que la mission ne dit pas (vision, problème, utilisateurs, parcours, hors-périmètre, indicateurs de succès, regroupement en fonctionnalités) ; Facultatif : la racine du projet de développement où BMAD Method est ou sera installé (--out).
- **Sorties** : Dans le dossier de planification de BMAD Method v6 (_bmad-output/planning-artifacts, ou celui de la configuration _bmad/ du projet) : brief.md, prd.md (FR-n par fonctionnalité, NFR-n, glossaire, périmètre, questions, hypothèses), architecture.md (décisions AD-n, flux et entités en Mermaid, interfaces), epics.md (ébauche des epics et stories) et addendum.md (correspondance des identifiants, options écartées, pièces de la mission) ; Rapport : fichiers écrits, gardés ou inchangés, compteurs, pièces absentes, suite dans BMAD.
- **`bmad_export.py`** : Exporte les livrables validés d'une mission vers les artefacts de planification de BMAD Method v6 : valide chaque pièce contre le schéma du skill qui l'a produite, renumérote les exigences (FR-n, NFR-n) en gardant l'identifiant d'origine, regroupe les exigences fonctionnelles en fonctionnalités, reprend l'option décidée (sinon recommandée, signalée) en décisions d'architecture, écrit une epic par fonctionnalité et une story par exigence avec les cas de recette en critères d'acceptation ; relit le tout avant d'écrire (chaque exigence dans le PRD, chaque FR dans une story, titres reconnus par sprint_plan.py de BMAD, liens) ; ne remplace pas un artefact modifié depuis le dernier export sans --force. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et decision.json contre leur schéma.
- **Dépend de** `domain-design` (`domain_build.py`, facultatif : sans lui, avertissement) : valider domaines.json contre son schéma.
- **Dépend de** `data-model` (`model_build.py`, facultatif : sans lui, avertissement) : valider modele.json contre son schéma.
- **Dépend de** `api-contract` (`api_build.py`, facultatif : sans lui, avertissement) : valider api.json contre son schéma.
- **Dépend de** `test-plan` (`test_build.py`, facultatif : sans lui, avertissement) : valider recette.json contre son schéma.
- **Dépend de** `tender-response` (`assumptions.py`, facultatif : sans lui, avertissement) : valider registre.json contre son schéma.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, facultatif : sans lui, avertissement) : lire le nom de la mission et le dossier de son workflow dans mission.json.
- **Passe la main** au skill `requirements-catalog` : exigences.json manque ou une exigence est à reformuler : le catalogue se corrige à la source, puis l'export se relance.
- **Passe la main** au skill `test-plan` : des stories sont sans critère d'acceptation (counts.without_criteria) : écrire les cas de recette, puis relancer l'export.
- **Passe la main** à l'utilisateur : les artefacts sont écrits : installer BMAD Method dans le projet cible et poursuivre avec ses skills (bmad-prd, bmad-create-epics-and-stories, bmad-sprint-planning, bmad-build).

## 1. Exporter

```bash
uv run scripts/bmad_export.py DOSSIER
uv run scripts/bmad_export.py DOSSIER --out RACINE_DU_DEPOT_DE_CODE
```

`DOSSIER` est celui du workflow ou de la mission ; seul `exigences.json`
est obligatoire. Sans `--out`, les artefacts vont dans
`DOSSIER/_bmad-output/planning-artifacts/` ; avec `--out`, dans le dossier
de planification du projet cible (lu dans sa configuration `_bmad/` s'il
en a une), et les pièces citées y sont copiées dans `sources/`.

| Artefact | Tiré de |
| --- | --- |
| `brief.md` | contexte, option retenue, utilisateurs, mesures indispensables, périmètre |
| `prd.md` | exigences fonctionnelles en FR-n par fonctionnalité, non fonctionnelles en NFR-n, glossaire, périmètre (souhaitable : reporté), questions ouvertes, hypothèses du registre |
| `architecture.md` | option décidée, style et relations entre contextes en décisions AD-n, flux et entités en Mermaid, interfaces de l'API |
| `epics.md` | une epic par fonctionnalité, une story par exigence fonctionnelle, cas de recette en critères d'acceptation ; ébauche à reprendre dans BMAD |
| `addendum.md` | correspondance FR-n / identifiant d'origine, options écartées, liens vers les pièces |

L'option exportée est celle de `decision.json`, sinon la recommandation
(signalée dans `warnings`) ; `--option ID` en impose une autre.

## 2. Lire le rapport

Lisez `files`, `counts`, `missing` et `warnings`, pas les fichiers écrits.

- `missing` : pièce absente et commande qui la produit. Dites-le à
  l'utilisateur ; ne la fabriquez pas pour l'export.
- `counts.without_criteria` : exigences fonctionnelles sans cas de recette
  ni mesure, donc stories sans critère d'acceptation.
- `status: garde` : artefact modifié depuis le dernier export (par
  l'utilisateur ou un agent BMAD), laissé tel quel. `--force` seulement si
  l'utilisateur le demande.

## 3. Compléter avec `bmad.json` (facultatif)

Si l'utilisateur veut un PRD complet, écrivez `DOSSIER/bmad.json` avec ce
que les sources disent et que les livrables ne portent pas, puis relancez
l'export. Schéma : `uv run scripts/bmad_export.py --schema`.

```json
{"vision": "…", "users": [{"name": "Assuré", "jobs": ["déclarer un sinistre sans se déplacer"]}],
 "journeys": [{"title": "…", "persona": "…", "path": ["…", "…"], "refs": ["EF-001"]}],
 "non_goals": ["…"], "metrics": [{"name": "…", "target": "…", "refs": ["EF-001"]}],
 "features": [{"name": "Déclaration", "refs": ["EF-001", "EF-002"]}]}
```

N'inventez ni indicateur ni parcours : un champ sans source reste absent,
et sa section est omise du PRD. Sans `features`, les exigences sont
regroupées par contexte délimité (`domaines.json`), sinon par domaine.

## 4. Suite dans BMAD

Donnez à l'utilisateur le champ `next` du rapport : BMAD installé dans le
projet (`npx bmad-method install`), `bmad-prd` valide le PRD,
`bmad-create-epics-and-stories` reprend l'ébauche, `bmad-sprint-planning`
écrit `sprint-status.yaml`, `bmad-build` développe. Une exigence qui
change se corrige dans le catalogue de la mission, puis l'export se
relance : les artefacts non modifiés sont réécrits, les autres gardés.
