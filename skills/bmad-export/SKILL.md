---
name: bmad-export
description: "Exporte une mission (exigences, option d'architecture retenue, domaines, modèle de données, API, plan de recette, design system, maquettes et revue UX) vers les artefacts de planification de BMAD Method v6 : product brief, PRD, architecture avec sa pile technique, documents UX (DESIGN.md, EXPERIENCE.md), ébauche d'epics et de stories, dans _bmad-output/planning-artifacts, prêts pour les agents BMAD. À utiliser pour passer du cadrage ou de l'avant-vente au développement avec BMAD, ou quand l'utilisateur demande un PRD, des epics ou des stories au format BMAD à partir d'un dossier déjà produit."
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
- **Entrées** : Le dossier d'un workflow ou d'une mission : exigences.json (obligatoire) et, s'ils existent, options.json, decision.json, domaines.json, modele.json, api.json, recette.json, registre.json, design-system.json, pages/*.json avec leurs maquettes et les maquettes HTML produites (pages/*.html, .css, assets/, code de la bibliothèque visée), revue-ux.json, decoupage.json ; Facultatif : bmad.json, ce que la mission ne dit pas (vision, problème, utilisateurs, parcours, hors-périmètre, indicateurs de succès, regroupement en fonctionnalités, frameworks et versions) ; Facultatif : la racine du projet de développement où BMAD Method est ou sera installé (--out).
- **Sorties** : Dans le dossier de planification de BMAD Method v6 (_bmad-output/planning-artifacts, ou celui de la configuration _bmad/ du projet) : brief.md, prd.md (FR-n par fonctionnalité, NFR-n, glossaire, périmètre, questions, hypothèses), architecture.md (décisions AD-n, flux et entités en Mermaid, interfaces, pile technique avec frameworks et versions), epics.md (ébauche des epics et stories) et addendum.md (correspondance des identifiants, options écartées, pièces de la mission) ; Si la mission a un design system, des pages décrites d'après les maquettes, une revue UX ou un découpage en composants : ux-designs/ux-<nom>/DESIGN.md (tokens et identité visuelle) et EXPERIENCE.md (écrans, composants, accessibilité, parcours, constats UX), maquettes d'origine, maquettes HTML au complet (pages, styles, images, code de la bibliothèque visée) et rendus copiés dans mockups/ ; bundle autonome : pièces citées copiées dans sources/, liens recalés sur les copies, aucun lien ni trace de la mission ou du vault : il se copie ou se transmet seul ; Rapport : fichiers écrits, gardés ou inchangés, compteurs, pièces absentes, suite dans BMAD.
- **`bmad_export.py`** : Exporte les livrables validés d'une mission vers les artefacts de planification de BMAD Method v6 : valide chaque pièce contre le schéma du skill qui l'a produite, renumérote les exigences (FR-n, NFR-n) en gardant l'identifiant d'origine, regroupe les exigences fonctionnelles en fonctionnalités, reprend l'option décidée (sinon recommandée, signalée) en décisions d'architecture, dresse la pile technique (bmad.json, bibliothèque d'interface des maquettes, technologie et version des composants d'options.json), écrit les documents UX depuis le design system, les pages et la revue UX, écrit une epic par fonctionnalité et une story par exigence avec les cas de recette en critères d'acceptation ; relit le tout avant d'écrire (chaque exigence dans le PRD, chaque FR dans une story, titres reconnus par sprint_plan.py de BMAD, aucun lien hors du bundle ni trace de la mission (noms des pièces et des documents sources, chemins absolus, marque et empreinte dans le frontmatter) : liens Markdown, HTML et CSS des copies recalés, notes du vault et wikilinks réduits à leur texte, lien sortant refusé) ; ne remplace pas un artefact modifié depuis le dernier export sans --force. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et decision.json contre leur schéma.
- **Dépend de** `domain-design` (`domain_build.py`, facultatif : sans lui, avertissement) : valider domaines.json contre son schéma.
- **Dépend de** `data-model` (`model_build.py`, facultatif : sans lui, avertissement) : valider modele.json contre son schéma.
- **Dépend de** `api-contract` (`api_build.py`, facultatif : sans lui, avertissement) : valider api.json contre son schéma.
- **Dépend de** `test-plan` (`test_build.py`, facultatif : sans lui, avertissement) : valider recette.json contre son schéma.
- **Dépend de** `tender-response` (`assumptions.py`, facultatif : sans lui, avertissement) : valider registre.json contre son schéma.
- **Dépend de** `design-system` (`ds_build.py`, facultatif : sans lui, avertissement) : valider design-system.json contre son schéma.
- **Dépend de** `mockup-to-html` (`page_build.py`, facultatif : sans lui, avertissement) : valider les pages décrites d'après les maquettes contre leur schéma.
- **Dépend de** `mockup-to-html` (`ux_review.py`, facultatif : sans lui, avertissement) : valider revue-ux.json contre son schéma.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, facultatif : sans lui, avertissement) : lire le nom de la mission et le dossier de son workflow dans mission.json.
- **Passe la main** au skill `requirements-catalog` : exigences.json manque ou une exigence est à reformuler : le catalogue se corrige à la source, puis l'export se relance.
- **Passe la main** au skill `test-plan` : des stories sont sans critère d'acceptation (counts.without_criteria) : écrire les cas de recette, puis relancer l'export.
- **Passe la main** au skill `mockup-to-html` : la mission a des maquettes mais pas encore de pages décrites ni de revue UX : les produire, puis relancer l'export.
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
en a une). Ce dossier est un bundle autonome : les pièces citées y sont
copiées dans `sources/`, les maquettes HTML et leurs fichiers dans
`mockups/` du dossier UX, leurs liens recalés sur les copies ; un lien
vers une note du vault, un autre fichier de la mission ou un wikilink
devient du texte (compté dans `warnings`). Un lien qui sortirait du
bundle (par exemple écrit dans `bmad.json`) ou un chemin absolu fait
échouer l'export. Le bundle ne garde aucune trace de la mission (ni noms
de ses pièces, ni marque d'export) : les empreintes qui protègent un
artefact repris dans BMAD sont dans `.bmad-export.json` de la mission.
Avant de transmettre un bundle copié ailleurs :
`uv run scripts/bmad_export.py --check DOSSIER_DU_BUNDLE`.

