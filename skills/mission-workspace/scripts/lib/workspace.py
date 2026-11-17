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
    rules("chiffrage", livrées, [entrées])   -> (règles de complétude, sources, erreurs)
    abaques([entrées], fichier)              -> (abaques fusionnés, sources, erreurs)
    git_init(racine, mission)                -> dépôt git local de la mission (mission.py init)
    git_commit(racine, mission, message)     -> commit de tout ce qui a changé (journal.py, à chaque validation)

Cloisonnement : dans une mission, un script n'écrit que dans le vault de la
mission ; un --vault qui en désigne un autre est refusé.

Source : shared/scripts/workspace.py, copiée par scripts/build.py dans le seul
skill mission-workspace (scripts/lib/) ; les autres skills le chargent par
skill_paths.require_module, déclaré dans requires. Ne modifiez pas la copie.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

from spec_schema import check

MISSION = "mission.json"
STATE = "workflow.json"
DEFAULTS = {"vault": "vault", "documents": "documents"}
# Versions passées des livrables (chaque version validée, copies rangées par mission.py tidy) : dossier masqué
# dans Obsidian, jamais de copie à côté d'un livrable.
HISTORY = ".historique"
# Dépôt git local de la mission (jamais poussé) : un commit par étape validée. Hors suivi : fichiers de travail,
# verrous, état d'affichage d'Obsidian, copies rangées par tidy ; les dépôts de code de la mission s'y ajoutent.
GIT_IGNORE = [".myskills-tmp/", "_tmp/", "workflow.lock", ".myskills-vault.lock", f"{HISTORY}/", "~$*", ".~lock.*",
              ".obsidian/workspace*.json", ".trash/"]
# Auteur des commits quand git n'en a pas de configuré.
GIT_AUTHOR = ["-c", "user.name=myskills", "-c", "user.email=myskills@localhost"]
WORKFLOWS = {"avant-vente": "avant-vente", "revue": "revue-dossier"}
_HERE = Path(__file__).resolve().parent
_SCHEMA = next((p for p in (_HERE / "mission.schema.json", _HERE.parent / "schemas" / "mission.schema.json")
                if p.is_file()), None)
_RULES = next((p for p in (_HERE / "rules.schema.json", _HERE.parent / "schemas" / "rules.schema.json")
               if p.is_file()), None)
_ABAQUES = next((p for p in (_HERE / "abaques.schema.json", _HERE.parent / "schemas" / "abaques.schema.json")
                 if p.is_file()), None)
# Règles de complétude de l'utilisateur, communes à ses missions : ce fichier, ou ~/.myskills/regles.json
# (vide : aucune).
RULES_ENV = "MYSKILLS_REGLES"
# Abaques du chiffrage de l'utilisateur, communs à ses missions : ce fichier, ou ~/.myskills/abaques.json.
ABAQUES_ENV = "MYSKILLS_ABAQUES"


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


def vault_args(parser, args, starts) -> list[str]:
    """--vault et --folder d'un script qui écrit dans le vault : ceux de la mission par défaut (vault_target),
    donnés ensemble (sinon parser.error), vault existant. Rend les erreurs à mettre dans le rapport."""
    args.vault, args.folder, errors = vault_target(args.vault, args.folder, starts)
    if errors:
        return errors
    if bool(args.vault) != bool(args.folder):
        parser.error("--vault et --folder vont ensemble")
    if args.vault and not Path(args.vault).is_dir():
        return [f"--vault : dossier introuvable {args.vault}"]
    return []


def user_rules() -> Path | None:
    """Fichier des règles de complétude de l'utilisateur, s'il existe."""
    value = os.environ.get(RULES_ENV)
    path = Path(value) if value else None if value is not None else Path.home() / ".myskills" / "regles.json"
    return path if path and path.is_file() else None


def rules(kind: str, builtin: Path | None, starts=()) -> tuple[list[dict], list[str], list[str]]:
    """Règles `kind` (chiffrage, revue, principes) : celles livrées avec le skill (builtin, s'il y en a),
    puis celles de l'utilisateur, puis celles de la mission des entrées (references.regles, puis
    references.principes). Une règle de même id remplace la précédente ; {"id", "off": true} la retire.
    Renvoie (règles, fichiers lus, erreurs)."""
    files = [Path(builtin)] if builtin else []
    if user_rules():
        files.append(user_rules())
    root = find(*starts)
    if root is not None:
        mission, _ = load(root)
        for key in ("regles", "principes") if kind == "principes" else ("regles",):
            if mission and mission.get("references", {}).get(key):
                files.append(Path(root) / mission["references"][key])
    merged: dict[str, dict] = {}
    errors: list[str] = []
    schema = json.loads(_RULES.read_text(encoding="utf-8"))
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"règles {path} illisibles : {error}")
            continue
        invalid = check(data, schema)
        for index, rule in enumerate(data.get(kind, []) if isinstance(data, dict) else []):
            if isinstance(rule, dict) and isinstance(rule.get("pattern"), str):
                try:
                    re.compile(rule["pattern"])
                except re.error as error:
                    invalid.append(f"{kind}/{index}/pattern : expression invalide ({error})")
        if invalid:
            errors += [f"règles {path.name} : {e}" for e in invalid]
            continue
        for rule in data.get(kind, []):
            merged.pop(rule["id"], None)
            if not rule.get("off"):
                merged[rule["id"]] = {**rule, "file": str(path)}
    return list(merged.values()), [str(p) for p in files], errors


