"""Emplacements des outils locaux (draw.io Desktop, LibreOffice, navigateur) et du
cache de myskills, sous Windows, macOS et Linux.

Source : shared/scripts/local_tools.py, copiée dans scripts/lib/ des skills qui
lancent ces outils par scripts/build.py. Ne modifiez pas les copies.
"""

import os
import shutil
from pathlib import Path

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
