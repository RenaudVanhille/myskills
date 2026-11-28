"""
title: Missions myskills
description: Une mission myskills par modèle ; chaque message est un tour joué par le service remote_server.py (skill remote-mission).
version: 0.1.0
license: MIT
"""

# Fonction « Pipe » d'Open WebUI, installée et réglée d'elle-même par chart/files/openwebui_install.py
# (servie par GET /openwebui/pipe ; import manuel possible : Admin > Fonctions). Bibliothèque standard
# seulement : aucun paquet à installer dans Open WebUI. Le pipe ne parle qu'au service
# remote_server.py (adresse interne du cluster) ; aucun contenu ne part ailleurs.

import asyncio
import json
import re
import urllib.error
import urllib.request
from urllib.parse import quote

try:
    from pydantic import BaseModel
except ImportError:  # hors d'Open WebUI (remote_server.py probe)
    class BaseModel:
        def __init__(self, **values):
            for name in dir(type(self)):
                if name.isupper():
                    setattr(self, name, values.get(name, getattr(type(self), name)))


class Pipe:
    class Valves(BaseModel):
        SERVER_URL: str = "http://myskills-remote.myskills.svc.cluster.local:8765"
        TOKEN: str = ""
        POLL_SECONDS: int = 20
        MAX_MINUTES: int = 180

    def __init__(self):
        self.type = "manifold"
        self.name = "mission "
        self.valves = self.Valves()

    # --- appels au service -------------------------------------------------------------
    def _call(self, method: str, path: str, payload: dict | None = None, timeout: float = 30,
              user: str = "", gitlab_token: str = "") -> tuple[int, dict]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        headers = {"Authorization": f"Bearer {self.valves.TOKEN}", "Content-Type": "application/json"}
        if user:  # le service lit les droits de cet utilisateur sur le projet GitLab de la mission
            headers["X-Myskills-User"] = user
        if gitlab_token:  # jeton GitLab de la connexion de l'utilisateur : merge request ouverte en son nom
            headers["X-Myskills-Gitlab-Token"] = gitlab_token
        request = urllib.request.Request(self.valves.SERVER_URL.rstrip("/") + path, data=data, method=method,
                                         headers=headers)
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read() or b"{}")
            except ValueError:
                return error.code, {"error": str(error)}

    async def _acall(self, *args, **kwargs) -> tuple[int, dict]:
        return await asyncio.to_thread(self._call, *args, **kwargs)

    def _upload(self, chat: str, user: str, name: str, data: bytes) -> tuple[int, dict]:
        request = urllib.request.Request(
            self.valves.SERVER_URL.rstrip("/") + f"/uploads?chat={quote(chat, safe='')}", data=data, method="POST",
            headers={"Authorization": f"Bearer {self.valves.TOKEN}", "X-Myskills-User": user,
                     "X-Myskills-Filename": quote(name), "Content-Type": "application/octet-stream"})
        try:
            with urllib.request.urlopen(request, timeout=300) as response:
                return response.status, json.loads(response.read() or b"{}")
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read() or b"{}")
            except ValueError:
                return error.code, {"error": str(error)}

    @staticmethod
    async def _file_bytes(item: dict) -> tuple[str, bytes]:
        """Nom et contenu d'un fichier joint, lus dans le stockage d'Open WebUI (le pipe tourne chez lui)."""
        from open_webui.models.files import Files
        from open_webui.storage.provider import Storage

        meta = item.get("file") if isinstance(item.get("file"), dict) else item
        found = Files.get_file_by_id(meta.get("id") or item.get("id"))
        found = await found if asyncio.iscoroutine(found) else found
        if found is None or not found.path:
            raise FileNotFoundError(item.get("name") or meta.get("filename") or "fichier")
        path = await asyncio.to_thread(Storage.get_file, found.path)
        data = await asyncio.to_thread(lambda: open(path, "rb").read())
        return found.filename or (found.meta or {}).get("name") or "fichier", data

    def pipes(self) -> list[dict]:
        try:
            code, data = self._call("GET", "/missions", timeout=10)
        except OSError as error:
            return [{"id": "indisponible", "name": f"service injoignable ({error})"}]
        if code != 200:
            return [{"id": "indisponible", "name": data.get("error", f"service : code {code}")}]
        return [{"id": m["id"], "name": m["title"]} for m in data["missions"]]

    # --- rendu ------------------------------------------------------------------------
    @staticmethod
    def render(report: dict) -> str:
        parts = []
        if report.get("shortcut"):
            done = report["shortcut"]
            word = "validée" if done["decision"] == "valide" else "renvoyée avec votre retour"
            parts.append(f"Étape **{done['stage']}** {word}.")
        if report.get("uploaded"):
            parts.append("Fichiers ajoutés à la mission : " + ", ".join(f"`{f}`" for f in report["uploaded"]) + ".")
        if report.get("answer"):
            parts.append(report["answer"])
        if report.get("mode") == "fin" and not report.get("errors"):
            parts.append("Session terminée : le travail est poussé sur la branche, la session est effacée. "
                         "Un nouveau message ouvre une session neuve.")
        if report.get("mode") == "statut":
            for wf in report.get("workflows", []):
                steps = ", ".join(f"{s} ({v})" for s, v in wf["stages"].items())
                parts.append(f"**{wf['workflow'] or wf['folder']}** : {steps}")
            if not report.get("workflows"):
                parts.append("Aucun workflow démarré dans cette mission.")
        for image in report.get("images", []):
            src = image.get("data") or image.get("url")
            if src:
                parts.append(f"![{image['path']}]({src})")
            if image.get("url") and image.get("source"):
                parts.append(f"[{image['source']}]({image['url'].removesuffix('.png')})")
        gate = report.get("gate")
        if gate:
            stages = ", ".join(gate["stages"])
            parts.append(f"> **En revue : {stages}.** Répondez `valide`, ou `retour : ...` avec vos corrections.")
        merge = report.get("merge_request")
        if merge and merge.get("url") and (merge.get("created") or report.get("mode") == "fin"):
            word = "ouverte" if merge.get("created") else "déjà ouverte"
            parts.append(f"> **Merge request {word}** ({merge.get('reason')}) : {merge['url']} ; "
                         "la fusion se décide dans GitLab.")
        if report.get("questions"):
            parts.append(f"> {report['questions']} question(s) ouverte(s) au journal.")
        for error in report.get("errors", []):
            parts.append(f"> ⚠️ {error}")
        if report.get("viewer"):
            parts.append(f"📂 [Fichiers de la mission]({report['viewer']})")
        if report.get("branch") and report.get("commit"):
            pushed = "poussée" if report.get("pushed") else "non poussée"
            parts.append(f"*Branche `{report['branch']}` ({pushed}), commit `{report['commit']}`, "
                         f"{report.get('seconds', 0)} s.*")
        return "\n\n".join(parts) + "\n"

    @staticmethod
    def task_answer(task: str, body: dict) -> str:
        """Réponse locale aux tâches d'Open WebUI, au format qu'il attend, sans appeler le service."""
        asked = [m.get("content") for m in body.get("messages", []) if m.get("role") == "user"]
        first = asked[0] if asked and isinstance(asked[0], str) else ""
        if "title" in task:
            return json.dumps({"title": " ".join(first.split())[:60] or "Mission"}, ensure_ascii=False)
        if "tags" in task:
            return json.dumps({"tags": ["mission"]})
        if "follow_up" in task:
            return json.dumps({"follow_ups": []})
        return ""

    async def _status(self, emitter, text: str, done: bool = False):
        if emitter:
            await emitter({"type": "status", "data": {"description": text, "done": done}})
            return None
        return f"> {text}\n\n"

    # --- un message -------------------------------------------------------------------
    async def pipe(self, body: dict, __metadata__: dict | None = None, __event_emitter__=None,
                   __chat_id__: str | None = None, __user__: dict | None = None,
                   __oauth_token__: dict | None = None, __task__: str | None = None,
                   __task_body__: dict | None = None, __files__: list | None = None):
        if __task__:  # tâche de fond d'Open WebUI (titre, étiquettes, suites...) : jamais un tour de mission
            yield self.task_answer(__task__, __task_body__ or body)
            return
        mission = body.get("model", "").split(".", 1)[-1]
        chat = __chat_id__ or (__metadata__ or {}).get("chat_id") or "sans-conversation"
        user = (__user__ or {}).get("email", "")
        messages = [m for m in body.get("messages", []) if m.get("role") == "user"]
        content = messages[-1]["content"] if messages else ""
        if isinstance(content, list):  # message multimodal : seul le texte est transmis
            content = " ".join(c.get("text", "") for c in content if c.get("type") == "text")
        content = re.sub(r"<attached_files>.*?</attached_files>\s*", "", content, flags=re.S)  # repères d'Open WebUI
        try:
            code, previous = await self._acall("GET", f"/chats/{quote(mission, safe='')}/{quote(chat, safe='')}",
                                               user=user)
            if code == 200 and previous.get("report"):
                yield "**Résultat du tour précédent**\n\n" + self.render(previous["report"]) + "\n---\n\n"
            uploads = []
            for item in [f for f in (__files__ or []) if isinstance(f, dict) and f.get("type", "file") == "file"]:
                try:
                    name, data = await self._file_bytes(item)
                except Exception as error:  # noqa: BLE001 : signalé, le message part quand même
                    yield f"> ⚠️ Fichier joint illisible ({error}) : non transmis.\n\n"
                    continue
                code, sent = await asyncio.to_thread(self._upload, chat, user, name, data)
                if code != 201:
                    yield f"> ⚠️ {name} : {sent.get('error', f'service : code {code}')}\n\n"
                    continue
                uploads.append(sent["upload"])
            code, started = await self._acall("POST", "/turns", {"mission": mission, "chat": chat, "message": content,
                                                                 "uploads": uploads},
                                              user=user, gitlab_token=(__oauth_token__ or {}).get("access_token", ""))
        except OSError as error:
            yield f"> ⚠️ Service des missions injoignable : {error}\n"
            return
        if code == 409:
            yield "> Un tour est déjà en cours dans cette conversation : je suis sa progression. " \
                  "Renvoyez votre message quand il sera fini.\n\n"
        elif code != 202:
            yield f"> ⚠️ {started.get('error', f'service : code {code}')}\n"
            return
        job, after, waited = started["job"], 0, 0.0
        while waited < self.valves.MAX_MINUTES * 60:
            try:
                _, view = await self._acall("GET", f"/jobs/{job}?after={after}&wait={self.valves.POLL_SECONDS}&ack=1",
                                            timeout=self.valves.POLL_SECONDS + 30)
            except OSError as error:
                yield f"> ⚠️ Suivi interrompu ({error}). Le tour continue : écrivez `/statut` plus tard.\n"
                return
            for event in view.get("events", []):
                line = await self._status(__event_emitter__, event["text"])
                if line:
                    yield line
            after = view.get("next", after)
            if view.get("done"):
                await self._status(__event_emitter__, "Tour terminé", done=True)
                yield self.render(view["report"])
                return
            waited += self.valves.POLL_SECONDS
        yield "> Le tour continue en arrière-plan : son résultat s'affichera à votre prochain message.\n"
