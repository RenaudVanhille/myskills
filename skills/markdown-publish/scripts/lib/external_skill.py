"""Skills installés à part, connus seulement par leur contrat d'interface.

Le contrat (`<nom>.contract.json`, copié à côté de ce module par
scripts/build.py depuis shared/external/) dit où chercher le skill, quel
script lancer et quelle version a été testée. Rien du skill n'est copié dans
myskills : s'il n'est pas installé, l'appelant reçoit la consigne
d'installation du contrat.
"""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def contract(name: str) -> dict:
    return json.loads((HERE / f"{name}.contract.json").read_text(encoding="utf-8"))


def candidates(spec: dict) -> list[Path]:
    """Dossiers possibles du skill, dans l'ordre du contrat (variable d'abord)."""
    found: list[Path] = []
    if os.environ.get(spec["locate"]["env"]):
        return [Path(os.environ[spec["locate"]["env"]]).expanduser().resolve()]
    cwd = Path.cwd().resolve()
    for pattern in spec["locate"]["folders"]:
        rel = pattern[2:]
        roots = [Path.home()] if pattern.startswith("~/") else [cwd, *cwd.parents]
        for root in roots:
            # Plusieurs versions en cache : la plus récente d'abord.
            found += sorted(root.glob(rel), key=lambda p: p.stat().st_mtime, reverse=True) if "*" in rel \
                else [root / rel]
    return found


def locate(name: str) -> tuple[dict, Path | None]:
    """(contrat, script d'entrée du skill installé, ou None)."""
    spec = contract(name)
    for folder in candidates(spec):
        entry = folder / spec["locate"]["entry"]
        if entry.is_file():
            return spec, entry
    return spec, None


def missing_message(spec: dict) -> str:
    return (f"skill {spec['skill']} introuvable (variable {spec['locate']['env']} ou dossiers d'installation "
            f"habituels) : {spec['install']}")


def version(spec: dict, entry: Path) -> tuple[str | None, str | None]:
    """(version lue, avertissement si elle diffère de la version testée)."""
    option = spec["command"].get("version")
    if not option:
        return None, None
    result = subprocess.run([sys.executable, str(entry), option], capture_output=True, text=True,
                            encoding="utf-8", errors="replace")
    match = re.search(r"(\d+)\.(\d+)(?:\.\d+)?", result.stdout + result.stderr)
    if not match:
        return None, f"{spec['skill']} : version illisible"
    got = match.group(0)
    if f"{match.group(1)}.{match.group(2)}" != spec["versions"]:
        return got, f"{spec['skill']} {got} installé, contrat écrit pour {spec['versions']}"
    return got, None
