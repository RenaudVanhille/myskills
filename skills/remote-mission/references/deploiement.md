# Déployer les missions à distance (Kubernetes, LiteLLM, GitLab, Open WebUI)

```
Open WebUI ──(pipe, jeton)──> myskills-remote (toujours prêt, léger) ──(read_api)──> GitLab : droits
   (SSO GitLab)                     │ crée un Job par tour (API du cluster)
                                    v
                              pod du tour (une mission) ──(clé virtuelle)──> LiteLLM
                                    └──(jeton git)──> GitLab : une branche par conversation
```

## Démarrage et concurrence

- **Service toujours prêt** : un pod léger (HTTP, droits, Jobs), sans dépôt ni
  clé LiteLLM.
- **Un Job par tour** (`runner.kind: kubernetes`) : pod à la demande, image
  déjà prête (outils et skills), dépôt de la seule mission cloné dans un volume
  vide, commit et push, puis arrêt ; le Job s'efface après `ttl_seconds`.
  Compter 10 à 30 s de démarrage (image en cache sur le nœud, clone).
- **Concurrence** : un tour à la fois par conversation (un message pendant un
  tour suit le tour en cours ; un Job encore actif est retrouvé après un
  redémarrage du service), au plus `server.max_jobs` tours en parallèle, et le
  `ResourceQuota` du namespace en plafond. Deux conversations d'une mission
  travaillent sur deux branches : rien ne s'écrase, un conflit se règle à la
  merge request.
- **Isolation** : un pod ne voit que sa mission, sans jeton de l'API du
  cluster ; jeton git propre à une mission possible (`missions.<nom>.git_secret`).
- `runner.kind: local` (défaut) joue les tours dans le pod du service, sur un
  volume persistant : utile sur un poste ou sans droit de créer des Jobs.

Tout est auto-hébergé : aucun contenu de mission ne sort vers un service tiers
(AGENTS.md, section 5). Les seuls flux sortants du pod sont LiteLLM et GitLab
(NetworkPolicy et `allowed_hosts`, repris dans `MYSKILLS_ALLOWED_HOSTS` pour
les scripts qui chargent un modèle local).

## 1. Image

```bash
docker build -f skills/remote-mission/assets/Dockerfile -t registry.exemple.local/myskills/remote-mission:2.4.0 .
```

L'image contient git, uv, Claude Code et les skills de myskills
(`install.py sync --tools claude`). Les modèles locaux éventuels
(`doctor.py GROUPE --prefetch`, skill `check-prerequisites`) s'ajoutent à la
construction, jamais pendant un tour. Un autre harness (OpenCode...) s'utilise
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

   La clé va dans le Secret `myskills-turn` (`ANTHROPIC_AUTH_TOKEN`), monté
   dans les seuls pods des tours, jamais dans `remote.json`. L'agent la reçoit (il appelle LiteLLM) ; le jeton du
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
`gitlab`) : à chaque tour, le service lit le rôle de l'utilisateur sur le
projet, groupes hérités compris.

| Rôle GitLab | Dans le chat |
| --- | --- |
| Reporter (20) et plus | `/statut` |
| Developer (30) et plus | tours d'agent, décisions de revue |
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
Protéger `main` : les tours ne poussent que sur `openwebui/<conversation>` ;
l'utilisateur fusionne par une merge request.

## 5. Kubernetes

```bash
kubectl -n myskills create secret generic myskills-remote \
  --from-literal=MYSKILLS_REMOTE_TOKEN="$(openssl rand -hex 32)" \
  --from-literal=GITLAB_ACCESS_TOKEN="<jeton read_api>"
kubectl -n myskills create secret generic myskills-turn \
  --from-literal=ANTHROPIC_AUTH_TOKEN="<clé virtuelle LiteLLM>"
kubectl -n myskills create secret generic myskills-git --from-file=.git-credentials
kubectl apply -f skills/remote-mission/assets/kubernetes/remote-mission.yaml
# facultatif, après relecture : kubectl apply -f skills/remote-mission/assets/kubernetes/litellm-clients.yaml
```

Le fichier crée : la ConfigMap de `remote.json` (missions, hôtes, `runner`),
le compte de service et son Role (Jobs, pods et leurs journaux, dans le
namespace seulement), un `ResourceQuota`, le Deployment du service, son
Service et deux NetworkPolicy (service : entrée depuis Open WebUI, sortie
vers l'API du cluster et GitLab ; pods des tours : aucune entrée, sortie vers
LiteLLM et GitLab). Adapter les adresses de l'API du cluster et de GitLab,
et les labels de LiteLLM. Le message de l'utilisateur passe dans la
définition du Job (variable `MYSKILLS_MESSAGE`) : lisible par qui peut lire
les Jobs du namespace, à réserver aux administrateurs. Avant de brancher
Open WebUI :

```bash
kubectl -n myskills exec deploy/myskills-remote -- uv run /opt/myskills/skills/remote-mission/scripts/remote_server.py check --config /etc/myskills/remote.json
```

## 6. Open WebUI

1. Admin > Fonctions > importer `assets/openwebui_pipe.py`.
2. Valves : `SERVER_URL` (`http://myskills-remote.myskills.svc.cluster.local:8765`),
   `TOKEN` (valeur de `MYSKILLS_REMOTE_TOKEN`).
3. Un modèle apparaît par mission ; restreindre chacun aux groupes concernés.

Le pipe affiche la progression du tour (statut), puis la réponse, les schémas
PNG (en ligne jusqu'à `inline_images_kb`, liens GitLab vers le PNG et le
`.drawio`) et l'étape en revue. Un tour plus long que la requête continue en
arrière-plan : son résultat s'affiche au message suivant.

## Limites connues

- Le vault Obsidian n'est pas servi : le parcourir dans GitLab ou le tirer
  en local (`git pull` de la branche).
- Les pièces jointes du chat ne sont pas transmises : déposer les documents
  dans `documents/` du dépôt.
- Un redémarrage du service ne coupe pas les Jobs en cours (ils finissent,
  font le commit et poussent), mais leur progression et leur réponse ne
  s'affichent plus dans le chat : `/statut` donne l'état, la branche garde le
  travail. En mode `local`, un redémarrage interrompt le tour.
