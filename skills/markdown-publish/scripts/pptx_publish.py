# /// script
# requires-python = ">=3.10"
# dependencies = []
# ///
"""Délègue une présentation PowerPoint à l'agent externe concepteur-deck, puis la vérifie.

myskills ne contient ni l'agent ni le skill markdown-to-pptx qui fait le
rendu : il s'appuie sur le seul contrat de l'agent
(scripts/lib/concepteur-deck.contract.json, copie de shared/external/).
Un script ne lance pas un agent : ce script prépare la demande, l'agent
appelant la passe à concepteur-deck, puis ce script vérifie le résultat.

Préparer (avant l'agent) :
- vérifie les sources : Markdown, images présentes et en PNG, JPEG ou SVG
  (un schéma source s'exporte d'abord avec diagram-export), texte
  alternatif, consignes <!-- slide: KIND --> connues du contrat ;
- en mode convertir, écrit la copie de travail dans .myskills-tmp/ (liens
  du journal retirés, chemins d'images recalculés) : l'agent la corrige,
  jamais la source ;
- trouve l'agent installé et écrit la demande (message de passage validé
  contre le schéma `request` du contrat) dans le rapport, champ `handoff`.
Vérifier (après l'agent, --check) : rouvre le .pptx (diapositives, images,
objets sans texte alternatif), valide l'état de relecture contre le schéma
`output_schema` du contrat, compare le Markdown relu, compte les points
[à compléter] et retire les copies .before-* laissées par le rendu.
Affiche un rapport JSON. Usage :
    uv run scripts/pptx_publish.py SOURCE.md [SOURCE...] [--out NOM.pptx] [--mode convertir|concevoir]
        [--objective TEXTE] [--audience technique|"non technique"] [--trame NOM] [--template MARQUE.potx]
        [--lang fr|en] [--slides N]
    uv run scripts/pptx_publish.py --check NOM.pptx [--source DECK.md]
"""

import argparse
import hashlib
import json
import os
import re
import sys
import zipfile
from pathlib import Path
from urllib.parse import unquote

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import external_skill  # noqa: E402
from spec_schema import check  # noqa: E402
from text_tools import unlink_notes  # noqa: E402

AGENT = "concepteur-deck"
TMP = ".myskills-tmp"
IMAGE = re.compile(r"(!\[([^\]]*)\]\(<?)([^)>\s]+)(>?(?:\s+\"[^\"]*\")?\))")
EMBED = re.compile(r"!\[\[([^\]|#]+)(?:\|([^\]]*))?\]\]")
HINT = re.compile(r"<!--\s*slide:\s*([a-z]+)")
TODO = re.compile(r"\[à compléter\]")
PICTURES = {".png", ".jpg", ".jpeg", ".svg"}
DIAGRAM_SOURCES = {".drawio", ".excalidraw", ".mmd", ".mermaid"}
SOURCES = {".md", ".markdown", ".txt", ".json", ".csv", ".pdf", ".docx", ".pptx", ".xlsx", ".png", ".jpg", ".jpeg"}


def check_markdown(doc: Path, text: str, kinds: list[str], strict: bool) -> tuple[int, list[str], list[str]]:
    """(images citées, erreurs, avertissements). strict : Markdown à convertir tel quel (conventions du contrat)."""
    errors, warnings, images = [], [], 0
    where = f"{doc.name} : " if not strict else ""
    if EMBED.search(text):
        errors.append(f"{where}syntaxe Obsidian ![[...]] : écrivez ![texte](chemin) (skill markdown-to-obsidian, sens inverse)")
    if re.search(r"^```mermaid", text, re.M):
        errors.append(f"{where}bloc mermaid : exportez-le en PNG (skill diagram-export) et citez l'image")
    for line, row in enumerate(text.splitlines(), 1):
        for _, alt, target, _ in IMAGE.findall(row):
            if re.match(r"^[a-z]+:", target):
                continue
            images += 1
            path = doc.parent / unquote(target)
            suffix = path.suffix.lower()
            if suffix in DIAGRAM_SOURCES:
                errors.append(f"{where}ligne {line} : {target} est un schéma source ; exportez-le en PNG "
                              f"(uv run ../diagram-export/scripts/export.py {target} --format png) et citez le PNG")
            elif not path.is_file():
                errors.append(f"{where}ligne {line} : image introuvable {target}")
            elif suffix not in PICTURES:
                errors.append(f"{where}ligne {line} : {target} : format {suffix or '?'} non lu, PNG, JPEG ou SVG attendu")
            if not alt.strip():
                warnings.append(f"{where}ligne {line} : image {target} sans texte alternatif")
        for kind in HINT.findall(row):
            if kind not in kinds:
                errors.append(f"{where}ligne {line} : consigne slide « {kind} » inconnue du contrat")
    if strict and len(re.findall(r"^# ", text, re.M)) != 1:
        warnings.append("un seul titre # attendu : il devient la couverture")
    return images, errors, warnings


