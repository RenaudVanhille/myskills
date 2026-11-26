# /// script
# requires-python = ">=3.10"
# ///
"""Joue un tour d'une mission à distance : un message de l'utilisateur, une réponse de l'agent.

Une conversation (Open WebUI ou autre) = une mission (dépôt git, GitLab auto-hébergé) et une
branche : <branch_prefix><conversation>. Le tour, sans rien demander au modèle hors de l'agent :
1. valide la configuration (schéma du contrat) : dépôts et services joignables pris dans
   allowed_hosts seulement, aucun identifiant dans une URL ;
2. clone le dépôt de la mission ou met à jour sa copie, sur la branche de la conversation ;
3. porte de revue : « valide » ou « retour : ... » quand une seule étape est en revue est passé
   tel quel à journal.py review (skill decision-log), sans tour de modèle pour cela ;
   « /statut » rend l'état sans lancer l'agent ;
4. lance l'agent sans terminal (commande de la configuration : claude -p, opencode run...),
   modèles servis par LiteLLM ou tout point d'accès du harness, dans le dossier de la mission ;
5. fait le commit de ce qui a changé et le pousse sur la branche ;
6. lit l'état des workflows (journal.py status) : étape en revue, questions ouvertes.

Rapport JSON : réponse de l'agent (Markdown), porte de revue, fichiers changés, images,
commit, poussé ou non. Le serveur remote_server.py appelle run_turn() pour chaque message.

    uv run scripts/remote_turn.py --config remote.json --mission NOM --chat ID --message TEXTE
"""

import argparse
import base64
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import quote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
import access  # noqa: E402
from skill_paths import absent, find_script, run_script  # noqa: E402
from spec_schema import read_spec, schema_option, print_schema, validate  # noqa: E402

STATUS_WORDS = {"/statut", "/status", "statut", "status"}
END_WORDS = {"/fin", "/end"}  # fin de session : dernier push, copie de travail et contexte de l'agent effacés
VALIDATE = re.compile(r"^\s*(je\s+valide|valide[rz]?|validé|ok|go|approve[d]?)\s*[.!]?\s*$", re.I)
FEEDBACK = re.compile(r"^\s*(retour|feedback)\s*:\s*(.+)$", re.I | re.S)
URL_VARS = re.compile(r"(_URL|_BASE|_HOST|_ENDPOINT)$")
ANSWER_MAX = 20000
DEFAULT_PROMPT = (
    "Tu es lancé à distance, sans terminal : l'utilisateur écrit dans Open WebUI et ne lit que ta "
    "réponse finale. Dossier de la mission : {folder}. Reprends la mission là où son journal l'a "
    "laissée (journal.py status, skill decision-log ; agent orientation si rien n'est commencé). "
    "Ne pose aucune question interactive : à une porte de revue ou une question, arrête-toi et "
    "écris la question à la fin de ta réponse. Réponse finale courte, en Markdown, livrables cités "
    "par leur chemin relatif.{note}\n\nMessage de l'utilisateur :\n{message}")


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", text).strip("-.")[:60] or "conversation"


