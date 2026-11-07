# Moteur de workflow : cas particuliers

À lire seulement quand l'agent `architecture-workflow` le dit : plusieurs
étapes prêtes en même temps, retour sur une étape validée, mission.

## Étapes en parallèle

Quand `ready` liste plusieurs étapes (par exemple revue et chiffrage après
les schémas) :

1. Demander en une seule question celles qui sont facultatives.
2. `start` chacune de celles retenues.
3. Lancer en même temps un sous-agent par étape : l'agent de son champ
   `agent` s'il en a un (ses consignes et son modèle), sinon un sous-agent
   au modèle de son niveau. Il reçoit le seul `stage` de son `start`, le
   dossier et les chemins des scripts de ses skills ; il produit les
   livrables, lance les `checks` (`check --submit` s'il y a un `run`) et
   note ses choix au journal (`journal.py` attend son tour, rien ne se
   perd).
4. Soumettre les étapes qui ne le sont pas encore et présenter leurs revues
   ensemble.

Sans outil de sous-agent, les mener l'une après l'autre.

## Retour sur une étape validée

`review --decision retour` remet à reprendre elle et les suivantes :
les reprendre dans l'ordre, chacune avec sa revue, par éditions ciblées en
gardant les identifiants.

## Mission

- Nouvelle avant-vente ou revue hors mission : `mission.py init DOSSIER
  --nature avant-vente|revue --name "<projet>"` (skill `mission-workspace`)
  démarre le workflow de sa nature, vault compris.
- Hors mission, avec un vault : le dossier du vault est choisi par
  `vault_profile.py` (skill `markdown-to-obsidian`) avant `journal.py init
  --vault VAULT --folder <dossier>`.
- Avant de livrer un dossier ou une offre d'une mission : `mission.py check
  DOSSIER` (cohérence entre livrables, à corriger ou à faire accepter avec
  la raison de l'utilisateur).
