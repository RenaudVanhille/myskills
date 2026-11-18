# /// script
# requires-python = ">=3.10"
# ///
"""Construit un design system à partir de ses tokens (couleurs, typographie, espacements, rayons, ombres).

Le modèle décrit les tokens dans un JSON court (souvent le brouillon de
ds_extract.py, corrigé) ; le script, et non le modèle :

- complète les couleurs manquantes (surface, bordure, texte secondaire,
  couleur du texte sur chaque couleur de fond) à partir de celles données ;
- contrôle les contrastes WCAG 2.1 (texte sur fond, bouton, statuts) et
  propose pour chaque paire trop faible une teinte qui passe ;
- signale les couleurs presque identiques, une échelle de tailles
  irrégulière, un espacement hors grille de 4 px ;
- avec --pages, fait l'inventaire des pages décrites pour mockup-to-html :
  composants et variantes employés, couleurs écrites en dur, tokens absents ;
- écrit <nom>.css (variables CSS), <nom>.tokens.json (format W3C Design
  Tokens), <nom>.md (documentation) et <nom>.styleguide.json, une page de
  référence décrite pour mockup-to-html ; avec --render, cette page est
  construite et rendue par page_build.py.

Le module sert aussi à page_build.py (mockup-to-html) : valeurs par défaut,
complément des tokens, variables CSS, contraste.

    uv run scripts/ds_build.py TOKENS.json [--pages PAGE.json ...] [--out-dir DOSSIER] [--render] | --schema
"""

import argparse
import colorsys
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import skill_paths  # noqa: E402
from spec_schema import check, input_schema, print_schema, validate  # noqa: E402
from text_tools import beside  # noqa: E402

DEFAULTS = {
    "colors": {"primary": "#2563eb", "secondary": "#475569", "background": "#ffffff", "text": "#0f172a",
               "success": "#15803d", "warning": "#b45309", "danger": "#b91c1c", "info": "#0369a1"},
    "fonts": {"body": "system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
              "heading": "system-ui, -apple-system, 'Segoe UI', Roboto, Arial, sans-serif",
              "mono": "ui-monospace, Consolas, 'Courier New', monospace"},
    "font_sizes": {"xs": 12, "sm": 14, "md": 16, "lg": 20, "xl": 24, "2xl": 32, "3xl": 40},
    "line_height": 1.5,
    "spacing": {"none": 0, "xs": 4, "sm": 8, "md": 16, "lg": 24, "xl": 32, "2xl": 48, "3xl": 64},
    "radii": {"none": 0, "sm": 4, "md": 8, "lg": 16, "full": 999},
    "shadows": {"sm": "0 1px 2px rgba(15, 23, 42, 0.08)", "md": "0 4px 12px rgba(15, 23, 42, 0.12)"},
    "max_width": 1200,
}
# Couleurs dont un texte se pose dessus : on-<couleur> calculé s'il manque.
FILLS = ("primary", "secondary", "success", "warning", "danger", "info")
STATUS = ("success", "warning", "danger", "info")
SIMILAR = 18  # distance RGB sous laquelle deux couleurs se confondent
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")


# --- Couleurs -----------------------------------------------------------------------------------------------

def rgb(hex_: str) -> tuple[int, int, int]:
    return tuple(int(hex_[i:i + 2], 16) for i in (1, 3, 5))


def to_hex(color) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c))):02x}" for c in color)


def mix(a: str, b: str, part: float) -> str:
    """a mêlé de part de b."""
    return to_hex([x + (y - x) * part for x, y in zip(rgb(a), rgb(b))])


def luminance(hex_: str) -> float:
    def channel(c):
        c /= 255
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (channel(c) for c in rgb(hex_))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    """Rapport de contraste WCAG 2.1, de 1 à 21."""
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return round((la + 0.05) / (lb + 0.05), 2)


def distance(a: str, b: str) -> float:
    return sum((x - y) ** 2 for x, y in zip(rgb(a), rgb(b))) ** 0.5


