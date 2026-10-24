# /// script
# requires-python = ">=3.10"
# ///
"""Choisit le format et le skill d'un schéma à partir d'une décision courte.

Le modèle écrit la décision en JSON (public, destination, type de schéma,
message principal, 3 à 7 éléments) ; le script la valide, applique la grille
de choix (public avant destination, format modifiable là où le schéma vit)
et rend la décision complète : format, skill, vue cloud, livraison selon la
destination et raison du choix. Avec --out, la décision est écrite en JSON
pour la passer au skill de dessin ou à un autre agent.

    uv run scripts/brief.py BRIEF.json [--out DECISION.json] | --json '{...}' | --schema
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402

# Type de schéma cloud -> vue de cloud_build.py.
CLOUD_VIEWS = {"cloud": "deployment", "cloud-reseau": "network", "kubernetes": "kubernetes", "pra": "dr",
               "pipeline": "pipeline", "menaces": "threats"}
MERMAID_KINDS = {"sequence", "etats", "classes", "donnees", "gantt"}
FORMATS = {"likec4": "LikeC4 (C4)", "mermaid": "Mermaid", "drawio": "draw.io", "excalidraw": "Excalidraw"}


def decide(brief: dict) -> tuple[str, str, str]:
    """(format, skill, raison) selon la grille de diagram-brief."""
    kind, audience, dest = brief["kind"], brief["audience"], brief["destination"]
    in_repo = dest in ("markdown", "obsidian")
    if kind in ("urbanisation", "capacites"):
        return "drawio", "urbanization-map", "cartographie du SI : draw.io généré par script, technique ou non"
    if kind in CLOUD_VIEWS:
        return "drawio", "cloud-architecture", "architecture cloud : draw.io aux icônes officielles, généré par script"
    if kind == "architecture":
        return "likec4", "c4-architecture", "architecture à plusieurs vues ou niveaux : modèle C4 à maintenir"
    if kind == "vue-c4":
        if in_repo:
            return "mermaid", "c4-architecture", "une vue C4 dans un Markdown : Mermaid généré depuis LikeC4"
        return "likec4", "c4-architecture", "vue C4 pour un document : export de la vue LikeC4"
    if kind in MERMAID_KINDS:
        return "mermaid", "mermaid-diagram", "séquence, états, classes, données ou planning : Mermaid"
    if audience == "non technique":
        return "excalidraw", "excalidraw-diagram", "public non technique : le public passe avant la destination"
    if in_repo and not brief.get("editable"):
        return "mermaid", "mermaid-diagram", "schéma technique dans un dépôt ou Obsidian : Mermaid reste modifiable"
    return "drawio", "drawio-diagram", "public technique, document ou wiki, mise en page précise : draw.io"


def delivery(fmt: str, dest: str) -> str:
    """Ce qu'on livre selon la destination (section 3 du SKILL.md)."""
    if dest == "markdown":
        return "bloc ```mermaid dans le fichier" if fmt == "mermaid" else "export SVG à côté, lien relatif"
    if dest == "obsidian":
        return {"mermaid": "bloc ```mermaid", "excalidraw": "export .excalidraw.svg intégré avec ![[...]]"}.get(
            fmt, "export PNG intégré avec ![[...]], source à côté")
    if dest == "confluence" and fmt == "drawio":
        return "le .drawio (macro draw.io) et le .drawio.png (à insérer dans la page)"
    if dest == "confluence":
        return "le PNG à insérer dans la page, la source jointe à la page"
    return "PNG à l'échelle 2 (diagram-export), la source à côté"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("brief", type=Path, nargs="?", help="décision courte en JSON")
    parser.add_argument("--json", help="décision courte en JSON sur une ligne, au lieu d'un fichier")
    parser.add_argument("--out", type=Path, help="écrit la décision complète dans ce fichier JSON")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la décision courte sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.brief and not args.json:
        parser.error("décision JSON attendue (fichier ou --json)")
    report = {"input": str(args.brief or "--json"), "decision": None, "output": None, "errors": [], "warnings": []}
    try:
        brief = json.loads(args.json if args.json else args.brief.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report["errors"] += validate(brief, __file__)
    if not report["errors"]:
        fmt, skill, why = decide(brief)
        count = len(brief["elements"])
        if not 3 <= count <= 7:
            report["warnings"].append(f"elements : {count} éléments, 3 à 7 attendus ; regroupez ou découpez en "
                                      "plusieurs schémas")
        decision = {**{k: v for k, v in brief.items() if not k.startswith("_")}, "format": FORMATS[fmt],
                    "skill": skill, "delivery": delivery(fmt, brief["destination"]), "reason": why}
        if skill == "cloud-architecture":
            decision["view"] = CLOUD_VIEWS[brief["kind"]]
            if brief["kind"] == "menaces":
                report["warnings"].append("menaces : le modèle STRIDE se prépare avec le skill threat-model, "
                                          "le schéma avec cloud_build.py --view threats")
        if brief["kind"] == "capacites":
            decision["vocabulary"] = "togaf"
        report["decision"] = decision
        if args.out:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["output"] = str(args.out)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
