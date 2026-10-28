# /// script
# requires-python = ">=3.10"
# ///
"""Épingle un modèle local dans shared/model-sources.json, ou vérifie les épinglages.

Seuls les modèles de cette liste peuvent être téléchargés par les scripts de
myskills (shared/scripts/model_store.py) : révision fixée (commit) et
empreinte SHA-256 de chaque fichier. Ajouter un modèle est une décision de
sécurité, relue en PR.

Usage :
    uv run scripts/pin_model.py ID --repo AUTEUR/NOM [--revision main] [--files a,b]
        [--purpose TEXTE] [--license LICENCE] [--write]
    uv run scripts/pin_model.py --check [ID ...]

Sans --write, l'entrée est seulement affichée dans le rapport. --check
compare chaque modèle épinglé à sa source (révision présente, mêmes
empreintes) : à lancer en CI. Seuls les hôtes de `hosts` sont contactés.

Rapport JSON sur la sortie standard (shared/schemas/pin-report.schema.json).
Codes de sortie : 0 succès, 1 erreur (source injoignable, empreinte différente,
entrée invalide).
"""

import argparse
import hashlib
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "shared" / "scripts"))
import model_store  # noqa: E402

model_store.SOURCES = REPO / "shared" / "model-sources.json"
model_store.SCHEMA = REPO / "shared" / "schemas" / "model-sources.schema.json"
SKIPPED = {".gitattributes", "README.md"}


def get(url: str):
    if not model_store.host_allowed(url):
        raise model_store.ModelError(f"hôte non autorisé : {urllib.parse.urlsplit(url).hostname}")
    opener = urllib.request.build_opener(model_store._AllowedRedirects())
    return opener.open(url, timeout=60)


def remote(repo: str, revision: str) -> dict:
    """Commit et empreinte SHA-256 de chaque fichier à cette révision (LFS : donnée
    par la source ; autres fichiers : téléchargés et calculés)."""
    with get(f"https://huggingface.co/api/models/{repo}/revision/{revision}?blobs=true") as response:
        info = json.load(response)
    commit, files = info["sha"], {}
    for sibling in info.get("siblings", []):
        name = sibling["rfilename"]
        if (sibling.get("lfs") or {}).get("sha256"):
            files[name] = sibling["lfs"]["sha256"]
        elif name not in SKIPPED:
            digest = hashlib.sha256()
            with get(f"https://huggingface.co/{repo}/resolve/{commit}/{name}") as response:
                while block := response.read(model_store.CHUNK):
                    digest.update(block)
            files[name] = digest.hexdigest()
    return {"revision": commit, "files": files}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="identifiant du modèle (whisper-small...)")
    parser.add_argument("--repo", help="dépôt Hugging Face AUTEUR/NOM")
    parser.add_argument("--revision", default="main", help="branche, étiquette ou commit à épingler")
    parser.add_argument("--files", help="fichiers à garder, séparés par des virgules (défaut : tous sauf README)")
    parser.add_argument("--purpose", default="", help="usage du modèle")
    parser.add_argument("--license", default="", help="licence du modèle")
    parser.add_argument("--write", action="store_true", help="écrire l'entrée dans shared/model-sources.json")
    parser.add_argument("--check", action="store_true", help="vérifier les modèles épinglés contre leur source")
    args = parser.parse_args()
    report = {"models": [], "errors": [], "warnings": []}
    try:
        data = model_store.sources()
    except model_store.ModelError as error:
        report["errors"].append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1

    if args.check:
        for model in args.ids or sorted(data["models"]):
            spec = data["models"].get(model)
            if not spec:
                report["errors"].append(f"modèle « {model} » non épinglé")
                continue
            try:
                found = remote(spec["source"]["repo"], spec["source"]["revision"])
            except (OSError, ValueError, KeyError, model_store.ModelError) as error:
                report["errors"].append(f"{model} : source injoignable : {error}")
                continue
            differ = [name for name, value in spec["files"].items() if found["files"].get(name) != value]
            report["models"].append({"id": model, "revision": found["revision"], "files": len(spec["files"]),
                                     "ok": not differ})
            report["errors"] += [f"{model} : {name} absent ou différent à la révision épinglée" for name in differ]
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0

    if len(args.ids) != 1 or not args.repo:
        report["errors"].append("donnez un identifiant et --repo AUTEUR/NOM (ou --check)")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    try:
        found = remote(args.repo, args.revision)
    except (OSError, ValueError, KeyError, model_store.ModelError) as error:
        report["errors"].append(f"source injoignable : {error}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    keep = set(args.files.split(",")) if args.files else set(found["files"]) - SKIPPED
    missing = sorted(keep - set(found["files"]))
    if missing:
        report["errors"].append(f"fichiers absents de la source : {', '.join(missing)}")
    entry = {"purpose": args.purpose or "à décrire", "license": args.license or "à vérifier",
             "source": {"provider": "huggingface", "repo": args.repo, "revision": found["revision"]},
             "files": {name: found["files"][name] for name in sorted(keep) if name in found["files"]}}
    report["models"].append({"id": args.ids[0], "revision": found["revision"], "files": len(entry["files"]),
                             "ok": not missing, "entry": entry})
    if args.write and not missing:
        data["models"][args.ids[0]] = entry
        model_store.SOURCES.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["warnings"].append("shared/model-sources.json modifié : lancez uv run scripts/build.py")
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
