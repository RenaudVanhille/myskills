# /// script
# requires-python = ">=3.10"
# ///
"""Construit la matrice de conformité d'une réponse : chaque exigence, la réponse et sa justification.

Entrée : `conformite.json`, qui renvoie au catalogue d'exigences
(requirements-catalog) et aux options d'architecture (architecture-options),
et donne une réponse par exigence retenue : conforme, partiel, non-conforme
ou sans-objet. Le script, et non le modèle :
- valide les deux fichiers contre le schéma de leur script ;
- prend l'option de la réponse (option, sinon la décision, sinon la
  recommandation) ;
- exige une réponse par exigence retenue, et une justification pour chaque
  réponse partielle ou non conforme ; une réponse conforme sans justification
  reprend les composants de l'option qui couvrent l'exigence ;
- signale une réponse qui contredit les écarts de l'option, et une exigence
  indispensable non conforme ;
- écrit `conformite.md`, `conformite.csv` (séparateur ;) et `conformite.xlsx`,
  puis relit le classeur.

    uv run scripts/compliance_build.py conformite.json [--out-dir DOSSIER] | --schema

Avec --draft, le script écrit d'abord la description (jamais par-dessus un
fichier existant) : une réponse par exigence retenue, tirée des écarts de
l'option, la note de l'écart en indice. Le modèle n'écrit que la
justification des réponses partielles ou non conformes.

    uv run scripts/compliance_build.py conformite.json --draft [--option ID]
"""

import argparse
import csv
import difflib
import json
import sys
import zipfile
from pathlib import Path
from xml.etree import ElementTree
from xml.sax.saxutils import escape

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

STATUSES = ["conforme", "partiel", "non-conforme", "sans-objet"]
FROM_GAP = {"partiel": "partiel", "non": "non-conforme"}
LABELS = {"conforme": "Conforme", "partiel": "Partiellement conforme", "non-conforme": "Non conforme",
          "sans-objet": "Sans objet"}
HEADER = ["Exigence", "Titre", "Type", "Priorité", "Réponse", "Justification", "Composants", "Source"]
WIDTHS = [12, 40, 16, 14, 22, 60, 30, 24]


def load(base: Path, name: str, field: str, skill: str, script: str,
         errors: list[str], warnings: list[str]) -> dict | None:
    """Fichier d'un autre skill, validé contre le schéma d'entrée de son script s'il est installé."""
    path = base / name
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{field} : fichier illisible {path} ({error})")
        return None
    schema = schema_of(skill, script)
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent(skill, script))
    invalid = check(data, schema) if schema else []
    if invalid:
        errors.extend(f"{field} : {path.name} : {e}" for e in invalid[:10])
        return None
    return data


def pick(arch: dict, wanted: str | None, errors: list[str], warnings: list[str]) -> dict | None:
    options = {o["id"]: o for o in arch["options"]}
    decision, rec = arch.get("decision"), arch.get("recommendation") or {}
    if not wanted:
        wanted = (decision or rec).get("option", "")
        if not decision:
            warnings.append(f"réponse sur l'option recommandée {wanted} : aucune décision dans les options")
    elif decision and decision["option"] != wanted:
        warnings.append(f"réponse sur l'option {wanted}, mais la décision retient l'option {decision['option']}")
    if wanted not in options:
        close = difflib.get_close_matches(wanted, list(options), n=1, cutoff=0.5)
        errors.append(f"option : option inconnue « {wanted} »" + (f" ; vouliez-vous « {close[0]} » ?" if close else
                                                                 f" (connues : {', '.join(options)})"))
        return None
    return options[wanted]


def retained(catalog: dict) -> list[dict]:
    return [r for r in catalog["requirements"] if r.get("status", "retenue") == "retenue"]


def kind_of(req: dict) -> str:
    nature = req.get("nature") or {"EF": "fonctionnelle", "ENF": "non-fonctionnelle"}.get(req["id"].split("-")[0], "")
    return nature.replace("-", " ")


def where(req: dict) -> str:
    return ", ".join(s["doc"] for s in req.get("sources", [])) or "déduite"


