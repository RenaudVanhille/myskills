# /// script
# requires-python = ">=3.10"
# ///
"""Assemble le dossier d'architecture technique (DAT) d'un dossier de workflow, selon un gabarit de sections.

Le gabarit (JSON, `references/gabarit-dat.json` par défaut) liste les
sections dans l'ordre, chacune avec ses pièces sources (motifs relatifs au
dossier) : Markdown repris tel quel (frontmatter et titre retirés, titres
décalés sous la section, liens recalés), images intégrées, ou fichiers
listés en annexe. Le modèle n'écrit que la synthèse (`synthese.md`) ; tout
le reste vient des livrables déjà validés du workflow, sans recopie.

Le script relit le dossier produit : chaque image et chaque lien local doit
exister. Une section obligatoire sans pièce est signalée (erreur avec
--strict, sans fichier produit).

Avec --tender ao.json (dépouillement de tender-response), le dossier est un
mémoire technique : les sections à thème suivent l'ordre des critères de
notation, chacune rappelle le critère et son poids ; un critère sans section
remplie et un mémoire qui dépasse le budget de pages du règlement (annexes
exclues, pages estimées sur les mots et les images) sont signalés (erreurs
avec --strict).

    uv run scripts/dossier_build.py DOSSIER [--template GABARIT.json] [--out dossier-architecture.md]
                                    [--title TITRE] [--tender ao.json] [--strict] | --schema
"""

import argparse
import json
import os
import re
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