def user_abaques() -> Path | None:
    """Fichier des abaques de l'utilisateur, s'il existe."""
    value = os.environ.get(ABAQUES_ENV)
    path = Path(value) if value else None if value is not None else Path.home() / ".myskills" / "abaques.json"
    return path if path and path.is_file() else None


def abaques(starts=(), explicit: Path | None = None) -> tuple[dict, list[str], list[str]]:
    """Abaques du chiffrage donnés avant le lancement : ceux de l'utilisateur, puis ceux de la mission des
    entrées (references.abaques), puis le fichier explicite (--abaques). Chaque fichier est validé
    (shared/schemas/abaques.schema.json) ; une section remplace clé à clé celle d'avant.
    Renvoie (abaques fusionnés, fichiers lus, erreurs) ; aucun fichier : ({}, [], []), valeurs par défaut."""
    files = [user_abaques()] if user_abaques() else []
    root = find(*starts)
    if root is not None:
        mission, _ = load(root)
        if mission and mission.get("references", {}).get("abaques"):
            files.append(Path(root) / mission["references"]["abaques"])
    if explicit:
        files.append(Path(explicit))
    schema = json.loads(_ABAQUES.read_text(encoding="utf-8"))
    merged: dict = {}
    errors: list[str] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"abaques {path} illisibles : {error}")
            continue
        invalid = check(data, schema, schema)
        if invalid:
            errors += [f"abaques {path.name} : {e}" for e in invalid]
            continue
        for key, value in data.items():
            if key.startswith("_"):
                continue
            merged[key] = {**merged[key], **value} if isinstance(value, dict) and isinstance(merged.get(key), dict) \
                else value
    return merged, [str(p) for p in files], errors


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, encoding="utf-8",
                          errors="replace")


def has_git(root: Path) -> bool:
    """La mission a son propre dépôt git (.git à sa racine) et git est installé."""
    return (Path(root) / ".git").exists() and shutil.which("git") is not None


def _ignore(root: Path, mission: dict) -> None:
    """.gitignore de la mission : lignes de GIT_IGNORE et dépôts de code de la mission, ajoutées si absentes."""
    path = Path(root) / ".gitignore"
    lines = path.read_text(encoding="utf-8").splitlines() if path.is_file() else []
    wanted = GIT_IGNORE + [Path(r["root"]).relative_to(Path(root).resolve()).as_posix() + "/"
                           for r in repos(root, mission) if inside(root, Path(r["root"]))]
    if (Path(root) / "code").is_dir():
        wanted.append("code/")
    missing = [line for line in dict.fromkeys(wanted) if line not in lines]
    if missing:
        path.write_text("\n".join(lines + missing) + "\n", encoding="utf-8")


def git_commit(root: Path, mission: dict, message: str) -> str | None:
    """Commit local de tout ce qui a changé dans la mission (jamais poussé) ; rend son identifiant court, ou None
    sans dépôt de la mission, sans changement ou si git échoue."""
    if not has_git(root):
        return None
    _ignore(root, mission)
    if _git(root, "add", "-A").returncode != 0 or _git(root, "diff", "--cached", "--quiet").returncode == 0:
        return None
    author = [] if _git(root, "config", "user.email").stdout.strip() else GIT_AUTHOR
    if subprocess.run(["git", "-C", str(root), *author, "commit", "-q", "-m", message], capture_output=True,
                      text=True, encoding="utf-8", errors="replace").returncode != 0:
        return None
    return _git(root, "rev-parse", "--short", "HEAD").stdout.strip() or None


def git_init(root: Path, mission: dict) -> tuple[str | None, str | None]:
    """Crée le dépôt git local de la mission et son premier commit. Rend (commit, avertissement) : rien si git
    manque, ou si la mission est déjà dans un dépôt qui n'est pas le sien (il n'est pas touché)."""
    if shutil.which("git") is None:
        return None, "git introuvable : pas d'historique git de la mission (installez git : https://git-scm.com)"
    if not (Path(root) / ".git").exists():
        outer = _git(root, "rev-parse", "--show-toplevel")
        if outer.returncode == 0 and outer.stdout.strip():
            return None, f"mission dans le dépôt git {outer.stdout.strip()} : pas de dépôt propre à la mission"
        if _git(root, "init", "-q").returncode != 0:
            return None, "git init a échoué : pas d'historique git de la mission"
    return git_commit(root, mission, f"init(mission): {mission.get('name', Path(root).name)}"), None