def readable_on(fill: str) -> str:
    """Blanc ou quasi-noir, celui qui contraste le mieux sur fill."""
    return "#ffffff" if contrast("#ffffff", fill) >= contrast("#111111", fill) else "#111111"


def accessible(fg: str, bg: str, target: float) -> str | None:
    """Teinte de fg, plus sombre ou plus claire selon le fond, qui atteint le contraste voulu."""
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in rgb(fg)))
    step = -0.01 if luminance(bg) > 0.18 else 0.01
    while 0 <= l <= 1:
        candidate = to_hex(c * 255 for c in colorsys.hls_to_rgb(h, l, s))
        if contrast(candidate, bg) >= target:
            return candidate
        l += step
    return None


# --- Tokens -------------------------------------------------------------------------------------------------

def complete(tokens: dict) -> tuple[dict, list[str]]:
    """Tokens complétés par les valeurs par défaut et les couleurs dérivées ; liste des couleurs dérivées."""
    theme = {key: (dict(value) if isinstance(value, dict) else value) for key, value in DEFAULTS.items()}
    for key, value in tokens.items():
        theme[key] = {**theme[key], **value} if isinstance(theme.get(key), dict) and isinstance(value, dict) else value
    colors, derived = theme["colors"], []
    given = tokens.get("colors", {})
    bg, text = colors["background"], colors["text"]
    surface = colors.get("surface", mix(bg, text, 0.04))
    # Texte secondaire : le plus proche du fond qui garde un contraste de 4,5 sur le fond et sur la surface.
    muted = next((mix(text, bg, p / 100) for p in range(50, -1, -2)
                  if min(contrast(mix(text, bg, p / 100), bg), contrast(mix(text, bg, p / 100), surface)) >= 4.5), text)
    for name, value in (("surface", surface), ("border", mix(bg, text, 0.14)), ("muted", muted)):
        if name not in colors:
            colors[name] = value
            derived.append(name)
    for name in FILLS:
        if name in colors and f"on-{name}" not in colors:
            colors[f"on-{name}"] = readable_on(colors[name])
            derived.append(f"on-{name}")
    # Couleurs par défaut gardées, à remplacer par celles de la maquette si elles diffèrent.
    derived += [name for name in DEFAULTS["colors"] if name not in given and name not in ("background", "text")]
    return theme, derived


def css_variables(theme: dict, selector: str = ":root") -> str:
    lines = [f"{selector} {{"]
    lines += [f"  --color-{k}: {v};" for k, v in theme["colors"].items()]
    lines += [f"  --font-{k}: {v};" for k, v in theme["fonts"].items()]
    lines += [f"  --text-{k}: {px(v)};" for k, v in theme["font_sizes"].items()]
    lines.append(f"  --line-height: {theme['line_height']};")
    lines += [f"  --space-{k}: {px(v)};" for k, v in theme["spacing"].items()]
    lines += [f"  --radius-{k}: {px(v)};" for k, v in theme["radii"].items()]
    lines += [f"  --shadow-{k}: {v};" for k, v in theme["shadows"].items()]
    lines.append(f"  --max-width: {px(theme['max_width'])};")
    return "\n".join(lines) + "\n}\n"


def px(value) -> str:
    return "0" if value == 0 else f"{value:g}px"


def dtcg(theme: dict) -> dict:
    """Tokens au format W3C Design Tokens (Style Dictionary, Tokens Studio)."""
    dim = lambda v: {"$type": "dimension", "$value": px(v)}  # noqa: E731
    return {
        "color": {k: {"$type": "color", "$value": v} for k, v in theme["colors"].items()},
        "font": {"family": {k: {"$type": "fontFamily", "$value": [f.strip().strip("'\"") for f in v.split(",")]}
                            for k, v in theme["fonts"].items()},
                 "size": {k: dim(v) for k, v in theme["font_sizes"].items()},
                 "line-height": {"$type": "number", "$value": theme["line_height"]}},
        "space": {k: dim(v) for k, v in theme["spacing"].items()},
        "radius": {k: dim(v) for k, v in theme["radii"].items()},
        "shadow": {k: {"$value": v, "$description": "ombre CSS"} for k, v in theme["shadows"].items()},
        "size": {"max-width": dim(theme["max_width"])},
    }


