# /// script
# requires-python = ">=3.10"
# ///
"""Assemble la présentation d'un dossier d'architecture à partir des étapes déjà validées.

Lit le dossier du workflow, sans rien demander au modèle :
- options.json (validé contre le schéma d'options_build.py) et le catalogue
  d'exigences qu'il cite ; decision.json s'il existe ;
- les PNG des schémas déjà exportés (schemas/option-<id>.drawio.png pour une
  option cloud, sinon la page de schemas/architectures.drawio).
Écrit presentation.md, au format que l'agent externe concepteur-deck convertit
(front matter, parties, une consigne de visuel par section) : chaque donnée
n'y figure qu'une fois (chiffres clés, exigences indispensables, notes par
critère en graphique, scores, écarts, comparaison, un schéma par option,
décision, couverture par l'option retenue, conséquences et questions
ouvertes). Le détail va dans les notes de l'orateur. La présentation se
délègue ensuite à concepteur-deck avec pptx_publish.py (skill markdown-publish). Les scores et contrôles
sont ceux d'options_build.py (skill architecture-options), appelé par son
contrat (`requires`).

    uv run scripts/deck_build.py DOSSIER [--out presentation.md]
"""

import argparse
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
from skill_paths import absent, find_script, load_module  # noqa: E402
from spec_schema import check, input_schema, validate  # noqa: E402
from text_tools import data_file, from_data  # noqa: E402

# Mêmes scores, contrôles et libellés que la comparaison validée (skill architecture-options).
OPTIONS = load_module("architecture-options", "options_build.py")

PER_LIST = 6  # éléments visibles par liste ; la suite va dans les notes


def short(text: str, limit: int = 90) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[:limit - 1].rsplit(" ", 1)[0] + "…"


def notes(lines: list[str]) -> list[str]:
    body = " ".join(" ".join(str(line).split()) for line in lines if line).replace("-->", "→")
    return [f"<!-- notes: {body} -->"] if body else []


def section(title: str, kind: str | None, body: list[str], speaker: list[str] = (), part: str | None = None) -> list[str]:
    head = [f"## {title}"] + ([f"<!-- part: {part} -->"] if part else []) + ([f"<!-- slide: {kind} -->"] if kind else [])
    return head + [""] + body + [""] + [n + "\n" for n in notes(list(speaker))]


def table(header: list[str], rows: list[list[str]]) -> list[str]:
    return ["| " + " | ".join(header) + " |", "|" + "---|" * len(header)] + \
           ["| " + " | ".join(OPTIONS.cell(v) for v in row) + " |" for row in rows]


def schema_image(folder: Path, option: dict, index: int) -> Path | None:
    """PNG déjà exporté : schéma cloud de l'option, sinon sa page de architectures.drawio."""
    names = [f"option-{option['id'].lower()}.drawio.png",
             "architectures.drawio.png" if index == 0 else f"architectures-{index + 1}.drawio.png"]
    return next((folder / "schemas" / n for n in names if (folder / "schemas" / n).is_file()), None)


