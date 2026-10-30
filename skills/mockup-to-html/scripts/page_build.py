# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "playwright>=1.48"]
# ///
"""Construit une page HTML/CSS depuis une description JSON courte, la rend et la compare à sa maquette.

Le modèle regarde la maquette et décrit la page : un arbre de composants
(section, row, grid, header, card, form, table...) avec leurs textes et des
références aux tokens du design system (couleurs, tailles, espacements). Le
script, et non le modèle, écrit le HTML sémantique et le CSS, puis contrôle :

- composants, propriétés, variantes et tokens connus ; images locales
  seulement (aucune ressource externe) ; zones découpées dans la maquette
  dans ses limites ;
- accessibilité : un seul h1, niveaux de titres sans saut, images avec
  texte alternatif, contraste du texte sur le fond de chaque section ;
- rendu dans un navigateur local (Playwright, réseau coupé) à la largeur de
  la maquette, capture, comparaison avec la maquette (similarité de 0 à 1,
  zones les plus éloignées, hauteur), débordement horizontal sur mobile.

Écrit <nom>.html, <nom>.css, assets/ (zones découpées), <nom>.render.png et,
avec une maquette, <nom>.compare.png (maquette, rendu, écarts côte à côte) :
le modèle ne regarde que cette image, et seulement si la similarité est
faible.

Cibles (--target) : html (défaut), bootstrap (classes et thème Bootstrap, rendu et
comparé de même), react-mui et react-antd (page TSX, thème tiré des tokens et
App ; JSX contrôlé, rendu non vérifié : la cible html sert de référence).

    uv run scripts/page_build.py PAGE.json [--out-dir DOSSIER] [--target html|bootstrap|react-mui|react-antd]
        [--no-render] [--min-similarity 0.6] | --schema
"""

import argparse
import difflib
import html
import json
import re
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
sys.path.insert(0, str(Path(__file__).resolve().parent / "targets"))
import local_tools  # noqa: E402
import react  # noqa: E402
import skill_paths  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

COMMON = {"type", "id", "align", "background", "color", "padding"}
PROPS = {
    "section": {"children", "width"},
    "row": {"children", "columns", "gap", "valign"},
    "stack": {"children", "gap"},
    "grid": {"children", "columns", "gap"},
    "header": {"text", "src", "crop", "alt", "items", "actions"},
    "nav": {"items", "variant"},
    "breadcrumb": {"items"},
    "heading": {"text", "level", "size"},
    "text": {"text", "size", "muted", "bold"},
    "link": {"text", "href"},
    "button": {"text", "variant", "size", "href"},
    "buttons": {"items"},
    "image": {"src", "crop", "alt", "height", "radius"},
    "box": {"width", "height", "radius", "shadow"},
    "card": {"title", "text", "src", "crop", "alt", "children", "actions", "shadow", "radius"},
    "form": {"title", "fields", "submit", "columns"},
    "table": {"headers", "rows", "variant"},
    "list": {"items", "variant"},
    "badge": {"text", "variant"},
    "alert": {"title", "text", "variant"},
    "tabs": {"items", "current"},
    "stepper": {"items", "current"},
    "stat": {"label", "value", "text"},
    "search": {"text", "placeholder"},
    "divider": set(),
    "spacer": {"size"},
    "footer": {"groups", "text"},
}
REQUIRED = {"heading": ["text"], "text": ["text"], "link": ["text"], "button": ["text"], "badge": ["text"],
            "buttons": ["items"], "nav": ["items"], "breadcrumb": ["items"], "list": ["items"], "tabs": ["items"],
            "stepper": ["items"], "form": ["fields"], "table": ["rows"], "stat": ["label", "value"],
            "row": ["children"], "grid": ["children"], "stack": ["children"], "section": ["children"]}
VARIANTS = {"button": ["primary", "secondary", "outline", "ghost", "danger"], "nav": ["horizontal", "vertical"],
            "table": ["plain", "striped"], "list": ["bullet", "ordered", "check", "plain"],
            "badge": ["neutral", "info", "success", "warning", "danger"],
            "alert": ["info", "success", "warning", "danger"]}
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
EXTERNAL = re.compile(r"^[a-z][a-z0-9+.-]*:", re.I)
MOBILE = 390
TARGET_NAMES = ["html", "bootstrap", "react-mui", "react-antd"]
SELECTED, STEP = 'aria-selected="true"', ' aria-current="step"'

