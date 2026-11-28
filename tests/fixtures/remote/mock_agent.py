"""Agent simulé des tests de remote-mission : aucun modèle appelé.

« soumets » : démarre et soumet l'étape documents du workflow de la mission (journal.py, chemin du
skill dans MOCK_SKILLS) ; sinon écrit une note et un schéma (.drawio et .drawio.png).
Termine, comme un agent de myskills, par son rapport final en JSON sur une ligne.
"""

import base64
import json
import os
import subprocess
import sys
from pathlib import Path

PNG = base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==")

prompt = Path(sys.argv[1]).read_text(encoding="utf-8")
message = prompt.split("Message de l'utilisateur :", 1)[-1].strip()
assert os.environ.get("ANTHROPIC_BASE_URL"), "agent.env non transmis"
assert "MYSKILLS_REMOTE_TOKEN" not in os.environ, "jeton du service transmis à l'agent"
print("suite de session" if "--continue" in sys.argv else "nouvelle session", flush=True)
print("lecture du journal", flush=True)
files = []
if "soumets" in message.lower():
    journal = [sys.executable, str(Path(os.environ["MOCK_SKILLS"]) / "decision-log" / "scripts" / "journal.py")]
    subprocess.run(journal + ["start", ".", "documents"], check=True, capture_output=True)
    Path("sources").mkdir(exist_ok=True)
    Path("sources/cahier.md").write_text("# Cahier des charges\n\nLe portail doit permettre de déclarer un sinistre.\n",
                                         encoding="utf-8")
    subprocess.run(journal + ["submit", ".", "documents"], check=True, capture_output=True)
    files = ["sources/cahier.md"]
    print("Étape **documents** soumise : `sources/cahier.md`.")
else:
    Path("schemas").mkdir(exist_ok=True)
    Path("schemas/contexte.drawio").write_text("<mxfile/>", encoding="utf-8")
    Path("schemas/contexte.drawio.png").write_bytes(PNG)
    Path("notes.md").write_text(f"# Notes\n\n{message}\n", encoding="utf-8")
    files = ["notes.md", "schemas/contexte.drawio"]
    print("Schéma de contexte écrit : `schemas/contexte.drawio`.")
print(json.dumps({"agent": "orientation", "status": "ok", "files": files, "tools": "simulé", "level": "simple",
                  "corrections": [], "todo": [], "next": None}, ensure_ascii=False))
