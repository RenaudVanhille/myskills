"""Rendu de ux.md, la spécification UX du dossier : identité visuelle et tokens (design-system.json),
écrans décrits d'après les maquettes (pages/*.json), maquettes HTML et code, composants (decoupage.json),
accessibilité et constats (revue-ux.json), parcours (specs.json).

    ux(m, links, code) -> (frontmatter, corps)
    requirements(m)    -> exigences d'interface UX-n, reprises dans livraison.md

`links` : pour chaque page, les liens vers sa maquette et son rendu HTML (déjà recalés par l'appelant).
"""

import json

from pack_render import bullets, intro, join, journey, section, table

HEURISTICS = {"h1": "visibilité de l'état", "h2": "monde réel", "h3": "contrôle et liberté", "h4": "cohérence",
              "h5": "prévention des erreurs", "h6": "reconnaissance", "h7": "souplesse", "h8": "sobriété",
              "h9": "récupération des erreurs", "h10": "aide", "a11y": "accessibilité"}
SEVERITY = {1: "mineur", 2: "gênant", 3: "majeur", 4: "bloquant"}


def px(scale: dict) -> dict:
    return {str(name): f"{value}px" if isinstance(value, (int, float)) else str(value)
            for name, value in (scale or {}).items()}


def walk(nodes):
    """Tous les nœuds d'une page, en profondeur."""
    for item in nodes or []:
        if isinstance(item, dict):
            yield item
            yield from walk(item.get("children"))


def tokens(ds: dict) -> dict:
    """Tokens du design system : couleurs à plat, typographie, rayons, espacements, composants."""
    fonts, colors = ds.get("fonts", {}), ds.get("colors", {})
    typography = {role: {"fontFamily": family} for role, family in fonts.items()}
    typography.setdefault("body", {}).update({"lineHeight": str(ds["line_height"])} if ds.get("line_height") else {})
    typography.update({f"text-{name}": {"fontSize": size} for name, size in px(ds.get("font_sizes")).items()})
    components = {f"{name}-{variant}": {"background": f"{{colors.{variant}}}"}
                  for name, spec in ds.get("components", {}).items()
                  for variant in spec.get("variants", []) if variant in colors}
    found = {"colors": colors, "typography": typography, "rounded": px(ds.get("radii")),
             "spacing": px(ds.get("spacing")), "components": components}
    return {key: value for key, value in found.items() if value}


def component(name: str, spec: dict) -> str:
    lines = [f"**{name}**" + (f" : {spec['description']}." if spec.get("description") else "")]
    if spec.get("variants"):
        lines.append("Variantes : " + ", ".join(spec["variants"]) + ".")
    return " ".join(lines)


def screens(m: dict, links: dict) -> str:
    """Un écran par page décrite : navigation, blocs principaux, maquette et rendu de référence."""
    rows = []
    for name, page in m["pages"]:
        nodes = list(walk(page["body"]))
        menu = next((n.get("items") for n in nodes if n.get("type") in ("header", "sidebar", "nav") and n.get("items")), [])
        kinds = list(dict.fromkeys(n["type"] for n in page["body"] if n.get("type")))
        rows.append([page["title"], ", ".join(str(i if isinstance(i, str) else i.get("text", "")) for i in menu),
                     ", ".join(kinds), " ".join(f"[{label}]({path})" for label, path in links.get(name, []))])
    return table(["Écran", "Navigation", "Blocs", "Référence"], rows)


def patterns(m: dict) -> str:
    """Composants du découpage (bibliothèque qui les fournit, écrans), sinon ceux comptés dans les pages."""
    found = [c for c in m["breakdown"].get("components", []) if not c.get("layout")]
    if found:
        return table(["Composant", "Emplois", "Écrans", "Fourni par"],
                     [[c["type"], c.get("count", ""), ", ".join(c.get("screens", [])),
                       c.get("library") or ("sur mesure" if not c.get("provided") else "")] for c in found])
    counts: dict[str, int] = {}
    for _, page in m["pages"]:
        for item in walk(page["body"]):
            counts[item.get("type", "?")] = counts.get(item.get("type", "?"), 0) + 1
    return table(["Composant", "Emplois"], [[kind, count] for kind, count in sorted(counts.items())])


def mockups(m: dict, links: dict, code: list[str]) -> str:
    """Maquettes HTML produites d'après les maquettes : pages à ouvrir, code de la bibliothèque visée."""
    pages = [f"[{page['title']}]({path})" for name, page in m["pages"]
             for label, path in links.get(name, []) if label == "HTML"]
    if not pages and not code:
        return ""
    target = m["breakdown"].get("target")
    return join([
        "Pages HTML et CSS construites d'après les maquettes, à ouvrir dans un navigateur ; point de départ "
        "du développement de l'interface, pas une référence qui prime sur ce document." if pages else "",
        bullets(pages),
        (f"Code généré pour {target} :\n" if target and target != "html" else "Code généré :\n")
        + bullets(f"[{path.rsplit('/', 1)[-1]}]({path})" for path in code) if code else ""])


