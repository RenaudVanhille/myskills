"""Visionneuse web des fichiers d'une mission : branche d'un dépôt local lue par git, lien signé, droits
revérifiés à l'ouverture, page et contenu bruts servis avec leurs protections, liens entrants des notes.

Usage : python visionneuse.py SKILLS ; rapport JSON (errors, warnings), code 1 si un contrôle échoue.
"""

import json
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

SCRIPTS = Path(sys.argv[1]).resolve().parent / "deploy" / "remote-mission" / "service" / "scripts"
sys.path.insert(0, str(SCRIPTS))
import remote_server  # noqa: E402
import viewer  # noqa: E402

errors = []


def expect(label, got, wanted):
    if got != wanted:
        errors.append(f"{label} : {got!r}, attendu {wanted!r}")


def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), "-c", "user.name=t", "-c", "user.email=t@t", *args], check=True,
                   capture_output=True)


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


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
    (repo / "vault" / "Exigences.md").write_text("# Exigences\n\nVoir [[Contexte|le contexte]].\n", encoding="utf-8")
    (repo / "vault" / "Contexte.md").write_text("---\ntype: schema\n---\n# Contexte\n\n![[contexte.png]]\n",
                                                 encoding="utf-8")
    (repo / "vault" / "contexte.png").write_bytes(b"\x89PNG\r\n\x1a\nfaux")
    (repo / "piege.html").write_text("<script>alert(1)</script>", encoding="utf-8")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "tour")
    git(repo, "checkout", "-q", "main")
    (base / "acces.json").write_text(json.dumps({"demo": {"reno@exemple.local": 30, "ancien@exemple.local": 0}}),
                                     encoding="utf-8")
    config = {"_base": str(base), "missions": {"demo": {"repo": "mission", "title": "Démo"}},
              "access": {"provider": "file", "file": "acces.json", "cache_seconds": 0},
              "viewer": {"url": "http://127.0.0.1/fichiers", "link_days": 1}, "agent": {"command": ["x"]}}
    service = remote_server.Service(config, "secret-du-service")
    server = remote_server.start_server(service, "127.0.0.1", 0)
    root = f"http://127.0.0.1:{server.server_address[1]}"
    link = viewer.link(config, "secret-du-service", "demo", "c1", "reno@exemple.local")
    page = root + link.split("127.0.0.1", 1)[1]

    code, headers, body = get(page)
    expect("page", code, 200)
    expect("page : CSP", "script-src 'self'" in headers.get("Content-Security-Policy", ""), True)
    code, _, body = get(page + "api/arbre")
    tree = json.loads(body) if code == 200 else {}
    expect("arbre : branche", tree.get("branch"), "openwebui/c1")
    expect("arbre : fichiers", sorted(f["path"] for f in tree.get("files", [])),
           ["mission.json", "piege.html", "vault/Contexte.md", "vault/Exigences.md", "vault/contexte.png"])
    expect("liens entrants", tree.get("backlinks", {}).get("vault/Contexte.md"), ["vault/Exigences.md"])
    code, headers, body = get(page + "brut/vault/Exigences.md")
    expect("brut : contenu", body.decode("utf-8").startswith("# Exigences"), True)
    expect("brut : bac à sable", headers.get("Content-Security-Policy"), "sandbox")
    code, headers, _ = get(page + "brut/piege.html")
    expect("HTML servi en texte", headers.get("Content-Type", "").startswith("text/plain"), True)
    expect("fichier hors branche", get(page + "brut/../acces.json")[0], 404)
    expect("chemin inconnu", get(page + "brut/vault/absent.md")[0], 404)
    expect("lien falsifié", get(page[:-2] + ("A" if page[-2] != "A" else "B") + "/")[0], 403)
    expired = viewer.sign("secret-du-service", "demo", "c1", "reno@exemple.local", -1)
    expect("lien expiré", get(f"{root}/fichiers/{expired}/")[0], 403)
    revoked = viewer.link(config, "secret-du-service", "demo", "c1", "ancien@exemple.local")
    expect("droits retirés", get(root + revoked.split("127.0.0.1", 1)[1])[0], 403)
    expect("ressource statique", get(f"{root}/fichiers/_static/viewer.js")[0], 200)
    expect("statique hors dossier", get(f"{root}/fichiers/_static/../viewer.html")[0] in (403, 404), True)
    expect("autres routes protégées", get(f"{root}/missions")[0], 401)

    remote_server.remote_turn.run_turn = lambda *a, **k: {**remote_server.remote_turn.empty_report("demo", "c1")}
    job = service.start("demo", "c1", "m", None)[1]["job"]
    for _ in range(50):
        if service.jobs[job].report is not None:
            break
        time.sleep(0.1)
    expect("lien dans la réponse", (service.jobs[job].report or {}).get("viewer", "").startswith(
        "http://127.0.0.1/fichiers/"), True)
    server.shutdown()

print(json.dumps({"errors": errors, "warnings": []}, ensure_ascii=False))
sys.exit(1 if errors else 0)
