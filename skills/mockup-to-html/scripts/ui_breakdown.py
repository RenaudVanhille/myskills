# /// script
# requires-python = ">=3.10"
# ///
"""Découpe les écrans décrits pour page_build.py en composants et en tire les lots du chiffrage frontend.

Le script, et non le modèle, lit les descriptions de pages (les mêmes que
page_build.py) et calcule :

- les composants employés : nombre, écrans, variantes, propriétés, celui de
  la bibliothèque visée (--target) qui le fournit, complexité tirée de
  règles explicites (type, nombre de champs ou de colonnes, variantes) ;
- les motifs répétés : sous-arbres de même structure (textes ignorés)
  présents au moins deux fois, candidats à un composant composé ;
- les écrans : composants, éléments interactifs, complexité ;
- les lots du chiffrage frontend, à trois points, au format des lots de
  solution-estimate : un par composant, un par motif, un par écran, et les
  lots transverses (socle, thème tiré des tokens, accessibilité,
  responsive, bibliothèque de composants) ;
- le réemploi entre écrans (`reuse`, part épargnée et base) : un écran de
  même structure qu'un précédent, ou semblable (mêmes composants), réutilise
  son lot ; un écran fait surtout de motifs réutilise le lot du motif ; un
  motif compte pour un seul composant dans l'écran qui l'emploie ;
- avec --ux, un lot par constat UX retenu (revue de ux_review.py) d'une
  gravité au moins égale à ux.min_severity : ce que la maquette ne montre
  pas (état d'erreur, aide, confirmation) et qu'il faudra construire.

Les jours viennent d'abaques : ceux donnés avant le lancement (section
frontend de ~/.myskills/abaques.json ou MYSKILLS_ABAQUES, de references.abaques
de mission.json, puis de --abaques), puis --rules, sinon des valeurs par
défaut à calibrer, signalées comme telles.

Écrit <nom>.json (découpage), <nom>.md, <nom>.csv et <nom>.lots.json, que
`estimate_build.py --draft --lots` (solution-estimate) reprend.

    uv run scripts/ui_breakdown.py PAGE [...] [--out decoupage] [--target html|bootstrap|react-mui|react-antd|vue-vuetify|angular-material]
        [--abaques ABAQUES.json] [--rules REGLES.json] [--component ID] [--ux REVUE.json ...] | --schema
"""

import argparse
import csv
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE / "targets"))
import react  # noqa: E402
import templates  # noqa: E402
import skill_paths  # noqa: E402
import workspace  # noqa: E402
from spec_schema import check, input_schema, print_schema, validate  # noqa: E402

LEVELS = ["faible", "moyenne", "elevee", "tres-elevee"]
# Mise en page et typographie : un seul lot, le thème et les gabarits les portent.
LAYOUT = {"section", "row", "stack", "grid", "spacer", "box", "divider", "heading", "text", "link"}
INTERACTIVE = {"form", "tabs", "stepper", "search", "table", "nav", "buttons", "button", "link", "header", "sidebar",
               "pagination", "modal"}
