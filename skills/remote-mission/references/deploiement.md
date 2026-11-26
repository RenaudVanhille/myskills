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
  `--continue` pour Claude Code) : il garde le contexte de la conversation.
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
  (`missions.<nom>.git_secret`). Le service frontal vérifie les droits avant
  chaque message.
- `runner.kind: local` (défaut) traite les conversations dans le service lui-même,
  sur un volume persistant : utile sur un poste ou sans droit de créer des pods.

## 1. Image

```bash
docker build -f skills/remote-mission/assets/Dockerfile -t registry.exemple.local/myskills/remote-mission:2.4.0 .
```

L'image contient git, uv, Claude Code et les skills de myskills
(`install.py sync --tools claude`). Les modèles locaux éventuels
(`doctor.py GROUPE --prefetch`, skill `check-prerequisites`) s'ajoutent à la
construction, jamais pendant une session. Un autre harness (OpenCode...) s'utilise
de même : l'installer dans l'image et changer `agent.command`.

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

   La clé va dans le Secret `myskills-session` (`ANTHROPIC_AUTH_TOKEN`), monté
   dans les seuls pods de session, jamais dans `remote.json`. L'agent la reçoit (il appelle LiteLLM) ; le jeton du
   service (`MYSKILLS_REMOTE_TOKEN`), lui, est retiré de son environnement.
2. **NetworkPolicy `litellm-clients`** (fichier facultatif
   `kubernetes/litellm-clients.yaml`) : seuls les pods déclarés joignent
   LiteLLM. Sur un LiteLLM déjà déployé, elle coupe tout client absent de sa
   liste : y ajouter d'abord chaque client actuel, et reprendre namespace,
   labels et port du déploiement existant (aussi dans la NetworkPolicy de
   sortie de `remote-mission.yaml` et `ANTHROPIC_BASE_URL`).
3. **Interface d'administration de LiteLLM** : pas d'Ingress public ; SSO de
   l'entreprise (ou GitLab) pour l'UI, clé maîtresse dans un Secret.
4. **Rien ne part ailleurs** : aucun callback de journalisation vers un service
   en ligne (Langfuse, Helicone... hébergés) ; `store_prompts_in_spend_logs:
   false` pour ne pas garder les contenus dans la base de LiteLLM.
5. Noms des modèles : les alias de LiteLLM (`claude-haiku`...) sont donnés à
   Claude Code par `ANTHROPIC_DEFAULT_HAIKU_MODEL`, `..._SONNET_...` et
   `..._OPUS_...` (`agent.env`) : les agents de myskills gardent leur niveau
   (léger, standard, puissant).

## 3. Qui accède à quelle mission

Les droits sont ceux du projet GitLab de la mission (`access`, fournisseur
`gitlab`) : à chaque message, le service lit le rôle de l'utilisateur sur le
projet, groupes hérités compris.

| Rôle GitLab | Dans le chat |
| --- | --- |
| Reporter (20) et plus | `/statut` |
| Developer (30) et plus | messages à l'agent, décisions de revue, `/fin` |
| aucun | refus motivé |

Seuils : `read_level`, `write_level`. Les droits lus sont gardés
`cache_seconds` (300 s par défaut) : un retrait de droits s'applique au plus
tard après ce délai.

- **Identité** : Open WebUI s'authentifie par GitLab (OIDC :
  `OPENID_PROVIDER_URL=https://gitlab.exemple.local/.well-known/openid-configuration`,
  `OAUTH_CLIENT_ID`, `OAUTH_CLIENT_SECRET`, `ENABLE_OAUTH_SIGNUP=true`) : le
  courriel transmis par le pipe est celui du compte GitLab.
- **Jeton de lecture des droits** (`GITLAB_ACCESS_TOKEN`) : jeton d'un compte de
  service, portée `read_api`. Un courriel privé n'est trouvé qu'avec un jeton
  administrateur ; sinon, demander aux utilisateurs un courriel public.
- **Confiance** : le service croit l'utilisateur que lui transmet le pipe, seul
  détenteur du jeton du service, et la NetworkPolicy n'admet qu'Open WebUI.
- **Conversation** : réservée à celui qui l'a ouverte.
- En complément, les droits d'Open WebUI sur les modèles (groupes) masquent une
  mission à qui n'a rien à y faire.

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
  --from-literal=ANTHROPIC_AUTH_TOKEN="<clé virtuelle LiteLLM>"
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

## 6. Open WebUI

1. Admin > Fonctions > importer `assets/openwebui_pipe.py`.
2. Valves : `SERVER_URL` (`http://myskills-remote.myskills.svc.cluster.local:8765`),
   `TOKEN` (valeur de `MYSKILLS_REMOTE_TOKEN`).
3. Un modèle apparaît par mission ; restreindre chacun aux groupes concernés.

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
