"""Fichiers d'une mission lus dans le chat (/fichiers, /lire du pipe) : service interne qui lit la branche
de la conversation (dépôt local, git), droits revérifiés à chaque appel, jeton du service exigé ; rendu par le
pipe (liste numérotée, Markdown d'Obsidian, images en ligne, CSV en tableau, binaire sans Open WebUI) ; miroir
dans Connaissances face à un faux open_webui (collection en lecture seule, dossiers, fichiers changés seuls recopiés,
fichiers retirés effacés).

Usage : python fichiers.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import asyncio
import json
import subprocess
import sys
import tempfile
import types
import urllib.error
import urllib.request
from pathlib import Path

DEPLOY = Path(sys.argv[1]).resolve().parent / "deploy" / "remote-mission"
sys.path.insert(0, str(DEPLOY / "service" / "scripts"))
sys.path.insert(0, str(DEPLOY))
import remote_server  # noqa: E402
import openwebui_pipe  # noqa: E402


# --- faux open_webui (mêmes fonctions que la v0.13) pour le miroir dans Connaissances -----------------------
KB, FILES, LINKS, DIRS, STORED = {}, {}, {}, {}, {}


class Form(types.SimpleNamespace):
    def __init__(self, **values):
        super().__init__(**{"meta": None, "access_grants": None, "data": {}, **values})


class Knowledges:
    @staticmethod
    async def get_knowledge_bases():
        return list(KB.values())

    @staticmethod
    async def insert_new_knowledge(user_id, form):
        KB[f"k{len(KB)}"] = types.SimpleNamespace(id=f"k{len(KB)}", user_id=user_id, name=form.name, meta=None,
                                                  grants=form.access_grants)
        return KB[f"k{len(KB) - 1}"]

    @staticmethod
    async def update_knowledge_meta_by_id(kid, meta):
        KB[kid].meta = meta

    @staticmethod
    async def update_knowledge_by_id(kid, form):
        KB[kid].name = form.name

    @staticmethod
    async def get_files_by_id(kid):
        return [FILES[f] for f, k in LINKS.items() if k[0] == kid]

    @staticmethod
    async def get_all_directories(kid):
        return [d for d in DIRS.values() if d.knowledge_id == kid]

    @staticmethod
    async def create_directory(kid, name, user_id, parent_id=None):
        DIRS[f"d{len(DIRS)}"] = types.SimpleNamespace(id=f"d{len(DIRS)}", knowledge_id=kid, name=name, parent_id=parent_id)
        return DIRS[f"d{len(DIRS) - 1}"]

    @staticmethod
    async def add_file_to_knowledge_by_id(kid, fid, user_id, directory_id=None):
        LINKS[fid] = (kid, directory_id)
        return True

    @staticmethod
    async def remove_file_from_knowledge_by_id(kid, fid):
        LINKS.pop(fid, None)


class Files:
    @staticmethod
    async def insert_new_file(user_id, form):
        FILES[form.id] = types.SimpleNamespace(id=form.id, user_id=user_id, path=form.path, meta=form.meta, data=form.data)
        return FILES[form.id]

    @staticmethod
    async def delete_file_by_id(fid):
        FILES.pop(fid, None)


class Storage:
    @staticmethod
    def upload_file(handle, name, tags):
        STORED[name] = handle.read()
        return STORED[name], name

    @staticmethod
    def delete_file(path):
        STORED.pop(path, None)


for name in ("open_webui", "open_webui.models", "open_webui.storage"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["open_webui.models.knowledge"] = types.SimpleNamespace(Knowledges=Knowledges, KnowledgeForm=Form)
sys.modules["open_webui.models.files"] = types.SimpleNamespace(Files=Files, FileForm=Form)
sys.modules["open_webui.storage.provider"] = types.SimpleNamespace(Storage=Storage)


def folder_of(fid):
    names, node = [], DIRS.get(LINKS[fid][1])
    while node:
        names.insert(0, node.name)
        node = DIRS.get(node.parent_id)
    return "/".join(names)

errors = []


def expect(label, got, wanted):
    if got != wanted:
        errors.append(f"{label} : {got!r}, attendu {wanted!r}")


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True)


def get(url, user="reno@exemple.local", token="secret-du-service"):
    headers = {"X-Myskills-User": user, **({"Authorization": f"Bearer {token}"} if token else {})}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=10) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as error:
        return error.code, error.read()


with tempfile.TemporaryDirectory() as tmp:
    base = Path(tmp)
    repo = base / "mission"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "mission.json").write_text("{}", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "init")
    git(repo, "checkout", "-q", "-b", "openwebui/c1")
    (repo / "vault").mkdir()
    (repo / "vault" / "Exigences.md").write_text(
        "---\ntype: exigences\nstatut: \"validee\"\n---\n# Exigences\n\nVoir [[Contexte|le contexte]].\n\n"
        "> [!question] À trancher\n\n![[contexte.png]]\n\n```mermaid\ngraph LR\n  A[[x]] --> B\n```\n",
        encoding="utf-8")
    (repo / "vault" / "Contexte.md").write_text("# Contexte\n", encoding="utf-8")
    (repo / "vault" / "contexte.png").write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    (repo / "donnees").mkdir()
    (repo / "donnees" / "flux.csv").write_text("source;cible\nportail;CRM|v2\n", encoding="utf-8")
    (repo / "livrables").mkdir()
    (repo / "livrables" / "dossier.docx").write_bytes(b"PK\x03\x04\0\0binaire")
    (repo / ".obsidian").mkdir()
    (repo / ".obsidian" / "app.json").write_text("{}", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "tour")
    git(repo, "checkout", "-q", "main")
    (base / "acces.json").write_text(json.dumps({"demo": {"reno@exemple.local": 30, "ancien@exemple.local": 0}}),
                                     encoding="utf-8")
    config = {"_base": str(base), "missions": {"demo": {"repo": "mission", "title": "Démo"}},
              "access": {"provider": "file", "file": "acces.json", "cache_seconds": 0}, "agent": {"command": ["x"]}}
    service = remote_server.Service(config, "secret-du-service")
    server = remote_server.start_server(service, "127.0.0.1", 0)
    root = f"http://127.0.0.1:{server.server_address[1]}"

    code, body = get(f"{root}/files/demo/c1")
    listing = json.loads(body) if code == 200 else {}
    expect("liste : branche", listing.get("branch"), "openwebui/c1")
    expect("liste : fichiers (dossiers cachés exclus)", sorted(f["path"] for f in listing.get("files", [])),
           ["donnees/flux.csv", "livrables/dossier.docx", "mission.json", "vault/Contexte.md",
            "vault/Exigences.md", "vault/contexte.png"])
    code, body = get(f"{root}/files/demo/c1/raw?path=vault/Contexte.md")
    expect("lecture brute", (code, body), (200, b"# Contexte\n"))
    expect("fichier caché refusé", get(f"{root}/files/demo/c1/raw?path=.obsidian/app.json")[0], 404)
    expect("hors branche refusé", get(f"{root}/files/demo/c1/raw?path=../acces.json")[0], 404)
    expect("branche absente : liste vide", json.loads(get(f"{root}/files/demo/c9")[1]).get("files"), [])
    expect("droits retirés", get(f"{root}/files/demo/c1", user="ancien@exemple.local")[0], 403)
    expect("mission inconnue", get(f"{root}/files/autre/c1")[0], 404)
    expect("jeton du service exigé", get(f"{root}/files/demo/c1", token="")[0], 401)
    service.owners[("demo", "c1")] = "autre@exemple.local"
    expect("conversation d'un autre", get(f"{root}/files/demo/c1")[0], 403)
    service.owners.clear()

    pipe = openwebui_pipe.Pipe()
    pipe.valves.SERVER_URL, pipe.valves.TOKEN = root, "secret-du-service"
    data, error = asyncio.run(pipe._listing("demo", "c1", "reno@exemple.local"))
    text = pipe.render_files(data or {"files": [], "branch": ""})
    expect("/fichiers : numérotés", "6. `vault/Exigences.md`" in text, True)
    files = (data or {}).get("files", [])
    expect("/lire 4", pipe.find_file(files, "4"), ("vault/Contexte.md", []))
    expect("/lire nom sans .md", pipe.find_file(files, "exigences"), ("vault/Exigences.md", []))
    expect("/lire ambigu", pipe.find_file(files, "vault")[0], None)

    def read(target):
        return asyncio.run(pipe.render_file("demo", "c1", "reno@exemple.local", "", target))

    note = read("Exigences.md")
    expect("Markdown : propriétés", "| statut | validee |" in note, True)
    expect("Markdown : wikilink", "**le contexte** (`/lire vault/Contexte.md`)" in note, True)
    expect("Markdown : image en ligne", "![contexte.png](data:image/png;base64," in note, True)
    expect("Markdown : callout", "> ❓ **À trancher**" in note, True)
    expect("Markdown : Mermaid intact", "A[[x]] --> B" in note, True)
    expect("CSV en tableau", "| portail | CRM\\|v2 |" in read("flux.csv"), True)
    expect("binaire sans Open WebUI", "téléchargement disponible dans Open WebUI" in read("dossier.docx"), True)
    expect("introuvable", "Aucun fichier « absent »" in read("absent"), True)
    pipe.valves.INLINE_KB = 0
    expect("image au-delà du budget", "⬇️" in read("contexte.png") or "Open WebUI" in read("contexte.png"), True)

    mirror = lambda: asyncio.run(pipe.mirror("demo", "c1", "reno@exemple.local", "u1"))  # noqa: E731
    expect("miroir : premier passage", mirror(), "Connaissances « Démo · c1 » : 6 ajouté(s).")
    base = next(iter(KB.values()), None)
    expect("miroir : collection à myskills, lue par l'utilisateur", (base.user_id, base.grants) if base else None,
           ("myskills", [{"principal_type": "user", "principal_id": "u1", "permission": "read"}]))
    held = {f.meta["myskills_path"]: f for f in FILES.values()}
    expect("miroir : dossiers", sorted(folder_of(f.id) for f in held.values()),
           ["", "donnees", "livrables", "vault", "vault", "vault"])
    expect("miroir : aperçu Obsidian lisible", "**le contexte**" in held["vault/Exigences.md"].data["content"], True)
    expect("miroir : binaire sans texte", held["livrables/dossier.docx"].data["content"], "")
    expect("miroir : rien de changé", mirror(), None)
    git(repo, "checkout", "-q", "openwebui/c1")
    (repo / "vault" / "Contexte.md").write_text("# Contexte\n\nrevu\n", encoding="utf-8")
    git(repo, "rm", "-q", "donnees/flux.csv")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "tour 2")
    git(repo, "checkout", "-q", "main")
    remote_server.mission_files.forget()
    expect("miroir : changé et retiré", mirror(), "Connaissances « Démo · c1 » : 1 mis à jour, 1 retiré(s).")
    expect("miroir : stockage nettoyé", len(STORED), 5)
    server.shutdown()

print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
