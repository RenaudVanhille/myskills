---
name: solution-estimate
description: "Chiffre une solution à partir du catalogue d'exigences et de l'option d'architecture retenue : charge de réalisation par lot, phase et profil (estimation à trois points, fourchette calculée), pilotage et provision, coût d'infrastructure, maintenance et exploitation, coût total sur plusieurs années, budget tenu ou dépassé, le tout en trois hypothèses de production comparées (sans IA, avec IA, dev IA natif), et un plan de charge par tâche (complexité, jours, heures), seul produit sans taux journaliers. Les calculs et les contrôles de couverture sont faits par script. À utiliser pour chiffrer un projet, estimer une charge, un budget, un coût d'infrastructure, un coût total de possession ou le gain d'un développement assisté par l'IA."
---

# solution-estimate

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
découpez la solution en lots et estimez chaque lot ; le script vérifie les
références, fait tous les calculs, met en forme et relit son CSV.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Options d'architecture (options.json d'architecture-options), avec la décision ou la recommandation ; Description JSON du chiffrage : title, context, requirements, architecture, option, currency, horizon, hosting (provider, qualifications, refs), providers, rates (facultatif), hours_per_day, work (id, name, phase, component, refs, effort, complexity, ai), overheads, contingency, infra (id, name, component, environment, kind, provider, quantity, unit_cost, period, basis), run, scenarios (avec-ia, ia-natif : factors, gain_uncertainty, setup_percent, tooling_per_day, run_factor, contingency, basis), ai_cost (tokens_per_day, phases, complexity, levels, models, prices, mix, exchange_rate, measured, basis), budget (dont ai), assumptions, exclusions ; Catalogue des hébergeurs (shared/providers.json, commun aux skills cloud : AWS, Azure, Google Cloud, OVHcloud, Cloud Temple, Outscale, S3NS, Bleu, NumSpot, Scaleway, interne ; juridiction, qualifications SecNumCloud, HDS), complété par un catalogue propre au projet ; Hypothèses de production par défaut (references/hypotheses-ia.json : facteurs par phase, incertitude, adoption, outillage IA, run, avec leurs sources), lues par le script ; Grille du coût IA du développement (references/jetons-ia.json, versionnée et datée : millions de jetons par jour de l'équipe en fourchette, poids des phases et des complexités, part de chaque niveau de travail, modèle par niveau, tarifs par modèle, mélange entrée, cache, sortie mesuré sur le dépôt, taux de change), lue par le script, jamais de tarif en ligne ; Règles de complétude (postes attendus) : references/postes-attendus.json, complétées par celles de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json) et de la mission (references.regles de mission.json), schéma shared/schemas/rules.schema.json ; Pour la calibration : missions passées comparables désignées dans mission.json (analogues), lues seulement, mission par mission ; Abaques donnés avant le lancement (shared/schemas/abaques.schema.json) : ~/.myskills/abaques.json ou MYSKILLS_ABAQUES, references.abaques de mission.json, --abaques ; section challenge pour les seuils des points à challenger ; sans eux, seuils par défaut à calibrer.
- **Sorties** : <nom>.md : chiffrage pour la revue (synthèse, budget, hypothèses sans IA, avec IA et IA natif, coût IA du développement, lots, phases, profils, infrastructure, run, coût total par année, points à challenger et réemploi, couverture, hypothèses, exclusions) ; <nom>.csv : lignes détaillées (lots, pilotage, infrastructure, run), séparateur point-virgule, relu par le script ; <nom>.hypotheses.csv : lignes de chaque hypothèse de production (sans IA, avec IA, IA natif : lots avec leur facteur, adoption, pilotage, outillage IA, run), relu par le script ; <nom>.charges.md et <nom>.charges.csv : plan de charge sans montant (chaque tâche avec sa complexité, ses jours et ses heures, sans IA, avec IA et IA natif ; par phase et par profil ; coût IA du développement en jetons et en dollars), relu par le script ; seuls produits sans rates ; <nom>.ia.json : coût IA du développement (jetons des agents et assistants, en dollars et dans la devise : médiane et fourchette P10-P90 à 80 %, par hypothèse et par lot, fiabilité des hypothèses, confiance de tenir le budget IA), relu par le script ; repris par spec-pack dans livraison.md ; <nom>.parcours.json (avec journeys) : coût par parcours, hypothèse et poste, avec références, relu par le script, aussi en section du chiffrage ; parcours.md (journeys_view.py) : workflow, coût et points d'attention par parcours, pour la restitution.
- **`estimate_build.py`** : Vérifie profils, composants de l'option (options.json), exigences (exigences.json) et hébergeur de chaque ligne d'infrastructure (catalogue, qualifications SecNumCloud, HDS...) ; calcule charge espérée par lot (trois points), fourchette P10-P90, pilotage, provision, infrastructure, run et coût total, pour trois hypothèses de production (sans IA, avec IA, dev IA natif) et le coût IA du développement (jetons : médiane et P10-P90 par hypothèse et par lot, fiabilité, budget IA) ; signale exigences sans lot, composants non chiffrés, postes attendus absents (règles de complétude), estimations incertaines, budget dépassé, écarts aux missions analogues ; applique le réemploi déclaré et relève les points à challenger (seuils des abaques, sinon par défaut) ; avec journeys, répartit la réalisation par parcours utilisateur et par poste, avec ses références, postes partagés au prorata, somme contrôlée ; écrit chiffrage, CSV, plan de charge sans montant (seul sans taux), <nom>.ia.json et <nom>.parcours.json, puis les relit. Avec --draft : brouillon de la description (lots par composant, transverses, valeurs usuelles, budget, infrastructure de cloud-cost, lots des experts --lots, transverses par ratio) ; le modèle n'écrit que les charges. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`journeys_view.py`** : Écrit parcours.md pour une restitution depuis <nom>.parcours.json : synthèse du coût par parcours, découpage en lots (lots propres et parcours qu'ils servent, lots partagés), puis par parcours son workflow (Mermaid : persona et étapes, sinon composants touchés), son coût et ses principaux postes dans l'hypothèse choisie, ses points d'attention (risques, hypothèses, dépendances, contrôles) ; recontrôle la somme, ne recalcule rien ; --export rend les workflows en image (diagram-export). Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json contre son schéma.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `markdown-to-obsidian` (`lib/vault_ontology.py`, obligatoire) : ontologie du vault Obsidian (source unique) : construire et vérifier les notes écrites.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Dépend de** `cloud-architecture` (`lib/providers.json`, obligatoire) : catalogue commun des hébergeurs.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : journeys_view.py --export : rendre le workflow de chaque parcours en image dans le même appel.
- **Vault Obsidian** : écrit les notes de type `chiffrage`, `lot` ; lit les notes typées, selon l'ontologie du vault (`vault_ontology.py` du skill markdown-to-obsidian).
- **Passe la main** au skill `decision-log` : noter les hypothèses de chiffrage, soumettre le chiffrage à la revue.
- **Passe la main** à l'agent `document-publisher` : le chiffrage doit être livré en Word, HTML ou XWiki.
- **Passe la main** au skill `architecture-options` : le coût chiffré contredit la note du critère coût d'une option : revoir sa note.