DEFAULT_RULES = {
    "profile": "dev-front",
    "days": {"faible": [0.25, 0.5, 0.75], "moyenne": [1, 1.5, 2.5], "elevee": [2, 3, 5], "tres-elevee": [4, 6, 10]},
    "library_factor": 0.4,
    "types": {"heading": "faible", "text": "faible", "link": "faible", "button": "faible", "buttons": "faible",
              "image": "faible", "badge": "faible", "breadcrumb": "faible", "list": "faible", "alert": "faible",
              "stat": "faible", "card": "moyenne", "nav": "moyenne", "search": "moyenne", "header": "moyenne",
              "footer": "moyenne", "tabs": "moyenne", "table": "moyenne", "form": "moyenne", "stepper": "elevee",
              "icon": "faible", "avatar": "faible", "pagination": "faible", "sidebar": "moyenne", "modal": "moyenne",
              "graph": "elevee"},
    "escalate": {"form_fields": 8, "table_columns": 6, "variants": 3},
    "layout": [1, 2, 3],
    "screen": {"base": [0.5, 1, 1.5], "per_component": 0.05},
    "reuse": {"same_structure": 50, "similar": 25, "similarity": 0.8, "pattern": 20, "pattern_share": 0.5},
    # Constats UX retenus : jours de correction par gravité (1 mineur à 4 bloquant).
    "ux": {"min_severity": 2, "days": {"1": [0.1, 0.25, 0.5], "2": [0.25, 0.5, 1], "3": [0.5, 1, 2],
                                       "4": [1, 2, 4]}},
    "transverse": [
        {"name": "Socle frontend : projet, routage, intégration continue", "phase": "realisation", "effort": [2, 3, 5]},
        {"name": "Thème tiré des tokens du design system", "phase": "realisation", "effort": [0.5, 1, 1.5]},
        {"name": "Bibliothèque de composants documentée (Storybook)", "phase": "conception", "effort": [1, 2, 3]},
        {"name": "Accessibilité (RGAA, WCAG) : audit et corrections", "phase": "tests", "per_screen": [0.25, 0.5, 0.75]},
        {"name": "Responsive : contrôle sur mobile et tablette", "phase": "tests", "per_screen": [0.1, 0.25, 0.35]},
    ],
}
# Composant de la bibliothèque visée, pour le découpage (indicatif).
LIBRARY = {
    "react-mui": {"header": "AppBar", "nav": "Link", "breadcrumb": "Breadcrumbs", "button": "Button",
                  "buttons": "Stack + Button", "card": "Card", "form": "TextField, Select...", "table": "Table",
                  "list": "List", "badge": "Chip", "alert": "Alert", "tabs": "Tabs", "stepper": "Stepper",
                  "search": "TextField", "divider": "Divider", "image": "Box img", "heading": "Typography",
                  "text": "Typography", "link": "Link", "section": "Box + Container", "row": "Grid", "grid": "Grid",
                  "stack": "Stack", "sidebar": "Box + List", "avatar": "Avatar", "pagination": "Pagination",
                  "modal": "Dialog", "graph": "SVG (bibliothèque de graphiques à choisir)"},
    "react-antd": {"header": "Menu", "nav": "Menu", "breadcrumb": "Breadcrumb", "button": "Button", "buttons": "Space",
                   "card": "Card", "form": "Form", "table": "Table", "list": "List", "badge": "Tag", "alert": "Alert",
                   "tabs": "Tabs", "stepper": "Steps", "stat": "Statistic", "search": "Input.Search",
                   "divider": "Divider", "image": "Image", "heading": "Typography.Title", "text": "Typography",
                   "link": "Typography.Link", "row": "Row / Col", "grid": "Row / Col", "stack": "Flex",
                   "sidebar": "Layout.Sider + Menu", "avatar": "Avatar", "pagination": "Pagination", "modal": "Modal",
                   "graph": "SVG (bibliothèque de graphiques à choisir)"},
    "bootstrap": {"button": ".btn", "buttons": ".btn", "card": ".card", "table": ".table", "badge": ".badge",
                  "alert": ".alert", "form": ".form-control", "breadcrumb": "(style propre)", "list": ".list-unstyled",
                  "divider": "hr"},
    "vue-vuetify": {"header": "v-toolbar", "nav": "v-btn variant=text", "breadcrumb": "v-breadcrumbs", "button": "v-btn",
                    "buttons": "v-btn", "card": "v-card", "form": "v-form, v-text-field, v-select...",
                    "table": "v-table", "list": "v-list", "badge": "v-chip", "alert": "v-alert", "tabs": "v-tabs",
                    "stepper": "v-stepper", "search": "v-text-field", "divider": "v-divider", "image": "v-img",
                    "row": "v-row / v-col", "grid": "v-row / v-col", "section": "v-container",
                    "sidebar": "v-navigation-drawer", "avatar": "v-avatar", "pagination": "v-pagination",
                    "modal": "v-dialog", "graph": "SVG (bibliothèque de graphiques à choisir)"},
    "angular-material": {"header": "mat-toolbar", "nav": "mat-button", "button": "mat-flat-button / mat-stroked-button",
                         "buttons": "mat-button", "card": "mat-card", "form": "mat-form-field, matInput, mat-select...",
                         "table": "table (mat-table pour les données dynamiques)", "list": "mat-list",
                         "badge": "mat-chip", "tabs": "mat-tab-group", "stepper": "mat-stepper",
                         "search": "mat-form-field", "divider": "mat-divider", "sidebar": "mat-sidenav",
                         "pagination": "mat-paginator", "graph": "SVG (bibliothèque de graphiques à choisir)"},
}


def provided(target: str) -> set[str]:
    for family in (react.TARGETS, templates.TARGETS):
        if target in family:
            return set(family[target]["provides"])
    if target == "bootstrap":
        return set(json.loads((HERE / "targets" / "bootstrap.json").read_text(encoding="utf-8"))["provides"])
    return set()


