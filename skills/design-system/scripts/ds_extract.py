# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.24"]
# ///
"""Tire la palette de couleurs de maquettes (PNG, JPEG, WebP) et propose un brouillon de tokens.

Le script, et non le modèle, mesure les couleurs : chaque image est réduite
sans lissage, ses couleurs sont comptées, les couleurs proches (dans une
image et d'une image à l'autre) fusionnées et classées par surface occupée. Il propose un rôle aux principales :

- background : la couleur la plus étendue ;
- text : la couleur neutre la plus contrastée sur le fond ;
- primary, puis secondary : les plus saturées, de teintes distinctes ;
- surface et border : les teintes neutres proches du fond.

Avec --draft, écrit un fichier de tokens pour ds_build.py : les couleurs à
rôle, les autres valeurs par défaut. Le modèle relit les rôles sur une
maquette, nomme le design system et corrige ; il n'écrit pas la palette.
Les images ne sont lues qu'en local.

Avec --draft, si le skill mockup-to-html est installé, ses mesures
(ui_analyze.py) remplacent les échelles par défaut : tailles de texte
relevées par l'OCR local (Tesseract, facultatif ; celle du texte courant
devient md), espacements entre blocs (grille de 4 px) et rayons des cadres. --scale
donne les pixels d'image par pixel CSS (2 pour une maquette exportée en 2x).

Avec --against TOKENS.json (design system fourni, ds_import.py), signale les
couleurs des maquettes qui s'en écartent et le token le plus proche.

    uv run scripts/ds_extract.py IMAGE [...] [--colors 12] [--draft TOKENS.json] [--name NOM] [--scale 1] [--against TOKENS.json]
"""

import argparse
import colorsys
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ds_build  # noqa: E402
import skill_paths  # noqa: E402

IMAGES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
MERGE = 12
TOLERANCE = 20  # distance RGB au-delà de laquelle une couleur de maquette s'écarte du design system  # distance RGB sous laquelle deux couleurs sont la même
SIDE = 320  # côté maximal de l'image réduite


