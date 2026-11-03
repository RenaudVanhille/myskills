"""Modèles locaux (transcription...) : sources autorisées, cache vérifié, flux réseau filtrés.

Un modèle ne vient que d'une source de model-sources.json : hôte autorisé,
révision épinglée (commit), empreinte SHA-256 de chaque fichier. Il se
télécharge une fois (doctor.py --prefetch, skill check-prerequisites) ou se
copie depuis un dossier (--models-from). Un script qui traite des documents
appelle guard_network() : seuls les hôtes identifiés (model-sources.json,
MYSKILLS_ALLOWED_HOSTS), la machine et le proxy restent joignables ; tout
autre flux est refusé et listé dans son rapport.

Pendant un run, rien ne se télécharge : require() rend le dossier vérifié ou
dit comment préparer la machine, hub_offline() coupe les téléchargements de
huggingface_hub et transformers.

Cache : <cache de myskills>/models/<id>/<révision>/, ou MYSKILLS_MODELS.

Source : shared/scripts/model_store.py, copiée par scripts/build.py dans le
seul skill check-prerequisites (scripts/lib/) ; les autres skills le chargent
par skill_paths.require_module, déclaré dans requires. Ne modifiez pas la copie.
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
if not SOURCES.is_file():  # source du dépôt (shared/scripts/), pas une copie dans lib/
    SOURCES, SCHEMA = HERE.parent / "model-sources.json", HERE.parent / "schemas" / "model-sources.schema.json"
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
        target.parent.mkdir(parents=True, exist_ok=True)
        part = target.with_name(target.name + ".part")
        if from_dir:
            # Copie du cache (<id>/<révision>/...), dossier du modèle (<id>/...) ou fichiers à plat.
            candidates = [Path(from_dir) / model / spec["source"]["revision"] / name,
                          Path(from_dir) / model / name, Path(from_dir) / name]
            source_file = next((c for c in candidates if c.is_file()), None)
            if source_file is None:
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


def require(model: str) -> Path:
    """Dossier vérifié du modèle, pour un run : rien n'est téléchargé pendant un
    traitement. Absent ou altéré, ModelError dit comment le préparer."""
    found = local_model(model)
    if found is None:
        raise ModelError(f"modèle {model} absent du cache ou altéré : préparez la machine avant le run avec "
                         "uv run scripts/doctor.py extraction --prefetch (skill check-prerequisites), "
                         "ou --models-from DOSSIER depuis une copie")
    return found


def hub_offline() -> None:
    """Interdit à huggingface_hub et transformers tout téléchargement dans ce
    processus (et ses enfants) : les modèles viennent du cache vérifié."""
    os.environ["HF_HUB_OFFLINE"] = os.environ["TRANSFORMERS_OFFLINE"] = "1"


def linked_tree(name: str, layout: dict[str, str]) -> Path:
    """Arborescence <cache>/<name>/<dossier>/ attendue par une bibliothèque
    (Docling : un dossier par dépôt), faite de liens physiques vers les modèles
    vérifiés (copie si le système de fichiers refuse les liens). `layout` donne,
    pour chaque dossier, l'identifiant du modèle."""
    root = models_root() / name
    for folder, model in layout.items():
        source = require(model)
        for file in entry(model)["files"]:
            target = root / folder / file
            if target.is_file() and target.stat().st_size == (source / file).stat().st_size:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.unlink(missing_ok=True)
            try:
                os.link(source / file, target)
            except OSError:
                shutil.copyfile(source / file, target)
    return root


# Checkpoints Laya utilisés par Router : anglais (racine du dépôt) et multilingue.
LAYA_MODEL = "laya"
LAYA_CHECKPOINTS = {"english": None, "multilingual": "multilingual"}


def laya_models() -> dict:
    """Argument `models` de laya.Router : les checkpoints du cache vérifié, sans
    téléchargement (ModelError s'il manque)."""
    folder = str(require(LAYA_MODEL))
    hub_offline()
    return {name: (folder, sub) for name, sub in LAYA_CHECKPOINTS.items()}


# Flux refusés depuis guard_network(), pour le rapport du script.
BLOCKED: list[str] = []


def _ip(value: str):
    try:
        return ipaddress.ip_address(value.split("%")[0])
    except ValueError:
        return None


def allowed_hosts() -> list[str]:
    """Hôtes joignables : ceux de model-sources.json, plus MYSKILLS_ALLOWED_HOSTS
    (motifs séparés par des virgules)."""
    extra = [h.strip() for h in os.environ.get("MYSKILLS_ALLOWED_HOSTS", "").split(",") if h.strip()]
    return list(sources()["hosts"]) + extra


def guard_network(warnings: list[str] | None = None) -> list[str]:
    """Limite les connexions du processus aux flux identifiés : hôtes de
    model-sources.json (et MYSKILLS_ALLOWED_HOSTS), la machine elle-même et le
    proxy configuré. Toute autre destination est refusée, notée dans BLOCKED et,
    si `warnings` est donnée (celle du rapport), signalée dans cette liste.
    Couvre le code Python (sockets, résolution de noms, tunnels de proxy
    http.client) ; pas une bibliothèque native qui ouvrirait ses propres
    connexions."""
    import http.client

    patterns = allowed_hosts()
    proxies = {urllib.parse.urlsplit(url).hostname for url in urllib.request.getproxies().values()
               if isinstance(url, str) and "://" in url} - {None}
    resolved: set[str] = set()
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = os.environ["DO_NOT_TRACK"] = "1"

    def host_ok(host: str) -> bool:
        host = host.strip("[]").lower().rstrip(".")
        address = _ip(host)
        if host == "localhost" or (address and address.is_loopback) or host in proxies:
            return True
        return any(fnmatch.fnmatch(host, pattern.lower()) for pattern in patterns)

    def refuse(destination: str):
        if destination not in BLOCKED:
            BLOCKED.append(destination)
            if warnings is not None:
                warnings.append(f"Flux non identifié refusé : {destination}")
        raise ConnectionRefusedError(f"flux non identifié refusé par myskills : {destination} "
                                     "(hôtes autorisés : shared/model-sources.json, MYSKILLS_ALLOWED_HOSTS)")

    original_getaddrinfo = socket.getaddrinfo

    def getaddrinfo(host, port, *args, **kwargs):
        name = host.decode() if isinstance(host, bytes) else host
        if name and not _ip(name.strip("[]")):
            if not host_ok(name):
                refuse(name)
            result = original_getaddrinfo(host, port, *args, **kwargs)
            resolved.update(str(entry[4][0]) for entry in result)
            return result
        return original_getaddrinfo(host, port, *args, **kwargs)

    def checked(address) -> None:
        if not isinstance(address, tuple):
            return  # socket Unix
        host = str(address[0])
        if host in resolved or host_ok(host):
            return
        refuse(host)

    original_connect, original_connect_ex = socket.socket.connect, socket.socket.connect_ex

    def connect(self, address):
        checked(address)
        return original_connect(self, address)

    def connect_ex(self, address):
        checked(address)
        return original_connect_ex(self, address)

    original_tunnel = http.client.HTTPConnection.set_tunnel

    def set_tunnel(self, host, *args, **kwargs):
        if not host_ok(host.rsplit(":", 1)[0] if host.count(":") == 1 else host):
            refuse(host)
        return original_tunnel(self, host, *args, **kwargs)

    socket.getaddrinfo = getaddrinfo
    socket.socket.connect, socket.socket.connect_ex = connect, connect_ex
    http.client.HTTPConnection.set_tunnel = set_tunnel
    return BLOCKED
