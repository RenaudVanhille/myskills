# /// script
# requires-python = ">=3.10"
# ///
"""Écrit la synthèse d'une page d'une restitution pour un client, un PO ou un BA, depuis une description courte.

Le modèle écrit `synthese.json` : le besoin, la solution retenue dans les mots
du métier, les bénéfices (chacun relié aux exigences qu'il sert), le coût et
le délai avec leur source, trois risques au plus, les décisions attendues du
client et la suite. Le script met en page `synthese.md` dans un ordre fixe :
en bref, décisions attendues, besoin, solution, ce que cela change, coût et
délai, risques, prochaines étapes.

Les identifiants d'exigences des bénéfices sont vérifiés dans le catalogue
(`--requirements`, défaut ../exigences.json puis exigences.json) et liés à sa
version Markdown. Avec `--journeys` (`<nom>.parcours.json` de
solution-estimate), le coût vient du chiffrage validé, total puis un tableau
par parcours trié du plus cher au moins cher, sans rien recalculer ; sinon,
`cost` est requis avec sa source. La page est relue : une synthèse de plus de
`--max-words` mots est signalée.

Un argument à motif (`../*.parcours.json`) sans fichier est ignoré.

    uv run scripts/readout.py synthese.json [--out synthese.md] [--requirements exigences.json]
                              [--journeys chiffrage.parcours.json] [--scenario ID] [--max-words 450] | --schema
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, read_spec, schema_option  # noqa: E402
from text_tools import cell, near  # noqa: E402

AUDIENCES = {"metier": "les métiers", "direction": "la direction", "comite": "le comité", "mixte": "un public mixte",
             "technique": "un public technique"}


def pick(value: str | None) -> Path | None:
    """Fichier d'une option : un motif prend le premier fichier trouvé, un motif sans fichier donne None."""
    if not value:
        return None
    if not any(c in value for c in "*?["):
        return Path(value)
    base = Path(value)
    anchor = Path(base.anchor) if base.is_absolute() else Path(".")
    found = sorted(anchor.glob(str(base.relative_to(anchor)) if base.is_absolute() else value))
    return found[0] if found else None


def money(value: float, currency: str) -> str:
    return f"{value:,.0f}".replace(",", " ") + f" {currency}"


def days(value: float) -> str:
    return f"{value:,.1f}".replace(",", " ").replace(".", ",").removesuffix(",0") + " j"


