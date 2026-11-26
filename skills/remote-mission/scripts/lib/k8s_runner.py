"""Un tour = un Job Kubernetes : pod à la demande, une seule mission, arrêté à la fin du tour.

Le service (remote_server.py, runner.kind = kubernetes) crée le Job par l'API du cluster, avec
le jeton de son compte de service (bibliothèque standard, aucun client à installer). Le pod
lance remote_turn.py --job : il clone la mission dans un volume vide, joue le tour, fait le
commit et pousse. Ses événements (JSON Lines sur la sortie d'erreur) et son rapport (dernière
ligne de la sortie standard) arrivent par les journaux du pod, lus au fil de l'eau.

Isolation : le pod ne voit que le dépôt de sa mission (jeton git propre à la mission possible,
missions.<nom>.git_secret), sans jeton de l'API Kubernetes ; le Job s'efface après
runner.ttl_seconds. Concurrence : un Job par tour en cours, au plus server.max_jobs.
"""

import hashlib
import json
import re
import secrets
import ssl
import time
import urllib.error
import urllib.request
from pathlib import Path

SA = Path("/var/run/secrets/kubernetes.io/serviceaccount")
SCRIPT = "/opt/myskills/skills/remote-mission/scripts/remote_turn.py"


class Kube:
    def __init__(self, runner: dict):
        self.api = runner.get("api", "https://kubernetes.default.svc").rstrip("/")
        token_file = Path(runner.get("token_file", SA / "token"))
        self.token = token_file.read_text(encoding="utf-8").strip() if token_file.is_file() else ""
        ns_file = SA / "namespace"
        self.namespace = runner.get("namespace") or \
            (ns_file.read_text(encoding="utf-8").strip() if ns_file.is_file() else "default")
        ca = Path(runner.get("ca_file", SA / "ca.crt"))
        self.context = ssl.create_default_context(cafile=str(ca)) if ca.is_file() else None

    def call(self, method: str, path: str, body: dict | None = None, stream: bool = False, timeout: float = 30):
        request = urllib.request.Request(self.api + path, method=method,
                                         data=json.dumps(body).encode("utf-8") if body is not None else None,
                                         headers={"Authorization": f"Bearer {self.token}",
                                                  "Content-Type": "application/json"})
        response = urllib.request.urlopen(request, timeout=timeout, context=self.context)
        return response if stream else json.loads(response.read() or b"{}")


def chat_label(mission: str, chat: str) -> str:
    return hashlib.sha256(f"{mission}\0{chat}".encode("utf-8")).hexdigest()[:16]


def manifest(config: dict, mission: str, chat: str, message: str, user: str | None, name: str) -> dict:
    runner = config["runner"]
    entry = config["missions"][mission]
    git_secret = entry.get("git_secret", runner.get("git_secret", "myskills-git"))
    labels = {"app": "myskills-turn", "myskills/mission": re.sub(r"[^a-z0-9-]", "-", mission.lower())[:63],
              "myskills/chat": chat_label(mission, chat)}
    command = ["uv", "run", "--quiet", runner.get("script", SCRIPT), "--job",
               "--config", runner.get("config_path", "/etc/myskills/remote.json"), "--workdir", "/work",
               "--mission", mission, "--chat", chat, "--message-env", "MYSKILLS_MESSAGE"]
    if user:
        command += ["--user", user]
    env = [{"name": "MYSKILLS_MESSAGE", "value": message},
           {"name": "GIT_CONFIG_COUNT", "value": "1"},
           {"name": "GIT_CONFIG_KEY_0", "value": "credential.helper"},
           {"name": "GIT_CONFIG_VALUE_0", "value": "store --file=/etc/myskills-git/.git-credentials"}]
    timeout = config["agent"].get("timeout", 3600)
    return {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "labels": labels},
        "spec": {
            "backoffLimit": 0,  # un tour ne se rejoue pas tout seul : il a pu pousser
            "activeDeadlineSeconds": timeout + 600,
            "ttlSecondsAfterFinished": runner.get("ttl_seconds", 900),
            "template": {
                "metadata": {"labels": labels},
                "spec": {
                    "restartPolicy": "Never",
                    "automountServiceAccountToken": False,
                    "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "fsGroup": 10001,
                                        "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{
                        "name": "tour", "image": runner["image"], "command": command, "env": env,
                        "envFrom": [{"secretRef": {"name": runner.get("secret", "myskills-turn")}}],
                        "resources": runner.get("resources", {"requests": {"cpu": "500m", "memory": "1Gi"},
                                                              "limits": {"memory": "4Gi"}}),
                        "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                        "volumeMounts": [{"name": "config", "mountPath": "/etc/myskills", "readOnly": True},
                                         {"name": "git", "mountPath": "/etc/myskills-git", "readOnly": True},
                                         {"name": "work", "mountPath": "/work"}]}],
                    "volumes": [{"name": "config", "configMap": {"name": runner.get("config_map", "myskills-remote")}},
                                {"name": "git", "secret": {"secretName": git_secret, "defaultMode": 0o400}},
                                {"name": "work", "emptyDir": {"sizeLimit": runner.get("work_size", "10Gi")}}]}}}}


