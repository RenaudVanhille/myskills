"""Petites mises en forme de texte communes aux scripts (copie faite par scripts/build.py)."""
from __future__ import annotations

import difflib
import re
import urllib.parse

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
