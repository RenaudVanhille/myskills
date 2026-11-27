# /// script
# requires-python = ">=3.10"
# ///
"""Service HTTP des missions à distance : Open WebUI (pipe) -> tours de mission en arrière-plan.

Bibliothèque standard seulement, pour un conteneur minimal (Kubernetes) ou un poste Windows.
Chaque message lance un tour (remote_turn.run_turn) dans un fil à part : la requête de chat ne
tient pas pendant le tour, le pipe suit les événements par appels longs (long poll) et se
raccroche au tour en cours si la connexion tombe. Un seul tour à la fois par conversation.

    GET  /health                   état du service (sans jeton)
    GET  /missions                 missions de la configuration (un modèle par mission dans Open WebUI)
    POST /turns                    {"mission", "chat", "message"} -> {"job"} ; 409 si un tour est en cours
    GET  /jobs/ID?after=N&wait=S   événements depuis N, puis le rapport quand le tour est fini (&ack=1 : lu)
    GET  /chats/MISSION/CHAT       tour en cours et dernier rapport non lu de la conversation

Jeton : en-tête « Authorization: Bearer ... », lu dans la variable server.token_env ; obligatoire
dès que le service écoute ailleurs que sur la machine elle-même.

    uv run deploy/remote-mission/service/scripts/remote_server.py serve --config remote.json [--host H] [--port P]
    uv run deploy/remote-mission/service/scripts/remote_server.py check --config remote.json
    uv run deploy/remote-mission/service/scripts/remote_server.py probe --config remote.json --mission NOM --pipe openwebui_pipe.py [--chat ID] [--message M]
"""

import argparse
import asyncio
import hashlib
import hmac
import importlib.util
import json
import os
import secrets
import signal
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(2, str(HERE.parents[3] / "shared" / "scripts"))  # bibliothèques partagées du dépôt myskills
import access  # noqa: E402
import discovery  # noqa: E402
import k8s_sessions  # noqa: E402
import merge_requests  # noqa: E402
import remote_turn  # noqa: E402
from spec_schema import print_schema, schema_option  # noqa: E402

LOOPBACK = {"127.0.0.1", "localhost", "::1"}
MAX_BODY = 1_000_000
PIPE = HERE.parents[1] / "openwebui_pipe.py"  # deploy/remote-mission/openwebui_pipe.py
OUTPUT_MAX = 4000


class Job:
    def __init__(self, mission: str, chat: str):
        self.id, self.mission, self.chat = uuid.uuid4().hex[:12], mission, chat
        self.events: list[dict] = []
        self.report: dict | None = None
        self.delivered = False
        self.cond = threading.Condition()

    def emit(self, kind: str, text: str) -> None:
        with self.cond:
            self.events.append({"t": round(time.time(), 1), "kind": kind, "text": text})
            self.cond.notify_all()

    def finish(self, report: dict) -> None:
        with self.cond:
            self.report = report
            self.cond.notify_all()

    def view(self, after: int, wait: float) -> dict:
        with self.cond:
            self.cond.wait_for(lambda: len(self.events) > after or self.report is not None, timeout=wait)
            return {"job": self.id, "events": self.events[after:], "next": len(self.events),
                    "done": self.report is not None, "report": self.report}