CSS = """*,*::before,*::after{box-sizing:border-box}
body{margin:0;font-family:var(--font-body);font-size:var(--text-md);line-height:var(--line-height);color:var(--color-text);background:var(--color-background)}
h1,h2,h3,h4,h5,h6{font-family:var(--font-heading);margin:0;line-height:1.2}
h1{font-size:var(--text-3xl)}h2{font-size:var(--text-2xl)}h3{font-size:var(--text-xl)}h4{font-size:var(--text-lg)}h5,h6{font-size:var(--text-md)}
p{margin:0}img{display:block;max-width:100%}a{color:var(--color-primary)}
.container{max-width:var(--max-width);margin:0 auto;padding:0 var(--space-lg)}
.c-section{padding:var(--space-2xl) 0}.c-section>.container,.c-section--full{display:flex;flex-direction:column;gap:var(--space-lg)}
.c-row{display:grid;gap:var(--space-lg)}
.c-stack{display:flex;flex-direction:column;gap:var(--space-md)}
.c-grid{display:grid;gap:var(--space-lg)}
.c-header{border-bottom:1px solid var(--color-border);background:var(--color-background)}
.c-header>.container{display:flex;align-items:center;gap:var(--space-lg);min-height:64px}
.c-header__logo{display:flex;align-items:center;gap:var(--space-sm);font-weight:700;font-size:var(--text-lg);color:inherit;text-decoration:none}
.c-header__logo img{max-height:40px;width:auto}
.c-header .c-nav{flex:1}
.c-nav ul{list-style:none;margin:0;padding:0;display:flex;gap:var(--space-lg)}
.c-nav a{color:inherit;text-decoration:none}.c-nav a[aria-current]{color:var(--color-primary);font-weight:600}
.c-nav--vertical ul{flex-direction:column;gap:var(--space-sm)}
.c-buttons,.c-header__actions{display:flex;flex-wrap:wrap;gap:var(--space-sm);align-items:center}
.c-button{display:inline-flex;align-items:center;justify-content:center;gap:.5em;padding:.625em 1.25em;border-radius:var(--radius-md);border:1px solid transparent;font:inherit;font-weight:600;line-height:1.2;text-decoration:none;cursor:pointer}
.c-button--primary{background:var(--color-primary);color:var(--color-on-primary)}
.c-button--secondary{background:var(--color-secondary);color:var(--color-on-secondary)}
.c-button--outline{background:transparent;border-color:var(--color-primary);color:var(--color-primary)}
.c-button--ghost{background:transparent;color:var(--color-primary)}
.c-button--danger{background:var(--color-danger);color:var(--color-on-danger)}
.c-button--sm{font-size:var(--text-sm);padding:.375em .875em}.c-button--lg{font-size:var(--text-lg)}
.c-text--muted{color:var(--color-muted)}.c-text--bold{font-weight:700}
.c-card{background:var(--color-background);color:var(--color-text);border:1px solid var(--color-border);border-radius:var(--radius-lg);overflow:hidden;display:flex;flex-direction:column}
.c-card__body{padding:var(--space-lg);display:flex;flex-direction:column;gap:var(--space-sm);flex:1}
.c-card__title{font-size:var(--text-lg)}
.c-image{width:100%;object-fit:cover}
.c-image--placeholder{background:var(--color-surface);border:1px dashed var(--color-border);display:flex;align-items:center;justify-content:center;color:var(--color-muted);min-height:160px}
.c-form{display:grid;gap:var(--space-md)}.c-form--2{grid-template-columns:1fr 1fr}.c-form>h2,.c-form>.c-buttons,.c-field--full{grid-column:1/-1}
.c-form>h2{font-size:var(--text-xl)}
.c-field{display:flex;flex-direction:column;gap:var(--space-xs)}
.c-field>label{font-weight:600;font-size:var(--text-sm)}
.c-field--check{flex-direction:row;align-items:center;gap:var(--space-sm)}.c-field--check>label{font-weight:400;font-size:var(--text-md)}
.c-field__help{font-size:var(--text-sm);color:var(--color-muted)}
fieldset.c-field{border:0;padding:0;margin:0;min-width:0}fieldset.c-field>legend{float:none;font-weight:600;font-size:var(--text-sm);line-height:inherit;padding:0;margin:0 0 var(--space-xs)}
fieldset.c-field>label{display:inline-flex;align-items:center;gap:.375em;margin-right:var(--space-md)}
input,select,textarea{font:inherit;padding:.625em .75em;border:1px solid var(--color-border);border-radius:var(--radius-md);background:var(--color-background);color:inherit;width:100%}
input[type=checkbox],input[type=radio]{width:auto}
.c-table{width:100%;border-collapse:collapse}
.c-table th,.c-table td{text-align:left;padding:var(--space-sm) var(--space-md);border-bottom:1px solid var(--color-border)}
.c-table th{font-size:var(--text-sm);color:var(--color-muted);font-weight:600}
.c-table--striped tbody tr:nth-child(odd){background:var(--color-surface)}
.c-list{margin:0;padding-left:1.25em;display:flex;flex-direction:column;gap:var(--space-xs)}
.c-list--plain,.c-list--check{list-style:none;padding-left:0}.c-list--check li::before{content:"\\2713";color:var(--color-success);margin-right:.5em}
.c-badge{display:inline-block;width:max-content;padding:.125em .625em;border-radius:var(--radius-full);font-size:var(--text-xs);font-weight:600;background:var(--color-surface);color:var(--color-text);border:1px solid var(--color-border)}
.c-alert{padding:var(--space-md);border-radius:var(--radius-md);border-left:4px solid var(--tone);background:color-mix(in srgb,var(--tone) 10%,var(--color-background));display:flex;flex-direction:column;gap:var(--space-xs)}
.c-tabs ul{display:flex;list-style:none;margin:0;padding:0;border-bottom:1px solid var(--color-border)}
.c-tabs a{display:block;padding:var(--space-sm) var(--space-md);color:var(--color-muted);text-decoration:none;border-bottom:2px solid transparent;margin-bottom:-1px}
.c-tabs a[aria-selected=true]{color:var(--color-primary);border-color:var(--color-primary);font-weight:600}
.c-stepper ol{display:flex;list-style:none;margin:0;padding:0;gap:var(--space-md);counter-reset:step}
.c-stepper li{flex:1;display:flex;align-items:center;gap:var(--space-sm);color:var(--color-muted)}
.c-stepper li::before{counter-increment:step;content:counter(step);flex:none;width:2em;height:2em;border-radius:50%;display:inline-flex;align-items:center;justify-content:center;border:2px solid var(--color-border);font-weight:600}
.c-stepper .is-done::before{background:var(--color-primary);border-color:var(--color-primary);color:var(--color-on-primary)}
.c-stepper .is-current{color:var(--color-text);font-weight:600}.c-stepper .is-current::before{border-color:var(--color-primary);color:var(--color-primary)}
.c-breadcrumb ol{display:flex;flex-wrap:wrap;list-style:none;margin:0;padding:0;gap:var(--space-xs);font-size:var(--text-sm);color:var(--color-muted)}
.c-breadcrumb li+li::before{content:"/";margin-right:var(--space-xs)}.c-breadcrumb a{color:inherit}
.c-stat{display:flex;flex-direction:column;gap:var(--space-xs)}.c-stat__value{font-size:var(--text-2xl);font-weight:700;line-height:1.2}
.c-stat__label{color:var(--color-muted);font-size:var(--text-sm)}
.c-search{display:flex;gap:var(--space-sm)}.c-search input{flex:1}
.c-divider{border:0;border-top:1px solid var(--color-border);margin:0;width:100%}
.c-footer{background:var(--color-surface);padding:var(--space-2xl) 0;font-size:var(--text-sm)}
.c-footer>.container{display:flex;flex-direction:column;gap:var(--space-lg)}
.c-footer__groups{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:var(--space-lg)}
.c-footer h2{font-size:var(--text-sm);margin-bottom:var(--space-sm)}
.c-footer ul{list-style:none;padding:0;margin:0;display:flex;flex-direction:column;gap:var(--space-xs)}.c-footer a{color:inherit}
.is-left{text-align:left;align-items:flex-start}.is-center{text-align:center;align-items:center;justify-content:center}.is-right{text-align:right;align-items:flex-end;justify-content:flex-end}
@media (max-width:767px){.c-row,.c-grid,.c-form--2{grid-template-columns:1fr!important}.c-header>.container{flex-wrap:wrap;padding-top:var(--space-sm);padding-bottom:var(--space-sm)}.c-nav ul{flex-wrap:wrap;gap:var(--space-sm) var(--space-md)}.c-stepper ol{flex-direction:column}.c-table{display:block;overflow-x:auto}}
"""


