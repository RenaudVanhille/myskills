"""Tour joué dans un Job Kubernetes (runner kubernetes de remote-mission), face à une API simulée.

L'API simulée (locale) reçoit le Job, lance la commande de son conteneur sur la machine (chemins
du pod remplacés par ceux du test), sert ses journaux comme ceux d'un pod. Le message passe par
la fonction Pipe d'Open WebUI et le service (remote_server.py probe). Aucun modèle : agent simulé.

Usage : python kube_job.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
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
from urllib.parse import parse_qs, unquote, urlparse

SKILLS = Path(sys.argv[1]).resolve()
HERE = Path(__file__).resolve().parent
OUT = Path(tempfile.mkdtemp(prefix="myskills-kube-"))
JOBS: dict[str, dict] = {}
errors: list[str] = []


def run_pod(name: str) -> None:
    job = JOBS[name]
    container = job["spec"]["spec"]["template"]["spec"]["containers"][0]
    command = [sys.executable] + container["command"][3:]  # uv run --quiet -> python
    command = [str(OUT / f"work-{name}") if c == "/work" else c for c in command]
    env = {**os.environ, **{e["name"]: e["value"] for e in container["env"]}}
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env)
    job["log"] = (result.stderr + result.stdout).encode("utf-8")
    job["phase"] = "Succeeded" if result.returncode == 0 else "Failed"
    job["done"].set()


class Kube(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, code=200):
        data = body if isinstance(body, bytes) else json.dumps(body).encode()
        self.send_response(code)
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer jeton-sa":
            return self.reply({"message": "Unauthorized"}, 401)
        url = urlparse(self.path)
        selector = unquote(parse_qs(url.query).get("labelSelector", [""])[0])
        if url.path == "/apis/batch/v1/namespaces/myskills/jobs":
            key, _, value = selector.partition("=")
            items = [{"metadata": {"name": n}, "status": {"active": 0 if j["done"].is_set() else 1}}
                     for n, j in JOBS.items() if j["spec"]["metadata"]["labels"].get(key) == value]
            return self.reply({"items": items})
        if url.path == "/api/v1/namespaces/myskills/pods":
            name = selector.partition("=")[2]
            job = JOBS.get(name)
            items = [{"metadata": {"name": f"{name}-pod"}, "status": {"phase": job["phase"]}}] if job else []
            return self.reply({"items": items})
        if url.path.startswith("/api/v1/namespaces/myskills/pods/") and url.path.endswith("/log"):
            name = url.path.split("/")[-2].removesuffix("-pod")
            JOBS[name]["done"].wait(120)
            return self.reply(JOBS[name]["log"])
        return self.reply({"message": "not found"}, 404)

    def do_POST(self):
        spec = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        name = spec["metadata"]["name"]
        JOBS[name] = {"spec": spec, "phase": "Running", "log": b"", "done": threading.Event()}
        threading.Thread(target=run_pod, args=(name,), daemon=True).start()
        return self.reply(spec, 201)


def probe(user: str, chat: str, message: str) -> dict:
    result = subprocess.run([sys.executable, str(SKILLS / "remote-mission" / "scripts" / "remote_server.py"), "probe",
                             "--config", str(OUT / "remote.json"), "--mission", "portail", "--chat", chat,
                             "--user", user, "--message", message],
                            capture_output=True, text=True, encoding="utf-8",
                            env={**os.environ, "MOCK_SKILLS": str(SKILLS)})
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"errors": [f"probe illisible : {(result.stderr or result.stdout)[-300:]}"], "output": ""}


server = ThreadingHTTPServer(("127.0.0.1", 0), Kube)
threading.Thread(target=server.serve_forever, daemon=True).start()
try:
    init = subprocess.run([sys.executable, str(SKILLS / "mission-workspace" / "scripts" / "mission.py"), "init",
                           str(OUT / "origin"), "--nature", "avant-vente", "--name", "Portail"],
                          capture_output=True, text=True, encoding="utf-8")
    if init.returncode:
        errors.append(f"mission.py init : {init.stdout[-300:]}")
    for name in ("acces.json", "mock_agent.py"):
        shutil.copyfile(HERE / name, OUT / name)
    (OUT / "token").write_text("jeton-sa", encoding="utf-8")
    config = json.loads((HERE / "remote.json").read_text(encoding="utf-8"))
    config["runner"] = {"kind": "kubernetes", "image": "registry.exemple.local/myskills/remote-mission:test",
                        "api": f"http://127.0.0.1:{server.server_address[1]}", "token_file": str(OUT / "token"),
                        "namespace": "myskills", "config_path": str(OUT / "remote.json"),
                        "script": str(SKILLS / "remote-mission" / "scripts" / "remote_turn.py")}
    (OUT / "remote.json").write_text(json.dumps(config), encoding="utf-8")

    report = probe("dev@exemple.local", "k1", "dessine le contexte")
    errors += [f"tour dans un pod : {e}" for e in report.get("errors", [])]
    for text in ("démarrage du pod", "lancement de l'agent", "Branche `openwebui/k1` (poussée)", "data:image/png"):
        if text not in (report.get("output") or ""):
            errors.append(f"sortie du pipe sans « {text} »")
    pod = next(iter(JOBS.values()), None)
    if pod is None:
        errors.append("aucun Job créé")
    else:
        spec = pod["spec"]["spec"]["template"]["spec"]
        command = spec["containers"][0]["command"]
        checks = {"pod sans jeton de l'API Kubernetes": spec.get("automountServiceAccountToken") is False,
                  "message passé par variable": "MYSKILLS_MESSAGE" in {e["name"] for e in spec["containers"][0]["env"]},
                  "remote_turn.py --job": "--job" in command and "--message-env" in command,
                  "Job non rejoué": pod["spec"]["spec"].get("backoffLimit") == 0,
                  "Job effacé après le tour": pod["spec"]["spec"].get("ttlSecondsAfterFinished", 0) > 0,
                  "volume de travail vide": any("emptyDir" in v for v in spec["volumes"])}
        errors += [f"Job : {label}" for label, ok in checks.items() if not ok]
    created = len(JOBS)
    refused = probe("lecteur@exemple.local", "k2", "dessine")
    if not any("Developer requis" in e for e in refused.get("errors", [])):
        errors.append(f"Reporter non refusé avant le Job : {refused.get('errors')}")
    if len(JOBS) != created:
        errors.append("Job créé pour un utilisateur sans droit")
finally:
    server.shutdown()
    shutil.rmtree(OUT, ignore_errors=True)
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
