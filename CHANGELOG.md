# Journal des versions

## À venir

- `architecture-options` : position de chaque option dans le POS du SI
  (`pos`, `placement`) : noms vérifiés dans le POS, impacts (créations,
  évolutions, remplacements, redondances, flux entre zones), critère
  « urbanisation », section dans `options.md` et l'ADR, POS cible par option
  (`schemas/pos-option-<id>.json` pour `pos_build.py`).
- `architecture-workflow` : demande le POS du SI avec le vault, construit
  le POS cible de chaque option à l'étape `schemas` ; note d'option du vault
  avec sa position.
- `options_build.py` : rapport conforme au contrat aussi après une erreur
  de référence (`trace` à null).

## 0.2.0 (2026-10-23)

Revue complète après la 0.1 : fiabilité, contrôle des workflows multi-agents,
tests sur trois systèmes et nouvelles fonctionnalités.

### Corrections

- `convert.py` : deux documents de même nom (`rapport.pdf`, `rapport.png`)
  ne s'écrasent plus ; un dossier passé en entrée est parcouru.
- Rapports JSON de forme unique (`results`, `errors`, `warnings`) pour les
  scripts qui traitent plusieurs fichiers ; `errors` et `warnings` toujours
  présents.
- `check_drawio.py` lit la charte depuis `shared/references/style.md`.
- Kiro : chemin des skills correct pour une installation globale.
- `export.py` signale une image vide ou presque blanche.

### Contrôle multi-agents

- `journal.py handoff|report` valide les messages de passage et les
  rapports finals des agents (schéma, fichiers cités) et les trace.
- Revue différentielle : à une nouvelle soumission, `changes` liste les
  exigences, options et fichiers changés.
- Revue dans Obsidian : note de revue par étape, `review --from-vault`.
- `vault_sync.py` valide chaque fichier lu contre le schéma du skill qui
  l'écrit et n'écrit que les notes changées.

### Nouveautés

- Matrice de traçabilité exigences → composants (`tracabilite.md`, `.csv`)
  et description cloud des options qui ont un fournisseur.
- `iac_import.py` : description de schéma cloud depuis Terraform (AWS,
  Azure, Google), docker-compose et Kubernetes.
- Workflows décrits en JSON (`journal.py init --definition`) : `architecture`
  et `cloud-existant` livrés.
- Glossaire du projet relié aux exigences, une note Obsidian par terme.
- Mode hors ligne : `doctor.py --prefetch`, Mermaid et Excalidraw à version
  fixée et empreinte SHA-512 vérifiée, `MYSKILLS_OFFLINE=1`.

### Tests

- CI GitHub Actions sous Ubuntu, macOS et Windows.
- `tests/cost.py --max-increase` signale une hausse de coût ; nouveaux cas
  d'agent (retour, reprise, cloud-existant).

## 0.1.0 (2026-10-22)

Première version.
