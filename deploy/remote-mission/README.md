# Déployer les missions à distance (Kubernetes, LiteLLM, GitLab, Open WebUI)

Fichiers de déploiement du skill `remote-mission`, gardés hors du skill : ils
servent à l'exploitation, pas à un agent, et ne sont donc pas copiés avec les
skills (`install.py sync`) sur les postes ni dans les pods de session.

| Fichier | Rôle |
| --- | --- |
| `chart/` | chart Helm : service frontal, sessions (RBAC, quota), NetworkPolicy, Open WebUI connecté par GitLab |
| `Dockerfile` | image du service et des sessions, avec les outils de tous les skills |
| `openwebui_pipe.py` | fonction Pipe à importer dans Open WebUI |
| `remote.example.json` | configuration du service hors Helm (poste, CI) ; le chart génère la sienne |

```
Open WebUI ──(pipe, jeton)──> myskills-remote (toujours prêt, léger) ──(read_api)──> GitLab : droits
   (SSO GitLab)                     │ crée, retrouve ou recharge le pod de la conversation
                                    v
                        pod de session (une conversation) ──(HTTPS, clé virtuelle)──> LiteLLM (autre cluster)
                          │ volume : copie de travail + contexte de l'agent
                          └──(jeton git)──> GitLab : une branche par conversation
```

## Sessions et concurrence

- **Service frontal toujours prêt** : un pod léger (HTTP, droits, pods de
  session), sans dépôt ni clé LiteLLM.
- **Un pod par conversation** (`runner.kind: kubernetes`) : créé au premier
  message (10 à 30 s : image en cache, clone), il reste prêt tant que la
  conversation est active ; les messages suivants partent tout de suite.
  L'agent reprend sa session à chaque message (`agent.continue_args`,
  `--continue` pour OpenCode et Claude Code) : il garde le contexte de la conversation.
- **Arrêt après inactivité** : sans message pendant `runner.idle_minutes`
  (120 par défaut), le pod s'arrête seul ; chaque message a déjà été commité et
  poussé.
- **Retour de l'utilisateur** : la conversation retrouve son volume (PVC :
  copie de travail et `HOME` de l'agent) ; un nouveau pod le monte, la session
  est rechargée avec son contexte.
- **Fin** : `/fin` dans le chat pousse, arrête le pod et efface le volume ; un
  volume sans pod depuis `runner.retention_days` (14 jours) est effacé. Le
  travail reste sur la branche.
- **Concurrence** : un message à la fois par conversation (un message envoyé
  pendant un autre suit celui en cours), au plus `server.max_jobs` messages
  traités en même temps par le service, et le `ResourceQuota` du namespace
  plafonne les sessions ouvertes. Deux conversations d'une mission
  travaillent sur deux branches : rien ne s'écrase, un conflit se règle à la
  merge request.
- **Isolation** : un pod ne voit que sa conversation et sa mission, sans
  jeton de l'API du cluster ; jeton git propre à une mission possible
  (`missions.<nom>.git_secret`).
- `runner.kind: local` (défaut) traite les conversations dans le service lui-même,
  sur un volume persistant : utile sur un poste ou sans droit de créer des pods.

## Choisir la mission dans Open WebUI

Une mission = un projet GitLab qui porte le topic `discovery.topic` (par
exemple `myskills-mission`), dans `discovery.group` s'il est donné : rien à
déclarer dans `remote.json`, ajouter le topic au projet suffit. Open WebUI
montre un seul modèle, « Missions » ; dans une conversation neuve :

