"""Petites mises en forme de texte communes aux scripts (copie faite par scripts/build.py)."""
from __future__ import annotations

import difflib


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
