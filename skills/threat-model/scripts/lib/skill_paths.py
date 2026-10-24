"""Accès aux scripts d'un autre skill de myskills, installé à côté.

Un script n'appelle un autre skill que par ces fonctions, et seulement si le
champ `requires` de son contract.json le déclare (vérifié par le cas
`regles` de tests/run.py) : les dépendances entre skills restent visibles
dans les contrats, CATALOG.md et catalog.json, jamais cachées dans un chemin.

    find_script("drawio-diagram", "check_drawio.py")   -> Path ou None
    load_module("drawio-diagram", "check_drawio.py")   -> module ou None
    schema_of("requirements-catalog", "req_build.py")  -> schéma d'entrée ou None
    absent("drawio-diagram", "check_drawio.py")        -> message à mettre dans le rapport

Source : shared/scripts/skill_paths.py, copiée dans scripts/lib/ des skills
qui ont un champ `requires` par scripts/build.py. Ne modifiez pas les copies.
"""

import importlib.util
import json
import sys
from pathlib import Path

# skills/<skill>/scripts/lib/skill_paths.py -> skills/
SKILLS = Path(__file__).resolve().parents[3]


def find_script(skill: str, script: str) -> Path | None:
    """Chemin du script d'un skill installé à côté, ou None s'il manque."""
    path = SKILLS / skill / "scripts" / script
    return path if path.is_file() else None


def load_module(skill: str, script: str):
    """Module Python du script (importé une fois), ou None si le skill manque."""
    path = find_script(skill, script)
    if path is None:
        return None
    name = path.stem
    if name in sys.modules and getattr(sys.modules[name], "__file__", None) == str(path):
        return sys.modules[name]
    # Le script importe ses voisins (lib/, autres scripts du skill) par son propre dossier.
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def schema_of(skill: str, script: str) -> dict | None:
    """Schéma d'entrée du script, lu dans le contract.json de son skill, ou None."""
    contract = SKILLS / skill / "contract.json"
    if find_script(skill, script) is None or not contract.is_file():
        return None
    for entry in json.loads(contract.read_text(encoding="utf-8")).get("scripts", []):
        if entry["name"] == script:
            return (entry.get("input") or {}).get("schema")
    return None


def absent(skill: str, script: str) -> str:
    """Message court pour le rapport quand le skill requis n'est pas installé."""
    return f"{script} introuvable : installez aussi le skill {skill} (myskills)"
