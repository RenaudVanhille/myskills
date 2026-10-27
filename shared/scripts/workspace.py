"""Espace de travail : un répertoire = une mission, avec son vault Obsidian unique.

La racine d'une mission porte `mission.json` (shared/schemas/mission.schema.json),
écrit par `mission.py init` (skill mission-workspace). Un script la trouve en
remontant depuis les fichiers qu'il reçoit : le modèle n'a plus à redonner le
vault, le dossier des notes ni les dépôts de code à chaque appel.

    find(Path("exigences.json"))             -> racine de la mission ou None
    load(racine)                             -> (mission, erreurs)
    vault_target(vault, folder, [entrées])   -> (vault, dossier des notes, erreurs)
    repos(racine, mission)                   -> dépôts, chemins résolus
    inside(racine, chemin)                   -> le chemin reste dans la mission

Cloisonnement : dans une mission, un script n'écrit que dans le vault de la
mission ; un --vault qui en désigne un autre est refusé.

Source : shared/scripts/workspace.py, copiée dans scripts/lib/ des skills qui
lisent ou écrivent le vault par scripts/build.py. Ne modifiez pas les copies.
"""

import json
from pathlib import Path

from spec_schema import check

MISSION = "mission.json"
STATE = "workflow.json"
DEFAULTS = {"vault": "vault", "documents": "documents"}
WORKFLOWS = {"avant-vente": "architecture", "revue": "revue-dossier"}
_HERE = Path(__file__).resolve().parent
_SCHEMA = next((p for p in (_HERE / "mission.schema.json", _HERE.parent / "schemas" / "mission.schema.json")
                if p.is_file()), None)


def schema() -> dict:
    return json.loads(_SCHEMA.read_text(encoding="utf-8"))


def find(*starts) -> Path | None:
    """Racine de la mission qui contient le premier chemin donné (fichier ou dossier), sinon None."""
    for start in starts:
        if not start:
            continue
        path = Path(start).resolve()
        if not path.is_dir():
            path = path.parent
        for folder in (path, *path.parents):
            if (folder / MISSION).is_file():
                return folder
    return None


def load(root: Path) -> tuple[dict | None, list[str]]:
    """mission.json validé contre son schéma ; ses chemins doivent rester dans la mission."""
    path = Path(root) / MISSION
    try:
        mission = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return None, [f"{MISSION} illisible : {error}"]
    errors = [f"{MISSION} : {e}" for e in check(mission, schema())]
    if errors:
        return None, errors
    paths = [("vault", mission.get("vault")), ("documents", mission.get("documents"))]
    paths += [(f"workflows/{i}/folder", w.get("folder")) for i, w in enumerate(mission.get("workflows", []))]
    paths += [(f"repos/{i}/path", r.get("path")) for i, r in enumerate(mission.get("repos", []))]
    paths += [(f"references/{k}", v) for k, v in mission.get("references", {}).items()]
    errors = [f"{MISSION} : {where} : « {value} » sort de la mission" for where, value in paths
              if value and not inside(root, Path(root) / value)]
    return (None, errors) if errors else (mission, [])


def inside(root: Path, path: Path) -> bool:
    try:
        Path(path).resolve().relative_to(Path(root).resolve())
        return True
    except ValueError:
        return False


def path_of(root: Path, mission: dict, key: str) -> Path:
    return Path(root) / mission.get(key, DEFAULTS[key])


def workflows(mission: dict) -> list[dict]:
    """Workflows déclarés, ou celui de la nature de la mission, à la racine."""
    return [{"definition": w["definition"], "folder": w.get("folder", ".")}
            for w in mission.get("workflows") or [{"definition": WORKFLOWS[mission["nature"]]}]]


def repos(root: Path, mission: dict) -> list[dict]:
    """Dépôts de la mission, avec `root` absolu (défaut : code/<name>)."""
    return [{**r, "root": str((Path(root) / r.get("path", f"code/{r['name']}")).resolve())}
            for r in mission.get("repos", [])]


def workflow_folder(starts, root: Path, vault: Path) -> str | None:
    """Dossier des notes du workflow le plus proche des entrées, s'il écrit dans ce vault."""
    for start in starts:
        if not start:
            continue
        path = Path(start).resolve()
        path = path if path.is_dir() else path.parent
        for folder in (path, *path.parents):
            state = folder / STATE
            if state.is_file():
                try:
                    memory = json.loads(state.read_text(encoding="utf-8")).get("memory") or {}
                except (OSError, ValueError):
                    memory = {}
                if memory.get("vault") and Path(memory["vault"]).resolve() == Path(vault).resolve():
                    return memory.get("folder")
                break
            if folder == Path(root).resolve():
                break
    return None


def vault_target(vault, folder, starts, default_folder: str | None = "Mission") -> tuple:
    """Vault et dossier des notes d'un script : ceux de la mission quand --vault n'est pas donné
    (dossier du workflow des entrées, sinon default_folder) ; hors mission, inchangés.
    Erreur si --vault désigne un autre vault que celui de la mission."""
    root = find(*starts)
    if root is None:
        return vault, folder, []
    mission, errors = load(root)
    if errors:
        return vault, folder, errors
    own = path_of(root, mission, "vault")
    if vault is None:
        if not own.is_dir():
            return None, folder, []
        vault = own
    elif Path(vault).resolve() != own.resolve():
        return vault, folder, [f"--vault : {vault} n'est pas le vault de la mission « {mission['name']} » ({own}) : "
                               "une mission n'écrit que dans son vault"]
    if folder is None:
        folder = workflow_folder(starts, root, vault) or default_folder
    return Path(vault), folder, []