def build(folder: Path, spec: dict, criteria: list[dict], ranking: list[dict], catalog: dict,
          out: Path, warnings: list[str]) -> tuple[str, int, int]:
    options = {o["id"]: o for o in spec["options"]}
    decision, rec = spec.get("decision"), spec["recommendation"]
    target = options[(decision or rec)["option"]]
    kept = [r for r in catalog.values() if r.get("status", "retenue") == "retenue"]
    key = [r for r in kept if r["priority"] == "indispensable"]
    questions = [(r["id"], q) for r in kept for q in r.get("questions", [])]
    title = spec.get("title") or "Options d'architecture"
    context = " ".join((spec.get("context") or "").split())
    front = ["---", f"title: {json.dumps(short(title, 60), ensure_ascii=False)}"]
    if context and len(context) <= 140:
        front.append(f"subtitle: {json.dumps(context, ensure_ascii=False)}")
    if decision:
        front.append(f"author: {json.dumps(decision['by'], ensure_ascii=False)}")
        if decision.get("date"):
            front.append(f"date: {json.dumps(decision['date'])}")
    front += [f"purpose: {'technical' if decision else 'proposal'}", "lang: fr", "---", "", f"# {title}", ""]
    lines, sections, images = front, 0, 0

    def add(*args, **kwargs):
        nonlocal sections
        lines.extend(section(*args, **kwargs))
        sections += 1

    # 1. Le besoin
    functional = sum(1 for r in kept if OPTIONS.nature(r) == "fonctionnelle")
    figures = [f"- **{len(kept)}** exigences retenues, dont {functional} fonctionnelles",
               f"- **{len(key)}** indispensables, à couvrir par toute option recevable"]
    if questions:
        figures.append(f"- **{len(questions)}** questions encore ouvertes")
    docs = sorted({s["doc"] for r in kept for s in r.get("sources", [])})
    part = "Le besoin"
    if context and len(context) > 140:
        add("Contexte", "text", [context], part=part)
        part = None
    add("Les exigences en chiffres", "stats", ["Le catalogue validé à l'étape exigences.", ""] + figures,
        [f"Sources : {', '.join(docs)}." if docs else ""], part=part)
    add("Exigences indispensables", "table",
        table(["Exigence", "Intitulé", "Mesure"], [[r["id"], short(r["title"], 40), short(r.get("metric", "–"), 40)]
                                                   for r in key]))
    glossary = catalog_glossary(folder, spec)
    if glossary:
        add("Glossaire", "table", table(["Terme", "Définition"],
                                        [[g["term"], short(g["definition"], 80)] for g in glossary]))

    # 2. Les options
    add("Options étudiées", "cards", [f"- **Option {o['id']}**: {short(o['name'], 80)}" for o in spec["options"]],
        [f"Option {o['id']} : {o['summary']}" for o in spec["options"]], part="Les options")
    rows = [[short(c["name"], 30)] + [str(o["scores"].get(c["id"], 0)) for o in spec["options"]] for c in criteria]
    add("Notes par critère", "chart",
        ["Notes de 1 à 5, pondérées par la priorité des exigences du critère.", ""]
        + table(["Critère"] + [f"Option {o['id']}" for o in spec["options"]], rows),
        [f"{c['name']} (poids {c['weight']}) : " + " ; ".join(
            f"{o['id']} {o['scores'].get(c['id'], '-')}" + (f", {o['score_notes'][c['id']]}"
                                                            if c["id"] in o.get("score_notes", {}) else "")
            for o in spec["options"]) + "." for c in criteria])
    add("Score pondéré", "stats",
        [f"- **{r['score']} %** option {r['option']}, "
         + (f"éliminée : {', '.join(r['blocking'])} non couverte" if r["blocking"] else "recevable")
         for r in ranking],
        ["Somme des notes pondérées, en pourcentage du maximum ; une option qui laisse une exigence "
         "indispensable non couverte est éliminée."])
    gaps = [[gid, f"Option {o['id']}", OPTIONS.LEVELS[g["level"]], short(g["note"], 40)]
            for o in spec["options"] for gid, g in o.get("gaps", {}).items()]
    if gaps:
        add("Écarts aux exigences", "table", ["Les exigences absentes sont couvertes par toutes les options.", ""]
            + table(["Exigence", "Option", "Couverture", "Note"], gaps))
    lines += ["## Comparaison des options", ""]
    sections += 1
    for option in spec["options"]:
        items = [f"Avantage : {p}" for p in option.get("pros", [])] + \
            [f"Limite : {c}" for c in option.get("cons", [])] + [f"Risque : {r}" for r in option.get("risks", [])]
        lines += [f"### Option {option['id']}", ""] + [f"- {short(i, 80)}" for i in items[:7]] + [""]
    for index, option in enumerate(spec["options"]):
        image = schema_image(folder, option, index)
        if image is None:
            warnings.append(f"option {option['id']} : schéma non exporté, diapositive omise (uv run "
                            f"../diagram-export/scripts/export.py schemas/architectures.drawio --format png)")
            continue
        rel = Path(os.path.relpath(image, out.parent)).as_posix()
        comps = [c["label"] + (f" ({c['tech']})" if c.get("tech") else "") for c in option["components"]]
        add(f"Architecture de l'option {option['id']}", "image",
            [f"![Schéma de l'option {option['id']} : {option['name']}]({rel})", ""]
            + [f"- {short(c, 60)}" for c in comps[:PER_LIST]],
            [f"Autres composants : {', '.join(comps[PER_LIST:])}." if comps[PER_LIST:] else ""])
        images += 1

    # 3. La décision
    chosen = decision or rec
    head = "Décision" if decision else "Recommandation"
    quote = [f"> {chosen['why']}", ">", f"> — {decision['by']}" + (f", {decision['date']}" if decision.get("date") else "")] \
        if decision else [f"Option {rec['option']} recommandée : {rec['why']}"]
    speaker = [f"Exigences déterminantes : {', '.join(chosen['refs'])}." if chosen.get("refs") else ""]
    if decision and decision["option"] != rec["option"]:
        speaker.append(f"La recommandation était l'option {rec['option']} : {rec['why']}")
    add(f"{head} : option {target['id']}", None if decision else "text", quote, speaker, part="La décision")
    cover = []
    for r in kept:
        gap = target.get("gaps", {}).get(r["id"])
        comps = [c["label"] for c in target["components"] if r["id"] in c.get("refs", [])]
        # Un écart de l'option retenue est déjà détaillé plus haut : ici, son seul niveau.
        text = short(", ".join(comps), 40) if comps else ("" if gap else "–")
        if gap:
            text = f"{text} ({OPTIONS.LEVELS[gap['level']]})" if text else OPTIONS.LEVELS[gap["level"]]
        cover.append([r["id"], r["priority"], text])
    add(f"Couverture par l'option {target['id']}", "table",
        ["Composants de l'option qui portent chaque exigence retenue.", ""]
        + table(["Exigence", "Priorité", "Composants"], cover))
    follow = [f"{q} ({rid})" for rid, q in questions]
    if follow:
        add("Questions ouvertes", "bullets", [f"- {short(f, 95)}" for f in follow[:PER_LIST]],
            [" ".join(follow[PER_LIST:])])
    return "\n".join(lines).rstrip() + "\n", sections, images


