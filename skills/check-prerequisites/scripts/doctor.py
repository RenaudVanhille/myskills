# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie les outils locaux dont les skills de myskills ont besoin (Windows,
macOS, Linux) et affiche un rapport JSON.

MarkItDown, Pandoc et Playwright sont fournis par uv aux scripts qui les
utilisent (dépendances PEP 723), Docling par `uvx` : seul uv est alors
obligatoire, leur installation à part est facultative.

Usage : uv run scripts/doctor.py [extraction|video|schemas|publication|revue|tout] [--prefetch]
        [--models-from DOSSIER]
Code de sortie : 0 si tous les outils obligatoires sont présents, 1 sinon
(ou groupe inconnu, ou préchargement en échec).

--prefetch télécharge dans le cache les bibliothèques JavaScript des rendus
(Mermaid, Excalidraw), à version fixée, et vérifie leur empreinte : la
machine peut ensuite travailler hors ligne (MYSKILLS_OFFLINE=1). Avec le
groupe extraction (Docling : mise en page et tableaux ; Laya), video
(Whisper) ou tout, il télécharge aussi les modèles locaux du groupe,
seulement depuis leur source épinglée dans model-sources.json, et vérifie
l'empreinte SHA-256 de chaque fichier. --models-from DOSSIER les copie
depuis un dossier (machine sans accès à la source, copie du cache), avec la
même vérification. Un run ne télécharge aucun modèle : il le lit dans ce
cache, ou s'arrête en donnant cette commande.
"""

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import external_skill  # noqa: E402
import local_tools  # noqa: E402
import model_store  # noqa: E402

# Modèles locaux préchargés par groupe (identifiants de model-sources.json) : un
# run n'en télécharge aucun, il les lit dans le cache vérifié.
GROUP_MODELS = {"extraction": ["docling-layout-heron", "docling-tableformer", "laya"],
                "video": ["whisper-small"]}
MODEL_USES = {"docling-layout-heron": "Docling, mise en page des PDF", "docling-tableformer": "Docling, tableaux",
              "laya": "tri des documents par Laya, --classify", "whisper-small": "transcription locale"}


def model_row(model: str, need: str, group: str) -> tuple:
    return (f"Modèle {model} vérifié dans le cache ({MODEL_USES[model]})", need,
            lambda: model_known(model) and model_store.local_model(model) is not None,
            f"uv run scripts/doctor.py {group} --prefetch")

# Bibliothèques des pages HTML (groupe maquettes) ; les autres paquets servent aux schémas.
MOCKUP_PACKAGES = ["bootstrap"]
UV = ("uv", "obligatoire", lambda: shutil.which("uv") is not None, "https://docs.astral.sh/uv/")
# (outil, obligatoire ou facultatif, test, commande ou page d'installation)
GROUPS = {
    "extraction": [
        UV,
        ("MarkItDown installé à part (sinon fourni par uv)", "facultatif",
         lambda: shutil.which("markitdown") is not None, 'uv tool install "markitdown[docx,pptx,xlsx,xls,pdf,outlook]"'),
        ("Docling installé à part (sinon lancé par uvx, ~2 Go au premier lancement)", "facultatif",
         lambda: shutil.which("docling") is not None, "uv tool install docling"),
        ("Tesseract (OCR local des PDF scannés ; sinon transcription par la vision)", "facultatif",
         lambda: shutil.which("tesseract") is not None,
         "winget install UB-Mannheim.TesseractOCR | brew install tesseract tesseract-lang | "
         "apt install tesseract-ocr tesseract-ocr-fra"),
        *(model_row(model, "facultatif", "extraction") for model in GROUP_MODELS["extraction"]),
    ],
    "video": [
        UV,
        *(model_row(model, "obligatoire", "video") for model in GROUP_MODELS["video"]),
    ],
    "schemas": [
        UV,
        ("draw.io Desktop", "obligatoire", lambda: local_tools.drawio_binary() is not None,
         "https://github.com/jgraph/drawio-desktop/releases"),
        ("Navigateur pour Playwright (Edge, Chrome ou Chromium)", "obligatoire", local_tools.browser_available,
         "uvx playwright install chromium"),
        ("Node.js (LikeC4 via npx)", "facultatif", lambda: shutil.which("node") is not None, "https://nodejs.org/"),
        ("LikeC4 installé (plus rapide que npx, nécessaire hors ligne)", "facultatif",
         lambda: shutil.which("likec4") is not None, "npm install -g likec4"),
        *((f"{name} {version} dans le cache (rendus hors ligne)", "facultatif",
           lambda name=name: local_tools.cached_package(name) is not None, "uv run scripts/doctor.py --prefetch")
          for name, (version, _, _) in local_tools.PACKAGES.items() if name not in MOCKUP_PACKAGES),
    ],
    "maquettes": [
        UV,
        ("Navigateur pour Playwright (Edge, Chrome ou Chromium) : rendu et comparaison des pages", "obligatoire",
         local_tools.browser_available, "uvx playwright install chromium"),
        *((f"{name} {local_tools.PACKAGES[name][0]} dans le cache (pages Bootstrap hors ligne)", "facultatif",
           lambda name=name: local_tools.cached_package(name) is not None, "uv run scripts/doctor.py maquettes --prefetch")
          for name in MOCKUP_PACKAGES),
    ],
    "publication": [
        UV,
        ("LibreOffice (PDF et relecture visuelle des .docx)", "facultatif",
         lambda: local_tools.soffice_binary() is not None, "https://www.libreoffice.org/download/"),
        ("Skill markdown-to-pptx installé à part (export PowerPoint)", "facultatif",
         lambda: external_skill.locate("markdown-to-pptx")[1] is not None,
         external_skill.contract("markdown-to-pptx")["install"]),
    ],
    "revue": [
        UV,
        ("graphify installé à part (code comparé à l'architecture, analyse locale)", "facultatif",
         lambda: external_skill.locate("graphify")[1] is not None, external_skill.contract("graphify")["install"]),
    ],
}


def model_known(model: str) -> bool:
    try:
        model_store.entry(model)
        return True
    except model_store.ModelError:
        return False


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    args = sys.argv[1:]
    prefetch = "--prefetch" in args
    args = [a for a in args if a != "--prefetch"]
    models_from = None
    if "--models-from" in args:
        index = args.index("--models-from")
        models_from = Path(args[index + 1]) if index + 1 < len(args) else Path()
        args = args[:index] + args[index + 2:]
        prefetch = True
    group = args[0] if args else "tout"
    if group != "tout" and group not in GROUPS:
        print(json.dumps({"group": group, "tools": [], "missing": [],
                          "errors": [f"groupe inconnu « {group} » (extraction, video, schemas, publication, revue, tout)"],
                          "warnings": []}, ensure_ascii=False))
        return 1
    errors = []
    if prefetch:
        for name in local_tools.PACKAGES:
            try:
                local_tools.npm_package(name)
            except local_tools.PackageError as error:
                errors.append(str(error))
        for name in GROUP_MODELS if group == "tout" else [group]:
            for model in GROUP_MODELS.get(name, []):
                if local_tools.offline() and not models_from:
                    continue
                try:
                    model_store.fetch(model, models_from)
                except model_store.ModelError as error:
                    errors.append(str(error))
    tools, seen = [], set()
    for name in GROUPS if group == "tout" else [group]:
        for label, need, test, install in GROUPS[name]:
            if label in seen:
                continue
            seen.add(label)
            status = "ok" if test() else ("manquant" if need == "obligatoire" else "absent")
            tools.append({"name": label, "group": name, "status": status,
                          **({"install": install} if status != "ok" else {})})
    missing = [t["name"] for t in tools if t["status"] == "manquant"]
    report = {"group": group, "tools": tools, "missing": missing,
              "errors": errors + [f"{t['name']} manquant : {t['install']}" for t in tools if t["status"] == "manquant"],
              "warnings": [f"{t['name']} absent (facultatif) : {t['install']}" for t in tools
                           if t["status"] == "absent"]}
    if local_tools.offline():
        report["warnings"].append("mode hors ligne (MYSKILLS_OFFLINE) : rien ne sera téléchargé")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if missing or errors else 0


if __name__ == "__main__":
    sys.exit(main())