def contrast_pairs(theme: dict, extra: list) -> list[tuple[str, str, float, str]]:
    """(texte, fond, minimum, usage) des paires à contrôler."""
    colors = theme["colors"]
    pairs = [("text", "background", 4.5, "texte courant"), ("text", "surface", 4.5, "texte sur surface"),
             ("muted", "background", 4.5, "texte secondaire"), ("muted", "surface", 4.5, "texte secondaire sur surface"),
             ("primary", "background", 4.5, "lien")]
    pairs += [(f"on-{n}", n, 4.5, f"texte sur {n}") for n in FILLS if n in colors]
    pairs += [(n, "background", 3.0, f"statut {n} (icône, bordure)") for n in STATUS if n in colors]
    pairs += [(fg, bg, 4.5, "paire déclarée") for fg, bg in extra]
    return [p for p in pairs if p[0] in colors and p[1] in colors]


def audit(tokens: dict, theme: dict, minimum: float, errors: list[str], warnings: list[str]) -> list[dict]:
    colors = theme["colors"]
    checks = []
    for fg, bg, need, usage in contrast_pairs(theme, tokens.get("contrast", {}).get("pairs", [])):
        need = max(need, minimum) if need >= 4.5 else need
        ratio = contrast(colors[fg], colors[bg])
        entry = {"fg": fg, "bg": bg, "ratio": ratio, "min": need, "ok": ratio >= need, "usage": usage}
        if not entry["ok"]:
            fix = accessible(colors[fg], colors[bg], need)
            entry["suggestion"] = fix
            locked = tokens.get("source", {}).get("locked")
            warnings.append(f"contraste {fg} sur {bg} : {ratio}:1, {need}:1 attendu ({usage})"
                            + (f" ; proposition {fg} = {fix}" if fix else "")
                            + (" ; design system fourni : écart à signaler au client, pas à corriger" if locked else ""))
        checks.append(entry)
    for fg, bg in tokens.get("contrast", {}).get("pairs", []):
        for name in (fg, bg):
            if name not in colors:
                errors.append(f"contrast/pairs : couleur inconnue « {name} »{close(name, colors)}")
    names = list(tokens.get("colors", {}))
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if distance(colors[a], colors[b]) < SIMILAR and not (a.startswith("on-") or b.startswith("on-")):
                warnings.append(f"colors : {a} ({colors[a]}) et {b} ({colors[b]}) presque identiques, fusionnez-les")
    sizes = sorted(theme["font_sizes"].values())
    ratios = [b / a for a, b in zip(sizes, sizes[1:]) if a]
    if ratios and max(ratios) / min(ratios) > 1.6:
        warnings.append("font_sizes : échelle irrégulière (rapports de " + ", ".join(f"{r:.2f}" for r in ratios)
                        + ") ; prenez un rapport constant, 1,2 à 1,333")
    if sizes and sizes[0] < 12:
        warnings.append(f"font_sizes : {sizes[0]} px, sous 12 px, trop petit pour être lu")
    off = [k for k, v in theme["spacing"].items() if v % 4]
    if off:
        warnings.append(f"spacing : {', '.join(off)} hors de la grille de 4 px")
    return checks


def close(name: str, known) -> str:
    match = difflib.get_close_matches(name, list(known), n=1)
    return f" ; vouliez-vous « {match[0]} » ?" if match else ""


# --- Inventaire des pages -----------------------------------------------------------------------------------

COLOR_PROPS = ("background", "color")


def walk(nodes: list, path: str):
    for i, node in enumerate(nodes):
        if isinstance(node, dict):
            yield f"{path}/{i}", node
            yield from walk(node.get("children", []), f"{path}/{i}/children")