## 1. Préparer

Partez de `exigences.json` et de `options.json` validés (skills
`requirements-catalog` et `architecture-options`), dans le même dossier.
L'option chiffrée est la décision de `options.json`, sinon sa
recommandation ; `option` en force une autre (le script avertit si elle
diffère de la décision). Lisez le rapport d'`options_build.py` ou
`options.md` une fois : composants, flux, écarts, hypothèses de coût du
critère `cout`.

## 2. Décrire le chiffrage

Commencez par le brouillon, sans recopier l'option :

```bash
uv run scripts/estimate_build.py chiffrage.json --draft [--option ID] [--infra couts.infra.json] [--lots decoupage.lots.json ...]
```

Il écrit `chiffrage.json` (jamais par-dessus un fichier existant) : lots par
composant et transverses, valeurs usuelles listées dans `_draft`, budget et
infrastructure, lots des experts avec `--lots`. Complétez l'`effort` de
chaque lot, `rates`, hypothèses et exclusions ; ne changez un lot ou une
valeur usuelle qu'avec une raison. Forme complète :
`uv run scripts/estimate_build.py --schema`. Options du brouillon, lots des
experts et exemple complet : `references/brouillon.md`.

Règles qui valent toujours :

- **Charge** : jours par profil, un nombre si elle est sûre, sinon
  `[mini, probable, maxi]` ; le script calcule espérance et P10-P90.
- **Pas de marge dans un lot** : pilotage (`overheads`) et provision
  (`contingency`) s'ajoutent une fois ; le réemploi se déclare (`reuse`).
- **Aucun tarif cherché en ligne** : chaque ligne d'infrastructure a sa
  `basis` (grille datée, devis ou hypothèse à faire valider).
- **Sans IA** : la charge saisie est celle d'une équipe sans IA ; le
  script recalcule avec IA et en dev IA natif, et estime le coût IA du
  développement (`references/jetons-ia.json`).

Détail de chaque champ (phases, complexité, hébergeur, run, budget,
facteurs IA, coût IA, réemploi, parcours) : `references/champs.md`, à lire
seulement si un champ pose question.

## 3. Construire

```bash
uv run scripts/estimate_build.py chiffrage.json
```

Dans un workflow avec un vault Obsidian, ajoutez `--vault VAULT --folder
DOSSIER` : une note `chiffrage` (évalue l'option) et une note `lot` par lot
(porte sur ses exigences) rejoignent la mémoire partagée.

Produit `chiffrage.md` (revue), `chiffrage.csv`,
`chiffrage.hypotheses.csv`, le plan de charge sans montant
`chiffrage.charges.md` et `.csv`, `chiffrage.ia.json` et, avec `journeys`,
`chiffrage.parcours.json`. Sans `rates`, seul le plan de charge est
produit. Corrigez jusqu'à zéro erreur, puis traitez chaque avertissement et
chaque point à challenger (`challenge`) : corriger, ou justifier dans
`assumptions`. Livrez les chiffres du rapport, sans relire les fichiers.

Que faire de chaque avertissement (postes attendus, missions analogues,
points à challenger et leurs seuils) et vue par parcours pour la
restitution (`journeys_view.py`) : `references/controles.md`, à lire
quand le rapport en signale.

Si le coût obtenu contredit la note du critère `cout` d'une option dans
`options.json`, signalez-le : la note se revoit avec `architecture-options`.
