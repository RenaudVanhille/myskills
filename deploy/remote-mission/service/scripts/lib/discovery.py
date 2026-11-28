"""Missions découvertes dans GitLab et conversation liée à sa mission.

Un projet GitLab qui porte le topic discovery.topic (et, si discovery.group est donné, rangé dans
ce groupe ou ses sous-groupes) est une mission : rien à déclarer dans remote.json. Open WebUI
montre un seul modèle, « Missions » (MODEL_ID) ; dans une conversation neuve :

    /missions                 missions où l'utilisateur a au moins le rôle de lecture
    /mission groupe/projet    lie la conversation à cette mission (droit d'écriture exigé)

La liaison conversation -> mission est gardée par le service : fichier _conversations.json des
copies de travail en mode local ; annotation du volume de session en mode kubernetes (le volume
est créé dès le choix), retrouvée après un redémarrage du service.
"""

import json
import os
import threading
import time
from pathlib import Path
from urllib.parse import quote, urlparse

import access

MODEL_ID = "missions"
HELP = ("Cette conversation n'est liée à aucune mission. Écrivez `/missions` pour voir celles qui vous "
        "sont ouvertes, puis `/mission groupe/projet` pour choisir.")
_cache: dict[str, tuple[float, list]] = {}
_lock = threading.Lock()


def access_allowed(host: str, patterns: list[str]) -> bool:
    return any(host == p or (p.startswith("*.") and host.endswith(p[1:])) for p in patterns)


def enabled(config: dict) -> bool:
    return bool(config.get("discovery"))


def _token(config: dict) -> str:
    name = config["access"].get("token_env", "GITLAB_ACCESS_TOKEN")
    token = os.environ.get(name, "")
    if not token:
        raise PermissionError(f"variable {name} vide : jeton GitLab (read_api) attendu pour lister les missions")
    return token


def entry(config: dict, project: dict) -> dict:
    """Mission tirée d'un projet GitLab (forme de missions.<nom> de remote.json)."""
    found = {"_discovered": True, "repo": project["http_url_to_repo"], "web": project["web_url"],
             "project": project["path_with_namespace"], "title": project.get("name") or project["path_with_namespace"]}
    if project.get("default_branch"):
        found["base"] = project["default_branch"]
    if config["discovery"].get("folder"):
        found["folder"] = config["discovery"]["folder"]
    return found


def in_scope(config: dict, project: dict) -> bool:
    """Projet mission : topic, groupe, non archivé, dépôt sur un hôte autorisé (allowed_hosts)."""
    rules = config["discovery"]
    host = urlparse(project.get("http_url_to_repo", "")).hostname
    if host and not access_allowed(host, config.get("allowed_hosts", [])):
        return False
    group = rules.get("group", "").strip("/")
    path = project.get("path_with_namespace", "")
    return rules["topic"] in (project.get("topics") or project.get("tag_list") or []) and \
        (not group or path.startswith(group + "/")) and not project.get("archived")


def projects(config: dict) -> list[dict]:
    """Projets missions visibles du compte de service (mis en cache cache_seconds)."""
    rules = config["discovery"]
    with _lock:
        hit = _cache.get("all")
        if hit and time.monotonic() - hit[0] < rules.get("cache_seconds", 300):
            return hit[1]
    api, token = config["access"]["api"].rstrip("/"), _token(config)
    group = rules.get("group", "").strip("/")
    base = f"{api}/groups/{quote(group, safe='')}/projects?include_subgroups=true&" if group else f"{api}/projects?"
    found, page = [], 1
    while True:
        code, batch = access._get(f"{base}topic={quote(rules['topic'])}&archived=false&per_page=100&page={page}", token)
        if code != 200:
            raise PermissionError(f"GitLab : liste des missions, code {code}")
        found += [p for p in batch or [] if in_scope(config, p)]
        if len(batch or []) < 100:
            break
        page += 1
    with _lock:
        _cache["all"] = (time.monotonic(), found)
    return found


def find(config: dict, path: str) -> dict | None:
    """Mission d'après son chemin GitLab, ou None hors du périmètre (topic, groupe)."""
    code, project = access._get(f"{config['access']['api'].rstrip('/')}/projects/{quote(path.strip('/'), safe='')}",
                                _token(config))
    if code != 200 or not project or not in_scope(config, project):
        return None
    return entry(config, project)


def register(config: dict, path: str) -> bool:
    """Ajoute la mission découverte à config["missions"] (pour run_turn et les pods de session)."""
    if path in config["missions"]:
        return True
    found = find(config, path)
    if found:
        config["missions"][path] = found
    return found is not None


def listing(config: dict, user: str | None) -> tuple[str, list[str]]:
    """Réponse de /missions : les missions où l'utilisateur peut au moins lire, et les erreurs."""
    try:
        rows = []
        for project in projects(config):
            path = project["path_with_namespace"]
            config["missions"].setdefault(path, entry(config, project))
            if access.check(config, path, user, write=False) is None:
                rows.append(f"- `{path}` : {project.get('description') or project.get('name') or ''}".rstrip(" :"))
    except (PermissionError, OSError, ValueError) as error:
        return "", [f"missions : {error}"]
    if not rows:
        return "Aucune mission ne vous est ouverte (topic GitLab " \
               f"`{config['discovery']['topic']}`).", []
    return "Missions ouvertes :\n\n" + "\n".join(rows) + "\n\nChoisissez avec `/mission groupe/projet`.", []


class Bindings:
    """Conversation -> mission : fichier en mode local, volume de session en mode kubernetes."""

    def __init__(self, config: dict, sessions=None):
        self.sessions = sessions
        self.file = Path(config["_base"]) / config.get("workdir", "clones") / "_conversations.json"
        self.lock = threading.Lock()

    def _read(self) -> dict:
        try:
            return json.loads(self.file.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def get(self, chat: str) -> str | None:
        with self.lock:
            found = self._read().get(chat, {}).get("mission")
        if found is None and self.sessions:
            found = self.sessions.bound_mission(chat)
        return found

    def set(self, chat: str, mission: str, user: str | None) -> None:
        if self.sessions:
            self.sessions.bind(mission, chat)
        with self.lock:
            data = self._read()
            data[chat] = {"mission": mission, "user": (user or "").lower(), "at": int(time.time())}
            self.file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
            tmp.replace(self.file)