def host_of(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme in ("http", "https", "ssh", "git"):
        return parsed.hostname
    match = re.match(r"^[\w.-]+@([\w.-]+):", value)  # git@gitlab.local:groupe/mission.git
    return match.group(1) if match else None


def allowed(host: str, patterns: list[str]) -> bool:
    return any(host == p or (p.startswith("*.") and host.endswith(p[1:])) for p in patterns)


def check_config(config: dict, base: Path) -> list[str]:
    """Contrôles hors schéma : hôtes autorisés, pas d'identifiant dans une URL, dépôt local présent."""
    errors, hosts = [], config.get("allowed_hosts", [])
    for name, mission in config["missions"].items():
        repo = mission["repo"]
        if re.match(r"^\w+://[^/@]+@", repo):
            errors.append(f"missions/{name}/repo : identifiants dans l'URL ; utilisez un secret git "
                          "(credential helper, jeton du runner)")
        host = host_of(repo)
        if host and not allowed(host, hosts):
            errors.append(f"missions/{name}/repo : hôte « {host} » absent de allowed_hosts")
        if not host and not (base / repo).is_dir():
            errors.append(f"missions/{name}/repo : dossier local « {repo} » introuvable")
    if not config["missions"] and not config.get("discovery"):
        errors.append("missions : au moins une mission, ou discovery pour les trouver dans GitLab")
    if config.get("discovery") and (config.get("access") or {}).get("provider", "gitlab") != "gitlab":
        errors.append("discovery : contrôle d'accès GitLab attendu (access.provider gitlab, access.api)")
    elif config.get("discovery") and not config.get("access"):
        errors.append("discovery : section access (API GitLab) attendue")
    runner = config.get("runner", {})
    if runner.get("kind") == "kubernetes" and not runner.get("image"):
        errors.append("runner/image : image du pod des tours attendue avec kind kubernetes")
    rights = config.get("access")
    if rights and rights.get("provider", "gitlab") == "gitlab":
        host = host_of(rights.get("api", ""))
        if not host:
            errors.append("access/api : adresse de l'API GitLab attendue (https://gitlab.../api/v4)")
        elif not allowed(host, hosts):
            errors.append(f"access/api : hôte « {host} » absent de allowed_hosts")
    elif rights and not (base / rights.get("file", "")).is_file():
        errors.append(f"access/file : fichier des droits « {rights.get('file')} » introuvable")
    for key, value in config["agent"].get("env", {}).items():
        host = host_of(value) if URL_VARS.search(key) else None
        if host and not allowed(host, hosts) and host not in ("localhost", "127.0.0.1"):
            errors.append(f"agent/env/{key} : hôte « {host} » absent de allowed_hosts (LiteLLM...)")
    return errors


def load_config(path: Path) -> tuple[dict | None, list[str]]:
    config, errors = read_spec(path, __file__)
    if config is None or errors:
        return None, errors
    return config, check_config(config, path.resolve().parent)


def git(cwd: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = {**os.environ, "GIT_TERMINAL_PROMPT": "0"}
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env)
    if check and result.returncode:
        raise RuntimeError(f"git {args[0]} : {(result.stderr or result.stdout).strip()[-300:]}")
    return result


def identity(config: dict) -> list[str]:
    author = config.get("git", {})
    return ["-c", f"user.name={author.get('name', 'myskills-remote')}",
            "-c", f"user.email={author.get('email', 'myskills-remote@localhost')}"]


class Refused(Exception):
    """Droits insuffisants au début de la session, avant un pull ou un push."""


def workspace(config: dict, base: Path, name: str, chat: str, emit, guard) -> tuple[Path, str]:
    """Copie de travail de la conversation, sur sa branche, à jour du dépôt. Sans copie, la session
    commence : guard("start") ; avant chaque pull : guard("pull")."""
    mission = config["missions"][name]
    repo = mission["repo"] if host_of(mission["repo"]) else str((base / mission["repo"]).resolve())
    branch = config.get("branch_prefix", "openwebui/") + slug(chat)
    target = (base / config.get("workdir", "clones")).resolve() / slug(name) / slug(chat)
    remote_has = bool(git(base, "ls-remote", "--heads", repo, branch).stdout.strip())
    if not (target / ".git").is_dir():
        guard("start")
        emit("git", f"clone de {name}")
        target.parent.mkdir(parents=True, exist_ok=True)
        start = branch if remote_has else mission.get("base")
        git(base, "clone", "--quiet", *(["--branch", start] if start else []), repo, str(target))
        if not remote_has:
            git(target, "checkout", "--quiet", "-b", branch)
    elif remote_has:
        guard("pull")
        emit("git", f"mise à jour de {branch}")
        git(target, "pull", "--quiet", "--ff-only", "origin", branch)
    return target, branch


def workflows(folder: Path) -> list[Path]:
    """Dossiers des workflows de la mission : mission.json, sinon les workflow.json trouvés."""
    mission = folder / "mission.json"
    if mission.is_file():
        try:
            listed = json.loads(mission.read_text(encoding="utf-8")).get("workflows") or []
            found = [folder / w.get("folder", ".") for w in listed]
            if found:
                return [f for f in found if (f / "workflow.json").is_file()]
        except (OSError, ValueError):
            pass
    hits = [p.parent for p in [folder / "workflow.json", *folder.glob("*/workflow.json")] if p.is_file()]
    return sorted(set(hits))


def status(folder: Path, warnings: list[str]) -> dict:
    """État des workflows : étapes, étape en revue (porte), questions ouvertes."""
    state = {"workflows": [], "gate": None, "questions": 0}
    if not workflows(folder):
        return state
    if find_script("decision-log", "journal.py") is None:
        warnings.append(absent("decision-log", "journal.py"))
        return state
    for wf in workflows(folder):
        report = run_script("decision-log", "journal.py", ["status", str(wf)])
        warnings.extend(f"journal.py status {wf.name} : {e}" for e in report.get("errors", []))
        stages = report.get("stages", {})
        rel = wf.relative_to(folder).as_posix()
        try:
            definition = json.loads((wf / "workflow.json").read_text(encoding="utf-8")).get("definition") or {}
        except (OSError, ValueError):
            definition = {}
        state["workflows"].append({"folder": rel, "workflow": definition.get("name", rel),
                                   "current": report.get("current"), "stages": stages})
        state["questions"] += report.get("questions", 0)
        review = [s for s, v in stages.items() if v == "en-revue"]
        if review and state["gate"] is None:
            state["gate"] = {"folder": rel, "stages": review}
    return state


def shortcut(folder: Path, message: str, state: dict, emit) -> tuple[dict | None, list[str]]:
    """« valide » ou « retour : ... » à une porte où une seule étape attend : journal.py review direct."""
    gate = state.get("gate")
    feedback = FEEDBACK.match(message)
    if not gate or len(gate["stages"]) != 1 or not (VALIDATE.match(message) or feedback):
        return None, []
    stage, decision = gate["stages"][0], "retour" if feedback else "valide"
    text = feedback.group(2).strip() if feedback else message.strip()
    emit("revue", f"{stage} : {decision}")
    report = run_script("decision-log", "journal.py", ["review", str(folder / gate["folder"]), stage,
                                                       "--decision", decision, "--text", text])
    if report.get("errors"):
        return None, [f"journal.py review {stage} : {e}" for e in report["errors"]]
    return {"stage": stage, "decision": decision, "folder": gate["folder"]}, []


def agent_env(config: dict) -> dict:
    """Environnement de l'agent : celui du service, sans son jeton, plus agent.env (LiteLLM...)."""
    server_token = config.get("server", {}).get("token_env", "MYSKILLS_REMOTE_TOKEN")
    env = {k: v for k, v in os.environ.items() if k != server_token}
    env.update(config["agent"].get("env", {}))
    hosts = ",".join(config.get("allowed_hosts", []))
    if hosts:  # model_store.guard_network() laisse joindre ces hôtes, et eux seuls (AGENTS.md, section 5)
        env["MYSKILLS_ALLOWED_HOSTS"] = ",".join(filter(None, [env.get("MYSKILLS_ALLOWED_HOSTS"), hosts]))
    author = config.get("git", {})
    for role in ("AUTHOR", "COMMITTER"):
        env.setdefault(f"GIT_{role}_NAME", author.get("name", "myskills-remote"))
        env.setdefault(f"GIT_{role}_EMAIL", author.get("email", "myskills-remote@localhost"))
    return env


def run_agent(config: dict, folder: Path, prompt: str, emit, resume: bool = False) -> tuple[str, list[str], dict | None]:
    """Lance l'agent ; chaque ligne de sa sortie est un événement, la sortie entière la réponse.
    resume : la conversation a déjà un tour d'agent ici, agent.continue_args reprend sa session
    (claude --continue) : l'agent garde le contexte des messages précédents."""
    agent = config["agent"]
    tmp = folder / ".myskills-tmp"
    tmp.mkdir(exist_ok=True)
    prompt_file = tmp / "remote-prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    values = {"{prompt}": prompt, "{prompt_file}": str(prompt_file), "{folder}": str(folder),
              "{python}": sys.executable, "{config_dir}": str(config["_base"])}
    command = [values.get(part, part) if part in values else
               re.sub(r"\{(prompt_file|folder|python|config_dir)\}", lambda m: values["{" + m.group(1) + "}"], part)
               for part in agent["command"]]
    command[0] = shutil.which(command[0]) or command[0]
    if resume:
        command += agent.get("continue_args", [])
    emit("agent", "reprise de la session de l'agent" if resume else "lancement de l'agent")
    started, lines = time.monotonic(), []
    try:
        process = subprocess.Popen(command, cwd=folder, env=agent_env(config), stdout=subprocess.PIPE,
                                   stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, text=True,
                                   encoding="utf-8", errors="replace")
    except OSError as error:
        return "", [f"agent : lancement impossible ({error}) ; vérifiez agent.command"], None
    errors, timeout = [], agent.get("timeout", 3600)
    for line in process.stdout:
        lines.append(line.rstrip("\n"))
        if line.strip() and not line.startswith('{"agent"'):  # le rapport final ne s'affiche pas
            emit("agent", line.rstrip()[:300])
        if time.monotonic() - started > timeout:
            process.kill()
            errors.append(f"agent : arrêté après {timeout} s (agent.timeout)")
            break
    code = process.wait()
    if code and not errors:
        errors.append(f"agent : code de sortie {code}")
    shutil.rmtree(tmp, ignore_errors=True)
    final = None
    while lines and not lines[-1].strip():
        lines.pop()
    if lines:  # rapport final de l'agent (agent-report.schema.json), gardé hors de la réponse
        try:
            candidate = json.loads(lines[-1])
            if isinstance(candidate, dict) and {"agent", "status"} <= candidate.keys():
                final = candidate
                lines.pop()
        except ValueError:
            pass
    answer = "\n".join(lines).strip()
    return answer[-ANSWER_MAX:], errors, final


