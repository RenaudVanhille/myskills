---
name: remote-mission
description: "Fait tourner une mission myskills à distance, depuis son dépôt GitLab auto-hébergé, avec Open WebUI comme seule interface : une conversation = une session (un pod Kubernetes qui garde le contexte de l'agent, arrêté après inactivité, rechargé au retour de l'utilisateur) sur une branche, modèles servis par LiteLLM, portes de revue posées dans le chat, commit et push à chaque message. Service HTTP, fonction Pipe d'Open WebUI et manifestes Kubernetes fournis. À utiliser pour déployer ou exploiter des missions hors du poste de l'utilisateur."
---

# remote-mission

Les chemins `scripts/...` et `assets/...` sont relatifs au dossier de ce
skill. Le service ne décide rien : il clone, lance l'agent, fait le commit
et relit le journal. Le jugement reste à l'agent lancé à chaque tour
(orientation, puis le workflow en cours).

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : remote.json : missions déclarées (dépôt GitLab auto-hébergé de chaque mission) ou découverte par topic GitLab, commande de l'agent sans terminal et ses variables (LiteLLM), hôtes autorisés, contrôle d'accès (API GitLab), jeton du service ; Un message de l'utilisateur et l'identifiant de sa conversation (Open WebUI), par mission.
- **Sorties** : Contrôle d'accès : rôle de l'utilisateur sur le projet GitLab de la mission vérifié au début de la session, avant chaque pull et chaque push ; refus motivé dans le chat ; Une branche par conversation dans le dépôt de la mission, un commit par message, poussée ; La réponse de l'agent en Markdown, les PNG changés (en ligne ou liés au dépôt avec leur .drawio), l'étape en revue posée en question ; assets/ : la fonction Pipe d'Open WebUI, une configuration d'exemple, l'image (outils de tous les skills, modèles et environnements préparés, travail hors ligne) et les manifestes Kubernetes (service frontal toujours prêt, un pod de session par conversation avec son volume et ses skills, RBAC limité aux pods et volumes, NetworkPolicy, clé LiteLLM en Secret, Open WebUI connecté par GitLab seulement).
- **`remote_turn.py`** : Joue un tour d'une mission à distance (déclarée dans remote.json ou découverte dans GitLab par le service) : configuration validée, droits de l'utilisateur sur le projet GitLab de la mission vérifiés au début de la session, avant chaque pull et chaque push, pas à chaque message (Developer pour ouvrir une session et pousser, Reporter pour /statut et pull, seuils réglables) (hôtes de allowed_hosts seulement, pas d'identifiant dans une URL), copie de travail de la conversation clonée ou mise à jour sur sa branche, décision de revue « valide » ou « retour : ... » passée à journal.py review sans tour de modèle quand une seule étape attend, « /statut » sans agent, « /fin » qui pousse et efface la copie de travail, session de l'agent reprise d'un message à l'autre (agent.continue_args : contexte gardé), agent lancé sans terminal ni shell (opencode run ou claude -p, sur LiteLLM) avec son jeton retiré de l'environnement et MYSKILLS_ALLOWED_HOSTS posé, commit et push de la branche, état des workflows relu (étape en revue, questions). Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`remote_server.py`** : Service HTTP (bibliothèque standard) entre Open WebUI et les tours ; missions déclarées (un modèle chacune) ou découvertes dans GitLab par leur topic (un modèle « Missions » : /missions liste celles ouvertes à l'utilisateur selon son rôle, /mission groupe/projet lie la conversation, liaison gardée après un redémarrage) ; chaque message lance remote_turn en arrière-plan, dans le service ou, avec runner kubernetes, dans le pod de session de la conversation (créé au premier message, retrouvé ensuite, arrêté après inactivité, rechargé depuis son volume avec le contexte de l'agent au retour de l'utilisateur, effacé par « /fin » ou après runner.retention_days), le pipe suit sa progression par appels longs et se raccroche au tour en cours, un tour à la fois par conversation, dernier rapport non lu rendu au message suivant ; droits vérifiés au démarrage ou au rechargement de la session, jeton Bearer obligatoire hors de la machine, utilisateur transmis par le pipe (en-tête X-Myskills-User) et conversation réservée à celui qui l'a ouverte. check valide la configuration ; probe joue un message de bout en bout par la fonction Pipe d'Open WebUI (assets/openwebui_pipe.py) sur un port local, pour tester sans Open WebUI. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : lire l'état des workflows (status) et enregistrer la décision de revue de l'utilisateur (review).
- **Passe la main** à l'agent `orientation` : chaque tour : l'agent lancé sans terminal reprend la mission par l'agent orientation puis le workflow en cours.

## 1. Configurer

Copier `assets/remote.example.json` : topic GitLab des missions
(`discovery`) ou une entrée par mission (dépôt, branche de départ, adresse
web pour les liens), la commande de
l'agent et ses variables, les hôtes autorisés (GitLab, LiteLLM : tout autre
hôte est refusé). Aucun secret dans ce fichier : jeton du service, clé
LiteLLM et accès git viennent de l'environnement (Secret Kubernetes).

```bash
uv run scripts/remote_server.py check --config remote.json
uv run scripts/remote_server.py probe --config remote.json --mission NOM
```

`probe` joue `/statut` par la fonction Pipe, sans Open WebUI ni modèle.

## 2. Déployer

Kubernetes, LiteLLM et Open WebUI : suivre `references/deploiement.md`
(image avec les outils et modèles de tous les skills, service toujours
prêt, un pod de session par conversation avec son volume, RBAC, clé LiteLLM
propre aux sessions, NetworkPolicy, Open WebUI connecté par GitLab, import du
pipe). À lire seulement pour installer ou modifier
le déploiement.

## 3. Dans le chat

- Missions trouvées dans GitLab par leur topic (`discovery`) : modèle
  « Missions », `/missions` pour la liste ouverte à l'utilisateur,
  `/mission groupe/projet` pour lier la conversation. Missions déclarées dans
  `missions` : un modèle chacune. Chaque conversation a sa branche.
- `valide` ou `retour : ...` quand une étape est en revue : décision passée
  à `journal.py review` sans tour de modèle, puis l'agent continue.
- `/statut` : état des workflows, sans agent.
- `/fin` : pousse et termine la session (pod et volume effacés) ; sans
  message pendant `runner.idle_minutes`, le pod s'arrête et la session se
  recharge au message suivant, contexte de l'agent compris.
- Un message pendant un tour : le pipe suit le tour en cours ; un résultat
  manqué s'affiche au message suivant.

Un tour isolé (CI GitLab, test) se joue aussi sans le service :
`uv run scripts/remote_turn.py --config remote.json --mission NOM --chat ID --message "..."`.