def palette(path: Path) -> dict[str, int]:
    """Couleurs de l'image réduite sans lissage (les aplats restent purs), par paliers de 8."""
    from PIL import Image

    with Image.open(path) as image:
        image = image.convert("RGB")
        ratio = SIDE / max(image.size)
        if ratio < 1:
            image = image.resize((max(1, round(image.width * ratio)), max(1, round(image.height * ratio))),
                                 Image.Resampling.NEAREST)
        counts: dict[str, int] = {}
        sums: dict[tuple, list] = {}
        for count, color in image.getcolors(maxcolors=image.width * image.height) or []:
            bucket = tuple(v // 8 for v in color)
            entry = sums.setdefault(bucket, [0, 0, 0, 0])
            entry[0] += count
            for i in range(3):
                entry[i + 1] += color[i] * count
        for count, *total in sums.values():
            hex_ = ds_build.to_hex(v / count for v in total)
            counts[hex_] = counts.get(hex_, 0) + count
    return counts


def merge(counts: dict[str, int]) -> list[tuple[str, int]]:
    """Couleurs proches fusionnées dans la plus étendue, par surface décroissante."""
    groups: list[list] = []
    for color, count in sorted(counts.items(), key=lambda kv: -kv[1]):
        group = next((g for g in groups if ds_build.distance(g[0], color) < MERGE), None)
        if group:
            group[1] += count
        else:
            groups.append([color, count])
    return [(c, n) for c, n in groups]


def saturation(hex_: str) -> float:
    h, l, s = colorsys.rgb_to_hls(*(c / 255 for c in ds_build.rgb(hex_)))
    return s * (1 - abs(2 * l - 1))  # chroma : ni presque blanc ni presque noir


def hue(hex_: str) -> float:
    return colorsys.rgb_to_hls(*(c / 255 for c in ds_build.rgb(hex_)))[0]


def roles(colors: list[tuple[str, float]]) -> dict[str, str]:
    found: dict[str, str] = {}
    if not colors:
        return found
    background = colors[0][0]
    found["background"] = background
    visible = [(c, s) for c, s in colors if s >= 0.005]
    # Texte : la couleur neutre la plus contrastée sur le fond (les aplats colorés sont des fonds ou des accents).
    inks = [c for c, s in colors if s >= 0.001 and saturation(c) <= 0.2] or [c for c, _ in visible]
    text = max(inks, key=lambda c: ds_build.contrast(c, background))
    if ds_build.contrast(text, background) >= 3:
        found["text"] = text
    vivid = sorted((c for c, s in visible if saturation(c) > 0.25 and c != text), key=lambda c: -dict(visible)[c])
    if vivid:
        found["primary"] = vivid[0]
        other = next((c for c in vivid[1:] if min(abs(hue(c) - hue(vivid[0])), 1 - abs(hue(c) - hue(vivid[0]))) > 0.08),
                     None)
        if other:
            found["secondary"] = other
    neutrals = [c for c, s in colors if s >= 0.002 and saturation(c) <= 0.12 and c not in found.values()]
    near = sorted(neutrals, key=lambda c: ds_build.distance(c, background))
    if near and ds_build.distance(near[0], background) < 40:
        found["surface"] = near[0]
        rest = [c for c in near[1:] if 1.1 < ds_build.contrast(c, background) < 2.5]
        if rest:
            found["border"] = rest[0]
    return found


def snap(values: list[float], defaults: dict, step: int = 1) -> dict:
    """Place chaque valeur mesurée sur la clé par défaut la plus proche (en rapport), garde l'échelle croissante."""
    scale = dict(defaults)
    keys = [k for k, v in defaults.items() if 0 < v < 999]
    taken: set[str] = set()
    for value in values:
        value = max(step, round(value / step) * step)
        key = min(keys, key=lambda k: abs(defaults[k] - value) / defaults[k])
        if key not in taken and abs(defaults[key] - value) / defaults[key] <= 0.5:
            scale[key] = value
            taken.add(key)
    ordered = sorted(keys, key=lambda k: defaults[k])
    for low, high in zip(ordered, ordered[1:]):
        if scale[high] <= scale[low]:
            scale[high] = scale[low] + step
    return scale


def measures(images: list[Path], scale: float, report: dict) -> dict | None:
    """Tailles de texte, espacements et rayons mesurés par ui_analyze.py (mockup-to-html), en px CSS."""
    module = skill_paths.load_module("mockup-to-html", "ui_analyze.py")
    if module is None:
        report["warnings"].append(f"échelles par défaut : {skill_paths.absent('mockup-to-html', 'ui_analyze.py')}")
        return None
    langs = module.tesseract_langs("fr")
    if not langs:
        report["warnings"].append("tailles de texte par défaut : Tesseract absent (check-prerequisites, groupe maquettes)")
    sizes: list[float] = []
    weighted: list[float] = []
    spacing: list[float] = []
    radii: list[float] = []
    for path in images:
        analysis = module.analyze(path, langs)
        sizes += [line["font_px"] / scale for line in analysis["texts"]]
        # Le texte courant porte le plus de caractères : médiane pondérée par la longueur.
        weighted += [line["font_px"] / scale for line in analysis["texts"] for _ in line["text"]]
        spacing += [v / scale for v in analysis["measures"]["spacing"]]
        radii += [v / scale for v in analysis["measures"]["radii"]]
    found: dict = {"font_sizes": None, "spacing": None, "radii": None}
    if sizes:
        body = sorted(weighted)[len(weighted) // 2]
        ratio = body / ds_build.DEFAULTS["font_sizes"]["md"]
        base = {k: v * ratio for k, v in ds_build.DEFAULTS["font_sizes"].items()}
        found["font_sizes"] = snap([body] + module.cluster(sizes), base)
        found["font_sizes"] = {k: max(8, min(128, round(v))) for k, v in found["font_sizes"].items()}
    if spacing:
        found["spacing"] = snap([v for v in module.cluster(spacing, 0.2) if v <= 96], ds_build.DEFAULTS["spacing"], 4)
    if radii:
        found["radii"] = snap(module.cluster(radii, 0.3), ds_build.DEFAULTS["radii"])
    return found


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("images", nargs="+", type=Path)
    parser.add_argument("--colors", type=int, default=12)
    parser.add_argument("--draft", type=Path)
    parser.add_argument("--name", default="")
    parser.add_argument("--against", type=Path)
    parser.add_argument("--scale", type=float, default=1.0)
    args = parser.parse_args()
    report = {"inputs": [str(p) for p in args.images], "palette": [], "roles": {}, "draft": None, "measures": None, "deviations": [],
              "errors": [], "warnings": []}
    counts: dict[str, int] = {}
    for path in args.images:
        if path.suffix.lower() not in IMAGES:
            report["errors"].append(f"{path.name} : format non reconnu ({', '.join(sorted(IMAGES))})")
            continue
        try:
            for color, count in palette(path).items():
                counts[color] = counts.get(color, 0) + count
        except ImportError:
            report["errors"].append("Pillow manquant : lancez ce script avec `uv run`")
            break
        except OSError as error:
            report["errors"].append(f"{path.name} : image illisible ({error})")
    if report["errors"]:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    total = sum(counts.values()) or 1
    colors = [(c, round(n / total, 4)) for c, n in merge(counts)]
    found = roles(colors)
    by_color = {v: k for k, v in found.items()}
    report["palette"] = [{"hex": c, "share": s, "role": by_color.get(c)} for c, s in colors
                         if s >= 0.002][:args.colors]
    report["roles"] = found
    missing = [r for r in ("text", "primary") if r not in found]
    if missing:
        report["warnings"].append(f"rôle non trouvé : {', '.join(missing)} ; valeur par défaut gardée, à choisir "
                                  "dans la palette")
    if args.against:
        # Design system fourni : les couleurs des maquettes qui s'en écartent, avec le token le plus proche.
        try:
            tokens = json.loads(args.against.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            report["errors"].append(f"--against : {args.against} illisible ({error})")
            print(json.dumps(report, ensure_ascii=False))
            return 1
        report["errors"] += ds_build.tokens_errors(tokens)
        if report["errors"]:
            print(json.dumps(report, ensure_ascii=False))
            return 1
        theme, _ = ds_build.complete(tokens)
        for hex_, share in colors:
            if share < 0.005:
                continue
            nearest = min(theme["colors"], key=lambda k: ds_build.distance(theme["colors"][k], hex_))
            gap = round(ds_build.distance(theme["colors"][nearest], hex_), 1)
            if gap > TOLERANCE:
                report["deviations"].append({"hex": hex_, "share": share, "nearest": nearest,
                                             "token": theme["colors"][nearest], "distance": gap})
        if report["deviations"]:
            report["warnings"].append(f"{len(report['deviations'])} couleur(s) des maquettes hors du design system fourni "
                                      "(deviations) : à prendre le token le plus proche, ou à signaler au client")
    if args.draft:
        name = args.name or args.draft.stem.replace("-", " ").capitalize()
        draft = {"name": name, "description": f"Tiré de {len(args.images)} maquette(s) par ds_extract.py, à relire.",
                 "colors": {**{k: v for k, v in ds_build.DEFAULTS["colors"].items() if k in ("background", "text")},
                            **{k: found[k] for k in ("primary", "secondary", "background", "surface", "text", "border")
                               if k in found}},
                 "fonts": ds_build.DEFAULTS["fonts"], "font_sizes": ds_build.DEFAULTS["font_sizes"],
                 "spacing": ds_build.DEFAULTS["spacing"], "radii": ds_build.DEFAULTS["radii"]}
        if "primary" not in found:
            draft["colors"]["primary"] = ds_build.DEFAULTS["colors"]["primary"]
        measured = measures(args.images, args.scale if args.scale > 0 else 1.0, report)
        if measured:
            report["measures"] = measured
            draft.update({k: v for k, v in measured.items() if v})
            draft["description"] += " Échelles mesurées par ui_analyze.py (mockup-to-html)."
        errors = ds_build.tokens_errors(draft)
        if errors:
            report["errors"] += errors
            print(json.dumps(report, ensure_ascii=False))
            return 1
        args.draft.parent.mkdir(parents=True, exist_ok=True)
        args.draft.write_text(json.dumps(draft, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report["draft"] = str(args.draft)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
