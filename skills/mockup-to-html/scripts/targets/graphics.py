"""Icônes et graphiques en SVG en ligne, communs à toutes les cibles de page_build.py.

Aucune ressource externe : un jeu d'icônes simple, dessiné pour ce dépôt
(licence MIT, trait de 2 px sur une grille de 24), et des graphiques à
barres, en courbe ou en anneau tirés de séries courtes. Le même arbre
(balise, attributs, enfants) s'écrit en HTML ou en JSX (attributs en
camelCase) ; les couleurs passent par des variables CSS des tokens ou par
une valeur fournie par la cible.
"""

import html
import math

# Tracés des icônes (viewBox 0 0 24 24, trait courant, sans remplissage).
ICONS = {
    "home": ["M3 11 12 4l9 7", "M5 10v10h14V10", "M10 20v-6h4v6"],
    "search": ["M11 4a7 7 0 1 0 0 14a7 7 0 1 0 0-14", "M16 16l5 5"],
    "user": ["M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8", "M4 21c0-4 4-6 8-6s8 2 8 6"],
    "users": ["M9 5a3.5 3.5 0 1 0 0 7a3.5 3.5 0 1 0 0-7", "M2 20c0-3.5 3-5.5 7-5.5s7 2 7 5.5",
              "M16 5.5a3 3 0 0 1 0 6", "M18 14.5c2.5.5 4 2.3 4 5"],
    "bell": ["M6 16V11a6 6 0 0 1 12 0v5l2 2H4z", "M10 21h4"],
    "settings": ["M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6",
                 "M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1 7 17M17 7l2.1-2.1"],
    "menu": ["M4 6h16", "M4 12h16", "M4 18h16"],
    "close": ["M6 6l12 12", "M18 6 6 18"],
    "plus": ["M12 5v14", "M5 12h14"],
    "minus": ["M5 12h14"],
    "check": ["M5 12l5 5 9-10"],
    "edit": ["M4 20h4L19 9l-4-4L4 16z", "M13 7l4 4"],
    "trash": ["M4 7h16", "M9 7V4h6v3", "M6 7l1 13h10l1-13"],
    "filter": ["M3 5h18l-7 8v6l-4 2v-8z"],
    "download": ["M12 4v11", "M7 10l5 5 5-5", "M4 20h16"],
    "upload": ["M12 20V9", "M7 14l5-5 5 5", "M4 4h16"],
    "calendar": ["M4 6h16v14H4z", "M4 10h16", "M8 3v4M16 3v4"],
    "mail": ["M3 6h18v12H3z", "M3 7l9 6 9-6"],
    "phone": ["M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2"],
    "file": ["M6 3h8l4 4v14H6z", "M14 3v4h4"],
    "folder": ["M3 6h6l2 2h10v11H3z"],
    "chart": ["M4 20V4", "M4 20h16", "M8 16v-4M12 16V8M16 16v-6"],
    "dashboard": ["M4 4h7v9H4z", "M13 4h7v5h-7z", "M13 11h7v9h-7z", "M4 15h7v5H4z"],
    "list": ["M9 6h11M9 12h11M9 18h11", "M4 6h1M4 12h1M4 18h1"],
    "logout": ["M10 4H5v16h5", "M14 8l4 4-4 4", "M18 12H9"],
    "lock": ["M6 11h12v9H6z", "M8 11V8a4 4 0 0 1 8 0v3"],
    "info": ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18", "M12 11v6", "M12 7h.01"],
    "warning": ["M12 3 2 20h20z", "M12 9v5", "M12 17h.01"],
    "help": ["M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18", "M9.5 9a2.5 2.5 0 1 1 3.5 2.3c-.7.3-1 .9-1 1.7", "M12 17h.01"],
    "star": ["M12 3l2.8 5.8 6.2.9-4.5 4.4 1 6.2L12 17.4 6.5 20.3l1-6.2L3 9.7l6.2-.9z"],
    "heart": ["M12 20s-8-5-8-11a4.5 4.5 0 0 1 8-2.8A4.5 4.5 0 0 1 20 9c0 6-8 11-8 11z"],
    "cart": ["M3 4h3l2 11h11l2-8H7", "M9 20h.01M17 20h.01"],
    "eye": ["M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z", "M12 9a3 3 0 1 0 0 6a3 3 0 1 0 0-6"],
    "chevron-right": ["M9 5l7 7-7 7"],
    "chevron-left": ["M15 5l-7 7 7 7"],
    "chevron-down": ["M5 9l7 7 7-7"],
    "arrow-right": ["M4 12h16", "M14 6l6 6-6 6"],
    "more": ["M5 12h.01M12 12h.01M19 12h.01"],
    "refresh": ["M20 11a8 8 0 1 0-2.3 5.7", "M20 4v7h-7"],
}
CHART_VARIANTS = ["bar", "line", "donut"]
SERIES = ["primary", "secondary", "info", "success", "warning", "danger"]

JSX_NAMES = {"class": "className", "stroke-width": "strokeWidth", "stroke-linecap": "strokeLinecap",
             "stroke-linejoin": "strokeLinejoin", "text-anchor": "textAnchor", "font-size": "fontSize",
             "aria-hidden": "aria-hidden", "aria-label": "aria-label", "stroke-dasharray": "strokeDasharray",
             "stroke-dashoffset": "strokeDashoffset", "font-weight": "fontWeight"}


