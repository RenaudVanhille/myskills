"""Fichiers d'une mission tels que la conversation les a poussés sur sa branche, pour /fichiers et /lire.

Rien n'est exposé hors du cluster : le service reste interne et seul le pipe d'Open WebUI l'appelle (jeton
du service), qui affiche les fichiers dans le chat. Les droits de lecture de l'utilisateur sur le projet
GitLab sont vérifiés à chaque appel (access).

La branche poussée est lue, pas le pod de session : la liste marche session arrêtée ou finie. Dépôt GitLab :
API (jeton read_api du service) ; dépôt local (dev) : git ls-tree et git show.

    GET /files/MISSION/CHAT              {"mission", "branch", "files": [{"path", "size", "sha"}]}
    GET /files/MISSION/CHAT/raw?path=P   contenu brut
"""

import json
import mimetypes
import os
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

import access

HIDDEN = re.compile(r"(^|/)\.(git|obsidian|historique|myskills-tmp|trash)(/|$)")
_cache: dict[tuple, tuple[float, list]] = {}
_lock = threading.Lock()


def _gitlab(config: dict, path: str, raw: bool = False):
    token = os.environ.get(config.get("access", {}).get("token_env", "GITLAB_ACCESS_TOKEN"), "")
    request = urllib.request.Request(config["access"]["api"].rstrip("/") + path, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read()
        return body if raw else json.loads(body or b"null")


def forget() -> None:
    """Oublie les listes gardées en cache (appelé à la fin de chaque tour)."""
    with _lock:
        _cache.clear()


class Branch:
    """Fichiers d'une branche de mission : GitLab (API) ou dépôt local (git)."""

    def __init__(self, config: dict, mission: str, branch: str):
        self.config, self.mission, self.branch = config, config["missions"][mission], branch
        repo = self.mission["repo"]
        self.local = None if "://" in repo or re.match(r"^[\w.-]+@[\w.-]+:", repo) else \
            (Path(config["_base"]) / repo).resolve()
        self.project = None if self.local else quote(access.project_of(self.mission), safe="")

    def files(self) -> list[dict]:
        key = (self.mission["repo"], self.branch)
        with _lock:
            hit = _cache.get(key)
            if hit and time.monotonic() - hit[0] < 10:
                return hit[1]
        found = [f for f in self._files() if not HIDDEN.search(f["path"])]
        with _lock:
            _cache[key] = (time.monotonic(), found)
        return found

    def _files(self) -> list[dict]:
        if self.local:
            result = subprocess.run(["git", "-C", str(self.local), "ls-tree", "-r", "-l", "-z", self.branch],
                                    capture_output=True)
            if result.returncode:
                return []
            files = []
            for entry in result.stdout.decode("utf-8", "replace").split("\0"):
                if "\t" in entry:
                    meta, path = entry.split("\t", 1)
                    _, kind, sha, size = meta.split()
                    if kind == "blob":
                        files.append({"path": path, "size": int(size) if size.isdigit() else None, "sha": sha})
            return files
        files, page = [], 1
        while True:
            try:
                batch = _gitlab(self.config, f"/projects/{self.project}/repository/tree?ref={quote(self.branch, safe='')}"
                                             f"&recursive=true&per_page=100&page={page}")
            except urllib.error.HTTPError as error:
                if error.code == 404:
                    return []
                raise
            files += [{"path": b["path"], "size": None, "sha": b.get("id")} for b in batch or [] if b.get("type") == "blob"]
            if not batch or len(batch) < 100:
                return files
            page += 1

    def read(self, path: str) -> bytes | None:
        if path not in {f["path"] for f in self.files()}:
            return None
        if self.local:
            result = subprocess.run(["git", "-C", str(self.local), "show", f"{self.branch}:{path}"],
                                    capture_output=True)
            return None if result.returncode else result.stdout
        try:
            return _gitlab(self.config, f"/projects/{self.project}/repository/files/{quote(path, safe='')}/raw"
                                        f"?ref={quote(self.branch, safe='')}", raw=True)
        except urllib.error.HTTPError:
            return None


def handle(config: dict, mission: str, chat: str, user: str | None, rest: list[str], query: dict,
           branch: str) -> tuple[int, dict, bytes]:
    """Réponse de GET /files/MISSION/CHAT[/raw] : (code, en-têtes, corps)."""
    as_json = {"Content-Type": "application/json; charset=utf-8"}

    def error(code: int, text: str) -> tuple[int, dict, bytes]:
        return code, as_json, json.dumps({"error": text}, ensure_ascii=False).encode()

    if mission not in config["missions"]:
        return error(404, f"mission « {mission} » inconnue")
    refused = access.check(config, mission, user, write=False, action="pull")
    if refused:
        return error(403, refused)
    found = Branch(config, mission, branch)
    try:
        if not rest:
            body = {"mission": config["missions"][mission].get("title", mission), "branch": branch,
                    "folder": config["missions"][mission].get("folder", "."), "files": found.files()}
            return 200, as_json, json.dumps(body, ensure_ascii=False).encode()
        if rest == ["raw"]:
            path = query.get("path", [""])[0]
            data = found.read(path)
            if data is None:
                return error(404, f"« {path} » absent de la branche {branch}")
            kind = mimetypes.guess_type(path)[0] or "application/octet-stream"
            return 200, {"Content-Type": kind}, data
    except (OSError, ValueError) as failure:
        return error(502, f"dépôt illisible : {failure}")
    return error(404, "chemin inconnu")
