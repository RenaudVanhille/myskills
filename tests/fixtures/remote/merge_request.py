"""Merge request ouverte par le service des missions face à une API GitLab simulée (locale, aucun réseau).

Ouverte à « /fin » et quand tous les workflows sont validés, pas sur un tour ordinaire ; au nom de
l'utilisateur (jeton transmis par le pipe dans X-Myskills-Gitlab-Token), sinon avec GITLAB_MR_TOKEN ;
merge request déjà ouverte reprise sans doublon ; branche par défaut lue ; sans jeton : avertissement ;
jeton jamais passé à l'agent ; pod de session qui n'ouvre rien.

Usage : python merge_request.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import json
import os
import sys
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SCRIPTS = Path(sys.argv[1]).resolve().parent / "deploy" / "remote-mission" / "service" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import remote_server  # noqa: E402
import remote_turn  # noqa: E402
import merge_requests  # noqa: E402  (lib/, ajouté par remote_turn)

OPENED: list[dict] = []
SEEN_TOKENS: list[str] = []


class GitLab(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        SEEN_TOKENS.append(self.headers.get("PRIVATE-TOKEN", ""))
        if self.headers.get("PRIVATE-TOKEN") not in ("jeton-reno", "jeton-service"):
            return self.reply(401, {"message": "401 Unauthorized"})
        if self.path.startswith("/api/v4/projects/archi%2Fportail/merge_requests?"):
            branch = self.path.split("source_branch=")[-1]
            return self.reply(200, [m for m in OPENED if m["source_branch"] == branch.replace("%2F", "/")])
        if self.path == "/api/v4/projects/archi%2Fportail":
            return self.reply(200, {"default_branch": "main"})
        return self.reply(404, {"message": "404"})

    def do_POST(self):
        SEEN_TOKENS.append(self.headers.get("PRIVATE-TOKEN", ""))
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        iid = len(OPENED) + 1
        OPENED.append({**body, "iid": iid, "web_url": f"https://gitlab.exemple.local/archi/portail/-/merge_requests/{iid}",
                       "token": self.headers.get("PRIVATE-TOKEN")})
        return self.reply(201, OPENED[-1])


server = ThreadingHTTPServer(("127.0.0.1", 0), GitLab)
threading.Thread(target=server.serve_forever, daemon=True).start()
api = f"http://127.0.0.1:{server.server_address[1]}/api/v4"
config = {"_base": ".", "missions": {"portail": {"repo": "git@gitlab.exemple.local:archi/portail.git"}},
          "access": {"api": api}, "merge_requests": {"labels": ["myskills"]}, "agent": {"command": ["x"]}}
errors = []


def expect(label, got, wanted):
    if got != wanted:
        errors.append(f"{label} : {got!r}, attendu {wanted!r}")


def turn(mode="agent", stages=None, pushed=True, branch="openwebui/c1"):
    report = {**remote_turn.empty_report("portail", "c1", "reno@exemple.local"), "mode": mode, "branch": branch,
              "pushed": pushed, "commit": "abc1234"}
    if stages is not None:
        report["workflows"] = [{"folder": ".", "workflow": "avant-vente", "current": None, "stages": stages}]
    return report


os.environ.pop("GITLAB_MR_TOKEN", None)
expect("tour ordinaire", merge_requests.reason(config, turn(stages={"a": "validee", "b": "en-revue"})), None)
expect("workflow terminé", merge_requests.reason(config, turn(stages={"a": "validee", "b": "sautee"})),
       "workflow terminé")
expect("fin de session", merge_requests.reason(config, turn("fin")), "fin de session")
expect("fin sans push", merge_requests.reason(config, turn("fin", pushed=False)), None)
expect("statut", merge_requests.reason(config, turn("statut", stages={"a": "validee"})), None)
expect("sans section", merge_requests.reason({**config, "merge_requests": None}, turn("fin")), None)
only_end = {**config, "merge_requests": {"on": ["fin"]}}
expect("on: fin seulement", merge_requests.reason(only_end, turn(stages={"a": "validee"})), None)

report = turn("fin")
merge_requests.after_turn(config, "portail", report, user_token="jeton-reno")
merge = report.get("merge_request") or {}
expect("ouverte", merge.get("created"), True)
expect("au nom de l'utilisateur", OPENED[0].get("token") if OPENED else None, "jeton-reno")
expect("cible : branche par défaut", OPENED[0].get("target_branch") if OPENED else None, "main")
expect("étiquettes", OPENED[0].get("labels") if OPENED else None, "myskills")

again = turn(stages={"a": "validee"})
merge_requests.after_turn(config, "portail", again, user_token="jeton-reno")
expect("pas de doublon", (len(OPENED), (again.get("merge_request") or {}).get("created")), (1, False))

os.environ["GITLAB_MR_TOKEN"] = "jeton-service"
other = turn("fin", branch="openwebui/c2")
merge_requests.after_turn({**config, "merge_requests": {"target": "develop"}}, "portail", other)
expect("jeton de secours", OPENED[-1].get("token"), "jeton-service")
expect("cible imposée", OPENED[-1].get("target_branch"), "develop")
expect("agent sans le jeton", "GITLAB_MR_TOKEN" in remote_turn.agent_env(config), False)

os.environ.pop("GITLAB_MR_TOKEN")
missing = turn("fin", branch="openwebui/c3")
merge_requests.after_turn(config, "portail", missing)
expect("sans jeton : avertissement", any("aucun jeton GitLab" in w for w in missing["warnings"]), True)
expect("sans jeton : rien d'ouvert", missing.get("merge_request"), None)

# Service : jeton du pipe lu dans l'en-tête, utilisé par le frontal, jamais par un pod de session.
remote_turn.run_turn = lambda cfg, name, chat, message, emit, user=None, files=None: turn("fin", branch=f"openwebui/{chat}")
for session, chat in ((None, "c4"), (("portail", "c5"), "c5")):
    service = remote_server.Service(config, "jeton-service-myskills", session)
    front = remote_server.start_server(service, "127.0.0.1", 0)
    request = urllib.request.Request(f"http://127.0.0.1:{front.server_address[1]}/turns", method="POST",
                                     data=json.dumps({"mission": "portail", "chat": chat, "message": "/fin"}).encode(),
                                     headers={"Authorization": "Bearer jeton-service-myskills",
                                              "X-Myskills-User": "reno@exemple.local",
                                              "X-Myskills-Gitlab-Token": "jeton-reno"})
    job = json.loads(urllib.request.urlopen(request, timeout=10).read())["job"]
    for _ in range(50):
        if service.jobs[job].report is not None:
            break
        time.sleep(0.1)
    got = (service.jobs[job].report or {}).get("merge_request")
    if session is None:
        expect("frontal : merge request au nom de l'utilisateur", (got or {}).get("created"), True)
        expect("frontal : jeton du pipe", OPENED[-1].get("token"), "jeton-reno")
    else:
        expect("pod de session : rien d'ouvert", got, None)
    front.shutdown()

server.shutdown()
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