class Page:
    """Construction d'une page : HTML, contrôles et zones découpées."""

    def __init__(self, spec: dict, theme: dict, ds, base: Path, out_dir: Path, stem: str, mockup):
        self.spec, self.theme, self.ds, self.base, self.out_dir, self.stem = spec, theme, ds, base, out_dir, stem
        self.mockup = mockup  # image PIL ou None
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.assets: list[Path] = []
        self.headings: list[tuple[int, str]] = []
        self.count = 0
        self.fields = 0
        self.sources: dict[int, str] = {}  # image locale de chaque nœud (cibles React)

    # --- tokens
    def token(self, where: str, kind: str, value, extra=()):
        known = {"color": self.theme["colors"], "space": self.theme["spacing"], "text": self.theme["font_sizes"],
                 "radius": self.theme["radii"], "shadow": self.theme["shadows"]}[kind]
        if kind == "color" and isinstance(value, str) and HEX.match(value):
            self.warnings.append(f"{where} : couleur {value} écrite en dur, hors design system (token à créer ?)")
            return value
        if value in known or value in extra:
            return f"var(--{kind}-{value})" if value in known else value
        match = difflib.get_close_matches(str(value), list(known), n=1)
        self.errors.append(f"{where} : token {kind} inconnu « {value} »"
                           + (f" ; vouliez-vous « {match[0]} » ?" if match else f" ({', '.join(known)})"))
        return ""

    def ink(self, node: dict) -> str | None:
        """Texte posé sur un fond du design system : on-<fond> s'il existe, sans color précisé."""
        name = f"on-{node.get('background')}"
        return name if "color" not in node and name in self.theme["colors"] else None

    def color_of(self, value) -> str | None:
        if isinstance(value, str) and HEX.match(value):
            return value
        return self.theme["colors"].get(value)

    # --- contrôle d'un nœud
    def check(self, node: dict, where: str) -> bool:
        kind = node["type"]
        unknown = sorted(set(node) - COMMON - PROPS[kind])
        for prop in unknown:
            self.errors.append(f"{where}/{prop} : propriété non permise pour {kind} "
                               f"(permises : {', '.join(sorted(PROPS[kind] | COMMON - {'type'}))})")
        for prop in REQUIRED.get(kind, []):
            if prop not in node:
                self.errors.append(f"{where} : champ « {prop} » manquant pour {kind}")
        if "variant" in node and node["variant"] not in VARIANTS.get(kind, []):
            match = difflib.get_close_matches(node["variant"], VARIANTS.get(kind, []), n=1)
            self.errors.append(f"{where}/variant : « {node['variant']} » non permis pour {kind} "
                               f"({', '.join(VARIANTS.get(kind, []))})" + (f" ; vouliez-vous « {match[0]} » ?" if match else ""))
        columns = node.get("columns")
        if kind == "row" and "columns" in node and not isinstance(columns, list):
            self.errors.append(f"{where}/columns : liste de proportions attendue pour row, par ex. [2, 1]")
        if kind in ("grid", "form") and isinstance(columns, list):
            self.errors.append(f"{where}/columns : nombre de colonnes (entier) attendu pour {kind}")
        if kind == "row" and isinstance(columns, list) and len(columns) != len(node.get("children", [])):
            self.warnings.append(f"{where} : {len(columns)} proportions pour {len(node.get('children', []))} enfants")
        if kind == "section" and node.get("width") not in (None, "full", "contained"):
            self.errors.append(f"{where}/width : « {node['width']} » non permis pour section (full, contained)")
        if kind == "box" and isinstance(node.get("width"), str):
            self.errors.append(f"{where}/width : largeur en pixels (entier) attendue pour box")
        return not unknown

    # --- rendu HTML
    def style(self, node: dict, where: str, extra: dict | None = None) -> str:
        rules = dict(extra or {})
        if "background" in node:
            rules["background"] = self.token(f"{where}/background", "color", node["background"])
        if "color" in node:
            rules["color"] = self.token(f"{where}/color", "color", node["color"])
        elif self.ink(node):
            rules["color"] = f"var(--color-{self.ink(node)})"
        if "padding" in node:
            value = self.token(f"{where}/padding", "space", node["padding"])
            rules["padding"] = f"{value} 0" if node["type"] == "section" else value
        text = ";".join(f"{k}:{v}" for k, v in rules.items() if v)
        return f' style="{html.escape(text)}"' if text else ""

    def classes(self, node: dict, *names: str) -> str:
        extra = [f"is-{node['align']}"] if node.get("align") else []
        return " ".join([n for n in names if n] + extra)

    def attrs(self, node: dict, where: str, *names: str, extra: dict | None = None) -> str:
        ident = f' id="{html.escape(node["id"])}"' if node.get("id") else ""
        return f'{ident} class="{self.classes(node, *names)}"{self.style(node, where, extra)}'

    def item(self, value) -> dict:
        return {"text": value} if isinstance(value, str) else value

    def link(self, item: dict) -> str:
        return html.escape(item.get("href", "#"), quote=True)

    def image(self, node: dict, where: str, css: str = "c-image", default_alt: str | None = None) -> str:
        alt = node.get("alt", default_alt)
        if alt is None:
            self.warnings.append(f"{where} : image sans texte alternatif (alt, \"\" si décorative)")
        source = None
        if "crop" in node:
            source = self.crop(node["crop"], f"{where}/crop")
        elif "src" in node:
            source = self.copy(node["src"], f"{where}/src")
        height = f' style="height:{node["height"]}px"' if node.get("height") else ""
        radius = node.get("radius")
        if radius:
            value = self.token(f"{where}/radius", "radius", radius)
            height = height[:-1] + f';border-radius:{value}"' if height else f' style="border-radius:{value}"'
        if source:
            self.sources[id(node)] = source
            return f'<img class="{css}" src="{html.escape(source)}" alt="{html.escape(alt or "")}"{height}>'
        label = html.escape(alt or "Image")
        return f'<div class="{css} c-image--placeholder" role="img" aria-label="{label}"{height}>{label}</div>'

    def crop(self, box: list, where: str) -> str | None:
        if self.mockup is None:
            self.errors.append(f"{where} : découpe sans maquette (champ mockup)")
            return None
        x, y, w, h = box
        if x + w > self.mockup.width or y + h > self.mockup.height:
            self.errors.append(f"{where} : zone {box} hors de la maquette ({self.mockup.width} x {self.mockup.height})")
            return None
        name = f"assets/{self.stem}-{len(self.assets) + 1}.png"
        target = self.out_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        self.mockup.crop((x, y, x + w, y + h)).save(target)
        self.assets.append(target)
        return name

    def copy(self, src: str, where: str) -> str | None:
        if EXTERNAL.match(src) or src.startswith("//"):
            self.errors.append(f"{where} : ressource externe « {src[:60]} » interdite, rendu local seulement ; "
                               "donnez un fichier local ou une zone de la maquette (crop)")
            return None
        path = (self.base / src).resolve()
        if not path.is_file():
            self.errors.append(f"{where} : image introuvable {src}")
            return None
        name = f"assets/{path.name}"
        target = self.out_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if path != target.resolve():
            shutil.copyfile(path, target)
        self.assets.append(target)
        return name

    def buttons(self, items: list, where: str, default_last: str = "primary", other: str = "secondary") -> str:
        out = []
        for i, raw in enumerate(items):
            item = self.item(raw)
            variant = item.get("variant") or (default_last if i == len(items) - 1 else other)
            if variant not in VARIANTS["button"]:
                self.errors.append(f"{where}/{i}/variant : « {variant} » non permis ({', '.join(VARIANTS['button'])})")
            out.append(f'<a class="c-button c-button--{variant}" href="{self.link(item)}">{html.escape(item["text"])}</a>')
        return "".join(out)

    def nav_list(self, items: list, current_attr: str = 'aria-current="page"', current: int | None = None) -> str:
        out = []
        for i, raw in enumerate(items):
            item = self.item(raw)
            active = item.get("active") or (current == i + 1)
            out.append(f'<li><a href="{self.link(item)}"{" " + current_attr if active else ""}>'
                       f'{html.escape(item["text"])}</a></li>')
        return "".join(out)

    def contrast(self, node: dict, where: str, inherited_bg: str, inherited_fg: str) -> tuple[str, str]:
        if node["type"] == "card":
            inherited_bg, inherited_fg = self.theme["colors"]["background"], self.theme["colors"]["text"]
        bg = self.color_of(node.get("background")) or inherited_bg
        fg = self.color_of(node.get("color") or self.ink(node)) or inherited_fg
        if ("background" in node or "color" in node) and bg and fg:
            ratio = self.ds.contrast(fg, bg)
            if ratio < 4.5:
                self.warnings.append(f"{where} : contraste du texte {ratio}:1 sur le fond, 4.5:1 attendu "
                                     "(color à préciser)")
        return bg, fg

    def node(self, node: dict, where: str, bg: str | None = None, fg: str | None = None) -> str:
        self.count += 1
        if not self.check(node, where):
            return ""
        kind, e = node["type"], html.escape
        bg, fg = self.contrast(node, where, bg or self.theme["colors"]["background"],
                               fg or self.theme["colors"]["text"])
        sub = lambda: "".join(self.node(c, f"{where}/children/{i}", bg, fg)  # noqa: E731
                              for i, c in enumerate(node.get("children", [])))
        if kind == "section":
            full = node.get("width") == "full"
            inner = sub()
            body = inner if full else f'<div class="container">{inner}</div>'
            return f'<section{self.attrs(node, where, "c-section", "c-section--full" if full else "")}>{body}</section>'
        if kind == "row":
            cols = " ".join(f"{c:g}fr" for c in node.get("columns") or [1] * len(node.get("children", [])))
            extra = {"grid-template-columns": cols}
            if node.get("gap"):
                extra["gap"] = self.token(f"{where}/gap", "space", node["gap"])
            if node.get("valign"):
                extra["align-items"] = {"start": "start", "center": "center", "end": "end", "stretch": "stretch"}.get(
                    node["valign"], "stretch")
            return f'<div{self.attrs(node, where, "c-row", extra=extra)}>{sub()}</div>'
        if kind == "grid":
            extra = {"grid-template-columns": f"repeat({node.get('columns', 3)},minmax(0,1fr))"}
            if node.get("gap"):
                extra["gap"] = self.token(f"{where}/gap", "space", node["gap"])
            return f'<div{self.attrs(node, where, "c-grid", extra=extra)}>{sub()}</div>'
        if kind == "stack":
            extra = {"gap": self.token(f"{where}/gap", "space", node["gap"])} if node.get("gap") else {}
            return f'<div{self.attrs(node, where, "c-stack", extra=extra)}>{sub()}</div>'
        if kind == "header":
            logo = ""
            if "crop" in node or "src" in node:
                logo = self.image(node, where, "c-header__mark", node.get("text", "Logo"))
            logo = f'<a class="c-header__logo" href="#">{logo}{e(node.get("text", ""))}</a>'
            nav = f'<nav class="c-nav" aria-label="Navigation principale"><ul>{self.nav_list(node["items"])}</ul></nav>' \
                if node.get("items") else '<div class="c-nav"></div>'
            actions = f'<div class="c-header__actions">{self.buttons(node["actions"], where + "/actions", "primary", "ghost")}</div>' \
                if node.get("actions") else ""
            return f'<header{self.attrs(node, where, "c-header")}><div class="container">{logo}{nav}{actions}</div></header>'
        if kind == "nav":
            variant = node.get("variant", "horizontal")
            return (f'<nav{self.attrs(node, where, "c-nav", f"c-nav--{variant}")} aria-label="Navigation">'
                    f'<ul>{self.nav_list(node["items"])}</ul></nav>')
        if kind == "breadcrumb":
            items = [self.item(i) for i in node["items"]]
            lis = "".join(f'<li><a href="{self.link(i)}">{e(i["text"])}</a></li>' for i in items[:-1])
            lis += f'<li aria-current="page">{e(items[-1]["text"])}</li>' if items else ""
            return f'<nav{self.attrs(node, where, "c-breadcrumb")} aria-label="Fil d\'Ariane"><ol>{lis}</ol></nav>'
        if kind == "heading":
            level = node.get("level", 2)
            self.headings.append((level, where))
            extra = {"font-size": self.token(f"{where}/size", "text", node["size"])} if node.get("size") else {}
            return f'<h{level}{self.attrs(node, where, "c-heading", extra=extra)}>{e(node["text"])}</h{level}>'
        if kind == "text":
            extra = {"font-size": self.token(f"{where}/size", "text", node["size"])} if node.get("size") else {}
            names = ["c-text", "c-text--muted" if node.get("muted") else "", "c-text--bold" if node.get("bold") else ""]
            return f'<p{self.attrs(node, where, *names, extra=extra)}>{e(node["text"])}</p>'
        if kind == "link":
            return f'<a{self.attrs(node, where, "c-link")} href="{self.link(node)}">{e(node["text"])}</a>'
        if kind == "button":
            names = ["c-button", f"c-button--{node.get('variant', 'primary')}",
                     f"c-button--{node['size']}" if node.get("size") in ("sm", "lg") else ""]
            if node.get("size") not in (None, "sm", "md", "lg"):
                self.errors.append(f"{where}/size : « {node['size']} » non permis pour button (sm, md, lg)")
            return f'<a{self.attrs(node, where, *names)} href="{self.link(node)}">{e(node["text"])}</a>'
        if kind == "buttons":
            return f'<div{self.attrs(node, where, "c-buttons")}>{self.buttons(node["items"], where + "/items")}</div>'
        if kind == "image":
            return self.image(node, where)
        if kind == "box":
            extra = {"height": f"{node.get('height', 16)}px"}
            if node.get("width"):
                extra["width"] = f"{node['width']}px"
            if node.get("radius"):
                extra["border-radius"] = self.token(f"{where}/radius", "radius", node["radius"])
            if node.get("shadow"):
                extra["box-shadow"] = self.token(f"{where}/shadow", "shadow", node["shadow"])
            return f'<div{self.attrs(node, where, "c-box", extra=extra)} aria-hidden="true"></div>'
        if kind == "card":
            extra = {}
            if node.get("radius"):
                extra["border-radius"] = self.token(f"{where}/radius", "radius", node["radius"])
            if node.get("shadow"):
                extra["box-shadow"] = self.token(f"{where}/shadow", "shadow", node["shadow"])
            media = self.image(node, where) if ("crop" in node or "src" in node) else ""
            level = min(6, max(2, self.headings[-1][0] + 1 if self.headings else 2))
            title = f'<h{level} class="c-card__title">{e(node["title"])}</h{level}>' if node.get("title") else ""
            if title:
                self.headings.append((level, where))
            text = f'<p>{e(node["text"])}</p>' if node.get("text") else ""
            actions = f'<div class="c-buttons">{self.buttons(node["actions"], where + "/actions", "outline", "ghost")}</div>' \
                if node.get("actions") else ""
            return (f'<article{self.attrs(node, where, "c-card", extra=extra)}>{media}<div class="c-card__body">'
                    f'{title}{text}{sub()}{actions}</div></article>')
        if kind == "form":
            cols = node.get("columns", 1)
            title = f'<h2>{e(node["title"])}</h2>' if node.get("title") else ""
            if title:
                self.headings.append((2, where))
            fields = "".join(self.field(f, f"{where}/fields/{i}") for i, f in enumerate(node["fields"]))
            submit = f'<div class="c-buttons"><button class="c-button c-button--primary" type="submit">' \
                     f'{e(node.get("submit", "Valider"))}</button></div>'
            return f'<form{self.attrs(node, where, "c-form", "c-form--2" if cols == 2 else "")}>{title}{fields}{submit}</form>'
        if kind == "table":
            head = "".join(f'<th scope="col">{e(h)}</th>' for h in node.get("headers", []))
            rows = "".join("<tr>" + "".join(f"<td>{e(str(c))}</td>" for c in row) + "</tr>" for row in node["rows"])
            width = len(node.get("headers", [])) or None
            if width and any(len(r) != width for r in node["rows"]):
                self.warnings.append(f"{where} : lignes de longueur différente de l'en-tête ({width} colonnes)")
            return (f'<table{self.attrs(node, where, "c-table", "c-table--" + node.get("variant", "plain"))}>'
                    f'{"<thead><tr>" + head + "</tr></thead>" if head else ""}<tbody>{rows}</tbody></table>')
        if kind == "list":
            variant = node.get("variant", "bullet")
            tag = "ol" if variant == "ordered" else "ul"
            lis = "".join(f"<li>{e(self.item(i)['text'])}</li>" for i in node["items"])
            return f'<{tag}{self.attrs(node, where, "c-list", "c-list--" + variant)}>{lis}</{tag}>'
        if kind == "badge":
            variant = node.get("variant", "neutral")
            extra = {} if variant == "neutral" else {
                "color": f"var(--color-{variant})", "border-color": f"var(--color-{variant})",
                "background": f"color-mix(in srgb,var(--color-{variant}) 12%,var(--color-background))"}
            return f'<span{self.attrs(node, where, "c-badge", f"c-badge--{variant}", extra=extra)}>{e(node["text"])}</span>'
        if kind == "alert":
            variant = node.get("variant", "info")
            title = f"<strong>{e(node['title'])}</strong>" if node.get("title") else ""
            role = "alert" if variant in ("danger", "warning") else "status"
            return (f'<div{self.attrs(node, where, "c-alert", f"c-alert--{variant}", extra={"--tone": f"var(--color-{variant})"})} role="{role}">'
                    f'{title}{"<p>" + e(node["text"]) + "</p>" if node.get("text") else ""}</div>')
        if kind == "tabs":
            return (f'<div{self.attrs(node, where, "c-tabs")}><ul role="tablist">'
                    f'{self.nav_list(node["items"], SELECTED, node.get("current", 1))}</ul></div>')
        if kind == "stepper":
            current = node.get("current", 1)
            lis = "".join(f'<li class="{"is-done" if i + 1 < current else "is-current" if i + 1 == current else ""}"'
                          f'{STEP if i + 1 == current else ""}>{e(self.item(s)["text"])}</li>'
                          for i, s in enumerate(node["items"]))
            return f'<nav{self.attrs(node, where, "c-stepper")} aria-label="Étapes"><ol>{lis}</ol></nav>'
        if kind == "stat":
            delta = f'<span class="c-text--muted">{e(node["text"])}</span>' if node.get("text") else ""
            return (f'<div{self.attrs(node, where, "c-stat")}><span class="c-stat__label">{e(node["label"])}</span>'
                    f'<span class="c-stat__value">{e(node["value"])}</span>{delta}</div>')
        if kind == "search":
            label = e(node.get("placeholder", "Rechercher"))
            return (f'<form{self.attrs(node, where, "c-search")} role="search"><input class="c-input" type="search" '
                    f'aria-label="{label}" placeholder="{label}"><button class="c-button c-button--primary" '
                    f'type="submit">{e(node.get("text", "Rechercher"))}</button></form>')
        if kind == "divider":
            return f'<hr{self.attrs(node, where, "c-divider")}>'
        if kind == "spacer":
            extra = {"height": self.token(f"{where}/size", "space", node.get("size", "lg"))}
            return f'<div{self.attrs(node, where, "c-spacer", extra=extra)} aria-hidden="true"></div>'
        if kind == "footer":
            groups = ""
            for i, group in enumerate(node.get("groups", [])):
                links = "".join(f'<li><a href="{self.link(self.item(x))}">{e(self.item(x)["text"])}</a></li>'
                                for x in group.get("items", []))
                groups += f'<div><h2>{e(group.get("title", ""))}</h2><ul>{links}</ul></div>'
            groups = f'<div class="c-footer__groups">{groups}</div>' if groups else ""
            text = f'<p class="c-text--muted">{e(node["text"])}</p>' if node.get("text") else ""
            return f'<footer{self.attrs(node, where, "c-footer")}><div class="container">{groups}{text}</div></footer>'
        return ""

    def field(self, field: dict, where: str) -> str:
        e = html.escape
        self.fields += 1
        ident = f"f-{self.fields}-{re.sub(r'[^a-z0-9]+', '-', field['label'].lower()).strip('-')}"
        kind = field.get("type", "text")
        required = " required" if field.get("required") else ""
        star = " *" if field.get("required") else ""
        placeholder = f' placeholder="{e(field["placeholder"])}"' if field.get("placeholder") else ""
        full = " c-field--full" if field.get("width") == "full" else ""
        help_ = f'<span class="c-field__help">{e(field["help"])}</span>' if field.get("help") else ""
        if kind in ("select", "radio") and not field.get("options"):
            self.errors.append(f"{where} : options manquantes pour un champ {kind}")
        if kind == "checkbox":
            return (f'<div class="c-field c-field--check{full}"><input class="c-check" type="checkbox" id="{ident}"{required}>'
                    f'<label for="{ident}">{e(field["label"])}{star}</label>{help_}</div>')
        if kind == "radio":
            options = "".join(f'<label><input type="radio" name="{ident}" value="{e(o)}"> {e(o)}</label>'
                              for o in field.get("options", []))
            return (f'<fieldset class="c-field{full}"><legend>{e(field["label"])}{star}</legend>'
                    f'{options}{help_}</fieldset>')
        if kind == "select":
            options = "".join(f"<option>{e(o)}</option>" for o in field.get("options", []))
            control = f'<select class="c-select" id="{ident}"{required}>{options}</select>'
        elif kind == "textarea":
            control = f'<textarea class="c-input" id="{ident}" rows="4"{placeholder}{required}></textarea>'
        else:
            control = f'<input class="c-input" type="{kind}" id="{ident}"{placeholder}{required}>'
        return f'<div class="c-field{full}"><label for="{ident}">{e(field["label"])}{star}</label>{control}{help_}</div>'

    def build(self) -> tuple[str, str]:
        body = self.spec["body"]
        head = [n for n in body if n.get("type") == "header"]
        foot = [n for n in body if n.get("type") == "footer"]
        parts, main = [], []
        for i, node in enumerate(body):
            where = f"body/{i}"
            out = self.node(node, where)
            if node.get("type") in ("header", "footer"):
                parts.append((node["type"], out))
            elif node.get("type") == "section":
                main.append(out)
            else:
                main.append(f'<div class="container">{out}</div>')
        top = "".join(o for k, o in parts if k == "header")
        bottom = "".join(o for k, o in parts if k == "footer")
        if len(head) > 1 or len(foot) > 1:
            self.warnings.append("plus d'un header ou d'un footer dans la page")
        self.accessibility()
        lang = self.spec.get("lang", "fr")
        description = self.spec.get("description", "")
        page = (f'<!doctype html>\n<html lang="{html.escape(lang)}">\n<head>\n<meta charset="utf-8">\n'
                f'<meta name="viewport" content="width=device-width, initial-scale=1">\n'
                f'<title>{html.escape(self.spec["title"])}</title>\n'
                + (f'<meta name="description" content="{html.escape(description)}">\n' if description else "")
                + f'<link rel="stylesheet" href="{self.stem}.css">\n</head>\n<body>\n'
                f'{top}\n<main>\n{chr(10).join(main)}\n</main>\n{bottom}\n</body>\n</html>\n')
        css = "/* Généré par page_build.py (mockup-to-html) : tokens du design system, puis composants. */\n" \
              + self.ds.css_variables(self.theme) + CSS
        return page, css

    def accessibility(self) -> None:
        levels = [lvl for lvl, _ in self.headings]
        if levels.count(1) != 1:
            self.warnings.append(f"{levels.count(1)} titre(s) de niveau 1 (h1) : un seul attendu par page")
        for (before, _), (level, where) in zip(self.headings, self.headings[1:]):
            if level > before + 1:
                self.warnings.append(f"{where} : titre de niveau {level} après un niveau {before} (niveau sauté)")


