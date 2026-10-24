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
- **Entrées** : Description JSON de la revue (revue.json) : composants, flux, couches, scénarios de qualité, risques, points de sensibilité, compromis, décisions ; ou les composants et flux d'une option d'architecture-options (source) ; Facultatif : le catalogue d'exigences (exigences.json de requirements-catalog), pour la traçabilité ; Facultatif : la description cloud de la même architecture (schemas/option-<id>.cloud.json), pour les piliers Well-Architected ; Facultatif : le code source, ou le graph.json déjà produit par graphify, pour comparer le code à l'architecture ; Facultatif : accept, les écarts acceptés avec leur raison.
- **Sorties** : <sujet>.revue.md : avis, synthèse par axe, arbre d'utilité (scénarios de qualité et leur évaluation), constats, risques, points de sensibilité et compromis, décisions, traçabilité des exigences, conformité du code, points à vérifier hors de la description.
- **`arch_review.py`** : Contrôle une architecture logicielle ou solution décrite en JSON, à la manière d'une revue ATAM : structure (cycles de dépendances synchrones, base partagée, couches, composant pivot, chaîne synchrone longue, dépendance synchrone à un système externe, point unique de défaillance), traçabilité des exigences (exigence indispensable sans composant ni décision, exigence non fonctionnelle sans scénario de qualité), scénarios de qualité (non satisfaits ou à risque sans risque noté, sans mesure), décisions et risques ; avec une description cloud, les piliers Well-Architected (wa_check.py de well-architected-review) ; avec le code, dépendances du code absentes de l'architecture et cycles entre composants, à partir du graphe de graphify (skill externe, analyse locale --code-only). Calcule l'avis et écrit <sujet>.revue.md. Rapport JSON, codes de sortie : 0 revue écrite, aucun constat non accepté au seuil --fail-on ; 1 description illisible, référence inconnue, graphify manquant ou en échec, ou constat non accepté au seuil --fail-on ; sauf erreur, le rapport et <sujet>.revue.md sont tout de même produits.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et en reprendre les composants et les flux de l'option revue.
- **Dépend de** `well-architected-review` (`wa_check.py`, facultatif : sans lui, avertissement) : piliers Well-Architected de la description cloud (cloud).
- **Passe la main** au skill externe `graphify` (installé à part, contrat `shared/external/graphify.contract.json`) : comparer le code à l'architecture : le script lance graphify extract --code-only sur code.root (analyse locale) et lit le graphe.
- **Passe la main** au skill `architecture-options` : un constat demande de changer l'option (composant, flux, écart) : corriger options.json puis relancer.
- **Passe la main** au skill `well-architected-review` : revue Well-Architected complète d'une architecture cloud, conventions du schéma comprises.
- **Passe la main** au skill `threat-model` : analyse des menaces STRIDE de l'architecture revue.
- **Passe la main** au skill `decision-log` : dans un workflow : noter les écarts acceptés et soumettre la revue.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept ; un risque attend un responsable.

## 1. Décrire l'architecture revue

Fichier `revue.json`, `--schema` en donne la forme. Pour une option
d'`architecture-options`, ne recopiez rien : `source` reprend ses
composants, ses flux, ses écarts et son catalogue d'exigences.

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
  (`scenarios`), avec atténuation et responsable.
- **Sensibilités et compromis** : un point de sensibilité est un choix dont
  dépend un attribut (`sensitivities`) ; un compromis en oppose deux
  (`tradeoffs`) et se rattache à la décision qui l'assume.
- **Décisions** : les décisions structurantes, avec leur ADR (`file`).
- **Cloud** : `"cloud": "schemas/option-a.cloud.json"` ajoute les piliers
  Well-Architected de `wa_check.py` (skill `well-architected-review`).

## 2. Comparer le code (facultatif)

Si le code existe, `"code": {"root": "../src"}` et un motif `code` par
composant (`src/api/**`, un dossier, `*.py`). Le script lance
`graphify extract RACINE --code-only` (skill externe graphify, installé à
part, `uv tool install graphifyy`) : analyse locale par tree-sitter, sans
modèle ni service en ligne ; le graphe reste dans `graphify-out/` à côté de
la revue, réutilisé aux relances. Avec un graphe déjà produit, donnez
`"graph"`. Le script signale les dépendances du code entre composants sans
flux déclaré, les cycles entre composants et les fichiers non rattachés.
N'utilisez pas graphify sans `--code-only` : les documents partiraient vers
un modèle.

## 3. Lancer la revue

```bash
uv run scripts/arch_review.py revue.json [--fail-on moyenne]
```

`--rules` liste les règles :

| Axe | Contrôles |
| --- | --- |
| Structure | cycle d'appels synchrones, base partagée par plusieurs composants, dépendance vers une couche supérieure, composant pivot (6 voisins ou plus), chaîne de plus de 4 appels synchrones, dépendance synchrone à un externe sur le parcours utilisateur, point unique de défaillance quand la disponibilité est exigée, composant sans flux |
| Code | dépendance du code absente de l'architecture, cycle entre composants dans le code, code non rattaché |
| Traçabilité | exigence indispensable sans composant, décision ni scénario (ou non couverte par l'option), exigence non fonctionnelle sans scénario, composant sans exigence ni décision |
| Scénarios | non satisfait ou à risque sans risque noté, sans mesure, à vérifier |
| Décisions et risques | aucune décision, décision proposée, compromis sans décision, risque haut sans atténuation, risque sans responsable |

Le rapport donne l'avis (`défavorable` dès un constat haut ouvert,
`favorable avec réserves` dès un constat moyen), les compteurs et les
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

Code de sortie 1 dès un constat non accepté de gravité `--fail-on` ou plus
(défaut `haute`) : c'est la porte de revue d'un workflow. Dans un workflow,
notez au journal (`journal.py log`, skill `decision-log`) chaque écart
accepté avec sa raison.