def walk(nodes, page: str, path: str):
    for i, node in enumerate(nodes):
        yield page, f"{path}/{i}", node
        yield from walk(node.get("children", []), page, f"{path}/{i}/children")


def signature(node: dict) -> str:
    kids = ",".join(signature(c) for c in node.get("children", []))
    tag = node["type"] + (f":{node['variant']}" if node.get("variant") else "")
    return f"{tag}({kids})" if kids else tag


def size(node: dict) -> int:
    return 1 + sum(size(c) for c in node.get("children", []))


def level(rules: dict, kind: str, nodes: list[dict]) -> str:
    base = LEVELS.index(rules["types"].get(kind, "faible"))
    esc = rules["escalate"]
    if kind == "form" and max(len(n.get("fields", [])) for n in nodes) > esc["form_fields"]:
        base += 1
    if kind == "table" and max(len(n.get("headers") or (n.get("rows") or [[]])[0]) for n in nodes) > esc["table_columns"]:
        base += 1
    if len({n.get("variant") for n in nodes if n.get("variant")}) >= esc["variants"]:
        base += 1
    return LEVELS[min(base, len(LEVELS) - 1)]


def scale(points, factor: float) -> list[float]:
    return [round(max(0.25, round(p * factor * 4) / 4), 2) for p in points]


def merge(rules: dict, override: dict) -> dict:
    out = {k: (dict(v) if isinstance(v, dict) else v) for k, v in rules.items()}
    for key, value in override.items():
        if isinstance(out.get(key), dict) and isinstance(value, dict):
            # Un niveau de plus (ux.days) : seules les clés données changent.
            out[key] = {**out[key], **{k: ({**out[key][k], **v} if isinstance(out[key].get(k), dict)
                                           and isinstance(v, dict) else v) for k, v in value.items()}}
        else:
            out[key] = value
    return out


def likeness(a: dict, b: dict) -> float:
    """Ressemblance de deux écrans : part commune de leurs composants (hors mise en page), par type."""
    keys = set(a) | set(b)
    top = sum(max(a.get(k, 0), b.get(k, 0)) for k in keys)
    return sum(min(a.get(k, 0), b.get(k, 0)) for k in keys) / top if top else 0


def net(entry: dict, profile: str) -> list[float]:
    keep = 1 - entry.get("reuse", {}).get("percent", 0) / 100
    return [round(v * keep, 2) for v in entry["effort"][profile]]


UX_SEVERITY = {1: "mineur", 2: "gênant", 3: "majeur", 4: "bloquant"}
UX_COMPLEXITY = {1: "faible", 2: "faible", 3: "moyenne", 4: "elevee"}