def catalog_glossary(folder: Path, spec: dict) -> list[dict]:
    try:
        return json.loads(from_data(data_file(folder, "options.json").parent, spec.get("requirements", "exigences.json")).read_text(encoding="utf-8")) \
            .get("glossary", [])
    except (OSError, ValueError):
        return []


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="dossier du workflow (options.json, exigences, schemas/)")
    parser.add_argument("--out", type=Path, help="Markdown à écrire (défaut : DOSSIER/presentation.md)")
    args = parser.parse_args()
    report = {"input": str(args.folder), "output": None, "sections": 0, "images": 0, "decided": None,
              "errors": [], "warnings": []}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    source = data_file(args.folder, "options.json")
    try:
        spec = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(f"options.json illisible : {error}")
        return done(1)
    options_script = find_script("architecture-options", "options_build.py")
    if OPTIONS is None or options_script is None:
        report["errors"].append(absent("architecture-options", "options_build.py"))
        return done(1)
    report["errors"] += [f"options.json : {e}" for e in validate(spec, options_script)]
    decision_file = data_file(args.folder, "decision.json")
    if decision_file.is_file() and not report["errors"]:
        try:
            spec["decision"] = json.loads(decision_file.read_text(encoding="utf-8"))
        except ValueError as error:
            report["errors"].append(f"decision.json illisible : {error}")
            return done(1)
        report["errors"] += [f"decision.json : {e}" for e in
                             check(spec["decision"], input_schema(options_script)["properties"]["decision"])]
    if report["errors"]:
        return done(1)
    found = OPTIONS.analyse(spec, source.parent)
    criteria, ranking, catalog, errors, warnings = (found[k] for k in
                                                    ("criteria", "ranking", "catalog", "errors", "warnings"))
    report["errors"] += errors
    report["warnings"] += warnings
    if errors:
        return done(1)
    out = args.out or args.folder / "presentation.md"
    text, report["sections"], report["images"] = build(args.folder.resolve(), spec, criteria, ranking, catalog,
                                                       out.resolve(), report["warnings"])
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    report.update(output=str(out), decided=(spec.get("decision") or {}).get("option"))
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
