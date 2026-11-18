---
name: test-plan
description: "Plan de recette tiré du catalogue d'exigences : un cas de test par exigence (ébauche par script), types fonctionnel, intégration, bout en bout, performance, sécurité, accessibilité, reprise, exploitation, résultats attendus qui reprennent les mesures des exigences non fonctionnelles, matrice de couverture contrôlée par script, CSV importable dans Xray, TestRail ou Azure Test Plans, et lots de recette chiffrés sur abaques pour solution-estimate. À utiliser pour une stratégie ou un plan de recette, une matrice de couverture des exigences ou le chiffrage de la recette."
---

# test-plan

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
écrivez les cas qui demandent du jugement (étapes, données, résultat
attendu) ; le script fait l'ébauche, contrôle la couverture et chiffre.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Le catalogue d'exigences (exigences.json de requirements-catalog), avec mesures des exigences non fonctionnelles ; Description JSON du plan de recette (test_build.py --schema) : cas de test, exigences couvertes, type, priorité, étapes, résultat attendu ; ou son ébauche (--draft) ; Facultatif : abaques de recette propres (rules du plan).
- **Sorties** : <plan>.md : cas de test, matrice de couverture exigences × cas, exigences non couvertes, charge de recette ; <plan>.csv : un cas par ligne (séparateur ;), importable dans Xray, TestRail ou Azure Test Plans ; <plan>.lots.json : lots de recette à trois points (conception, exécution par campagne, automatisation) au format de solution-estimate.
- **`test_build.py`** : Écrit l'ébauche du plan depuis les exigences (--draft : un cas par exigence retenue, type tiré de la catégorie, résultat attendu tiré du texte et de la mesure) ; contrôle identifiants, exigences citées, couverture (exigence indispensable sans cas : erreur), mesure reprise dans le résultat attendu des exigences mesurées ; calcule la charge de recette sur abaques ; écrit le plan, le CSV relu et les lots contrôlés contre le schéma du chiffrage. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : contrôler les lots de recette contre le schéma des lots du chiffrage.
- **Passe la main** au skill `solution-estimate` : chiffrer la recette : estimate_build.py --draft --lots <plan>.lots.json.
- **Passe la main** au skill `requirements-catalog` : une exigence n'est pas testable telle qu'écrite (pas de mesure, ambiguë) : la reformuler dans le catalogue.
- **Passe la main** à l'utilisateur : le nombre de campagnes, les données de test ou l'outil de recette ne sont pas connus : la question à poser.

## 1. Partir de l'ébauche

```bash
uv run scripts/test_build.py plan.json --draft --requirements exigences.json
```

Un cas par exigence retenue, type tiré de la catégorie, résultat attendu
repris du texte et de la mesure (`metric`). Jamais par-dessus un plan
existant.

## 2. Compléter les cas

Forme complète : `uv run scripts/test_build.py --schema`.

- **Étapes** : remplacez « à décrire » par les actions de l'utilisateur ou
  du système, dans l'ordre ; **données** (`data`) si le cas en demande.
- **Résultat attendu** : vérifiable ; pour une exigence mesurée, il
  reprend sa mesure mot pour mot (sinon averti).
- **Découpage** : une exigence large se couvre par plusieurs cas, un
  parcours complet par un cas `bout-en-bout` qui cite plusieurs exigences.
- **Automatisation** : `"automated": true` pour les cas de non-régression.
- **Abaques** : `rules` (campagnes, jours par type) seulement si
  l'utilisateur en donne ; sinon les valeurs par défaut sont signalées.

## 3. Construire

```bash
uv run scripts/test_build.py plan.json
```

Zéro erreur exigée : une exigence indispensable sans cas est une erreur.
Les avertissements (mesure non reprise, exigence importante non couverte)
se corrigent ou se disent à l'utilisateur.

## 4. Livrer

`plan.md`, `plan.csv` (import dans l'outil de recette) et `plan.lots.json`,
que `estimate_build.py chiffrage.json --draft --lots plan.lots.json`
(skill `solution-estimate`) reprend.
