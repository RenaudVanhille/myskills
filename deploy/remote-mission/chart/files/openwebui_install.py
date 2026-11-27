# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Installe et tient à jour le pipe myskills dans Open WebUI, sans passage par l'interface d'administration.

Lancé en tâche de fond dans le conteneur d'Open WebUI (chart Helm, docker compose du dev local) :

    python openwebui_install.py & exec bash start.sh

1. attend qu'Open WebUI réponde (/health : base migrée) ;
2. lit la source du pipe chez le service des missions (GET /openwebui/pipe, même version que le service) ;
3. crée ou met à jour la fonction dans la base d'Open WebUI, l'active et règle ses Valves SERVER_URL et TOKEN
   (les autres Valves réglées par un administrateur sont gardées) ;
4. recommence toutes les --every secondes : une nouvelle version du service met le pipe à jour d'elle-même.

Il passe par les modèles internes d'Open WebUI (version épinglée dans le chart et le compose) : l'API HTTP
demanderait un administrateur connecté, qui n'existe pas avant la première connexion par GitLab.
Variables : MYSKILLS_SERVER_URL, MYSKILLS_REMOTE_TOKEN. Chaque passage écrit un rapport JSON sur une ligne.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

FUNCTION_ID = "myskills_missions"
NAME = "Missions myskills"
DESCRIPTION = "Missions myskills : chaque conversation joue la mission dans son pod de session."
OWNER = "myskills"


def fetch(url: str, token: str = "", timeout: float = 10) -> dict:
    request = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"} if token else {})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8") or "{}")


def wait_webui(webui: str, deadline: float) -> None:
    while True:
        try:
            if fetch(webui.rstrip("/") + "/health").get("status") is True:
                return
        except (OSError, ValueError, urllib.error.URLError):
            pass
        if time.time() > deadline:
            raise TimeoutError(f"Open WebUI ne répond pas sur {webui}/health")
        time.sleep(3)


def sync(content: str, server_url: str, token: str, function_id: str = FUNCTION_ID) -> dict:
    """Crée ou met à jour la fonction, l'active et règle ses Valves. Rend l'action faite."""
    sys.path.insert(0, os.getcwd())  # /app/backend dans l'image d'Open WebUI
    from open_webui.models.functions import FunctionForm, FunctionMeta, Functions
    from open_webui.utils.plugin import load_function_module_by_id, replace_imports

    content = replace_imports(content)
    _module, kind, frontmatter = load_function_module_by_id(function_id, content)  # source invalide : exception
    if kind != "pipe":
        raise ValueError(f"la source servie est une fonction « {kind} », pas un pipe")
    meta = FunctionMeta(description=DESCRIPTION, manifest=frontmatter or {})
    existing = Functions.get_function_by_id(function_id)
    actions = []

    def done(result, action: str) -> None:  # les modèles d'Open WebUI rendent None sur échec
        if result is None:
            raise RuntimeError(f"Open WebUI a refusé l'écriture ({action})")
        actions.append(action)

    if existing is None:
        done(Functions.insert_new_function(OWNER, kind,
                                           FunctionForm(id=function_id, name=NAME, content=content, meta=meta)),
             "créé")
    elif existing.content != content:
        done(Functions.update_function_by_id(function_id, {"content": content, "type": kind,
                                                           "meta": meta.model_dump()}), "mis à jour")
    if existing is None or not existing.is_active:
        done(Functions.update_function_by_id(function_id, {"is_active": True}), "activé")
    valves = Functions.get_function_valves_by_id(function_id) or {}
    wanted = {**valves, "SERVER_URL": server_url, "TOKEN": token}
    if wanted != valves:
        done(Functions.update_function_valves_by_id(function_id, wanted), "valves réglées")
    return {"function": function_id, "actions": actions or ["inchangé"]}


def run_once(args, token: str) -> dict:
    report = {"function": FUNCTION_ID, "actions": [], "errors": [], "warnings": []}
    try:
        wait_webui(args.webui, time.time() + args.wait)
        pipe = fetch(args.server_url.rstrip("/") + "/openwebui/pipe", token)
        report.update(sync(pipe["content"], args.server_url, token))
        report["sha256"] = pipe.get("sha256")
    except urllib.error.HTTPError as error:
        report["errors"].append(f"service des missions : HTTP {error.code} sur /openwebui/pipe"
                                + (" (MYSKILLS_REMOTE_TOKEN différent de celui du service ?)" if error.code == 401 else ""))
    except Exception as error:  # noqa: BLE001 : la boucle continue, l'erreur est rapportée
        report["errors"].append(f"{type(error).__name__}: {error}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--server-url", default=os.environ.get("MYSKILLS_SERVER_URL", ""),
                        help="URL du service des missions vue d'Open WebUI (défaut : $MYSKILLS_SERVER_URL)")
    parser.add_argument("--webui", default=f"http://127.0.0.1:{os.environ.get('PORT', '8080')}",
                        help="Open WebUI local (attente de /health)")
    parser.add_argument("--every", type=int, default=600, help="secondes entre deux passages ; 0 : un seul")
    parser.add_argument("--wait", type=int, default=600, help="attente maximale d'Open WebUI à chaque passage")
    args = parser.parse_args()
    token = os.environ.get("MYSKILLS_REMOTE_TOKEN", "")
    if not args.server_url:
        print(json.dumps({"errors": ["--server-url ou MYSKILLS_SERVER_URL manquant"], "warnings": []},
                         ensure_ascii=False), flush=True)
        return 1
    while True:
        report = run_once(args, token)
        print("[myskills pipe] " + json.dumps(report, ensure_ascii=False), flush=True)
        if args.every <= 0:
            return 1 if report["errors"] else 0
        time.sleep(args.every if not report["errors"] else min(args.every, 30))


if __name__ == "__main__":
    sys.exit(main())
