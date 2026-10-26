# /// script
# requires-python = ">=3.10"
# ///
"""Installe et synchronise skills et agents pour Claude Code, GitHub Copilot,
OpenCode, Kiro et Hermes, en global (dossier personnel) ou dans un projet.

Usage :
    uv run scripts/install.py sync [--global | --project DIR] [--tools claude,copilot,opencode,kiro,hermes]
                                   [--repo OWNER/NOM] [--ref BRANCHE] [--source DIR|ZIP] [--models FICHIER]
                                   [--force] [--dry-run]
    uv run scripts/install.py status [--global | --project DIR] [--offline]
    uv run scripts/install.py [--project DIR | --global] [--tools opencode,kiro,hermes] [--models FICHIER] [--dry-run]
    uv run scripts/install.py --schema

sync : télécharge la dernière version du dépôt GitHub (archive de l'API,
authentifiée par MYSKILLS_TOKEN, GH_TOKEN, GITHUB_TOKEN, `gh auth token` ou,
à défaut, un jeton demandé dans le terminal) dans ~/.myskills/cache, ou
prend une copie locale (--source : dossier, clone git ou « Download ZIP »),
installe pour les outils ciblés et retire ce qu'une synchro précédente
avait installé et qui n'existe plus. Portée globale par défaut ; outils par défaut : ceux de la synchro précédente, sinon ceux
détectés. Rien n'est réécrit si la version, les outils et les modèles n'ont
pas changé (--force pour réinstaller). L'état est gardé dans
~/.myskills/state.json (global) ou <projet>/.myskills.json, avec une copie
de ce script dans ~/.myskills/install.py pour les synchros suivantes.

status : ce qui est installé, fichiers manquants et, sauf --offline,
version disponible sur GitHub.

Sans commande : installation depuis ce dépôt (projet courant par défaut,
OpenCode, Kiro et Hermes), comme sync --source.

--models : JSON des modèles de votre abonnement, par outil puis par niveau,
prioritaire sur shared/models.json (schéma : --schema), par exemple
{"opencode": {"simple": "anthropic/claude-haiku-4-5"}, "kiro": {"moyen": "claude-sonnet-4.6"}}.
Kiro n'a pas de modèle de repli : un identifiant absent de son service fait
échouer l'agent (liste : /model dans Kiro). Les modèles sont gardés dans
l'état et repris aux synchros suivantes.

Rapport JSON sur la sortie standard (shared/schemas/install-report.schema.json) ;
code 0 succès, 1 erreur.
"""

import argparse
import datetime
import difflib
import getpass
import hashlib
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
TOOLS = ("claude", "copilot", "opencode", "kiro", "hermes")
LEGACY_TOOLS = "opencode,kiro,hermes"
DEFAULT_REPO = "RenaudVanhille/myskills"
API = "https://api.github.com"
# Indices qu'un outil est présent sur le poste : commandes, puis dossier de configuration.
DETECT = {"claude": (("claude",), ".claude"), "copilot": (("copilot",), ".copilot"),
          "opencode": (("opencode",), ".config/opencode"), "kiro": (("kiro-cli", "kiro"), ".kiro"),
          "hermes": (("hermes",), ".hermes")}


class Failure(Exception):
    """Erreur qui arrête la commande : elle va dans `errors` du rapport."""


def home() -> Path:
    return Path.home()


def state_dir() -> Path:
    return home() / ".myskills"


def state_path(global_: bool, root: Path) -> Path:
    return state_dir() / "state.json" if global_ else root / ".myskills.json"


def read_state(path: Path, warnings: list[str]) -> dict:
    if not path.is_file():
        return {}
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        warnings.append(f"état illisible {path} ({error}) : ignoré")
        return {}
    if not isinstance(state, dict) or not isinstance(state.get("tools"), dict):
        warnings.append(f"état {path} sans liste d'outils : ignoré")
        return {}
    return state


def emit(report: dict) -> int:
    report.setdefault("errors", [])
    report.setdefault("warnings", [])
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


