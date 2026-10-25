---
name: data-protection
description: "Prépare la conformité RGPD d'une solution : fiches du registre des traitements (article 30) et analyse d'impact relative à la protection des données (AIPD, article 35), avec nécessité de l'AIPD selon les critères du CEPD, transferts hors UE, hébergeur extraterritorial, risques pour les personnes notés en gravité et vraisemblance, mesures liées aux exigences et aux menaces STRIDE. Les contrôles et la carte des risques sont faits par script. À utiliser pour une analyse RGPD, une AIPD (DPIA), un registre des traitements ou un dossier d'homologation."
---

# data-protection

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décrivez les traitements et jugez les risques ; le script contrôle,
calcule les niveaux et met en forme. Ce skill prépare l'analyse : elle se
valide avec le délégué à la protection des données.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON des traitements de données personnelles et des risques pour les personnes (dpia_build.py --schema) ; Facultatif : exigences.json (requirements-catalog) et le .threats.md (threat-model), cités par les mesures ; l'hébergeur (shared/providers.json).
- **Sorties** : <nom>.registre.md : fiches du registre des traitements (art. 30) ; <nom>.aipd.md : analyse d'impact (critères, risques, carte gravité × vraisemblance, mesures, résiduels, points à valider).
- **`dpia_build.py`** : Contrôle la description des traitements et des risques (nécessité de l'AIPD selon les critères du CEPD, base légale, données sensibles, durée de conservation, transferts hors EEE sans garantie, hébergeur extraterritorial, événements redoutés couverts, résiduel jamais supérieur à l'initial, résiduel élevé qui appelle la consultation de la CNIL, références vers les exigences et les menaces), calcule les niveaux et la carte des risques, écrit le registre et l'AIPD. Rapport JSON, codes de sortie : 0 registre et AIPD écrits (avertissements possibles : critères, résiduels élevés, événements non couverts) ; 1 description invalide, traitement ou référence inconnus, transfert hors EEE sans garantie, conservation manquante, résiduel supérieur à l'initial ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Vault Obsidian** : écrit les notes de type `traitement`, `risque` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `threat-model` : les menaces STRIDE de l'architecture ne sont pas encore analysées : elles nourrissent les risques et les mesures.
- **Passe la main** au skill `decision-log` : noter au journal un risque accepté et sa raison, soumettre l'AIPD à la revue.
- **Passe la main** à l'agent `document-publisher` : le registre ou l'AIPD doivent être livrés en Word ou PDF.
- **Passe la main** à l'utilisateur : faire valider l'analyse par le délégué à la protection des données et décider d'un risque résiduel élevé.

## 1. Décrire

Fichier `aipd.json` (`uv run scripts/dpia_build.py --schema` donne sa
forme), dans le dossier du projet :

```json
{
  "title": "Portail de déclaration des sinistres",
  "controller": "Mutuelle exemple",
  "requirements": "exigences.json",
  "threats": "schemas/option-a.threats.md",
  "hosting": {"provider": "outscale"},
  "criteria": ["donnees-sensibles", "grande-echelle"],
  "treatments": [
    {"id": "T-01", "name": "Déclaration des sinistres", "purpose": "Recevoir et instruire les déclarations",
     "legal_basis": "contrat", "subjects": ["assurés"], "retention": "durée du contrat + 5 ans",
     "data": [{"category": "identité et contrat"}, {"category": "santé (dommages corporels)", "sensitive": true}],
     "art9_exception": "constatation, exercice ou défense d'un droit en justice (art. 9.2.f)",
     "recipients": ["gestionnaires sinistres", "experts mandatés"], "flows": ["F1", "F4"], "refs": ["EF-001"]}
  ],
  "risks": [
    {"id": "R-01", "treatment": "T-01", "event": "acces-illegitime", "sources": ["attaquant externe"],
     "impacts": "divulgation de données de santé", "gravity": 4, "likelihood": 2,
     "measures": [{"text": "authentification forte des gestionnaires", "refs": ["ENF-003", "M063"]}],
     "residual": {"gravity": 4, "likelihood": 1}}
  ]
}
```

- **Critères** (`criteria`) : ceux du CEPD que le traitement remplit ; deux
  au moins rendent l'AIPD obligatoire.
- **Traitements** : une finalité par traitement, base légale de
  l'article 6, exception de l'article 9.2 pour des données sensibles, durée
  de conservation, destinataires, transferts (`country` et `mechanism` hors
  EEE). `flows` reprend les numéros de flux du schéma cloud.
- **Risques** : au moins un par événement redouté (accès illégitime,
  modification non désirée, disparition) et par traitement ; gravité et
  vraisemblance de 1 à 4 ; mesures existantes ou prévues avec leurs `refs`
  (exigences, menaces `M001` du modèle STRIDE) ; risque résiduel après
  mesures. C'est là que porte votre jugement.
- **Hébergeur** : `hosting.provider` du catalogue commun ; un hébergeur
  hors UE est signalé pour qu'un risque d'accès illégitime le couvre.

## 2. Construire

```bash
uv run scripts/dpia_build.py aipd.json
```

Dans un workflow avec un vault Obsidian, ajoutez `--vault VAULT --folder
DOSSIER` : une note `traitement` par traitement (liée aux exigences) et une
note `risque` par risque (liée à son traitement) rejoignent la mémoire
partagée.

Produit `aipd.registre.md` et `aipd.aipd.md`. Corrigez jusqu'à zéro erreur
(transfert sans garantie, conservation manquante, résiduel supérieur à
l'initial, référence inconnue), puis traitez les avertissements :
événement redouté non couvert, données sensibles sans exception, résiduel
élevé (mesures à renforcer, sinon consultation préalable de la CNIL).
Livrez les compteurs du rapport, sans relire les fichiers.

## 3. Relire avec l'utilisateur

Un risque accepté se note au journal du workflow (skill `decision-log`)
avec sa raison. L'analyse se termine par l'avis du délégué à la protection
des données, que le script ne remplace pas.
