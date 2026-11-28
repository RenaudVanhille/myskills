"""Fichiers joints dans le chat : reçus par le service (POST /uploads), remis au tour qui les cite, relayés au
pod de session, refusés d'une autre conversation ou au-delà de la taille permise, effacés après le tour.

Usage : python uploads.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote

SCRIPTS = Path(sys.argv[1]).resolve().parent / "deploy" / "remote-mission" / "service" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import remote_server  # noqa: E402
import remote_turn  # noqa: E402

errors = []
SEEN: list[tuple] = []


def expect(label, got, wanted):
    if got != wanted:
        errors.append(f"{label} : {got!r}, attendu {wanted!r}")


def fake_turn(cfg, name, chat, message, emit, user=None, files=None):
    SEEN.append((chat, [(Path(f).name, Path(f).read_bytes(), str(f)) for f in files or []]))
    return {**remote_turn.empty_report(name, chat, user), "uploaded": [f"documents/{Path(f).name}" for f in files or []]}


remote_turn.run_turn = fake_turn
config = {"_base": ".", "missions": {"portail": {"repo": "x"}}, "server": {"max_upload_mb": 1},
          "agent": {"command": ["x"]}}


def call(url, path, data, headers, method="POST"):
    request = urllib.request.Request(url + path, data=data, method=method,
                                     headers={"Authorization": "Bearer t", **headers})
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read() or b"{}")


def wait(service, job):
    for _ in range(50):
        if service.jobs[job].report is not None:
            return service.jobs[job].report
        time.sleep(0.1)
    return None


service = remote_server.Service(config, "t")
server = remote_server.start_server(service, "127.0.0.1", 0)
url = f"http://127.0.0.1:{server.server_address[1]}"
user = {"X-Myskills-User": "reno@exemple.local"}

code, sent = call(url, "/uploads?chat=c1", "Exigence 1 : déclarer un sinistre.".encode(),
                  {**user, "X-Myskills-Filename": quote("cahier des charges.txt")})
expect("upload accepté", code, 201)
code, other = call(url, "/uploads?chat=c2", b"x", {**user, "X-Myskills-Filename": "autre.txt"})
code, refused = call(url, "/turns", json.dumps({"mission": "portail", "chat": "c1", "message": "m",
                                                "uploads": [other.get("upload")]}).encode(),
                     {**user, "Content-Type": "application/json"})
expect("fichier d'une autre conversation", code, 400)
code, too_big = call(url, "/uploads?chat=c1", b"x" * 1_000_001, {**user, "X-Myskills-Filename": "gros.bin"})
expect("taille maximale", code, 413)
code, bad = call(url, "/uploads?chat=c1", b"x", {**user, "X-Myskills-Filename": ".."})
expect("nom invalide", code, 400)

code, started = call(url, "/turns", json.dumps({"mission": "portail", "chat": "c1", "message": "analyse",
                                                "uploads": [sent.get("upload")]}).encode(),
                     {**user, "Content-Type": "application/json"})
expect("tour lancé", code, 202)
report = wait(service, started.get("job"))
expect("fichier remis au tour", [(n, d) for n, d, _ in SEEN[-1][1]] if SEEN else None,
       [("cahier des charges.txt", "Exigence 1 : déclarer un sinistre.".encode())])
expect("rapport", (report or {}).get("uploaded"), ["documents/cahier des charges.txt"])
expect("copie d'attente effacée", Path(SEEN[-1][1][0][2]).exists() if SEEN and SEEN[-1][1] else None, False)

# Pod de session : le frontal lui envoie d'abord les fichiers, puis le tour.
pod = remote_server.Service(config, "jeton-pod", ("portail", "c3"))
pod_server = remote_server.start_server(pod, "127.0.0.1", 0)
staged = Path(remote_server.tempfile.mkdtemp()) / "notes.md"
staged.write_text("# Notes\n", encoding="utf-8")
relayed = remote_server.forward(f"http://127.0.0.1:{pod_server.server_address[1]}", "jeton-pod", "portail", "c3",
                                "lis mes notes", "reno@exemple.local", lambda kind, text: None, [staged])
expect("relayé au pod", relayed.get("uploaded"), ["documents/notes.md"])
expect("contenu relayé", SEEN[-1][1][0][1] if SEEN[-1][1] else None, b"# Notes\n")

server.shutdown()
pod_server.shutdown()
print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