def parse_tools(value: str) -> list[str]:
    tools, bad = [], []
    for tool in (t.strip() for t in value.split(",")):
        if not tool:
            continue
        if tool not in TOOLS:
            close = difflib.get_close_matches(tool, TOOLS, n=1, cutoff=0.6)
            bad.append(f"--tools : outil inconnu « {tool} »"
                       + (f" ; vouliez-vous « {close[0]} » ?" if close else f" (permis : {', '.join(TOOLS)})"))
        elif tool not in tools:
            tools.append(tool)
    if bad:
        raise Failure("\n".join(bad))
    if not tools:
        raise Failure(f"--tools : aucun outil (permis : {', '.join(TOOLS)})")
    return tools


def detect_tools() -> list[str]:
    return [tool for tool, (commands, folder) in DETECT.items()
            if any(shutil.which(c) for c in commands) or (home() / folder).is_dir()]


# ---------------------------------------------------------------- GitHub

TOKEN: dict[str, str | None] = {}


def token() -> str | None:
    """Jeton GitHub : variables d'environnement, puis `gh auth token` si gh est installé."""
    if "value" in TOKEN:
        return TOKEN["value"]
    TOKEN["value"] = None
    for name in ("MYSKILLS_TOKEN", "GH_TOKEN", "GITHUB_TOKEN"):
        if os.environ.get(name):
            TOKEN["value"] = os.environ[name]
            return TOKEN["value"]
    if shutil.which("gh"):
        try:
            result = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=20)
            if result.returncode == 0 and result.stdout.strip():
                TOKEN["value"] = result.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return TOKEN["value"]


def ask_token() -> str | None:
    """Sans gh ni variable : demande le jeton dans le terminal (saisie masquée, jamais enregistré)."""
    if not sys.stdin.isatty():
        return None
    value = getpass.getpass("Jeton GitHub (lecture du dépôt myskills, non enregistré) : ").strip()
    TOKEN["value"] = value or None
    return TOKEN["value"]


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def http_get(url: str, accept: str, auth: str | None) -> bytes:
    """GET sur l'API GitHub ; une redirection (archive) est suivie sans le jeton."""
    headers = {"Accept": accept, "User-Agent": "myskills-install", "X-GitHub-Api-Version": "2022-11-28"}
    if auth:
        headers["Authorization"] = f"Bearer {auth}"
    opener = urllib.request.build_opener(NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=60) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        if error.code in (301, 302, 303, 307, 308) and error.headers.get("Location"):
            request = urllib.request.Request(error.headers["Location"], headers={"User-Agent": "myskills-install"})
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.read()
        if error.code in (401, 403, 404) and not auth and ask_token():
            return http_get(url, accept, TOKEN["value"])
        if error.code in (401, 403, 404):
            hint = ("jeton refusé ou sans accès au dépôt" if auth else
                    "dépôt privé ou introuvable et aucun jeton : définissez MYSKILLS_TOKEN (jeton avec "
                    "accès en lecture au dépôt), lancez `gh auth login`, ou passez une archive "
                    "téléchargée depuis GitHub avec --source myskills-main.zip")
            raise Failure(f"GitHub {error.code} sur {url} : {hint}") from None
        raise Failure(f"GitHub {error.code} sur {url}") from None
    except (urllib.error.URLError, OSError) as error:
        raise Failure(f"GitHub injoignable ({url}) : {getattr(error, 'reason', error)}") from None


def remote_sha(repo: str, ref: str) -> str:
    sha = http_get(f"{API}/repos/{repo}/commits/{ref}", "application/vnd.github.sha", token()).decode().strip()
    if len(sha) != 40:
        raise Failure(f"référence « {ref} » introuvable dans {repo}")
    return sha


def download(repo: str, sha: str) -> Path:
    """Archive du commit dans ~/.myskills/cache/<sha>."""
    cache = state_dir() / "cache"
    target = cache / sha
    if (target / "scripts" / "install.py").is_file():
        return target
    data = http_get(f"{API}/repos/{repo}/tarball/{sha}", "application/vnd.github+json", token())
    partial = cache / f"{sha}.partial"
    shutil.rmtree(partial, ignore_errors=True)
    partial.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as archive:
        for member in archive.getmembers():
            parts = Path(member.name).parts[1:]  # dossier racine <owner>-<repo>-<sha>/
            if not parts or ".." in parts or not (member.isfile() or member.isdir()):
                continue
            path = partial.joinpath(*parts)
            if member.isdir():
                path.mkdir(parents=True, exist_ok=True)
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(archive.extractfile(member).read())
    partial.rename(target)
    return target


