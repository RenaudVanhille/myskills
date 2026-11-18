---
name: migration-assessment
description: "Évalue un portefeuille d'applications pour une migration vers le cloud (ou un autre hébergement) selon les 6R : réhéberger, replateformer, refondre, racheter, retirer ou conserver, avec la raison, l'effort et le risque de chaque choix. Le script contrôle les dépendances, les retraits, l'obsolescence et l'hébergeur cible, puis calcule les vagues de migration. À utiliser pour une étude de migration, un plan de sortie d'un datacenter, une rationalisation du portefeuille applicatif ou un inventaire à trier en 6R."
---

# migration-assessment

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
choisissez la stratégie de chaque application et dites pourquoi ; le
script contrôle la cohérence du portefeuille et calcule les vagues.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON du portefeuille d'applications et de la stratégie 6R de chacune (assess_build.py --schema), tirée d'un inventaire (CSV, POS d'urbanization-map, documents) ; Facultatif : exigences.json (requirements-catalog), cité par les applications ; l'hébergeur cible (shared/providers.json).
- **Sorties** : <nom>.md : synthèse par stratégie, tableau des applications, vagues de migration, points d'attention ; <nom>.csv : une ligne par application (stratégie, effort, risque, vague) ; <nom>.waves.json : vagues de migration, reprises par transition-roadmap.
- **`assess_build.py`** : Contrôle l'évaluation 6R (dépendances connues et sans cycle, application retirée encore utilisée, refactor d'effort S, rehost d'une technologie hors support, repurchase sans cible, application critique à risque élevé sans parade, données sensibles chez un hébergeur extraterritorial, références vers les exigences) et calcule les vagues de migration selon les dépendances. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `cloud-architecture` (`lib/providers.json`, obligatoire) : catalogue commun des hébergeurs.
- **Passe la main** au skill `transition-roadmap` : planifier les vagues dans la feuille de route de transition (waves dans sa description).
- **Passe la main** au skill `cloud-architecture` : décrire et dessiner l'architecture cible des applications migrées.
- **Passe la main** au skill `data-protection` : des données sensibles partent chez un hébergeur soumis à des lois extraterritoriales.
- **Passe la main** au skill `solution-estimate` : chiffrer la migration à partir des efforts et des vagues.
- **Passe la main** à l'utilisateur : faire valider chaque retrait d'application et les stratégies des applications critiques.

## 1. Décrire

Fichier `migration.json` (`uv run scripts/assess_build.py --schema` donne
sa forme sur une ligne) : `title`, `target.provider` (hébergeur cible du
catalogue commun : aws, azure, gcp, ovh, outscale, s3ns...), `requirements`
(chemin de `exigences.json`, s'il existe) et une entrée par application.
Partez de l'inventaire fourni (CSV, POS d'`urbanization-map`, documents) ;
une information absente reste absente plutôt qu'inventée.

Repères pour la stratégie :

| Stratégie | Quand |
| --- | --- |
| `rehost` | socle supporté, peu de temps, pas de bénéfice attendu d'une refonte |
| `replatform` | gain rapide en passant à un service géré (base, conteneurs) sans toucher au code métier |
| `refactor` | application différenciante, besoins d'élasticité ou de résilience que l'existant ne tient pas ; effort L ou XL |
| `repurchase` | fonction standard couverte par un SaaS ou un progiciel (`target_service` obligatoire) |
| `retire` | usage faible ou fonction reprise ailleurs ; aucune application gardée n'en dépend |
| `retain` | contrainte forte (réglementaire, matériel, fin de vie proche) ; à réévaluer |

`why` tient en une phrase qui cite le fait décisif (fin de support,
usage, dépendance, exigence). Une application critique à risque élevé a
ses `mitigations`.

## 2. Contrôler et calculer

```bash
uv run scripts/assess_build.py migration.json [--max-per-wave 5]
```

Corrigez jusqu'à zéro erreur : dépendance inconnue ou en cycle,
application retirée dont une autre dépend, hébergeur ou exigence
inconnus. Lisez les avertissements (refactor d'effort S, rehost d'un socle
hors support, données sensibles chez un hébergeur extraterritorial) :
corrigez la description ou dites à l'utilisateur pourquoi le choix tient.

Le rapport donne les compteurs par stratégie et le nombre de vagues ; ne
relisez pas `migration.md`. Les vagues (`migration.waves.json`) se
planifient avec `transition-roadmap` ; des données sensibles chez un
hébergeur hors UE appellent `data-protection`.
