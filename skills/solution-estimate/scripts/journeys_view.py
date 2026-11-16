# /// script
# requires-python = ">=3.10"
# ///
"""Vue par parcours utilisateur pour une restitution : workflow, coût et points d'attention de chaque parcours.

Entrée : `<nom>.parcours.json`, écrit par estimate_build.py quand le chiffrage
déclare ses parcours (`journeys`) ; validé contre son schéma, puis la somme des
parcours est recontrôlée pour chaque hypothèse. Sortie : `parcours.md`, un
tableau de synthèse (coût, part, nombre de points d'attention), le découpage
en lots (lots propres et parcours servis, lots partagés) puis, par
parcours, son schéma de workflow (Mermaid : persona puis étapes, à défaut les
composants touchés), son coût dans l'hypothèse choisie avec ses principaux
postes, et ses points d'attention (risques, hypothèses, dépendances, contrôles
du chiffrage). Rien n'est recalculé : les montants sont ceux du chiffrage.

Avec `--export png`, chaque workflow est aussi écrit en `.mmd` et rendu en
image en local (skill diagram-export) ; `parcours.md` cite alors les images.

    uv run scripts/journeys_view.py chiffrage.parcours.json [--out parcours.md] [--scenario sans-ia|avec-ia|ia-natif]
                                    [--export png|svg] | --schema
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import export_image  # noqa: E402
from spec_schema import print_schema, read_spec, schema_option  # noqa: E402
from estimate_common import days, money, pct  # noqa: E402
from estimate_journeys import POSTS, attention, sums  # noqa: E402
from text_tools import cell  # noqa: E402


def label(text: str) -> str:
    """Libellé Mermaid entre guillemets, guillemets internes neutralisés."""
    return '"' + str(text).replace('"', "#quot;") + '"'


def flowchart(j: dict) -> str:
    """Workflow du parcours : persona, puis ses étapes (à défaut, les composants touchés), de gauche à droite."""
    steps = j["path"] or j["components"] or [j["title"]]
    lines = ["flowchart LR", f"  P([{label(j.get('persona', 'Utilisateur'))}])"]
    lines += [f"  S{n}[{label(f'{n}. {s}' if j['path'] else s)}]" for n, s in enumerate(steps, 1)]
    lines.append("  P --> " + " --> ".join(f"S{n}" for n in range(1, len(steps) + 1)))
    return "\n".join(lines) + "\n"


def lots_section(journeys: list[dict]) -> list[str]:
    """Découpage en lots vu du PO : chaque lot propre et les parcours qu'il sert, puis les lots partagés."""
    own: dict[str, dict] = {}
    shared: dict[str, str] = {}
    for j in journeys:
        for lot in j["lots"]:
            if lot["how"] == "partage":
                shared[lot["id"]] = lot["name"]
                continue
            entry = own.setdefault(lot["id"], {"name": lot["name"], "post": lot["post"], "serves": []})
            entry["serves"].append(f"{j['id']} {j['title']}" + ("" if lot["share"] >= 1 else f" ({pct(lot['share'])})"))
    md = ["## Découpage en lots", "", "Lots propres aux parcours et ceux qu'ils servent : reporter un parcours retire "
          "du périmètre les lots qui ne servent que lui.", "", "| Lot | Poste | Parcours servis |",
          "| --- | --- | --- |"]
    md += [f"| {k} {cell(v['name'])} | {POSTS[v['post']].split(' (')[0]} | {cell(', '.join(v['serves']))} |"
           for k, v in own.items()]
    shared = {k: v for k, v in shared.items() if k not in own}
    if shared:
        md += ["", "Lots partagés par tous les parcours, au prorata :", ""] + [f"- {k} {v}" for k, v in shared.items()]
    return md + [""]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("view", type=Path, nargs="?", help="<nom>.parcours.json d'estimate_build.py")
    parser.add_argument("--out", type=Path, help="Markdown produit (défaut : parcours.md à côté de l'entrée)")
    parser.add_argument("--scenario", help="hypothèse de production montrée (défaut : la première, sans IA)")
    parser.add_argument("--export", choices=["png", "svg"], help="rend aussi chaque workflow en image (diagram-export)")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.view:
        parser.error("<nom>.parcours.json attendu")
    out = args.out or args.view.parent / "parcours.md"
    report = {"input": str(args.view), "outputs": [], "journeys": 0, "scenario": None, "total": None,
              "images": [], "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]
    view, invalid = read_spec(args.view, __file__)
    errors += invalid or sums(view, args.view.name)
    if not errors:
        ids = [s["id"] for s in view["scenarios"]]
        index = ids.index(args.scenario) if args.scenario in ids else 0
        if args.scenario and args.scenario not in ids:
            errors.append(f"--scenario : « {args.scenario} » inconnu (permis : {', '.join(ids)})")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    scen, cur = view["scenarios"][index], view["currency"]
    value = (lambda x: money(x["cost"], cur)) if cur else (lambda x: f"{days(x['days'])} j")
    md = [f"# Parcours utilisateurs : {view['title']}", "",
          f"Coût de réalisation par parcours, hypothèse {scen['name'][0].lower() + scen['name'][1:]}, option "
          f"{view['option']}. La somme des parcours redonne la réalisation : {value(scen)}. Les postes partagés "
          f"(cadrage, recette, pilotage, provision...) sont répartis au prorata du coût propre de chaque parcours. "
          f"Ils pèsent {pct(view['spread'])} du total sans IA. Détail des postes et de leurs références : le chiffrage.", "",
          "| Parcours | Persona | Coût | Part | Points d'attention |", "| --- | --- | --- | --- | --- |"]
    for j in view["journeys"]:
        x = j["scenarios"][index]
        md.append(f"| {j['id']} {cell(j['title'])} | {cell(j.get('persona', ''))} | {value(x)} | {pct(x['share'])} | "
                  f"{len(attention(j))} |")
    md += [f"| **Total** |  | **{value(scen)}** | 100 % |  |", ""]
    md += lots_section(view["journeys"])
    for j in view["journeys"]:
        x = j["scenarios"][index]
        md += [f"## {j['id']}. {j['title']}", "", "### Workflow", ""]
        chart = flowchart(j)
        if args.export:
            source = out.parent / "parcours" / f"{re.sub(r'[^A-Za-z0-9_.-]', '-', j['id'])}.mmd"
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(chart, encoding="utf-8", newline="\n")
            done, failed = export_image(source, args.export)
            errors += failed
            warnings += done["warnings"]
            image = source.with_suffix(f".{args.export}")
            report["images"].append(str(image))
            md += [f"![Workflow du parcours {j['id']}]({image.relative_to(out.parent).as_posix()})", ""]
        else:
            md += ["```mermaid", chart.rstrip(), "```", ""]
        main_posts = sorted(((v["cost"] if cur else v["days"], k) for k, v in x["posts"].items()
                             if k not in ("provision",)), reverse=True)
        base = x["cost"] if cur else x["days"]
        top = ", ".join(f"{POSTS[k].split(' (')[0]} {pct(v / base)}" for v, k in main_posts[:3] if v) if base else ""
        md += ["### Coût", "", f"{value(x)}, soit {pct(x['share'])} de la réalisation"
               + (f" ({days(x['days'])} j)" if cur else "") + (f" ; principaux postes : {top}." if top else "."), ""]
        points = attention(j)
        md += ["### Points d'attention", ""] + ([f"- {p}" for p in points] or ["Aucun point relevé."]) + [""]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(md), encoding="utf-8", newline="\n")
    # Relecture : une section par parcours, chaque image citée présente.
    text = out.read_text(encoding="utf-8")
    found = len(re.findall(r"^## ", text, re.M)) - 1
    if found != len(view["journeys"]):
        errors.append(f"{out.name} : {found} sections de parcours au lieu de {len(view['journeys'])}")
    errors += [f"{out.name} : image absente {p}" for p in report["images"] if not Path(p).exists()]
    report.update(outputs=[str(out)], journeys=len(view["journeys"]), scenario=scen["id"],
                  total=scen["cost"] if cur else scen["days"])
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
