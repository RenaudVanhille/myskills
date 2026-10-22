# /// script
# requires-python = ">=3.10"
# dependencies = ["markitdown[docx,pptx,xlsx,pdf]>=0.1.7", "pypdf>=5"]
# ///
"""Convertit un document (PDF, DOCX, PPTX, XLSX, image) en Markdown, en local.

Les images sont extraites dans <sortie>/attachments/ et liées en relatif.
Affiche un rapport JSON sur la sortie standard.

Usage :
    uv run scripts/convert.py FICHIER [--out DOSSIER] [--engine auto|markitdown|docling]

Moteurs :
    markitdown  rapide, bon sur Office et les PDF simples (défaut en auto)
    docling     PDF scannés (OCR) ou riches en tableaux ; lancé via `uvx`
                s'il n'est pas installé (premier lancement long : ~2 Go)
"""

import argparse
import base64
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

OFFICE = {".docx", ".pptx", ".xlsx", ".xls", ".doc", ".ppt"}
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
# En dessous de ce nombre de caractères, une page PDF est considérée scannée.
MIN_CHARS_PER_PAGE = 30
DATA_URI = re.compile(r"!\[([^\]]*)\]\(data:image/([a-zA-Z0-9.+-]+);base64,([^)]+)\)")


def pdf_profile(path: Path) -> dict:
    from pypdf import PdfReader

    reader = PdfReader(str(path))
    chars = [len((page.extract_text() or "").strip()) for page in reader.pages]
    scanned = [i + 1 for i, n in enumerate(chars) if n < MIN_CHARS_PER_PAGE]
    return {"pages": len(chars), "scanned_pages": scanned}


def extract_data_uris(markdown: str, attachments: Path, stem: str) -> tuple[str, int]:
    """Remplace les images base64 par des fichiers dans attachments/."""
    count = 0

    def save(match: re.Match) -> str:
        nonlocal count
        count += 1
        alt, ext, data = match.groups()
        ext = {"jpeg": "jpg", "svg+xml": "svg"}.get(ext.lower(), ext.lower())
        name = f"{stem}-{count}.{ext}"
        attachments.mkdir(parents=True, exist_ok=True)
        (attachments / name).write_bytes(base64.b64decode(data))
        return f"![{alt or name}](attachments/{name})"

    return DATA_URI.sub(save, markdown), count


def promote_empty_headers(markdown: str) -> str:
    """Remplace un en-tête de tableau vide (fréquent avec Word) par la
    première ligne de données."""
    lines = markdown.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        is_empty_header = (line.strip().startswith("|")
                           and not line.replace("|", "").strip()
                           and i + 2 < len(lines)
                           and set(lines[i + 1].replace("|", "").strip()) <= {"-", ":", " "}
                           and lines[i + 2].strip().startswith("|"))
        if is_empty_header:
            out += [lines[i + 2], lines[i + 1]]
            i += 3
            continue
        out.append(line)
        i += 1
    return "\n".join(out)


def run_markitdown(path: Path) -> str:
    from markitdown import MarkItDown

    text = MarkItDown().convert(str(path), keep_data_uris=True).text_content
    return promote_empty_headers(text)


def docling_command() -> list[str] | None:
    if shutil.which("docling"):
        return ["docling"]
    if shutil.which("uvx"):
        return ["uvx", "--from", "docling", "docling"]
    return None


def run_docling(path: Path, attachments: Path, stem: str) -> tuple[str, int]:
    command = docling_command()
    if command is None:
        raise RuntimeError("Docling introuvable : installez-le (uv tool install docling).")
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(command + [str(path), "--to", "md", "--image-export-mode",
                                  "referenced", "--output", tmp],
                       check=True, capture_output=True, text=True)
        tmp_dir = Path(tmp)
        markdown = next(tmp_dir.glob("*.md")).read_text(encoding="utf-8")
        count = 0
        for image in sorted(p for p in tmp_dir.rglob("*") if p.suffix.lower() in IMAGES):
            count += 1
            name = f"{stem}-{count}{image.suffix.lower()}"
            attachments.mkdir(parents=True, exist_ok=True)
            shutil.copy2(image, attachments / name)
            relative = image.relative_to(tmp_dir).as_posix()
            markdown = markdown.replace(relative, f"attachments/{name}")
    return markdown, count


def convert(path: Path, out: Path, engine: str) -> dict:
    suffix = path.suffix.lower()
    stem = path.stem
    attachments = out / "attachments"
    report = {"input": str(path), "output": str(out / f"{stem}.md"),
              "type": None, "engine": None, "pages": None, "images": 0,
              "needs_vision": False, "warnings": []}

    if suffix in IMAGES:
        report["type"], report["engine"] = "image", "copie"
        attachments.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, attachments / path.name)
        markdown = (f"# {stem}\n\n![{stem}](attachments/{path.name})\n\n"
                    "<!-- vision : transcrire ici le contenu de l'image -->\n")
        report["images"], report["needs_vision"] = 1, True
    else:
        if suffix == ".pdf":
            report["type"] = "pdf"
            profile = pdf_profile(path)
            report["pages"] = profile["pages"]
            if profile["scanned_pages"]:
                report["warnings"].append(
                    f"Pages sans texte (scannées ?) : {profile['scanned_pages']}")
                if engine == "auto":
                    engine = "docling"
        elif suffix in OFFICE:
            report["type"] = "office"
        else:
            report["type"] = "autre"
        if engine == "auto":
            engine = "markitdown"

        if engine == "docling":
            try:
                markdown, report["images"] = run_docling(path, attachments, stem)
            except (RuntimeError, subprocess.CalledProcessError) as error:
                detail = (getattr(error, "stderr", "") or str(error)).strip().splitlines()
                last = detail[-1] if detail else "erreur inconnue"
                report["warnings"].append(f"Docling a échoué, repli sur MarkItDown : {last[:300]}")
                engine = "markitdown"
        if engine == "markitdown":
            markdown, report["images"] = extract_data_uris(run_markitdown(path), attachments, stem)
            if report["type"] == "pdf" and report["warnings"]:
                report["needs_vision"] = True
        report["engine"] = engine

    if len(markdown.strip()) < 20:
        report["warnings"].append("Résultat presque vide : document scanné ou protégé ?")
        report["needs_vision"] = True
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{stem}.md", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown.rstrip() + "\n")
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--engine", choices=["auto", "markitdown", "docling"], default="auto")
    args = parser.parse_args()

    reports, failed = [], False
    for path in args.files:
        if not path.is_file():
            reports.append({"input": str(path), "error": "Fichier introuvable"})
            failed = True
            continue
        try:
            reports.append(convert(path.resolve(), args.out.resolve(), args.engine))
        except Exception as error:  # noqa: BLE001 - le rapport doit lister chaque échec
            reports.append({"input": str(path), "error": f"{type(error).__name__}: {error}"})
            failed = True
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