class Service:
    """État partagé : tours en cours et derniers rapports, par conversation."""

    def __init__(self, config: dict, token: str | None, session: tuple | None = None):
        self.config, self.token = config, token
        self.session = session  # pod de session : la seule conversation qu'il sert
        self.last_activity = time.monotonic()
        self.sessions = k8s_sessions.Sessions(config) \
            if config.get("runner", {}).get("kind") == "kubernetes" and session is None else None
        self.jobs: dict[str, Job] = {}
        self.chats: dict[tuple, str] = {}
        self.owners: dict[tuple, str] = {}  # conversation -> utilisateur qui l'a ouverte
        self.lock = threading.Lock()
        self.turns = 0
        self.max_jobs = config.get("server", {}).get("max_jobs", 4)
        self.bindings = discovery.Bindings(config, self.sessions) if discovery.enabled(config) else None

    def discovered(self) -> set:
        """Missions ajoutées par la découverte GitLab (absentes du modèle par mission)."""
        return {k for k, v in self.config["missions"].items() if v.get("_discovered")}

    def running(self) -> int:
        return sum(1 for j in self.jobs.values() if j.report is None)

    def owner_refused(self, mission: str, chat: str, user: str | None) -> str | None:
        owner = self.owners.get((mission, chat))
        if self.config.get("access") and owner and (user or "").lower() != owner:
            return "conversation ouverte par un autre utilisateur"
        return None

    def quick(self, mission: str, chat: str, user: str | None, answer: str = "", errors=()) -> tuple[int, dict]:
        """Réponse immédiate, sans session (commandes du modèle Missions)."""
        job = Job(mission, chat)
        job.finish({**remote_turn.empty_report(mission, chat, user), "mode": "statut", "answer": answer,
                    "errors": list(errors)})
        with self.lock:
            self.jobs[job.id], self.chats[(mission, chat)] = job, job.id
        return 202, {"job": job.id}

    def resolve(self, chat: str, message: str, user: str | None) -> tuple[str | None, tuple | None]:
        """Modèle Missions : (mission liée, None) ou (None, réponse immédiate) pour /missions, /mission, aide."""
        command = message.strip()
        if command.lower() == "/missions":
            answer, errors = discovery.listing(self.config, user)
            return None, self.quick(discovery.MODEL_ID, chat, user, answer, errors)
        if command.lower().startswith("/mission "):
            path = command.split(None, 1)[1].strip().strip("`/")
            try:
                known = discovery.register(self.config, path)
            except (PermissionError, OSError, ValueError) as error:
                return None, self.quick(discovery.MODEL_ID, chat, user, errors=[f"missions : {error}"])
            if not known:
                return None, self.quick(discovery.MODEL_ID, chat, user,
                                        errors=[f"« {path} » n'est pas une mission (topic {self.config['discovery']['topic']})"])
            refused = access.check(self.config, path, user, write=True, action="start")
            if refused:
                return None, self.quick(discovery.MODEL_ID, chat, user, errors=[refused])
            self.bindings.set(chat, path, user)
            return None, self.quick(discovery.MODEL_ID, chat, user,
                                    f"Mission **{path}** choisie pour cette conversation. Écrivez votre premier message.")
        bound = self.bindings.get(chat)
        if bound is None:
            return None, self.quick(discovery.MODEL_ID, chat, user, discovery.HELP)
        try:
            if not discovery.register(self.config, bound):
                return None, self.quick(discovery.MODEL_ID, chat, user,
                                        errors=[f"mission « {bound} » sortie du périmètre (topic retiré, projet archivé ?)"])
        except (PermissionError, OSError, ValueError) as error:
            return None, self.quick(discovery.MODEL_ID, chat, user, errors=[f"missions : {error}"])
        return bound, None

    def start(self, mission: str, chat: str, message: str, user: str | None,
              gitlab_token: str = "") -> tuple[int, dict]:
        """gitlab_token : jeton GitLab de l'utilisateur (pipe), pour la seule merge request de ce tour."""
        if mission == discovery.MODEL_ID and self.bindings:
            mission, answered = self.resolve(chat, message, user)
            if answered:
                return answered
        if mission not in self.config["missions"]:
            return 404, {"error": f"mission « {mission} » inconnue"}
        if self.session and (mission, chat) != self.session:
            return 403, {"error": "ce pod de session sert une autre conversation"}
        self.last_activity = time.monotonic()
        refused = self.owner_refused(mission, chat, user)
        if refused:
            return 403, {"error": refused}
        with self.lock:
            current = self.jobs.get(self.chats.get((mission, chat), ""))
            if current and current.report is None:
                return 409, {"job": current.id, "busy": True}
            if self.running() >= self.max_jobs:
                return 503, {"error": f"{self.max_jobs} tours déjà en cours (server.max_jobs), réessayez plus tard"}
            job = Job(mission, chat)
            self.jobs[job.id], self.chats[(mission, chat)] = job, job.id
            self.owners.setdefault((mission, chat), (user or "").lower())
            self.turns += 1

        def work() -> None:
            try:
                if self.sessions:
                    report = self.via_session(mission, chat, message, user, job.emit)
                else:  # droits vérifiés au début de la session, avant chaque pull et chaque push
                    report = remote_turn.run_turn(self.config, mission, chat, message, job.emit, user=user)
                if self.session is None:  # service frontal : jamais dans le pod de session
                    merge_requests.after_turn(self.config, mission, report, job.emit, gitlab_token)
            except Exception as error:  # le service survit à un tour en échec
                report = {**remote_turn.empty_report(mission, chat), "errors": [f"tour interrompu : {error}"]}
            job.finish(report)
            self.last_activity = time.monotonic()

        threading.Thread(target=work, daemon=True).start()
        return 202, {"job": job.id}

    def via_session(self, mission: str, chat: str, message: str, user: str | None, emit) -> dict:
        """Message passé au pod de session de la conversation (créé, retrouvé ou rechargé). Les droits
        se vérifient ici quand la session démarre ou se recharge, puis dans le pod avant chaque pull
        et chaque push ; pas à chaque message."""
        empty = remote_turn.empty_report(mission, chat, user)
        try:
            if not self.sessions.running(mission, chat):
                refused = access.check(self.config, mission, user, action="start",
                                       write=message.strip().lower() not in remote_turn.STATUS_WORDS)
                if refused:
                    return {**empty, "errors": [refused]}
            url, token = self.sessions.ensure(mission, chat, emit)
            report = forward(url, token, mission, chat, message, user, emit)
            if report.get("mode") == "fin" and not report.get("errors"):
                self.sessions.end(mission, chat)
                emit("session", "pod et volume de la session effacés")
            return report
        except (urllib.error.URLError, OSError, RuntimeError, ValueError) as error:
            return {**empty, "errors": [f"session : {error}"]}

    def chat(self, mission: str, chat: str, user: str | None) -> dict:
        if mission == discovery.MODEL_ID and self.bindings:
            mission = self.bindings.get(chat) or mission
        if self.owner_refused(mission, chat, user):
            return {"job": None, "running": False, "report": None}
        job = self.jobs.get(self.chats.get((mission, chat), ""))
        if job is None:
            return {"job": None, "running": False, "report": None}
        unread = job.report if job.report is not None and not job.delivered else None
        return {"job": job.id, "running": job.report is None, "report": unread}


