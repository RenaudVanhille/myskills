"""Visionneuse web des fichiers d'une mission : ce que la conversation a poussé sur sa branche.

Le service la sert sous viewer.path (défaut /fichiers), derrière l'Ingress d'Open WebUI. Pas de compte à
part : chaque réponse du chat porte un lien signé (HMAC du jeton du service) qui nomme la mission, la
conversation et l'utilisateur, valable viewer.link_days jours ; ses droits de lecture sur le projet GitLab
sont revérifiés à chaque ouverture (access).

Les fichiers sont lus sur la branche poussée de la conversation, pas dans le pod de session : la page
marche aussi quand la session est arrêtée ou finie. Dépôt GitLab : API (jeton read_api du service) ;
dépôt local (dev) : git ls-tree et git show.

    GET {path}/{lien}/                page (static/viewer.html)
    GET {path}/{lien}/api/arbre       {"mission", "branch", "folder", "files": [{"path", "size"}], "backlinks"}
    GET {path}/{lien}/brut/CHEMIN     contenu brut (CSP sandbox, nosniff)
    GET {path}/_static/FICHIER        page, script, style et bibliothèques (static/vendor, fetch_vendor.py)
"""

import base64
import hashlib
import hmac
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
from urllib.parse import quote, urlparse

import access

STATIC = Path(__file__).resolve().parents[2] / "static"
DEFAULT_PATH = "/fichiers"
_cache: dict[tuple, tuple[float, object]] = {}
_lock = threading.Lock()


def settings(config: dict) -> dict | None:
    section = config.get("viewer")
    if not section or not section.get("url"):
        return None
    url = section["url"].rstrip("/")
    return {"url": url, "path": urlparse(url).path.rstrip("/") or DEFAULT_PATH, "days": section.get("link_days", 7)}


# --- liens signés --------------------------------------------------------------------------------------
def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def sign(secret: str, mission: str, chat: str, user: str | None, days: float) -> str:
    payload = _b64(json.dumps({"m": mission, "c": chat, "u": (user or "").lower(),
                               "e": int(time.time() + days * 86400)}, separators=(",", ":")).encode())
    mac = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()[:18])
    return f"{payload}.{mac}"


def verify(secret: str, token: str) -> dict | None:
    try:
        payload, mac = token.split(".", 1)
        wanted = _b64(hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()[:18])
        if not hmac.compare_digest(mac, wanted):
            return None
        data = json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except (ValueError, TypeError):
        return None
    return data if data.get("e", 0) > time.time() else None


def link(config: dict, secret: str, mission: str, chat: str, user: str | None) -> str | None:
    found = settings(config)
    if not found or not secret:
        return None
    return f"{found['url']}/{sign(secret, mission, chat, user, found['days'])}/"


# --- lecture de la branche ------------------------------------------------------------------------------
def _gitlab(config: dict, path: str, raw: bool = False):
    token = os.environ.get(config.get("access", {}).get("token_env", "GITLAB_ACCESS_TOKEN"), "")
    request = urllib.request.Request(config["access"]["api"].rstrip("/") + path, headers={"PRIVATE-TOKEN": token})
    with urllib.request.urlopen(request, timeout=20) as response:
        body = response.read()
        return (body, response.headers) if raw else json.loads(body or b"null")


class Branch:
    """Fichiers d'une branche de mission : GitLab (API) ou dépôt local (git)."""

    def __init__(self, config: dict, mission: str, branch: str):
        self.config, self.mission, self.branch = config, config["missions"][mission], branch
        repo = self.mission["repo"]
        self.local = None if "://" in repo or re.match(r"^[\w.-]+@[\w.-]+:", repo) else \
            (Path(config["_base"]) / repo).resolve()
        self.project = None if self.local else quote(access.project_of(self.mission), safe="")

    def files(self) -> list[dict]:
        key = ("arbre", self.mission["repo"], self.branch)
        with _lock:
            hit = _cache.get(key)
            if hit and time.monotonic() - hit[0] < 20:
                return hit[1]
        found = self._files()
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
                    size = meta.split()[-1]
                    files.append({"path": path, "size": int(size) if size.isdigit() else 0})
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
            files += [{"path": b["path"], "size": None} for b in batch or [] if b.get("type") == "blob"]
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
            body, _ = _gitlab(self.config, f"/projects/{self.project}/repository/files/{quote(path, safe='')}/raw"
                                           f"?ref={quote(self.branch, safe='')}", raw=True)
            return body
        except urllib.error.HTTPError:
            return None


WIKILINK = re.compile(r"!?\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")