def inventory(pages: list[Path], theme: dict, errors: list[str], warnings: list[str]) -> dict:
    components: dict[str, dict] = {}
    hard: dict[str, list[str]] = {}
    for page in pages:
        try:
            spec = json.loads(page.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"--pages : {page.name} illisible ({error})")
            continue
        for where, node in walk(spec.get("body", []), "body"):
            entry = components.setdefault(node.get("type", "?"), {"count": 0, "variants": set(), "pages": set()})
            entry["count"] += 1
            entry["pages"].add(page.stem)
            if node.get("variant"):
                entry["variants"].add(node["variant"])
            for prop in COLOR_PROPS:
                value = node.get(prop)
                if isinstance(value, str) and HEX.match(value):
                    hard.setdefault(value.lower(), []).append(f"{page.stem}:{where}")
                elif isinstance(value, str) and value not in theme["colors"]:
                    errors.append(f"{page.name} {where}/{prop} : couleur « {value} » absente des tokens"
                                  f"{close(value, theme['colors'])}")
    for value, places in sorted(hard.items()):
        nearest = min(theme["colors"], key=lambda k: distance(theme["colors"][k], value))
        warnings.append(f"couleur écrite en dur {value} ({len(places)} fois, {places[0]}) : token {nearest} "
                        f"({theme['colors'][nearest]}) ou nouveau token")
    return {"components": {k: {"count": v["count"], "variants": sorted(v["variants"]), "pages": sorted(v["pages"])}
                           for k, v in sorted(components.items())},
            "hardcoded": {k: len(v) for k, v in hard.items()}}


# --- Sorties ------------------------------------------------------------------------------------------------

def markdown(tokens: dict, theme: dict, checks: list[dict], derived: list[str], inv: dict | None, stem: str) -> str:
    c = theme["colors"]
    out = [f"# Design system : {tokens['name']}", ""]
    if tokens.get("description"):
        out += [tokens["description"], ""]
    if tokens.get("principles"):
        out += ["## Principes", ""] + [f"- {p}" for p in tokens["principles"]] + [""]
    out += ["## Couleurs", "", "| Token | Valeur | Variable CSS | Contraste sur background | Origine |",
            "| --- | --- | --- | --- | --- |"]
    out += [f"| `{k}` | `{v}` | `var(--color-{k})` | {contrast(v, c['background'])}:1 | "
            f"{'dérivée ou par défaut' if k in derived else 'donnée'} |" for k, v in c.items()]
    out += ["", "## Contrastes (WCAG 2.1)", "", "| Texte | Fond | Rapport | Minimum | Usage | Résultat |",
            "| --- | --- | --- | --- | --- | --- |"]
    out += [f"| `{x['fg']}` | `{x['bg']}` | {x['ratio']}:1 | {x['min']}:1 | {x['usage']} | "
            + ("conforme" if x["ok"] else f"insuffisant, proposition `{x.get('suggestion') or '-'}`") + " |"
            for x in checks]
    out += ["", "## Typographie", "", "| Rôle | Police |", "| --- | --- |"]
    out += [f"| `{k}` | {v} |" for k, v in theme["fonts"].items()]
    out += ["", f"Interligne : {theme['line_height']}.", "", "| Taille | Valeur | Variable CSS |",
            "| --- | --- | --- |"]
    out += [f"| `{k}` | {px(v)} | `var(--text-{k})` |" for k, v in theme["font_sizes"].items()]
    for title, key, var in (("Espacements", "spacing", "space"), ("Rayons", "radii", "radius"),
                            ("Ombres", "shadows", "shadow")):
        out += ["", f"## {title}", "", "| Token | Valeur | Variable CSS |", "| --- | --- | --- |"]
        out += [f"| `{k}` | `{px(v) if isinstance(v, (int, float)) else v}` | `var(--{var}-{k})` |"
                for k, v in theme[key].items()]
    docs = tokens.get("components", {})
    used = (inv or {}).get("components", {})
    if docs or used:
        out += ["", "## Composants", "", "| Composant | Description | Variantes | Emplois |", "| --- | --- | --- | --- |"]
        for name in sorted(set(docs) | set(used)):
            doc, use = docs.get(name, {}), used.get(name, {})
            variants = sorted(set(doc.get("variants", [])) | set(use.get("variants", [])))
            count = f"{use['count']} ({', '.join(use['pages'])})" if use else "non employé"
            out.append(f"| `{name}` | {doc.get('description', '')} | {', '.join(variants)} | {count} |")
        for name, doc in docs.items():
            rules = [f"- À faire : {d}" for d in doc.get("do", [])] + [f"- À éviter : {d}" for d in doc.get("dont", [])]
            if doc.get("usage") or rules:
                out += ["", f"### {name}", ""] + ([doc["usage"], ""] if doc.get("usage") else []) + rules
    if inv and inv["hardcoded"]:
        out += ["", "## Couleurs écrites en dur dans les pages", ""]
        out += [f"- `{k}` : {n} fois" for k, n in inv["hardcoded"].items()]
    out += ["", "## Emploi", "", f"Les variables sont dans `{stem}.css` (`<link rel=\"stylesheet\" href=\"{stem}.css\">`), "
            f"les tokens au format W3C Design Tokens dans `{stem}.tokens.json` (Style Dictionary, Tokens Studio).", ""]
    return "\n".join(out)