def handler(service: Service):
    class Handler(BaseHTTPRequestHandler):
        server_version = "myskills-remote"

        def log_message(self, *args) -> None:  # pas de contenu de mission dans les journaux du pod
            pass

        def send(self, code: int, payload: dict) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def authorized(self) -> bool:
            if not service.token:
                return True
            given = self.headers.get("Authorization", "").removeprefix("Bearer ").strip()
            return hmac.compare_digest(given.encode(), service.token.encode())

        def do_GET(self) -> None:
            url = urlparse(self.path)
            parts = [unquote(p) for p in url.path.strip("/").split("/") if p]
            if parts == ["health"]:
                return self.send(200, {"ok": True, "running": service.running()})
            if not self.authorized():
                return self.send(401, {"error": "jeton absent ou invalide"})
            query = parse_qs(url.query)
            if parts == ["missions"]:
                listed = [{"id": k, "title": v.get("title", k)} for k, v in service.config["missions"].items()
                          if k not in service.discovered()]
                if service.bindings:
                    listed.insert(0, {"id": discovery.MODEL_ID,
                                      "title": service.config["discovery"].get("title", "Missions myskills")})
                return self.send(200, {"missions": listed})
            if len(parts) == 2 and parts[0] == "jobs":
                job = service.jobs.get(parts[1])
                if job is None:
                    return self.send(404, {"error": "tour inconnu (service redémarré ?)"})
                after = int(query.get("after", ["0"])[0])
                wait = min(float(query.get("wait", ["20"])[0]), 60.0)
                view = job.view(after, wait)
                if view["done"] and query.get("ack") == ["1"]:
                    job.delivered = True
                return self.send(200, view)
            if parts == ["openwebui", "pipe"]:  # source du pipe, installée par openwebui_install.py
                content = PIPE.read_text(encoding="utf-8")
                return self.send(200, {"content": content,
                                       "sha256": hashlib.sha256(content.encode("utf-8")).hexdigest()})
            if len(parts) == 3 and parts[0] == "chats":
                return self.send(200, service.chat(parts[1], parts[2], self.headers.get("X-Myskills-User")))
            return self.send(404, {"error": "chemin inconnu"})

        def do_POST(self) -> None:
            if not self.authorized():
                return self.send(401, {"error": "jeton absent ou invalide"})
            if urlparse(self.path).path.rstrip("/") != "/turns":
                return self.send(404, {"error": "chemin inconnu"})
            length = int(self.headers.get("Content-Length", "0"))
            if length > MAX_BODY:
                return self.send(413, {"error": "message trop long"})
            try:
                data = json.loads(self.rfile.read(length) or b"{}")
                mission, chat, message = str(data["mission"]), str(data["chat"]), str(data["message"])
            except (ValueError, KeyError, TypeError):
                return self.send(400, {"error": "attendu : {\"mission\", \"chat\", \"message\"}"})
            code, payload = service.start(mission, chat, message, self.headers.get("X-Myskills-User"),
                                          self.headers.get("X-Myskills-Gitlab-Token", ""))
            return self.send(code, payload)

    return Handler


