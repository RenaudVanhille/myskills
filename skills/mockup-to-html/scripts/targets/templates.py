"""Cibles Vue et Angular de page_build.py : la page en composant Vue 3 avec Vuetify, ou en composant Angular
standalone avec Angular Material.

Comme pour React (react.py), le même arbre de composants devient un composant
qui n'emploie que ceux de la bibliothèque, et les tokens du design system
deviennent son thème et un objet `tokens` partagé. Le gabarit est un arbre
d'éléments (El) rendu par le script : textes et attributs échappés, liaisons
écrites dans la syntaxe de la cible (`:prop` pour Vue, `[prop]` pour
Angular). Une nouvelle bibliothèque s'ajoute par une entrée de TARGETS et une
classe d'émission.
"""

import html
import json
import re

from react import pascal

TARGETS = {
    "vue-vuetify": {"label": "Vue 3 avec Vuetify 3",
                    "provides": ["header", "nav", "breadcrumb", "button", "buttons", "card", "form", "table", "list",
                                 "badge", "alert", "tabs", "stepper", "search", "divider", "image"]},
    "angular-material": {"label": "Angular avec Angular Material",
                         "provides": ["header", "nav", "button", "buttons", "card", "form", "table", "list", "badge",
                                      "tabs", "stepper", "search", "divider"]},
}
SEVERITY = {"info": "info", "success": "success", "warning": "warning", "danger": "error"}
VOID = {"img", "input", "hr", "br"}
IDENT = re.compile(r"^[A-Za-z_]\w*$")


def esc_text(value) -> str:
    """Texte d'un gabarit : HTML échappé, accolades neutralisées (interpolation Vue et Angular)."""
    return html.escape(str(value), quote=False).replace("{", "&#123;").replace("}", "&#125;")


def esc_attr(value) -> str:
    """Valeur d'attribut entre guillemets doubles : les apostrophes des liaisons restent lisibles."""
    return str(value).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


class El:
    def __init__(self, tag: str, attrs: dict | None = None, *children, text=None):
        self.tag, self.attrs = tag, {k: v for k, v in (attrs or {}).items() if v is not None}
        self.children = [c for c in children if c is not None]
        self.text = text

    def render(self, depth: int = 0) -> str:
        pad = "  " * depth
        attrs = "".join(f" {k}" if v is True else f' {k}="{esc_attr(v)}"' for k, v in self.attrs.items())
        if self.tag in VOID:
            return f"{pad}<{self.tag}{attrs} />\n"
        if self.text is not None and not self.children:
            return f"{pad}<{self.tag}{attrs}>{esc_text(self.text)}</{self.tag}>\n"
        if not self.children:
            return f"{pad}<{self.tag}{attrs}></{self.tag}>\n"
        inner = (f"{pad}  {esc_text(self.text)}\n" if self.text is not None else "") + \
            "".join(c.render(depth + 1) for c in self.children)
        return f"{pad}<{self.tag}{attrs}>\n{inner}{pad}</{self.tag}>\n"


def js(value) -> str:
    """Valeur littérale dans une expression de gabarit (entre guillemets doubles) : chaînes en apostrophes."""
    if isinstance(value, str):
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"
    if isinstance(value, list):
        return "[" + ", ".join(js(v) for v in value) + "]"
    if isinstance(value, dict):
        keys = [k if IDENT.match(k) else js(k) for k in value]
        return "{ " + ", ".join(f"{k}: {js(v)}" for k, v in zip(keys, value.values())) + " }"
    return json.dumps(value)


