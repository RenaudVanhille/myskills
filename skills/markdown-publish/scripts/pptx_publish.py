# /// script
# requires-python = ">=3.10"
# dependencies = ["python-pptx>=1.0", "markdown-it-py>=3.0"]
# ///
"""Publie un Markdown en présentation PowerPoint avec le skill markdown-to-pptx, installé à part.

myskills ne contient pas ce skill : il le trouve et l'appelle par son seul
contrat d'interface (scripts/lib/markdown-to-pptx.contract.json, copie de
shared/external/). Le script :
- vérifie le Markdown : images présentes et en PNG, JPEG ou SVG (un schéma
  source s'exporte d'abord avec diagram-export), texte alternatif, consignes
  <!-- slide: KIND --> connues du contrat ;
- lance le skill dans le dossier du Markdown (son dossier .md2pptx/ de marque
  est ainsi trouvé), avec --plan ;
- valide le plan rendu contre le schéma du contrat, puis rouvre le .pptx :
  nombre de diapositives, images, objets sans texte alternatif.
Affiche un rapport JSON. Usage :
    uv run scripts/pptx_publish.py DOC.md [--out DOSSIER] [--template MARQUE.potx] [--lang fr|en]
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
import external_skill  # noqa: E402
from spec_schema import check  # noqa: E402

SKILL = "markdown-to-pptx"
IMAGE = re.compile(r"!\[([^\]]*)\]\(<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\)")
EMBED = re.compile(r"!\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]")
HINT = re.compile(r"<!--\s*slide:\s*([a-z]+)")
PICTURES = {".png", ".jpg", ".jpeg", ".svg"}
DIAGRAM_SOURCES = {".drawio", ".excalidraw", ".mmd", ".mermaid"}


def check_markdown(doc: Path, text: str, kinds: list[str]) -> tuple[int, list[str], list[str]]:
    """(images citées, erreurs, avertissements) avant tout rendu."""
    errors, warnings, images = [], [], 0
    if EMBED.search(text):
        errors.append("syntaxe Obsidian ![[...]] : écrivez ![texte](chemin) (skill markdown-to-obsidian, sens inverse)")
    if re.search(r"^```mermaid", text, re.M):
        errors.append("bloc mermaid : exportez-le en PNG (skill diagram-export) et citez l'image")
    for line, row in enumerate(text.splitlines(), 1):
        for alt, target in IMAGE.findall(row):
            if re.match(r"^[a-z]+:", target):
                continue
            images += 1
            path = (doc.parent / unquote(target))
            suffix = path.suffix.lower()
            if suffix in DIAGRAM_SOURCES:
                errors.append(f"ligne {line} : {target} est un schéma source ; exportez-le en PNG "
                              f"(uv run ../diagram-export/scripts/export.py {target} --format png) et citez le PNG")
            elif not path.is_file():
                errors.append(f"ligne {line} : image introuvable {target}")
            elif suffix not in PICTURES:
                errors.append(f"ligne {line} : {target} : format {suffix or '?'} non lu, PNG, JPEG ou SVG attendu")
            if not alt.strip():
                warnings.append(f"ligne {line} : image {target} sans texte alternatif")
        for kind in HINT.findall(row):
            if kind not in kinds:
                errors.append(f"ligne {line} : consigne slide « {kind} » inconnue du contrat ({', '.join(kinds)})")
    if len(re.findall(r"^# ", text, re.M)) != 1:
        warnings.append("un seul titre # attendu : il devient la couverture")
    return images, errors, warnings


def inspect(path: Path) -> dict:
    """Relit le .pptx : diapositives, images, objets (image, tableau, graphique) sans texte alternatif."""
    with zipfile.ZipFile(path) as archive:
        slides = sorted((n for n in archive.namelist() if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)),
                        key=lambda n: int(re.search(r"\d+", n.rsplit("/", 1)[1]).group()))
        pictures, missing = 0, []
        for number, name in enumerate(slides, 1):
            xml = archive.read(name).decode("utf-8")
            for tag in re.findall(r"<p:(?:pic|graphicFrame)\b.*?<p:cNvPr\b[^>]*>", xml, re.S):
                pictures += tag.startswith("<p:pic")
                if "descr=" not in tag.rsplit("<p:cNvPr", 1)[1]:
                    missing.append(number)
    return {"slides": len(slides), "pictures": pictures, "missing_alt": missing}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("doc", type=Path, help="document Markdown")
    parser.add_argument("--out", type=Path, help="dossier de sortie (défaut : à côté du Markdown)")
    parser.add_argument("--template", type=Path, help="gabarit .potx de la marque")
    parser.add_argument("--lang", choices=["fr", "en"], help="langue des libellés générés (défaut : détectée)")
    args = parser.parse_args()
    report = {"input": str(args.doc), "output": None, "skill": None, "version": None, "slides": 0,
              "kinds": {}, "images": 0, "missing_alt": 0, "errors": [], "warnings": []}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    spec, entry = external_skill.locate(SKILL)
    if not args.doc.is_file() or args.doc.suffix.lower() not in (".md", ".markdown"):
        report["errors"].append(f"Markdown introuvable : {args.doc}" if not args.doc.is_file()
                                else f"{args.doc.name} : Markdown attendu (.md)")
        return done(1)
    if args.template and not args.template.is_file():
        report["errors"].append(f"gabarit introuvable : {args.template}")
        return done(1)
    doc = args.doc.resolve()
    expected, errors, warnings = check_markdown(doc, doc.read_text(encoding="utf-8"), spec["markdown"]["kinds"])
    report["errors"] += errors
    report["warnings"] += warnings
    if entry is None:
        report["errors"].append(external_skill.missing_message(spec))
    if report["errors"]:
        return done(1)
    report["skill"] = str(entry.parent.parent)
    report["version"], warning = external_skill.version(spec, entry)
    if warning:
        report["warnings"].append(warning)

    out = (args.out.resolve() if args.out else doc.parent) / f"{doc.stem}.pptx"
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        plan_path = Path(tmp) / "plan.json"
        command = [sys.executable, str(entry), str(doc), "-o", str(out), "--plan", str(plan_path)]
        if args.template:
            command += ["--template", str(args.template.resolve())]
        if args.lang:
            command += ["--lang", args.lang]
        result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                                cwd=doc.parent)
        if result.returncode != 0 or not out.is_file() or not plan_path.is_file():
            meaning = spec["exit_codes"].get(str(result.returncode), "code inattendu")
            tail = (result.stderr.strip().splitlines() or [""])[-1][:300]
            report["errors"].append(f"{SKILL} : code {result.returncode} ({meaning}) {tail}".strip())
            out.unlink(missing_ok=True)
            return done(1)
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    invalid = check(plan, spec["plan"])
    if invalid:
        report["errors"] += [f"plan rendu non conforme au contrat : {e}" for e in invalid]
        out.unlink(missing_ok=True)
        return done(1)
    kinds = [s["kind"] for s in plan["slides"]]
    report["kinds"] = {k: kinds.count(k) for k in dict.fromkeys(kinds)}
    report["warnings"] += [f"{SKILL} : {w}" for w in plan.get("warnings", [])]
    try:
        found = inspect(out)
    except (zipfile.BadZipFile, KeyError) as error:
        report["errors"].append(f"{out.name} illisible : {error}")
        out.unlink(missing_ok=True)
        return done(1)
    report.update(slides=found["slides"], images=found["pictures"], missing_alt=len(found["missing_alt"]))
    if found["slides"] != len(kinds):
        report["errors"].append(f"{found['slides']} diapositive(s) écrite(s), {len(kinds)} dans le plan")
    if found["pictures"] < expected:
        report["errors"].append(f"{found['pictures']} image(s) dans la présentation, {expected} citée(s)")
    if found["missing_alt"]:
        report["warnings"].append("objet sans texte alternatif, diapositive(s) "
                                  + ", ".join(map(str, sorted(set(found["missing_alt"])))))
    if report["errors"]:
        out.unlink(missing_ok=True)
        return done(1)
    ai_mark.inherit(doc, [out])
    report["output"] = str(out)
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
