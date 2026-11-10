"""Constantes et mises en forme communes au chiffrage (estimate_build.py)."""
from __future__ import annotations

import difflib
import unicodedata


PHASES = {"cadrage": "Cadrage", "conception": "Conception", "realisation": "Réalisation",
          "integration": "Intégration", "tests": "Tests et recette", "deploiement": "Déploiement",
          "migration": "Reprise de données", "conduite-changement": "Conduite du changement",
          "pilotage": "Pilotage"}


COMPLEXITY = {"faible": "Faible", "moyenne": "Moyenne", "elevee": "Élevée", "tres-elevee": "Très élevée"}


SIZES = ((5, "faible"), (15, "moyenne"), (40, "elevee"))  # jours espérés d'une tâche : complexité déduite


QUALIFIED_KINDS = ("cloud", "service")  # lignes soumises aux qualifications exigées


# Seuils des points à challenger, à calibrer : remplacés par la section challenge des abaques de
# l'utilisateur ou de la mission (shared/schemas/abaques.schema.json, workspace.abaques).
CHALLENGE = {"max_margin": 35, "realisation_min_share": 0.4, "max_lot_days": 40, "similarity": 0.8}


BUILD_PHASES = ("realisation", "integration")


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def money(value: float, currency: str) -> str:
    return f"{value:,.0f}".replace(",", " ") + f" {currency}"


def pct(share: float) -> str:
    """Part (0 à 1) en pourcentage, à la française."""
    return f"{share * 100:.0f} %"


def days(value: float) -> str:
    return f"{value:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0")


def hint(value: str, choices) -> str:
    close = difflib.get_close_matches(value, list(choices), n=1, cutoff=0.6)
    return f" ; vouliez-vous « {close[0]} » ?" if close else f" (connus : {', '.join(choices)})"


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()
