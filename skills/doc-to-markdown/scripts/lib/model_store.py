"""Modèles locaux (transcription...) : sources autorisées, cache vérifié, réseau coupé.

Un modèle ne vient que d'une source de model-sources.json : hôte autorisé,
révision épinglée (commit), empreinte SHA-256 de chaque fichier. Il se
télécharge une fois (doctor.py --prefetch, skill check-prerequisites) ou se
copie depuis un dossier (--models-from) ; ensuite le script qui s'en sert
coupe le réseau (forbid_network) : aucun contenu de document ne peut partir.

Cache : <cache de myskills>/models/<id>/<révision>/, ou MYSKILLS_MODELS.

Source : shared/scripts/model_store.py, copiée dans scripts/lib/ des skills
qui s'en servent par scripts/build.py. Ne modifiez pas les copies.
"""

import fnmatch
import hashlib
import ipaddress
import json
import os
import shutil
import socket
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCES = HERE / "model-sources.json"
SCHEMA = HERE / "model-sources.schema.json"
CHUNK = 1 << 20


class ModelError(Exception):
    pass


def sources() -> dict:
    """Liste des sources, validée contre son schéma."""
    from spec_schema import check

    data = json.loads(SOURCES.read_text(encoding="utf-8"))
    errors = check(data, json.loads(SCHEMA.read_text(encoding="utf-8")))
    if errors:
        raise ModelError(f"{SOURCES.name} invalide : " + " ; ".join(errors))
    return data


def models_root() -> Path:
    if os.environ.get("MYSKILLS_MODELS"):
        return Path(os.environ["MYSKILLS_MODELS"])
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    root = Path(base) if base else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "myskills" / "models"


def entry(model: str) -> dict:
    models = sources()["models"]
    if model not in models:
        raise ModelError(f"modèle « {model} » inconnu ; autorisés : {', '.join(sorted(models))}")
    return models[model]


def model_dir(model: str) -> Path:
    return models_root() / model / entry(model)["source"]["revision"]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        while block := handle.read(CHUNK):
            digest.update(block)
    return digest.hexdigest()


def local_model(model: str) -> Path | None:
    """Dossier du modèle s'il est complet et vérifié ; l'empreinte n'est recalculée
    que si un fichier a changé depuis la dernière vérification."""
    folder, files = model_dir(model), entry(model)["files"]
    stamp = folder / "VERIFIED.json"
    if not all((folder / name).is_file() for name in files):
        return None
    state = {name: [(folder / name).stat().st_size, (folder / name).stat().st_mtime_ns] for name in files}
    try:
        if json.loads(stamp.read_text(encoding="utf-8")) == state:
            return folder
    except (OSError, ValueError):
        pass
    if any(sha256(folder / name) != expected for name, expected in files.items()):
        return None
    stamp.write_text(json.dumps(state), encoding="utf-8")
    return folder


def host_allowed(url: str) -> bool:
    host = urllib.parse.urlsplit(url).hostname or ""
    return urllib.parse.urlsplit(url).scheme == "https" and \
        any(fnmatch.fnmatch(host, pattern) for pattern in sources()["hosts"])


class _AllowedRedirects(urllib.request.HTTPRedirectHandler):
    """Suit une redirection seulement vers un hôte autorisé (CDN de la source)."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if not host_allowed(newurl):
            raise ModelError(f"redirection refusée vers un hôte non autorisé : {urllib.parse.urlsplit(newurl).hostname}")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def file_url(source: dict, name: str) -> str:
    if source["provider"] == "huggingface":
        return f"https://huggingface.co/{source['repo']}/resolve/{source['revision']}/{name}"
    raise ModelError(f"fournisseur inconnu : {source['provider']}")


def fetch(model: str, from_dir: Path | None = None) -> Path:
    """Télécharge (ou copie depuis from_dir) et vérifie chaque fichier du modèle."""
    found = local_model(model)
    if found:
        return found
    spec, folder = entry(model), model_dir(model)
    folder.mkdir(parents=True, exist_ok=True)
    opener = urllib.request.build_opener(_AllowedRedirects())
    for name, expected in spec["files"].items():
        target = folder / name
        if target.is_file() and sha256(target) == expected:
            continue
        part = target.with_name(target.name + ".part")
        if from_dir:
            source_file = Path(from_dir) / name
            if not source_file.is_file():
                raise ModelError(f"{model} : {name} absent de {from_dir}")
            shutil.copyfile(source_file, part)
        else:
            url = file_url(spec["source"], name)
            if not host_allowed(url):
                raise ModelError(f"hôte non autorisé : {urllib.parse.urlsplit(url).hostname}")
            try:
                with opener.open(url, timeout=60) as response, open(part, "wb") as handle:
                    shutil.copyfileobj(response, handle, CHUNK)
            except OSError as error:
                part.unlink(missing_ok=True)
                raise ModelError(f"{model} : téléchargement de {name} impossible : {error}") from error
        got = sha256(part)
        if got != expected:
            part.unlink(missing_ok=True)
            raise ModelError(f"{model} : empreinte de {name} différente de la source épinglée "
                             f"(attendu {expected[:12]}…, reçu {got[:12]}…) : fichier refusé")
        part.replace(target)
    found = local_model(model)
    if not found:
        raise ModelError(f"{model} : vérification impossible après téléchargement")
    return found


def _local(address) -> bool:
    if not isinstance(address, tuple):
        return True  # socket Unix
    try:
        return ipaddress.ip_address(address[0]).is_loopback
    except ValueError:
        return address[0] == "localhost"


def forbid_network() -> None:
    """Coupe toute connexion réseau sortante du processus Python (boucle locale
    permise) et met les bibliothèques de modèles en mode hors ligne."""
    for name in ("HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE", "HF_DATASETS_OFFLINE", "HF_HUB_DISABLE_TELEMETRY",
                 "DO_NOT_TRACK", "MYSKILLS_OFFLINE"):
        os.environ[name] = "1"
    # Pas de proxy : un proxy local (boucle locale permise) laisserait sortir les données.
    for name in list(os.environ):
        if name.lower() in ("http_proxy", "https_proxy", "all_proxy", "ftp_proxy"):
            del os.environ[name]
    os.environ["NO_PROXY"] = os.environ["no_proxy"] = "*"
    urllib.request.getproxies = dict
    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def connect(self, address):
        if not _local(address):
            raise ConnectionRefusedError(f"réseau coupé par myskills : connexion vers {address[0]} refusée")
        return original_connect(self, address)

    def connect_ex(self, address):
        if not _local(address):
            raise ConnectionRefusedError(f"réseau coupé par myskills : connexion vers {address[0]} refusée")
        return original_connect_ex(self, address)

    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
