---
name: spec-pack
description: "Extrait d'une mission (exigences, option d'architecture retenue, domaines, modèle de données, API, plan de recette, design system, maquettes et revue UX) un dossier de spécifications autonome en Markdown : fonctionnel, UX, architecture, tests, livraison et un index de traçabilité, sans format propre à un outil, prêt pour le développement assisté par IA (BMAD, Spec Kit, Kiro, Copilot ou une équipe). Le dossier ne garde aucun lien ni trace de la mission : il se copie ou se transmet seul. À utiliser pour passer du cadrage ou de l'avant-vente au développement, ou quand l'utilisateur demande des spécifications, un PRD, des stories ou un dossier à donner à un agent de développement."
---

# spec-pack

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script
écrit tout depuis les livrables validés ; vous n'écrivez, au besoin, que
`specs.json`. Les documents ne suivent le format d'aucun outil : chacun se
lit seul et se donne tel quel à l'outil de développement choisi.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Le dossier d'un workflow ou d'une mission : exigences.json (obligatoire) et, s'ils existent, options.json, decision.json, domaines.json, modele.json, api.json, recette.json, registre.json, design-system.json, pages/*.json avec leurs maquettes et les maquettes HTML produites (pages/*.html, .css, assets/, code de la bibliothèque visée), revue-ux.json, decoupage.json ; Facultatif : specs.json, ce que la mission ne dit pas (vision, problème, utilisateurs, parcours, hors-périmètre, indicateurs de succès, regroupement en fonctionnalités, frameworks et versions) ; Facultatif : le dossier où écrire les spécifications (--out, défaut DOSSIER/specs).
- **Sorties** : Un dossier de spécifications autonome, en Markdown, sans format propre à un outil de développement IA (utilisable avec BMAD, Spec Kit, Kiro, Copilot ou une équipe) : README.md (index, conventions d'identifiants, traçabilité exigence, composants, cas, story), fonctionnel.md (vision, utilisateurs, parcours, glossaire, FR-n avec critères d'acceptation, périmètre, indicateurs, questions, hypothèses), ux.md (identité visuelle et tokens, écrans, maquettes HTML et code, composants, accessibilité, constats UX), architecture.md (décisions AD-n, pile technique et versions, composants et flux en Mermaid, données, interfaces, NFR-n, options écartées, risques), tests.md (stratégie, cas de recette, vérification des NFR, couverture), livraison.md (lots et stories S-n.m, ordre, dépendances, définition de terminé) ; chaque document ouvre sur un frontmatter YAML pour les agents (type, description, audience, language, status, defines : identifiants dont il est la source, covers : exigences traitées, related : documents cités) ; Pièces citées copiées dans annexes/, maquettes HTML au complet copiées dans maquettes/, liens recalés sur les copies ; aucun lien ni trace de la mission ou du vault (ni noms de ses pièces, ni chemins de la machine) : le dossier se copie ou se transmet seul ; empreintes des documents gardées dans .spec-pack.json de la mission ; Rapport : documents écrits, gardés ou inchangés, compteurs, pièces absentes, suite.
- **`spec_pack.py`** : Extrait d'une mission un dossier de spécifications autonome pour le développement assisté par IA, quel que soit l'outil : valide chaque pièce contre le schéma du skill qui l'a produite, renumérote les exigences (FR-n, NFR-n) en gardant l'identifiant d'origine, les regroupe en fonctionnalités, reprend l'option décidée (sinon recommandée, signalée) en décisions d'architecture, dresse la pile technique (specs.json, bibliothèque d'interface des maquettes, technologie et version des composants d'options.json), écrit l'UX depuis le design system, les pages et la revue UX, les cas de recette en critères d'acceptation, un lot par fonctionnalité et une story par exigence ; relit le tout avant d'écrire (chaque exigence dans son document, chaque FR sa story et sa ligne de couverture, aucun lien hors du dossier ni chemin de la machine : liens des copies recalés, notes du vault et wikilinks réduits à leur texte, lien sortant refusé) ; ne remplace pas un document modifié depuis le dernier export sans --force ; --check contrôle un dossier copié ailleurs. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
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
- **Passe la main** au skill `test-plan` : des exigences sont sans critère d'acceptation (counts.without_criteria) : écrire les cas de recette, puis relancer l'export.
- **Passe la main** au skill `mockup-to-html` : la mission a des maquettes mais pas encore de pages décrites ni de revue UX : les produire, puis relancer l'export.
- **Passe la main** à l'utilisateur : les spécifications sont écrites : donner le dossier (README.md et le document de l'aspect traité) à l'outil de développement IA choisi, quel qu'il soit ; spec_pack.py --check avant de transmettre une copie.

## 1. Exporter

```bash
uv run scripts/spec_pack.py DOSSIER
uv run scripts/spec_pack.py DOSSIER --out DOSSIER_DES_SPECS
```

`DOSSIER` est celui du workflow ou de la mission ; seul `exigences.json`
est obligatoire. Sans `--out`, les documents vont dans `DOSSIER/specs/`.

| Document | Tiré de |
| --- | --- |
| `README.md` | index des documents, conventions d'identifiants, traçabilité exigence, composants, cas, story ; ce qui reste à compléter |
| `fonctionnel.md` | vision, problème, utilisateurs, parcours (`specs.json`), glossaire, exigences fonctionnelles FR-n par fonctionnalité avec leurs critères d'acceptation (cas de recette), périmètre, indicateurs, questions ouvertes, hypothèses du registre |
| `ux.md` | `design-system.json` (identité visuelle, tokens en JSON), `pages/*.json` (écrans, maquettes HTML, rendus), code de la bibliothèque visée, `decoupage.json` (composants), `revue-ux.json` (accessibilité, constats), exigences d'interface UX-n |
| `architecture.md` | option décidée, style et relations entre contextes en décisions AD-n, pile technique, composants et flux en Mermaid, entités et champs, interfaces de l'API, NFR-n, options écartées, risques |
| `tests.md` | stratégie, cas de recette par fonctionnalité, vérification des NFR, exigences sans cas, couverture |
| `livraison.md` | un lot par fonctionnalité, une story S-n.m par exigence fonctionnelle avec ses critères, ordre de réalisation, dépendances, définition de terminé |

Chaque document commence par un frontmatter YAML lisible par tout agent :
`type`, `description`, `audience`, `language`, `status`, `defines` (les
identifiants dont il est la source : FR-n, AD-n et NFR-n, T-n, S-n.m, UX-n),
`covers` (les exigences qu'il traite sans les définir) et `related` (les
autres documents qu'il cite). Un agent choisit ainsi le document à lire
sans l'ouvrir.

`ux.md` n'est écrit que si la mission porte ses sources, `architecture.md`
que si elle a des options. Une ligne de pile sans version est marquée
« à fixer » et comptée dans `counts.stack_without_version`. L'option
exportée est celle de `decision.json`, sinon la recommandation (signalée
dans `warnings`) ; `--option ID` en impose une autre.

Le dossier est autonome : les pièces citées sont copiées dans `annexes/`,
les maquettes HTML et leurs fichiers dans `maquettes/`, leurs liens
recalés sur les copies ; un lien vers une note du vault, un autre fichier
de la mission ou un wikilink devient du texte (compté dans `warnings`). Un
lien qui sortirait du dossier (par exemple écrit dans `specs.json`) ou un
chemin absolu fait échouer l'export. Les documents ne nomment pas les
pièces de la mission ; les empreintes qui protègent un document modifié
sont dans `.spec-pack.json` de la mission. Avant de transmettre une
copie : `uv run scripts/spec_pack.py --check DOSSIER_DES_SPECS`.

## 2. Lire le rapport

Lisez `files`, `counts`, `missing` et `warnings`, pas les documents écrits.

- `missing` : pièce absente et commande qui la produit. Dites-le à
  l'utilisateur ; ne la fabriquez pas pour l'export.
- `counts.without_criteria` : exigences fonctionnelles sans cas de recette
  ni mesure, donc stories sans critère d'acceptation.
- `status: garde` : document modifié depuis le dernier export, laissé tel
  quel. `--force` seulement si l'utilisateur le demande.

## 3. Compléter avec `specs.json` (facultatif)

Si l'utilisateur veut des spécifications complètes, écrivez
`DOSSIER/specs.json` avec ce que les sources disent et que les livrables
ne portent pas, puis relancez l'export. Schéma :
`uv run scripts/spec_pack.py --schema`.

```json
{"vision": "…", "users": [{"name": "Assuré", "jobs": ["déclarer un sinistre sans se déplacer"]}],
 "journeys": [{"title": "…", "persona": "…", "path": ["…", "…"], "refs": ["EF-001"]}],
 "non_goals": ["…"], "metrics": [{"name": "…", "target": "…", "refs": ["EF-001"]}],
 "features": [{"name": "Déclaration", "refs": ["EF-001", "EF-002"]}],
 "stack": [{"name": "React", "version": "18.3", "role": "interface"}, {"name": "Spring Boot", "version": "3.3", "role": "API"}]}
```

N'inventez ni indicateur, ni parcours, ni version : demandez à
l'utilisateur les frameworks et versions retenus s'il veut une pile
complète ; un champ sans source reste absent et sa section est omise.
Sans `features`, les exigences sont regroupées par contexte délimité
(`domaines.json`), sinon par domaine.

## 4. Suite

Donnez à l'utilisateur le champ `next` du rapport : le dossier se donne
tel quel à l'outil de développement (README.md et le document de l'aspect
traité, ou tout le dossier). Une exigence qui change se corrige dans le
catalogue de la mission, puis l'export se relance : les documents non
modifiés sont réécrits, les autres gardés.
