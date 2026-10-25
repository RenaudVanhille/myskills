"""Accès aux scripts d'un autre skill de myskills, installé à côté.

Un script n'appelle un autre skill que par ces fonctions, et seulement si le
champ `requires` de son contract.json le déclare (vérifié par le cas
`regles` de tests/run.py) : les dépendances entre skills restent visibles
dans les contrats, CATALOG.md et catalog.json, jamais cachées dans un chemin.

    find_script("drawio-diagram", "check_drawio.py")   -> Path ou None
    load_module("drawio-diagram", "check_drawio.py")   -> module ou None
    schema_of("requirements-catalog", "req_build.py")  -> schéma d'entrée ou None
    run_script("diagram-export", "export.py", [args])  -> rapport JSON du script
    export_image(Path("x.drawio"), "png")              -> résumé de l'export (diagram-export)
    absent("drawio-diagram", "check_drawio.py")        -> message à mettre dans le rapport

Source : shared/scripts/skill_paths.py, copiée dans scripts/lib/ des skills
qui ont un champ `requires` par scripts/build.py. Ne modifiez pas les copies.
"""

import importlib.util
import json
import shutil
import subprocess
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


def run_script(skill: str, script: str, args: list) -> dict:
    """Lance le script d'un autre skill (avec uv s'il est là) et rend son rapport JSON ;
    errors explique un skill absent ou un rapport illisible."""
    path = find_script(skill, script)
    if path is None:
        return {"errors": [absent(skill, script)], "warnings": []}
    runner = ["uv", "run", "--quiet"] if shutil.which("uv") else [sys.executable]
    result = subprocess.run(runner + [str(path)] + [str(a) for a in args], capture_output=True,
                            text=True, encoding="utf-8")
    try:
        return json.loads(result.stdout)
    except ValueError:
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["sans sortie"]
        return {"errors": [f"{script} : rapport illisible ({tail[0][:200]})"], "warnings": []}


def export_image(source: Path, fmt: str) -> tuple[dict, list[str]]:
    """Exporte un schéma juste construit avec diagram-export (--export d'un script de construction) :
    rend le résumé pour le rapport (outputs, warnings) et les erreurs."""
    report = run_script("diagram-export", "export.py", [source, "--format", fmt])
    results = report.get("results", [])
    summary = {"outputs": [o for r in results for o in r.get("outputs", [])],
               "warnings": [w for r in results for w in r.get("warnings", [])] + report.get("warnings", [])}
    return summary, [f"export : {e}" for e in report.get("errors", [])]
