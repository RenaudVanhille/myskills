---
name: cloud-cost
description: "Estime et compare le coût de fonctionnement mensuel d'options d'architecture cloud (AWS, Azure, Google Cloud, OVHcloud, Scaleway, ou prix propres) : consommations par option (calcul, conteneurs, base de données, stockage, réseau, journaux), plages horaires, remise d'engagement, production et hors production, calculées par script sur une grille de prix locale. Signale les prix à vérifier, le hors production allumé en continu et les postes oubliés. À utiliser pour un coût de run, une estimation FinOps, comparer des options sur leur coût d'hébergement ou préparer les lignes d'infrastructure d'un chiffrage."
---

# cloud-cost

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
dimensionnez (quels services, combien, quand) ; le script prend les prix,
calcule et compare. Aucun tarif n'est consulté en ligne : la grille livrée
(`references/prix.json`) donne des ordres de grandeur pour comparer, à
vérifier avant tout engagement.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Les options d'architecture cloud à comparer (options.json d'architecture-options, ou leurs schémas cloud) et le dimensionnement connu : volumes, utilisateurs, données ; Description JSON des consommations par option (cost_build.py --schema) : service de la grille, quantité, environnement, plage horaire, prix propre et sa base, remise d'engagement ; Facultatif : une grille de prix propre (devis, grille vérifiée), de même forme que references/prix.json.
- **Sorties** : <nom>.md : comparaison des options (par mois, par an, sur l'horizon, production et hors production), coût par catégorie, détail des lignes avec la base de chaque prix ; <nom>.csv : une ligne par consommation (séparateur ;) ; Avec --infra : <nom>.infra.json, les lignes d'infrastructure du chiffrage de l'option (solution-estimate).
- **`cost_build.py`** : Vérifie hébergeurs et services de la grille, calcule chaque consommation (prix horaire et plage, ou prix mensuel), la remise d'engagement, le coût mensuel par catégorie et par environnement, annuel et sur l'horizon, classe les options ; signale les prix indicatifs à vérifier, le hors production allumé en continu avec l'économie d'un arrêt, les postes souvent oubliés (trafic sortant, sauvegardes, journaux) et le budget dépassé ; écrit la comparaison et le CSV, relit le CSV pour vérifier les totaux ; avec --infra, écrit les lignes d'infrastructure du chiffrage. Rapport JSON, codes de sortie : 0 comparaison écrite et CSV vérifié (avertissements possibles : prix indicatifs, postes oubliés, budget) ; 1 description invalide, hébergeur ou service inconnu, prix absent sans unit_cost, base manquante, grille illisible ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : vérifier les lignes d'infrastructure de --infra contre le schéma du chiffrage.
- **Passe la main** au skill `architecture-options` : le coût de fonctionnement change la note du critère cout d'une option.
- **Passe la main** au skill `solution-estimate` : chiffrer l'option retenue : ses lignes d'infrastructure viennent de --infra.
- **Passe la main** à l'utilisateur : valider le dimensionnement et faire vérifier les prix indicatifs avant tout engagement.

## 1. Décrire les consommations

Fichier `couts.json` (`uv run scripts/cost_build.py --schema` donne sa
forme sur une ligne) : `title`, `horizon_months` (défaut 36),
`budget_monthly` s'il y en a un, et une entrée par option :

```json
{"title": "Portail sinistres : coût de run",
 "budget_monthly": 4000,
 "options": [
  {"id": "A", "name": "Conteneurs managés", "provider": "aws",
   "discount": {"percent": 30, "basis": "engagement d'un an (Savings Plans)"},
   "items": [
    {"id": "api", "service": "conteneur.vcpu", "quantity": 4, "component": "api"},
    {"id": "api-ram", "service": "conteneur.ram", "quantity": 8},
    {"id": "recette", "service": "conteneur.vcpu", "quantity": 2, "environment": "hors-production", "schedule": "ouvre"},
    {"id": "bdd", "service": "bdd.vcpu", "quantity": 2},
    {"id": "sortant", "service": "reseau.sortant", "quantity": 500},
    {"id": "licence", "service": "journaux", "quantity": 20, "unit_cost": 0.3, "basis": "devis Datadog 2026-10"}]}]}
```

Services de la grille : `vm.vcpu`, `vm.ram`, `conteneur.vcpu`,
`conteneur.ram`, `kubernetes.plan-controle`, `fonction.appels` (millions
par mois), `bdd.vcpu`, `bdd.stockage`, `stockage.bloc`, `stockage.objet`,
`sauvegarde` (Go par mois), `reseau.sortant` (Go par mois),
`reseau.equilibreur`, `reseau.nat`, `reseau.ip`, `journaux` (Go ingérés
par mois). Un service à l'heure prend `schedule` : `continu` (730 h,
défaut), `ouvre` (264 h : 12 h par jour ouvré) ou un nombre d'heures. Un
hébergeur sans prix dans la grille (souverain, interne) demande
`unit_cost` et `basis` sur chaque ligne, comme un devis. Gardez les
identifiants d'options d'`architecture-options`.

## 2. Calculer et comparer

```bash
uv run scripts/cost_build.py couts.json [--infra A]
```

Le rapport donne pour chaque option le coût par mois, par an, sur
l'horizon, par catégorie, l'économie possible hors production, et
`cheapest`. Erreurs : hébergeur ou service inconnu (avec la valeur proche),
prix absent sans `unit_cost`, prix propre ou remise sans base. Traitez les
avertissements : prix indicatifs (à faire vérifier), hors production
allumé en continu (passer en `ouvre` ou dire pourquoi), postes oubliés
(trafic sortant, sauvegardes, journaux : ligne à ajouter ou absence à
justifier), budget dépassé (le dire, ne pas réduire le dimensionnement pour
le tenir). `couts.md` est pour l'utilisateur : ne le relisez pas.

Avec `--infra A`, `couts.infra.json` donne les lignes d'infrastructure de
l'option A au format du `chiffrage.json` de `solution-estimate` : une par
environnement et catégorie, au mois, avec leur base.

## 3. Ensuite

Un écart de coût net entre options peut changer la note du critère `cout`
dans `options.json` : signalez-le, la note se revoit avec
`architecture-options`. Le dimensionnement et les prix se valident avec
l'utilisateur.
