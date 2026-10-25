---
name: solution-estimate
description: "Chiffre une solution à partir du catalogue d'exigences et de l'option d'architecture retenue : charge de réalisation par lot, phase et profil (estimation à trois points, fourchette calculée), pilotage et provision, coût d'infrastructure, maintenance et exploitation, coût total sur plusieurs années, budget tenu ou dépassé. Les calculs et les contrôles de couverture sont faits par script. À utiliser pour chiffrer un projet, estimer une charge, un budget, un coût d'infrastructure ou un coût total de possession."
---

# solution-estimate

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
découpez la solution en lots et estimez chaque lot ; le script vérifie les
références, fait tous les calculs, met en forme et relit son CSV.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Options d'architecture (options.json d'architecture-options), avec la décision ou la recommandation ; Description JSON du chiffrage : title, context, requirements, architecture, option, currency, horizon, hosting (provider, qualifications, refs), providers, rates, work (id, name, phase, component, refs, effort), overheads, contingency, infra (id, name, component, environment, kind, provider, quantity, unit_cost, period, basis), run, budget, assumptions, exclusions ; Catalogue des hébergeurs (shared/providers.json, commun aux skills cloud : AWS, Azure, Google Cloud, OVHcloud, Cloud Temple, Outscale, S3NS, Bleu, NumSpot, Scaleway, interne ; juridiction, qualifications SecNumCloud, HDS), complété par un catalogue propre au projet.
- **Sorties** : <nom>.md : chiffrage pour la revue (synthèse, budget, lots, phases, profils, infrastructure, run, coût total par année, couverture, hypothèses, exclusions) ; <nom>.csv : lignes détaillées (lots, pilotage, infrastructure, run), séparateur point-virgule, relu par le script.
- **`estimate_build.py`** : Vérifie les profils, les composants de l'option chiffrée (options.json, architecture-options) et les exigences (exigences.json, requirements-catalog), contrôle l'hébergeur de chaque ligne d'infrastructure contre le catalogue des hébergeurs et les qualifications exigées (SecNumCloud, HDS...), calcule la charge espérée de chaque lot (estimation à trois points), la fourchette P10-P90 de la réalisation, le pilotage, la provision, l'infrastructure par an et ponctuelle, le run et le coût total sur l'horizon ; signale les exigences qu'aucun lot ne porte, les composants sans chiffrage, les estimations très incertaines et les dépassements de budget ; écrit le chiffrage et son CSV, puis relit le CSV pour vérifier les totaux. Rapport JSON, codes de sortie : 0 chiffrage produit et CSV vérifié (avertissements possibles) ; 1 description invalide, profil, composant ou exigence inconnu, estimation hors ordre, CSV qui ne redonne pas les totaux ; aucun fichier produit sauf dans ce dernier cas.
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

Fichier `chiffrage.json` (`uv run scripts/estimate_build.py --schema`
donne sa forme) :

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
- **Hypothèses et exclusions** : chacune en une phrase ; elles vont dans
  le chiffrage et, dans un workflow, au journal.

## 3. Construire

```bash
uv run scripts/estimate_build.py chiffrage.json
```

Produit `chiffrage.md` (revue) et `chiffrage.csv` (lignes détaillées,
ouvrable dans un tableur). Corrigez jusqu'à zéro erreur, puis traitez les
avertissements : exigence qu'aucun lot ne porte (ajouter un lot ou des
`refs`, ou l'exclure avec sa raison), composant sans chiffrage, estimation
incertaine, budget dépassé. Livrez les chiffres du rapport, sans relire
les fichiers.

Si le coût obtenu contredit la note du critère `cout` d'une option dans
`options.json`, signalez-le : la note se revoit avec `architecture-options`.