TEMPLATE = Path(__file__).resolve().parent.parent / "references" / "gabarit-dat.json"
LINK = re.compile(r"(!?\[[^\]]*\])\(([^)\s]+)(\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
FRONTMATTER = re.compile(r"\A---\n.*?\n---\n", re.S)
# Pages d'un mémoire estimées sans rendu : mots par page, part de page d'une image.
WORDS_PER_PAGE = 450
IMAGE_PAGE = 0.5


def load_tender(path: Path, errors: list[str], warnings: list[str]) -> dict | None:
    """Dépouillement (tender-response), validé contre le schéma de tender_build.py s'il est installé."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"tender : fichier illisible {path} ({error})")
        return None
    schema = schema_of("tender-response", "tender_build.py")
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent("tender-response", "tender_build.py"))
    invalid = check(data, schema) if schema else []
    if invalid:
        errors.extend(f"tender : {path.name} : {e}" for e in invalid[:10])
        return None
    return data


def leaves(tender: dict) -> list[dict]:
    """Critères notés sur le mémoire : sans sous-critère, hors prix."""
    criteria = tender.get("criteria", [])
    parents = {c.get("parent") for c in criteria}
    return [c for c in criteria if c["id"] not in parents and c["topic"] != "prix"]


def follow(sections: list[dict], criteria: list[dict]) -> list[dict]:
    """Sections à thème rangées dans l'ordre des critères ; les autres gardent leur place avant ou après."""
    rank: dict[str, int] = {}
    for index, criterion in enumerate(criteria):
        rank.setdefault(criterion["topic"], index)
    topical = [s for s in sections if s.get("topic")]
    if not topical:
        return sections
    first = sections.index(topical[0])
    return ([s for s in sections[:first] if not s.get("topic")]
            + sorted(topical, key=lambda s: rank.get(s["topic"], len(rank)))
            + [s for s in sections[first:] if not s.get("topic")])


def matches(folder: Path, patterns: list[str], out: Path) -> list[Path]:
    """Fichiers du dossier pour ces motifs, dans l'ordre des motifs, sans doublon ni le dossier produit."""
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(folder.glob(pattern)):
            if path.is_file() and path not in found and path.resolve() != out.resolve() \
                    and ".myskills-tmp" not in path.parts:
                found.append(path)
    return found


def relative(target: Path, out_dir: Path) -> str:
    """Chemin de la cible vu du dossier produit ; absolu si elle est sur un autre lecteur (Windows)."""
    try:
        return Path(os.path.relpath(target, out_dir)).as_posix()
    except ValueError:
        return Path(target).resolve().as_posix()


def relink(text: str, source: Path, out_dir: Path) -> str:
    """Recale les liens et images relatifs d'une pièce sur l'emplacement du dossier produit."""
    def fix(match: re.Match) -> str:
        target = match.group(2)
        if re.match(r"^([a-z]+:|#|/)", target):
            return match.group(0)
        path, _, anchor = target.partition("#")
        moved = relative(source.parent / path, out_dir)
        return f"{match.group(1)}({moved}{'#' + anchor if anchor else ''}{match.group(3) or ''})"
    return LINK.sub(fix, text)


def demote(text: str, levels: int) -> tuple[str, str | None]:
    """Retire le frontmatter et le premier titre de niveau 1 (rendu à part), décale les autres titres."""
    text = FRONTMATTER.sub("", text, count=1)
    lines, title, fence = [], None, False
    for line in text.splitlines():
        if line.lstrip().startswith(("```", "~~~")):
            fence = not fence
        heading = None if fence else HEADING.match(line)
        if heading and len(heading.group(1)) == 1 and title is None:
            title = heading.group(2).strip()
            continue
        if heading:
            line = "#" * min(6, len(heading.group(1)) + levels) + " " + heading.group(2)
        lines.append(line)
    return "\n".join(lines).strip(), title


def check_links(text: str, out_dir: Path) -> list[str]:
    """Liens et images locaux du dossier produit qui ne mènent à rien."""
    missing = []
    for match in LINK.finditer(text):
        target = match.group(2).partition("#")[0]
        if target and not re.match(r"^[a-z][a-z0-9+.-]+:", target) and not (out_dir / target).exists():
            missing.append(target)
    return sorted(set(missing))


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, nargs="?", help="dossier du workflow (livrables validés)")
    parser.add_argument("--template", type=Path, help="gabarit des sections : fichier JSON, ou nom d'un gabarit livré "
                                                      "(dat, défaut ; avis : avis sur un dossier reçu ; conformite : dossier de conformité ; migration : dossier de migration ; memoire : mémoire technique ; documentation ; restitution ; existant)")
    parser.add_argument("--out", type=Path, help="dossier produit (défaut : DOSSIER/dossier-architecture.md)")
    parser.add_argument("--title", help="titre du dossier (défaut : titre du workflow, sinon celui du gabarit)")
    parser.add_argument("--tender", type=Path,
                        help="dépouillement ao.json (tender-response) : mémoire technique dans l'ordre des critères, "
                             "couverture des critères et budget de pages contrôlés")
    parser.add_argument("--strict", action="store_true",
                        help="section obligatoire sans pièce : erreur, et aucun fichier produit")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON du gabarit sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.folder:
        parser.error("DOSSIER attendu")
    errors: list[str] = []
    warnings: list[str] = []
    template_path = args.template or TEMPLATE
    # Un nom court désigne un gabarit livré : --template avis -> references/gabarit-avis.json.
    if args.template and args.template.name == str(args.template) and not args.template.suffix:
        template_path = TEMPLATE.with_name(f"gabarit-{args.template.name}.json")
    report = {"input": str(args.folder), "template": str(template_path), "output": None, "sections": 0,
              "included": [], "missing": [], "pieces": 0, "images": 0, "criteria": None, "pages": None,
              "page_budget": None, "errors": errors, "warnings": warnings}
    if not args.folder.is_dir():
        errors.append(f"dossier introuvable : {args.folder}")
    try:
        template = json.loads(template_path.read_text(encoding="utf-8"))
        # Gabarit validé contre le schéma d'entrée du contract.json avant tout traitement.
        errors += validate(template, __file__)
    except (OSError, ValueError) as error:
        errors.append(f"gabarit illisible : {error}")
        template = None
    if template and not errors:
        ids = [s["id"] for s in template["sections"]]
        errors += [f"sections : identifiant en double « {i} »" for i in sorted({i for i in ids if ids.count(i) > 1})]
    tender = load_tender(args.tender, errors, warnings) if args.tender else None
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    folder = args.folder
    out = args.out or folder / "dossier-architecture.md"
    out_dir = out.resolve().parent
    title = args.title
    if not title and (folder / "workflow.json").exists():
        try:
            title = json.loads((folder / "workflow.json").read_text(encoding="utf-8")).get("title")
        except ValueError:
            warnings.append("workflow.json illisible : titre du gabarit")
    title = title or template.get("title", "Dossier d'architecture technique")
    body: list[str] = []
    toc: list[str] = []
    criteria = leaves(tender) if tender else []
    sections = follow(template["sections"], criteria) if tender else template["sections"]
    covered: set[str] = set()
    words, pictures = 0, 0
    for section in sections:
        pieces = matches(folder, section["sources"], out)
        kind = section.get("kind", "markdown")
        if kind == "images":
            pieces = [p for p in pieces if p.suffix.lower() in (".png", ".jpg", ".jpeg", ".svg", ".gif")]
        elif kind == "markdown":
            pieces = [p for p in pieces if p.suffix.lower() == ".md"]
        if not pieces:
            if section.get("required"):
                report["missing"].append(section["id"])
                hint = f" ({section['help']})" if section.get("help") else ""
                (errors if args.strict else warnings).append(
                    f"section « {section['id']} » sans pièce : {', '.join(section['sources'])}{hint}")
            else:
                continue
        heading = f"{len(toc) + 1}. {section['title']}"
        toc.append(f"- [{heading}](#{re.sub(r'[^a-z0-9à-ÿ -]', '', heading.lower()).replace(' ', '-')})")
        body += [f"## {heading}", ""]
        answered = [c for c in criteria if c["topic"] == section.get("topic")]
        if answered and section["topic"] not in covered:
            body += ["> Répond au critère " + ", ".join(f"{c['id']} « {c['label']} » ({c['weight']} %)"
                                                         for c in answered) + ".", ""]
        if section.get("intro"):
            body += [section["intro"], ""]
        if not pieces:
            body += [f"> À compléter : aucune pièce ({', '.join(section['sources'])}).", ""]
            continue
        report["included"].append(section["id"])
        report["pieces"] += len(pieces)
        if section.get("topic"):
            covered.add(section["topic"])
        counted = not section.get("annex") and kind != "files"
        for piece in pieces:
            rel = relative(piece.resolve(), out_dir)
            if kind == "images":
                report["images"] += 1
                pictures += counted
                body += [f"![{piece.stem}]({rel})", "", f"*{piece.stem}*", ""]
            elif kind == "files":
                body.append(f"- [{piece.relative_to(folder).as_posix()}]({rel})")
            else:
                text, piece_title = demote(piece.read_text(encoding="utf-8"), 2 if len(pieces) > 1 else 1)
                if len(pieces) > 1:
                    body += [f"### {piece_title or piece.stem}", ""]
                body += [relink(text, piece.resolve(), out_dir), ""]
                report["images"] += len(re.findall(r"!\[[^\]]*\]\(", text))
                if counted:
                    words += len(re.findall(r"\w+", re.sub(r"\]\([^)]*\)", "]", text)))
                    pictures += len(re.findall(r"!\[[^\]]*\]\(", text))
        if kind == "files":
            body.append("")
    report["sections"] = len(toc)
    if tender:
        uncovered = [c for c in criteria if c["topic"] not in covered]
        report["criteria"] = {"covered": [c["id"] for c in criteria if c["topic"] in covered],
                              "uncovered": [c["id"] for c in uncovered]}
        for c in uncovered:
            where = [s["id"] for s in sections if s.get("topic") == c["topic"]]
            (errors if args.strict else warnings).append(
                f"critère {c['id']} « {c['label']} » ({c['weight']} %) sans section remplie"
                + (f" : {', '.join(where)}" if where else f" : aucune section de thème {c['topic']} dans le gabarit"))
        report["pages"] = round(words / WORDS_PER_PAGE + pictures * IMAGE_PAGE, 1)
        budget = next((p.get("pages") for p in tender.get("pieces", []) if p.get("memoire")), None)
        report["page_budget"] = budget
        if budget and report["pages"] > budget:
            (errors if args.strict else warnings).append(
                f"mémoire estimé à {report['pages']} pages pour {budget} au plus (annexes exclues)")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    text = "\n".join([f"# {title}", "", f"Version du {date.today().isoformat()}, assemblée depuis `{folder.name}/` "
                      "par dossier_build.py (skill architecture-dossier).", "", "## Sommaire", "", *toc, "", *body])
    text = re.sub(r"\n{3,}", "\n\n", text).rstrip() + "\n"
    broken = check_links(text, out_dir)
    if broken:
        warnings.append(f"{len(broken)} lien(s) ou image(s) introuvable(s) : {', '.join(broken[:5])}")
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    report["output"] = str(out)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