def breakdown(pages: list[tuple[str, dict]], target: str, rules: dict, component: str | None,
              findings: list[dict] | None = None) -> dict:
    nodes = [(p, w, n) for page, spec in pages for p, w, n in walk(spec["body"], page, "body")]
    library, names = provided(target), LIBRARY.get(target, {})
    by_type: dict[str, list] = {}
    for page, where, node in nodes:
        by_type.setdefault(node["type"], []).append((page, node))
    components = []
    for kind, found in sorted(by_type.items()):
        group = [n for _, n in found]
        components.append({
            "type": kind, "count": len(group), "screens": sorted({p for p, _ in found}),
            "variants": sorted({n["variant"] for n in group if n.get("variant")}),
            "props": sorted({k for n in group for k in n if k not in ("type", "children", "id")}),
            "layout": kind in LAYOUT, "complexity": None if kind in LAYOUT else level(rules, kind, group),
            "library": names.get(kind) if kind in library or kind in names else None,
            "provided": kind in library})
    counts: dict[str, list] = {}
    for page, where, node in nodes:
        if node.get("children") and size(node) >= 3:
            counts.setdefault(signature(node), []).append((page, where, node))
    patterns = []
    for sig, found in sorted(counts.items(), key=lambda kv: -len(kv[1])):
        if len(found) < 2:
            continue
        node = found[0][2]
        inner = sorted({c["type"] for c in node["children"]})
        patterns.append({"name": f"{node['type']} de {', '.join(inner)}", "signature": sig, "count": len(found),
                         "screens": sorted({p for p, _, _ in found}), "places": [f"{p}:{w}" for p, w, _ in found][:5],
                         "size": size(node), "_found": [(p, w) for p, w, _ in found]})
    screens = []
    for page, spec in pages:
        own = [(w, n) for p, w, n in nodes if p == page]
        fields = sum(len(n.get("fields", [])) for _, n in own)
        interactive = sum(1 for _, n in own if n["type"] in INTERACTIVE) + fields
        content = [(w, n) for w, n in own if n["type"] not in LAYOUT]
        lvl = LEVELS[min(3, (len(content) > 15) + (interactive > 10) + (fields > 12))]
        # Un motif compte pour un composant : ses nœuds de contenu ne s'ajoutent pas un à un.
        roots = sorted({w for pat in patterns for p, w in pat["_found"] if p == page})
        roots = [w for i, w in enumerate(roots) if not any(w.startswith(r + "/") for r in roots[:i])]
        covered = [w for w, _ in content if any(w == r or w.startswith(r + "/") for r in roots)]
        main_pattern = max((pat for pat in patterns if any(p == page for p, _ in pat["_found"])),
                           key=lambda pat: pat["size"], default=None)
        types: dict[str, int] = {}
        for _, n in content:
            types[n["type"]] = types.get(n["type"], 0) + 1
        screens.append({"screen": page, "title": spec["title"], "components": len(content), "interactive": interactive,
                        "fields": fields, "complexity": lvl, "in_patterns": len(covered),
                        "counted": len(content) - len(covered) + len(roots),
                        "_structure": ",".join(signature(n) for n in spec["body"]), "_types": types,
                        "_pattern": main_pattern})
    # Lots au format de solution-estimate (work).
    profile, days, work = rules["profile"], rules["days"], []

    def lot(name, phase, points, complexity, note, reuse=None):
        entry = {"id": f"F{len(work) + 1}", "name": name, "phase": phase, "effort": {profile: points},
                 "complexity": complexity, "note": note}
        if component:
            entry["component"] = component
        if reuse and reuse["percent"]:
            entry["reuse"] = reuse
        work.append(entry)
        return entry["id"]
    layout_types = [c["type"] for c in components if c["layout"]]
    if layout_types:
        lot("Mise en page et typographie : gabarits, grilles, sections, titres et textes", "realisation", rules["layout"], "moyenne",
            f"{', '.join(layout_types)} ; règle layout")
    for c in components:
        if c["layout"]:
            continue
        factor = rules["library_factor"] if c["provided"] else 1
        variants = f" ({', '.join(c['variants'])})" if c["variants"] else ""
        source = f"fourni par {target} ({c['library']}), facteur {factor:g}" if c["provided"] else "écrit sur mesure"
        lot(f"Composant {c['type']}{variants}", "realisation", scale(days[c["complexity"]], factor), c["complexity"],
            f"{c['count']} emploi(s) sur {len(c['screens'])} écran(s) ; {source} ; abaque {c['complexity']}")
    for p in patterns:
        p["lot"] = lot(f"Composant composé : {p['name']}", "realisation", days["faible"], "faible",
                       f"motif répété {p['count']} fois ({', '.join(p['screens'])})")
    reuse, seen = rules["reuse"], []
    for s in screens:
        extra = rules["screen"]["per_component"] * s["counted"]
        same = next((o for o in seen if o["_structure"] == s["_structure"]), None)
        close = max(seen, key=lambda o: likeness(o["_types"], s["_types"]), default=None)
        share = s["in_patterns"] / s["components"] if s["components"] else 0
        if same:
            why = {"from": same["lot"], "percent": reuse["same_structure"],
                   "basis": f"même structure que l'écran {same['title']} : gabarit et logique repris, textes et données propres"}
        elif close and likeness(close["_types"], s["_types"]) >= reuse["similarity"]:
            why = {"from": close["lot"], "percent": reuse["similar"],
                   "basis": f"composants à {likeness(close['_types'], s['_types']):.0%} communs avec l'écran "
                            f"{close['title']}".replace("%", " %")}
        elif s["_pattern"] and share >= reuse["pattern_share"]:
            why = {"from": s["_pattern"]["lot"], "percent": reuse["pattern"],
                   "basis": f"{share:.0%} des composants dans des motifs répétés".replace("%", " %")}
        else:
            why = None
        motifs = f", dont {s['in_patterns']} dans des motifs (comptés {s['counted']})" if s["in_patterns"] else ""
        s["lot"] = lot(f"Écran {s['title']}", "realisation", [round(v + extra, 2) for v in rules["screen"]["base"]],
                       s["complexity"], f"{s['components']} composants{motifs}, {s['fields']} champs ; intégration et "
                       "données de l'écran", why)
        seen.append(s)
    ux_lots = 0
    titles = {s["screen"]: s["title"] for s in screens}
    for f in sorted(findings or [], key=lambda f: -f["severity"]):
        if f["severity"] < rules["ux"]["min_severity"]:
            continue
        page = Path(f["page"]).stem if f.get("page") else None
        where = f" ; écran {titles.get(page, page)}" if page else ""
        lot(f"Correction UX ({f['heuristic']}, {UX_SEVERITY[f['severity']]}) : {f['problem']}"[:200], "realisation",
            rules["ux"]["days"][str(f["severity"])], UX_COMPLEXITY[f["severity"]],
            f"constat UX retenu : {f['fix']}{where} ; abaque ux gravité {f['severity']}")
        ux_lots += 1
    for t in rules["transverse"]:
        points = t.get("effort") or [round(v * len(screens), 2) for v in t["per_screen"]]
        lot(t["name"], t["phase"], points, "moyenne", "lot transverse" + (" par écran" if t.get("per_screen") else ""))
    total = [round(sum(net(w, profile)[i] for w in work), 2) for i in range(3)]
    gross = [round(sum(w["effort"][profile][i] for w in work), 2) for i in range(3)]
    for item in patterns + screens:
        for key in [k for k in item if k.startswith("_")]:
            del item[key]
    return {"target": target, "screens": screens, "components": components, "patterns": patterns,
            "lots": {"domain": "frontend", "profile": profile, "component": component, "work": work},
            "days": total, "gross_days": gross, "ux_lots": ux_lots}


