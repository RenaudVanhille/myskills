"""Missions découvertes dans GitLab (topic) et choisies depuis Open WebUI, face à une API GitLab simulée.

Modèle unique « Missions » : aide dans une conversation non liée, /missions limité aux missions où
l'utilisateur peut lire, /mission refusé hors du topic ou sans droit d'écriture, liaison gardée par
le service (relue par un service neuf), puis un message joué dans la mission choisie. Agent simulé.

Usage : python decouverte.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

SKILLS = Path(sys.argv[1]).resolve()
HERE = Path(__file__).resolve().parent
OUT = Path(tempfile.mkdtemp(prefix="myskills-decouverte-"))
errors: list[str] = []


def project(path: str, topics: list[str], **extra) -> dict:
    return {"path_with_namespace": path, "name": path.split("/")[-1], "description": f"Mission {path}",
            "http_url_to_repo": str(OUT / "origin"), "web_url": f"https://gitlab.exemple.local/{path}",
            "default_branch": None, "topics": topics, **extra}


PROJECTS = {"archi/portail": project("archi/portail", ["myskills-mission"]),
            "archi/secret": project("archi/secret", ["myskills-mission"]),
            "archi/autre": project("archi/autre", []),
            "archi/vieux": project("archi/vieux", ["myskills-mission"], archived=True)}


class GitLab(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        url = urlparse(self.path)
        path = unquote(url.path)
        if self.headers.get("PRIVATE-TOKEN") != "jeton-lecture":
            body, code = {"message": "401"}, 401
        elif path == "/api/v4/projects" and "topic=myskills-mission" in url.query:
            body, code = [p for p in PROJECTS.values() if "myskills-mission" in p["topics"]], 200
        elif path.startswith("/api/v4/projects/") and "/members/all/" in path:
            project_path = path.split("/api/v4/projects/")[1].split("/members/all/")[0]
            body, code = ({"access_level": 30}, 200) if project_path == "archi/portail" else ({}, 404)
        elif path.startswith("/api/v4/projects/") and path.split("/api/v4/projects/")[1] in PROJECTS:
            body, code = PROJECTS[path.split("/api/v4/projects/")[1]], 200
        elif path == "/api/v4/users":
            body, code = [{"id": 7, "public_email": "dev@exemple.local"}], 200
        else:
            body, code = {"message": "404"}, 404
        data = json.dumps(body).encode()
        self.send_response(code)
        self.end_headers()
        self.wfile.write(data)


def probe(chat: str, message: str) -> dict:
    result = subprocess.run([sys.executable, str(SKILLS / "remote-mission" / "scripts" / "remote_server.py"), "probe",
                             "--config", str(OUT / "remote.json"), "--mission", "missions", "--chat", chat,
                             "--user", "dev@exemple.local", "--message", message],
                            capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "GITLAB_ACCESS_TOKEN": "jeton-lecture", "MOCK_SKILLS": str(SKILLS)})
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"errors": [f"probe illisible : {(result.stderr or result.stdout)[-300:]}"], "output": ""}


def expect(label: str, report: dict, present=(), absent=(), error: str = "") -> None:
    output = report.get("output") or ""
    if error:
        if not any(error in e for e in report.get("errors", [])):
            errors.append(f"{label} : erreur « {error} » attendue ({report.get('errors')})")
    else:
        errors.extend(f"{label} : {e}" for e in report.get("errors", []))
    errors.extend(f"{label} : sortie sans « {t} »" for t in present if t not in output)
    errors.extend(f"{label} : sortie avec « {t} »" for t in absent if t in output)


server = ThreadingHTTPServer(("127.0.0.1", 0), GitLab)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    init = subprocess.run([sys.executable, str(SKILLS / "mission-workspace" / "scripts" / "mission.py"), "init",
                           str(OUT / "origin"), "--nature", "avant-vente", "--name", "Portail"],
                          capture_output=True, text=True, encoding="utf-8")
    if init.returncode:
        errors.append(f"mission.py init : {init.stdout[-300:]}")
    shutil.copyfile(HERE / "mock_agent.py", OUT / "mock_agent.py")
    config = json.loads((HERE / "remote.json").read_text(encoding="utf-8"))
    config["missions"] = {}
    config["access"] = {"provider": "gitlab", "api": f"http://127.0.0.1:{server.server_address[1]}/api/v4"}
    config["allowed_hosts"].append("127.0.0.1")
    config["discovery"] = {"topic": "myskills-mission", "title": "Missions de test"}
    (OUT / "remote.json").write_text(json.dumps(config), encoding="utf-8")

    expect("conversation non liée", probe("d1", "bonjour"), ["n'est liée à aucune mission", "/missions"])
    expect("/missions", probe("d1", "/missions"), ["archi/portail"], ["archi/secret", "archi/autre", "archi/vieux"])
    expect("/mission sans droit", probe("d1", "/mission archi/secret"), error="requis pour ouvrir une session")
    expect("/mission hors topic", probe("d1", "/mission archi/autre"), error="n'est pas une mission")
    expect("/mission", probe("d1", "/mission archi/portail"), ["Mission **archi/portail** choisie"])
    expect("message dans la mission", probe("d1", "dessine le contexte"),
           ["lancement de l'agent", "Branche `openwebui/d1` (poussée)"])
    branches = subprocess.run(["git", "-C", str(OUT / "origin"), "branch", "--list", "openwebui/d1"],
                              capture_output=True, text=True, encoding="utf-8").stdout
    if "openwebui/d1" not in branches:
        errors.append("branche openwebui/d1 absente du dépôt de la mission")
    expect("autre conversation", probe("d2", "dessine"), ["n'est liée à aucune mission"], ["lancement de l'agent"])
finally:
    server.shutdown()
    shutil.rmtree(OUT, ignore_errors=True)
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