def draft(path: Path, wanted: str | None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(path), "outputs": [], "option": None, "answers": 0, "to_justify": 0,
              "errors": errors, "warnings": warnings}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une description")
        return report
    base = path.parent
    catalog = load(base, "exigences.json", "requirements", "requirements-catalog", "req_build.py", errors, warnings)
    arch = load(base, "options.json", "architecture", "architecture-options", "options_build.py", errors, warnings)
    option = pick(arch, wanted, errors, warnings) if arch else None
    if errors or not catalog or not option:
        return report
    answers = []
    for req in retained(catalog):
        gap = option.get("gaps", {}).get(req["id"])
        status = "sans-objet" if req["priority"] == "hors-perimetre" else FROM_GAP[gap["level"]] if gap else "conforme"
        answer = {"id": req["id"], "status": status}
        if gap:
            answer["hint"] = gap["note"]
        answers.append(answer)
    spec = {"title": "Matrice de conformité", "requirements": "exigences.json", "architecture": "options.json",
            "option": option["id"], "answers": answers,
            "_draft": "Brouillon de compliance_build.py --draft : réponses tirées des écarts de l'option. Écrire la "
                      "justification de chaque réponse partielle ou non conforme (hint : la note de l'écart) ; une "
                      "réponse conforme sans justification reprend les composants qui couvrent l'exigence."}
    invalid = validate(spec, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], option=option["id"], answers=len(answers),
                  to_justify=sum(1 for a in answers if a["status"] in ("partiel", "non-conforme")))
    return report


def column(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rest = divmod(index - 1, 26)
        name = chr(65 + rest) + name
    return name


def write_xlsx(path: Path, rows: list[list[str]], statuses: list[str]) -> None:
    """Classeur minimal (bibliothèque standard) : en-tête gras figé, filtre, couleur de la réponse."""
    # Style de la cellule Réponse : vert, orange, rouge (cellXfs 2 à 4), sinon texte renvoyé à la ligne (5).
    fill = {"conforme": 2, "partiel": 3, "non-conforme": 4, "sans-objet": 5}
    sheet = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">',
             '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" state="frozen"/>'
             '</sheetView></sheetViews><cols>']
    sheet += [f'<col min="{i + 1}" max="{i + 1}" width="{w}" customWidth="1"/>' for i, w in enumerate(WIDTHS)]
    sheet.append("</cols><sheetData>")
    for r, row in enumerate(rows, 1):
        cells = []
        for c, value in enumerate(row):
            style = 1 if r == 1 else fill[statuses[r - 2]] if c == 4 else 5
            cells.append(f'<c r="{column(c)}{r}" t="inlineStr" s="{style}"><is><t xml:space="preserve">'
                         f'{escape(str(value))}</t></is></c>')
        sheet.append(f'<row r="{r}">{"".join(cells)}</row>')
    sheet.append(f'</sheetData><autoFilter ref="A1:{column(len(HEADER) - 1)}{len(rows)}"/></worksheet>')
    fills = "".join(f'<fill><patternFill patternType="solid"><fgColor rgb="FF{rgb}"/></patternFill></fill>'
                    for rgb in ("DCFCE7", "FEF3C7", "FEE2E2"))
    styles = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
              '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
              '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
              '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
              f'<fills count="5"><fill><patternFill patternType="none"/></fill>'
              f'<fill><patternFill patternType="gray125"/></fill>{fills}</fills>'
              '<borders count="1"><border/></borders><cellStyleXfs count="1"><xf/></cellStyleXfs>'
              '<cellXfs count="6"><xf/>'
              '<xf fontId="1" applyFont="1"/>'
              + "".join(f'<xf fillId="{f}" applyFill="1" applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf>'
                        for f in (2, 3, 4))
              + '<xf applyAlignment="1"><alignment wrapText="1" vertical="top"/></xf></cellXfs>'
              '<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles></styleSheet>')
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
            '</Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Conformité" sheetId="1" r:id="rId1"/></sheets>'
            '<definedNames><definedName name="_xlnm._FilterDatabase" localSheetId="0" hidden="1">'
            f"'Conformité'!$A$1:${column(len(HEADER) - 1)}${len(rows)}</definedName></definedNames></workbook>",
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
            '</Relationships>',
        "xl/worksheets/sheet1.xml": "".join(sheet),
        "xl/styles.xml": styles}
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, text in parts.items():
            archive.writestr(name, text)


