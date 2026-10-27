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
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Options d'architecture (options.json d'architecture-options), avec la décision ou la recommandation ; Description JSON du chiffrage : title, context, requirements, architecture, option, currency, horizon, hosting (provider, qualifications, refs), providers, rates (facultatif), hours_per_day, work (id, name, phase, component, refs, effort, complexity, ai), overheads, contingency, infra (id, name, component, environment, kind, provider, quantity, unit_cost, period, basis), run, scenarios (avec-ia, ia-natif : factors, gain_uncertainty, setup_percent, tooling_per_day, run_factor, contingency, basis), budget, assumptions, exclusions ; Catalogue des hébergeurs (shared/providers.json, commun aux skills cloud : AWS, Azure, Google Cloud, OVHcloud, Cloud Temple, Outscale, S3NS, Bleu, NumSpot, Scaleway, interne ; juridiction, qualifications SecNumCloud, HDS), complété par un catalogue propre au projet ; Hypothèses de production par défaut (references/hypotheses-ia.json : facteurs par phase, incertitude, adoption, outillage IA, run, avec leurs sources), lues par le script.
- **Sorties** : <nom>.md : chiffrage pour la revue (synthèse, budget, hypothèses sans IA, avec IA et IA natif, lots, phases, profils, infrastructure, run, coût total par année, couverture, hypothèses, exclusions) ; <nom>.csv : lignes détaillées (lots, pilotage, infrastructure, run), séparateur point-virgule, relu par le script ; <nom>.hypotheses.csv : lignes de chaque hypothèse de production (sans IA, avec IA, IA natif : lots avec leur facteur, adoption, pilotage, outillage IA, run), relu par le script ; <nom>.charges.md et <nom>.charges.csv : plan de charge sans montant (chaque tâche avec sa complexité, ses jours et ses heures, sans IA, avec IA et IA natif ; par phase et par profil), relu par le script ; seuls produits sans rates.
- **`estimate_build.py`** : Vérifie les profils, les composants de l'option chiffrée (options.json, architecture-options) et les exigences (exigences.json, requirements-catalog), contrôle l'hébergeur de chaque ligne d'infrastructure contre le catalogue des hébergeurs et les qualifications exigées (SecNumCloud, HDS...), calcule la charge espérée de chaque lot (estimation à trois points), la fourchette P10-P90 de la réalisation, le pilotage, la provision, l'infrastructure par an et ponctuelle, le run et le coût total sur l'horizon, puis les mêmes montants pour trois hypothèses de production (sans IA, avec IA, dev IA natif : facteur de charge par phase ou par lot, incertitude élargie, adoption, licences et jetons, run) ; signale les exigences qu'aucun lot ne porte, les composants sans chiffrage, les postes souvent oubliés (tests de sécurité, hors production, réseau, recette, mise en production, formation), les estimations très incertaines et les dépassements de budget ; écrit le chiffrage, son CSV et celui des hypothèses, ainsi que le plan de charge sans montant (tâche, complexité, jours, heures) ; sans taux journaliers, ce plan de charge seul, puis relit les CSV pour vérifier les totaux ; avec --draft, écrit le brouillon de la description (lots par composant et transverses, valeurs usuelles, budget, infrastructure de cloud-cost) pour que le modèle n'écrive que les charges. Rapport JSON, codes de sortie : 0 chiffrage produit et CSV vérifié (avertissements possibles) ; 1 description invalide, profil, composant ou exigence inconnu, estimation hors ordre, CSV qui ne redonne pas les totaux ; aucun fichier produit sauf dans ce dernier cas.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json contre son schéma.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Vault Obsidian** : écrit les notes de type `chiffrage`, `lot` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
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
uv run scripts/estimate_build.py chiffrage.json --draft [--option ID] [--infra couts.infra.json]
```

Il écrit `chiffrage.json` (jamais par-dessus un fichier existant) : un lot
par composant à construire ou à intégrer, les lots transverses (cadrage,
recette, tests de sécurité, mise en production, formation), pilotage,
provision et run aux valeurs usuelles (listées dans `_draft`), budget tiré
des exigences de coût, lignes d'infrastructure de `cost_build.py --infra`.
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

- **Lots** : un lot par composant de l'option à construire ou à modifier,
  plus les lots transverses (cadrage, tests, déploiement, reprise de
  données, conduite du changement) ; `phase` parmi cadrage, conception,
  realisation, integration, tests, deploiement, migration,
  conduite-changement, pilotage. `component` reprend l'identifiant du
  composant dans `options.json` ; `refs` ajoute les exigences que le lot
  porte en plus de celles du composant.
- **Taux** : `rates` est facultatif. Sans lui, seules les charges sont
  produites (jours et heures, sans montant) : la valorisation reste au
  chef de projet. `hours_per_day` (défaut 7) convertit les jours en heures.
- **Complexité** : `complexity` par lot (faible, moyenne, elevee,
  tres-elevee) quand elle tient à autre chose que la taille (technologie
  nouvelle, dépendance externe, sujet réglementé) ; sans elle, le script
  la déduit de la charge espérée et le signale.
- **Charge** : jours par profil, un nombre si la charge est sûre, sinon
  `[mini, probable, maxi]`. Le script calcule l'espérance (mini + 4
  probable + maxi) / 6 et la fourchette P10-P90 : ne les écrivez pas. Un
  lot dont l'écart mini-maxi dépasse le probable est signalé : découpez-le
  ou levez l'hypothèse.
- **Pilotage** : `overheads` en pourcentage de la charge des lots, au taux
  d'un profil. **Provision** : `contingency`, en % du coût de réalisation.
- **Infrastructure** : une ligne par poste (`kind` cloud, licence,
  materiel, service, autre ; `period` mois, an ou unique), avec `basis`
  obligatoire : grille tarifaire et sa date, devis, ou hypothèse de
  dimensionnement. Aucun tarif ne se cherche en ligne : un prix inconnu est
  une hypothèse à faire valider, notée comme telle.
- **Hébergeur** : `hosting` donne l'hébergeur par défaut et les
  qualifications exigées par les exigences, par exemple
  `{"provider": "cloud-temple", "qualifications": ["secnumcloud"], "refs": ["ENF-003"]}` ;
  une ligne peut en nommer un autre (`provider`). Sans `hosting`, c'est le
  `provider` de l'option. Les hébergeurs connus (aws, azure, gcp, ovh,
  cloud-temple, outscale, s3ns, bleu, numspot, scaleway, sur-site), leur
  juridiction et leurs qualifications (secnumcloud, hds) sont dans
  `shared/providers.json` (copié dans `scripts/lib/`) ; ne le chargez pas, le script le lit. Un
  hébergeur ou une qualification propre au projet s'ajoute dans un
  catalogue du dossier, de même forme, cité par `providers`. Le script
  signale chaque ligne cloud ou service dont l'hébergeur n'a pas une
  qualification exigée, rappelle de vérifier l'offre chez un hébergeur
  qualifié (la qualification porte sur une offre) et avertit si l'option
  est décrite chez un autre fournisseur.
- **Run** : par an, `days_per_year` avec `profile`, ou `percent_of_build`
  (part du coût de réalisation hors provision).
- **Budget** : plafonds `build`, `monthly` (infrastructure et run par
  mois), `tco`, avec les exigences qui les fixent (`refs`). Un dépassement
  est signalé.
- **Hypothèses de production** : la charge saisie est celle d'une équipe
  sans IA ; le script la recalcule toujours pour trois hypothèses, sans
  IA, avec IA (développement assisté) et dev IA natif (agents qui écrivent
  code et tests, l'équipe spécifie et valide). Pour chacune : facteur de
  charge par phase, incertitude sur le gain (commune à tous les lots, elle
  élargit la fourchette), adoption (outillage, garde-fous, formation, en %
  de la charge), licences et jetons par jour travaillé, facteur du run.
  Les valeurs par défaut et leurs sources sont dans
  `references/hypotheses-ia.json` (ne le chargez pas, le script le lit).
  Ne les changez que sur une base : mesure de l'équipe, lot pilote, offre
  d'un éditeur, par exemple
  `"scenarios": {"avec-ia": {"factors": {"realisation": 0.65}, "basis": "mesure de l'équipe, 2026"}}`.
  Un lot où l'IA aide peu ou beaucoup (code ancien, progiciel peu
  documenté, sujet réglementé) prend son propre facteur,
  `"ai": {"avec-ia": 0.95, "ia-natif": 0.9}`, avec la raison dans `note`.
- **Hypothèses et exclusions** : chacune en une phrase ; elles vont dans
  le chiffrage et, dans un workflow, au journal.

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
incertaine, poste souvent oublié (tests de sécurité, hors production,
réseau, recette, mise en production, formation : lot, ligne, hypothèse ou
exclusion), budget dépassé, valeurs d'hypothèse sans base. Livrez les chiffres du rapport, sans relire
les fichiers.

Si le coût obtenu contredit la note du critère `cout` d'une option dans
`options.json`, signalez-le : la note se revoit avec `architecture-options`.