def changed_files(target: Path) -> list[str]:
    out = git(target, "status", "--porcelain", "--untracked-files=all").stdout
    return [line[3:].strip('"') for line in out.splitlines() if line.strip()]


def images(config: dict, name: str, branch: str, target: Path, files: list[str]) -> list[dict]:
    """PNG changés : lien vers le dépôt (links.web) et, petits, en ligne (data:)."""
    web = config["missions"][name].get("web")
    limit = config.get("inline_images_kb", 300) * 1024
    found = []
    for path in files:
        full = target / path
        if not path.lower().endswith(".png") or not full.is_file():
            continue
        drawio = path[:-4] if path.lower().endswith(".drawio.png") else None
        entry = {"path": path,
                 "url": f"{web.rstrip('/')}/-/raw/{quote(branch, safe='')}/{quote(path)}" if web else None,
                 "source": drawio if drawio and (target / drawio).is_file() else None,
                 "data": None}
        if full.stat().st_size <= limit:
            entry["data"] = "data:image/png;base64," + base64.b64encode(full.read_bytes()).decode("ascii")
        found.append(entry)
    return found


def commit_push(config: dict, target: Path, branch: str, chat: str, emit, push: bool,
                guard=lambda kind: None) -> tuple[str | None, bool, list[str]]:
    errors = []
    if changed_files(target):
        git(target, "add", "--all")
        git(target, *identity(config), "commit", "--quiet", "-m", f"mission : tour à distance ({slug(chat)})")
    head = git(target, "rev-parse", "--short", "HEAD").stdout.strip()
    pushed = False
    if push and config.get("push", True):
        try:
            guard("push")
        except Refused as error:
            return head, False, [f"{error} ; commit {head} gardé dans la session"]
        emit("git", f"push de {branch}")
        result = git(target, "push", "--quiet", "-u", "origin", branch, check=False)
        pushed = result.returncode == 0
        if not pushed:
            errors.append(f"git push : {(result.stderr or result.stdout).strip()[-300:]} ; commit {head} gardé")
    return head, pushed, errors


