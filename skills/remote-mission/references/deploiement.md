# Déployer les missions à distance (Kubernetes, LiteLLM, GitLab, Open WebUI)

```
Open WebUI ──(pipe, jeton)──> myskills-remote (toujours prêt, léger) ──(read_api)──> GitLab : droits
   (SSO GitLab)                     │ crée, retrouve ou recharge le pod de la conversation
                                    v
                        pod de session (une conversation) ──(clé virtuelle)──> LiteLLM
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
docker build -f skills/remote-mission/assets/Dockerfile -t registry.exemple.local/myskills/remote-mission:2.4.0 .
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

## 2. LiteLLM : une clé propre au service, un accès réservé

1. **Clé virtuelle dédiée**, créée par un administrateur de LiteLLM, limitée
   aux modèles utiles, avec un budget et une équipe à part :

   ```bash
   curl -s http://litellm.litellm.svc.cluster.local:4000/key/generate \
     -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" \
     -d '{"key_alias": "myskills-remote", "team_id": "myskills",
          "models": ["claude-haiku", "claude-sonnet", "claude-opus"],
          "max_budget": 200, "budget_duration": "30d", "rpm_limit": 60}'
   ```

   La clé va dans le Secret `myskills-session` (`LITELLM_API_KEY`), monté
   dans les seuls pods de session, jamais dans `remote.json`. L'agent la reçoit (il appelle LiteLLM) ; le jeton du
   service (`MYSKILLS_REMOTE_TOKEN`), lui, est retiré de son environnement.
2. **NetworkPolicy `litellm-clients`** (fichier facultatif
   `kubernetes/litellm-clients.yaml`) : seuls les pods déclarés joignent
   LiteLLM. Sur un LiteLLM déjà déployé, elle coupe tout client absent de sa
   liste : y ajouter d'abord chaque client actuel, et reprendre namespace,
   labels et port du déploiement existant (aussi dans la NetworkPolicy de
   sortie de `remote-mission.yaml` et `LITELLM_BASE_URL`).
3. **Interface d'administration de LiteLLM** : pas d'Ingress public ; SSO de
   l'entreprise (ou GitLab) pour l'UI, clé maîtresse dans un Secret.
4. **Rien ne part ailleurs** : aucun callback de journalisation vers un service
   en ligne (Langfuse, Helicone... hébergés) ; `store_prompts_in_spend_logs:
   false` pour ne pas garder les contenus dans la base de LiteLLM.
5. Noms des modèles : les alias de LiteLLM (`claude-haiku`, `claude-sonnet`,
   `claude-opus`) sont déclarés dans `opencode.json` (fournisseur `litellm`,
   compatible OpenAI) et `models.json` les donne aux agents de myskills par
   niveau (léger, standard, puissant) quand les skills sont copiés dans la
   session (`runner.models`). Les deux fichiers sont dans la ConfigMap.

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
`--build-arg CLAUDE_CODE_VERSION=...`, puis dans `remote.json` :

```json
"agent": {
  "command": ["claude", "-p", "{prompt}", "--output-format", "text", "--permission-mode", "acceptEdits",
              "--allowedTools", "Bash(uv run:*)", "Bash(python:*)", "Read", "Write", "Edit", "Glob", "Grep", "Skill", "Agent"],
  "env": {"ANTHROPIC_BASE_URL": "http://litellm.litellm.svc.cluster.local:4000",
          "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku", "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet",
          "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1"},
  "continue_args": ["--continue"]
},
"runner": {"tools": "claude", "models": "/etc/myskills/models.json"}
```

et la clé dans le Secret sous `ANTHROPIC_AUTH_TOKEN`.

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
jeton de groupe, dans le Secret `myskills-git` (fichier `.git-credentials`).
Protéger `main` : les sessions ne poussent que sur `openwebui/<conversation>` ;
l'utilisateur fusionne par une merge request.

## 5. Kubernetes

```bash
kubectl -n myskills create secret generic myskills-remote \
  --from-literal=MYSKILLS_REMOTE_TOKEN="$(openssl rand -hex 32)" \
  --from-literal=GITLAB_ACCESS_TOKEN="<jeton read_api>"
