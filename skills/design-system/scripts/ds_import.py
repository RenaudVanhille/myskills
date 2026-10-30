# /// script
# requires-python = ">=3.10"
# ///
"""Reprend un design system existant et l'écrit au format des tokens de myskills.

Formats reconnus, sans rien télécharger :

- tokens W3C Design Tokens (`$value`, `$type`), Style Dictionary et Tokens
  Studio (`value`, `type`), alias `{color.blue.500}` résolus ;
- feuille de style à variables CSS (`--color-primary: #0b3d91;` dans
  `:root`), `var(--x)` résolus ;
- thème MUI (`palette`, `typography`, `shape`, `spacing`) et thème Ant
  Design (`token` : colorPrimary, fontFamily, borderRadius...), en JSON ou
  dans un fichier .ts/.js (objet littéral de createTheme ou ThemeConfig) ;
- tokens de myskills (contrôlés tels quels).

Le script, et non le modèle, lit chaque token, normalise sa valeur
(#rgb, rgb(), rem, px), le range par nature (couleur, police, taille,
espacement, rayon, ombre) et donne aux couleurs les rôles attendus
(primary, background, text, surface, border, muted, success, warning,
danger, info) d'après leur nom. Les couleurs sans rôle sont gardées sous
leur nom. Le fichier écrit porte `source` (`locked` : le design system
fourni prime sur les maquettes, qui ne le modifient pas).

    uv run scripts/ds_import.py FICHIER [...] --out design-system.json [--name NOM]
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds_build  # noqa: E402

# Rôle -> noms qui le désignent (après normalisation : minuscules, séparateurs en tirets), le plus précis d'abord.
ROLES = {
    "on-primary": ["on-primary", "primary-contrast-text", "primary-contrasttext", "primary-foreground", "color-white-on-primary"],
    "on-secondary": ["on-secondary", "secondary-contrast-text", "secondary-contrasttext", "secondary-foreground"],
    "primary": ["primary", "primary-main", "brand", "brand-primary", "color-primary", "palette-primary-main", "accent"],
    "secondary": ["secondary", "secondary-main", "brand-secondary", "color-secondary", "palette-secondary-main"],
    "background": ["background", "background-default", "bg", "bg-base", "color-bg-base", "body-bg", "page",
                   "color-bg-layout", "canvas"],
    "surface": ["surface", "background-paper", "paper", "bg-subtle", "color-bg-container", "card", "bg-surface"],
    "text": ["text", "text-primary", "foreground", "fg", "color-text-base", "color-text", "body-color", "body-text",
             "on-background", "on-surface"],
    "muted": ["muted", "text-secondary", "color-text-secondary", "text-muted", "secondary-text", "subtle"],
    "border": ["border", "divider", "color-border", "outline", "border-color", "stroke"],
    "success": ["success", "success-main", "color-success", "positive"],
    "warning": ["warning", "warning-main", "color-warning", "caution"],
    "danger": ["danger", "error", "error-main", "color-error", "negative", "critical"],
    "info": ["info", "info-main", "color-info", "information"],
}
FONT_ROLES = {"heading": ["heading", "headings", "title", "display", "font-family-heading"],
              "mono": ["mono", "monospace", "code", "font-family-code"],
              "body": ["body", "base", "sans", "font-family", "text", "default"]}
HEX3 = re.compile(r"^#([0-9a-fA-F]{3})$")
HEX6 = re.compile(r"^#([0-9a-fA-F]{6})([0-9a-fA-F]{2})?$")
RGB = re.compile(r"^rgba?\(\s*(\d+)[\s,]+(\d+)[\s,]+(\d+)")
DIM = re.compile(r"^(-?\d*\.?\d+)\s*(px|rem|em)?$")


def norm(name: str) -> str:
    name = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", name)
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


def color(value) -> str | None:
    if not isinstance(value, str):
        return None
    value = value.strip()
    if HEX3.match(value):
        return "#" + "".join(c * 2 for c in value[1:]).lower()
    match = HEX6.match(value)
    if match:
        return f"#{match.group(1).lower()}"
    match = RGB.match(value)
    return ds_build.to_hex(int(v) for v in match.groups()) if match else None


def dimension(value) -> float | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, dict) and "value" in value:  # DTCG 2025 : {"value": 16, "unit": "px"}
        return dimension(f"{value['value']}{value.get('unit', 'px')}")
    match = DIM.match(str(value).strip())
    if not match:
        return None
    number = float(match.group(1))
    return number * 16 if match.group(2) in ("rem", "em") else number


# --- Lecture des formats ------------------------------------------------------------------------------------

def js_object(text: str) -> dict:
    """Objet littéral JS simple (createTheme({...}), ThemeConfig = {...}) lu comme du JSON."""
    start = text.find("{", text.find("createTheme(") if "createTheme(" in text else text.find("="))
    depth, end = 0, -1
    for i in range(start, len(text)):
        depth += {"{": 1, "}": -1}.get(text[i], 0)
        if depth == 0:
            end = i
            break
    body = text[start:end + 1]
    body = re.sub(r"//[^\n]*|/\*.*?\*/", "", body, flags=re.S)
    body = re.sub(r"'([^'\\]*)'", lambda m: json.dumps(m.group(1)), body)
    body = re.sub(r"([{,]\s*)([A-Za-z_$][\w$]*)\s*:", r'\1"\2":', body)
    body = re.sub(r",\s*([}\]])", r"\1", body)
    return json.loads(body)


def flatten(data, prefix: str = "", inherited: str | None = None) -> list[tuple[str, object, str | None]]:
    """(chemin, valeur, type) des feuilles ; un token W3C ou Style Dictionary est une feuille."""
    out = []
    if isinstance(data, dict):
        kind = data.get("$type", data.get("type") if isinstance(data.get("type"), str) else None) or inherited
        if "$value" in data or ("value" in data and not isinstance(data.get("value"), dict)):
            return [(prefix, data.get("$value", data.get("value")), kind)]
        for key, value in data.items():
            if key.startswith("$") or key in ("type", "description"):
                continue
            out += flatten(value, f"{prefix}.{key}" if prefix else key, kind)
    elif isinstance(data, list) and all(isinstance(v, (int, float)) for v in data):
        out.append((prefix, data, inherited))
    else:
        out.append((prefix, data, inherited))
    return out


def resolve(entries: list[tuple], warnings: list[str]) -> list[tuple]:
    """Alias {chemin.du.token} et var(--nom) remplacés par leur valeur."""
    values = {path: value for path, value, _ in entries}
    values.update({norm(path): value for path, value, _ in entries})

    def one(value, seen=()):
        if isinstance(value, str):
            match = re.fullmatch(r"\{([^}]+)\}|var\(--([\w-]+)(?:,[^)]*)?\)", value.strip())
            if match:
                key = match.group(1) or match.group(2)
                target = values.get(key, values.get(norm(key)))
                if target is None or key in seen:
                    warnings.append(f"alias non résolu : {value}")
                    return None
                return one(target, (*seen, key))
        return value
    return [(path, one(value), kind) for path, value, kind in entries]


def read(path: Path, errors: list[str]) -> tuple[str, list[tuple]]:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in (".css", ".scss"):
        return "css", [(f"--{m.group(1)}", m.group(2).strip(), None)
                       for m in re.finditer(r"--([\w-]+)\s*:\s*([^;}{]+);", text)]
    try:
        data = json.loads(text) if path.suffix.lower() == ".json" else js_object(text)
    except (ValueError, IndexError) as error:
        errors.append(f"{path.name} : illisible ({str(error)[:80]}) ; donnez le thème en JSON, en tokens W3C ou en CSS")
        return "?", []
    if isinstance(data, dict) and "colors" in data and isinstance(data["colors"], dict) and "name" in data:
        return "myskills", [("myskills", data, None)]
    if isinstance(data, dict) and "palette" in data:
        return "mui", flatten({k: v for k, v in data.items() if k in ("palette", "typography", "shape", "spacing")})
    if isinstance(data, dict) and isinstance(data.get("token"), dict):
        return "antd", flatten(data["token"])
    return "tokens", flatten(data)


# --- Classement ---------------------------------------------------------------------------------------------

def nature(path: str, value, kind: str | None) -> str | None:
    name = norm(path)
    kind = (kind or "").lower()
    if kind == "color" or (color(value) and not re.search(r"shadow|elevation", name)):
        return "color" if color(value) else None
    if kind in ("fontfamily", "font-family") or re.search(r"font-?family|(^|-)font$|family", name):
        return "font"
    if kind == "shadow" or re.search(r"shadow|elevation", name):
        return "shadow"
    if re.search(r"radius|rounded|corner", name):
        return "radius"
    if re.search(r"font-?size|text-(xs|sm|md|base|lg|xl|\d)|fontsize|(^|-)size-(xs|sm|md|lg|xl|\d)", name) \
            or kind in ("fontsize", "font-size"):
        return "font_size"
    if re.search(r"space|spacing|gap|gutter|margin|padding", name) or kind == "spacing":
        return "spacing"
    if re.search(r"line-?height", name):
        return "line_height"
    if kind == "dimension":
        return "spacing"
    return None


def short(path: str, cut: tuple[str, ...]) -> str:
    """Nom court d'un token : chemin normalisé sans les préfixes de nature (color-, palette-, space-...)."""
    name = norm(path)
    for prefix in cut:
        name = re.sub(rf"^(?:[a-z]+-)?{prefix}(?:-|$)", "", name)
    return name