class Base:
    bind = ":"  # préfixe d'une liaison d'attribut

    def __init__(self, theme: dict, images: dict):
        self.theme, self.images = theme, images
        self.used: set[str] = set()

    def items(self, values) -> list[dict]:
        return [{"text": v} if isinstance(v, str) else v for v in values or []]

    def color(self, value) -> str:
        return js(value) if value.startswith("#") else f"tokens.colors[{js(value)}]"

    def px(self, kind: str, key) -> str:
        return f"{self.theme[kind][key]:g}px"

    def style(self, node: dict, extra: dict | None = None, axis: bool = False) -> dict:
        """Attribut de style lié (couleurs des tokens) ou statique (dimensions)."""
        rules = {k: js(v) for k, v in (extra or {}).items()}
        if node.get("background"):
            rules["background"] = self.color(node["background"])
        ink = node.get("color") or (f"on-{node['background']}" if node.get("background")
                                    and f"on-{node['background']}" in self.theme["colors"] else None)
        if ink:
            rules["color"] = self.color(ink)
        if node.get("padding"):
            rules["paddingBlock" if axis else "padding"] = js(self.px("spacing", node["padding"]))
        if node.get("align"):
            rules["textAlign"] = js(node["align"])
        if not rules:
            return {}
        body = ", ".join(f"{k}: {v}" for k, v in rules.items())
        return {f"{self.bind}style" if self.bind == ":" else "[ngStyle]": f"{{ {body} }}"}

    def kids(self, node: dict) -> list:
        return [self.node(c) for c in node.get("children", [])]

    def node(self, node: dict):
        method = getattr(self, f"n_{node['type']}", None)
        return method(node) if method else None

    def size(self, node: dict) -> dict:
        return {"fontSize": self.px("font_sizes", node["size"])} if node.get("size") else {}

    # communs : balises HTML et styles
    def n_spacer(self, node):
        return El("div", {"style": f"height: {self.px('spacing', node.get('size', 'lg'))}", "aria-hidden": "true"})

    def n_box(self, node):
        extra = {"height": f"{node.get('height', 16)}px"}
        if node.get("width"):
            extra["width"] = f"{node['width']}px"
        if node.get("radius"):
            extra["borderRadius"] = self.px("radii", node["radius"])
        return El("div", {"aria-hidden": "true", **self.style(node, extra)})

    def n_section(self, node):
        padding = {} if node.get("padding") else {"paddingBlock": self.px("spacing", "2xl") if "2xl" in self.theme["spacing"] else "48px"}
        inner = El("div", {"class": "page-container"}, *self.kids(node)) if node.get("width") != "full" else None
        return El("section", self.style(node, padding, True), *([inner] if inner else self.kids(node)))

    def n_heading(self, node):
        level = node.get("level", 2)
        return El(f"h{level}", self.style(node, self.size(node)), text=node["text"])

    def n_text(self, node):
        extra = self.size(node)
        if node.get("bold"):
            extra["fontWeight"] = "700"
        if node.get("muted"):
            extra["color"] = None
        attrs = self.style(node, {k: v for k, v in extra.items() if v})
        if node.get("muted"):
            attrs["class"] = "text-muted"
        return El("p", attrs, text=node["text"])

    def n_link(self, node):
        return El("a", {"href": node.get("href", "#")}, text=node["text"])

    def breadcrumb_html(self, node):
        items = self.items(node["items"])
        lis = [El("li", {}, El("a", {"href": i.get("href", "#")}, text=i["text"])) for i in items[:-1]]
        lis += [El("li", {"aria-current": "page"}, text=items[-1]["text"])] if items else []
        return El("nav", {"aria-label": "Fil d'Ariane", "class": "breadcrumb"}, El("ol", {}, *lis))

    def footer_groups(self, node, link_tag="a"):
        groups = [El("div", {}, El("h2", {"class": "footer-title"}, text=g.get("title", "")),
                     El("ul", {}, *[El("li", {}, El(link_tag, {"href": i.get("href", "#")}, text=i["text"]))
                                    for i in self.items(g.get("items"))]))
                  for g in node.get("groups", [])]
        note = El("p", {"class": "text-muted"}, text=node["text"]) if node.get("text") else None
        bg = self.color(node["background"]) if node.get("background") else "tokens.colors.surface"
        style = {f"{self.bind}style" if self.bind == ":" else "[ngStyle]": f"{{ background: {bg}, paddingBlock: '48px' }}"}
        return El("footer", style, El("div", {"class": "page-container"},
                                      El("div", {"class": "footer-groups"}, *groups) if groups else None, note))

    def stat_html(self, node):
        return El("div", {"class": "stat"}, El("span", {"class": "text-muted"}, text=node["label"]),
                  El("strong", {"class": "stat-value"}, text=node["value"]),
                  El("span", {"class": "text-muted"}, text=node["text"]) if node.get("text") else None)

    def image_src(self, node):
        return self.images.get(id(node))