| Message | Effet |
| --- | --- |
| `/missions` | missions où l'utilisateur a au moins le rôle de lecture |
| `/mission archi/portail` | lie la conversation à cette mission (rôle d'écriture), sa session démarre au message suivant |
| autre message, conversation non liée | rappel de ces deux commandes |

La liaison est gardée par le service (sur le volume de session en mode
kubernetes) : une conversation reprise des jours plus tard retrouve sa
mission. Le compte de service GitLab (`GITLAB_ACCESS_TOKEN`) doit voir les
projets missions (Reporter sur le groupe). Un projet archivé, sans le topic
ou hors de `allowed_hosts` n'est pas une mission. `missions` de
`remote.json` reste possible : un modèle par mission déclarée.

## 1. Image

```bash
docker build -f deploy/remote-mission/Dockerfile -t registry.exemple.local/myskills/remote-mission:2.4.0 .
```

Une seule image sert au service frontal et aux pods de session. Elle contient
tout ce que les skills utilisent, préparé à la construction pour qu'une
session travaille hors ligne (`UV_OFFLINE`, `MYSKILLS_OFFLINE`,
`HF_HUB_OFFLINE`) :

| Besoin | Dans l'image |
| --- | --- |
| Agent | OpenCode (`OPENCODE_VERSION`, licence MIT) ; Claude Code en plus si `CLAUDE_CODE_VERSION` est donné ; skills et agents de myskills |
| Scripts | uv, Python 3.12, environnement de chaque script préparé (`uv sync --script`) |
| Schémas | draw.io Desktop (`DRAWIO_VERSION`) sous écran virtuel (xvfb), Chromium de Playwright, Node.js et LikeC4, paquets Mermaid et Excalidraw en cache |
| Extraction | Tesseract (fr, en), modèles Docling et Whisper préchargés depuis leurs sources épinglées (`doctor.py tout --prefetch`, empreintes vérifiées) |
| Publication | LibreOffice sans interface, polices ; skill externe markdown-to-pptx si `MD2PPTX_REPO` est donné |
| Revue | graphify (skill externe) |

La construction finit par `doctor.py tout` (journal de construction) : un
outil absent y est signalé. Les caches (uv, modèles, navigateur) sont hors du
`HOME`, qui est sur le volume de la session. Chromium et draw.io tournent
sans bac à sable (`MYSKILLS_NO_SANDBOX=1`, le pod n'a aucun privilège). Au
démarrage d'un pod, un conteneur d'initialisation copie les skills de l'image
dans le `HOME` de la session (`install.py sync`, `runner.tools`) : une
nouvelle image les met à jour au rechargement suivant. Un autre harness
(OpenCode...) s'installe de même dans l'image, avec `agent.command` et
`runner.tools`.

## 2. LiteLLM hors du cluster : une clé propre aux sessions, un accès réservé

LiteLLM tourne sur un autre cluster : les pods de session le joignent par
HTTPS (`litellm.url`, par exemple `https://litellm.exemple.local/v1`), par la
sortie du cluster. Seuls eux l'appellent ; le service frontal et Open WebUI
n'y ont pas accès.

1. **Clé virtuelle dédiée**, créée par un administrateur de LiteLLM, limitée
   aux modèles utiles, avec un budget et une équipe à part :

   ```bash
   curl -s https://litellm.exemple.local/key/generate \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
     -d '{"key_alias": "myskills-remote", "team_id": "myskills",
          "models": ["claude-haiku", "claude-sonnet", "claude-opus"],
          "max_budget": 200, "budget_duration": "30d", "rpm_limit": 60}'
   ```

   La clé va dans le Secret des sessions (`LITELLM_API_KEY`), monté dans les
   seuls pods de session. L'agent la reçoit (il appelle LiteLLM) ; le jeton du
   service (`MYSKILLS_REMOTE_TOKEN`), lui, est retiré de son environnement.
2. **Flux réservé, des deux côtés** : ici, la NetworkPolicy des sessions
   n'ouvre que `litellm.cidrs` sur `litellm.port` (adresse de LiteLLM ou de
   son Ingress) ; côté LiteLLM, n'admettre que l'adresse de sortie de ce
   cluster (liste d'IP de l'Ingress ou pare-feu), en plus de la clé.
3. **Certificat** : un certificat d'une autorité interne se déclare par
   `caSecret` (Secret avec les `*.crt`) : ajouté aux autorités de l'image pour
   git, Python et Node, dans les sessions, le service et Open WebUI.
4. **Interface d'administration de LiteLLM** : pas d'accès public ; SSO de
   l'entreprise (ou GitLab), clé maîtresse dans un Secret.
5. **Rien ne part ailleurs** : aucun callback de journalisation vers un service
   en ligne (Langfuse, Helicone... hébergés) ; `store_prompts_in_spend_logs:
   false` pour ne pas garder les contenus dans la base de LiteLLM.
6. **Noms des modèles** : les alias de LiteLLM (`litellm.models` : simple,
   moyen, complexe) vont dans la configuration d'OpenCode et dans le modèle de
   chaque niveau des agents de myskills (`opencode.json` et `models.json`,
   générés par le chart dans sa ConfigMap).

## Agent : OpenCode (défaut) ou Claude Code

OpenCode (licence MIT) est l'agent par défaut : `agent.command`
`["opencode", "run", "{prompt}"]`, `continue_args` `["--continue"]`,
configuration `OPENCODE_CONFIG=/etc/myskills/opencode.json` (seul fournisseur
LiteLLM, partage désactivé, ni mise à jour ni téléchargement de modèles ou de
serveurs de langage, `webfetch` refusé, shell limité à `uv run`, `python` et
la lecture de git). Vérifié face à un LiteLLM simulé, Internet coupé : réponse,
reprise de session avec son contexte, agents de myskills trouvés avec leur
modèle par niveau.

Claude Code reste possible si sa licence convient : construire l'image avec
`--build-arg CLAUDE_CODE_VERSION=...`, puis `agent.kind: claude` dans les
valeurs du chart (commande, alias des modèles par `ANTHROPIC_DEFAULT_*_MODEL`
et skills copiés pour Claude Code), la clé dans le Secret des sessions sous
`ANTHROPIC_AUTH_TOKEN`.

## 3. Qui accède à quelle mission

Les droits sont ceux du projet GitLab de la mission (`access`, fournisseur
`gitlab`) : le rôle de l'utilisateur sur le projet, groupes hérités
compris, est lu au début de la session (création ou rechargement du pod),
puis avant chaque pull et chaque push sur le dépôt ; pas à chaque message.

| Moment | Rôle exigé (défaut) |
| --- | --- |
| Début de session | Developer (30), Reporter (20) pour `/statut` |
| Avant un pull | Reporter (20) |
| Avant un push | Developer (30) : sinon le commit reste dans la session, refus motivé |

Un droit retiré pendant une session s'applique donc au prochain pull ou push.
Seuils : `read_level`, `write_level`. Les droits lus sont gardés
`cache_seconds` (300 s par défaut) dans chaque pod.

- **Identité** : Open WebUI s'authentifie par GitLab seulement (section 6) :
  le courriel transmis par le pipe est celui du compte GitLab.
- **Jeton de lecture des droits** (`GITLAB_ACCESS_TOKEN`, dans les Secrets
  `myskills-remote` et `myskills-session` : le pod de session vérifie les
  droits avant ses pull et push) : jeton d'un compte de
  service, portée `read_api`. Un courriel privé n'est trouvé qu'avec un jeton
  administrateur ; sinon, demander aux utilisateurs un courriel public.
- **Confiance** : le service croit l'utilisateur que lui transmet le pipe, seul
  détenteur du jeton du service, et la NetworkPolicy n'admet qu'Open WebUI.
- **Conversation** : réservée à celui qui l'a ouverte.

## 4. Git

Jeton de déploiement GitLab (`write_repository`) par projet de mission ou
jeton de groupe, dans le Secret `myskills-git` (fichier `.git-credentials`, `secrets.git`).
Protéger `main` : les sessions ne poussent que sur `openwebui/<conversation>` ;
l'utilisateur fusionne par une merge request.

## 5. Installer avec Helm

Un namespace, une installation (le service retrouve les pods de session par
leurs labels dans son namespace).

1. **Application GitLab pour Open WebUI** (Admin > Applications, ou celle d'un
   groupe) : nom `Open WebUI`, URI de redirection
   `https://chat.exemple.local/oauth/oidc/callback`, confidentielle, portées
   `openid`, `email`, `profile`. Garder l'Application ID et le Secret.
2. **Secrets**, créés à part (le chart ne fait que les nommer) :

   ```bash
   kubectl create namespace myskills
   kubectl -n myskills create secret generic myskills-remote \
     --from-literal=MYSKILLS_REMOTE_TOKEN="$(openssl rand -hex 32)" \
     --from-literal=GITLAB_ACCESS_TOKEN="<jeton read_api>"
   kubectl -n myskills create secret generic myskills-session \
     --from-literal=LITELLM_API_KEY="<clé virtuelle LiteLLM>" \
     --from-literal=GITLAB_ACCESS_TOKEN="<jeton read_api>"
   kubectl -n myskills create secret generic myskills-git --from-file=.git-credentials
   kubectl -n myskills create secret generic open-webui \
     --from-literal=WEBUI_SECRET_KEY="$(openssl rand -hex 32)" \
     --from-literal=OAUTH_CLIENT_ID="<Application ID>" \
     --from-literal=OAUTH_CLIENT_SECRET="<Secret>"
   # autorité interne, si GitLab ou LiteLLM en ont une : --set caSecret=autorite-interne
   kubectl -n myskills create secret generic autorite-interne --from-file=interne.crt
   ```

3. **Valeurs** (`values.yaml` du chart, à copier) : `image`, `gitlab.url` et
   `gitlab.cidrs`, `gitlab.discovery` (topic des missions), `litellm.url`,
   `litellm.cidrs` et `litellm.models`, `kubernetes.apiCidrs` (adresse de
   l'API du cluster : `kubectl get endpoints kubernetes`), `openWebui.url`,
   `openWebui.ingress`, groupes GitLab d'Open WebUI.
4. **Installation** :

   ```bash
   helm upgrade --install myskills deploy/remote-mission/chart -n myskills -f mes-valeurs.yaml
   ```

   Le chart crée : la ConfigMap (`remote.json`, `opencode.json`,
   `models.json`, générés depuis les valeurs), le compte de service et son
   Role (pods et volumes du namespace), un `ResourceQuota`, le service
   frontal, Open WebUI (volume, Ingress) et les NetworkPolicy (service :
   entrée depuis Open WebUI, sortie vers l'API du cluster, GitLab et les
   sessions ; sessions : entrée depuis le service, sortie vers GitLab et
   LiteLLM ; Open WebUI : entrée depuis l'Ingress, sortie vers le service et
   GitLab). Les notes de fin d'installation donnent la commande de
   vérification (`remote_server.py check`) et les Valves du pipe.

Le contenu des conversations reste dans les volumes de session : réserver aux
administrateurs le droit de lire les volumes et d'entrer dans les pods du
namespace.

## 6. Open WebUI et SSO GitLab

Open WebUI (`openWebui.enabled`) n'a que GitLab comme moyen de connexion : ni
formulaire ni mot de passe, ni Ollama ni API OpenAI directe, ni télémétrie
ni téléchargement de modèle.

1. **Qui entre** : les groupes GitLab de l'utilisateur (revendication
   `groups`) décident du rôle dans Open WebUI : `openWebui.allowedGroups`
   pour entrer, `openWebui.adminGroups` pour administrer. Les missions,
   elles, restent ouvertes selon le rôle sur leur projet GitLab (section 3) ;
   aucun droit par modèle n'est à poser dans Open WebUI.
2. **Fonction Pipe** (un administrateur) : Admin > Fonctions > importer
   `openwebui_pipe.py`, l'activer, puis Valves : `SERVER_URL` et `TOKEN`
   donnés par les notes de l'installation. Le modèle « Missions » apparaît
   pour tous (modèle public).

Le pipe affiche la progression du message (statut), puis la réponse, les schémas
PNG (en ligne jusqu'à `inline_images_kb`, liens GitLab vers le PNG et le
`.drawio`) et l'étape en revue. Un traitement plus long que la requête
continue en arrière-plan : son résultat s'affiche au message suivant.

## Limites connues

- Le vault Obsidian n'est pas servi : le parcourir dans GitLab ou le tirer
  en local (`git pull` de la branche).
- Les pièces jointes du chat ne sont pas transmises : déposer les documents
  dans `documents/` du dépôt.
- Un redémarrage du service ne coupe pas les sessions (elles vivent dans
  leurs pods, retrouvés au message suivant), mais la réponse d'un message en
  cours à ce moment ne s'affiche pas : la branche garde le travail. En mode
  `local`, un redémarrage interrompt le message en cours.
- Un pod de session arrêté en plein message (nœud perdu) reprend au message
  suivant depuis son volume ; le message interrompu n'a pas de commit.