def styleguide(tokens: dict, theme: dict, stem: str, inv: dict | None) -> dict:
    """Page de référence décrite pour page_build.py (mockup-to-html)."""
    colors = theme["colors"]
    swatches = []
    for name, value in colors.items():
        if name.startswith("on-"):
            continue
        ink = f"on-{name}" if f"on-{name}" in colors else max(("text", "background"),
                                                               key=lambda k: contrast(colors[k], value))
        swatches.append({"type": "card", "background": name, "color": ink, "title": name, "text": value})
    sizes = [{"type": "heading", "level": 3, "size": k, "text": f"{k} · {px(v)} · Aa Bb Cc"}
             for k, v in sorted(theme["font_sizes"].items(), key=lambda kv: -kv[1])]
    spaces = [{"type": "row", "columns": [1, 5], "valign": "center", "children": [
        {"type": "text", "text": f"{k} · {px(v)}", "size": "sm"},
        {"type": "box", "width": v, "height": 12, "background": "primary"}]}
        for k, v in theme["spacing"].items() if v]
    used = set((inv or {}).get("components", {}))
    samples = [
        {"type": "buttons", "items": [{"text": v.capitalize(), "variant": v}
                                       for v in ("primary", "secondary", "outline", "ghost", "danger")]},
        {"type": "row", "columns": [1, 1, 1, 1], "children": [{"type": "badge", "text": v, "variant": v}
                                                               for v in ("info", "success", "warning", "danger")]},
        {"type": "alert", "variant": "info", "title": "Information", "text": "Message d'information."},
        {"type": "alert", "variant": "danger", "title": "Erreur", "text": "Message d'erreur."},
        {"type": "tabs", "items": ["Onglet 1", "Onglet 2", "Onglet 3"], "current": 1},
        {"type": "stepper", "items": ["Étape 1", "Étape 2", "Étape 3"], "current": 2},
        {"type": "breadcrumb", "items": ["Accueil", "Rubrique", "Page"]},
        {"type": "row", "columns": [1, 1], "children": [
            {"type": "form", "fields": [{"label": "Champ texte", "type": "text", "placeholder": "Saisie"},
                                        {"label": "Liste", "type": "select", "options": ["Choix 1", "Choix 2"]},
                                        {"label": "Case à cocher", "type": "checkbox"}], "submit": "Valider"},
            {"type": "card", "title": "Carte", "text": "Texte de la carte.", "actions": ["Action"]}]},
        {"type": "table", "variant": "striped", "headers": ["Colonne", "Valeur"], "rows": [["A", "1"], ["B", "2"]]},
    ]
    body = [
        {"type": "header", "text": tokens["name"], "items": ["Couleurs", "Typographie", "Espacements", "Composants"]},
        {"type": "section", "children": [{"type": "heading", "level": 1, "text": f"Design system : {tokens['name']}"},
                                         *([{"type": "text", "text": tokens["description"], "muted": True}]
                                           if tokens.get("description") else [])]},
        {"type": "section", "children": [{"type": "heading", "level": 2, "text": "Couleurs"},
                                         {"type": "grid", "columns": 4, "children": swatches}]},
        {"type": "section", "background": "surface", "children": [{"type": "heading", "level": 2, "text": "Typographie"},
                                                                  {"type": "stack", "children": sizes}]},
        {"type": "section", "children": [{"type": "heading", "level": 2, "text": "Espacements"},
                                         {"type": "stack", "gap": "sm", "children": spaces}]},
        {"type": "section", "background": "surface", "children": [
            {"type": "heading", "level": 2, "text": "Composants"},
            *([{"type": "text", "muted": True, "text": "Employés dans les pages : " + ", ".join(sorted(used))}]
              if used else []),
            {"type": "stack", "gap": "lg", "children": samples}]},
        {"type": "footer", "text": f"Généré par ds_build.py depuis {stem}.json"},
    ]
    return {"title": f"Design system : {tokens['name']}", "tokens": f"{stem}.json", "body": body}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("tokens", nargs="?", type=Path)
    parser.add_argument("--pages", nargs="*", type=Path, default=[])
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.tokens), "outputs": [], "colors": 0, "derived": [], "contrast": [],
              "components": {}, "styleguide": None, "errors": [], "warnings": []}
    if args.tokens is None:
        report["errors"].append("fichier des tokens manquant (TOKENS.json)")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    try:
        tokens = json.loads(args.tokens.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(f"{args.tokens} illisible : {error}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report["errors"] = validate(tokens, __file__)
    if report["errors"]:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    errors, warnings = report["errors"], report["warnings"]
    theme, derived = complete(tokens)
    minimum = tokens.get("contrast", {}).get("min", 4.5)
    checks = audit(tokens, theme, minimum, errors, warnings)
    inv = inventory(args.pages, theme, errors, warnings) if args.pages else None
    report.update(colors=len(theme["colors"]), derived=derived, contrast=[c for c in checks if not c["ok"]],
                  components={k: v["count"] for k, v in (inv or {}).get("components", {}).items()})
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    out_dir = args.out_dir or args.tokens.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.tokens.stem
    files = {f"{stem}.css": css_variables(theme),
             f"{stem}.tokens.json": json.dumps(dtcg(theme), ensure_ascii=False, indent=2) + "\n",
             f"{stem}.md": markdown(tokens, theme, checks, derived, inv, stem)}
    guide = styleguide(tokens, theme, stem, inv)
    if out_dir.resolve() != args.tokens.parent.resolve():
        guide["tokens"] = str(args.tokens.resolve())
    files[f"{stem}.styleguide.json"] = json.dumps(guide, ensure_ascii=False, indent=2) + "\n"
    for name, text in files.items():
        path = beside(out_dir / name)
        path.write_text(text, encoding="utf-8")
        report["outputs"].append(str(path))
    if args.render and skill_paths.find_script("mockup-to-html", "page_build.py") is None:
        warnings.append(f"styleguide non rendu : {skill_paths.absent('mockup-to-html', 'page_build.py')}")
    elif args.render:
        built =skill_paths.run_script("mockup-to-html", "page_build.py", [out_dir / f"{stem}.styleguide.json"])
        report["styleguide"] = {"outputs": built.get("outputs", []), "rendered": built.get("rendered", False)}
        errors += [f"styleguide : {e}" for e in built.get("errors", [])]
        warnings += [f"styleguide : {w}" for w in built.get("warnings", [])]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


def tokens_errors(tokens) -> list[str]:
    """Erreurs d'un fichier de tokens au regard du schéma d'entrée (pour page_build.py)."""
    return [f"tokens : {e}" for e in check(tokens, input_schema(__file__))]


if __name__ == "__main__":
    sys.exit(main())
