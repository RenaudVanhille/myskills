"""Cibles React de page_build.py : code TSX d'une page avec MUI (Material UI) ou Ant Design.

Le même arbre de composants que la page HTML devient un composant React qui
n'emploie que ceux de la bibliothèque, et les tokens du design system
deviennent son thème (createTheme pour MUI, ConfigProvider pour antd) et un
objet `tokens` partagé. Textes et valeurs passent par json.dumps : aucune
chaîne n'est collée telle quelle dans le code. Une nouvelle bibliothèque
s'ajoute par une entrée de TARGETS et ses fonctions.
"""

import json
import re

import graphics

TARGETS = {
    "react-mui": {"module": "@mui/material", "label": "MUI (Material UI) 7",
                  "provides": ["header", "nav", "breadcrumb", "button", "buttons", "card", "form", "table", "list",
                               "badge", "alert", "tabs", "stepper", "search", "divider", "image", "sidebar", "avatar",
                               "pagination", "modal"]},
    "react-antd": {"module": "antd", "label": "Ant Design 5",
                   "provides": ["header", "nav", "breadcrumb", "button", "buttons", "card", "form", "table", "list",
                                "badge", "alert", "tabs", "stepper", "stat", "search", "divider", "image", "sidebar",
                                "avatar", "pagination", "modal"]},
}
SEVERITY = {"info": "info", "success": "success", "warning": "warning", "danger": "error"}


