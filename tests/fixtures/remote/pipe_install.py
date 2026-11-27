"""Installation automatique du pipe dans Open WebUI (chart/files/openwebui_install.py), sans Open WebUI.

Le service sert la source du pipe (GET /openwebui/pipe, jeton exigé) ; un faux paquet open_webui (base en
mémoire, mêmes fonctions que la v0.6.18) reçoit la fonction : créée, activée et réglée au premier passage,
inchangée au second, rétablie si désactivée, mise à jour si la source change, Valves d'un administrateur
gardées ; jeton faux signalé.

Usage : python pipe_install.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import argparse
import json
import os
import sys
import tempfile
import types
from pathlib import Path

DEPLOY = Path(sys.argv[1]).resolve().parent / "deploy" / "remote-mission"
sys.path.insert(0, str(DEPLOY / "service" / "scripts"))
sys.path.insert(0, str(DEPLOY / "chart" / "files"))
import remote_server  # noqa: E402

# --- faux open_webui --------------------------------------------------------------------------------------
ROWS: dict = {}


class Row(types.SimpleNamespace):
    pass


class FunctionMeta:
    def __init__(self, description=None, manifest=None):
        self.description, self.manifest = description, manifest or {}

    def model_dump(self):
        return {"description": self.description, "manifest": self.manifest}


class FunctionForm:
    def __init__(self, id, name, content, meta):
        self.id, self.name, self.content, self.meta = id, name, content, meta


class Functions:
    @staticmethod
    def get_function_by_id(fid):
        return ROWS.get(fid)

    @staticmethod
    def insert_new_function(user_id, kind, form):
        ROWS[form.id] = Row(id=form.id, user_id=user_id, type=kind, name=form.name, content=form.content,
                            meta=form.meta.model_dump(), valves=None, is_active=False, is_global=False)
        return ROWS[form.id]

    @staticmethod
    def update_function_by_id(fid, updated):
        for key, value in updated.items():
            setattr(ROWS[fid], key, value)
        return ROWS[fid]

    @staticmethod
    def get_function_valves_by_id(fid):
        return ROWS[fid].valves

    @staticmethod
    def update_function_valves_by_id(fid, valves):
        ROWS[fid].valves = dict(valves)
        return ROWS[fid]


def load_function_module_by_id(fid, content):
    namespace: dict = {}
    exec(compile(content, fid, "exec"), namespace)  # noqa: S102 : source du dépôt
    return None, "pipe" if "Pipe" in namespace else "filter", {}


for name in ("open_webui", "open_webui.models", "open_webui.utils"):
    sys.modules[name] = types.ModuleType(name)
sys.modules["open_webui.models.functions"] = types.SimpleNamespace(
    Functions=Functions, FunctionForm=FunctionForm, FunctionMeta=FunctionMeta)
sys.modules["open_webui.utils.plugin"] = types.SimpleNamespace(
    load_function_module_by_id=load_function_module_by_id, replace_imports=lambda c: c)

import openwebui_install  # noqa: E402

# --- contrôles --------------------------------------------------------------------------------------------
errors = []


def expect(label, got, wanted):
    if got != wanted:
        errors.append(f"{label} : {got!r}, attendu {wanted!r}")


service = remote_server.Service({"missions": {}}, "jeton-pipe")
server = remote_server.start_server(service, "127.0.0.1", 0)
url = f"http://127.0.0.1:{server.server_address[1]}"
openwebui_install.wait_webui = lambda webui, deadline: None  # pas d'Open WebUI à attendre
args = argparse.Namespace(server_url=url, webui="http://127.0.0.1:1", wait=1)
fid = openwebui_install.FUNCTION_ID

first = openwebui_install.run_once(args, "jeton-pipe")
expect("premier passage", first["actions"], ["créé", "activé", "valves réglées"])
row = ROWS.get(fid)
expect("source servie", row and row.content, (DEPLOY / "openwebui_pipe.py").read_text(encoding="utf-8"))
expect("type", row and row.type, "pipe")
expect("valves", row and row.valves, {"SERVER_URL": url, "TOKEN": "jeton-pipe"})
expect("second passage", openwebui_install.run_once(args, "jeton-pipe")["actions"], ["inchangé"])

row.is_active = False
row.valves["POLL_SECONDS"] = 5  # réglage d'un administrateur
expect("pipe désactivé à la main", openwebui_install.run_once(args, "jeton-pipe")["actions"], ["activé"])
expect("valves de l'administrateur gardées", row.valves.get("POLL_SECONDS"), 5)

with tempfile.TemporaryDirectory() as tmp:
    newer = Path(tmp) / "openwebui_pipe.py"
    newer.write_text(remote_server.PIPE.read_text(encoding="utf-8") + "\n# version suivante\n", encoding="utf-8")
    remote_server.PIPE = newer
    expect("nouvelle version du service", openwebui_install.run_once(args, "jeton-pipe")["actions"], ["mis à jour"])
    expect("source à jour", row.content.endswith("# version suivante\n"), True)

refused = openwebui_install.run_once(args, "faux")
expect("jeton faux", bool(refused["errors"]) and "401" in refused["errors"][0], True)
server.shutdown()
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
