"""Qui peut faire quoi dans quelle mission : rôle de l'utilisateur sur le projet GitLab de la mission.

Le service reçoit l'utilisateur d'Open WebUI (courriel, transmis par le pipe, seul détenteur du
jeton du service). Avec Open WebUI branché sur GitLab (OIDC), ce courriel est celui du compte
GitLab : son rôle sur le projet de la mission, groupes hérités compris (members/all), décide.

    Reporter (20) et plus : /statut, lecture ; Developer (30) et plus : tours d'agent.
    Seuils : access.read_level et access.write_level.

Fournisseur « file » : un fichier JSON {mission: {utilisateur: niveau}}, pour un poste seul ou les
tests. Toute erreur (GitLab injoignable, utilisateur introuvable) refuse l'accès.
"""

import json
import os
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse

LEVELS = {0: "aucun", 10: "Guest", 15: "Planner", 20: "Reporter", 30: "Developer", 40: "Maintainer", 50: "Owner"}
_cache: dict[tuple, tuple[float, int]] = {}
_lock = threading.Lock()


def project_of(mission: dict) -> str:
    """Chemin du projet GitLab : mission.project, sinon tiré de l'URL du dépôt."""
    if mission.get("project"):
        return mission["project"]
    repo = mission["repo"]
    path = urlparse(repo).path if "://" in repo else repo.split(":", 1)[-1]
    return path.strip("/").removesuffix(".git")


def _get(url: str, token: str) -> tuple[int, object]:
    request = urllib.request.Request(url, headers={"PRIVATE-TOKEN": token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read() or b"null")
    except urllib.error.HTTPError as error:
        return error.code, None


def gitlab_level(access: dict, project: str, user: str) -> int:
    token = os.environ.get(access.get("token_env", "GITLAB_ACCESS_TOKEN"), "")
    if not token:
        raise PermissionError(f"variable {access.get('token_env', 'GITLAB_ACCESS_TOKEN')} vide : "
                              "jeton GitLab (read_api) attendu pour lire les droits")
    api = access["api"].rstrip("/")
    if "@" in user:
        code, found = _get(f"{api}/users?search={quote(user)}", token)
        wanted = user.lower()
        users = [u for u in (found or []) if wanted in {str(u.get(k, "")).lower()
                                                      for k in ("email", "public_email", "commit_email")}]
    else:
        code, users = _get(f"{api}/users?username={quote(user)}", token)
    if code != 200:
        raise PermissionError(f"GitLab : recherche de l'utilisateur, code {code}")
    if len(users or []) != 1:
        raise PermissionError(f"utilisateur « {user} » introuvable dans GitLab (courriel public, ou jeton "
                              "administrateur pour les courriels privés)")
    code, member = _get(f"{api}/projects/{quote(project, safe='')}/members/all/{users[0]['id']}", token)
    if code == 404:
        return 0
    if code != 200:
        raise PermissionError(f"GitLab : droits sur {project}, code {code}")
    return int(member.get("access_level", 0))


def file_level(access: dict, base: Path, name: str, user: str) -> int:
    table = json.loads((base / access["file"]).read_text(encoding="utf-8"))
    rights = {k.lower(): v for k, v in table.get(name, {}).items()}
    return int(rights.get(user.lower(), rights.get("*", 0)))


def level(config: dict, name: str, user: str) -> int:
    access = config["access"]
    key = (name, user.lower())
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < access.get("cache_seconds", 300):
            return hit[1]
    if access.get("provider", "gitlab") == "file":
        found = file_level(access, Path(config["_base"]), name, user)
    else:
        found = gitlab_level(access, project_of(config["missions"][name]), user)
    with _lock:
        _cache[key] = (time.monotonic(), found)
    return found


def check(config: dict, name: str, user: str | None, write: bool) -> str | None:
    """None si l'utilisateur peut agir, sinon la raison du refus (affichée dans le chat)."""
    access = config.get("access")
    if not access:
        return None
    if not user:
        return "utilisateur inconnu : le contrôle d'accès est actif (access) et le pipe n'a transmis personne"
    try:
        got = level(config, name, user)
    except (PermissionError, OSError, ValueError) as error:
        return f"accès refusé, droits illisibles : {error}"
    need = access.get("write_level", 30) if write else access.get("read_level", 20)
    if got < need:
        return (f"accès refusé : {user} a le rôle {LEVELS.get(got, got)} sur la mission « {name} », "
                f"{LEVELS.get(need, need)} requis pour {'jouer un tour' if write else 'lire son état'}")
    return None