def js(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def text(value) -> str:
    return "{" + js(value) + "}"


def pascal(stem: str) -> str:
    words = re.findall(r"[A-Za-z0-9]+", stem.encode("ascii", "ignore").decode()) or ["Page"]
    name = "".join(w[:1].upper() + w[1:] for w in words)
    return name if name[0].isalpha() else f"P{name}"


class Emitter:
    def __init__(self, target: str, theme: dict, images: dict):
        self.target, self.theme, self.images = target, theme, images
        self.used: set[str] = set()
        self.mui = target == "react-mui"

    # --- valeurs des tokens
    def color(self, value) -> str | None:
        if value is None:
            return None
        if isinstance(value, str) and value.startswith("#"):
            return js(value)
        return f"tokens.colors[{js(value)}]"

    def space(self, value) -> str | None:
        return None if value is None else js(f"{self.theme['spacing'][value]:g}px")

    def ink(self, node: dict) -> str | None:
        if "color" in node:
            return self.color(node["color"])
        name = f"on-{node.get('background')}"
        return self.color(name) if name in self.theme["colors"] else None

    def tag(self, name: str) -> str:
        self.used.add(name.split(".")[0])
        return name

    def style(self, node: dict, extra: dict | None = None, padding_axis: bool = False) -> str:
        rules = dict(extra or {})
        if node.get("background"):
            rules["background" if not self.mui else "bgcolor"] = self.color(node["background"])
        ink = self.ink(node)
        if ink:
            rules["color"] = ink
        if node.get("padding"):
            key = ("py" if self.mui else "paddingBlock") if padding_axis else ("p" if self.mui else "padding")
            rules[key] = self.space(node["padding"])
        if node.get("align"):
            rules["textAlign"] = js(node["align"])
        if not rules:
            return ""
        body = ", ".join(f"{k if re.match(r'^[A-Za-z]+$', k) else js(k)}: {v}" for k, v in rules.items())
        return f" {'sx' if self.mui else 'style'}={{{{ {body} }}}}"

    def items(self, values) -> list[dict]:
        return [{"text": v} if isinstance(v, str) else v for v in values or []]

    def kids(self, node: dict, depth: int) -> str:
        return "".join(self.node(c, depth) for c in node.get("children", []))

    # --- nœuds
    def node(self, node: dict, depth: int) -> str:
        pad = "  " * depth
        kind = node["type"]
        method = getattr(self, f"{'mui' if self.mui else 'antd'}_{kind}", None) or getattr(self, f"any_{kind}", None)
        out = method(node, depth) if method else ""
        return "".join(f"{pad}{line}\n" for line in out.splitlines() if line.strip()) if "\n" in out else (
            f"{pad}{out}\n" if out else "")

    def block(self, opening: str, inner: str, closing: str) -> str:
        return f"{opening}\n{inner}{closing}" if inner else f"{opening}{closing}"

    def indent(self, code: str, n: int = 1) -> str:
        return "".join("  " * n + line + "\n" for line in code.splitlines() if line.strip())

    def image_src(self, node: dict) -> str | None:
        return self.images.get(id(node))

    # Composants communs (balises HTML et Box/div)
    def any_spacer(self, node, depth):
        size = self.space(node.get("size", "lg"))
        return f"<{self.tag('Box')} sx={{{{ height: {size} }}}} />" if self.mui else f"<div style={{{{ height: {size} }}}} />"

    def any_box(self, node, depth):
        extra = {"height": js(f"{node.get('height', 16)}px")}
        if node.get("width"):
            extra["width"] = js(f"{node['width']}px")
        if node.get("radius"):
            extra["borderRadius"] = js(f"{self.theme['radii'][node['radius']]:g}px")
        return (f"<{self.tag('Box')}{self.style(node, extra)} />" if self.mui
                else f"<div aria-hidden{self.style(node, extra)} />")

    def svg_icon(self, name: str, size: float = 20, label: str | None = None) -> str:
        return graphics.write(graphics.icon(name, size, label), jsx=True)

    def any_icon(self, node, depth):
        src = self.image_src(node)
        if src:
            return f"<img src={js(src)} alt={js(node.get('label', ''))} style={{{{ height: 24 }}}} />"
        size = self.theme["font_sizes"].get(node.get("size", "lg"), 20)
        return f"<span style={{{{ display: \"inline-flex\", lineHeight: 0 }}}}>{self.svg_icon(node['name'], size, node.get('label'))}</span>"

    def any_graph(self, node, depth):
        colors = graphics.theme_colors(self.theme)
        svg = graphics.write(graphics.chart(node.get("variant", "bar"), self.items(node["items"]), colors,
                                            node.get("height", 240), node.get("title", "")), jsx=True)
        caption = f"<figcaption style={{{{ fontWeight: 600 }}}}>{text(node['title'])}</figcaption>" if node.get("title") else ""
        return f"<figure style={{{{ margin: 0 }}}}>\n  {caption}\n  {svg}\n</figure>" if caption else f"<figure style={{{{ margin: 0 }}}}>{svg}</figure>"

    def initials(self, node) -> str:
        return graphics.initials(node.get("text", ""))

    # --- MUI
    def mui_sidebar(self, node, depth):
        width = node.get("width", 240)
        bg = self.color(node.get("background")) or "\"background.default\""
        src = self.image_src(node)
        logo = f"<{self.tag('Box')} component=\"img\" src={js(src)} alt={js(node.get('alt', ''))} sx={{{{ height: 36 }}}} />" if src else ""
        brand = (f"  <{self.tag('Stack')} direction=\"row\" spacing={{1}} alignItems=\"center\">{logo}<{self.tag('Typography')} variant=\"h6\" "
                 f"sx={{{{ fontWeight: 700 }}}}>{text(node.get('text', ''))}</Typography></Stack>\n") if (src or node.get("text")) else ""
        rows = ""
        for item in self.items(node["items"]):
            mark = f"<{self.tag('ListItemIcon')} sx={{{{ minWidth: 32 }}}}>{self.svg_icon(item['icon'], 18)}</ListItemIcon>" if item.get("icon") else ""
            selected = " selected" if item.get("active") else ""
            rows += (f"    <{self.tag('ListItemButton')} component=\"a\" href={js(item.get('href', '#'))}{selected}>{mark}"
                     f"<{self.tag('ListItemText')} primary={js(item['text'])} /></ListItemButton>\n")
        nav = f"  <{self.tag('List')} component=\"nav\" aria-label=\"Navigation principale\">\n{rows}  </List>\n"
        main = self.indent(self.kids(node, 0), 2)
        return (f"<{self.tag('Box')} sx={{{{ display: \"flex\", minHeight: \"100vh\" }}}}>\n"
                f"  <Box component=\"aside\" sx={{{{ width: {width}, flexShrink: 0, bgcolor: {bg}, borderRight: 1, borderColor: \"divider\", p: 2 }}}}>\n"
                f"{self.indent(brand + nav)}  </Box>\n  <Box component=\"main\" sx={{{{ flex: 1, minWidth: 0 }}}}>\n{main}  </Box>\n</Box>")

    def mui_avatar(self, node, depth):
        size = {"sm": 28, "md": 40, "lg": 64}.get(node.get("size", "md"), 40)
        src = self.image_src(node)
        if src:
            return f"<{self.tag('Avatar')} src={js(src)} alt={js(node.get('alt', node.get('text', '')))} sx={{{{ width: {size}, height: {size} }}}} />"
        return (f"<{self.tag('Avatar')} aria-label={js(node.get('text', ''))} sx={{{{ width: {size}, height: {size}, bgcolor: \"primary.main\" }}}}>"
                f"{text(self.initials(node))}</Avatar>")

    def mui_pagination(self, node, depth):
        return f"<{self.tag('Pagination')} count={{{node['pages']}}} page={{{node.get('current', 1)}}} color=\"primary\" shape=\"rounded\" />"

    def mui_modal(self, node, depth):
        body = f"    <{self.tag('DialogContentText')}>{text(node['text'])}</DialogContentText>\n" if node.get("text") else ""
        body += self.indent(self.kids(node, 0), 2)
        actions = "".join("    " + self.mui_button({"text": a["text"], "variant": a.get("variant") or (
            "primary" if n == len(node["actions"]) - 1 else "ghost")}, 0) + "\n" for n, a in enumerate(self.items(node.get("actions"))))
        foot = f"  <{self.tag('DialogActions')}>\n{actions}  </DialogActions>\n" if actions else ""
        return (f"<{self.tag('Dialog')} open aria-labelledby=\"dialog-title\">\n"
                f"  <{self.tag('DialogTitle')} id=\"dialog-title\">{text(node['title'])}</DialogTitle>\n"
                f"  <{self.tag('DialogContent')}>\n{body}  </DialogContent>\n{foot}</Dialog>")

    def mui_section(self, node, depth):
        inner = self.indent(self.kids(node, 0), 2)
        container = f"  <{self.tag('Container')} maxWidth=\"lg\">\n  <{self.tag('Stack')} spacing={{3}}>\n{inner}  </Stack>\n  </Container>\n" \
            if node.get("width") != "full" else inner
        padding = {} if node.get("padding") else {"py": js(f"{self.theme['spacing'].get('2xl', 48):g}px")}
        return f"<Box component=\"section\"{self.style(node, padding, True)}>\n{container}</Box>".replace(
            "<Box", f"<{self.tag('Box')}", 1)

    def mui_row(self, node, depth):
        cols = node.get("columns") or [1] * len(node.get("children", []))
        total = sum(cols) or 1
        cells = "".join(f"  <{self.tag('Grid')} size={{{{ xs: 12, md: {max(1, round(12 * c / total))} }}}}>\n"
                        f"{self.indent(self.node(child, 0), 2)}  </Grid>\n"
                        for c, child in zip(cols, node.get("children", [])))
        gap = node.get("gap")
        spacing = f" spacing={{{round(self.theme['spacing'][gap] / 8, 2):g}}}" if gap else " spacing={3}"
        align = {"start": "flex-start", "center": "center", "end": "flex-end", "stretch": "stretch"}.get(node.get("valign"))
        return f"<Grid container{spacing}{f' alignItems={js(align)}' if align else ''}{self.style(node)}>\n{cells}</Grid>"

    def mui_grid(self, node, depth):
        size = max(1, 12 // node.get("columns", 3))
        cells = "".join(f"  <{self.tag('Grid')} size={{{{ xs: 12, md: {size} }}}}>\n{self.indent(self.node(c, 0), 2)}  </Grid>\n"
                        for c in node.get("children", []))
        gap = node.get("gap")
        spacing = f" spacing={{{round(self.theme['spacing'][gap] / 8, 2):g}}}" if gap else " spacing={3}"
        return f"<Grid container{spacing}{self.style(node)}>\n{cells}</Grid>"

    def mui_stack(self, node, depth):
        gap = node.get("gap")
        spacing = f" spacing={{{round(self.theme['spacing'][gap] / 8, 2):g}}}" if gap else " spacing={2}"
        return self.block(f"<{self.tag('Stack')}{spacing}{self.style(node)}>", self.indent(self.kids(node, 0)), "</Stack>")

    def mui_header(self, node, depth):
        parts = []
        src = self.image_src(node)
        if src:
            parts.append(f"<{self.tag('Box')} component=\"img\" src={js(src)} alt={js(node.get('alt', ''))} sx={{{{ height: 36 }}}} />")
        parts.append(f"<{self.tag('Typography')} variant=\"h6\" component=\"a\" href=\"#\" sx={{{{ fontWeight: 700, color: \"inherit\", textDecoration: \"none\" }}}}>{text(node.get('text', ''))}</Typography>")
        links = "".join(f"  <{self.tag('Link')} href={js(i.get('href', '#'))} underline=\"hover\" color=\"inherit\">{text(i['text'])}</Link>\n"
                        for i in self.items(node.get("items")))
        parts.append(f"<{self.tag('Stack')} component=\"nav\" aria-label=\"Navigation principale\" direction=\"row\" spacing={{3}} sx={{{{ flex: 1, justifyContent: \"center\" }}}}>\n{links}</Stack>")
        for i, a in enumerate(self.items(node.get("actions"))):
            parts.append(self.mui_button({"text": a["text"], "variant": a.get("variant") or ("primary" if i == len(node["actions"]) - 1 else "ghost"),
                                          "href": a.get("href")}, 0))
        inner = self.indent("\n".join(parts), 2)
        return (f"<{self.tag('AppBar')} position=\"static\" color=\"inherit\" elevation={{0}} sx={{{{ borderBottom: 1, borderColor: \"divider\" }}}}>\n"
                f"  <{self.tag('Toolbar')} sx={{{{ gap: 3 }}}}>\n{inner}  </Toolbar>\n</AppBar>")

    def mui_nav(self, node, depth):
        direction = "column" if node.get("variant") == "vertical" else "row"
        links = "".join(f"  <{self.tag('Link')} href={js(i.get('href', '#'))} underline=\"hover\">{text(i['text'])}</Link>\n"
                        for i in self.items(node["items"]))
        return f"<{self.tag('Stack')} component=\"nav\" direction={js(direction)} spacing={{2}}>\n{links}</Stack>"

    def mui_breadcrumb(self, node, depth):
        items = self.items(node["items"])
        links = "".join(f"  <{self.tag('Link')} href={js(i.get('href', '#'))} underline=\"hover\" color=\"inherit\">{text(i['text'])}</Link>\n"
                        for i in items[:-1])
        last = f"  <{self.tag('Typography')} color=\"text.primary\">{text(items[-1]['text'])}</Typography>\n" if items else ""
        return f"<{self.tag('Breadcrumbs')} aria-label=\"Fil d'Ariane\">\n{links}{last}</Breadcrumbs>"

    def mui_heading(self, node, depth):
        level = node.get("level", 2)
        extra = {"fontSize": js(f"{self.theme['font_sizes'][node['size']]:g}px")} if node.get("size") else {}
        return f"<{self.tag('Typography')} variant=\"h{level}\" component=\"h{level}\"{self.style(node, extra)}>{text(node['text'])}</Typography>"

    def mui_text(self, node, depth):
        extra = {"fontSize": js(f"{self.theme['font_sizes'][node['size']]:g}px")} if node.get("size") else {}
        if node.get("bold"):
            extra["fontWeight"] = "700"
        muted = ' color="text.secondary"' if node.get("muted") else ""
        return f"<{self.tag('Typography')}{muted}{self.style(node, extra)}>{text(node['text'])}</Typography>"

    def mui_link(self, node, depth):
        return f"<{self.tag('Link')} href={js(node.get('href', '#'))}>{text(node['text'])}</Link>"

    def mui_button(self, node, depth):
        variant = node.get("variant", "primary")
        kind = {"primary": "contained", "secondary": "contained", "danger": "contained", "outline": "outlined"}.get(variant, "text")
        color = {"secondary": "secondary", "danger": "error"}.get(variant, "primary")
        size = f" size={js({'sm': 'small', 'lg': 'large'}[node['size']])}" if node.get("size") in ("sm", "lg") else ""
        href = f" href={js(node['href'])}" if node.get("href") else ""
        return f"<{self.tag('Button')} variant=\"{kind}\" color=\"{color}\"{size}{href}>{text(node['text'])}</Button>"

    def mui_buttons(self, node, depth):
        items = self.items(node["items"])
        inner = "".join("  " + self.mui_button({"text": i["text"], "variant": i.get("variant") or (
            "primary" if n == len(items) - 1 else "secondary"), "href": i.get("href")}, 0) + "\n" for n, i in enumerate(items))
        return f"<{self.tag('Stack')} direction=\"row\" spacing={{1}} useFlexGap sx={{{{ flexWrap: \"wrap\" }}}}>\n{inner}</Stack>"

    def mui_image(self, node, depth):
        src = self.image_src(node)
        height = f", height: {node['height']}" if node.get("height") else ""
        if not src:
            return (f"<{self.tag('Box')} role=\"img\" aria-label={js(node.get('alt', 'Image'))} sx={{{{ bgcolor: \"action.hover\", minHeight: {node.get('height', 160)}, "
                    f"display: \"flex\", alignItems: \"center\", justifyContent: \"center\" }}}}>{text(node.get('alt', 'Image'))}</Box>")
        width = node["width"] if isinstance(node.get("width"), int) else "\"100%\""
        return f"<{self.tag('Box')} component=\"img\" src={js(src)} alt={js(node.get('alt', ''))} sx={{{{ width: {width}, objectFit: \"cover\"{height} }}}} />"

    def mui_card(self, node, depth):
        src = self.image_src(node)
        media = f"  <{self.tag('CardMedia')} component=\"img\" image={js(src)} alt={js(node.get('alt', ''))} />\n" if src else ""
        body = ""
        if node.get("title"):
            body += f"  <{self.tag('Typography')} variant=\"h6\" component=\"h3\">{text(node['title'])}</Typography>\n"
        if node.get("text"):
            body += f"  <{self.tag('Typography')} color=\"text.secondary\">{text(node['text'])}</Typography>\n"
        body += self.indent(self.kids(node, 0))
        actions = ""
        if node.get("actions"):
            buttons = "".join("  " + self.mui_button({"text": a["text"], "variant": a.get("variant") or "outline"}, 0) + "\n"
                              for a in self.items(node["actions"]))
            actions = f"  <{self.tag('CardActions')}>\n{buttons}  </CardActions>\n"
        return (f"<{self.tag('Card')} variant=\"outlined\" sx={{{{ height: \"100%\" }}}}{self.style(node)}>\n{media}"
                f"  <{self.tag('CardContent')}>\n{self.indent(body)}  </CardContent>\n{actions}</Card>").replace(" sx={{ height: \"100%\" }} sx=", " sx=")

    def mui_field(self, field: dict) -> str:
        kind = field.get("type", "text")
        req = " required" if field.get("required") else ""
        helper = f" helperText={js(field['help'])}" if field.get("help") else ""
        ph = f" placeholder={js(field['placeholder'])}" if field.get("placeholder") else ""
        if kind == "checkbox":
            return (f"<{self.tag('FormControlLabel')} control={{<{self.tag('Checkbox')}{req} />}} label={js(field['label'])} />")
        if kind == "switch":
            return (f"<{self.tag('FormControlLabel')} control={{<{self.tag('Switch')}{req} />}} label={js(field['label'])} />")
        if kind == "radio":
            opts = "".join(f"  <FormControlLabel value={js(o)} control={{<{self.tag('Radio')} />}} label={js(o)} />\n"
                           for o in field.get("options", []))
            self.used.add("FormControlLabel")
            return (f"<{self.tag('FormControl')}{req}>\n  <{self.tag('FormLabel')}>{text(field['label'])}</FormLabel>\n"
                    f"  <{self.tag('RadioGroup')} row>\n{self.indent(opts)}  </RadioGroup>\n</FormControl>")
        if kind == "select":
            opts = "".join(f"  <{self.tag('MenuItem')} value={js(o)}>{text(o)}</MenuItem>\n" for o in field.get("options", []))
            return f"<{self.tag('TextField')} select label={js(field['label'])} defaultValue=\"\" fullWidth{req}{helper}>\n{opts}</TextField>"
        extra = " multiline minRows={4}" if kind == "textarea" else (f" type={js(kind)}" if kind != "text" else "")
        shrink = " slotProps={{ inputLabel: { shrink: true } }}" if kind in ("date", "file") else ""
        return f"<{self.tag('TextField')} label={js(field['label'])} fullWidth{extra}{ph}{req}{helper}{shrink} />"

    def mui_form(self, node, depth):
        cols = 6 if node.get("columns") == 2 else 12
        title = f"  <{self.tag('Typography')} variant=\"h5\" component=\"h2\">{text(node['title'])}</Typography>\n" if node.get("title") else ""
        fields = "".join(f"  <{self.tag('Grid')} size={{{{ xs: 12, md: {12 if f.get('width') == 'full' else cols} }}}}>\n"
                         f"{self.indent(self.mui_field(f), 2)}  </Grid>\n" for f in node["fields"])
        submit = f"  <{self.tag('Button')} type=\"submit\" variant=\"contained\">{text(node.get('submit', 'Valider'))}</Button>\n"
        return (f"<{self.tag('Stack')} component=\"form\" spacing={{2}}{self.style(node)}>\n{title}"
                f"  <Grid container spacing={{2}}>\n{self.indent(fields)}  </Grid>\n{submit}</Stack>")

    def mui_table(self, node, depth):
        head = "".join(f"<{self.tag('TableCell')}>{text(h)}</TableCell>" for h in node.get("headers", []))
        rows = "".join(f"    <TableRow>{''.join(f'<TableCell>{text(str(c))}</TableCell>' for c in row)}</TableRow>\n"
                       for row in node["rows"])
        self.used.update({"TableContainer", "Table", "TableHead", "TableBody", "TableRow", "TableCell"})
        head_block = f"  <TableHead>\n    <TableRow>{head}</TableRow>\n  </TableHead>\n" if head else ""
        return (f"<TableContainer>\n<Table size=\"small\">\n{head_block}  <TableBody>\n{rows}  </TableBody>\n</Table>\n</TableContainer>")

    def mui_list(self, node, depth):
        items = "".join(f"  <{self.tag('ListItem')}><{self.tag('ListItemText')} primary={js(i['text'])} /></ListItem>\n"
                        for i in self.items(node["items"]))
        return f"<{self.tag('List')} dense>\n{items}</List>"

    def mui_badge(self, node, depth):
        color = {"neutral": "default", "danger": "error"}.get(node.get("variant", "neutral"), node.get("variant"))
        return f"<{self.tag('Chip')} label={js(node['text'])} size=\"small\" color={js(color)} variant=\"outlined\" />"

    def mui_alert(self, node, depth):
        title = f"<{self.tag('AlertTitle')}>{text(node['title'])}</AlertTitle>" if node.get("title") else ""
        return f"<{self.tag('Alert')} severity={js(SEVERITY[node.get('variant', 'info')])}>{title}{text(node.get('text', ''))}</Alert>"

    def mui_tabs(self, node, depth):
        tabs = "".join(f"  <{self.tag('Tab')} label={js(i['text'])} />\n" for i in self.items(node["items"]))
        return f"<{self.tag('Tabs')} value={{{node.get('current', 1) - 1}}}>\n{tabs}</Tabs>"

    def mui_stepper(self, node, depth):
        steps = "".join(f"  <{self.tag('Step')}><{self.tag('StepLabel')}>{text(i['text'])}</StepLabel></Step>\n"
                        for i in self.items(node["items"]))
        return f"<{self.tag('Stepper')} activeStep={{{node.get('current', 1) - 1}}} alternativeLabel>\n{steps}</Stepper>"

    def mui_stat(self, node, depth):
        delta = f"  <Typography variant=\"body2\" color=\"text.secondary\">{text(node['text'])}</Typography>\n" if node.get("text") else ""
        return (f"<{self.tag('Stack')} spacing={{0.5}}>\n  <{self.tag('Typography')} variant=\"body2\" color=\"text.secondary\">{text(node['label'])}</Typography>\n"
                f"  <Typography variant=\"h4\" component=\"p\">{text(node['value'])}</Typography>\n{delta}</Stack>")

    def mui_search(self, node, depth):
        label = node.get("placeholder", "Rechercher")
        return (f"<{self.tag('Stack')} component=\"form\" role=\"search\" direction=\"row\" spacing={{1}}>\n"
                f"  <{self.tag('TextField')} type=\"search\" size=\"small\" fullWidth placeholder={js(label)} slotProps={{{{ htmlInput: {{ \"aria-label\": {js(label)} }} }}}} />\n"
                f"  <{self.tag('Button')} type=\"submit\" variant=\"contained\">{text(node.get('text', 'Rechercher'))}</Button>\n</Stack>")

    def mui_divider(self, node, depth):
        return f"<{self.tag('Divider')} />"

    def mui_footer(self, node, depth):
        groups = ""
        for g in node.get("groups", []):
            links = "".join(f"      <Link href={js(i.get('href', '#'))} color=\"inherit\" underline=\"hover\">{text(i['text'])}</Link>\n"
                            for i in self.items(g.get("items")))
            self.used.update({"Link", "Grid", "Stack", "Typography"})
            groups += (f"  <Grid size={{{{ xs: 12, sm: 6, md: 3 }}}}>\n    <Typography variant=\"subtitle2\" component=\"h2\" gutterBottom>{text(g.get('title', ''))}</Typography>\n"
                       f"    <Stack spacing={{0.5}}>\n{links}    </Stack>\n  </Grid>\n")
        grid = f"  <Grid container spacing={{3}} sx={{{{ mb: 3 }}}}>\n{self.indent(groups)}  </Grid>\n" if groups else ""
        note = f"  <{self.tag('Typography')} variant=\"body2\" color=\"text.secondary\">{text(node['text'])}</Typography>\n" if node.get("text") else ""
        self.used.update({"Box", "Container"})
        bg = self.color(node["background"]) if node.get("background") else "tokens.colors.surface"
        return (f"<Box component=\"footer\" sx={{{{ bgcolor: {bg}, py: \"48px\" }}}}>\n  <Container maxWidth=\"lg\">\n"
                f"{self.indent(grid + note)}  </Container>\n</Box>")

    # --- Ant Design
    def antd_section(self, node, depth):
        inner = self.indent(self.kids(node, 0), 2)
        padding = {} if node.get("padding") else {"paddingBlock": js(f"{self.theme['spacing'].get('2xl', 48):g}px")}
        body = (f"  <div style={{{{ maxWidth: tokens.maxWidth, margin: \"0 auto\", padding: \"0 24px\" }}}}>\n"
                f"  <{self.tag('Flex')} vertical gap={{24}}>\n{inner}  </Flex>\n  </div>\n") if node.get("width") != "full" else inner
        return f"<section{self.style(node, padding, True)}>\n{body}</section>"

    def antd_row(self, node, depth):
        cols = node.get("columns") or [1] * len(node.get("children", []))
        total = sum(cols) or 1
        cells = "".join(f"  <{self.tag('Col')} xs={{24}} md={{{max(1, round(24 * c / total))}}}>\n{self.indent(self.node(child, 0), 2)}  </Col>\n"
                        for c, child in zip(cols, node.get("children", [])))
        gap = self.theme["spacing"].get(node.get("gap") or "lg", 24)
        align = {"start": "top", "center": "middle", "end": "bottom", "stretch": "stretch"}.get(node.get("valign"))
        return f"<{self.tag('Row')} gutter={{[{gap:g}, {gap:g}]}}{f' align={js(align)}' if align else ''}{self.style(node)}>\n{cells}</Row>"

    def antd_grid(self, node, depth):
        span = max(1, 24 // node.get("columns", 3))
        gap = self.theme["spacing"].get(node.get("gap") or "lg", 24)
        cells = "".join(f"  <{self.tag('Col')} xs={{24}} md={{{span}}}>\n{self.indent(self.node(c, 0), 2)}  </Col>\n"
                        for c in node.get("children", []))
        return f"<{self.tag('Row')} gutter={{[{gap:g}, {gap:g}]}}{self.style(node)}>\n{cells}</Row>"

    def antd_stack(self, node, depth):
        gap = self.theme["spacing"].get(node.get("gap") or "md", 16)
        return self.block(f"<{self.tag('Flex')} vertical gap={{{gap:g}}}{self.style(node)}>", self.indent(self.kids(node, 0)), "</Flex>")

    def antd_header(self, node, depth):
        src = self.image_src(node)
        logo = f"<img src={js(src)} alt={js(node.get('alt', ''))} style={{{{ height: 36 }}}} />" if src else ""
        items = js([{"key": str(n), "label": i["text"]} for n, i in enumerate(self.items(node.get("items")))])
        actions = "".join("    " + self.antd_button({"text": a["text"], "variant": a.get("variant") or (
            "primary" if n == len(node["actions"]) - 1 else "ghost")}, 0) + "\n" for n, a in enumerate(self.items(node.get("actions"))))
        self.used.update({"Flex", "Menu", "Typography", "Space"})
        return (f"<header style={{{{ borderBottom: `1px solid ${{tokens.colors.border}}`, background: tokens.colors.background }}}}>\n"
                f"  <Flex align=\"center\" gap={{24}} style={{{{ maxWidth: tokens.maxWidth, margin: \"0 auto\", padding: \"0 24px\", minHeight: 64 }}}}>\n"
                f"    <Flex align=\"center\" gap={{8}}>{logo}<Typography.Text strong style={{{{ fontSize: 20 }}}}>{text(node.get('text', ''))}</Typography.Text></Flex>\n"
                f"    <Menu mode=\"horizontal\" items={{{items}}} style={{{{ flex: 1, borderBottom: 0, justifyContent: \"center\" }}}} aria-label=\"Navigation principale\" />\n"
                f"    <Space>\n{actions}    </Space>\n  </Flex>\n</header>")

    def antd_sidebar(self, node, depth):
        width = node.get("width", 240)
        selected = [str(n) for n, i in enumerate(self.items(node["items"])) if i.get("active")]
        entries = ", ".join("{ key: " + js(str(n)) + ", label: " + js(i["text"])
                            + (f", icon: {self.svg_icon(i['icon'], 18)}" if i.get("icon") else "") + " }"
                            for n, i in enumerate(self.items(node["items"])))
        src = self.image_src(node)
        logo = f"<img src={js(src)} alt={js(node.get('alt', ''))} style={{{{ height: 36 }}}} />" if src else ""
        brand = (f"    <Flex align=\"center\" gap={{8}} style={{{{ padding: 16 }}}}>{logo}<Typography.Text strong style={{{{ fontSize: 20 }}}}>"
                 f"{text(node.get('text', ''))}</Typography.Text></Flex>\n") if (src or node.get("text")) else ""
        bg = self.color(node["background"]) if node.get("background") else "tokens.colors.surface"
        self.used.update({"Layout", "Menu", "Flex", "Typography"})
        main = self.indent(self.kids(node, 0), 2)
        return (f"<Layout style={{{{ minHeight: \"100vh\" }}}}>\n"
                f"  <Layout.Sider width={{{width}}} theme=\"light\" style={{{{ background: {bg} }}}}>\n{brand}"
                f"    <Menu mode=\"inline\" selectedKeys={{{js(selected)}}} items={{[{entries}]}} style={{{{ background: \"transparent\", borderInlineEnd: 0 }}}} aria-label=\"Navigation principale\" />\n"
                f"  </Layout.Sider>\n  <Layout.Content style={{{{ background: tokens.colors.background }}}}>\n{main}  </Layout.Content>\n</Layout>")

    def antd_avatar(self, node, depth):
        size = {"sm": 28, "md": 40, "lg": 64}.get(node.get("size", "md"), 40)
        src = self.image_src(node)
        if src:
            return f"<{self.tag('Avatar')} size={{{size}}} src={js(src)} alt={js(node.get('alt', node.get('text', '')))} />"
        return (f"<{self.tag('Avatar')} size={{{size}}} aria-label={js(node.get('text', ''))} style={{{{ background: tokens.colors.primary }}}}>"
                f"{text(self.initials(node))}</Avatar>")

    def antd_pagination(self, node, depth):
        return (f"<{self.tag('Pagination')} current={{{node.get('current', 1)}}} total={{{node['pages'] * 10}}} "
                f"showSizeChanger={{false}} />")

    def antd_modal(self, node, depth):
        body = f"  <{self.tag('Typography')}.Paragraph>{text(node['text'])}</Typography.Paragraph>\n" if node.get("text") else ""
        body += self.indent(self.kids(node, 0))
        actions = "".join("    " + self.antd_button({"text": a["text"], "variant": a.get("variant") or (
            "primary" if n == len(node["actions"]) - 1 else "ghost")}, 0) + "\n" for n, a in enumerate(self.items(node.get("actions"))))
        if actions:
            self.used.add("Flex")
            body += f"  <Flex justify=\"end\" gap={{8}}>\n{actions}  </Flex>\n"
        return f"<{self.tag('Modal')} open title={js(node['title'])} footer={{null}} closable>\n{body}</Modal>"

    def antd_nav(self, node, depth):
        items = js([{"key": str(n), "label": i["text"]} for n, i in enumerate(self.items(node["items"]))])
        mode = "inline" if node.get("variant") == "vertical" else "horizontal"
        return f"<{self.tag('Menu')} mode={js(mode)} items={{{items}}} />"

    def antd_breadcrumb(self, node, depth):
        return f"<{self.tag('Breadcrumb')} items={{{js([{'title': i['text']} for i in self.items(node['items'])])}}} />"

    def antd_heading(self, node, depth):
        level = min(5, node.get("level", 2))
        extra = {"fontSize": js(f"{self.theme['font_sizes'][node['size']]:g}px")} if node.get("size") else {}
        extra["margin"] = "0"
        extra.setdefault("color", "\"inherit\"")
        self.used.add("Typography")
        return f"<Typography.Title level={{{level}}}{self.style(node, extra)}>{text(node['text'])}</Typography.Title>"

    def antd_text(self, node, depth):
        extra = {"fontSize": js(f"{self.theme['font_sizes'][node['size']]:g}px")} if node.get("size") else {}
        extra["margin"] = "0"
        if not node.get("muted"):
            extra.setdefault("color", "\"inherit\"")
        muted = ' type="secondary"' if node.get("muted") else ""
        strong = " strong" if node.get("bold") else ""
        self.used.add("Typography")
        return f"<Typography.Paragraph{muted}{self.style(node, extra)}>{'<Typography.Text strong>' if strong else ''}{text(node['text'])}{'</Typography.Text>' if strong else ''}</Typography.Paragraph>"

    def antd_link(self, node, depth):
        self.used.add("Typography")
        return f"<Typography.Link href={js(node.get('href', '#'))}>{text(node['text'])}</Typography.Link>"

    def antd_button(self, node, depth):
        variant = node.get("variant", "primary")
        kind = {"primary": "primary", "secondary": "primary", "danger": "primary", "outline": "default", "ghost": "link"}[variant]
        extra = " danger" if variant == "danger" else ""
        style = " style={{ background: tokens.colors.secondary, color: tokens.colors[\"on-secondary\"] }}" if variant == "secondary" else ""
        size = f" size={js({'sm': 'small', 'lg': 'large'}[node['size']])}" if node.get("size") in ("sm", "lg") else ""
        href = f" href={js(node['href'])}" if node.get("href") else ""
        return f"<{self.tag('Button')} type=\"{kind}\"{extra}{size}{href}{style}>{text(node['text'])}</Button>"

    def antd_buttons(self, node, depth):
        items = self.items(node["items"])
        inner = "".join("  " + self.antd_button({"text": i["text"], "variant": i.get("variant") or (
            "primary" if n == len(items) - 1 else "outline"), "href": i.get("href")}, 0) + "\n" for n, i in enumerate(items))
        return f"<{self.tag('Space')} wrap>\n{inner}</Space>"

    def antd_image(self, node, depth):
        src = self.image_src(node)
        if not src:
            return (f"<div role=\"img\" aria-label={js(node.get('alt', 'Image'))} style={{{{ background: tokens.colors.surface, minHeight: {node.get('height', 160)}, "
                    f"display: \"flex\", alignItems: \"center\", justifyContent: \"center\" }}}}>{text(node.get('alt', 'Image'))}</div>")
        height = f" height={{{node['height']}}}" if node.get("height") else ""
        width = f"{{{node['width']}}}" if isinstance(node.get("width"), int) else "\"100%\""
        return f"<{self.tag('Image')} src={js(src)} alt={js(node.get('alt', ''))} preview={{false}} width={width}{height} style={{{{ objectFit: \"cover\" }}}} />"

    def antd_card(self, node, depth):
        src = self.image_src(node)
        cover = f" cover={{<img src={js(src)} alt={js(node.get('alt', ''))} />}}" if src else ""
        title = f" title={js(node['title'])}" if node.get("title") else ""
        actions = ""
        if node.get("actions"):
            actions = " actions={[" + ", ".join(self.antd_button({"text": a["text"], "variant": a.get("variant") or "ghost"}, 0)
                                                 .replace("<Button", f"<Button key={js(str(n))}", 1)
                                                 for n, a in enumerate(self.items(node["actions"]))) + "]}"
        body = ""
        if node.get("text"):
            self.used.add("Typography")
            body += f"  <Typography.Paragraph type=\"secondary\" style={{{{ margin: 0 }}}}>{text(node['text'])}</Typography.Paragraph>\n"
        body += self.indent(self.kids(node, 0))
        return f"<{self.tag('Card')}{title}{cover}{actions} style={{{{ height: \"100%\" }}}}>\n{body}</Card>"

    def antd_field(self, field: dict, n: int) -> str:
        kind = field.get("type", "text")
        ph = f" placeholder={js(field['placeholder'])}" if field.get("placeholder") else ""
        control = {
            "select": f"<{self.tag('Select')} options={{{js([{'value': o, 'label': o} for o in field.get('options', [])])}}}{ph} />",
            "textarea": f"<Input.TextArea rows={{4}}{ph} />",
            "password": f"<Input.Password{ph} />",
            "number": f"<{self.tag('InputNumber')} style={{{{ width: \"100%\" }}}}{ph} />",
            "date": f"<{self.tag('DatePicker')} style={{{{ width: \"100%\" }}}} />",
            "radio": f"<{self.tag('Radio')}.Group options={{{js(field.get('options', []))}}} />",
            "file": f"<{self.tag('Upload')}><Button>{text(field.get('placeholder', 'Choisir un fichier'))}</Button></Upload>",
        }.get(kind)
        if kind == "switch":
            return (f"<Form.Item label={js(field['label'])} name={js(f'f{n}')} valuePropName=\"checked\">\n"
                    f"  <{self.tag('Switch')} />\n</Form.Item>")
        if kind == "checkbox":
            return (f"<Form.Item name={js(f'f{n}')} valuePropName=\"checked\"{' rules={[{ required: true }]}' if field.get('required') else ''}>\n"
                    f"  <{self.tag('Checkbox')}>{text(field['label'])}</Checkbox>\n</Form.Item>")
        if control is None:
            control = f"<Input type={js(kind)}{ph} />" if kind != "text" else f"<Input{ph} />"
        self.used.update({"Input", "Button"})
        help_ = f" extra={js(field['help'])}" if field.get("help") else ""
        rules = " rules={[{ required: true }]}" if field.get("required") else ""
        return f"<Form.Item label={js(field['label'])} name={js(f'f{n}')}{rules}{help_}>\n  {control}\n</Form.Item>"

    def antd_form(self, node, depth):
        span = 12 if node.get("columns") == 2 else 24
        title = f"  <Typography.Title level={{3}}>{text(node['title'])}</Typography.Title>\n" if node.get("title") else ""
        if title:
            self.used.add("Typography")
        fields = "".join(f"    <Col xs={{24}} md={{{24 if f.get('width') == 'full' else span}}}>\n{self.indent(self.antd_field(f, n), 3)}    </Col>\n"
                         for n, f in enumerate(node["fields"]))
        self.used.update({"Form", "Row", "Col", "Button"})
        return (f"<Form layout=\"vertical\"{self.style(node)}>\n{title}  <Row gutter={{16}}>\n{fields}  </Row>\n"
                f"  <Button type=\"primary\" htmlType=\"submit\">{text(node.get('submit', 'Valider'))}</Button>\n</Form>")

    def antd_table(self, node, depth):
        headers = node.get("headers") or [f"Colonne {i + 1}" for i in range(max((len(r) for r in node["rows"]), default=0))]
        columns = [{"title": h, "dataIndex": f"c{i}", "key": f"c{i}"} for i, h in enumerate(headers)]
        data = [{"key": str(n), **{f"c{i}": str(c) for i, c in enumerate(row)}} for n, row in enumerate(node["rows"])]
        return f"<{self.tag('Table')} size=\"small\" pagination={{false}} columns={{{js(columns)}}} dataSource={{{js(data)}}} />"

    def antd_list(self, node, depth):
        return (f"<{self.tag('List')} size=\"small\" dataSource={{{js([i['text'] for i in self.items(node['items'])])}}} "
                f"renderItem={{(item) => <List.Item>{{item}}</List.Item>}} />")

    def antd_badge(self, node, depth):
        color = {"neutral": None, "info": "processing", "success": "success", "warning": "warning", "danger": "error"}[node.get("variant", "neutral")]
        return f"<{self.tag('Tag')}{f' color={js(color)}' if color else ''}>{text(node['text'])}</Tag>"

    def antd_alert(self, node, depth):
        message = node.get("title") or node.get("text", "")
        desc = f" description={js(node['text'])}" if node.get("title") and node.get("text") else ""
        return f"<{self.tag('Alert')} type={js(SEVERITY[node.get('variant', 'info')])} message={js(message)}{desc} showIcon />"

    def antd_tabs(self, node, depth):
        items = js([{"key": str(n), "label": i["text"]} for n, i in enumerate(self.items(node["items"]))])
        return f"<{self.tag('Tabs')} activeKey={js(str(node.get('current', 1) - 1))} items={{{items}}} />"

    def antd_stepper(self, node, depth):
        items = js([{"title": i["text"]} for i in self.items(node["items"])])
        return f"<{self.tag('Steps')} current={{{node.get('current', 1) - 1}}} items={{{items}}} />"

    def antd_stat(self, node, depth):
        suffix = f" suffix={js(node['text'])}" if node.get("text") else ""
        return f"<{self.tag('Statistic')} title={js(node['label'])} value={js(node['value'])}{suffix} />"

    def antd_search(self, node, depth):
        self.used.add("Input")
        label = node.get("placeholder", "Rechercher")
        return f"<Input.Search placeholder={js(label)} aria-label={js(label)} enterButton={js(node.get('text', 'Rechercher'))} />"

    def antd_divider(self, node, depth):
        return f"<{self.tag('Divider')} style={{{{ margin: 0 }}}} />"

    def antd_footer(self, node, depth):
        groups = ""
        for g in node.get("groups", []):
            links = "".join(f"        <Typography.Link href={js(i.get('href', '#'))}>{text(i['text'])}</Typography.Link>\n"
                            for i in self.items(g.get("items")))
            groups += (f"    <Col xs={{24}} sm={{12}} md={{6}}>\n      <Typography.Title level={{5}}>{text(g.get('title', ''))}</Typography.Title>\n"
                       f"      <Flex vertical gap={{4}}>\n{links}      </Flex>\n    </Col>\n")
        self.used.update({"Typography", "Row", "Col", "Flex"})
        grid = f"  <Row gutter={{24}} style={{{{ marginBottom: 24 }}}}>\n{groups}  </Row>\n" if groups else ""
        note = f"  <Typography.Text type=\"secondary\">{text(node['text'])}</Typography.Text>\n" if node.get("text") else ""
        bg = self.color(node["background"]) if node.get("background") else "tokens.colors.surface"
        return (f"<footer style={{{{ background: {bg}, paddingBlock: 48 }}}}>\n"
                f"  <div style={{{{ maxWidth: tokens.maxWidth, margin: \"0 auto\", padding: \"0 24px\" }}}}>\n{self.indent(grid + note)}  </div>\n</footer>")


def theme_file(target: str, theme: dict) -> str:
    colors, sizes = theme["colors"], theme["font_sizes"]
    tokens = {"colors": colors, "fonts": theme["fonts"], "fontSizes": sizes, "spacing": theme["spacing"],
              "radii": theme["radii"], "shadows": theme["shadows"], "lineHeight": theme["line_height"],
              "maxWidth": theme["max_width"]}
    head = ("// Généré par page_build.py (mockup-to-html) depuis les tokens du design system : ne pas modifier,\n"
            "// régénérer depuis le fichier de tokens.\n")
    shared = f"export const tokens = {json.dumps(tokens, ensure_ascii=False, indent=2)} as const;\n"
    if target == "react-mui":
        palette = {"primary": {"main": colors["primary"], "contrastText": colors.get("on-primary", "#ffffff")},
                   "secondary": {"main": colors["secondary"], "contrastText": colors.get("on-secondary", "#ffffff")},
                   "error": {"main": colors["danger"]}, "warning": {"main": colors["warning"]},
                   "info": {"main": colors["info"]}, "success": {"main": colors["success"]},
                   "background": {"default": colors["background"], "paper": colors["background"]},
                   "text": {"primary": colors["text"], "secondary": colors["muted"]}, "divider": colors["border"]}
        typo = {"fontFamily": theme["fonts"]["body"], "fontSize": sizes.get("md", 16),
                **{f"h{n}": {"fontFamily": theme["fonts"]["heading"], "fontSize": f"{sizes.get(k, 16):g}px", "fontWeight": 700}
                   for n, k in zip(range(1, 7), ("3xl", "2xl", "xl", "lg", "md", "md"))}}
        config = {"palette": palette, "typography": typo, "shape": {"borderRadius": theme["radii"].get("md", 8)}}
        return (head + "import { createTheme } from \"@mui/material/styles\";\n\n" + shared +
                f"\nexport const theme = createTheme({json.dumps(config, ensure_ascii=False, indent=2)});\n")
    config = {"token": {"colorPrimary": colors["primary"], "colorSuccess": colors["success"],
                        "colorWarning": colors["warning"], "colorError": colors["danger"], "colorInfo": colors["info"],
                        "colorTextBase": colors["text"], "colorBgBase": colors["background"],
                        "colorBorder": colors["border"], "fontFamily": theme["fonts"]["body"],
                        "fontSize": sizes.get("md", 16), "borderRadius": theme["radii"].get("md", 8)}}
    return (head + "import type { ThemeConfig } from \"antd\";\n\n" + shared +
            f"\nexport const theme: ThemeConfig = {json.dumps(config, ensure_ascii=False, indent=2)};\n")


def page_file(target: str, spec: dict, theme: dict, stem: str, images: dict) -> tuple[str, str, list[str]]:
    """(nom du composant, code TSX, composants de la bibliothèque employés)."""
    emitter = Emitter(target, theme, images)
    body = "".join(emitter.node(node, 3) for node in spec["body"])
    name = f"{pascal(stem)}Page"
    used = sorted(emitter.used - {""})
    module = TARGETS[target]["module"]
    imports = f"import {{ {', '.join(used)} }} from \"{module}\";\n" if used else ""
    code = ("// Généré par page_build.py (mockup-to-html) depuis " + f"{stem}.json : régénérer plutôt que modifier.\n"
            + imports + "import { tokens } from \"./theme\";\n\n"
            + f"export default function {name}() {{\n  return (\n    <>\n{body}    </>\n  );\n}}\n")
    if "tokens." not in body:
        code = code.replace("import { tokens } from \"./theme\";\n", "")
    return name, code, used


def app_file(target: str, page: str) -> str:
    if target == "react-mui":
        return ("import { CssBaseline, ThemeProvider } from \"@mui/material\";\nimport { theme } from \"./theme\";\n"
                f"import {page} from \"./{page}\";\n\nexport default function App() {{\n  return (\n"
                f"    <ThemeProvider theme={{theme}}>\n      <CssBaseline />\n      <{page} />\n    </ThemeProvider>\n  );\n}}\n")
    return ("import { ConfigProvider } from \"antd\";\nimport { theme } from \"./theme\";\n"
            f"import {page} from \"./{page}\";\n\nexport default function App() {{\n  return (\n"
            f"    <ConfigProvider theme={{theme}}>\n      <{page} />\n    </ConfigProvider>\n  );\n}}\n")


TAG = re.compile(r"<(/?)([A-Za-z][\w.]*)([^<>]*?)(/?)>")


def check_jsx(code: str, imported: list[str]) -> list[str]:
    """Balises équilibrées et composants importés, dans le JSX produit (expressions {...} ignorées)."""
    errors, stack, depth, out, i = [], [], 0, [], 0
    in_string = None
    while i < len(code):
        ch = code[i]
        if depth and in_string:
            if ch == "\\":
                i += 2
                continue
            if ch == in_string:
                in_string = None
        elif depth and ch in "\"'`":
            in_string = ch
        elif ch == "{":
            depth += 1
        elif ch == "}" and depth:
            depth -= 1
        elif not depth:
            out.append(ch)
        i += 1
    flat = "".join(out)
    body = flat[flat.find("return ("):] if "return (" in flat else flat
    for closing, name, _, selfclose in TAG.findall(body):
        if selfclose:
            continue
        if closing:
            if not stack or stack[-1] != name:
                errors.append(f"balise </{name}> sans ouverture correspondante")
                break
            stack.pop()
        else:
            stack.append(name)
    if stack:
        errors.append(f"balise <{stack[-1]}> non fermée")
    used = {n.split(".")[0] for n in re.findall(r"<([A-Z][\w.]*)", code)}
    errors += [f"composant {n} employé sans import" for n in sorted(used - set(imported)) if not n.endswith("Page")]
    return errors