# --- Cibles : Bootstrap (classes et thème), React (MUI, Ant Design) ------------------------------------

TARGETS_DIR = Path(__file__).resolve().parent / "targets"


def bootstrap(markup: str, css: str, out_dir: Path, report: dict) -> tuple[str, str]:
    """Classes des composants remplacées par celles de Bootstrap ; feuille de Bootstrap (version fixée, empreinte
    vérifiée, cache local) copiée dans vendor/ ; thème Bootstrap tiré des tokens."""
    target = json.loads((TARGETS_DIR / "bootstrap.json").read_text(encoding="utf-8"))
    package = local_tools.npm_package(target["package"])
    version, entry, _ = local_tools.PACKAGES[target["package"]]
    vendor = out_dir / "vendor" / f"bootstrap-{version}.min.css"
    vendor.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(package / entry, vendor)
    report["outputs"].append(str(vendor))
    classes = target["classes"]

    def swap(match):
        names = [n for c in match.group(1).split() for n in (classes[c].split() if c in classes else [c])]
        return f'class="{" ".join(names)}"'
    markup = re.sub(r'class="([^"]*)"', swap, markup)
    markup = markup.replace('<link rel="stylesheet" href=', f'<link rel="stylesheet" href="vendor/{vendor.name}">\n'
                                                         '<link rel="stylesheet" href=', 1)
    return markup, css + "/* Thème Bootstrap tiré des tokens (targets/bootstrap.json). */\n" + "\n".join(target["css"]) + "\n"


