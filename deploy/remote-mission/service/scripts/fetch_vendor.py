# /// script
# requires-python = ">=3.10"
# ///
"""Bibliothèques de la visionneuse des fichiers de mission (marked, DOMPurify, Mermaid), installées en local.

Lit static/vendor.json (version épinglée, URL de l'archive npm, empreinte SHA-256), télécharge chaque
archive, vérifie son empreinte et n'en extrait que le fichier utile dans --dest. Lancé à la construction
des images : le service les sert lui-même, aucun navigateur ne passe par un CDN. --check dit ce qui
manque sans rien télécharger.

    uv run deploy/remote-mission/service/scripts/fetch_vendor.py --dest deploy/remote-mission/service/static/vendor
    uv run deploy/remote-mission/service/scripts/fetch_vendor.py --dest DIR --check

Rapport JSON : {"dest", "installed", "present", "missing", "errors", "warnings"} ; code 1 en cas d'erreur.
"""

import argparse
import hashlib
import io
import json
import sys
import tarfile
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE.parent / "static" / "vendor.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dest", type=Path, default=HERE.parent / "static" / "vendor",
                        help="dossier des bibliothèques (défaut : static/vendor du service)")
    parser.add_argument("--check", action="store_true", help="vérifier seulement ce qui est présent")
    args = parser.parse_args()
    report = {"dest": str(args.dest), "installed": [], "present": [], "missing": [], "errors": [], "warnings": []}
    libs = json.loads(MANIFEST.read_text(encoding="utf-8"))["libs"]
    args.dest.mkdir(parents=True, exist_ok=True) if not args.check else None
    for lib in libs:
        target = args.dest / lib["file"]
        if target.is_file():
            report["present"].append(lib["file"])
            continue
        if args.check:
            report["missing"].append(lib["file"])
            continue
        try:
            with urllib.request.urlopen(lib["url"], timeout=120) as response:
                archive = response.read()
        except OSError as error:
            report["errors"].append(f"{lib['name']} {lib['version']} : téléchargement impossible ({error})")
            continue
        digest = hashlib.sha256(archive).hexdigest()
        if digest != lib["sha256"]:
            report["errors"].append(f"{lib['name']} {lib['version']} : empreinte {digest} au lieu de {lib['sha256']}")
            continue
        with tarfile.open(fileobj=io.BytesIO(archive), mode="r:gz") as tar:
            member = tar.extractfile(lib["member"])
            if member is None:
                report["errors"].append(f"{lib['name']} : {lib['member']} absent de l'archive")
                continue
            target.write_bytes(member.read())
        report["installed"].append(lib["file"])
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
