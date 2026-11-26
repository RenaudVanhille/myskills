---
name: remote-mission
description: "Fait tourner une mission myskills à distance, depuis son dépôt GitLab auto-hébergé, avec Open WebUI comme seule interface : une conversation = une mission et une branche, chaque message un tour d'agent sans terminal (modèles servis par LiteLLM), portes de revue posées dans le chat, commit et push à chaque tour. Service HTTP, fonction Pipe d'Open WebUI et manifestes Kubernetes fournis. À utiliser pour déployer ou exploiter des missions hors du poste de l'utilisateur."
---

# remote-mission

Les chemins `scripts/...` et `assets/...` sont relatifs au dossier de ce
skill. Le service ne décide rien : il clone, lance l'agent, fait le commit
et relit le journal. Le jugement reste à l'agent lancé à chaque tour
(orientation, puis le workflow en cours).

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : remote.json : missions (dépôt GitLab auto-hébergé de chaque mission), commande de l'agent sans terminal et ses variables (LiteLLM), hôtes autorisés, contrôle d'accès (API GitLab), jeton du service ; Un message de l'utilisateur et l'identifiant de sa conversation (Open WebUI), par mission.
- **Sorties** : Contrôle d'accès : chaque tour vérifie le rôle de l'utilisateur sur le projet GitLab de la mission ; refus motivé dans le chat ; Une branche par conversation dans le dépôt de la mission, un commit par tour, poussée ; La réponse de l'agent en Markdown, les PNG changés (en ligne ou liés au dépôt avec leur .drawio), l'étape en revue posée en question ; assets/ : la fonction Pipe d'Open WebUI, une configuration d'exemple et les manifestes Kubernetes (Deployment, Service, volume, NetworkPolicy, clé LiteLLM en Secret).
- **`remote_turn.py`** : Joue un tour d'une mission à distance : configuration validée, droits de l'utilisateur sur le projet GitLab de la mission vérifiés (Reporter pour /statut, Developer pour un tour, seuils réglables) (hôtes de allowed_hosts seulement, pas d'identifiant dans une URL), copie de travail de la conversation clonée ou mise à jour sur sa branche, décision de revue « valide » ou « retour : ... » passée à journal.py review sans tour de modèle quand une seule étape attend, « /statut » sans agent, agent lancé sans terminal ni shell (claude -p sur LiteLLM...) avec son jeton retiré de l'environnement et MYSKILLS_ALLOWED_HOSTS posé, commit et push de la branche, état des workflows relu (étape en revue, questions). Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`remote_server.py`** : Service HTTP (bibliothèque standard) entre Open WebUI et les tours : chaque message lance remote_turn en arrière-plan, le pipe suit sa progression par appels longs et se raccroche au tour en cours, un tour à la fois par conversation, dernier rapport non lu rendu au message suivant ; jeton Bearer obligatoire hors de la machine, utilisateur transmis par le pipe (en-tête X-Myskills-User) et conversation réservée à celui qui l'a ouverte. check valide la configuration ; probe joue un message de bout en bout par la fonction Pipe d'Open WebUI (assets/openwebui_pipe.py) sur un port local, pour tester sans Open WebUI. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : lire l'état des workflows (status) et enregistrer la décision de revue de l'utilisateur (review).
- **Passe la main** à l'agent `orientation` : chaque tour : l'agent lancé sans terminal reprend la mission par l'agent orientation puis le workflow en cours.

## 1. Configurer

Copier `assets/remote.example.json` : une entrée par mission (dépôt,
branche de départ, adresse web GitLab pour les liens), la commande de
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
(image, volume des copies de travail, clé LiteLLM propre au service,
NetworkPolicy, import du pipe). À lire seulement pour installer ou modifier
le déploiement.

## 3. Dans le chat

- Un modèle par mission ; une nouvelle conversation part de `base` sur sa
  propre branche.
- `valide` ou `retour : ...` quand une étape est en revue : décision passée
  à `journal.py review` sans tour de modèle, puis l'agent continue.
- `/statut` : état des workflows, sans agent.
- Un message pendant un tour : le pipe suit le tour en cours ; un résultat
  manqué s'affiche au message suivant.

Un tour isolé (CI GitLab, test) se joue aussi sans le service :
`uv run scripts/remote_turn.py --config remote.json --mission NOM --chat ID --message "..."`.