def write(tree, jsx: bool = False) -> str:
    """Écrit (balise, attributs, enfants) en HTML ou en JSX ; un enfant chaîne est un texte échappé."""
    if isinstance(tree, str):
        text = html.escape(tree)
        return text.replace("{", "&#123;").replace("}", "&#125;") if jsx else text
    tag, attrs, children = tree
    parts = []
    for key, value in attrs.items():
        name = JSX_NAMES.get(key, key) if jsx else key
        parts.append(f' {name}="{html.escape(str(value), quote=True)}"')
    inner = "".join(write(c, jsx) for c in children)
    if not inner and tag in ("path", "rect", "circle", "polyline", "line"):
        return f"<{tag}{''.join(parts)} />" if jsx else f"<{tag}{''.join(parts)}/>"
    return f"<{tag}{''.join(parts)}>{inner}</{tag}>"


def icon(name: str, size: float = 20, label: str | None = None):
    paths = [("path", {"d": d}, []) for d in ICONS[name]]
    attrs = {"viewBox": "0 0 24 24", "width": f"{size:g}", "height": f"{size:g}", "fill": "none",
             "stroke": "currentColor", "stroke-width": "2", "stroke-linecap": "round", "stroke-linejoin": "round"}
    attrs.update({"role": "img", "aria-label": label} if label else {"aria-hidden": "true"})
    return ("svg", attrs, paths)


def chart(variant: str, items: list[dict], colors: dict, height: int = 240, title: str = ""):
    """Graphique SVG ; colors donne la valeur (couleur, var(--...)) de chaque token de SERIES, plus text et border."""
    values = [float(i.get("value", 0)) for i in items]
    labels = [i["text"] for i in items]
    summary = (title + " : " if title else "") + ", ".join(f"{l} {v:g}" for l, v in zip(labels, values))
    width = 600
    kids: list = []
    top = max(values + [0]) or 1
    if variant == "donut":
        total = sum(v for v in values if v > 0) or 1
        r, cx, cy, start = 70, 120, height / 2, -math.pi / 2
        for i, value in enumerate(values):
            angle = 2 * math.pi * max(value, 0) / total
            end = start + angle
            large = 1 if angle > math.pi else 0
            x0, y0 = cx + r * math.cos(start), cy + r * math.sin(start)
            x1, y1 = cx + r * math.cos(end - 1e-6), cy + r * math.sin(end - 1e-6)
            kids.append(("path", {"d": f"M{x0:.1f} {y0:.1f}A{r} {r} 0 {large} 1 {x1:.1f} {y1:.1f}", "fill": "none",
                                  "stroke": colors[SERIES[i % len(SERIES)]], "stroke-width": "28"}, []))
            ly = 30 + i * 26
            kids.append(("rect", {"x": "240", "y": f"{ly - 12}", "width": "14", "height": "14", "rx": "3",
                                  "fill": colors[SERIES[i % len(SERIES)]]}, []))
            kids.append(("text", {"x": "262", "y": f"{ly}", "font-size": "14", "fill": colors["text"]},
                         [f"{labels[i]} ({value:g})"]))
            start = end
    else:
        left, bottom, plot_h = 40, height - 28, height - 48
        step = (width - left - 10) / max(1, len(values))
        kids.append(("line", {"x1": f"{left}", "y1": f"{bottom}", "x2": f"{width - 10}", "y2": f"{bottom}",
                              "stroke": colors["border"]}, []))
        points = []
        for i, value in enumerate(values):
            h = plot_h * max(value, 0) / top
            x = left + i * step
            if variant == "bar":
                kids.append(("rect", {"x": f"{x + step * 0.2:.1f}", "y": f"{bottom - h:.1f}", "width": f"{step * 0.6:.1f}",
                                      "height": f"{h:.1f}", "rx": "3", "fill": colors["primary"]}, []))
            points.append(f"{x + step / 2:.1f},{bottom - h:.1f}")
            kids.append(("text", {"x": f"{x + step / 2:.1f}", "y": f"{height - 8}", "text-anchor": "middle",
                                  "font-size": "13", "fill": colors["text"]}, [labels[i]]))
        if variant == "line":
            kids.append(("polyline", {"points": " ".join(points), "fill": "none", "stroke": colors["primary"],
                                      "stroke-width": "3", "stroke-linejoin": "round"}, []))
            for point in points:
                x, y = point.split(",")
                kids.append(("circle", {"cx": x, "cy": y, "r": "4", "fill": colors["primary"]}, []))
    return ("svg", {"viewBox": f"0 0 {width} {height}", "width": "100%", "height": f"{height}",
                    "role": "img", "aria-label": summary, "preserveAspectRatio": "xMinYMid meet"}, kids)


def css_colors() -> dict:
    """Couleurs des graphiques en variables CSS des tokens (cible html, Bootstrap, Vue, Angular)."""
    return {**{name: f"var(--color-{name}, currentColor)" for name in SERIES},
            "text": "var(--color-muted, currentColor)", "border": "var(--color-border, currentColor)"}


def theme_colors(theme: dict) -> dict:
    """Couleurs des graphiques en valeurs exactes des tokens (cibles React, Vue, Angular)."""
    colors = theme["colors"]
    return {**{name: colors.get(name, colors.get("primary", "#2563eb")) for name in SERIES},
            "text": colors.get("muted", "#64748b"), "border": colors.get("border", "#e2e8f0")}


def initials(text: str) -> str:
    words = [w for w in text.replace("-", " ").split() if w[:1].isalnum()]
    if not words:
        return "?"
    return (words[0][0] + (words[-1][0] if len(words) > 1 else "")).upper() if len(text) > 3 else text[:3].upper()