| Artefact | Tiré de |
| --- | --- |
| `brief.md` | contexte, option retenue, utilisateurs, mesures indispensables, périmètre |
| `prd.md` | exigences fonctionnelles en FR-n par fonctionnalité, non fonctionnelles en NFR-n, glossaire, périmètre (souhaitable : reporté), questions ouvertes, hypothèses du registre |
| `architecture.md` | option décidée, style et relations entre contextes en décisions AD-n, flux et entités en Mermaid, interfaces de l'API, pile technique |
| `ux-designs/ux-<nom>/DESIGN.md` | `design-system.json` : tokens en frontmatter, couleurs, typographie, espacements, composants |
| `ux-designs/ux-<nom>/EXPERIENCE.md` | `pages/*.json` (un écran par page, maquette d'origine, maquette HTML, rendu et comparaison liés), maquettes HTML et code de la bibliothèque visée (`pages/*.html`, `.css`, `assets/`, `.tsx`, `.vue`...), `decoupage.json` (composants, bibliothèque visée), `revue-ux.json` (accessibilité, constats), parcours de `bmad.json` |
| `epics.md` | une epic par fonctionnalité, une story par exigence fonctionnelle, cas de recette en critères d'acceptation ; ébauche à reprendre dans BMAD |
| `addendum.md` | correspondance FR-n / identifiant d'origine, options écartées, liens vers les pièces |

La pile technique (`Stack`) réunit le champ `stack` de `bmad.json`, la
bibliothèque d'interface visée par le découpage des maquettes (`--target`
de `ui_breakdown.py`) et la technologie des composants de l'option, avec leur `version`
quand `options.json` la donne (c'est là qu'une version se décide et se
trace ; `stack` sert au reste : base de tests, outillage) ; une
ligne sans version est marquée « à fixer » et comptée dans
`counts.stack_without_version`. Les deux documents UX ne sont écrits que
si la mission porte leurs sources.

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
 "features": [{"name": "Déclaration", "refs": ["EF-001", "EF-002"]}],
 "stack": [{"name": "React", "version": "18.3", "role": "interface"}, {"name": "Spring Boot", "version": "3.3", "role": "API"}]}
```

N'inventez ni indicateur, ni parcours, ni version : demandez à
l'utilisateur les frameworks et versions retenus s'il veut une pile
complète ; un champ sans source reste absent,
et sa section est omise du PRD. Sans `features`, les exigences sont
regroupées par contexte délimité (`domaines.json`), sinon par domaine.

## 4. Suite dans BMAD

Donnez à l'utilisateur le champ `next` du rapport : BMAD installé dans le
projet (`npx bmad-method install`), `bmad-prd` valide le PRD,
`bmad-ux` reprend les documents UX,
`bmad-create-epics-and-stories` reprend l'ébauche, `bmad-sprint-planning`
écrit `sprint-status.yaml`, `bmad-build` développe. Une exigence qui
change se corrige dans le catalogue de la mission, puis l'export se
relance : les artefacts non modifiés sont réécrits, les autres gardés.
