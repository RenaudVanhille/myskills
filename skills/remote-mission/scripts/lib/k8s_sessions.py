"""Une session = un pod Kubernetes par conversation, vivant tant que la conversation est active.

Le service frontal (remote_server.py, runner.kind = kubernetes) garde la main sur les droits et
crée, retrouve ou recharge le pod de la conversation par l'API du cluster (bibliothèque standard,
jeton de son compte de service). Le pod lance remote_server.py serve --session : il joue les
tours de cette seule conversation, l'agent reprend sa session à chaque message (contexte gardé),
et il s'arrête seul après runner.idle_minutes sans message.

Le volume de la session (PVC) garde la copie de travail et le contexte de l'agent (HOME) : quand
l'utilisateur revient, un nouveau pod monte le même volume et la session est rechargée. « /fin »
pousse, arrête le pod et efface le volume ; un volume sans pod depuis runner.retention_days est
effacé (le travail reste sur la branche).
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
SERVER = "/opt/myskills/skills/remote-mission/scripts/remote_server.py"


def chat_label(mission: str, chat: str) -> str:
    return hashlib.sha256(f"{mission}\0{chat}".encode("utf-8")).hexdigest()[:16]


def conversation_label(chat: str) -> str:
    return hashlib.sha256(chat.encode("utf-8")).hexdigest()[:16]


class Sessions:
    def __init__(self, config: dict):
        self.config, self.runner = config, config["runner"]
        self.api = self.runner.get("api", "https://kubernetes.default.svc").rstrip("/")
        token_file = Path(self.runner.get("token_file", SA / "token"))
        self.token = token_file.read_text(encoding="utf-8").strip() if token_file.is_file() else ""
        ns_file = SA / "namespace"
        self.ns = self.runner.get("namespace") or \
            (ns_file.read_text(encoding="utf-8").strip() if ns_file.is_file() else "default")
        ca = Path(self.runner.get("ca_file", SA / "ca.crt"))
        self.context = ssl.create_default_context(cafile=str(ca)) if ca.is_file() else None

    # --- API du cluster -------------------------------------------------------------------
    def call(self, method: str, path: str, body: dict | None = None, patch: bool = False):
        """Réponse JSON, ou None sur 404."""
        kind = "application/merge-patch+json" if patch else "application/json"
        request = urllib.request.Request(self.api + path, method=method,
                                         data=json.dumps(body).encode("utf-8") if body is not None else None,
                                         headers={"Authorization": f"Bearer {self.token}", "Content-Type": kind})
        try:
            with urllib.request.urlopen(request, timeout=30, context=self.context) as response:
                return json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            if error.code == 404:
                return None
            raise

    def pods(self, name: str = "") -> str:
        return f"/api/v1/namespaces/{self.ns}/pods" + (f"/{name}" if name else "")

    def claims(self, name: str = "") -> str:
        return f"/api/v1/namespaces/{self.ns}/persistentvolumeclaims" + (f"/{name}" if name else "")

    # --- définition du pod et du volume -----------------------------------------------------
    def labels(self, mission: str, chat: str) -> dict:
        return {"app": "myskills-session", "myskills/chat": chat_label(mission, chat),
                "myskills/conv": conversation_label(chat),
                "myskills/mission": re.sub(r"[^a-z0-9-]", "-", mission.lower()).strip("-")[:63] or "mission"}

    def claim(self, name: str, mission: str, chat: str) -> dict:
        spec = {"accessModes": ["ReadWriteOnce"],
                "resources": {"requests": {"storage": self.runner.get("session_size", "5Gi")}}}
        if self.runner.get("storage_class"):
            spec["storageClassName"] = self.runner["storage_class"]
        return {"apiVersion": "v1", "kind": "PersistentVolumeClaim",
                "metadata": {"name": name, "labels": self.labels(mission, chat),
                             "annotations": {"myskills/last-used": str(int(time.time())),
                                             "myskills/mission-path": mission}},
                "spec": spec}

    def pod(self, name: str, mission: str, chat: str) -> dict:
        runner, entry = self.runner, self.config["missions"][mission]
        command = ["uv", "run", "--quiet", runner.get("script", SERVER), "serve",
                   "--config", runner.get("config_path", "/etc/myskills/remote.json"),
                   "--host", "0.0.0.0", "--port", "8765", "--workdir", "/work/clones",
                   "--session", f"{mission}:{chat}", "--idle-minutes", str(runner.get("idle_minutes", 120))]
        env = [{"name": "MYSKILLS_REMOTE_TOKEN", "value": secrets.token_urlsafe(24)},
               {"name": "MYSKILLS_MISSION_SPEC", "value": json.dumps(entry, ensure_ascii=False)},  # mission découverte
               {"name": "HOME", "value": "/work/home"},  # contexte de l'agent (claude --continue) sur le volume
               {"name": "GIT_CONFIG_COUNT", "value": "1"},
               {"name": "GIT_CONFIG_KEY_0", "value": "credential.helper"},
               {"name": "GIT_CONFIG_VALUE_0", "value": "store --file=/etc/myskills-git/.git-credentials"}]
        return {
            "apiVersion": "v1", "kind": "Pod",
            "metadata": {"name": name, "labels": self.labels(mission, chat)},
            "spec": {
                "restartPolicy": "Never",  # arrêt après inactivité : la session se recharge au message suivant
                "automountServiceAccountToken": False,
                "securityContext": {"runAsNonRoot": True, "runAsUser": 10001, "fsGroup": 10001,
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "session", "image": runner["image"], "command": command, "env": env,
                    "ports": [{"containerPort": 8765}],
                    "envFrom": [{"secretRef": {"name": runner.get("secret", "myskills-session")}}],
                    "resources": runner.get("resources", {"requests": {"cpu": "250m", "memory": "1Gi"},
                                                          "limits": {"memory": "4Gi"}}),
                    "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                    "volumeMounts": [{"name": "config", "mountPath": "/etc/myskills", "readOnly": True},
                                     {"name": "git", "mountPath": "/etc/myskills-git", "readOnly": True},
                                     {"name": "work", "mountPath": "/work"}]}],
                "volumes": [
                    {"name": "config", "configMap": {"name": runner.get("config_map", "myskills-remote")}},
                    {"name": "git", "secret": {"secretName": entry.get("git_secret", runner.get("git_secret", "myskills-git")),
                                               "defaultMode": 0o400}},
                    {"name": "work", "persistentVolumeClaim": {"claimName": name}}]}}

    # --- cycle de vie -----------------------------------------------------------------------
    @staticmethod
    def name(mission: str, chat: str) -> str:
        return f"myskills-session-{chat_label(mission, chat)}"

    def address(self, pod: dict) -> tuple[str, str] | None:
        """URL et jeton du pod prêt, ou None."""
        ip = pod.get("status", {}).get("podIP")
        if pod.get("status", {}).get("phase") != "Running" or not ip:
            return None
        container = pod["spec"]["containers"][0]
        port = container.get("ports", [{}])[0].get("containerPort", 8765)
        token = next(e["value"] for e in container["env"] if e["name"] == "MYSKILLS_REMOTE_TOKEN")
        return f"http://{ip}:{port}", token

    def healthy(self, url: str) -> bool:
        try:
            with urllib.request.urlopen(url + "/health", timeout=5) as response:
                return response.status == 200
        except OSError:
            return False

    def bind(self, mission: str, chat: str) -> None:
        """Conversation liée à une mission (/mission) : son volume est créé et garde la liaison."""
        name = self.name(mission, chat)
        if self.call("GET", self.claims(name)) is None:
            self.call("POST", self.claims(), self.claim(name, mission, chat))

    def bound_mission(self, chat: str) -> str | None:
        """Mission liée à la conversation, lue sur son volume (après un redémarrage du service)."""
        found = self.call("GET", self.claims() + f"?labelSelector=myskills%2Fconv%3D{conversation_label(chat)}") or {}
        for claim in found.get("items", []):
            mission = claim["metadata"].get("annotations", {}).get("myskills/mission-path")
            if mission:
                return mission
        return None

    def running(self, mission: str, chat: str) -> bool:
        """Session en cours : son pod tourne (sinon elle démarre ou se recharge)."""
        pod = self.call("GET", self.pods(self.name(mission, chat))) or {}
        return pod.get("status", {}).get("phase") == "Running"

    def ensure(self, mission: str, chat: str, emit) -> tuple[str, str]:
        """Pod prêt de la conversation : retrouvé, créé ou rechargé depuis son volume."""
        name = self.name(mission, chat)
        self.collect(keep=name)
        pod = self.call("GET", self.pods(name))
        if pod and pod.get("status", {}).get("phase") in ("Succeeded", "Failed"):
            self.call("DELETE", self.pods(name))  # arrêtée après inactivité : rechargée ci-dessous
            for _ in range(60):
                if self.call("GET", self.pods(name)) is None:
                    break
                time.sleep(1)
            pod = None
        if pod is None:
            existing = self.call("GET", self.claims(name))
            if existing is None:
                self.call("POST", self.claims(), self.claim(name, mission, chat))
            emit("session", "rechargement de la session" if existing else "démarrage de la session")
            self.call("POST", self.pods(), self.pod(name, mission, chat))
        self.call("PATCH", self.claims(name), {"metadata": {"annotations": {"myskills/last-used": str(int(time.time()))}}},
                  patch=True)
        limit = time.monotonic() + self.runner.get("startup_seconds", 300)
        while time.monotonic() < limit:
            pod = self.call("GET", self.pods(name)) or {}
            found = self.address(pod)
            if found and self.healthy(found[0]):
                return found
            if pod.get("status", {}).get("phase") in ("Succeeded", "Failed"):
                raise RuntimeError(f"pod {name} arrêté au démarrage (kubectl logs {name})")
            time.sleep(2)
        raise RuntimeError(f"pod {name} pas prêt après {self.runner.get('startup_seconds', 300)} s (image, quota, volume ?)")

    def end(self, mission: str, chat: str) -> None:
        name = self.name(mission, chat)
        self.call("DELETE", self.pods(name))
        self.call("DELETE", self.claims(name))

    def collect(self, keep: str = "") -> list[str]:
        """Efface les volumes de session sans pod, inutilisés depuis runner.retention_days."""
        horizon = time.time() - self.runner.get("retention_days", 14) * 86400
        found = self.call("GET", self.claims() + "?labelSelector=app%3Dmyskills-session") or {}
        removed = []
        for claim in found.get("items", []):
            name = claim["metadata"]["name"]
            used = int(claim["metadata"].get("annotations", {}).get("myskills/last-used", "0") or 0)
            if name != keep and used < horizon and self.call("GET", self.pods(name)) is None:
                self.call("DELETE", self.claims(name))
                removed.append(name)
        return removed