def backlinks(branch: Branch, files: list[dict]) -> dict:
    """Notes Markdown qui citent chaque note ([[nom]]) : le panneau « Liens entrants » de la page."""
    key = ("liens", branch.mission["repo"], branch.branch, len(files))
    with _lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < 60:
            return hit[1]
    names = {}
    for f in files:
        if f["path"].endswith(".md"):
            names.setdefault(Path(f["path"]).stem.lower(), f["path"])
    found: dict[str, list[str]] = {}
    for f in files:
        if not f["path"].endswith(".md") or (f.get("size") or 0) > 1_000_000:
            continue
        text = (branch.read(f["path"]) or b"").decode("utf-8", "replace")
        for target in {m.group(1).strip().lower() for m in WIKILINK.finditer(text)}:
            target_path = names.get(Path(target).stem.lower() if target.endswith(".md") else target)
            if target_path and target_path != f["path"]:
                found.setdefault(target_path, []).append(f["path"])
    with _lock:
        _cache[key] = (time.monotonic(), found)
    return found


# --- réponses HTTP --------------------------------------------------------------------------------------
PAGE_CSP = ("default-src 'self'; img-src 'self' data: blob:; style-src 'self' 'unsafe-inline'; "
            "script-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'self'")


def static_file(name: str) -> tuple[int, dict, bytes]:
    for folder in (STATIC, STATIC / "vendor"):
        path = (folder / name).resolve()
        if path.parent == folder.resolve() and path.is_file():
            kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            return 200, {"Content-Type": kind + ("; charset=utf-8" if kind.startswith(("text/", "application/javascript")) else ""),
                         "Cache-Control": "public, max-age=3600"}, path.read_bytes()
    return 404, {"Content-Type": "text/plain; charset=utf-8"}, b"introuvable"


def handle(config: dict, secret: str, parts: list[str], branch_of) -> tuple[int, dict, bytes]:
    """parts : chemin après viewer.path. branch_of(mission, chat) -> nom de la branche de la conversation."""
    text = {"Content-Type": "text/plain; charset=utf-8"}
    if parts and parts[0] == "_static":
        return static_file("/".join(parts[1:]))
    grant = verify(secret, parts[0]) if parts else None
    if grant is None:
        return 403, text, "Lien expiré ou invalide : rouvrez-le depuis la dernière réponse du chat.".encode()
    if grant["m"] not in config["missions"]:
        return 404, text, "Mission inconnue.".encode()
    refused = access.check(config, grant["m"], grant["u"] or None, write=False, action="pull") if grant["u"] \
        else None
    if refused:
        return 403, text, refused.encode()
    branch = Branch(config, grant["m"], branch_of(grant["m"], grant["c"]))
    rest = parts[1:]
    if not rest:
        page = (STATIC / "viewer.html").read_bytes()
        return 200, {"Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": PAGE_CSP,
                     "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}, page
    if rest == ["api", "arbre"]:
        try:
            files = branch.files()
            links = backlinks(branch, files)
        except (OSError, ValueError) as error:
            return 502, text, f"Dépôt illisible : {error}".encode()
        body = {"mission": config["missions"][grant["m"]].get("title", grant["m"]), "branch": branch.branch,
                "folder": config["missions"][grant["m"]].get("folder", "."), "files": files, "backlinks": links,
                "libs": sorted(p.name for p in (STATIC / "vendor").glob("*.js"))}
        return 200, {"Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store"}, \
            json.dumps(body, ensure_ascii=False).encode()
    if rest[0] == "brut" and len(rest) > 1:
        path = "/".join(rest[1:])
        data = branch.read(path)
        if data is None:
            return 404, text, "Fichier absent de la branche.".encode()
        kind = mimetypes.guess_type(path)[0] or ("text/plain" if _is_text(data) else "application/octet-stream")
        if kind.startswith("text/") or kind in ("application/json", "image/svg+xml"):
            kind += "; charset=utf-8"
        headers = {"Content-Type": kind, "Content-Security-Policy": "sandbox", "X-Content-Type-Options": "nosniff",
                   "Cache-Control": "no-store", "Referrer-Policy": "no-referrer"}
        if kind.startswith(("text/html", "application/xhtml")):
            headers["Content-Type"] = "text/plain; charset=utf-8"  # jamais exécuté dans la page
        return 200, headers, data
    return 404, text, "Chemin inconnu.".encode()


def _is_text(data: bytes) -> bool:
    try:
        data[:4096].decode("utf-8")
        return b"\0" not in data[:4096]
    except UnicodeDecodeError:
        return False