class Vuetify(Base):
    bind = ":"

    def tag(self, name: str, attrs=None, *children, text=None) -> El:
        self.used.add(name)
        return El(name, attrs, *children, text=text)

    def gap(self, node, default="lg") -> int:
        return max(0, min(16, round(self.theme["spacing"].get(node.get("gap") or default, 24) / 4)))

    def n_row(self, node):
        cols = node.get("columns") or [1] * len(node.get("children", []))
        total = sum(cols) or 1
        align = {"start": "start", "center": "center", "end": "end", "stretch": "stretch"}.get(node.get("valign"))
        cells = [self.tag("v-col", {"cols": "12", "md": str(max(1, round(12 * c / total)))}, self.node(child))
                 for c, child in zip(cols, node.get("children", []))]
        return self.tag("v-row", {"align": align, **self.style(node)}, *cells)

    def n_grid(self, node):
        span = str(max(1, 12 // node.get("columns", 3)))
        return self.tag("v-row", self.style(node), *[self.tag("v-col", {"cols": "12", "md": span}, self.node(c))
                                                     for c in node.get("children", [])])

    def n_stack(self, node):
        return El("div", {"class": f"d-flex flex-column ga-{self.gap(node, 'md')}", **self.style(node)}, *self.kids(node))

    def n_header(self, node):
        src = self.image_src(node)
        logo = El("img", {"src": src, "alt": node.get("alt", ""), "height": "36"}) if src else None
        nav = El("nav", {"aria-label": "Navigation principale", "class": "d-flex ga-6 mx-auto"},
                 *[El("a", {"href": i.get("href", "#"), "class": "text-decoration-none text-high-emphasis"}, text=i["text"])
                   for i in self.items(node.get("items"))])
        actions = [self.n_button({"text": a["text"], "variant": a.get("variant") or (
            "primary" if n == len(node["actions"]) - 1 else "ghost")}) for n, a in enumerate(self.items(node.get("actions")))]
        return self.tag("v-toolbar", {"color": "background", "border": "b", "class": "px-6", "height": "64"},
                        logo, El("strong", {"class": "text-h6 ms-2"}, text=node.get("text", "")), nav, *actions)

    def n_nav(self, node):
        vertical = node.get("variant") == "vertical"
        return self.tag("v-list", {"density": "compact", "nav": True} if vertical else {"class": "d-flex"},
                        *[self.tag("v-list-item", {"href": i.get("href", "#"), "title": i["text"]})
                          for i in self.items(node["items"])])

    def n_breadcrumb(self, node):
        return self.tag("v-breadcrumbs", {":items": js([i["text"] for i in self.items(node["items"])]), "class": "pa-0"})

    def n_button(self, node):
        variant = node.get("variant", "primary")
        attrs = {"variant": {"primary": "flat", "secondary": "flat", "danger": "flat", "outline": "outlined"}.get(variant, "text"),
                 "color": {"secondary": "secondary", "danger": "error"}.get(variant, "primary"),
                 "size": {"sm": "small", "lg": "large"}.get(node.get("size")), "href": node.get("href")}
        return self.tag("v-btn", attrs, text=node["text"])

    def n_buttons(self, node):
        items = self.items(node["items"])
        return El("div", {"class": "d-flex flex-wrap ga-2"}, *[self.n_button({"text": i["text"], "href": i.get("href"),
                  "variant": i.get("variant") or ("primary" if n == len(items) - 1 else "secondary")}) for n, i in enumerate(items)])

    def n_image(self, node):
        src = self.image_src(node)
        if not src:
            return self.tag("v-sheet", {"color": "surface", "height": str(node.get("height", 160)), "role": "img",
                                        "aria-label": node.get("alt", "Image"), "class": "d-flex align-center justify-center"},
                            text=node.get("alt", "Image"))
        return self.tag("v-img", {"src": src, "alt": node.get("alt", ""), "height": str(node["height"]) if node.get("height") else None,
                                  "cover": True})

    def n_card(self, node):
        src = self.image_src(node)
        parts = [self.tag("v-img", {"src": src, "alt": node.get("alt", ""), "cover": True}) if src else None]
        if node.get("title"):
            parts.append(self.tag("v-card-title", {"tag": "h3"}, text=node["title"]))
        body = ([El("p", {"class": "text-medium-emphasis"}, text=node["text"])] if node.get("text") else []) + self.kids(node)
        if body:
            parts.append(self.tag("v-card-text", {}, *body))
        if node.get("actions"):
            parts.append(self.tag("v-card-actions", {}, *[self.n_button({"text": a["text"], "variant": a.get("variant") or "outline"})
                                                          for a in self.items(node["actions"])]))
        return self.tag("v-card", {"variant": "outlined", "class": "h-100", **self.style(node)}, *parts)

    def field(self, f: dict, n: int):
        kind = f.get("type", "text")
        common = {"label": f["label"], "placeholder": f.get("placeholder"), "hint": f.get("help"),
                  "persistent-hint": True if f.get("help") else None,
                  ":rules": "[(v) => !!v || 'Champ obligatoire']" if f.get("required") else None}
        if kind == "select":
            return self.tag("v-select", {**common, ":items": js(f.get("options", []))})
        if kind == "textarea":
            return self.tag("v-textarea", {**common, "rows": "4"})
        if kind == "checkbox":
            return self.tag("v-checkbox", {"label": f["label"], ":rules": common[":rules"], "hide-details": "auto"})
        if kind == "radio":
            return self.tag("v-radio-group", {"label": f["label"], "inline": True},
                            *[self.tag("v-radio", {"label": o, "value": o}) for o in f.get("options", [])])
        if kind == "file":
            return self.tag("v-file-input", common)
        return self.tag("v-text-field", {**common, "type": kind if kind != "text" else None})

    def n_form(self, node):
        span = "6" if node.get("columns") == 2 else "12"
        cols = [self.tag("v-col", {"cols": "12", "md": "12" if f.get("width") == "full" else span}, self.field(f, n))
                for n, f in enumerate(node["fields"])]
        return self.tag("v-form", self.style(node),
                        El("h2", {"class": "text-h5 mb-4"}, text=node["title"]) if node.get("title") else None,
                        self.tag("v-row", {"dense": True}, *cols),
                        self.tag("v-btn", {"type": "submit", "color": "primary", "variant": "flat"}, text=node.get("submit", "Valider")))

    def n_table(self, node):
        head = El("thead", {}, El("tr", {}, *[El("th", {}, text=h) for h in node.get("headers", [])])) if node.get("headers") else None
        body = El("tbody", {}, *[El("tr", {}, *[El("td", {}, text=str(c)) for c in row]) for row in node["rows"]])
        return self.tag("v-table", {"density": "compact", "striped": "even" if node.get("variant") == "striped" else None}, head, body)

    def n_list(self, node):
        return self.tag("v-list", {"density": "compact"}, *[self.tag("v-list-item", {"title": i["text"],
                        "prepend-icon": "mdi-check" if node.get("variant") == "check" else None}) for i in self.items(node["items"])])

    def n_badge(self, node):
        color = {"neutral": None, "danger": "error"}.get(node.get("variant", "neutral"), node.get("variant"))
        return self.tag("v-chip", {"size": "small", "color": color, "variant": "outlined"}, text=node["text"])

    def n_alert(self, node):
        return self.tag("v-alert", {"type": SEVERITY[node.get("variant", "info")], "variant": "tonal",
                                    "title": node.get("title"), "text": node.get("text")})

    def n_tabs(self, node):
        return self.tag("v-tabs", {":model-value": str(node.get("current", 1) - 1), "color": "primary"},
                        *[self.tag("v-tab", {}, text=i["text"]) for i in self.items(node["items"])])

    def n_stepper(self, node):
        return self.tag("v-stepper", {":items": js([i["text"] for i in self.items(node["items"])]),
                                      ":model-value": str(node.get("current", 1)), "hide-actions": True, "flat": True})

    def n_stat(self, node):
        return self.stat_html(node)

    def n_search(self, node):
        label = node.get("placeholder", "Rechercher")
        return El("form", {"role": "search", "class": "d-flex ga-2"},
                  self.tag("v-text-field", {"type": "search", "label": label, "density": "compact", "hide-details": True}),
                  self.tag("v-btn", {"type": "submit", "color": "primary", "variant": "flat"}, text=node.get("text", "Rechercher")))

    def n_divider(self, node):
        return self.tag("v-divider")

    def n_footer(self, node):
        return self.footer_groups(node)


class Material(Base):
    bind = "["

    MODULES = {"mat-toolbar": "MatToolbarModule", "mat-button": "MatButtonModule", "mat-card": "MatCardModule",
               "mat-form-field": "MatFormFieldModule", "matInput": "MatInputModule", "mat-select": "MatSelectModule",
               "mat-checkbox": "MatCheckboxModule", "mat-radio": "MatRadioModule", "mat-list": "MatListModule",
               "mat-chip": "MatChipsModule", "mat-tab": "MatTabsModule", "mat-stepper": "MatStepperModule",
               "mat-divider": "MatDividerModule", "ngStyle": "NgStyle"}

    def use(self, module: str):
        self.used.add(module)

    def style(self, node, extra=None, axis=False):
        attrs = super().style(node, extra, axis)
        if attrs:
            self.use("ngStyle")
        return attrs

    def gap(self, node, default="lg") -> str:
        return self.px("spacing", node.get("gap") or default) if (node.get("gap") or default) in self.theme["spacing"] else "24px"

    def n_row(self, node):
        cols = node.get("columns") or [1] * len(node.get("children", []))
        align = {"start": "start", "center": "center", "end": "end"}.get(node.get("valign"), "stretch")
        style = f"grid-template-columns: {' '.join(f'{c:g}fr' for c in cols)}; gap: {self.gap(node)}; align-items: {align}"
        return El("div", {"class": "grid", "style": style, **self.style(node)}, *self.kids(node))

    def n_grid(self, node):
        style = f"grid-template-columns: repeat({node.get('columns', 3)}, minmax(0, 1fr)); gap: {self.gap(node)}"
        return El("div", {"class": "grid", "style": style, **self.style(node)}, *self.kids(node))

    def n_stack(self, node):
        return El("div", {"class": "stack", "style": f"gap: {self.gap(node, 'md')}", **self.style(node)}, *self.kids(node))

    def n_header(self, node):
        self.use("mat-toolbar")
        src = self.image_src(node)
        logo = El("img", {"src": src, "alt": node.get("alt", ""), "height": "36"}) if src else None
        nav = El("nav", {"aria-label": "Navigation principale", "class": "toolbar-nav"},
                 *[El("a", {"mat-button": True, "href": i.get("href", "#")}, text=i["text"]) for i in self.items(node.get("items"))])
        if node.get("items"):
            self.use("mat-button")
        actions = [self.n_button({"text": a["text"], "variant": a.get("variant") or (
            "primary" if n == len(node["actions"]) - 1 else "ghost")}) for n, a in enumerate(self.items(node.get("actions")))]
        return El("mat-toolbar", {"class": "page-toolbar"}, logo, El("strong", {"class": "brand"}, text=node.get("text", "")),
                  nav, *actions)

    def n_nav(self, node):
        self.use("mat-list")
        return El("mat-nav-list", {}, *[El("a", {"mat-list-item": True, "href": i.get("href", "#")}, text=i["text"])
                                        for i in self.items(node["items"])])

    def n_breadcrumb(self, node):
        return self.breadcrumb_html(node)

    def n_button(self, node):
        self.use("mat-button")
        variant = node.get("variant", "primary")
        kind = {"primary": "mat-flat-button", "secondary": "mat-flat-button", "danger": "mat-flat-button",
                "outline": "mat-stroked-button"}.get(variant, "mat-button")
        cls = {"secondary": "btn-secondary", "danger": "btn-danger"}.get(variant)
        tag = "a" if node.get("href") else "button"
        return El(tag, {kind: True, "class": cls, "href": node.get("href"), "type": "button" if tag == "button" else None},
                  text=node["text"])

    def n_buttons(self, node):
        items = self.items(node["items"])
        return El("div", {"class": "actions"}, *[self.n_button({"text": i["text"], "href": i.get("href"),
                  "variant": i.get("variant") or ("primary" if n == len(items) - 1 else "secondary")}) for n, i in enumerate(items)])

    def n_image(self, node):
        src = self.image_src(node)
        if not src:
            return El("div", {"class": "placeholder", "role": "img", "aria-label": node.get("alt", "Image"),
                              "style": f"min-height: {node.get('height', 160)}px"}, text=node.get("alt", "Image"))
        return El("img", {"src": src, "alt": node.get("alt", ""), "class": "cover",
                          "style": f"height: {node['height']}px" if node.get("height") else None})

    def n_card(self, node):
        self.use("mat-card")
        src = self.image_src(node)
        parts = [El("img", {"mat-card-image": True, "src": src, "alt": node.get("alt", "")}) if src else None]
        if node.get("title"):
            parts.append(El("mat-card-header", {}, El("mat-card-title", {}, text=node["title"])))
        body = ([El("p", {"class": "text-muted"}, text=node["text"])] if node.get("text") else []) + self.kids(node)
        if body:
            parts.append(El("mat-card-content", {}, *body))
        if node.get("actions"):
            parts.append(El("mat-card-actions", {}, *[self.n_button({"text": a["text"], "variant": a.get("variant") or "outline"})
                                                      for a in self.items(node["actions"])]))
        return El("mat-card", {"appearance": "outlined", "class": "full-height", **self.style(node)}, *parts)

    def field(self, f: dict, n: int):
        kind = f.get("type", "text")
        required = True if f.get("required") else None
        hint = El("mat-hint", {}, text=f["help"]) if f.get("help") else None
        if kind == "checkbox":
            self.use("mat-checkbox")
            return El("mat-checkbox", {"required": required}, text=f["label"])
        if kind == "radio":
            self.use("mat-radio")
            return El("div", {"class": "field"}, El("label", {"class": "field-label"}, text=f["label"]),
                      El("mat-radio-group", {"aria-label": f["label"]},
                         *[El("mat-radio-button", {"value": o}, text=o) for o in f.get("options", [])]))
        if kind == "file":
            # matInput refuse type="file" : champ natif stylé comme un bouton Material, sans module de plus.
            self.files = getattr(self, "files", 0) + 1
            ident = f"fichier-{self.files}"
            return El("div", {"class": "field"}, El("label", {"class": "field-label", "for": ident}, text=f["label"]),
                      El("input", {"id": ident, "type": "file", "class": "file-input", "required": required}),
                      El("small", {"class": "text-muted"}, text=f["help"]) if f.get("help") else None)
        self.use("mat-form-field")
        if kind == "select":
            self.use("mat-select")
            control = El("mat-select", {"required": required}, *[El("mat-option", {"value": o}, text=o) for o in f.get("options", [])])
        else:
            self.use("matInput")
            if kind == "textarea":
                control = El("textarea", {"matInput": True, "rows": "4", "placeholder": f.get("placeholder"), "required": required})
            else:
                control = El("input", {"matInput": True, "type": kind, "placeholder": f.get("placeholder"), "required": required})
        return El("mat-form-field", {"appearance": "outline", "class": "full-width"}, El("mat-label", {}, text=f["label"]),
                  control, hint)

    def n_form(self, node):
        cols = 2 if node.get("columns") == 2 else 1
        fields = [El("div", {"class": "span-all" if f.get("width") == "full" else None}, self.field(f, n))
                  for n, f in enumerate(node["fields"])]
        self.use("mat-button")
        return El("form", {"class": "form", **self.style(node)},
                  El("h2", {}, text=node["title"]) if node.get("title") else None,
                  El("div", {"class": "grid", "style": f"grid-template-columns: repeat({cols}, minmax(0, 1fr)); gap: 0 16px"}, *fields),
                  El("button", {"mat-flat-button": True, "type": "submit"}, text=node.get("submit", "Valider")))

    def n_table(self, node):
        head = El("thead", {}, El("tr", {}, *[El("th", {}, text=h) for h in node.get("headers", [])])) if node.get("headers") else None
        body = El("tbody", {}, *[El("tr", {}, *[El("td", {}, text=str(c)) for c in row]) for row in node["rows"]])
        return El("table", {"class": "table" + (" striped" if node.get("variant") == "striped" else "")}, head, body)

    def n_list(self, node):
        self.use("mat-list")
        return El("mat-list", {}, *[El("mat-list-item", {}, text=i["text"]) for i in self.items(node["items"])])

    def n_badge(self, node):
        self.use("mat-chip")
        return El("mat-chip-set", {}, El("mat-chip", {"class": f"chip-{node.get('variant', 'neutral')}"}, text=node["text"]))

    def n_alert(self, node):
        variant = node.get("variant", "info")
        return El("div", {"class": f"alert alert-{variant}", "role": "alert" if variant in ("danger", "warning") else "status"},
                  El("strong", {}, text=node["title"]) if node.get("title") else None,
                  El("p", {}, text=node["text"]) if node.get("text") else None)

    def n_tabs(self, node):
        self.use("mat-tab")
        return El("mat-tab-group", {"[selectedIndex]": str(node.get("current", 1) - 1)},
                  *[El("mat-tab", {"label": i["text"]}) for i in self.items(node["items"])])

    def n_stepper(self, node):
        self.use("mat-stepper")
        return El("mat-stepper", {"[selectedIndex]": str(node.get("current", 1) - 1), "labelPosition": "bottom"},
                  *[El("mat-step", {"label": i["text"]}) for i in self.items(node["items"])])

    def n_stat(self, node):
        return self.stat_html(node)

    def n_search(self, node):
        self.use("mat-form-field")
        self.use("matInput")
        self.use("mat-button")
        label = node.get("placeholder", "Rechercher")
        return El("form", {"role": "search", "class": "search"},
                  El("mat-form-field", {"appearance": "outline", "class": "full-width", "subscriptSizing": "dynamic"},
                     El("mat-label", {}, text=label), El("input", {"matInput": True, "type": "search"})),
                  El("button", {"mat-flat-button": True, "type": "submit"}, text=node.get("text", "Rechercher")))

    def n_divider(self, node):
        self.use("mat-divider")
        return El("mat-divider")

    def n_footer(self, node):
        self.use("ngStyle")
        return self.footer_groups(node)


def tokens_ts(theme: dict) -> str:
    tokens = {"colors": theme["colors"], "fonts": theme["fonts"], "fontSizes": theme["font_sizes"],
              "spacing": theme["spacing"], "radii": theme["radii"], "shadows": theme["shadows"],
              "lineHeight": theme["line_height"], "maxWidth": theme["max_width"]}
    return ("// Généré par page_build.py (mockup-to-html) depuis les tokens du design system : régénérer plutôt que modifier.\n"
            f"export const tokens = {json.dumps(tokens, ensure_ascii=False, indent=2)} as const;\n")


PAGE_CSS = """.page-container { max-width: {max}px; margin: 0 auto; padding: 0 24px; display: flex; flex-direction: column; gap: 24px; }
.text-muted { color: {muted}; }
a:not([class]) { color: {link}; }
footer a { color: inherit; }
.stat { display: flex; flex-direction: column; gap: 4px; }
.stat-value { font-size: {stat}px; }
.breadcrumb ol { display: flex; gap: 8px; list-style: none; margin: 0; padding: 0; color: {muted}; }
.breadcrumb li + li::before { content: "/"; margin-right: 8px; }
.footer-groups { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 24px; margin-bottom: 24px; }
.footer-groups ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.footer-title { font-size: 14px; margin: 0 0 8px; }
h1, h2, h3, h4, p { margin: 0; }
"""


def page_css(theme: dict, extra: str = "") -> str:
    return (PAGE_CSS.replace("{max}", f"{theme['max_width']:g}").replace("{muted}", theme["colors"]["muted"])
            .replace("{link}", theme["colors"].get("link", theme["colors"]["primary"]))
            .replace("{stat}", f"{theme['font_sizes'].get('2xl', 32):g}") + extra)


MATERIAL_CSS = """.grid { display: grid; }
.stack { display: flex; flex-direction: column; }
.actions, .search { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; }
.search .full-width { flex: 1; }
.full-width { width: 100%; }
.full-height { height: 100%; }
.span-all { grid-column: 1 / -1; }
.field { display: flex; flex-direction: column; gap: 4px; margin-bottom: 16px; }
.field-label { color: {muted}; font-size: 14px; }
.file-input { font: inherit; }
.form { display: flex; flex-direction: column; gap: 8px; }
.page-toolbar { gap: 16px; border-bottom: 1px solid {border}; background: {bg}; }
.toolbar-nav { flex: 1; display: flex; justify-content: center; gap: 8px; }
.cover { width: 100%; object-fit: cover; display: block; }
.placeholder { background: {surface}; display: flex; align-items: center; justify-content: center; }
.table { width: 100%; border-collapse: collapse; }
.table th, .table td { text-align: left; padding: 8px 16px; border-bottom: 1px solid {border}; }
.table.striped tbody tr:nth-child(odd) { background: {surface}; }
.alert { padding: 16px; border-radius: 8px; border-left: 4px solid; }
{alerts}.btn-secondary { --mat-button-filled-container-color: {secondary}; --mat-button-filled-label-text-color: {onsecondary};
  --mdc-filled-button-container-color: {secondary}; --mdc-filled-button-label-text-color: {onsecondary}; }
.btn-danger { --mat-button-filled-container-color: {danger}; --mat-button-filled-label-text-color: {ondanger};
  --mdc-filled-button-container-color: {danger}; --mdc-filled-button-label-text-color: {ondanger}; }
.form > button { align-self: flex-start; }
@media (max-width: 767px) { .grid { grid-template-columns: 1fr !important; } .toolbar-nav { display: none; } }
"""


def material_css(theme: dict) -> str:
    c = theme["colors"]
    alerts = "".join(f".alert-{v} {{ border-color: {c[v]}; background: color-mix(in srgb, {c[v]} 10%, {c['background']}); }}\n"
                     for v in ("info", "success", "warning", "danger"))
    out = MATERIAL_CSS
    for key, value in {"muted": c["muted"], "border": c["border"], "bg": c["background"], "surface": c["surface"], "secondary": c["secondary"],
                       "onsecondary": c.get("on-secondary", "#ffffff"), "danger": c["danger"],
                       "ondanger": c.get("on-danger", "#ffffff"), "alerts": alerts}.items():
        out = out.replace("{" + key + "}", value)
    return out


def files_for(target: str, spec: dict, theme: dict, stem: str, images: dict) -> tuple[dict, list[str]]:
    """Fichiers de la page (nom -> texte) et composants de la bibliothèque employés."""
    name = f"{pascal(stem)}Page"
    if target == "vue-vuetify":
        emitter = Vuetify(theme, images)
        body = "".join(el.render(2) for el in map(emitter.node, spec["body"]) if el is not None)
        needs_tokens = "tokens." in body
        script = ('<script setup lang="ts">\nimport { tokens } from "./tokens";\n</script>\n\n' if needs_tokens else "")
        sfc = (f"<!-- Généré par page_build.py (mockup-to-html) depuis {stem}.json : régénérer plutôt que modifier. -->\n"
               f"{script}<template>\n  <div class=\"page\">\n{body}  </div>\n</template>\n\n<style scoped>\n"
               f"{page_css(theme)}</style>\n")
        c = theme["colors"]
        colors = {"primary": c["primary"], "secondary": c["secondary"], "error": c["danger"], "warning": c["warning"],
                  "info": c["info"], "success": c["success"], "background": c["background"], "surface": c["background"],
                  "on-primary": c.get("on-primary", "#ffffff"), "on-secondary": c.get("on-secondary", "#ffffff")}
        palette = "".join(f"          {json.dumps(k)}: {json.dumps(v)},\n" for k, v in colors.items())
        plugin = ("// Généré par page_build.py (mockup-to-html) : thème Vuetify tiré des tokens du design system.\n"
                  "import \"@mdi/font/css/materialdesignicons.css\";\nimport \"vuetify/styles\";\nimport { createVuetify } from \"vuetify\";\n"
                  "import * as components from \"vuetify/components\";\nimport * as directives from \"vuetify/directives\";\n\n"
                  "export default createVuetify({\n  components,\n  directives,\n  theme: {\n    defaultTheme: \"designSystem\",\n"
                  "    themes: {\n      designSystem: {\n        dark: false,\n        colors: {\n" + palette +
                  "        },\n      },\n    },\n  },\n"
                  f"  defaults: {{ VBtn: {{ rounded: {theme['radii'].get('md', 8):g} }} }},\n}});\n")
        app = ("<script setup lang=\"ts\">\n" f"import {name} from \"./{name}.vue\";\n</script>\n\n<template>\n  <v-app>\n"
               f"    <v-main>\n      <{name} />\n    </v-main>\n  </v-app>\n</template>\n")
        main = ("import { createApp } from \"vue\";\nimport App from \"./App.vue\";\nimport vuetify from \"./vuetify\";\n\n"
                "createApp(App).use(vuetify).mount(\"#app\");\n")
        return {f"{name}.vue": sfc, "vuetify.ts": plugin, "tokens.ts": tokens_ts(theme), "App.vue": app, "main.ts": main}, \
            sorted(emitter.used)
    emitter = Material(theme, images)
    body = "".join(el.render(1) for el in map(emitter.node, spec["body"]) if el is not None)
    selector = "app-" + re.sub(r"(?<!^)(?=[A-Z])", "-", name).lower()
    file = re.sub(r"-page$", "", selector[4:]) + "-page"
    modules = sorted({Material.MODULES[m] for m in emitter.used})
    lines = [f"import {{ {m} }} from \"{'@angular/common' if m == 'NgStyle' else '@angular/material/' + MODULE_PATH[m]}\";"
             for m in modules]
    needs_tokens = "tokens." in body
    component = ("// Généré par page_build.py (mockup-to-html) : régénérer plutôt que modifier.\n"
                 "import { Component } from \"@angular/core\";\n" + "\n".join(lines) + "\n"
                 + ("import { tokens } from \"./tokens\";\n" if needs_tokens else "") + "\n"
                 f"@Component({{\n  selector: \"{selector}\",\n  standalone: true,\n  imports: [{', '.join(modules)}],\n"
                 f"  templateUrl: \"./{file}.component.html\",\n  styleUrl: \"./{file}.component.css\",\n}})\n"
                 f"export class {name}Component {{\n" + ("  readonly tokens = tokens;\n" if needs_tokens else "") + "}\n")
    template = (f"<!-- Généré par page_build.py (mockup-to-html) depuis {stem}.json : régénérer plutôt que modifier. -->\n"
                f"<div class=\"page\">\n{body}</div>\n")
    c, f = theme["colors"], theme["fonts"]
    styles = ("// Généré par page_build.py (mockup-to-html) : thème Angular Material tiré des tokens du design system.\n"
              "@use \"@angular/material\" as mat;\n\nhtml {\n  color-scheme: light;\n"
              f"  @include mat.theme((color: (theme-type: light), typography: {json.dumps(f['body'].split(',')[0].strip().strip(chr(39) + chr(34)))}, density: 0));\n}}\n\n"
              "// Couleurs exactes du design system, après le thème pour l'emporter.\nhtml {\n"
              f"  --mat-sys-primary: {c['primary']};\n  --mat-sys-on-primary: {c.get('on-primary', '#ffffff')};\n"
              f"  --mat-sys-secondary: {c['secondary']};\n  --mat-sys-error: {c['danger']};\n"
              f"  --mat-sys-surface: {c['background']};\n  --mat-sys-on-surface: {c['text']};\n"
              f"  --mat-sys-on-surface-variant: {c['muted']};\n  --mat-sys-outline: {c['border']};\n"
              f"  --mat-sys-outline-variant: {c['border']};\n  --mat-sys-corner-medium: {theme['radii'].get('md', 8):g}px;\n}}\n\n"
              f"body {{ margin: 0; font-family: {f['body']}; color: {c['text']}; background: {c['background']}; }}\n")
    return {f"{file}.component.ts": component, f"{file}.component.html": template,
            f"{file}.component.css": page_css(theme, material_css(theme)), "tokens.ts": tokens_ts(theme),
            "styles.scss": styles}, modules


MODULE_PATH = {"MatToolbarModule": "toolbar", "MatButtonModule": "button", "MatCardModule": "card",
               "MatFormFieldModule": "form-field", "MatInputModule": "input", "MatSelectModule": "select",
               "MatCheckboxModule": "checkbox", "MatRadioModule": "radio", "MatListModule": "list",
               "MatChipsModule": "chips", "MatTabsModule": "tabs", "MatStepperModule": "stepper",
               "MatDividerModule": "divider"}

TAG = re.compile(r"<(/?)([A-Za-z][\w.-]*)((?:\s+[^<>]*?)?)\s*(/?)>")


def check_template(text: str) -> list[str]:
    """Balises équilibrées dans un gabarit Vue ou Angular (commentaires et éléments vides exclus)."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"<(script|style)\b.*?</\1>", "", text, flags=re.S)
    stack, errors = [], []
    for closing, name, _, selfclose in TAG.findall(text):
        if selfclose or name.lower() in VOID:
            continue
        if closing:
            if not stack or stack[-1] != name:
                errors.append(f"balise </{name}> sans ouverture correspondante")
                break
            stack.pop()
        else:
            stack.append(name)
    if stack and not errors:
        errors.append(f"balise <{stack[-1]}> non fermée")
    return errors