def unzip(archive: Path) -> Path:
    """Archive « Download ZIP » de GitHub, extraite dans ~/.myskills/cache/zip (remplacée à chaque fois)."""
    target = state_dir() / "cache" / "zip"
    shutil.rmtree(target, ignore_errors=True)
    try:
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                parts = Path(member.filename).parts
                if not parts or member.is_dir() or ".." in parts or Path(member.filename).is_absolute():
                    continue
                path = target.joinpath(*parts)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(bundle.read(member))
    except (OSError, zipfile.BadZipFile) as error:
        raise Failure(f"--source : archive illisible {archive} ({error})") from None
    found = [p.parent.parent for p in target.glob("*/scripts/install.py")] + \
        [p.parent.parent for p in target.glob("scripts/install.py")]
    if not found:
        raise Failure(f"--source : {archive} ne contient pas le dépôt myskills (scripts/install.py)")
    return found[0]


# ---------------------------------------------------------------- installation

def local_version(source: Path) -> str:
    """Empreinte du contenu installé depuis un dossier local (skills, agents, modèles)."""
    digest = hashlib.sha256()
    files = [p for d in ("skills", "src/agents") for p in (source / d).rglob("*") if p.is_file()]
    for path in sorted(files + [source / "shared" / "models.json"]):
        if "__pycache__" in path.parts:
            continue
        digest.update(path.relative_to(source).as_posix().encode())
        digest.update(path.read_bytes())
    return "local-" + digest.hexdigest()[:12]


def layout(tool: str, global_: bool, root: Path, tools: list[str]) -> dict:
    """Dossiers des skills et des agents de l'outil, nom des fichiers agents et format."""
    if tool == "claude":
        base = root / ".claude"
        return {"skills": base / "skills", "agents": base / "agents", "suffix": ".md"}
    if tool == "copilot":
        if global_:
            base = root / ".copilot"
            return {"skills": base / "skills", "agents": base / "agents", "suffix": ".agent.md"}
        # En projet, Copilot lit aussi .claude/skills : pas de seconde copie si Claude est ciblé.
        skills = None if "claude" in tools else root / ".github" / "skills"
        return {"skills": skills, "agents": root / ".github" / "agents", "suffix": ".agent.md"}
    if tool == "opencode":
        base = root / ".config" / "opencode" if global_ else root / ".opencode"
        return {"skills": base / "skills", "agents": base / "agents", "suffix": ".md"}
    if tool == "kiro":
        return {"skills": root / ".kiro" / "skills", "agents": root / ".kiro" / "agents", "suffix": ".md",
                "skills_ref": "~/.kiro/skills" if global_ else ".kiro/skills"}
    # Hermes n'a pas d'agents : chaque agent y devient un skill.
    skills = root / ".hermes" / "skills"
    return {"skills": skills, "agents": skills, "suffix": "/SKILL.md"}


def install_tool(tool: str, where: dict, root: Path, dry: bool) -> tuple[list[str], int, int]:
    """Copie les skills et écrit les agents ; renvoie les chemins installés (relatifs à root)."""
    from agents_lib import parse_agent, render_agent, source_agents, write_text

    paths, skills, agents = [], 0, 0
    if where["skills"] is not None:
        for skill in sorted(p for p in (REPO / "skills").iterdir() if p.is_dir()):
            target = where["skills"] / skill.name
            if not dry:
                shutil.rmtree(target, ignore_errors=True)
                shutil.copytree(skill, target, ignore=shutil.ignore_patterns(".gitkeep", "__pycache__"))
            paths.append(target.relative_to(root).as_posix())
            skills += 1
    for src in source_agents():
        name = parse_agent(src)[0]["name"]
        target = (where["agents"] / name / "SKILL.md") if tool == "hermes" else where["agents"] / f"{name}{where['suffix']}"
        if not dry:
            write_text(target, render_agent(src, tool, where.get("skills_ref", ".kiro/skills")))
        paths.append((target.parent if tool == "hermes" else target).relative_to(root).as_posix())
        agents += 1
    return paths, skills, agents


