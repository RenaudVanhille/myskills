# Moteur de workflow : cas particuliers

À lire seulement quand l'agent `architecture-workflow` le dit : plusieurs
étapes prêtes en même temps, retour sur une étape validée, mission.

## Étapes en parallèle

Quand `ready` liste plusieurs étapes (par exemple revue et chiffrage après
les schémas) :

1. Demander en une seule question celles qui sont facultatives.
2. `start` chacune de celles retenues.
3. Lancer en même temps un sous-agent par étape : l'agent de son champ
   `agent` s'il en a un (ses consignes), sinon un sous-agent, toujours au
   modèle du niveau de l'étape (`level`, paramètre de modèle de l'outil de
   sous-agent) : une étape moyenne confiée à un agent complexe tourne au
   modèle standard. Il reçoit le seul `stage` de son `start`, le
   dossier et les chemins des scripts de ses skills ; il produit les
   livrables, lance les `checks` (`check --submit` s'il y a un `run`) et
   note ses choix au journal (`journal.py` attend son tour, rien ne se
   perd).
4. Soumettre les étapes qui ne le sont pas encore et présenter leurs revues
   ensemble.

Sans outil de sous-agent, les mener l'une après l'autre.

## Retour sur une étape validée

`review --decision retour` remet à reprendre l'étape seule : la reprendre
par éditions ciblées en gardant les identifiants, puis la soumettre. À sa
validation, `impacts.redo` liste les étapes dont une entrée a changé, déjà
remises à reprendre : les reprendre dans l'ordre, chacune avec sa revue.
Les étapes de `impacts.kept` restent validées : ne pas les relancer ni
réécrire leurs livrables (schémas compris). Chaque version validée est
gardée : dans une mission qui a son dépôt git, par le commit
`valide(ETAPE)` (`git log`, `git diff` pour comparer) ; sinon dans
`.historique/ETAPE/DATE/`. Les livrables se reprennent sur place, jamais de
copie `.avant-*` ou `.v1` à côté. Ce dépôt reste local : ne le poussez
jamais.

Seules les décisions sont numérotées D-xxx et ont une ligne du tableau
« Décisions » de journal.md et une note dans le vault : choix, hypothèses,
questions et réponses, retours, sauts, annotations. Les soumissions,
validations, invalidations, passages de main et rapports d'agent sont des
événements E-xxx, gardés dans workflow.json (statuts, empreintes, retours
y renvoient) et listés dans la section repliée « Historique des étapes ».
Ne notez pas de `log` pour une simple validation ou un message de suivi.
Un journal tenu avant cette règle perd ce bruit à `upgrade --apply`
(`upgrade.noise`, repris par `mission.py upgrade`) : seules restent, par
étape, la dernière soumission et la dernière validation ou invalidation,
renumérotées E-xxx ; l'état d'avant reste dans le commit git de la mission.

Le journal reste compact sur un workflow rejoué : à la validation (ou au
saut) d'une étape, les entrées de ses versions précédentes (choix,
hypothèses, passages, soumissions, retour ou invalidation qui l'a rouverte)
et ses soumissions remplacées passent à `archive` dans `workflow.json`, avec
l'entrée qui les remplace (`superseded_by`, rapport `superseded`). Rien
n'est supprimé : `journal.md` les range dans une section « Archives »
repliée, le vault n'en garde pas de note, `lessons.py` en lit toujours les
retours. Une question ouverte, ou dont la réponse est active, reste active.
Les identifiants ne sont jamais réattribués. Un journal
rejoué avant cette règle s'allège par `upgrade DOSSIER --apply`.

## Entrées d'un autre workflow

Un motif `../` du champ `inputs` (exigences ou options du workflow parent,
lues par une restitution) est pris en empreinte au démarrage de l'étape.
S'il change ensuite, `status` avertit (« fichiers extérieurs modifiés après
validation », repris par `mission.py status`) : montrez-le à l'utilisateur,
qui décide du retour.

## Mission

- Nouvelle avant-vente ou revue hors mission : `mission.py init DOSSIER
  --nature avant-vente|revue --name "<projet>"` (skill `mission-workspace`)
  démarre le workflow de sa nature, vault compris ; si l'utilisateur cite
  le référentiel de son client, ajoute `--referentiel DOSSIER` (ses notes
  sont copiées dans le vault).
- Hors mission, avec un vault : le dossier du vault est choisi par
  `vault_profile.py` (skill `markdown-to-obsidian`) avant `journal.py init
  --vault VAULT --folder <dossier>`.
- Avant de livrer un dossier ou une offre d'une mission : `mission.py check
  DOSSIER` (cohérence entre livrables, à corriger ou à faire accepter avec
  la raison de l'utilisateur). Un `next` qui propose de verser des notes au
  référentiel du client : montre le `referentiel.py push` à blanc, `--apply`
  seulement avec son accord.
- Un avertissement de `mission.py status` sur des copies de sauvegarde ou
  des dossiers de travail à ranger : montre `mission.py tidy DOSSIER` à
  blanc, puis `--apply` avec l'accord de l'utilisateur.