def forward(url: str, token: str, mission: str, chat: str, message: str, user: str | None, emit) -> dict:
    """Joue le message dans un autre service (le pod de session) et relaie ses événements."""
    def call(method: str, path: str, payload: dict | None = None, timeout: float = 30) -> tuple[int, dict]:
        request = urllib.request.Request(url + path, method=method,
                                         data=json.dumps(payload).encode("utf-8") if payload else None,
                                         headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json",
                                                  "X-Myskills-User": user or ""})
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read() or b"{}")

    code, started = call("POST", "/turns", {"mission": mission, "chat": chat, "message": message})
    if code not in (202, 409):
        raise RuntimeError(started.get("error", f"pod de session : code {code}"))
    if code == 409:
        emit("session", "un message est déjà en cours dans la session : suivi de celui-ci")
    job, after = started["job"], 0
    while True:
        _, view = call("GET", f"/jobs/{job}?after={after}&wait=25&ack=1", timeout=60)
        for event in view.get("events", []):
            emit(event["kind"], event["text"])
        after = view.get("next", after)
        if view.get("done"):
            return view["report"]


def report(command: str, **fields) -> dict:
    return {"command": command, "url": None, "missions": 0, "turns": 0, "output": None,
            "errors": [], "warnings": [], **fields}


def token_for(config: dict, host: str, out: dict) -> str | None:
    name = config.get("server", {}).get("token_env", "MYSKILLS_REMOTE_TOKEN")
    token = os.environ.get(name)
    if not token and host not in LOOPBACK:
        out["errors"].append(f"variable {name} vide : jeton obligatoire hors de la machine (Secret Kubernetes)")
    elif not token:
        out["warnings"].append(f"variable {name} vide : service sans jeton, joignable de la machine seulement")
    return token