def load_json(path: Path, skill: str, script: str, errors: list[str], warnings: list[str]) -> dict | None:
    """JSON d'un autre skill, validé contre le schéma de son script s'il est installé."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{path} illisible : {error}")
        return None
    schema = schema_of(skill, script)
    if schema is None:
        warnings.append(f"{path.name} non vérifié : " + absent(skill, script))
    invalid = check(data, schema) if schema else []
    errors.extend(f"{path.name} : {e}" for e in invalid[:5])
    return None if invalid else data


def cost_section(spec: dict, journeys: dict | None, scenario: str | None, source: str | None) -> list[str]:
    """Coût et délai : le chiffrage par parcours s'il est donné (le plus cher d'abord), sinon cost du JSON."""
    md = ["## Coût et délai", ""]
    if journeys:
        ids = [s["id"] for s in journeys["scenarios"]]
        index = ids.index(scenario) if scenario in ids else 0
        scen, cur = journeys["scenarios"][index], journeys["currency"]
        value = (lambda x: money(x["cost"], cur)) if cur else (lambda x: days(x["days"]))
        md += [f"Réalisation : **{value(scen)}**" + (f" ({days(scen['days'])} de travail)" if cur else "")
               + f", hypothèse {scen['name'][0].lower() + scen['name'][1:]} (source : {source}).", "",
               "Coût par parcours, du plus cher au moins cher :", "", "| Parcours | Pour qui | Coût | Part |",
               "| --- | --- | --- | --- |"]
        rows = sorted(journeys["journeys"], key=lambda j: -j["scenarios"][index]["share"])
        md += [f"| {cell(j['title'])} | {cell(j.get('persona', ''))} | {value(j['scenarios'][index])} | "
               f"{j['scenarios'][index]['share'] * 100:.0f} % |" for j in rows]
        md.append("")
    if spec.get("cost"):
        md += [f"{'Autres coûts' if journeys else 'Coût'} : {spec['cost']['text']} (source : {spec['cost']['source']}).", ""]
    if spec.get("delay"):
        md += [f"Délai : {spec['delay']['text']} (source : {spec['delay']['source']}).", ""]
    return md


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="synthese.json")
    parser.add_argument("--out", type=Path, help="synthèse produite (défaut : synthese.md à côté de l'entrée)")
    parser.add_argument("--requirements", help="catalogue d'exigences (défaut : ../exigences.json, puis exigences.json)")
    parser.add_argument("--journeys", help="<nom>.parcours.json de solution-estimate : coût par parcours ; motif sans fichier ignoré")
    parser.add_argument("--scenario", help="hypothèse de production montrée (défaut : la première, sans IA)")
    parser.add_argument("--max-words", type=int, default=450, help="mots au plus pour tenir sur une page (défaut 450)")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("synthese.json attendu")
    out = args.out or args.spec.parent / "synthese.md"
    report = {"input": str(args.spec), "output": None, "words": 0, "benefits": 0, "risks": 0, "decisions": 0,
              "journeys": 0, "requirements": [], "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]
    spec, invalid = read_spec(args.spec, __file__)
    errors += invalid
    folder = args.spec.parent
    req_path = pick(args.requirements) if args.requirements else next(
        (p for p in (folder / ".." / "exigences.json", folder / "exigences.json") if p.is_file()), None)
    catalog = load_json(req_path, "requirements-catalog", "req_build.py", errors, warnings) if req_path else None
    journeys_path = pick(args.journeys)
    journeys = load_json(journeys_path, "solution-estimate", "journeys_view.py", errors, warnings) \
        if journeys_path else None
    if spec and not invalid:
        known = {r["id"] for r in catalog["requirements"]} if catalog else set()
        refs = [r for b in spec["benefits"] for r in b["refs"]]
        if catalog:
            errors += [f"benefits : exigence inconnue {r}{near(r, known)}" for r in dict.fromkeys(refs) if r not in known]
        elif refs:
            warnings.append("exigences des bénéfices non vérifiées : aucun catalogue (--requirements)")
        if not journeys and not spec.get("cost"):
            errors.append("cost : requis sans chiffrage par parcours (--journeys) ; donnez le coût et sa source")
        if journeys and args.scenario and args.scenario not in [s["id"] for s in journeys["scenarios"]]:
            errors.append(f"--scenario : « {args.scenario} » inconnu (permis : "
                          f"{', '.join(s['id'] for s in journeys['scenarios'])})")
        report["requirements"] = sorted(set(refs))
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    page = req_path.with_suffix(".md") if req_path else None

    def link(ref: str) -> str:
        """Exigence liée à la version Markdown du catalogue, si elle existe."""
        if not page or not page.is_file():
            return ref
        try:
            rel = Path(os.path.relpath(page.resolve(), out.resolve().parent)).as_posix()
        except ValueError:
            rel = page.resolve().as_posix()
        return f"[{ref}]({rel})"

    audience = AUDIENCES[spec.get("audience", "metier")]
    md = [f"# {spec['title']}", "", f"> **En bref.** {spec['summary']}", "",
          f"Synthèse d'une page pour {audience}. Le détail technique est en annexe ; les termes techniques sont "
          "définis dans le glossaire.", "", "## Décisions attendues de votre part", ""]
    for d in spec["decisions"]:
        line = f"- **{d['question']}**"
        if d.get("options"):
            line += " Choix : " + " ; ".join(d["options"]) + "."
        if d.get("due"):
            line += f" Pour le {d['due']}."
        md.append(line)
    md += ["", "## Le besoin", "", spec["need"], "", "## La solution proposée", "", spec["solution"], "",
           "## Ce que cela change pour vous", ""]
    md += [f"- {b['text'].rstrip(' .')} ({', '.join(link(r) for r in b['refs'])})." for b in spec["benefits"]]
    md += [""] + cost_section(spec, journeys, args.scenario, journeys_path.name if journeys_path else None)
    md += ["## Les risques majeurs", ""]
    md += [f"- **{r['text']}**" + (f" Parade : {r['mitigation']}" if r.get("mitigation") else "") for r in spec["risks"]]
    if spec.get("next_steps"):
        md += ["", "## Prochaines étapes", ""] + [f"{n}. {s}" for n, s in enumerate(spec["next_steps"], 1)]
    text = "\n".join(md).rstrip() + "\n"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8", newline="\n")
    # Relecture : sections attendues présentes, une page au plus.
    written = out.read_text(encoding="utf-8")
    for heading in ("## Décisions attendues de votre part", "## Ce que cela change pour vous", "## Coût et délai",
                    "## Les risques majeurs"):
        if heading not in written:
            errors.append(f"{out.name} : section absente « {heading[3:]} »")
    words = len(re.findall(r"\w+", re.sub(r"\]\([^)]*\)|\|", " ", written)))
    if words > args.max_words:
        warnings.append(f"{out.name} : {words} mots pour {args.max_words} au plus (une page) : raccourcir le besoin, "
                        "la solution ou les bénéfices")
    report.update(output=str(out), words=words, benefits=len(spec["benefits"]), risks=len(spec["risks"]),
                  decisions=len(spec["decisions"]), journeys=len(journeys["journeys"]) if journeys else 0)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