def remove(root: Path, rel: str) -> None:
    path = root / rel
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink()
    # Dossiers devenus vides (.github/agents, .opencode...), sans remonter au-delà de root.
    for parent in path.parents:
        if parent == root or root not in parent.parents or not parent.is_dir() or any(parent.iterdir()):
            break
        parent.rmdir()


def load_models(path: Path | None, previous: dict) -> dict:
    """Modèles de l'abonnement : fichier --models validé contre son schéma, sinon ceux de l'état."""
    if path is None:
        return previous.get("models") or {}
    sys.path.insert(0, str(REPO / "shared" / "scripts"))
    from spec_schema import check

    try:
        models = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise Failure(f"--models : fichier illisible ({error})") from None
    errors = check(models, models_schema())
    if errors:
        raise Failure("\n".join(f"--models : {e}" for e in errors))
    return models


def models_schema() -> dict:
    return json.loads((REPO / "shared" / "schemas" / "install-models.schema.json").read_text(encoding="utf-8"))


def claude_plugin_installed() -> bool:
    path = home() / ".claude" / "plugins" / "installed_plugins.json"
    try:
        return "myskills@" in path.read_text(encoding="utf-8")
    except OSError:
        return False


def apply(args, source: dict, report: dict) -> None:
    """Installe depuis REPO pour la portée et les outils demandés, puis écrit l'état."""
    import agents_lib

    global_ = args.global_
    root = home() if global_ else args.project.resolve()
    spath = state_path(global_, root)
    previous = read_state(spath, report["warnings"])
    if args.tools:
        tools = parse_tools(args.tools)
    elif previous:
        tools = [t for t in previous["tools"] if t in TOOLS]
    else:
        tools = detect_tools()
        if not tools:
            raise Failure(f"aucun outil détecté sur ce poste : précisez --tools ({', '.join(TOOLS)})")
        report["warnings"].append(f"outils détectés : {', '.join(tools)}")
    models = load_models(args.models, previous)
    agents_lib.OVERRIDES.clear()
    agents_lib.OVERRIDES.update(models)
    report.update({"scope": "global" if global_ else "project", "root": str(root), "tools": tools,
                   "source": source, "state": str(spath)})

    old_paths = {tool: set(entry.get("paths", [])) for tool, entry in previous.get("tools", {}).items()}
    unchanged = (previous.get("source", {}).get("sha") == source["sha"] and list(previous["tools"]) == tools
                 and (previous.get("models") or {}) == models
                 and all((root / p).exists() for paths in old_paths.values() for p in paths))
    if unchanged and not args.force:
        report["changed"] = False
        report["installed"] = {t: previous["tools"][t].get("counts", {"skills": 0, "agents": 0}) for t in tools}
        return

    new_state = {"version": 1, "scope": report["scope"], "root": str(root), "source": source,
                 "installed_at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                 "models": models, "tools": {}}
    report["installed"] = {}
    for tool in tools:
        paths, skills, agents = install_tool(tool, layout(tool, global_, root, tools), root, args.dry_run)
        counts = {"skills": skills, "agents": agents}
        report["installed"][tool] = counts
        new_state["tools"][tool] = {"counts": counts, "paths": paths}
    kept = {p for entry in new_state["tools"].values() for p in entry["paths"]}
    stale = sorted({p for paths in old_paths.values() for p in paths} - kept)
    report["removed"] = len(stale)
    report["changed"] = True
    if args.dry_run:
        return
    for rel in stale:
        remove(root, rel)
    agents_lib.write_text(spath, json.dumps(new_state, ensure_ascii=False, indent=1) + "\n")
    if source["repo"]:
        # Le cache ne garde que la version installée.
        for other in (state_dir() / "cache").iterdir():
            if other.name != source["sha"]:
                shutil.rmtree(other, ignore_errors=True)
    if global_:
        # Copie autonome du script : `uv run ~/.myskills/install.py sync` pour les synchros suivantes.
        shutil.copyfile(Path(__file__), state_dir() / "install.py")

    if "hermes" in tools and not global_:
        # Hermes ne lit que ~/.hermes/skills et les dossiers de skills.external_dirs.
        report["next_steps"].append(
            f'hermes config set skills.external_dirs "{(root / ".hermes" / "skills").resolve()}" '
            "(une fois ; remplace les external_dirs déjà configurés)")
    if "claude" in tools and global_ and claude_plugin_installed():
        report["warnings"].append("le plugin myskills est aussi installé dans Claude Code : skills en double ; "
                                  "retirez-le avec /plugin uninstall myskills@myskills")
    if "copilot" in tools:
        report["next_steps"].append("si le plugin myskills est installé dans Copilot, retirez-le "
                                    "(copilot plugin uninstall myskills@myskills) pour éviter les doublons")


# ---------------------------------------------------------------- commandes

def resolve_source(args, previous: dict) -> tuple[Path, dict]:
    """Dossier source et sa version : --source, sinon GitHub (dépôt et branche de l'état par défaut)."""
    old = previous.get("source", {})
    if args.source is None and not args.repo and old.get("path") and not old.get("repo"):
        args.source = Path(old["path"])
    if args.source is not None:
        source = args.source.resolve()
        if source.suffix.lower() == ".zip" and source.is_file():
            source = unzip(source)
        if not (source / "skills").is_dir() or not (source / "scripts" / "install.py").is_file():
            raise Failure(f"--source : {source} n'est pas une copie du dépôt myskills (skills/, scripts/install.py)")
        return source, {"repo": None, "ref": None, "sha": args.sha or local_version(source), "path": str(source)}
    repo = args.repo or old.get("repo") or DEFAULT_REPO
    ref = args.ref or old.get("ref") or "main"
    sha = remote_sha(repo, ref)
    path = old.get("path") if old.get("sha") == sha and old.get("path") and Path(old["path"]).is_dir() else None
    path = Path(path) if path else (None if args.dry_run else download(repo, sha))
    return path, {"repo": repo, "ref": ref, "sha": sha, "path": str(path) if path else None}


def cmd_sync(args, report: dict) -> int | None:
    global_ = args.global_ or args.project is None
    args.global_ = global_
    root = home() if global_ else args.project.resolve()
    previous = read_state(state_path(global_, root), report["warnings"])
    source, info = resolve_source(args, previous)
    if source is None:  # --dry-run sans archive téléchargée
        report.update({"scope": "global" if global_ else "project", "root": str(root), "source": info,
                       "changed": previous.get("source", {}).get("sha") != info["sha"], "installed": {}})
        return None
    if source != REPO:
        # La version téléchargée fait l'installation avec son propre script.
        if "def cmd_sync" not in (source / "scripts" / "install.py").read_text(encoding="utf-8"):
            raise Failure(f"la version {info['sha'][:12]} ({info['ref'] or info['path']}) ne connaît pas sync : "
                          "choisissez une version plus récente (--ref)")
        command = [sys.executable, str(source / "scripts" / "install.py"), "sync", "--source", str(source),
                   "--sha", info["sha"], "--origin", json.dumps({"repo": info["repo"], "ref": info["ref"]})]
        command += ["--global"] if global_ else ["--project", str(root)]
        command += [f"--{k}={v}" for k, v in (("tools", args.tools), ("models", args.models)) if v]
        command += [flag for flag, on in (("--force", args.force), ("--dry-run", args.dry_run)) if on]
        return subprocess.run(command).returncode
    if args.origin:
        info.update(json.loads(args.origin))
    apply(args, info, report)
    return None


def cmd_status(args, report: dict) -> None:
    scopes = []
    if args.global_ or args.project is None:
        scopes.append((True, home()))
    if args.project is not None or (not args.global_ and (Path.cwd() / ".myskills.json").is_file()):
        scopes.append((False, (args.project or Path.cwd()).resolve()))
    remote = {}
    report["scopes"] = []
    for global_, root in scopes:
        spath = state_path(global_, root)
        state = read_state(spath, report["warnings"])
        entry = {"scope": "global" if global_ else "project", "root": str(root), "state": str(spath),
                 "installed": bool(state), "tools": {}}
        if state:
            source = state.get("source", {})
            entry.update({"sha": source.get("sha"), "repo": source.get("repo"), "ref": source.get("ref"),
                          "installed_at": state.get("installed_at")})
            for tool, item in state["tools"].items():
                missing = [p for p in item.get("paths", []) if not (root / p).exists()]
                entry["tools"][tool] = {**item.get("counts", {}), "missing": missing}
                if missing:
                    report["warnings"].append(f"{entry['scope']}/{tool} : {len(missing)} élément(s) manquant(s), "
                                              "relancez sync --force")
            if source.get("repo") and not args.offline:
                key = (source["repo"], source.get("ref") or "main")
                try:
                    remote[key] = remote.get(key) or remote_sha(*key)
                    entry["remote_sha"] = remote[key]
                    entry["up_to_date"] = remote[key] == source.get("sha")
                except Failure as error:
                    report["warnings"].append(f"version distante inconnue : {error}")
        report["scopes"].append(entry)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    argv = sys.argv[1:]
    command = argv[0] if argv and argv[0] in ("sync", "status") else "install"
    if command != "install":
        argv = argv[1:]
    parser = argparse.ArgumentParser(prog=f"install.py {command}" if command != "install" else "install.py",
                                     description=__doc__.splitlines()[0])
    where = parser.add_mutually_exclusive_group()
    where.add_argument("--project", type=Path, help="dossier du projet")
    where.add_argument("--global", dest="global_", action="store_true", help="dossier personnel")
    parser.add_argument("--schema", action="store_true", help="afficher le schéma de --models et quitter")
    if command == "status":
        parser.add_argument("--offline", action="store_true", help="ne pas interroger GitHub")
    else:
        parser.add_argument("--tools", help=f"outils ciblés, séparés par des virgules ({', '.join(TOOLS)})")
        parser.add_argument("--models", type=Path, help="JSON des modèles par outil puis par niveau")
        parser.add_argument("--dry-run", action="store_true", help="afficher sans rien écrire")
    if command == "sync":
        parser.add_argument("--repo", help=f"dépôt GitHub (défaut : {DEFAULT_REPO})")
        parser.add_argument("--ref", help="branche, tag ou commit (défaut : main)")
        parser.add_argument("--source", type=Path, help="copie locale du dépôt (dossier ou .zip de GitHub), sans téléchargement")
        parser.add_argument("--force", action="store_true", help="réinstaller même si rien n'a changé")
        parser.add_argument("--sha", help=argparse.SUPPRESS)
        parser.add_argument("--origin", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.schema:
        print(json.dumps(models_schema(), ensure_ascii=False))
        return 0
    if getattr(args, "models", None):
        args.models = args.models.resolve()

    report = {"command": command, "errors": [], "warnings": [], "next_steps": []}
    if command in ("install", "sync"):
        report["dry_run"] = args.dry_run
    try:
        if command == "status":
            cmd_status(args, report)
        elif command == "sync":
            code = cmd_sync(args, report)
            if code is not None:
                return code
        else:
            # Installation depuis ce dépôt : projet courant et OpenCode, Kiro, Hermes par défaut.
            if not args.global_:
                args.project = args.project or Path.cwd()
            args.tools = args.tools or LEGACY_TOOLS
            args.force, args.sha, args.origin = True, None, None
            apply(args, {"repo": None, "ref": None, "sha": local_version(REPO), "path": str(REPO)}, report)
    except Failure as error:
        report["errors"] += str(error).splitlines()
    except ModuleNotFoundError as error:
        report["errors"].append(f"{error.name} introuvable : lancez ce script depuis une copie complète du dépôt "
                                "ou utilisez la commande sync")
    return emit(report)


if __name__ == "__main__":
    sys.exit(main())