def active_job(kube: Kube, mission: str, chat: str) -> str | None:
    """Job encore actif de la conversation (après un redémarrage du service, par exemple)."""
    found = kube.call("GET", f"/apis/batch/v1/namespaces/{kube.namespace}/jobs"
                             f"?labelSelector=myskills/chat%3D{chat_label(mission, chat)}")
    for job in found.get("items", []):
        if job.get("status", {}).get("active"):
            return job["metadata"]["name"]
    return None


def wait_pod(kube: Kube, name: str, emit, limit: float = 600) -> tuple[str | None, str]:
    started = time.monotonic()
    while time.monotonic() - started < limit:
        pods = kube.call("GET", f"/api/v1/namespaces/{kube.namespace}/pods?labelSelector=job-name%3D{name}")
        for pod in pods.get("items", []):
            phase = pod.get("status", {}).get("phase", "Pending")
            if phase != "Pending":
                return pod["metadata"]["name"], phase
        time.sleep(2)
    return None, "Pending"


def run(config: dict, mission: str, chat: str, message: str, user: str | None, emit, empty: dict) -> dict:
    """Crée le Job du tour, suit les journaux de son pod et rend le rapport de remote_turn.py."""
    kube = Kube(config["runner"])
    report = dict(empty)
    try:
        if active_job(kube, mission, chat):
            report["errors"].append("un tour de cette conversation tourne encore dans le cluster ; réessayez ensuite")
            return report
        name = f"myskills-tour-{chat_label(mission, chat)[:8]}-{secrets.token_hex(3)}"
        kube.call("POST", f"/apis/batch/v1/namespaces/{kube.namespace}/jobs",
                  manifest(config, mission, chat, message, user, name))
        emit("pod", "démarrage du pod du tour")
        pod, phase = wait_pod(kube, name, emit)
        if pod is None:
            report["errors"].append(f"pod du Job {name} toujours en attente (image, quota, nœud ?)")
            return report
        final = None
        logs = kube.call("GET", f"/api/v1/namespaces/{kube.namespace}/pods/{pod}/log?follow=true",
                         stream=True, timeout=config["agent"].get("timeout", 3600) + 900)
        for raw in logs:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("{"):
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if {"kind", "text"} <= data.keys():
                emit(data["kind"], data["text"])
            elif {"mission", "errors", "warnings"} <= data.keys():
                final = data
        if final is None:
            report["errors"].append(f"pod {pod} terminé sans rapport (journaux : kubectl logs {pod})")
            return report
        return final
    except (urllib.error.URLError, OSError, ValueError, KeyError) as error:
        report["errors"].append(f"API Kubernetes : {error}")
        return report
