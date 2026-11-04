---
name: architecture-review
description: "Revue d'une architecture logicielle ou solution à la manière d'ATAM : scénarios de qualité évalués, risques, points de sensibilité, compromis et décisions, contrôle mécanique de la structure (cycles, base partagée, couches, chaîne synchrone, dépendance externe, point unique de défaillance) et de la traçabilité des exigences, avis calculé. Peut comparer le code à l'architecture avec graphify (analyse locale) et intégrer les piliers Well-Architected d'une option cloud. À utiliser pour revoir, auditer ou valider une architecture, une option retenue ou un dossier d'architecture."
---

# architecture-review

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
écrivez la revue (scénarios, évaluations, risques) ; le script vérifie les
références, applique les règles, calcule l'avis et met en forme.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON de la revue (revue.json) : composants, flux, couches, scénarios de qualité, risques, points de sensibilité, compromis, décisions ; ou les composants et flux d'une option d'architecture-options (source) ; Facultatif : le catalogue d'exigences (exigences.json de requirements-catalog), pour la traçabilité ; Facultatif : la description cloud de la même architecture (schemas/option-<id>.cloud.json), pour les piliers Well-Architected ; Facultatif : le code source, ou le graph.json déjà produit par graphify, pour comparer le code à l'architecture ; Facultatif : accept, les écarts acceptés avec leur raison ; Règles de complétude (scénarios attendus) : references/scenarios-attendus.json, complétées par celles de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json) et de la mission (references.regles de mission.json), schéma shared/schemas/rules.schema.json ; Facultatif : les principes d'architecture du client, dans la mission (references.principes, liste principes de shared/schemas/rules.schema.json).
- **Sorties** : <sujet>.revue.md : avis, synthèse par axe, arbre d'utilité (scénarios de qualité et leur évaluation), constats, risques, points de sensibilité et compromis, décisions, traçabilité des exigences, conformité du code, points à vérifier hors de la description ; Avec --vault : dans le vault, Revues d'architecture/<titre>.md (revue-architecture, avis, evalue), Constats/<titre>/*.md et Risques/<titre>/*.md (porte-sur, issu-de).
- **`arch_review.py`** : Contrôle une architecture logicielle ou solution décrite en JSON, à la manière d'une revue ATAM : structure (cycles de dépendances synchrones, base partagée, couches, composant pivot, chaîne synchrone longue, dépendance synchrone à un système externe, point unique de défaillance), traçabilité des exigences (exigence indispensable sans composant ni décision, exigence non fonctionnelle sans scénario de qualité), scénarios de qualité (non satisfaits ou à risque sans risque noté, sans mesure, scénario attendu absent selon les règles de complétude : pointe de charge, panne, sinistre, attaque, croissance, incident), décisions et risques ; principes d'architecture du client (references.principes de la mission : composants et flux visés, champs exigés ou interdits) ; avec une description cloud, les piliers Well-Architected (wa_check.py de well-architected-review) ; avec le code, dépendances du code absentes de l'architecture et cycles entre composants, à partir du graphe de graphify (skill externe : code analysé en local ; documents, si demandés, lus par le modèle du harness ou un modèle local). Calcule l'avis et écrit <sujet>.revue.md ; avec --vault, verse la revue, ses constats et ses risques dans le vault Obsidian, notes vérifiées contre l'ontologie avant l'écriture ; avec plusieurs dépôts (code.repos, ou ceux de la mission), un graphe par dépôt et les appels entre services lus dans la configuration et les contrats (URL d'un autre service, base de données, canaux AsyncAPI) : appel absent de l'architecture, flux déclaré sans trace, base partagée, dépôt sans composant. Avec --draft, écrit d'abord le brouillon de la description (source, squelettes de scénarios) que le modèle complète et évalue. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et en reprendre les composants et les flux de l'option revue.
- **Dépend de** `well-architected-review` (`wa_check.py`, facultatif : sans lui, avertissement) : piliers Well-Architected de la description cloud (cloud).
- **Dépend de** `markdown-to-obsidian` (`lib/vault_ontology.py`, obligatoire) : ontologie du vault Obsidian (source unique) : construire et vérifier les notes écrites.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Vault Obsidian** : écrit les notes de type `revue-architecture`, `constat`, `risque` ; lit les notes typées, selon l'ontologie du vault (`vault_ontology.py` du skill markdown-to-obsidian).
- **Passe la main** au skill externe `graphify` (installé à part, contrat `shared/external/graphify.contract.json`) : comparer le code à l'architecture : le script lance graphify extract sur code.root, ou sur chaque dépôt de code.repos ou de la mission, en parallèle (--code-only par défaut, ou documents lus par le modèle du harness ou Ollama avec semantic) et lit les graphes.
- **Passe la main** au skill `architecture-options` : un constat demande de changer l'option (composant, flux, écart) : corriger options.json puis relancer.
- **Passe la main** au skill `well-architected-review` : revue Well-Architected complète d'une architecture cloud, conventions du schéma comprises.
- **Passe la main** au skill `threat-model` : analyse des menaces STRIDE de l'architecture revue.
- **Passe la main** au skill `decision-log` : dans un workflow : noter les écarts acceptés et soumettre la revue.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept ; un risque attend un responsable.

## 1. Décrire l'architecture revue

Fichier `revue.json`, `--schema` en donne la forme. Pour une option
d'`architecture-options`, ne recopiez rien : `source` reprend ses
composants, ses flux, ses écarts et son catalogue d'exigences, et
`arch_review.py revue.json --draft [--option ID]` écrit la description avec
un squelette de scénario (`a-verifier`) par exigence non fonctionnelle
indispensable ou importante et par scénario attendu : complétez et
évaluez.

```json
{
  "title": "Portail de sinistres, option A",
  "source": {"options": "options.json", "option": "A"},
  "layers": ["presentation", "application", "integration"],
  "components": [{"id": "portail", "label": "Portail web", "layer": "presentation", "count": 2},
                 {"id": "api", "label": "API déclarations", "layer": "application", "count": 2,
                  "code": ["src/api/**"]}],
  "scenarios": [{"id": "QS-01", "attribute": "performance", "importance": "haute", "difficulty": "moyenne",
                 "stimulus": "10 000 assurés déclarent après une tempête", "environment": "pic",
                 "response": "les déclarations sont enregistrées", "measure": "95 % en moins de 2 s",
                 "refs": ["ENF-001"], "components": ["api"], "status": "satisfait",
                 "note": "mise à l'échelle automatique, file vers la gestion"}],
  "risks": [{"id": "R-01", "text": "l'annuaire bloque la connexion s'il tombe", "severity": "moyenne",
             "scenarios": ["QS-02"], "mitigation": "délai court et message d'attente", "owner": "équipe portail"}],
  "tradeoffs": [{"text": "file asynchrone : charge absorbée, transmission différée",
                 "attributes": ["performance", "utilisabilite"], "decision": "ADR-001"}],
  "decisions": [{"id": "ADR-001", "title": "Option A retenue", "status": "acceptee",
                 "refs": ["ENF-004"], "file": "adr-architecture.md"}]
}
```

- **Composants et flux** : sans `source`, donnez-les (`role` parmi person,
  system, external, db, queue ; `style` sync ou async). Avec `source`, un
  composant de même `id` précise celui de l'option (`layer`, `count`,
  `code`) ; un nouvel `id` l'ajoute.
- **Scénarios de qualité** : l'arbre d'utilité. Un scénario par exigence non
  fonctionnelle indispensable ou importante (au moins), avec stimulus,
  réponse et mesure vérifiable. Évaluez chacun (`status` : satisfait,
  risque, non-satisfait, a-verifier) et dites pourquoi dans `note` :
  c'est le cœur de la revue, le seul jugement que le script ne fait pas.
- **Risques** : chaque scénario à risque ou non satisfait a son risque
  (`scenarios`), avec atténuation et responsable. Un risque noté reste un
  constat de sa gravité (RSK-03), et un scénario non satisfait un constat de
  son importance (QUA-05), tant que l'utilisateur ne l'a pas accepté
  (`accept`, par exemple `"RSK-03@R-01"`) : une atténuation prévue ne suffit
  pas à rendre l'avis favorable.
- **Sensibilités et compromis** : un point de sensibilité est un choix dont
  dépend un attribut (`sensitivities`) ; un compromis en oppose deux
  (`tradeoffs`) et se rattache à la décision qui l'assume.
- **Décisions** : les décisions structurantes, avec leur ADR (`file`).
- **Cloud** : `"cloud": "schemas/option-a.cloud.json"` ajoute les piliers
  Well-Architected de `wa_check.py` (skill `well-architected-review`).

## 2. Comparer le code (facultatif)

Si le code existe, `"code": {"root": "../src"}` et un motif `code` par
composant : le script lance graphify (skill externe, analyse locale sans
modèle) et signale dépendances non déclarées, cycles et fichiers non
rattachés. Graphe existant, documents lus (`semantic`), Copilot ou Kiro :
`references/code.md`, à lire seulement dans ce cas.

## 3. Lancer la revue

```bash
uv run scripts/arch_review.py revue.json [--fail-on moyenne]
```

`--rules` liste les règles (structure, code, traçabilité, scénarios,
décisions et risques, principes du client), détaillées dans
`references/regles.md`.

Les scénarios attendus sont des règles de complétude
(`references/scenarios-attendus.json`), complétées par celles de
l'utilisateur et de la mission (`references.regles` de mission.json).

Les principes d'architecture du client (cadre de cohérence technique,
normes) se décrivent une fois dans la mission, fichier désigné par
`references.principes` (liste `principes` de
`shared/schemas/rules.schema.json` : composants ou flux visés par `select`,
champs exigés par `require` ou interdits par `forbid`, gravité, source).
Chaque écart est un constat `PRI-01` de l'axe Principes du client ; un écart
accepté par le client va dans `accept` avec sa raison.

Le rapport donne l'avis (`défavorable` dès un constat haut ouvert,
`favorable avec réserves` dès un constat moyen ; risques et scénarios non
satisfaits compris), les compteurs et les
constats ; `REVUE.revue.md` (ou `revue.md`) reprend l'avis, la synthèse par
axe, l'arbre d'utilité, les constats, risques, compromis, décisions, la
traçabilité et ce qui ne se vérifie pas sur une description. Lisez le
rapport, pas le Markdown.

Corrigez la description (ou l'option, puis relancez `options_build.py`). Un
écart voulu s'accepte avec la raison donnée par l'utilisateur ; il reste
dans la revue sans compter :

```json
"accept": {"STR-08@portail": "CDN managé, redondant par construction"}
```

Dans un workflow dont le vault Obsidian sert de mémoire partagée, ajoutez
`--vault VAULT --folder DOSSIER` (le dossier du workflow dans le vault,
celui de `journal.py init`) : la revue y devient une note
`revue-architecture` (avis, `evalue` vers la note de l'option et l'ADR),
avec une note par constat et par risque (`porte-sur` l'exigence ou
l'option, `issu-de` la revue). Les notes sont vérifiées contre l'ontologie
du vault avant l'écriture ; à la relance, un constat disparu est retiré.

Code de sortie 1 dès un constat non accepté de gravité `--fail-on` ou plus
(défaut `haute`) : c'est la porte de revue d'un workflow. Dans un workflow,
notez au journal (`journal.py log`, skill `decision-log`) chaque écart
accepté avec sa raison.
