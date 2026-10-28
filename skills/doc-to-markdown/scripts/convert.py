# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = ["markitdown[docx,pptx,xlsx,pdf]>=0.1.7", "pypdf>=5", "pypdfium2>=4"]
# ///
"""Convertit un document (PDF, DOCX, PPTX, XLSX, image) en Markdown, en local.

Les images sont extraites dans <sortie>/attachments/ et liées en relatif.
Un dossier donne tous ses documents convertibles. Deux documents de même nom
(rapport.pdf, rapport.docx) donnent rapport-pdf.md et rapport-docx.md : rien
n'est écrasé.
Affiche un rapport JSON sur la sortie standard.

Usage :
    uv run scripts/convert.py FICHIER|DOSSIER [...] [--out DOSSIER] [--engine auto|markitdown|docling]
        [--classify [--domains a,b]] [--no-clean] [--skip-existing] [--jobs N]

Moteurs :
    markitdown  rapide, bon sur Office et les PDF simples (défaut en auto)
    docling     PDF scannés (OCR) ou riches en tableaux ; lancé via `uvx`
                s'il n'est pas installé (premier lancement long : ~2 Go)

L'OCR de Docling passe par Tesseract installé en local, jamais par son
choix automatique : RapidOCR, qu'il prend par défaut, télécharge ses modèles
depuis ModelScope (modelscope.cn). Sans Tesseract, Docling tourne sans OCR et
les pages scannées vont à la vision. Les fichiers audio et vidéo sont refusés
(Docling les transcrit avec des modèles téléchargés, MarkItDown les envoie à
un service de reconnaissance vocale en ligne).

Avec --classify, chaque document passe d'abord par classify.py (modèle local
Laya) : type et domaine sont ajoutés au rapport, et un PDF riche en tableaux
ou en colonnes part sur Docling en mode auto.

Un PDF converti par MarkItDown est nettoyé (lignes d'un même paragraphe
réunies, césures recollées, en-têtes et pieds de page répétés retirés à
partir de 3 pages) ; ce que le script ne peut pas trancher (titres probables,
mots peut-être coupés) va dans `hints`, avec le numéro de ligne. --no-clean
désactive ce nettoyage.

Les pages à transcrire par vision (scannées, sans OCR) sont rendues en PNG
dans <sortie>/.myskills-tmp/<nom>-pages/ et listées dans `vision_pages` :
seules ces images sont à ouvrir.

Avec --skip-existing, un document dont le Markdown existe déjà et est plus
récent que lui n'est pas reconverti : les corrections faites dessus restent.

Les documents d'un lot se convertissent en parallèle (--jobs, par défaut
jusqu'à 4) ; Docling, qui occupe déjà tous les cœurs, garde un document à la
fois. Le rapport suit l'ordre des documents.

Chaque Markdown produit est vérifié comme par validate.py : le résultat est
dans `validation` du rapport, inutile de lancer validate.py juste après.
"""

import argparse
import base64
import concurrent.futures
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from validate import check

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from script_report import print_report  # noqa: E402

OFFICE = {".docx", ".pptx", ".xlsx", ".xls", ".doc", ".ppt"}
IMAGES = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
# Audio et vidéo : non pris en charge (transcription par modèle ou service en ligne).
MEDIA = {".mp4", ".m4a", ".mov", ".avi", ".mkv", ".webm", ".mp3", ".wav", ".ogg", ".flac"}
# Langues OCR de Tesseract essayées, dans l'ordre (fichiers .traineddata).
OCR_LANGS = ("fra", "eng")
# Documents pris dans un dossier passé en argument.
CONVERTIBLE = OFFICE | IMAGES | {".pdf", ".html", ".htm", ".csv", ".epub"}
# En dessous de ce nombre de caractères, une page PDF est considérée scannée.
MIN_CHARS_PER_PAGE = 30
# Côté le plus long d'une page rendue pour la vision : au-delà, le modèle la
# réduit de toute façon, et chaque pixel en plus coûte des tokens.
VISION_MAX_PX = 1568
MAX_HINTS = 40
CLASSIFY = Path(__file__).with_name("classify.py")
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


def is_text(line: str) -> bool:
    """Ligne de texte courant : ni vide, ni titre, ni tableau, ni liste, ni image."""
    s = line.strip()
    return bool(s) and not re.match(r"^(#|\||[-*+•] |\d+[.)] |!\[|<!--|```|>)", s)