def start_server(service: Service, host: str, port: int) -> ThreadingHTTPServer:
    server = ThreadingHTTPServer((host, port), handler(service))
    server.daemon_threads = True
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def load_pipe(path: Path):
    spec = importlib.util.spec_from_file_location("openwebui_pipe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def drive_pipe(url: str, token: str, mission: str, chat: str, message: str, user: str | None,
                     pipe_file: Path) -> str:
    """Joue le message comme Open WebUI le ferait : modèle « fonction.mission », chat_id en métadonnées."""
    pipe = load_pipe(pipe_file).Pipe()
    pipe.valves.SERVER_URL, pipe.valves.TOKEN, pipe.valves.POLL_SECONDS = url, token, 2
    models = pipe.pipes()
    if mission not in {m["id"] for m in models}:
        raise RuntimeError(f"pipe : mission « {mission} » absente de pipes() ({models})")
    body = {"model": f"myskills_remote.{mission}", "stream": True,
            "messages": [{"role": "user", "content": message}]}
    chunks = []
    async for chunk in pipe.pipe(body, __metadata__={"chat_id": chat},
                                 __user__={"email": user} if user else None):
        chunks.append(chunk)
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", nargs="?", choices=["serve", "check", "probe"])
    parser.add_argument("--config", type=Path, help="configuration (remote.json), schéma de remote_turn.py")
    parser.add_argument("--host", help="adresse d'écoute (défaut : server.host, sinon 127.0.0.1)")
    parser.add_argument("--port", type=int, help="port (défaut : server.port, sinon 8765)")
    parser.add_argument("--workdir", type=Path, help="serve : copies de travail (remplace workdir)")
    parser.add_argument("--session", help="serve : pod de session, ne sert que MISSION:CONVERSATION")
    parser.add_argument("--idle-minutes", type=float, help="serve : s'arrête après ce temps sans message")
    parser.add_argument("--mission", help="probe : mission à jouer")
    parser.add_argument("--chat", default="probe", help="probe : conversation (défaut : probe)")
    parser.add_argument("--user", help="probe : utilisateur Open WebUI (courriel), pour le contrôle d'accès")
    parser.add_argument("--pipe", type=Path, help="probe : fonction Pipe d'Open WebUI "
                        "(deploy/remote-mission/openwebui_pipe.py du dépôt myskills : hors du skill)")
    parser.add_argument("--message", default="/statut", help="probe : message (défaut : /statut, sans agent)")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    out = report(args.command or "")
    if not args.command or not args.config:
        out["errors"].append("attendu : serve|check|probe --config remote.json")
        print(json.dumps(out, ensure_ascii=False))
        return 1
    config, errors = remote_turn.load_config(args.config)
    out["errors"] += errors
    if config is not None:
        config["_base"] = str(args.config.resolve().parent)
        out["missions"] = len(config["missions"])
    if out["errors"] or args.command == "check":
        print(json.dumps(out, ensure_ascii=False))
        return 1 if out["errors"] else 0
    settings = config.get("server", {})
    host = args.host or settings.get("host", "127.0.0.1")
    if args.workdir:
        config["workdir"] = str(args.workdir.resolve())
    session = tuple(args.session.split(":", 1)) if args.session else None
    if session and len(session) == 2 and session[0] not in config["missions"] and os.environ.get("MYSKILLS_MISSION_SPEC"):
        config["missions"][session[0]] = json.loads(os.environ["MYSKILLS_MISSION_SPEC"])  # mission découverte
    if session and (len(session) != 2 or session[0] not in config["missions"]):
        out["errors"].append(f"--session : MISSION:CONVERSATION attendu, mission de la configuration ({args.session})")
    if args.command == "probe":
        host, token = "127.0.0.1", secrets.token_urlsafe(16)
        if not args.mission:
            out["errors"].append("probe : --mission attendu")
        if not args.pipe or not args.pipe.is_file():
            out["errors"].append(f"probe : fonction Pipe introuvable ({args.pipe or '--pipe absent'}) ; --pipe CHEMIN "
                                 "vers deploy/remote-mission/openwebui_pipe.py d'une copie du dépôt myskills")
        if out["errors"]:
            print(json.dumps(out, ensure_ascii=False))
            return 1
        service = Service(config, token)
        server = start_server(service, host, 0)
        out["url"] = f"http://{host}:{server.server_address[1]}"
        try:
            text = asyncio.run(drive_pipe(out["url"], token, args.mission, args.chat, args.message,
                                          args.user, args.pipe))
            out["output"] = text[-OUTPUT_MAX:]
            if not text.strip():
                out["errors"].append("probe : réponse vide du pipe")
        except Exception as error:
            out["errors"].append(f"probe : {error}")
        finally:
            server.shutdown()
        out["turns"] = service.turns
        last = next(iter(service.jobs.values()), None)
        if last and last.report:
            out["errors"] += last.report["errors"]
            out["warnings"] += last.report["warnings"]
        print(json.dumps(out, ensure_ascii=False))
        return 1 if out["errors"] else 0
    token = token_for(config, host, out)
    if out["errors"]:
        print(json.dumps(out, ensure_ascii=False))
        return 1
    service = Service(config, token, session)
    server = start_server(service, host, args.port or settings.get("port", 8765))
    out["url"] = f"http://{host}:{server.server_address[1]}"
    print(json.dumps({"listening": out["url"], "missions": out["missions"]}, ensure_ascii=False),
          file=sys.stderr, flush=True)
    def stop(*_):  # Kubernetes arrête le pod par SIGTERM
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, stop)
    idle = args.idle_minutes * 60 if args.idle_minutes else None
    try:
        while True:
            time.sleep(min(5.0, idle / 4) if idle else 3600)
            if idle and not service.running() and time.monotonic() - service.last_activity > idle:
                out["warnings"].append(f"arrêt après {args.idle_minutes:g} min sans message (session rechargée au suivant)")
                break
    except KeyboardInterrupt:
        pass
    server.shutdown()
    out["turns"] = service.turns
    print(json.dumps(out, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
