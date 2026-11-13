---
name: operations-dossier
description: "Écrit et contrôle le dossier d'exploitation d'une solution (DEX, runbook) : services et engagements (disponibilité cible, RPO, RTO, indisponibilité permise calculée), supervision et alertes, sauvegardes et tests de restauration, astreinte et escalade, fiches réflexes d'incident, opérations récurrentes, avec les trous de couverture relevés par des règles (service critique sans alerte ni fiche, sauvegarde incompatible avec le RPO, exigence de disponibilité non tenue). À utiliser pour préparer la mise en production ou le passage en exploitation, répondre au volet exploitabilité d'un appel d'offres, ou revoir l'exploitabilité d'une architecture."
---

# operations-dossier

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décrivez l'exploitation ; le script contrôle, calcule et écrit le dossier.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : L'architecture retenue (options.json, description cloud ou dossier d'architecture) et le catalogue d'exigences (exigences.json), pour les services et leurs engagements ; Description JSON de l'exploitation (ops_build.py --schema) : services et engagements (disponibilité, RPO, RTO), alertes, sauvegardes, astreinte, fiches réflexes, opérations récurrentes.
- **Sorties** : <nom>.md : dossier d'exploitation (services et engagements avec indisponibilité permise, supervision et alertes, sauvegardes et restauration, astreinte et escalade, fiches réflexes, opérations récurrentes, points ouverts).
- **`ops_build.py`** : Contrôle la description de l'exploitation (références, sauvegardes confrontées au RPO), calcule l'indisponibilité permise par la disponibilité cible de chaque service, relève les trous de couverture (règles OPS-01 à OPS-10 : service critique sans engagement, sans alerte ou sans fiche, restauration jamais testée, astreinte insuffisante, exigence portée par aucun service) et écrit le dossier d'exploitation en Markdown. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Passe la main** au skill `requirements-catalog` : une exigence de disponibilité ou d'exploitation manque ou n'a pas de mesure : la compléter dans le catalogue.
- **Passe la main** au skill `capacity-sizing` : les seuils d'alerte dépendent de la charge attendue : la dimensionner d'abord.
- **Passe la main** au skill `architecture-dossier` : joindre le dossier d'exploitation au dossier d'architecture technique.
- **Passe la main** à l'utilisateur : un engagement (disponibilité, RPO, RTO, astreinte) n'est ni dans les exigences ni dans les documents : la question à poser, jamais une valeur inventée.

## 1. Partir de l'architecture et des exigences

Les services viennent de l'architecture retenue (composants d'`options.json`,
description cloud, dossier d'architecture) ; les engagements viennent du
catalogue d'exigences (disponibilité, RPO, RTO, exploitabilité) ou des
documents. Un engagement absent des sources ne s'invente pas : posez la
question à l'utilisateur, une seule fois, ou laissez le champ vide : le
script le relève.

## 2. Décrire l'exploitation

Fichier `<nom>.json` (`ops_build.py --schema` en donne la forme) :

```json
{
  "title": "Dossier d'exploitation : portail de sinistres",
  "requirements": "exigences.json",
  "services": [
    {"id": "portail", "name": "Portail assurés", "criticality": "critique",
     "slo": {"availability": 99.5}, "rto_hours": 4, "refs": ["ENF-002"]},
    {"id": "base", "name": "Base des déclarations", "criticality": "critique",
     "slo": {"availability": 99.9}, "rpo_hours": 1, "rto_hours": 2}
  ],
  "monitoring": [
    {"id": "A-1", "service": "portail", "signal": "taux d'erreurs 5xx",
     "threshold": "> 2 % pendant 5 min", "severity": "critique", "notify": "N1", "runbook": "RB-1"}
  ],
  "backups": [
    {"service": "base", "what": "déclarations", "frequency_hours": 1,
     "retention_days": 35, "offsite": true, "restore_test": "trimestriel"}
  ],
  "oncall": {"hours": "24/7", "levels": [{"level": "N1", "who": "Équipe plateforme", "delay_minutes": 15}]},
  "runbooks": [
    {"id": "RB-1", "title": "Portail en erreur", "service": "portail",
     "symptoms": ["Page d'erreur pour les assurés"],
     "diagnosis": ["Regarder les erreurs par route"],
     "actions": ["Revenir à la version précédente"], "escalation": "N1"}
  ]
}
```

- Une alerte mesure un symptôme vu par l'utilisateur (erreurs, lenteur,
  file qui grossit), avec un seuil et une durée ; pas une cause interne.
- Une fiche réflexe se lit à 3 heures du matin : des actions dans l'ordre,
  chacune vérifiable, puis le retour arrière et qui prévenir.
- `refs` relie un service aux exigences qu'il tient ; avec `requirements`,
  une exigence de disponibilité ou d'exploitabilité portée par aucun
  service est relevée.

## 3. Construire

```bash
uv run scripts/ops_build.py <nom>.json
```

Une référence inconnue ou une sauvegarde moins fréquente que le RPO est
une erreur : corrigez d'après `errors` (le nom proche est proposé), rien
n'est écrit. Sinon le script écrit `<nom>.md` et rend les trous de
couverture dans `findings` (règles OPS-01 à OPS-10, gravité haute d'abord),
repris dans la section « Points ouverts » du dossier avec leur correction.

Lisez le rapport, pas le dossier. Pour chaque constat : corrigez la
description si la source donne la réponse ; sinon présentez-le à
l'utilisateur, qui tranche. Ne supprimez pas un service ou une alerte pour
faire disparaître un constat. `--strict` donne le code 1 tant qu'il reste
un constat de gravité haute (pour un contrôle avant mise en production).

## 4. Livrer

`<nom>.md`, à joindre au dossier d'architecture ou à publier (skill
`markdown-publish`). Donnez les compteurs du rapport (`counts`) et les
constats de gravité haute restants.