def role_of(name: str, table: dict) -> str | None:
    for role, names in table.items():
        if name in names:
            return role
    for role, names in table.items():
        if any(name.endswith(f"-{n}") or name.startswith(f"{n}-") for n in names[:2]) and not name.startswith("on-"):
            return role
    return None


def convert(fmt: str, entries: list[tuple], name: str, errors: list[str], warnings: list[str]) -> tuple[dict, dict]:
    if fmt == "myskills":
        return entries[0][1], {"mapped": {}, "kept": [], "ignored": []}
    tokens = {"name": name, "colors": {}, "fonts": {}, "font_sizes": {}, "spacing": {}, "radii": {}, "shadows": {}}
    mapped, kept, ignored = {}, [], []
    for path, value, kind in entries:
        what = nature(path, value, kind)
        if what is None or value is None:
            ignored.append(path)
            continue
        if what == "color":
            hex_ = color(value)
            label = short(path, ("color", "colors", "palette")) or norm(path)
            role = role_of(label, ROLES)
            if role and role not in tokens["colors"]:
                tokens["colors"][role] = hex_
                mapped[role] = path
            elif re.match(r"^[a-z0-9][a-z0-9-]*$", label) and label not in tokens["colors"]:
                tokens["colors"][label] = hex_
                kept.append(label)
        elif what == "font":
            family = ", ".join(value) if isinstance(value, list) else str(value)
            role = role_of(short(path, ("font-family", "font", "fonts", "typography")), FONT_ROLES) or "body"
            if role not in tokens["fonts"]:
                tokens["fonts"][role] = family
                mapped[f"fonts.{role}"] = path
        elif what == "shadow":
            if isinstance(value, str):
                tokens["shadows"][short(path, ("shadow", "shadows", "elevation", "box-shadow")) or "md"] = value
        elif what == "line_height":
            number = dimension(value)
            if number and 1 <= number <= 2.5:
                tokens["line_height"] = number
        else:
            number = dimension(value)
            key = {"radius": "radii", "font_size": "font_sizes", "spacing": "spacing"}[what]
            label = short(path, {"radius": ("border-radius", "radius", "radii", "rounded", "shape"),
                                 "font_size": ("font-size", "font-sizes", "fontsize", "text", "size", "typography"),
                                 "spacing": ("spacing", "space", "size", "gap")}[what]) or "md"
            limit = {"radii": 999, "font_sizes": 128, "spacing": 256}[key]
            if number is None or number < 0 or number > limit or not re.match(r"^[a-z0-9][a-z0-9-]*$", label):
                ignored.append(path)
                continue
            if key == "font_sizes" and number < 8:
                ignored.append(path)
                continue
            tokens[key][label] = round(number, 2)
    if fmt == "mui" and "spacing" in dict((p, v) for p, v, _ in entries):
        tokens["spacing"] = {}  # MUI : facteur d'espacement, pas une échelle ; valeurs par défaut gardées
    tokens = {k: v for k, v in tokens.items() if v != {}}
    missing = [r for r in ("primary", "background", "text") if r not in tokens.get("colors", {})]
    for role in missing:
        tokens.setdefault("colors", {})[role] = ds_build.DEFAULTS["colors"][role]
    if missing:
        warnings.append(f"rôle(s) absent(s) du design system fourni : {', '.join(missing)} ; valeur par défaut mise, "
                        "à confirmer avec le client")
    return tokens, {"mapped": mapped, "kept": kept, "ignored": ignored}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="+", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--name", default="")
    args = parser.parse_args()
    report = {"inputs": [str(p) for p in args.files], "format": None, "output": None, "colors": 0, "mapped": {},
              "kept": [], "ignored": 0, "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]
    formats, entries = [], []
    for path in args.files:
        if not path.is_file():
            errors.append(f"{path} introuvable")
            continue
        fmt, found = read(path, errors)
        formats.append(fmt)
        entries += found
    if errors or not entries:
        errors += [] if errors else ["aucun token trouvé dans les fichiers donnés"]
        print(json.dumps(report, ensure_ascii=False))
        return 1
    fmt = formats[0] if len(set(formats)) == 1 else "+".join(sorted(set(formats)))
    if fmt != "myskills":
        entries = resolve(entries, warnings)
    name = args.name or args.out.stem.replace("-", " ").capitalize()
    tokens, detail = convert("myskills" if fmt == "myskills" else fmt, entries, name, errors, warnings)
    tokens["source"] = {"format": fmt, "files": [p.name for p in args.files], "locked": True}
    tokens.setdefault("description", f"Design system fourni ({', '.join(p.name for p in args.files)}), repris par "
                                     "ds_import.py : il prime sur les maquettes.")
    errors += ds_build.tokens_errors(tokens)
    report.update(format=fmt, colors=len(tokens.get("colors", {})), mapped=detail["mapped"], kept=detail["kept"],
                  ignored=len(detail["ignored"]))
    if detail["ignored"]:
        warnings.append(f"{len(detail['ignored'])} token(s) non repris (nature inconnue ou valeur hors bornes) : "
                        + ", ".join(detail["ignored"][:5]) + ("..." if len(detail["ignored"]) > 5 else ""))
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(tokens, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    report["output"] = str(args.out)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
