"""Contrôle d'accès de remote-mission face à une API GitLab simulée (locale, aucun réseau).

Usage : python gitlab_droits.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import json
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(sys.argv[1]).resolve().parent / "deploy" / "remote-mission" / "service" / "scripts" / "lib"))
import access  # noqa: E402

USERS = [{"id": 7, "username": "reno", "public_email": "reno@exemple.local"}, {"id": 8, "email": "autre@exemple.local"}]


class GitLab(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        if self.headers.get("PRIVATE-TOKEN") != "jeton-lecture":
            body, code = {"message": "401"}, 401
        elif self.path.startswith("/api/v4/users?search="):
            body, code = USERS, 200
        elif self.path == "/api/v4/users?username=reno":
            body, code = USERS[:1], 200
        elif self.path == "/api/v4/projects/archi%2Fportail/members/all/7":
            body, code = {"access_level": 30}, 200
        else:
            body, code = {"message": "404"}, 404
        data = json.dumps(body).encode()
        self.send_response(code)
        self.end_headers()
        self.wfile.write(data)


server = ThreadingHTTPServer(("127.0.0.1", 0), GitLab)
threading.Thread(target=server.serve_forever, daemon=True).start()
os.environ["GITLAB_ACCESS_TOKEN"] = "jeton-lecture"
config = {"_base": ".", "missions": {"portail": {"repo": "git@gitlab.exemple.local:archi/portail.git"}},
          "access": {"api": f"http://127.0.0.1:{server.server_address[1]}/api/v4", "cache_seconds": 0}}
errors = []


def expect(label, got, wanted):
    if (got is None) != (wanted is None) or (wanted and wanted not in got):
        errors.append(f"{label} : {got!r}, attendu {wanted!r}")


expect("projet tiré de l'URL ssh", access.project_of(config["missions"]["portail"]), "archi/portail")
expect("Developer par courriel public", access.check(config, "portail", "reno@exemple.local", True), None)
expect("Developer par nom", access.check(config, "portail", "reno", True), None)
config["access"]["write_level"] = 40
expect("Maintainer exigé", access.check(config, "portail", "reno", True), "Maintainer requis")
expect("non membre", access.check(config, "portail", "autre@exemple.local", False), "rôle aucun")
expect("inconnu de GitLab", access.check(config, "portail", "x@exemple.local", False), "introuvable")
os.environ["GITLAB_ACCESS_TOKEN"] = "faux"
expect("jeton refusé", access.check(config, "portail", "reno", False), "code 401")
server.shutdown()
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
