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
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Options d'architecture (options.json d'architecture-options), avec la décision ou la recommandation ; Description JSON du chiffrage : title, context, requirements, architecture, option, currency, horizon, hosting (provider, qualifications, refs), providers, rates (facultatif), hours_per_day, work (id, name, phase, component, refs, effort, complexity, ai), overheads, contingency, infra (id, name, component, environment, kind, provider, quantity, unit_cost, period, basis), run, scenarios (avec-ia, ia-natif : factors, gain_uncertainty, setup_percent, tooling_per_day, run_factor, contingency, basis), budget, assumptions, exclusions ; Catalogue des hébergeurs (shared/providers.json, commun aux skills cloud : AWS, Azure, Google Cloud, OVHcloud, Cloud Temple, Outscale, S3NS, Bleu, NumSpot, Scaleway, interne ; juridiction, qualifications SecNumCloud, HDS), complété par un catalogue propre au projet ; Hypothèses de production par défaut (references/hypotheses-ia.json : facteurs par phase, incertitude, adoption, outillage IA, run, avec leurs sources), lues par le script ; Règles de complétude (postes attendus) : references/postes-attendus.json, complétées par celles de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json) et de la mission (references.regles de mission.json), schéma shared/schemas/rules.schema.json ; Pour la calibration : missions passées comparables désignées dans mission.json (analogues), lues seulement, mission par mission ; Abaques donnés avant le lancement (shared/schemas/abaques.schema.json) : ~/.myskills/abaques.json ou MYSKILLS_ABAQUES, references.abaques de mission.json, --abaques ; section challenge pour les seuils des points à challenger ; sans eux, seuils par défaut à calibrer.
- **Sorties** : <nom>.md : chiffrage pour la revue (synthèse, budget, hypothèses sans IA, avec IA et IA natif, lots, phases, profils, infrastructure, run, coût total par année, points à challenger et réemploi, couverture, hypothèses, exclusions) ; <nom>.csv : lignes détaillées (lots, pilotage, infrastructure, run), séparateur point-virgule, relu par le script ; <nom>.hypotheses.csv : lignes de chaque hypothèse de production (sans IA, avec IA, IA natif : lots avec leur facteur, adoption, pilotage, outillage IA, run), relu par le script ; <nom>.charges.md et <nom>.charges.csv : plan de charge sans montant (chaque tâche avec sa complexité, ses jours et ses heures, sans IA, avec IA et IA natif ; par phase et par profil), relu par le script ; seuls produits sans rates.
- **`estimate_build.py`** : Vérifie les profils, les composants de l'option chiffrée (options.json, architecture-options) et les exigences (exigences.json, requirements-catalog), contrôle l'hébergeur de chaque ligne d'infrastructure contre le catalogue des hébergeurs et les qualifications exigées (SecNumCloud, HDS...), calcule la charge espérée de chaque lot (estimation à trois points), la fourchette P10-P90 de la réalisation, le pilotage, la provision, l'infrastructure par an et ponctuelle, le run et le coût total sur l'horizon, puis les mêmes montants pour trois hypothèses de production (sans IA, avec IA, dev IA natif : facteur de charge par phase ou par lot, incertitude élargie, adoption, licences et jetons, run) ; signale les exigences qu'aucun lot ne porte, les composants sans chiffrage, les postes attendus absents (règles de complétude selon les exigences et les composants : tests de sécurité et de charge, hors production, réseau, recette, mise en production, formation, sauvegarde, supervision, intégration, reprise de données), les estimations très incertaines et les dépassements de budget ; écrit le chiffrage, son CSV et celui des hypothèses, ainsi que le plan de charge sans montant (tâche, complexité, jours, heures) ; sans taux journaliers, ce plan de charge seul, puis relit les CSV pour vérifier les totaux ; dans une mission qui désigne des missions passées (analogues), compare les parts de charge par phase à leurs fourchettes (écarts en avertissements, rien de leur contenu recopié) ; avec --draft, écrit le brouillon de la description (lots par composant et transverses, valeurs usuelles, budget, infrastructure de cloud-cost, lots des experts frontend et backend, --lots) pour que le modèle n'écrive que les charges ; applique le réemploi déclaré par lot (reuse : part épargnée, base) et donne le taux de réemploi ; relève les points à challenger (marges cumulées, part de la réalisation, lots trop gros, lots semblables sans réemploi, jours par exigence) avec les seuils des abaques donnés avant le lancement, sinon des seuils par défaut à calibrer. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json contre son schéma.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `markdown-to-obsidian` (`lib/vault_ontology.py`, obligatoire) : ontologie du vault Obsidian (source unique) : construire et vérifier les notes écrites.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Dépend de** `cloud-architecture` (`lib/providers.json`, obligatoire) : catalogue commun des hébergeurs.
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
uv run scripts/estimate_build.py chiffrage.json --draft [--option ID] [--infra couts.infra.json] [--lots decoupage.lots.json --lots decoupage-back.lots.json]
```

Il écrit `chiffrage.json` (jamais par-dessus un fichier existant) : un lot
par composant à construire ou à intégrer, les lots transverses (cadrage,
recette, tests de sécurité, mise en production, formation), pilotage,
provision et run aux valeurs usuelles (listées dans `_draft`), budget tiré
des exigences de coût, lignes d'infrastructure de `cost_build.py --infra`,
et, avec `--lots` (répétable, alias `--frontend`), les lots des experts à
la place du lot global de chaque composant qu'ils couvrent : frontend
(`ui_breakdown.py`, skill `mockup-to-html` : composants, motifs, écrans) et
backend (`api_breakdown.py`, skill `api-contract`), charges d'abaque et
réemploi à relire.
Complétez-le : `effort` de chaque lot (vide), `rates`, hypothèses et
exclusions ; ajoutez, découpez ou retirez un lot, et revoyez les valeurs
usuelles, seulement quand vous avez une raison. La forme complète
(`uv run scripts/estimate_build.py --schema`) :

```json
{
  "title": "Chiffrage du portail de sinistres",
  "rates": {"chef-de-projet": 850, "architecte": 950, "developpeur": 650},
  "work": [
    {"id": "L1", "name": "API des déclarations", "phase": "realisation", "component": "api",
     "refs": ["EF-001", "EF-002"], "effort": {"developpeur": [25, 35, 55], "architecte": 3}}
  ],
  "overheads": [{"id": "P1", "name": "Pilotage", "percent": 12, "profile": "chef-de-projet"}],
  "contingency": 10,
  "infra": [
    {"id": "I1", "name": "Conteneurs managés, 2 zones", "component": "api", "environment": "production",
     "kind": "cloud", "quantity": 4, "unit_cost": 70, "period": "mois",
     "basis": "hypothèse : 4 tâches 1 vCPU 2 Go, grille publique 2026"}
  ],
  "run": [{"id": "R1", "name": "Maintenance corrective et évolutive", "percent_of_build": 15}],
  "budget": {"monthly": 8000, "refs": ["ENF-005"]},
  "assumptions": ["L'outil de gestion expose une API de création de dossier."]
}
```

Règles qui valent toujours :

- **Charge** : jours par profil, un nombre si elle est sûre, sinon
  `[mini, probable, maxi]` ; le script calcule espérance et P10-P90.
- **Pas de marge dans un lot** : pilotage (`overheads`) et provision
  (`contingency`) s'ajoutent une fois ; le réemploi se déclare (`reuse`).
- **Aucun tarif cherché en ligne** : chaque ligne d'infrastructure a sa
  `basis` (grille datée, devis ou hypothèse à faire valider).
- **Sans IA** : la charge saisie est celle d'une équipe sans IA ; le
  script recalcule avec IA et en dev IA natif.

Détail de chaque champ (phases, complexité, hébergeur, run, budget,
facteurs IA, réemploi, hypothèses) : `references/champs.md`, à lire
seulement si un champ pose question.

## 3. Construire

```bash
uv run scripts/estimate_build.py chiffrage.json
```

Dans un workflow avec un vault Obsidian, ajoutez `--vault VAULT --folder
DOSSIER` : une note `chiffrage` (évalue l'option) et une note `lot` par lot
(porte sur ses exigences) rejoignent la mémoire partagée.

Produit `chiffrage.md` (revue, avec la comparaison des trois hypothèses),
`chiffrage.csv` (lignes détaillées, ouvrable dans un tableur) et
`chiffrage.hypotheses.csv` (lignes de chaque hypothèse), plus le plan de
charge sans montant `chiffrage.charges.md` et `chiffrage.charges.csv`
(chaque tâche avec sa complexité, ses jours et ses heures dans les trois
hypothèses ; par phase et par profil). Sans `rates`, seul ce plan de
charge est produit. Corrigez jusqu'à zéro erreur, puis traitez les
avertissements : exigence qu'aucun lot ne porte (ajouter un lot ou des
`refs`, ou l'exclure avec sa raison), composant sans chiffrage, estimation
incertaine, poste attendu absent (`missing` : tests de sécurité, de
charge, hors production, réseau, recette, mise en production, formation,
sauvegarde, supervision, intégration, reprise de données, selon les
exigences et les composants : lot, ligne, hypothèse ou exclusion), budget
dépassé, valeurs d'hypothèse sans base. Livrez les chiffres du rapport, sans relire
les fichiers.

Les postes attendus sont des règles de complétude
(`references/postes-attendus.json`), complétées par celles de
l'utilisateur et de la mission (`references.regles` de mission.json) :
un oubli relevé en revue devient une règle (`lessons.py`, decision-log).

Dans une mission dont `mission.json` désigne des missions passées
comparables (`analogues`), le rapport compare la part de chaque phase à
leur fourchette (`analogy`) : une phase hors fourchette ou absente est un
avertissement à justifier ou à corriger. Seuls les noms des missions
sortent ; rien de leur contenu n'est recopié.

**Points à challenger** (`challenge` du rapport, section du chiffrage) :
marges cumulées (pilotage, provision, asymétrie des trois points), part de
la réalisation et de l'intégration, lots trop gros, lots semblables sans
réemploi, jours de lots par exigence. Les seuils viennent des abaques donnés
avant le lancement (section `challenge` de `~/.myskills/abaques.json` ou
`MYSKILLS_ABAQUES`, de `references.abaques` de mission.json, puis
`--abaques`), sinon de valeurs par défaut à calibrer (`calibrated: false`).
Chaque point se justifie (dans `assumptions`) ou se corrige.

Si le coût obtenu contredit la note du critère `cout` d'une option dans
`options.json`, signalez-le : la note se revoit avec `architecture-options`.
