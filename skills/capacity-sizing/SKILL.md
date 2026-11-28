---
name: capacity-sizing
description: "Dimensionnement d'une solution à partir des volumes et des exigences non fonctionnelles : débit moyen et de pointe, vCPU, mémoire et instances par composant avec la redondance qu'impose la disponibilité, stockage des données et des fichiers à l'horizon avec croissance et rétention, sauvegardes, trafic sortant, journaux, chaque calcul avec sa formule. Écrit aussi les consommations au format de cloud-cost pour chiffrer le run. À utiliser pour une volumétrie, un capacity planning, un dimensionnement d'infrastructure ou avant un coût de fonctionnement."
---

# capacity-sizing

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous posez
les hypothèses ; le script calcule, montre ses formules et prépare le
chiffrage du run.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Les exigences de volumétrie, de performance et de disponibilité (exigences.json) et l'option d'architecture retenue (options.json) ; Description JSON des hypothèses (size_build.py --schema) : utilisateurs, requêtes, pic, données, fichiers, croissance, disponibilité, composants.
- **Sorties** : <nom>.md : hypothèses et chaque calcul avec sa formule (débits, instances, vCPU, mémoire, stockage, réseau, sauvegardes) ; <nom>.result.json : résultats chiffrés par composant ; Avec --provider et --option : <nom>.couts.json, consommations au format de cloud-cost (cost_build.py).
- **`size_build.py`** : Calcule débits moyen et de pointe, vCPU, mémoire et instances par composant avec la redondance qu'impose la disponibilité, stockage des données et fichiers à l'horizon, sauvegardes, trafic sortant et journaux ; signale capacités par défaut, pic faible, zone unique pour une haute disponibilité ; écrit les calculs et, avec --provider, la description cloud-cost contrôlée contre son schéma. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `cloud-cost` (`cost_build.py`, facultatif : sans lui, avertissement) : contrôler la description des consommations écrite pour cloud-cost.
- **Passe la main** au skill `cloud-cost` : chiffrer le coût de fonctionnement : cost_build.py <nom>.couts.json.
- **Passe la main** au skill `well-architected-review` : vérifier la fiabilité et la performance de l'option au regard du dimensionnement.
- **Passe la main** à l'utilisateur : les volumes ou le facteur de pic ne sont pas connus : la question à poser, ou l'hypothèse à faire valider.

## 1. Décrire les hypothèses

Tirez-les des exigences (volumétrie, performance, disponibilité) et
notez chacune de celles que vous posez dans `assumptions`. Fichier
`dimensionnement.json` (`uv run scripts/size_build.py --schema`) :

```json
{
  "title": "Dimensionnement du portail sinistres", "refs": ["PERF-01", "DISP-01"],
  "users": {"total": 200000, "active_share": 0.02},
  "load": {"requests_per_user_hour": 30, "peak_factor": 10},
  "data": [{"name": "déclarations", "records": 500000, "record_kb": 4, "growth_per_year": 15}],
  "files": [{"name": "photos", "count_per_month": 40000, "size_mb": 2, "retention_years": 5}],
  "availability": {"target": 99.9, "zones": 2},
  "components": [{"id": "api", "kind": "api", "rps_per_vcpu": 80}, {"id": "base", "kind": "db"}],
  "assumptions": ["2 % des assurés connectés en heure ouvrée"]
}
```

- **Capacité par vCPU** (`rps_per_vcpu`) : une mesure ou une référence ;
  sans elle, la valeur par défaut est signalée.
- **Pic** : `peak_factor` tiré d'une exigence (tempête, échéance) ; sous 2,
  il est à justifier.

## 2. Construire

```bash
uv run scripts/size_build.py dimensionnement.json --provider aws --option A
```

Le rapport donne la pointe, les instances, les vCPU et le stockage ;
`--provider` écrit `dimensionnement.couts.json` pour `cloud-cost`.

## 3. Livrer

`dimensionnement.md` (calculs et formules) et, pour le coût de run,
`cost_build.py dimensionnement.couts.json` (skill `cloud-cost`).