def write_react(target: str, spec: dict, theme: dict, page: "Page", out_dir: Path, stem: str, report: dict) -> int:
    """Page TSX, thème et App pour MUI ou Ant Design ; JSX contrôlé (balises, imports), rendu non vérifié."""
    name, code, used = react.page_file(target, spec, theme, stem, page.sources)
    errors = react.check_jsx(code, used)
    if errors:
        report["errors"] += [f"{name}.tsx : {e}" for e in errors]
        return 1
    files = {f"{name}.tsx": code, "theme.ts": react.theme_file(target, theme), "App.tsx": react.app_file(target, name)}
    for file, text in files.items():
        (out_dir / file).write_text(text, encoding="utf-8")
    report["outputs"] = [str(out_dir / f) for f in files] + [str(a) for a in page.assets]
    report["library"] = used
    report["warnings"].append(f"rendu {react.TARGETS[target]['label']} non vérifié (pas de Node ni de bundler pendant le "
                              "run) : la page HTML de la même description (--target html) sert de référence visuelle")
    return 0


# --- Rendu et comparaison -----------------------------------------------------------------------------------

def render(out_dir: Path, page_name: str, width: int, scale: float, png: Path) -> dict:
    """Capture pleine page à la largeur donnée, puis débordement à la largeur mobile ; réseau coupé."""
    from playwright.sync_api import sync_playwright

    blocked: list[str] = []

    def serve(route):
        rel = route.request.url.split("://local.myskills/", 1)[1].split("?")[0]
        path = (out_dir / rel).resolve()
        if path.is_file() and out_dir.resolve() in path.parents:
            kind = {".html": "text/html", ".css": "text/css", ".png": "image/png", ".svg": "image/svg+xml",
                    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(path.suffix.lower(),
                                                                                         "application/octet-stream")
            route.fulfill(body=path.read_bytes(), content_type=kind)
        else:
            route.fulfill(status=404, body="")

    def block(route):
        blocked.append(route.request.url[:80])
        route.abort()

    with sync_playwright() as pw:
        browser = local_tools.launch_chromium(pw)
        try:
            page = browser.new_page(viewport={"width": width, "height": 800}, device_scale_factor=scale)
            page.route("**/*", block)
            page.route("http://local.myskills/**", serve)
            page.goto(f"http://local.myskills/{page_name}", wait_until="load")
            page.screenshot(path=str(png), full_page=True)
            mobile = browser.new_page(viewport={"width": MOBILE, "height": 800})
            mobile.route("**/*", block)
            mobile.route("http://local.myskills/**", serve)
            mobile.goto(f"http://local.myskills/{page_name}", wait_until="load")
            overflow = mobile.evaluate("document.documentElement.scrollWidth > window.innerWidth + 1")
        finally:
            browser.close()
    return {"blocked": sorted(set(blocked)), "mobile_overflow": bool(overflow)}


def compare(mockup, render_png: Path, out: Path) -> dict:
    """Similarité de 0 (pas mieux qu'une page unie) à 1 (identique), zones les plus éloignées, hauteur."""
    from PIL import Image, ImageChops, ImageFilter, ImageStat

    target = mockup.convert("RGB")
    with Image.open(render_png) as shot:
        shot = shot.convert("RGB")
    if shot.width != target.width:
        shot = shot.resize((target.width, max(1, round(shot.height * target.width / shot.width))))
    height_ratio = round(shot.height / target.height, 3)
    canvas = Image.new("RGB", target.size, shot.getpixel((0, shot.height - 1)))
    canvas.paste(shot.crop((0, 0, target.width, min(shot.height, target.height))), (0, 0))
    small = (120, max(1, round(120 * target.height / target.width)))
    a = target.resize(small, Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(1))
    b = canvas.resize(small, Image.Resampling.BOX).filter(ImageFilter.GaussianBlur(1))
    diff = ImageChops.difference(a, b)
    flat = Image.new("RGB", small, tuple(round(v) for v in ImageStat.Stat(a).mean))
    mean = lambda img: sum(ImageStat.Stat(img).mean) / 3  # noqa: E731
    base = max(mean(ImageChops.difference(a, flat)), 4.0)
    similarity = round(max(0.0, 1 - mean(diff) / base), 3)
    zones = []
    cell = small[0] // 4
    for top in range(0, small[1], cell):
        for left in range(0, small[0], cell):
            box = (left, top, min(left + cell, small[0]), min(top + cell, small[1]))
            local = round(max(0.0, 1 - mean(diff.crop(box)) / base), 3)
            ratio = target.width / small[0]
            zones.append({"x": round(box[0] * ratio), "y": round(box[1] * ratio),
                          "width": round((box[2] - box[0]) * ratio), "height": round((box[3] - box[1]) * ratio),
                          "similarity": local})
    worst = sorted((z for z in zones if z["similarity"] < similarity - 0.1), key=lambda z: z["similarity"])[:3]
    # Image de relecture : maquette, rendu, écarts amplifiés en rouge.
    side = 480
    size = (side, max(1, round(side * target.height / target.width)))
    heat = ImageChops.difference(target.resize(size), canvas.resize(size)).convert("L").point(lambda v: min(255, v * 3))
    red = Image.merge("RGB", (heat, Image.new("L", size, 0), Image.new("L", size, 0)))
    faded = Image.blend(target.resize(size).convert("L").convert("RGB"), Image.new("RGB", size, "white"), 0.6)
    sheet = Image.new("RGB", (side * 3 + 16, size[1]), "white")
    for i, panel in enumerate((target.resize(size), canvas.resize(size), ImageChops.add(faded, red))):
        sheet.paste(panel, (i * (side + 8), 0))
    sheet.save(out)
    return {"similarity": similarity, "height_ratio": height_ratio, "zones": worst}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", nargs="?", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--min-similarity", type=float, default=0.6)
    parser.add_argument("--target", choices=TARGET_NAMES, default="html")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.spec), "target": args.target, "outputs": [], "library": [], "components": 0, "tokens": None, "rendered": False,
              "similarity": None, "height_ratio": None, "zones": [], "mobile_overflow": None, "blocked": [],
              "errors": [], "warnings": []}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if args.spec is None:
        report["errors"].append("description de la page manquante (PAGE.json)")
        return done(1)
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(f"{args.spec} illisible : {error}")
        return done(1)
    report["errors"] = validate(spec, __file__)
    if report["errors"]:
        return done(1)
    ds = skill_paths.load_module("design-system", "ds_build.py")
    if ds is None:
        report["errors"].append(skill_paths.absent("design-system", "ds_build.py"))
        return done(1)
    base = args.spec.parent
    tokens = {}
    if spec.get("tokens"):
        path = base / spec["tokens"]
        report["tokens"] = str(path)
        try:
            tokens = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            report["errors"].append(f"tokens : {spec['tokens']} illisible ({error}) ; ds_extract.py --draft l'écrit")
            return done(1)
        report["errors"] += ds.tokens_errors(tokens)
        if report["errors"]:
            return done(1)
    theme, _ = ds.complete(tokens)
    if spec.get("max_width"):
        theme["max_width"] = spec["max_width"]
    mockup = None
    if spec.get("mockup"):
        try:
            from PIL import Image
            mockup = Image.open(base / spec["mockup"])
            mockup.load()
        except ImportError:
            report["errors"].append("Pillow manquant : lancez ce script avec `uv run`")
            return done(1)
        except OSError as error:
            report["errors"].append(f"mockup : {spec['mockup']} illisible ({error})")
            return done(1)
    out_dir = args.out_dir or base
    stem = args.spec.stem
    page = Page(spec, theme, ds, base, out_dir, stem, mockup)
    out_dir.mkdir(parents=True, exist_ok=True)
    markup, css = page.build()
    report["components"] = page.count
    report["errors"] += page.errors
    report["warnings"] += page.warnings
    if report["errors"]:
        for asset in page.assets:
            if asset.parent.name == "assets" and asset.name.startswith(stem + "-"):
                asset.unlink(missing_ok=True)
        return done(1)
    if args.target.startswith("react-"):
        return done(write_react(args.target, spec, theme, page, out_dir, stem, report))
    if args.target == "bootstrap":
        try:
            markup, css = bootstrap(markup, css, out_dir, report)
        except local_tools.PackageError as error:
            report["errors"].append(f"Bootstrap : {error}")
            return done(1)
    (out_dir / f"{stem}.html").write_text(markup, encoding="utf-8")
    (out_dir / f"{stem}.css").write_text(css, encoding="utf-8")
    report["outputs"] = [str(out_dir / f"{stem}.html"), str(out_dir / f"{stem}.css")] + \
        [str(a) for a in page.assets] + report["outputs"]
    if args.no_render:
        report["warnings"].append("rendu non vérifié (--no-render)")
        return done(0)
    scale = spec.get("scale", 1)
    width = spec.get("width") or (round(mockup.width / scale) if mockup else 1280)
    png = out_dir / f"{stem}.render.png"
    try:
        shot = render(out_dir, f"{stem}.html", width, scale, png)
    except ImportError:
        report["warnings"].append("rendu non vérifié : Playwright manquant, lancez ce script avec `uv run`")
        return done(0)
    except local_tools.PackageError as error:
        report["warnings"].append(f"rendu non vérifié : {error}")
        return done(0)
    report.update(rendered=True, mobile_overflow=shot["mobile_overflow"], blocked=shot["blocked"])
    report["outputs"].append(str(png))
    if shot["blocked"]:
        report["warnings"].append(f"{len(shot['blocked'])} requête(s) externe(s) bloquée(s) : {shot['blocked'][0]}")
    if shot["mobile_overflow"]:
        report["warnings"].append(f"débordement horizontal à {MOBILE} px (mobile) : colonnes ou tableau trop larges")
    if mockup is not None:
        compare_png = out_dir / f"{stem}.compare.png"
        result = compare(mockup, png, compare_png)
        report.update(similarity=result["similarity"], height_ratio=result["height_ratio"], zones=result["zones"])
        report["outputs"].append(str(compare_png))
        if result["similarity"] < args.min_similarity:
            report["warnings"].append(f"similarité {result['similarity']} sous {args.min_similarity} : regardez "
                                      f"{compare_png.name} et corrigez les zones signalées")
        if not 0.85 <= result["height_ratio"] <= 1.15:
            report["warnings"].append(f"hauteur du rendu {result['height_ratio']} fois celle de la maquette")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