def heading_like(line: str) -> bool:
    s = line.strip()
    if not s or len(s) > 80 or re.search(r"[.,;:!?)]$", s):
        return False
    if re.match(r"^\d+(\.\d+)*[.)]?\s+[A-ZÀ-Ý]", s):  # titre numéroté : 1. Introduction, 2.3 Flux
        return len(s) <= 60
    return is_text(s) and (s[0].isupper() or s[0].isdigit())


def clean_pdf_text(markdown: str, pages: int | None) -> tuple[str, list[str]]:
    """Nettoyage sûr d'un PDF converti par MarkItDown, et indices pour le reste."""
    lines = markdown.split("\n")
    # En-têtes et pieds de page : même ligne courte (chiffres ignorés) sur la plupart des pages.
    removed = set()
    if pages and pages >= 3:
        counts: dict[str, int] = {}
        for line in lines:
            if is_text(line) and len(line.strip()) <= 80:
                key = re.sub(r"\d+", "#", line.strip())
                counts[key] = counts.get(key, 0) + 1
        removed = {key for key, n in counts.items() if n >= max(3, pages * 0.6)}
    kept = [l for l in lines if not (is_text(l) and re.sub(r"\d+", "#", l.strip()) in removed)]

    widths = sorted(len(l.strip()) for l in kept if is_text(l))
    wide = widths[int(len(widths) * 0.9)] * 0.6 if widths else 0
    vocabulary = set(re.findall(r"\w+", " ".join(kept).lower()))
    out, hints = [], []
    for line in kept:
        previous = out[-1] if out else ""
        joinable = (is_text(previous) and is_text(line) and len(previous.strip()) >= wide
                    and not re.search(r"[.!?:]$", previous.strip()))
        if not joinable:
            # Une ligne vide entre un paragraphe et un tableau, pour que le tableau se rende.
            if previous.strip() and line.strip() and is_text(previous) != is_text(line) \
                    and (line.lstrip().startswith("|") or previous.lstrip().startswith("|")):
                out.append("")
            out.append(line.rstrip())
            continue
        head, tail = previous.rstrip(), line.strip()
        if re.search(r"\w-$", head) and tail[:1].islower():
            out[-1] = head[:-1] + tail  # césure
        elif re.search(r"\w$", head) and tail[:1].islower():
            left, right = re.search(r"(\w+)$", head).group(1), re.match(r"(\w+)", tail).group(1)
            if (left + right).lower() in vocabulary and left.lower() not in vocabulary:
                out[-1] = head + tail
            else:
                out[-1] = head + " " + tail
                hints.append(f"Ligne {len(out)} : mot peut-être coupé « {left} {right} »")
        else:
            out[-1] = head + " " + tail
    for number, line in enumerate(out, 1):
        if heading_like(line) and len(hints) < MAX_HINTS:
            hints.append(f"Ligne {number} : titre probable « {line.strip()} »")
    if removed:
        hints.insert(0, f"En-têtes ou pieds de page retirés : {', '.join(sorted(removed))}")
    return "\n".join(out), hints[:MAX_HINTS]


def render_pages(pdf: Path, numbers: list[int], folder: Path) -> list[str]:
    """Rend les pages demandées en PNG, côté le plus long limité à VISION_MAX_PX."""
    import pypdfium2 as pdfium

    folder.mkdir(parents=True, exist_ok=True)
    document = pdfium.PdfDocument(str(pdf))
    paths = []
    for number in numbers:
        page = document[number - 1]
        scale = min(2.0, VISION_MAX_PX / max(page.get_size()))
        target = folder / f"page-{number}.png"
        page.render(scale=scale).to_pil().save(target)
        paths.append(str(target))
    document.close()
    return paths


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


def tesseract_langs() -> list[str]:
    """Langues de OCR_LANGS installées pour Tesseract ; vide sans Tesseract."""
    if not shutil.which("tesseract"):
        return []
    try:
        listed = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                                text=True, encoding="utf-8", timeout=30).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return []
    return [lang for lang in OCR_LANGS if lang in listed]


def docling_ocr_args() -> list[str]:
    """OCR de Docling : Tesseract local, sinon aucun. Jamais le choix
    automatique, qui prend RapidOCR et télécharge ses modèles sur ModelScope."""
    langs = tesseract_langs()
    if not langs:
        return ["--no-ocr"]
    return ["--ocr-engine", "tesseract_cli", "--ocr-lang", ",".join(langs)]


