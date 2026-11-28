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


BINARY = r"\.(docx?|xlsx?|pptx?|od[tsp]|pdf|zip|gz|7z|jar|exe|dll|so|bin|mp[34]|wav|m4a|webm|mov)$"
OWNER = "myskills"  # propriétaire des collections et fichiers du miroir (comme la fonction)


class Pipe:
    class Valves(BaseModel):
        SERVER_URL: str = "http://myskills-remote.myskills.svc.cluster.local:8765"
        TOKEN: str = ""
        POLL_SECONDS: int = 20
        MAX_MINUTES: int = 180
        INLINE_KB: int = 3000  # images en ligne par réponse de /lire (au-delà : lien de téléchargement)
        KNOWLEDGE: bool = True  # miroir de la branche dans Connaissances (une collection par conversation)
        KNOWLEDGE_MAX_MB: int = 20  # fichiers plus gros : laissés hors du miroir (/lire les ouvre)

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

    # --- fichiers de la mission : /fichiers, /lire (le service reste interne, tout passe par le chat) ---
    def _raw(self, mission: str, chat: str, path: str, user: str) -> tuple[int, bytes]:
        request = urllib.request.Request(
            self.valves.SERVER_URL.rstrip("/") + f"/files/{quote(mission, safe='')}/{quote(chat, safe='')}/raw"
            f"?path={quote(path, safe='')}",
            headers={"Authorization": f"Bearer {self.valves.TOKEN}", "X-Myskills-User": user})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, response.read()
        except urllib.error.HTTPError as error:
            return error.code, error.read()

    async def _listing(self, mission: str, chat: str, user: str) -> tuple[dict | None, str | None]:
        code, data = await self._acall("GET", f"/files/{quote(mission, safe='')}/{quote(chat, safe='')}", user=user)
        if code != 200:
            return None, data.get("error", f"service : code {code}")
        data["files"] = sorted(data.get("files", []), key=lambda f: ("/" in f["path"], f["path"].lower()))
        return data, None

    @staticmethod
    def _size(size) -> str:
        if not size:
            return ""
        return f" ({size / 1_000_000:.1f} Mo)" if size >= 1_000_000 else f" ({max(1, round(size / 1000))} ko)"

    def render_files(self, data: dict) -> str:
        files = data["files"]
        if not files:
            return (f"Aucun fichier sur la branche `{data['branch']}` pour l'instant : ils apparaissent après le "
                    "premier tour de la conversation.")
        lines = [f"**{data['mission']}**, branche `{data['branch']}` : {len(files)} fichier(s). "
                 "`/lire N` ou `/lire chemin` pour en afficher un.", ""]
        folder = None
        for number, item in enumerate(files[:400], 1):
            top = item["path"].split("/", 1)[0] if "/" in item["path"] else ""
            if top != folder:
                folder = top
                lines += ["", f"**{top or 'Racine'}**"]
            lines.append(f"{number}. `{item['path']}`{self._size(item.get('size'))}")
        if len(files) > 400:
            lines.append(f"… et {len(files) - 400} autres : `/lire chemin` les ouvre aussi.")
        return "\n".join(lines) + "\n"

    @staticmethod
    def find_file(files: list, target: str) -> tuple[str | None, list]:
        target = target.strip().strip("`").lstrip("./")
        paths = [f["path"] for f in files]
        if target.isdigit():
            index = int(target) - 1
            return (paths[index], []) if 0 <= index < len(paths) else (None, [])
        if target in paths:
            return target, []
        low = target.lower()
        for key in (lambda p: p.lower().rsplit("/", 1)[-1] == low,
                    lambda p: p.lower().rsplit("/", 1)[-1] in (low + ".md",),
                    lambda p: low in p.lower()):
            found = [p for p in paths if key(p)]
            if len(found) == 1:
                return found[0], []
            if found:
                return None, found[:15]
        return None, []

    async def _attach(self, name: str, data: bytes, user_id: str) -> str | None:
        """Fichier rangé dans le stockage d'Open WebUI : lien de téléchargement servi par Open WebUI."""
        try:
            import io
            import uuid as uuidlib
            import mimetypes
            from open_webui.models.files import FileForm, Files
            from open_webui.storage.provider import Storage
        except ImportError:
            return None
        file_id = str(uuidlib.uuid4())
        _, path = await asyncio.to_thread(Storage.upload_file, io.BytesIO(data), f"{file_id}_{name}", {})
        kind = mimetypes.guess_type(name)[0] or "application/octet-stream"
        made = Files.insert_new_file(user_id, FileForm(id=file_id, filename=name, path=path,
                                                       meta={"name": name, "content_type": kind, "size": len(data)}))
        if asyncio.iscoroutine(made):
            made = await made
        return f"/api/v1/files/{file_id}/content" if made else None

    @staticmethod
    def _data_uri(path: str, data: bytes) -> str:
        import base64
        import mimetypes
        kind = mimetypes.guess_type(path)[0] or "image/png"
        return f"data:{kind};base64,{base64.b64encode(data).decode()}"

    async def render_file(self, mission: str, chat: str, user: str, user_id: str, target: str) -> str:
        data, error = await self._listing(mission, chat, user)
        if error:
            return f"> ⚠️ {error}\n"
        path, candidates = self.find_file(data["files"], target)
        if not path:
            if candidates:
                return "Plusieurs fichiers correspondent :\n\n" + "\n".join(f"- `{p}`" for p in candidates) + "\n"
            return f"Aucun fichier « {target} » sur la branche `{data['branch']}` : `/fichiers` les liste.\n"
        code, raw = await asyncio.to_thread(self._raw, mission, chat, path, user)
        if code != 200:
            return f"> ⚠️ `{path}` : lecture impossible (code {code}).\n"
        head = f"📄 `{path}`\n\n"
        name = path.rsplit("/", 1)[-1]
        low = name.lower()
        budget = [self.valves.INLINE_KB * 1000]

        async def image(rel: str) -> str | None:
            code, blob = await asyncio.to_thread(self._raw, mission, chat, rel, user)
            if code != 200 or len(blob) > budget[0]:
                return None
            budget[0] -= len(blob)
            return self._data_uri(rel, blob)

        if re.search(r"\.(png|jpe?g|gif|webp)$", low):
            uri = await image(path)
            return head + (f"![{name}]({uri})\n" if uri else await self._download(name, raw, user_id))
        if low.endswith(".drawio"):
            png = next((p for p in (path + ".png", path[:-7] + ".png") if p in {f["path"] for f in data["files"]}), None)
            uri = await image(png) if png else None
            return head + (f"![{name}]({uri})\n\n" if uri else "Pas d'export PNG de ce schéma.\n\n") + \
                await self._download(name, raw, user_id)
        try:
            text = raw.decode("utf-8")
            if "\0" in text[:4096] or re.search(BINARY, low):
                raise UnicodeDecodeError("utf-8", b"", 0, 1, "binaire")
        except UnicodeDecodeError:
            return head + await self._download(name, raw, user_id)
        if low.endswith(".md"):
            return head + await self._markdown(text, path, data["files"], image)
        if low.endswith((".csv", ".tsv")):
            return head + self._table(text, "\t" if low.endswith(".tsv") else ";" if ";" in text.split("\n", 1)[0] else ",")
        if low.endswith(".json"):
            try:
                text = json.dumps(json.loads(text), ensure_ascii=False, indent=2)
            except ValueError:
                pass
        cut = len(text) > 60_000
        language = low.rsplit(".", 1)[-1] if "." in low else ""
        return head + f"```{language}\n{text[:60_000]}\n```\n" + \
            ("\n*Fichier tronqué : le reste est dans le téléchargement.*\n\n" + await self._download(name, raw, user_id)
             if cut else "")

    async def _download(self, name: str, data: bytes, user_id: str) -> str:
        url = await self._attach(name, data, user_id) if user_id else None
        return f"⬇️ [Télécharger {name}]({url}){self._size(len(data))}\n" if url else \
            f"Fichier binaire {name}{self._size(len(data))} : téléchargement disponible dans Open WebUI seulement.\n"

    @staticmethod
    def _table(text: str, separator: str) -> str:
        import csv
        import io
        rows = list(csv.reader(io.StringIO(text), delimiter=separator))
        if not rows:
            return "Fichier vide.\n"
        cell = lambda v: v.replace("|", "\\|").replace("\n", " ")  # noqa: E731
        width = max(len(r) for r in rows)
        rows = [r + [""] * (width - len(r)) for r in rows]
        lines = ["| " + " | ".join(cell(v) for v in rows[0]) + " |", "|" + " --- |" * width]
        lines += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows[1:201]]
        if len(rows) > 201:
            lines.append(f"\n*{len(rows) - 201} lignes de plus dans le fichier.*")
        return "\n".join(lines) + "\n"

    async def _markdown(self, text: str, path: str, files: list, image) -> str:
        """Markdown d'Obsidian pour le chat : propriétés en tableau, wikilinks vers /lire, images en ligne."""
        known = {f["path"] for f in files}
        by_name = {}
        for item in files:
            base = item["path"].rsplit("/", 1)[-1].lower()
            by_name.setdefault(base, item["path"])
            if base.endswith(".md"):
                by_name.setdefault(base[:-3], item["path"])
        folder = path.rsplit("/", 1)[0] + "/" if "/" in path else ""

        def locate(name: str) -> str | None:
            name = name.strip()
            if name in known:
                return name
            parts = []
            for part in (folder + name).split("/"):
                if part == "..":
                    parts = parts[:-1]
                elif part not in ("", "."):
                    parts.append(part)
            joined = "/".join(parts)
            return joined if joined in known else by_name.get(name.lower().rsplit("/", 1)[-1])

        props = ""
        match = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n?", text, re.S)
        if match:
            rows = [line.split(":", 1) for line in match.group(1).splitlines() if re.match(r"^[\w-]+:", line)]
            if rows:
                props = "| Propriété | Valeur |\n| --- | --- |\n" + "\n".join(
                    f"| {k.strip()} | {v.strip().strip(chr(34)).replace('|', '/')} |" for k, v in rows) + "\n\n"
            text = text[match.end():]
        out = []
        for chunk in re.split(r"(```.*?```)", text, flags=re.S):  # blocs de code (Mermaid...) laissés tels quels
            if chunk.startswith("```"):
                out.append(chunk)
                continue
            for found in set(re.findall(r"!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", chunk)) | \
                    set(m for m in re.findall(r"!\[[^\]]*\]\(<?([^)>\s]+)>?\)", chunk) if "://" not in m
                        and not m.startswith("data:")):
                where = locate(found)
                uri = await image(where) if where and re.search(r"\.(png|jpe?g|gif|webp)$", where, re.I) else None
                chunk = chunk.replace(f"![[{found}]]", f"![{found}]({uri})" if uri else f"*(image {found})*")
                if uri:
                    chunk = re.sub(r"(!\[[^\]]*\]\()<?" + re.escape(found) + r">?\)", lambda m: m.group(1) + uri + ")", chunk)

            def wikilink(m):
                where, label = locate(m.group(1)), (m.group(3) or m.group(1)).strip()
                return f"**{label}** (`/lire {where}`)" if where else label
            chunk = re.sub(r"\[\[([^\]|#]+)(#[^\]|]*)?(?:\|([^\]]+))?\]\]", wikilink, chunk)

            def mdlink(m):
                where = locate(m.group(2)) if "://" not in m.group(2) and not m.group(2).startswith(("#", "data:")) else None
                return f"{m.group(1)} (`/lire {where}`)" if where else m.group(0)
            chunk = re.sub(r"(?<!!)\[([^\]]+)\]\(<?([^)>]+)>?\)", mdlink, chunk)
            icons = {"note": "📝", "info": "ℹ️", "question": "❓", "retour": "↩️", "warning": "⚠️", "attention": "⚠️",
                     "danger": "⛔", "success": "✅", "todo": "☑️", "tip": "💡", "example": "📌"}
            chunk = re.sub(r"^>\s*\[!(\w+)\][-+]?\s*(.*)$",
                           lambda m: f"> {icons.get(m.group(1).lower(), '📌')} **{m.group(2) or m.group(1).capitalize()}**",
                           chunk, flags=re.M)
            out.append(chunk)
        return props + "".join(out) + "\n"

    # --- miroir dans Connaissances ------------------------------------------------------
    @staticmethod
    async def _done(value):
        return await value if asyncio.iscoroutine(value) else value

    async def mirror(self, mission: str, chat: str, user: str, user_id: str) -> str | None:
        """Copie la branche de la conversation dans une collection Connaissances d'Open WebUI.

        Collection et fichiers appartiennent à « myskills » ; l'utilisateur les lit seulement (la branche GitLab
        reste la référence, une modification dans Open WebUI serait perdue). Seuls les fichiers dont l'empreinte
        git a changé sont recopiés. Rend une ligne pour la réponse, ou None si rien n'a changé.
        """
        if not self.valves.KNOWLEDGE or not user_id:
            return None
        try:
            from open_webui.models.files import FileForm, Files
            from open_webui.models.knowledge import KnowledgeForm, Knowledges
            from open_webui.storage.provider import Storage
        except ImportError:
            return None
        data, error = await self._listing(mission, chat, user)
        if error:
            return f"Connaissances non mises à jour : {error}"
        done, key = self._done, {"mission": mission, "chat": chat}
        name = f"{data['mission']} · {await self._chat_title(chat)}"[:120]
        description = f"Fichiers de la branche {data['branch']} (copie en lecture seule, mise à jour à chaque tour)."
        base = next((kb for kb in await done(Knowledges.get_knowledge_bases())
                     if (kb.meta or {}).get("myskills") == key), None)
        if base is None:
            base = await done(Knowledges.insert_new_knowledge(OWNER, KnowledgeForm(
                name=name, description=description,
                access_grants=[{"principal_type": "user", "principal_id": user_id, "permission": "read"}])))
            if base is None:
                return "Connaissances : Open WebUI a refusé la création de la collection."
            await done(Knowledges.update_knowledge_meta_by_id(base.id, {**(base.meta or {}), "myskills": key}))
        elif base.name != name:
            await done(Knowledges.update_knowledge_by_id(base.id, KnowledgeForm(name=name, description=description)))
        held = {(f.meta or {}).get("myskills_path"): f for f in await done(Knowledges.get_files_by_id(base.id))}
        folders = {}
        found = await done(Knowledges.get_all_directories(base.id)) or []
        by_id = {d.id: d for d in found}
        for item in found:
            parts, node = [], item
            while node:
                parts.insert(0, node.name)
                node = by_id.get(node.parent_id)
            folders["/".join(parts)] = item.id

        async def folder(path: str) -> str | None:
            if not path:
                return None
            if path not in folders:
                parent, _, leaf = path.rpartition("/")
                made = await done(Knowledges.create_directory(base.id, leaf, OWNER, await folder(parent)))
                folders[path] = made.id if made else None
            return folders[path]

        async def drop(item) -> None:
            await done(Knowledges.remove_file_from_knowledge_by_id(base.id, item.id))
            await done(Files.delete_file_by_id(item.id))
            try:
                await asyncio.to_thread(Storage.delete_file, item.path)
            except Exception:  # noqa: BLE001 : fichier déjà absent du stockage
                pass

        async def no_image(_):
            return None

        import io
        import mimetypes
        import uuid as uuidlib
        counts = {"ajouté(s)": 0, "mis à jour": 0, "retiré(s)": 0, "trop gros": 0}
        wanted = {f["path"]: f for f in data["files"]}
        for path, item in wanted.items():
            old = held.get(path)
            if old is not None and (old.meta or {}).get("myskills_sha") == item.get("sha") and item.get("sha"):
                continue
            if (item.get("size") or 0) > self.valves.KNOWLEDGE_MAX_MB * 1_000_000:
                counts["trop gros"] += 1
                continue
            code, raw = await asyncio.to_thread(self._raw, mission, chat, path, user)
            if code != 200 or not raw:  # fichier vide : rien à montrer, le stockage d'Open WebUI le refuse
                continue
            if len(raw) > self.valves.KNOWLEDGE_MAX_MB * 1_000_000:
                counts["trop gros"] += 1
                continue
            if old is not None:
                await drop(old)
            file_id, leaf = str(uuidlib.uuid4()), path.rsplit("/", 1)[-1]
            try:
                text = raw.decode("utf-8") if b"\0" not in raw[:4096] else ""
            except UnicodeDecodeError:
                text = ""
            if text and leaf.lower().endswith(".md"):  # aperçu de Connaissances : Obsidian lisible (liens, encadrés)
                text = await self._markdown(text, path, data["files"], no_image)
            _, stored = await asyncio.to_thread(Storage.upload_file, io.BytesIO(raw), f"{file_id}_{leaf}", {})
            meta = {"name": leaf, "content_type": mimetypes.guess_type(leaf)[0] or "application/octet-stream",
                    "size": len(raw), "myskills_path": path, "myskills_sha": item.get("sha")}
            if await done(Files.insert_new_file(OWNER, FileForm(id=file_id, filename=leaf, path=stored, meta=meta,
                                                               data={"content": text, "status": "completed"}))):
                await done(Knowledges.add_file_to_knowledge_by_id(base.id, file_id, OWNER,
                                                                  await folder(path.rpartition("/")[0])))
                counts["mis à jour" if old is not None else "ajouté(s)"] += 1
        for path, old in held.items():
            if path not in wanted:
                await drop(old)
                counts["retiré(s)"] += 1
        changed = ", ".join(f"{n} {word}" for word, n in counts.items() if n)
        return f"Connaissances « {name} » : {changed}." if changed else None

    @staticmethod
    async def _chat_title(chat: str) -> str:
        try:
            from open_webui.models.chats import Chats
            found = Chats.get_chat_by_id(chat)
            found = await found if asyncio.iscoroutine(found) else found
            return (found.title if found else "") or chat[:8]
        except Exception:  # noqa: BLE001 : titre facultatif
            return chat[:8]

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
        command = content.strip()
        if command.lower() in ("/fichiers", "/files") or re.match(r"(?i)^/(lire|read)\s+\S", command):
            try:
                if command.lower() in ("/fichiers", "/files"):
                    data, error = await self._listing(mission, chat, user)
                    yield f"> ⚠️ {error}\n" if error else self.render_files(data)
                else:
                    yield await self.render_file(mission, chat, user, (__user__ or {}).get("id", ""),
                                                 command.split(None, 1)[1])
            except OSError as error:
                yield f"> ⚠️ Service des missions injoignable : {error}\n"
            return
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
                try:
                    copied = await self.mirror(mission, chat, user, (__user__ or {}).get("id", ""))
                except Exception as error:  # noqa: BLE001 : le miroir ne fait jamais échouer un tour
                    copied = f"Connaissances non mises à jour : {type(error).__name__}: {error}"
                if copied:
                    yield f"\n*{copied}*\n"
                return
            waited += self.valves.POLL_SECONDS
        yield "> Le tour continue en arrière-plan : son résultat s'affichera à votre prochain message.\n"