def read_xlsx(path: Path) -> int:
    """Relecture : nombre de lignes de la feuille (lève une erreur si le classeur est illisible)."""
    with zipfile.ZipFile(path) as archive:
        for name in ("[Content_Types].xml", "xl/workbook.xml", "xl/styles.xml"):
            ElementTree.fromstring(archive.read(name))
        root = ElementTree.fromstring(archive.read("xl/worksheets/sheet1.xml"))
    return len(root.findall(".//{http://schemas.openxmlformats.org/spreadsheetml/2006/main}row"))


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description conformite.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--draft", action="store_true", help="écrire le brouillon : une réponse par exigence retenue")
    parser.add_argument("--option", help="avec --draft : option de la réponse (défaut : décision, sinon recommandation)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    if args.draft:
        report = draft(args.spec, args.option)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.spec), "outputs": [], "option": None, "requirements": 0,
              "counts": {s: 0 for s in STATUSES}, "rate": None, "errors": errors, "warnings": warnings}
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    errors += validate(spec, __file__)
    base = args.spec.resolve().parent
    catalog = arch = option = None
    if not errors:
        catalog = load(base, spec.get("requirements", "exigences.json"), "requirements", "requirements-catalog",
                       "req_build.py", errors, warnings)
        arch = load(base, spec.get("architecture", "options.json"), "architecture", "architecture-options",
                    "options_build.py", errors, warnings)
        option = pick(arch, spec.get("option"), errors, warnings) if arch else None
    if errors or not catalog or not option:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    reqs = {r["id"]: r for r in retained(catalog)}
    answers: dict[str, dict] = {}
    for index, answer in enumerate(spec["answers"]):
        at = f"answers/{index} ({answer['id']})"
        if answer["id"] in answers:
            errors.append(f"{at} : réponse en double")
        elif answer["id"] not in reqs:
            close = difflib.get_close_matches(answer["id"], list(reqs), n=1, cutoff=0.6)
            errors.append(f"{at} : exigence inconnue ou non retenue" + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            continue
        answers[answer["id"]] = answer
        if answer["status"] in ("partiel", "non-conforme") and not answer.get("justification", "").strip():
            errors.append(f"{at} : justification manquante pour une réponse {answer['status']}")
    missing = [rid for rid in reqs if rid not in answers]
    if missing:
        errors.append(f"exigences sans réponse : {', '.join(missing[:10])}" + (" ..." if len(missing) > 10 else ""))
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    rows, statuses, lines = [HEADER], [], []
    for rid, req in reqs.items():
        answer = answers[rid]
        status = answer["status"]
        gap = option.get("gaps", {}).get(rid)
        expected = FROM_GAP[gap["level"]] if gap else "conforme"
        if status in ("conforme", "partiel", "non-conforme") and status != expected:
            warnings.append(f"{rid} : réponse {status} alors que l'option {option['id']} donne "
                            f"{'un écart ' + gap['level'] if gap else 'aucun écart'}")
        if status == "non-conforme" and req["priority"] == "indispensable":
            warnings.append(f"{rid} : exigence indispensable non conforme, offre à risque")
        comps = [c["label"] for c in option["components"] if rid in c.get("refs", [])]
        text = answer.get("justification") or (f"Couvert par : {', '.join(comps)}" if comps and status == "conforme"
                                               else f"Couvert par l'option {option['id']}" if status == "conforme" else "")
        rows.append([rid, req["title"], kind_of(req), req["priority"], LABELS[status], text, ", ".join(comps),
                     where(req)])
        statuses.append(status)
        report["counts"][status] += 1
    counted = len(reqs) - report["counts"]["sans-objet"]
    report["rate"] = round(100 * report["counts"]["conforme"] / counted, 1) if counted else None
    out_dir = args.out_dir or base
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.stem
    md, csv_path, xlsx = out_dir / f"{stem}.md", out_dir / f"{stem}.csv", out_dir / f"{stem}.xlsx"
    c = report["counts"]
    lines = [f"# {spec.get('title') or 'Matrice de conformité'}", "",
             f"Fichier généré par `compliance_build.py` depuis `{args.spec.name}`, qui fait foi. "
             f"Réponse sur l'option {option['id']} : {option['name']}.", "",
             f"{len(reqs)} exigences : {c['conforme']} conformes, {c['partiel']} partiellement, "
             f"{c['non-conforme']} non conformes, {c['sans-objet']} sans objet"
             + (f" ; taux de conformité {str(report['rate']).replace('.', ',')} %." if report["rate"] is not None else "."),
             "", "| " + " | ".join(HEADER[:6]) + " |", "| " + " | ".join(["---"] * 6) + " |"]
    lines += ["| " + " | ".join(cell(v) for v in row[:6]) + " |" for row in rows[1:]]
    ai_mark.write_text(md, "\n".join(lines) + "\n")
    # utf-8-sig : Excel sous Windows reconnaît alors les accents.
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    write_xlsx(xlsx, rows, statuses)
    ai_mark.mark(xlsx)
    try:
        read = read_xlsx(xlsx)
    except (zipfile.BadZipFile, ElementTree.ParseError, KeyError) as error:
        read = -1
        errors.append(f"{xlsx.name} illisible à la relecture : {error}")
    if read != len(rows) and read != -1:
        errors.append(f"{xlsx.name} : {read} lignes relues pour {len(rows)} écrites")
    report.update(outputs=[str(md), str(csv_path), str(xlsx)], option=option["id"], requirements=len(reqs))
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