# Docling prend déjà tous les cœurs et beaucoup de mémoire : un document à la fois.
DOCLING_SLOT = threading.Semaphore(1)


def run_docling(path: Path, attachments: Path, stem: str) -> tuple[str, int]:
    command = docling_command()
    if command is None:
        raise RuntimeError("Docling introuvable : installez-le (uv tool install docling).")
    with tempfile.TemporaryDirectory() as tmp:
        env = {**os.environ, "HF_HUB_DISABLE_TELEMETRY": "1", "DO_NOT_TRACK": "1"}
        subprocess.run(command + [str(path), "--to", "md", "--image-export-mode",
                                  "referenced", *docling_ocr_args(), "--output", tmp],
                       check=True, capture_output=True, text=True, env=env)
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


def run_classifier(files: list[Path], domains: str | None) -> tuple[dict, str | None]:
    """Lance classify.py dans son propre environnement (dépendances lourdes)."""
    command = (["uv", "run", "--quiet", str(CLASSIFY)] if shutil.which("uv")
               else [sys.executable, str(CLASSIFY)])
    command += [str(f) for f in files] + (["--domains", domains] if domains else [])
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    try:
        reports = json.loads(result.stdout)["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        lines = (result.stderr or "sortie vide").strip().splitlines()
        return {}, f"Classification impossible : {lines[-1][:300] if lines else '?'}"
    return {Path(r["input"]).resolve(): r for r in reports if "error" not in r}, None


def unique_stems(files: list[Path]) -> dict[Path, str]:
    """Nom de sortie de chaque document : son nom sans extension, suivi de
    l'extension (rapport-pdf) quand deux documents du lot portent le même nom,
    pour qu'aucun Markdown ni aucune image n'en écrase un autre. Comparaison sans
    casse, comme sous Windows et macOS."""
    stems: dict[Path, str] = {}
    taken: set[str] = set()
    counts: dict[str, int] = {}
    for path in files:
        counts[path.stem.lower()] = counts.get(path.stem.lower(), 0) + 1
    for path in files:
        stem = path.stem if counts[path.stem.lower()] == 1 else f"{path.stem}-{path.suffix[1:].lower()}"
        base, number = stem, 2
        while stem.lower() in taken:
            stem, number = f"{base}-{number}", number + 1
        taken.add(stem.lower())
        stems[path] = stem
    return stems


def expand(paths: list[Path], out: Path) -> list[Path]:
    """Un dossier donne ses documents convertibles (sous-dossiers compris, hors
    Markdown, dossiers cachés et dossier de sortie)."""
    files = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in CONVERTIBLE
                            and not any(part.startswith(".") for part in p.relative_to(path).parts)
                            and out not in p.resolve().parents)
        else:
            files.append(path)
    return list(dict.fromkeys(files))