def write(result: dict, base: Path) -> list[Path]:
    md = [f"# Découpage en composants ({result['target']})", "",
          f"{len(result['screens'])} écran(s), {sum(1 for c in result['components'] if not c['layout'])} composant(s), "
          f"{len(result['patterns'])} motif(s) répété(s) ; charge frontend {result['days'][0]:g} à {result['days'][2]:g} "
          f"jours (probable {result['days'][1]:g}) après réemploi, {result['origin']}.", "",
          "## Composants", "", "| Composant | Emplois | Écrans | Variantes | Complexité | Bibliothèque |",
          "| --- | --- | --- | --- | --- | --- |"]
    md += [f"| `{c['type']}` | {c['count']} | {', '.join(c['screens'])} | {', '.join(c['variants'])} | "
           f"{c['complexity'] or 'mise en page'} | {c['library'] or ('sur mesure' if not c['layout'] else '')} |"
           for c in result["components"]]
    if result["patterns"]:
        md += ["", "## Motifs répétés (composants composés candidats)", "", "| Motif | Fois | Écrans | Structure |",
               "| --- | --- | --- | --- |"]
        md += [f"| {p['name']} | {p['count']} | {', '.join(p['screens'])} | `{p['signature'][:80]}` |"
               for p in result["patterns"]]
    md += ["", "## Écrans", "", "| Écran | Composants | Dans des motifs | Interactifs | Champs | Complexité |",
           "| --- | --- | --- | --- | --- | --- |"]
    md += [f"| {s['title']} | {s['components']} | {s['in_patterns']} | {s['interactive']} | {s['fields']} | "
           f"{s['complexity']} |" for s in result["screens"]]
    profile = result["lots"]["profile"]
    md += ["", f"## Lots du chiffrage frontend (jours, profil `{profile}`)", "",
           "| Lot | Phase | Mini | Probable | Maxi | Réemploi | Note |", "| --- | --- | --- | --- | --- | --- | --- |"]
    for w in result["lots"]["work"]:
        low, likely, high = w["effort"][profile]
        reuse = f"{w['reuse']['percent']:g} % de {w['reuse']['from']}" if w.get("reuse") else ""
        md.append(f"| {w['id']} {w['name']} | {w['phase']} | {low:g} | {likely:g} | {high:g} | {reuse} | {w['note']} |")
    md += ["", f"Charges brutes {result['gross_days'][0]:g} / {result['gross_days'][1]:g} / {result['gross_days'][2]:g} "
           "jours avant réemploi.", "",
           "Reprise dans le chiffrage : `estimate_build.py chiffrage.json --draft --lots "
           f"{base.name}.lots.json` (solution-estimate).", ""]
    paths = {base.with_suffix(".json"): json.dumps(result, ensure_ascii=False, indent=1) + "\n",
             base.with_suffix(".md"): "\n".join(md),
             base.parent / f"{base.name}.lots.json": json.dumps(result["lots"], ensure_ascii=False, indent=1) + "\n"}
    for path, text in paths.items():
        path.write_text(text, encoding="utf-8")
    csv_path = base.with_suffix(".csv")
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        out = csv.writer(handle, delimiter=";")
        out.writerow(["id", "lot", "phase", "complexite", "mini", "probable", "maxi", "note"])
        for w in result["lots"]["work"]:
            out.writerow([w["id"], w["name"], w["phase"], w["complexity"], *w["effort"][profile], w["note"]])
    return [*paths, csv_path]


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("pages", nargs="*", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--target", choices=["html", "bootstrap", *react.TARGETS, *templates.TARGETS], default="html")
    parser.add_argument("--abaques", type=Path)
    parser.add_argument("--rules", type=Path)
    parser.add_argument("--component")
    parser.add_argument("--ux", nargs="+", type=Path, default=[])
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"inputs": [str(p) for p in args.pages], "target": args.target, "outputs": [], "screens": 0,
              "components": 0, "patterns": 0, "lots": 0, "reused": 0, "ux_lots": 0, "days": [], "abaques": [],
              "calibrated": False,
              "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.pages:
        errors.append("aucune description de page (PAGE.json de page_build.py)")
        return done(1)
    abaques, sources, invalid = workspace.abaques(args.pages, args.abaques)
    errors += invalid
    own = abaques.get("frontend", {})
    errors += [f"abaques frontend : {e}" for e in check(own, input_schema(__file__))]
    rules = merge(DEFAULT_RULES, own)
    if args.rules:
        try:
            override = json.loads(args.rules.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"--rules : {args.rules} illisible ({error})")
            return done(1)
        errors += validate(override, __file__)
        rules = merge(rules, override)
        sources.append(str(args.rules))
    page_schema = input_schema(HERE / "page_build.py")
    pages = []
    for path in args.pages:
        try:
            spec = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"{path.name} illisible ({error})")
            continue
        errors += [f"{path.name} : {e}" for e in check(spec, page_schema)][:10]
        pages.append((path.stem, spec))
    # Constats UX retenus par le modèle dans la revue de ux_review.py (même schéma).
    review_schema, findings = input_schema(HERE / "ux_review.py"), []
    for path in args.ux:
        try:
            review = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"--ux : {path.name} illisible ({error})")
            continue
        found = [f"--ux {path.name} : {e}" for e in check(review, review_schema)]
        errors += found[:10]
        if not found:
            findings += review["findings"]
    if args.ux and not errors and not findings:
        warnings.append("--ux : aucun constat dans la revue ; seuls les contrôles mécaniques ont été faits ?")
    if errors:
        return done(1)
    result = breakdown(pages, args.target, rules, args.component, findings)
    calibrated = bool(own) or bool(args.rules)
    result["lots"]["abaques"] = sources
    result["origin"] = ("abaques fournis (" + ", ".join(Path(s).name for s in sources) + ")") if calibrated \
        else "abaques par défaut, à calibrer"
    result["lots"]["source"] = [str(p) for p in args.pages]
    # Lots conformes au schéma des lots de solution-estimate, s'il est installé.
    estimate = skill_paths.schema_of("solution-estimate", "estimate_build.py")
    if estimate is None:
        warnings.append(f"lots non contrôlés : {skill_paths.absent('solution-estimate', 'estimate_build.py')}")
    else:
        item = {**estimate["properties"]["work"]["items"], "$defs": estimate.get("$defs", {})}
        for w in result["lots"]["work"]:
            errors += [f"lots/{w['id']} : {e}" for e in check(w, item)]
    if errors:
        return done(1)
    base = args.out or args.pages[0].parent / "decoupage"
    base.parent.mkdir(parents=True, exist_ok=True)
    report["outputs"] = [str(p) for p in write(result, base)]
    report.update(screens=len(result["screens"]), components=sum(1 for c in result["components"] if not c["layout"]),
                  patterns=len(result["patterns"]), lots=len(result["lots"]["work"]),
                  reused=sum(1 for w in result["lots"]["work"] if w.get("reuse")), ux_lots=result["ux_lots"],
                  days=result["days"],
                  abaques=sources, calibrated=calibrated)
    if not calibrated:
        warnings.append("abaques frontend par défaut, à calibrer : donnez les vôtres avant le lancement "
                        "(section frontend de ~/.myskills/abaques.json, references.abaques de la mission ou --abaques)")
    if args.target == "html":
        warnings.append("sans --target, chaque composant est compté sur mesure ; une bibliothèque réduit la charge des "
                        "composants qu'elle fournit")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