def empty_report(name: str, chat: str, user: str | None = None) -> dict:
    return {"mission": name, "chat": chat, "user": user, "branch": None, "folder": None, "mode": "agent", "answer": "",
            "shortcut": None, "gate": None, "questions": 0, "workflows": [], "changed": [], "images": [],
            "commit": None, "pushed": False, "resumed": False, "seconds": 0, "errors": [], "warnings": []}


def run_turn(config: dict, name: str, chat: str, message: str, emit=lambda kind, text: None,
             push: bool = True, user: str | None = None, check_access: bool = True) -> dict:
    """Un tour complet ; config déjà validée (load_config), config["_base"] = dossier de la configuration.
    Avec access, les droits de l'utilisateur sur le projet GitLab de la mission se vérifient au début
    de la session (écriture, lecture pour /statut), avant chaque pull (lecture) et chaque push
    (écriture), pas à chaque message."""
    report, started = empty_report(name, chat, user), time.monotonic()
    base = Path(config["_base"])
    if name not in config["missions"]:
        report["errors"].append(f"mission « {name} » inconnue (permis : {', '.join(config['missions'])})")
        return report
    reading = message.strip().lower() in STATUS_WORDS

    def guard(kind: str) -> None:
        refused = access.check(config, name, user, write={"start": not reading, "pull": False, "push": True}[kind],
                               action=kind) if check_access else None
        if refused:
            raise Refused(refused)

    try:
        target, branch = workspace(config, base, name, chat, emit, guard)
        folder = (target / config["missions"][name].get("folder", ".")).resolve()
        report.update(branch=branch, folder=folder.relative_to(target).as_posix())
        before = changed_files(target)
        if before:
            report["warnings"].append(f"copie de travail non propre avant le tour ({len(before)} fichiers), "
                                      "repris dans le commit")
        state = status(folder, report["warnings"])
        if message.strip().lower() in STATUS_WORDS:
            report["mode"] = "statut"
        elif message.strip().lower() in END_WORDS:
            report["mode"] = "fin"
            report["commit"], report["pushed"], errors = commit_push(config, target, branch, chat, emit, push, guard)
            report["errors"] += errors
            state = status(folder, report["warnings"])
            if not errors:
                emit("session", "fin de session : copie de travail effacée")
                shutil.rmtree(target, ignore_errors=True)
        else:
            done, errors = shortcut(folder, message, state, emit)
            report["shortcut"], report["errors"] = done, report["errors"] + errors
            if not errors:
                note = (f" L'utilisateur vient de donner sa décision « {done['decision']} » sur l'étape "
                        f"{done['stage']} : elle est déjà enregistrée au journal (journal.py review), "
                        "ne la refais pas ; continue." if done else "")
                template = config["agent"].get("prompt", DEFAULT_PROMPT)
                prompt = template.replace("{folder}", str(folder)).replace("{note}", note) \
                    .replace("{message}", message)
                marker = target / ".git" / "myskills-agent-session"  # hors des fichiers suivis par git
                answer, errors, final = run_agent(config, folder, prompt, emit, resume=marker.is_file())
                report["answer"], report["errors"] = answer, report["errors"] + errors
                report["resumed"] = marker.is_file()
                if not errors:
                    marker.write_text(time.strftime("%Y-%m-%dT%H:%M:%S"), encoding="utf-8")
                if final and final.get("todo"):
                    report["warnings"] += [f"agent, reste à faire : {t}" for t in final["todo"][:5]]
            changed = changed_files(target)
            report["changed"] = changed
            report["images"] = images(config, name, branch, target, changed)
            report["commit"], report["pushed"], errors = commit_push(config, target, branch, chat, emit, push, guard)
            report["errors"] += errors
            state = status(folder, report["warnings"])
        report.update(gate=state["gate"], questions=state["questions"], workflows=state["workflows"])
    except (RuntimeError, Refused) as error:
        report["errors"].append(str(error))
    report["seconds"] = round(time.monotonic() - started, 1)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--config", type=Path, help="configuration du service (remote.json)")
    parser.add_argument("--mission", help="mission de la configuration (missions.<nom>)")
    parser.add_argument("--chat", help="identifiant de la conversation (une branche par conversation)")
    parser.add_argument("--message", help="message de l'utilisateur")
    parser.add_argument("--message-file", type=Path, help="message lu dans un fichier (UTF-8)")
    parser.add_argument("--message-env", help="message lu dans cette variable d'environnement (Job Kubernetes)")
    parser.add_argument("--user", help="utilisateur (courriel ou nom GitLab), exigé si access est configuré")
    parser.add_argument("--workdir", type=Path, help="copies de travail (remplace workdir de la configuration)")
    parser.add_argument("--no-push", action="store_true", help="commit local seulement")
    parser.add_argument("--events", type=Path, help="journal des événements du tour (JSON Lines)")
    parser.add_argument("--job", action="store_true",
                        help="tour lancé par le service dans un pod : événements sur la sortie d'erreur, images en "
                             "ligne gardées, droits déjà vérifiés par le service")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = empty_report(args.mission or "", args.chat or "", args.user)
    message = args.message if args.message is not None else \
        os.environ.get(args.message_env) if args.message_env else \
        args.message_file.read_text(encoding="utf-8") if args.message_file else None
    missing = [o for o, v in (("--config", args.config), ("--mission", args.mission), ("--chat", args.chat),
                              ("--message, --message-file ou --message-env", message)) if v is None]
    if missing:
        report["errors"].append(f"options manquantes : {', '.join(missing)}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    config, errors = load_config(args.config)
    if errors:
        report["errors"] = errors
        print(json.dumps(report, ensure_ascii=False))
        return 1
    config["_base"] = str(args.config.resolve().parent)
    if args.workdir:
        config["workdir"] = str(args.workdir.resolve())
    sink = sys.stderr if args.job else args.events.open("w", encoding="utf-8") if args.events else None

    def emit(kind: str, text: str) -> None:
        if sink:
            sink.write(json.dumps({"t": round(time.time(), 1), "kind": kind, "text": text}, ensure_ascii=False) + "\n")
            sink.flush()

    try:
        report = run_turn(config, args.mission, args.chat, message, emit, push=not args.no_push,
                          user=args.user, check_access=not args.job)
    finally:
        if sink and sink is not sys.stderr:
            sink.close()
    if not args.job:  # le rapport reste court : les images en ligne sont pour le service
        for image in report["images"]:
            image["data"] = bool(image["data"])
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