def convert(path: Path, out: Path, engine: str, classification: dict | None = None,
            clean: bool = True, stem: str | None = None) -> dict:
    suffix = path.suffix.lower()
    stem = stem or path.stem
    attachments = out / "attachments"
    report = {"input": str(path), "output": str(out / f"{stem}.md"),
              "type": None, "engine": None, "pages": None, "images": 0,
              "needs_vision": False, "warnings": []}
    if classification:
        report["classification"] = {key: classification[key] for key in
                                    ("type", "domaine", "tables", "engine", "method", "warnings")}

    if suffix in MEDIA:
        raise ValueError("audio ou vidéo non pris en charge : la transcription locale n'est pas "
                         "fournie (Docling télécharge des modèles, MarkItDown appelle un service en ligne)")
    if suffix in IMAGES:
        report["type"], report["engine"] = "image", "copie"
        attachments.mkdir(parents=True, exist_ok=True)
        image = f"{stem}{suffix}"
        shutil.copy2(path, attachments / image)
        markdown = (f"# {path.stem}\n\n![{path.stem}](attachments/{image})\n\n"
                    "<!-- vision : transcrire ici le contenu de l'image -->\n")
        report["images"], report["needs_vision"] = 1, True
        report["vision_pages"] = [str(attachments / image)]
    else:
        profile = {"pages": None, "scanned_pages": []}
        if suffix == ".pdf":
            report["type"] = "pdf"
            profile = pdf_profile(path)
            report["pages"] = profile["pages"]
            if profile["scanned_pages"]:
                report["warnings"].append(
                    f"Pages sans texte (scannées ?) : {profile['scanned_pages']}")
                ocr = bool(tesseract_langs())
                if engine == "auto" and ocr:
                    engine = "docling"
                elif not ocr:
                    report["warnings"].append(
                        "OCR local absent (Tesseract) : pages scannées à transcrire par la vision")
                    report["needs_vision"] = True
            if engine == "auto" and classification and classification["engine"] == "docling":
                report["warnings"].append(
                    f"Tableaux ou colonnes probables ({classification['tables']}) : Docling")
                engine = "docling"
        elif suffix in OFFICE:
            report["type"] = "office"
        else:
            report["type"] = "autre"
        if engine == "auto":
            engine = "markitdown"

        if engine == "docling":
            try:
                with DOCLING_SLOT:
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
            if report["type"] == "pdf" and clean:
                markdown, report["hints"] = clean_pdf_text(markdown, report["pages"])
        report["engine"] = engine

    if len(markdown.strip()) < 20:
        report["warnings"].append("Résultat presque vide : document scanné ou protégé ?")
        report["needs_vision"] = True
        profile["scanned_pages"] = list(range(1, (report["pages"] or 0) + 1))
    if report["type"] == "pdf" and report["needs_vision"] and profile["scanned_pages"]:
        report["vision_pages"] = render_pages(path, profile["scanned_pages"],
                                              out / ".myskills-tmp" / f"{stem}-pages")
    out.mkdir(parents=True, exist_ok=True)
    with open(out / f"{stem}.md", "w", encoding="utf-8", newline="\n") as handle:
        handle.write(markdown.rstrip() + "\n")
    result = check(out / f"{stem}.md", obsidian=False)
    report["validation"] = {key: result[key] for key in ("ok", "errors", "warnings")}
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path, help="documents ou dossiers")
    parser.add_argument("--out", type=Path, default=Path("."))
    parser.add_argument("--engine", choices=["auto", "markitdown", "docling"], default="auto")
    parser.add_argument("--classify", action="store_true",
                        help="classer d'abord les documents avec le modèle local Laya")
    parser.add_argument("--domains", help="avec --classify : domaines possibles, séparés par des virgules")
    parser.add_argument("--skip-existing", action="store_true",
                        help="ne pas reconvertir un document dont le Markdown est plus récent")
    parser.add_argument("--no-clean", action="store_true",
                        help="ne pas nettoyer le texte des PDF (paragraphes, césures, en-têtes)")
    parser.add_argument("--jobs", type=int, default=min(4, os.cpu_count() or 1),
                        help="documents convertis en même temps (défaut : jusqu'à 4 ; 1 : un par un)")
    args = parser.parse_args()

    reports, failed = [], False
    files = expand(args.files, args.out.resolve())
    stems = unique_stems(files)
    classifications, classify_warning = {}, None
    if args.classify:
        existing = [path.resolve() for path in files
                    if path.is_file() and path.suffix.lower() not in IMAGES]
        if existing:
            classifications, classify_warning = run_classifier(existing, args.domains)
    def one(path: Path) -> tuple[dict, bool]:
        """Rapport d'un document et s'il a échoué."""
        if not path.is_file():
            return {"input": str(path), "error": "Fichier introuvable"}, True
        target = args.out.resolve() / f"{stems[path]}.md"
        if args.skip_existing and target.is_file() and target.stat().st_mtime >= path.stat().st_mtime:
            return {"input": str(path), "output": str(target), "skipped": True}, False
        try:
            report = convert(path.resolve(), args.out.resolve(), args.engine,
                             classifications.get(path.resolve()), not args.no_clean, stems[path])
            if stems[path] != path.stem:
                report["warnings"].append(f"Nom déjà pris dans le lot : écrit sous {stems[path]}.md")
            return report, False
        except Exception as error:  # noqa: BLE001 - le rapport doit lister chaque échec
            return {"input": str(path), "error": f"{type(error).__name__}: {error}"}, True

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        for report, error in pool.map(one, files):
            reports.append(report)
            failed = failed or error
    print_report(reports, warnings=[classify_warning] if classify_warning else [])
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