def findings(m: dict) -> str:
    rows = [[SEVERITY.get(f["severity"], f["severity"]), HEURISTICS.get(f["heuristic"], f["heuristic"]),
             f.get("page", ""), f["problem"], f["fix"]]
            for f in sorted(m["review"].get("findings", []), key=lambda f: -f["severity"])]
    return join([m["review"].get("summary", ""), table(["Gravité", "Heuristique", "Écran", "Constat", "Correction"], rows)])


def identity(ds: dict) -> str:
    locked = (ds.get("source") or {}).get("locked")
    rules = [f"À faire ({name}) : {text}" for name, spec in ds.get("components", {}).items() for text in spec.get("do", [])]
    rules += [f"À éviter ({name}) : {text}" for name, spec in ds.get("components", {}).items()
              for text in spec.get("dont", [])]
    sizes = ", ".join(f"{name} {size}" for name, size in px(ds.get("font_sizes")).items())
    return join([
        join([f"Design system **{ds['name']}**. " + ds.get("description", ""), bullets(ds.get("principles", [])),
              "Fourni par le client : il s'applique tel quel, sans modification." if locked else ""]),
        section("Couleurs", bullets(f"`{role}` : {value}" for role, value in ds.get("colors", {}).items()), 3),
        section("Typographie", join([bullets(f"`{role}` : {family}" for role, family in ds.get("fonts", {}).items()),
                                     f"Tailles : {sizes}." if sizes else ""]), 3),
        section("Espacements et mise en page", join([
            bullets(f"`{name}` : {value}" for name, value in px(ds.get("spacing")).items()),
            f"Largeur du contenu : {ds['max_width']}px." if ds.get("max_width") else ""]), 3),
        section("Ombres", bullets(f"`{name}` : {value}" for name, value in ds.get("shadows", {}).items()), 3),
        section("Formes", bullets(f"`{name}` : {value}" for name, value in px(ds.get("radii")).items()), 3),
        section("Composants du design system", bullets(component(name, spec)
                                                       for name, spec in ds.get("components", {}).items()), 3),
        section("Règles", bullets(rules), 3),
        section("Tokens", "Valeurs à reprendre telles quelles (thème, variables CSS) :\n\n```json\n"
                + json.dumps(tokens(ds), ensure_ascii=False, indent=1) + "\n```", 3),
    ])


def ux(m: dict, links: dict, code: list[str]) -> tuple[dict, str]:
    target, ds = m["breakdown"].get("target"), m["design"] or {}
    foundation = join([
        f"Bibliothèque d'interface visée : {target}." if target and target != "html" else "",
        f"Écrans décrits d'après les maquettes : {len(m['pages'])}. Les maquettes et leurs rendus HTML sont des "
        "références de composition ; en cas d'écart, ce document l'emporte." if m["pages"] else ""])
    level = m["review"].get("level") or "AA"
    contrast = (ds.get("contrast") or {}).get("min")
    access = [f"Niveau WCAG visé : {level}." + (f" Contraste minimal du texte : {contrast}." if contrast else "")]
    access += [f"{f['problem']} : {f['fix']}" for f in m["review"].get("findings", []) if f["heuristic"] == "a11y"]
    flows = "\n".join(journey(j, i, m) for i, j in enumerate(m["extra"].get("journeys", []), 1))
    body = join([
        intro(m, "ux.md", foundation),
        section("Identité visuelle", identity(ds) if ds else ""),
        section("Écrans", screens(m, links)),
        section("Maquettes HTML", mockups(m, links, code)),
        section("Composants d'interface", patterns(m)),
        section("Accessibilité", bullets(access) if m["review"] or ds else ""),
        section("Parcours", flows),
        section("Constats de la revue UX", findings(m)),
        section("Exigences d'interface", bullets(requirements(m))),
    ])
    return {"title": f"Spécification UX : {m['name']}", "type": "ux"}, body


def requirements(m: dict) -> list[str]:
    """Exigences d'interface : un écran par ligne, puis les constats majeurs de la revue UX."""
    lines = [f"Écran « {page['title']} » conforme à ux.md (identité visuelle, composants, accessibilité)"
             for _, page in m["pages"]]
    lines += [f"{f['problem']} : {f['fix']} ({SEVERITY[f['severity']]})"
              for f in m["review"].get("findings", []) if f["severity"] >= 3]
    return [f"UX-{i} : {line}" for i, line in enumerate(lines, 1)]
