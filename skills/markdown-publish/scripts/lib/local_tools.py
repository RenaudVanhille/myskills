"""Emplacements des outils locaux (draw.io Desktop, LibreOffice, navigateur) et du
cache de myskills, sous Windows, macOS et Linux ; bibliothèques JavaScript
téléchargées une fois, à une version fixée, et vérifiées par leur empreinte.

Hors ligne (MYSKILLS_OFFLINE=1), rien n'est téléchargé : le cache doit avoir été
rempli avant (doctor.py --prefetch, ou copie du dossier de cache).

Source : shared/scripts/local_tools.py, copiée dans scripts/lib/ des skills qui
lancent ces outils par scripts/build.py. Ne modifiez pas les copies.
"""

import base64
import hashlib
import os
import shutil
import subprocess
import tarfile
import urllib.request
from pathlib import Path

# Paquets npm rendus dans le navigateur local : version fixée et empreinte SRI du
# registre npm (dist.integrity), vérifiée avant toute extraction.
PACKAGES = {
    "mermaid": ("11.12.0", "dist/mermaid.min.js",
                "sha512-ZudVx73BwrMJfCFmSSJT84y6u5brEoV8DOItdHomNLz32uBjNrelm7mg95X7g+C6UoQH/W6mBLGDEDv73JdxBg=="),
    "@excalidraw/utils": ("0.1.7", "dist/prod/index.js",
                          "sha512-yxIemG1JiR76OOKi1+ILTWPSwZfmyKJR0a9suAh9Tb2tNFjkva5TUBBAy1lymAoLnkib+kO71v4bv6k2mqTZhA=="),
}


class PackageError(Exception):
    pass

PROGRAM_FILES = [Path(os.environ[v]) for v in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA")
                 if os.environ.get(v)]
DRAWIO_PATHS = [
    *(base / "draw.io" / "draw.io.exe" for base in PROGRAM_FILES),
    *(base / "Programs" / "draw.io" / "draw.io.exe" for base in PROGRAM_FILES),
    Path("/Applications/draw.io.app/Contents/MacOS/draw.io"),
    Path("/opt/drawio/drawio"),
]
SOFFICE_PATHS = [
    *(base / "LibreOffice" / "program" / "soffice.exe" for base in PROGRAM_FILES),
    Path("/Applications/LibreOffice.app/Contents/MacOS/soffice"),
    Path("/usr/bin/soffice"), Path("/usr/lib/libreoffice/program/soffice"),
]
BROWSER_PATHS = [
    *(base / "Microsoft" / "Edge" / "Application" / "msedge.exe" for base in PROGRAM_FILES),
    *(base / "Google" / "Chrome" / "Application" / "chrome.exe" for base in PROGRAM_FILES),
    Path("/Applications/Google Chrome.app"), Path("/Applications/Microsoft Edge.app"),
]
PLAYWRIGHT_CACHE = [
    *([Path(os.environ["PLAYWRIGHT_BROWSERS_PATH"])] if os.environ.get("PLAYWRIGHT_BROWSERS_PATH") else []),
    *(base / "ms-playwright" for base in PROGRAM_FILES),
    Path.home() / "Library" / "Caches" / "ms-playwright",
    Path.home() / ".cache" / "ms-playwright",
]


def first_command(*names: str) -> str | None:
    return next((shutil.which(n) for n in names if shutil.which(n)), None)


def drawio_binary() -> str | None:
    """draw.io Desktop : commande du PATH, sinon emplacement d'installation habituel."""
    return first_command("drawio", "draw.io") or next((str(p) for p in DRAWIO_PATHS if p.is_file()), None)


def soffice_binary() -> str | None:
    """LibreOffice (soffice)."""
    return first_command("soffice", "libreoffice") or next((str(p) for p in SOFFICE_PATHS if p.is_file()), None)


def browser_available() -> bool:
    """Un navigateur que Playwright peut piloter : MYSKILLS_BROWSER, Edge, Chrome ou Chromium."""
    custom = os.environ.get("MYSKILLS_BROWSER")
    if custom and Path(custom).exists():
        return True
    return bool(first_command("msedge", "microsoft-edge", "google-chrome", "chromium", "chrome")
                or any(p.exists() for p in BROWSER_PATHS)
                or any(p.is_dir() and any(p.glob("chromium*")) for p in PLAYWRIGHT_CACHE))


def cache_dir() -> Path:
    """Cache des bibliothèques téléchargées (Mermaid, Excalidraw, LikeC4...)."""
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    root = Path(base) if base else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "myskills"


def offline() -> bool:
    return os.environ.get("MYSKILLS_OFFLINE", "").strip().lower() in ("1", "true", "oui", "yes")


def package_dir(name: str) -> Path:
    version = PACKAGES[name][0]
    return cache_dir() / f"{name.strip('@').replace('/', '-')}-{version}"


def cached_package(name: str) -> Path | None:
    """Dossier du paquet extrait et vérifié, s'il est dans le cache."""
    root = package_dir(name)
    entry = PACKAGES[name][1]
    return root / "package" if (root / "package" / entry).is_file() and (root / "VERIFIED").is_file() else None


def integrity_ok(path: Path, integrity: str) -> bool:
    algorithm, _, expected = integrity.partition("-")
    digest = hashlib.new(algorithm, path.read_bytes()).digest()
    return base64.b64encode(digest).decode() == expected


def npm_package(name: str) -> Path:
    """Paquet npm du cache ; sinon téléchargé (npm pack, sinon le registre), vérifié, puis extrait."""
    found = cached_package(name)
    if found:
        return found
    version, _, integrity = PACKAGES[name]
    root = package_dir(name)
    if offline():
        raise PackageError(f"{name} {version} absent du cache {root.parent} (mode hors ligne) : lancez "
                           "`uv run scripts/doctor.py --prefetch` (skill check-prerequisites) sur une machine "
                           "connectée, puis copiez ce dossier")
    shutil.rmtree(root, ignore_errors=True)
    root.mkdir(parents=True, exist_ok=True)
    tgz = root / "package.tgz"
    npm = shutil.which("npm")
    if npm:
        subprocess.run([npm, "pack", f"{name}@{version}", "--pack-destination", str(root), "--silent"],
                       cwd=root, capture_output=True, timeout=300)
        packed = next((p for p in root.glob("*.tgz") if p != tgz), None)
        if packed:
            packed.replace(tgz)
    if not tgz.is_file():
        url = f"https://registry.npmjs.org/{name}/-/{name.split('/')[-1]}-{version}.tgz"
        try:
            urllib.request.urlretrieve(url, tgz)
        except OSError as error:
            raise PackageError(f"téléchargement de {name} {version} impossible : {error}") from error
    if not integrity_ok(tgz, integrity):
        shutil.rmtree(root, ignore_errors=True)
        raise PackageError(f"{name} {version} : empreinte différente de celle attendue, paquet supprimé")
    with tarfile.open(tgz) as archive:
        archive.extractall(root, filter="data") if hasattr(tarfile, "data_filter") else archive.extractall(root)
    tgz.unlink()
    (root / "VERIFIED").write_text(integrity + "\n", encoding="utf-8")
    return root / "package"