def working_copy(doc: Path, text: str, target: Path) -> str:
    """Copie à convertir : liens du journal retirés, images relatives recalculées depuis target."""
    def rebase(match: re.Match) -> str:
        link = match.group(3)
        if re.match(r"^[a-z]+:", link) or Path(unquote(link)).is_absolute():
            return match.group(0)
        try:
            moved = Path(os.path.relpath(doc.parent / unquote(link), target.parent)).as_posix()
        except ValueError:  # autre lecteur sous Windows : chemin absolu
            moved = (doc.parent / unquote(link)).resolve().as_posix()
        return f"{match.group(1)}{moved}{match.group(4)}"
    return IMAGE.sub(rebase, unlink_notes(text))


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


def prepare(args, spec: dict, report: dict) -> int:
    sources = [p.resolve() for p in args.sources]
    report["inputs"] = [str(p) for p in args.sources]
    report["errors"] += [f"source introuvable : {raw}" for p, raw in zip(sources, args.sources) if not p.is_file()]
    if args.mode == "convertir" and len(sources) != 1:
        report["errors"].append("mode convertir : un seul Markdown attendu (plusieurs sources : --mode concevoir)")
    if args.template and not args.template.is_file():
        report["errors"].append(f"gabarit introuvable : {args.template}")
    if args.trame and args.trame not in spec["trames"]:
        report["errors"].append(f"trame « {args.trame} » inconnue du contrat ({', '.join(spec['trames'])})")
    for path in sources:
        if not path.is_file():
            continue
        suffix = path.suffix.lower()
        if args.mode == "convertir" and suffix not in (".md", ".markdown"):
            report["errors"].append(f"{path.name} : Markdown attendu (.md) en mode convertir")
        elif suffix not in SOURCES:
            report["warnings"].append(f"{path.name} : format {suffix or '?'} peut-être illisible pour l'agent")
        if suffix in (".md", ".markdown"):
            images, errors, warnings = check_markdown(path, path.read_text(encoding="utf-8"),
                                                      spec["markdown"]["kinds"], args.mode == "convertir")
            report["images"] += images
            report["errors"] += errors
            report["warnings"] += warnings
    if report["errors"]:
        return 1
    first = sources[0]
    out = (args.out.resolve() if args.out else first.with_suffix(".pptx"))
    if out.suffix.lower() != ".pptx":
        report["errors"].append(f"{out.name} : fichier .pptx attendu pour --out")
        return 1
    deck_md = out.with_suffix(".md")
    if args.mode == "concevoir" and deck_md in sources:
        report["errors"].append(f"mode concevoir : l'agent écrit {deck_md.name}, qui est une source ; "
                                "donnez un autre nom à --out")
        return 1
    _, agent = external_skill.locate_agent(AGENT)
    if agent is None:
        report["errors"].append(external_skill.missing_message(spec))
        return 1
    report["agent"] = str(agent)
    tmp = Path.cwd().resolve() / TMP
    preview = tmp / f"{out.stem}-apercu"
    files = [str(p) for p in sources]
    constraints = [f"mode : {args.mode}"]
    if args.mode == "convertir":
        copy = tmp / f"{out.stem}.md"
        copy.parent.mkdir(parents=True, exist_ok=True)
        copy.write_text(working_copy(first, first.read_text(encoding="utf-8"), copy), encoding="utf-8", newline="\n")
        files = [str(copy)]
        constraints.append(f"Markdown complet : convertis {copy} sans le réécrire ; corrige seulement cette copie "
                           "aux lignes signalées par la relecture")
    else:
        constraints.append(f"écris le Markdown du deck dans {deck_md}")
    if args.trame:
        constraints.append(f"trame : {args.trame}")
    if args.template:
        constraints.append(f"gabarit : {args.template.resolve()}")
    if args.lang:
        constraints.append(f"langue : {args.lang}")
    if args.slides:
        constraints.append(f"taille cible : {args.slides} diapositives")
    constraints += [
        "délégation : ne pose aucune question, prends l'option la plus probable et note-la dans tes hypothèses",
        f"génère avec --strict --review new --autofix --preview {preview} ; corrige le Markdown, jamais le .pptx",
        "ne modifie aucune source ; termine par les chemins du .md et du .pptx, les hypothèses et les points "
        "[à compléter]",
    ]
    handoff = {"agent": AGENT, "objective": args.objective or f"Présentation PowerPoint de {first.stem}",
               "files": files, "audience": args.audience, "destination": "powerpoint", "output": str(out),
               "constraints": constraints, "level": "complexe" if args.mode == "concevoir" else "moyen"}
    invalid = check(handoff, spec["request"])
    if invalid:
        report["errors"] += [f"demande non conforme au contrat de {AGENT} : {e}" for e in invalid]
        return 1
    report["handoff"] = handoff
    report["output"] = str(out)
    return 0


def find_state(out: Path) -> Path | None:
    for folder in (Path.cwd().resolve() / TMP / f"{out.stem}-apercu", out.parent / "apercu"):
        if (folder / f"{out.stem}.review.json").is_file():
            return folder / f"{out.stem}.review.json"
    return None


