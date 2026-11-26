"""Pod de session par conversation (runner kubernetes de remote-mission), face à une API simulée.

L'API simulée (locale) reçoit le volume et le pod de la session, lance la commande du conteneur
sur la machine (chemins du pod remplacés par un dossier par volume, port libre), et sert l'état du
pod. Chaque message passe par la fonction Pipe d'Open WebUI et un service frontal neuf
(remote_server.py probe), comme après un redémarrage. Aucun modèle : agent simulé.

Vérifie : session démarrée, pod retrouvé au message suivant (contexte de l'agent repris), pod
arrêté (inactivité) puis rechargé depuis son volume avec le contexte, droits vérifiés au début de
la session (Reporter refusé sans pod créé) et avant le push (pas à chaque message), « /fin » qui
efface pod et volume.

Usage : python kube_session.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

SKILLS = Path(sys.argv[1]).resolve()
HERE = Path(__file__).resolve().parent
OUT = Path(tempfile.mkdtemp(prefix="myskills-session-"))
PODS: dict[str, dict] = {}
CLAIMS: dict[str, dict] = {}
CREATED = {"pods": 0}
errors: list[str] = []


def free_port() -> int:
    with socket.socket() as probe_socket:
        probe_socket.bind(("127.0.0.1", 0))
        return probe_socket.getsockname()[1]


def start_pod(spec: dict) -> dict:
    name = spec["metadata"]["name"]
    container = spec["spec"]["containers"][0]
    port = free_port()
    volume = OUT / f"pvc-{name}"
    command = [sys.executable] + container["command"][3:]  # uv run --quiet -> python
    command = [str(port) if c == "8765" else str(volume / "clones") if c == "/work/clones" else c for c in command]
    container["ports"][0]["containerPort"] = port
    env = {**os.environ, **{e["name"]: e["value"] for e in container["env"]}, "HOME": str(volume / "home")}
    log = (OUT / f"{name}.log").open("a", encoding="utf-8")
    process = subprocess.Popen(command, env=env, stdout=log, stderr=log)
    CREATED["pods"] += 1
    return {"spec": spec, "process": process, "log": log}


def pod_view(name: str) -> dict:
    pod = PODS[name]
    code = pod["process"].poll()
    phase = "Running" if code is None else "Succeeded" if code == 0 else "Failed"
    return {**pod["spec"], "status": {"phase": phase, "podIP": "127.0.0.1"}}


class Kube(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def reply(self, body, code=200):
        data = json.dumps(body).encode()
        self.send_response(code)
        self.end_headers()
        self.wfile.write(data)

    def route(self):
        if self.headers.get("Authorization") != "Bearer jeton-sa":
            return None, None
        url = urlparse(self.path)
        parts = url.path.strip("/").split("/")
        return parts, unquote(parse_qs(url.query).get("labelSelector", [""])[0])

    def do_GET(self):
        parts, selector = self.route()
        if parts is None:
            return self.reply({"message": "Unauthorized"}, 401)
        if parts[-2] == "pods" and parts[-1] in PODS:
            return self.reply(pod_view(parts[-1]))
        if parts[-1] == "persistentvolumeclaims":
            key, _, value = selector.partition("=")
            return self.reply({"items": [c for c in CLAIMS.values() if c["metadata"]["labels"].get(key) == value]})
        if parts[-2] == "persistentvolumeclaims" and parts[-1] in CLAIMS:
            return self.reply(CLAIMS[parts[-1]])
        return self.reply({"message": "not found"}, 404)

    def do_POST(self):
        parts, _ = self.route()
        spec = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        name = spec["metadata"]["name"]
        if parts[-1] == "persistentvolumeclaims":
            CLAIMS[name] = spec
            (OUT / f"pvc-{name}").mkdir(exist_ok=True)
        elif parts[-1] == "pods":
            if spec["spec"].get("automountServiceAccountToken") is not False:
                errors.append("pod de session avec le jeton de l'API Kubernetes")
            if spec["spec"]["volumes"][-1].get("persistentVolumeClaim", {}).get("claimName") not in CLAIMS:
                errors.append("pod de session sans son volume")
            init = (spec["spec"].get("initContainers") or [{}])[0]
            if "sync" not in init.get("command", []) or {"name": "HOME", "value": "/work/home"} not in init.get("env", []):
                errors.append("pod de session sans copie des skills dans son HOME (initContainer)")
            PODS[name] = start_pod(spec)
        return self.reply(spec, 201)

    def do_PATCH(self):
        parts, _ = self.route()
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        if parts[-2] == "persistentvolumeclaims" and parts[-1] in CLAIMS:
            CLAIMS[parts[-1]]["metadata"]["annotations"].update(body["metadata"]["annotations"])
            return self.reply(CLAIMS[parts[-1]])
        return self.reply({"message": "not found"}, 404)

    def do_DELETE(self):
        parts, _ = self.route()
        name = parts[-1]
        if parts[-2] == "pods" and name in PODS:
            pod = PODS.pop(name)
            pod["process"].terminate()
            pod["process"].wait(10)
            pod["log"].close()
            return self.reply({})
        if parts[-2] == "persistentvolumeclaims" and name in CLAIMS:
            CLAIMS.pop(name)
            shutil.rmtree(OUT / f"pvc-{name}", ignore_errors=True)
            return self.reply({})
        return self.reply({"message": "not found"}, 404)


def probe(user: str, message: str, chat: str = "s1") -> dict:
    result = subprocess.run([sys.executable, str(SKILLS / "remote-mission" / "scripts" / "remote_server.py"), "probe",
                             "--config", str(OUT / "remote.json"), "--mission", "portail", "--chat", chat,
                             "--user", user, "--message", message, "--pipe", str(SKILLS.parent / "deploy" / "remote-mission" / "openwebui_pipe.py")],
                            capture_output=True, text=True, encoding="utf-8")
    try:
        return json.loads(result.stdout)
    except ValueError:
        return {"errors": [f"probe illisible : {(result.stderr or result.stdout)[-300:]}"], "output": ""}


def expect(label: str, report: dict, texts: list[str], pods: int) -> None:
    errors.extend(f"{label} : {e}" for e in report.get("errors", []))
    errors.extend(f"{label} : sortie sans « {t} »" for t in texts if t not in (report.get("output") or ""))
    if CREATED["pods"] != pods:
        errors.append(f"{label} : {CREATED['pods']} pods créés, {pods} attendus")


os.environ["MOCK_SKILLS"] = str(SKILLS)
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
    config["access"]["cache_seconds"] = 0  # droits relus à chaque contrôle (retrait en cours de session)
    config["runner"] = {"kind": "kubernetes", "image": "registry.exemple.local/myskills/remote-mission:test",
                        "api": f"http://127.0.0.1:{server.server_address[1]}", "token_file": str(OUT / "token"),
                        "namespace": "myskills", "config_path": str(OUT / "remote.json"), "idle_minutes": 30,
                        "script": str(SKILLS / "remote-mission" / "scripts" / "remote_server.py")}
    (OUT / "remote.json").write_text(json.dumps(config), encoding="utf-8")

    expect("premier message", probe("dev@exemple.local", "dessine le contexte"),
           ["démarrage de la session", "lancement de l'agent", "nouvelle session", "(poussée)", "data:image/png"], 1)
    expect("pod retrouvé", probe("dev@exemple.local", "complète le schéma"),
           ["reprise de la session de l'agent", "suite de session"], 1)
    for pod in PODS.values():  # arrêt après inactivité
        pod["process"].terminate()
        pod["process"].wait(10)
    expect("session rechargée", probe("dev@exemple.local", "où en est-on ?"),
           ["rechargement de la session", "reprise de la session de l'agent", "suite de session"], 2)
    refused = probe("lecteur@exemple.local", "dessine", chat="s2")
    if not any("requis pour ouvrir une session" in e for e in refused.get("errors", [])) or CREATED["pods"] != 2:
        errors.append(f"Reporter, nouvelle session : refus attendu sans pod créé ({refused.get('errors')})")
    # Droit retiré pendant la session : le message passe (pas de contrôle par message), le push est refusé.
    (OUT / "acces.json").write_text(json.dumps({"portail": {"dev@exemple.local": 20}}), encoding="utf-8")
    pushed = probe("dev@exemple.local", "dessine")
    if not any("requis pour pousser sur le dépôt" in e for e in pushed.get("errors", [])) \
            or "suite de session" not in (pushed.get("output") or "") or CREATED["pods"] != 2:
        errors.append(f"droit retiré en session : message traité, push refusé attendus ({pushed.get('errors')})")
    shutil.copyfile(HERE / "acces.json", OUT / "acces.json")
    expect("fin de session", probe("dev@exemple.local", "/fin"), ["Session terminée"], 2)
    if PODS or CLAIMS:
        errors.append(f"/fin : pod ou volume restant ({list(PODS)}, {list(CLAIMS)})")
    # Mission choisie par /mission (modèle Missions) : liaison gardée sur le volume, relue par un service neuf.
    sys.path.insert(0, str(SKILLS / "remote-mission" / "scripts" / "lib"))
    import k8s_sessions  # noqa: E402
    config["_base"] = str(OUT)
    k8s_sessions.Sessions(config).bind("portail", "s9")
    if k8s_sessions.Sessions(config).bound_mission("s9") != "portail" or \
            k8s_sessions.Sessions(config).bound_mission("s10") is not None:
        errors.append("liaison conversation -> mission non relue sur le volume de session")
finally:
    server.shutdown()
    for pod in PODS.values():
        pod["process"].kill()
        pod["log"].close()
    if errors:  # journaux des pods pour comprendre l'échec
        for log in OUT.glob("*.log"):
            errors.append(f"{log.name} : {log.read_text(encoding='utf-8')[-400:]}")
    shutil.rmtree(OUT, ignore_errors=True)
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
