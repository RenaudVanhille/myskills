"""Petites mises en forme de texte communes aux scripts (copie faite par scripts/build.py)."""
from __future__ import annotations

import difflib
import re
import urllib.parse
from pathlib import Path

# Lien Markdown qu'un journal de workflow pose sur un identifiant d'exigence dans un livrable :
# [EF-001](vault/Projets/X/Exigences/EF-001.md).
NOTE_LINK = re.compile(r"\[([^\]\n]+)\]\(([^)\s]+\.md)\)")


def unlink_notes(text: str) -> str:
    """Texte sans les liens posés sur les identifiants d'exigence (journal.py, skill decision-log) : pour
    l'export d'un livrable et pour son empreinte, qui ne dépend pas de ces liens."""
    def plain(match: re.Match) -> str:
        parts = urllib.parse.unquote(match.group(2)).split("/")
        linked = len(parts) > 1 and parts[-2] == "Exigences" and parts[-1] == match.group(1) + ".md"
        return match.group(1) if linked else match.group(0)
    return NOTE_LINK.sub(plain, text) if "](" in text else text


def cell(text, bar: str = "\\|") -> str:
    """Texte sur une ligne pour une cellule de tableau Markdown, barre verticale échappée."""
    return str(text).replace("|", bar).replace("\n", " ")


def slash_cell(text) -> str:
    """Comme cell, la barre verticale remplacée par une barre oblique."""
    return cell(text, "/")


def near(value, choices, n: int = 1) -> str:
    """Suite d'un message d'erreur qui propose les valeurs proches : « ; vouliez-vous « x » ? », sinon vide."""
    found = difflib.get_close_matches(str(value), [str(c) for c in choices], n=n, cutoff=0.6)
    return f" ; vouliez-vous « {' » ou « '.join(found)} » ?" if found else ""


# Dossier des fichiers machine d'une mission (JSON, CSV...) : les documents lisibles produits à partir d'eux
# (Markdown, schémas, images, classeurs) vont à la racine du workflow, à côté de journal.md.
DATA_DIR = "donnees"
READABLE = {".md", ".drawio", ".png", ".svg", ".xlsx", ".html", ".pptx", ".docx", ".pdf", ".excalidraw", ".canvas"}


def readable_dir(folder: Path) -> Path:
    """Dossier des documents lisibles écrits à partir de fichiers de folder : le parent de donnees/, sinon folder."""
    return folder.parent if folder.name == DATA_DIR else folder


def beside(path: Path) -> Path:
    """Chemin de sortie d'un document : un format lisible prévu dans donnees/ remonte à la racine du workflow."""
    return readable_dir(path.parent) / path.name if path.suffix.lower() in READABLE else path


def data_file(folder: Path, name: str) -> Path:
    """Fichier machine d'un workflow, cité avec ou sans donnees/ : là où il est (donnees/ d'abord, puis la racine
    d'un workflow ouvert avant ce rangement), sinon là où il doit être écrit."""
    bare = name.removeprefix(DATA_DIR + "/")
    for path in (folder / DATA_DIR / bare, folder / bare):
        if path.exists():
            return path
    return folder / DATA_DIR / bare if (folder / DATA_DIR).is_dir() or bare != name else folder / bare


def from_data(base: Path, relative: str | Path) -> Path:
    """Chemin cité dans un fichier de base (son dossier) : depuis donnees/, ce qui n'y est pas (sources/, schemas/,
    pages/...) se lit à la racine du workflow."""
    path = base / relative
    if base.name == DATA_DIR and not path.exists() and (base.parent / relative).exists():
        return base.parent / relative
    return path


# Numérotation des exigences que le catalogue attribue lui-même (requirements-catalog) : EF-001 fonctionnelle,
# préfixe de sa catégorie pour une non fonctionnelle (SECU-01, PERF-01...). ENF- reste celui de la catégorie
# « autre » et des catalogues numérotés avant ces préfixes. Un identifiant repris des documents ne change pas.
NFR_PREFIXES = {"performance": "PERF", "disponibilite": "DISP", "securite": "SECU", "conformite": "CONF",
                "exploitabilite": "EXPL", "maintenabilite": "MAIN", "evolutivite": "EVOL",
                "interoperabilite": "INTE", "utilisabilite": "UTIL", "portabilite": "PORT", "cout": "COUT",
                "autre": "ENF"}
GENERATED_ID = re.compile(r"^(EF|" + "|".join(NFR_PREFIXES.values()) + r")-\d{2,3}$")


def generated_id(prefix: str, number: int) -> str:
    """EF-001 (fonctionnelle, trois chiffres comme avant) ; SECU-01 (non fonctionnelle, deux chiffres au moins)."""
    return f"{prefix}-{number:03d}" if prefix == "EF" else f"{prefix}-{number:02d}"


def requirement_nature(req: dict) -> str | None:
    """fonctionnelle ou non-fonctionnelle : champ nature, sinon préfixe de numérotation (EF-, ENF-, SECU-...)."""
    if req.get("nature"):
        return req["nature"]
    if not GENERATED_ID.match(str(req.get("id", ""))):
        return None
    return "fonctionnelle" if req["id"].startswith("EF-") else "non-fonctionnelle"