def verify(args, spec: dict, report: dict) -> int:
    out = args.check.resolve()
    report["inputs"] = [str(args.check)]
    if not out.is_file() or out.suffix.lower() != ".pptx":
        report["errors"].append(f"présentation introuvable : {args.check}" if not out.is_file()
                                else f"{out.name} : fichier .pptx attendu")
        return 1
    try:
        found = inspect(out)
    except (zipfile.BadZipFile, KeyError) as error:
        report["errors"].append(f"{out.name} illisible : {error}")
        return 1
    report.update(slides=found["slides"], images=found["pictures"], missing_alt=len(found["missing_alt"]))
    if not found["slides"]:
        report["errors"].append(f"{out.name} : aucune diapositive")
    if found["missing_alt"]:
        report["warnings"].append("objet sans texte alternatif, diapositive(s) "
                                  + ", ".join(map(str, sorted(set(found["missing_alt"])))))
    candidates = [args.source.resolve()] if args.source else \
        [Path.cwd().resolve() / TMP / f"{out.stem}.md", out.with_suffix(".md")]
    deck_md = next((p for p in candidates if p.is_file()), None)
    if deck_md is None:
        report["warnings"].append(f"Markdown du deck introuvable ({', '.join(str(p) for p in candidates)}) : "
                                  "images et points [à compléter] non comptés")
    else:
        text = deck_md.read_text(encoding="utf-8")
        cited, _, _ = check_markdown(deck_md, text, spec["markdown"]["kinds"], False)
        report["todo"] = len(TODO.findall(text))
        if report["todo"]:
            report["warnings"].append(f"{report['todo']} point(s) [à compléter] dans {deck_md.name}")
        if found["pictures"] < cited:
            report["errors"].append(f"{found['pictures']} image(s) dans la présentation, {cited} citée(s)")
    state_path = find_state(out)
    if state_path is None:
        report["warnings"].append(f"pas d'état de relecture {out.stem}.review.json : rendu non relu par {AGENT}")
    else:
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
        except ValueError as error:
            state = None
            report["errors"].append(f"{state_path.name} illisible : {error}")
        invalid = check(state, spec["output_schema"]) if state is not None else []
        report["errors"] += [f"état de relecture non conforme au contrat : {e}" for e in invalid]
        if state is not None and not invalid:
            report["review"] = {"status": state["status"], "round": state["round"], "issues": state["issues"]}
            meaning = spec["verdicts"][state["status"]]
            if state["status"] == "fix":
                report["errors"].append(f"relecture : {meaning} ({state['issues']} défaut(s), tour {state['round']})")
            elif state["status"] == "stop":
                report["warnings"].append(f"relecture : {meaning} ({state['issues']} défaut(s))")
            if deck_md is not None and state["md"] and state["md"] != hashlib.sha1(deck_md.read_bytes()).hexdigest():
                report["errors"].append(f"{deck_md.name} modifié après la dernière génération : relancez le rendu")
    for leftover in (out.with_suffix(".before-update.pptx"),
                     *(p.with_suffix(".before-autofix.md") for p in ([deck_md] if deck_md else []))):
        if leftover.is_file():
            leftover.unlink()
            report["removed"].append(str(leftover))
    if report["errors"]:
        return 1
    report["output"] = str(out)
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", type=Path, nargs="*", help="Markdown à convertir, ou sources du deck à concevoir")
    parser.add_argument("--out", type=Path, help="présentation à produire (défaut : première source en .pptx)")
    parser.add_argument("--mode", choices=["convertir", "concevoir"], default="convertir",
                        help="convertir un Markdown complet (défaut) ou concevoir le deck depuis les sources")
    parser.add_argument("--objective", help="décision ou action que le deck doit obtenir, et de qui")
    parser.add_argument("--audience", choices=["technique", "non technique"], default="non technique")
    parser.add_argument("--trame", help="trame de l'agent (propale, copil, comite-archi...)")
    parser.add_argument("--template", type=Path, help="gabarit .potx de la marque")
    parser.add_argument("--lang", choices=["fr", "en"], help="langue du deck (défaut : celle des sources)")
    parser.add_argument("--slides", type=int, help="taille cible en diapositives")
    parser.add_argument("--check", type=Path, metavar="NOM.pptx", help="vérifier la présentation rendue par l'agent")
    parser.add_argument("--source", type=Path, help="avec --check : Markdown du deck, s'il n'est pas à sa place")
    args = parser.parse_args()
    report = {"mode": "verifier" if args.check else "preparer", "inputs": [], "output": None, "agent": None,
              "handoff": None, "slides": 0, "images": 0, "missing_alt": 0, "review": None, "todo": 0,
              "removed": [], "errors": [], "warnings": []}
    spec = external_skill.contract(AGENT)
    if args.check and args.sources:
        report["errors"].append("--check vérifie une présentation : pas de source à préparer en même temps")
        code = 1
    elif not args.check and not args.sources:
        report["errors"].append("source attendue (ou --check NOM.pptx)")
        code = 1
    else:
        code = verify(args, spec, report) if args.check else prepare(args, spec, report)
    print(json.dumps(report, ensure_ascii=False))
    return code


if __name__ == "__main__":
    sys.exit(main())