kubectl -n myskills create secret generic myskills-session \
  --from-literal=LITELLM_API_KEY="<clé virtuelle LiteLLM>" \
  --from-literal=GITLAB_ACCESS_TOKEN="<jeton read_api>"
kubectl -n myskills create secret generic myskills-git --from-file=.git-credentials
kubectl apply -f skills/remote-mission/assets/kubernetes/remote-mission.yaml
# facultatif, après relecture : kubectl apply -f skills/remote-mission/assets/kubernetes/litellm-clients.yaml
```

Le fichier crée : la ConfigMap de `remote.json` (missions, hôtes, `runner`),
le compte de service et son Role (pods et volumes, dans le namespace
seulement), un `ResourceQuota`, le Deployment du service, son Service et
deux NetworkPolicy (service : entrée depuis Open WebUI, sortie vers l'API du
cluster, GitLab et les pods de session ; pods de session : entrée depuis le
service seulement, sortie vers LiteLLM et GitLab). Adapter les adresses de
l'API du cluster et de GitLab, et les labels de LiteLLM. Le contenu des
conversations reste dans les volumes de session : réserver aux
administrateurs le droit de lire les volumes et d'entrer dans les pods du
namespace. Avant de brancher Open WebUI :

```bash
kubectl -n myskills exec deploy/myskills-remote -- uv run /opt/myskills/skills/remote-mission/scripts/remote_server.py check --config /etc/myskills/remote.json
```

## 6. Open WebUI et SSO GitLab

`assets/kubernetes/open-webui.yaml` déploie Open WebUI (namespace
`open-webui`, volume pour sa base, Ingress en TLS) avec GitLab comme seul
moyen de connexion : ni formulaire ni mot de passe, ni Ollama ni API OpenAI
directe, ni télémétrie ni téléchargement de modèle.

1. **Application GitLab** (Admin > Applications, ou celle d'un groupe) :
   nom `Open WebUI`, URI de redirection
   `https://chat.exemple.local/oauth/oidc/callback`, confidentielle, portées
   `openid`, `email`, `profile`. Garder l'Application ID et le Secret.
2. **Secret et manifeste** :

   ```bash
   kubectl create namespace open-webui
   kubectl -n open-webui create secret generic open-webui \
     --from-literal=WEBUI_SECRET_KEY="$(openssl rand -hex 32)" \
     --from-literal=OAUTH_CLIENT_ID="<Application ID>" \
     --from-literal=OAUTH_CLIENT_SECRET="<Secret>"
   kubectl apply -f skills/remote-mission/assets/kubernetes/open-webui.yaml
   ```

   Adapter les adresses (`WEBUI_URL`, `OPENID_PROVIDER_URL`,
   `OPENID_REDIRECT_URI`, Ingress), l'adresse de GitLab dans la
   NetworkPolicy et, pour un GitLab à certificat interne, le CA monté
   (`SSL_CERT_FILE`, `REQUESTS_CA_BUNDLE`).
3. **Qui entre** : les groupes GitLab de l'utilisateur (revendication
   `groups`) décident du rôle dans Open WebUI : `OAUTH_ALLOWED_ROLES`
   (`myskills/utilisateurs`, `myskills/admins`) pour entrer,
   `OAUTH_ADMIN_ROLES` (`myskills/admins`) pour administrer. Les missions,
   elles, restent ouvertes selon le rôle sur leur projet GitLab (section 3) ;
   aucun droit par modèle n'est à poser dans Open WebUI.
4. **Fonction Pipe** (un administrateur) : Admin > Fonctions > importer
   `assets/openwebui_pipe.py`, l'activer, puis Valves : `SERVER_URL`
   (`http://myskills-remote.myskills.svc.cluster.local:8765`), `TOKEN`
   (valeur de `MYSKILLS_REMOTE_TOKEN`). Le modèle « Missions » apparaît pour
   tous (modèle public).

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
