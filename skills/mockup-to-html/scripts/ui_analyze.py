# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "numpy>=1.24"]
# ///
"""Mesure la mise en page d'une maquette d'écran et en tire une ébauche de description de page.

Le modèle n'estime plus à l'œil positions, tailles et textes : le script les
mesure, en local, sans modèle téléchargé.

- bandes horizontales de la page (fond, hauteur, filet de séparation) ;
- colonnes de chaque bande (profil horizontal du contenu) ;
- cadres : aplats (boutons, badges, logos), cadres à bordure (cartes,
  champs, tableaux), images ; rayon des coins estimé ;
- textes avec leur position, leur taille de police estimée et leur couleur,
  par OCR local (Tesseract, déjà utilisé par doc-to-markdown) ; sans
  Tesseract, la mise en page est mesurée sans les textes (signalé) ;
- tailles de police, espacements et rayons récurrents.

Écrit <maquette>.analysis.json et, avec --draft, <maquette>.json : une
ébauche de description de page pour page_build.py (bandes en sections,
colonnes en grille ou en rangée, cartes, titres et textes exacts, boutons,
tokens les plus proches), à relire et corriger par le modèle au lieu de tout
écrire. page_build.py reprend la même analyse pour comparer le rendu à la
maquette bloc par bloc.

    uv run scripts/ui_analyze.py MAQUETTE.png... [--tokens design-system.json] [--draft]
        [--out-dir DOSSIER] [--scale 2] [--lang fr] [--force]
"""

import argparse
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import script_report  # noqa: E402
import skill_paths  # noqa: E402

TOL = 30          # écart de couleur (somme des trois canaux) au-delà duquel un pixel se distingue du fond
MIN_BAND = 24     # hauteur minimale d'une bande ; en dessous, filet ou bande mêlée à la précédente
MIN_GAP = 24      # vide minimal entre deux colonnes
MIN_CONF = 60     # confiance OCR minimale d'un mot
DESCENDERS = set("gjpqyQ,;()")
TALL = set("bdfhijklt0123456789ÀÂÄÇÉÈÊËÎÏÔÖÙÛÜ'\"!?/|&@#%{}[]") | set("ABCDEFGHIJKLMNOPQRSTUVWXYZ")


# --- Image -------------------------------------------------------------------------------------------------

def load(path_or_image):
    import numpy as np
    from PIL import Image
    image = path_or_image if hasattr(path_or_image, "convert") else Image.open(path_or_image)
    return np.asarray(image.convert("RGB"), dtype=np.int16)


def hexa(color) -> str:
    return "#" + "".join(f"{max(0, min(255, int(c))):02x}" for c in color)


def distance(a, b) -> int:
    return int(sum(abs(int(x) - int(y)) for x, y in zip(a, b)))


def mode_color(pixels):
    """Couleur la plus fréquente d'un lot de pixels (quantifiée à 8 niveaux par canal, puis moyenne exacte)."""
    import numpy as np
    flat = pixels.reshape(-1, 3)
    keys = (flat[:, 0] >> 3) * 1024 + (flat[:, 1] >> 3) * 32 + (flat[:, 2] >> 3)
    values, counts = np.unique(keys, return_counts=True)
    best = values[counts.argmax()]
    return tuple(int(round(v)) for v in flat[keys == best].mean(axis=0)), float(counts.max() / len(keys))


def bands(arr) -> list[dict]:
    """Bandes horizontales de fond uni ; un filet fin devient la bordure basse de la bande qui le précède."""
    import numpy as np
    height, width = arr.shape[:2]
    step = max(1, width // 320)
    rows = []
    for y in range(height):
        color, share = mode_color(arr[y, ::step])
        rows.append(color)
    runs: list[list] = []  # [y0, y1, couleur]
    for y, color in enumerate(rows):
        if runs and distance(runs[-1][2], color) <= TOL // 2:
            runs[-1][1] = y + 1
        else:
            runs.append([y, y + 1, color])
    out: list[dict] = []
    for y0, y1, color in runs:
        thin = y1 - y0 < MIN_BAND
        if out and thin and y1 - y0 <= 4:
            out[-1]["border"] = hexa(color)
            out[-1]["height"] = y1 - out[-1]["y"]
            continue
        if out and (thin or distance(out[-1]["rgb"], color) <= TOL // 2):
            out[-1]["height"] = y1 - out[-1]["y"]
            if not thin:
                out[-1]["border"] = None  # filet au milieu de la bande (carte, tableau) : pas une bordure
            continue
        out.append({"y": y0, "height": y1 - y0, "rgb": color, "background": hexa(color), "border": None})
    for band in out:
        sub = arr[band["y"]:band["y"] + band["height"]]
        band["rgb"], _ = mode_color(sub[:, ::step])
        band["background"] = hexa(band["rgb"])
    return out


def content_mask(arr, background):
    import numpy as np
    return np.abs(arr - np.array(background, dtype=np.int16)).sum(axis=2) > TOL


def columns(mask, x_offset: int = 0) -> list[dict]:
    """Colonnes d'une bande : suites de x où du contenu existe, séparées par un vide d'au moins MIN_GAP px."""
    import numpy as np
    profile = mask.any(axis=0)
    xs = np.flatnonzero(profile)
    if not len(xs):
        return []
    cols, start, last = [], int(xs[0]), int(xs[0])
    for x in xs[1:]:
        if x - last > MIN_GAP:
            cols.append((start, last + 1))
            start = int(x)
        last = int(x)
    cols.append((start, last + 1))
    out = []
    for x0, x1 in cols:
        ys = np.flatnonzero(mask[:, x0:x1].any(axis=1))
        out.append({"x": x0 + x_offset, "width": x1 - x0, "top": int(ys[0]), "bottom": int(ys[-1]) + 1})
    return out


def components(mask) -> list[tuple[int, int, int, int, int]]:
    """Composantes connexes (4-connexité) par segments de lignes et union-find : (x0, y0, x1, y1, pixels)."""
    import numpy as np
    parent: list[int] = []

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    previous: list[tuple[int, int, int]] = []
    runs_all: list[tuple[int, int, int, int]] = []
    for y in range(mask.shape[0]):
        row = mask[y]
        if not row.any():
            previous = []
            continue
        padded = np.concatenate(([0], row.view(np.int8), [0]))
        edges = np.flatnonzero(np.diff(padded))
        current = []
        j = 0
        for x0, x1 in zip(edges[::2], edges[1::2]):
            label = len(parent)
            parent.append(label)
            while j < len(previous) and previous[j][1] <= x0:
                j += 1
            k = j
            while k < len(previous) and previous[k][0] < x1:
                a, b = find(previous[k][2]), find(label)
                if a != b:
                    parent[b] = a
                k += 1
            current.append((int(x0), int(x1), label))
            runs_all.append((y, int(x0), int(x1), label))
        previous = current
    boxes: dict[int, list[int]] = {}
    for y, x0, x1, label in runs_all:
        root = find(label)
        box = boxes.get(root)
        if box is None:
            boxes[root] = [x0, y, x1, y + 1, x1 - x0]
        else:
            box[0], box[1], box[2], box[3] = min(box[0], x0), min(box[1], y), max(box[2], x1), max(box[3], y + 1)
            box[4] += x1 - x0
    return [tuple(b) for b in boxes.values()]


def dilate(mask, steps: int = 2):
    """Masque épaissi de quelques pixels : un coin arrondi lissé ne coupe plus un cadre en morceaux."""
    import numpy as np
    out = mask.copy()
    for _ in range(steps):
        grown = out.copy()
        grown[1:] |= out[:-1]
        grown[:-1] |= out[1:]
        grown[:, 1:] |= out[:, :-1]
        grown[:, :-1] |= out[:, 1:]
        out = grown
    return out


def radius(mask, x0, y0) -> int:
    """Rayon du coin haut gauche : pas en diagonale avant de toucher le cadre, ramené au rayon d'un quart de cercle."""
    for d in range(0, 40):
        if y0 + d >= mask.shape[0] or x0 + d >= mask.shape[1]:
            break
        if mask[y0 + d, x0 + d]:
            return round(d * 3.414)
    return 0


def frames(arr, band: dict, width: int) -> list[dict]:
    """Aplats, cadres à bordure et images d'une bande."""
    import numpy as np
    y_off = band["y"]
    sub = arr[y_off:y_off + band["height"]]
    mask = content_mask(sub, band["rgb"])
    if band.get("border"):
        mask[-4:] = False
    out = []
    for x0, y0, x1, y1, count in components(dilate(mask)):
        x0, y0 = min(x0 + 2, x1 - 1), min(y0 + 2, y1 - 1)  # cadre ramené à sa taille avant épaississement
        x1, y1 = max(x1 - 2, x0 + 1), max(y1 - 2, y0 + 1)
        w, h = x1 - x0, y1 - y0
        if w < 28 or h < 14 or (w > 0.97 * width and h < 6):
            continue
        count = int(mask[y0:y1, x0:x1].sum())
        fill = count / (w * h)
        region = sub[y0:y1, x0:x1]
        frame = {"x": x0, "y": y0 + y_off, "width": w, "height": h}
        if fill >= 0.7:
            color, share = mode_color(region)
            frame.update(kind="fill" if share >= 0.55 else "image", color=hexa(color))
            if frame["kind"] == "image" and min(w, h) < 32:
                continue
        elif fill <= 0.4:
            edge = lambda line: float(line.mean()) if len(line) else 0.0  # noqa: E731
            mid_x, mid_y = slice(x0 + w // 5, x1 - w // 5), slice(y0 + h // 5, y1 - h // 5)
            sides = [edge(mask[y0:y0 + 3, mid_x].any(axis=0)), edge(mask[y1 - 3:y1, mid_x].any(axis=0)),
                     edge(mask[mid_y, x0:x0 + 3].any(axis=1)), edge(mask[mid_y, x1 - 3:x1].any(axis=1))]
            if min(sides) < 0.8:
                continue
            ring = sub[y0 + h // 2, x0:x0 + 3]
            color, _ = mode_color(ring.reshape(-1, 1, 3))
            frame.update(kind="outline", color=hexa(color))
        else:
            continue
        frame["radius"] = radius(mask, x0, y0) if frame["kind"] != "image" else 0
        out.append(frame)
    return out


# --- Textes (OCR local) ------------------------------------------------------------------------------------

def tesseract_langs(lang: str) -> str | None:
    binary = shutil.which("tesseract")
    if not binary:
        return None
    try:
        listed = subprocess.run([binary, "--list-langs"], capture_output=True, text=True, timeout=30).stdout.split()
    except (OSError, subprocess.SubprocessError):
        return None
    wanted = [{"fr": "fra", "en": "eng", "de": "deu", "es": "spa", "it": "ita", "nl": "nld"}.get(lang[:2], "eng"), "eng"]
    langs = [code for code in dict.fromkeys(wanted) if code in listed]
    return "+".join(langs) if langs else None


def ocr(image, langs: str, psm: int = 11, zoom: int = 2) -> list[dict]:
    """Mots reconnus par Tesseract (en local), coordonnées ramenées à l'image d'origine."""
    from PIL import Image
    big = image.convert("L").resize((image.width * zoom, image.height * zoom), Image.Resampling.LANCZOS)
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "ocr.png"
        big.save(source)
        try:
            done = subprocess.run([shutil.which("tesseract"), str(source), "stdout", "-l", langs, "--psm", str(psm), "tsv"],
                                  capture_output=True, text=True, encoding="utf-8", timeout=120,
                                  env={**os.environ, "OMP_THREAD_LIMIT": "1"})
        except (OSError, subprocess.SubprocessError):
            return []
    words = []
    for line in done.stdout.splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) < 12 or cols[0] != "5" or not cols[11].strip():
            continue
        text, conf = cols[11].strip(), float(cols[10])
        if conf < MIN_CONF or not re.search(r"\w", text):
            continue
        x, y, w, h = (round(int(v) / zoom) for v in cols[6:10])
        words.append({"text": text, "x": x, "y": y, "width": w, "height": h, "conf": round(conf),
                      "line": f"{cols[2]}.{cols[3]}.{cols[4]}"})
    return words


def font_px(word: dict) -> float:
    """Taille de police tirée de la hauteur d'encre du mot : jambage bas, lettre haute, ou minuscules seules."""
    chars = set(word["text"])
    if chars & DESCENDERS:
        return word["height"] / 1.05
    if chars & TALL:
        return word["height"] / 0.78
    return word["height"] / 0.55


def ink(arr, box: dict, background) -> str:
    """Couleur du texte : la plus éloignée du fond parmi les pixels du cadre."""
    import numpy as np
    region = arr[box["y"]:box["y"] + box["height"], box["x"]:box["x"] + box["width"]].reshape(-1, 3)
    if not len(region):
        return hexa(background)
    gap = np.abs(region - np.array(background, dtype=np.int16)).sum(axis=1)
    strong = region[gap >= gap.max() * 0.8]
    return hexa(strong.mean(axis=0))


def lines_of(words: list[dict]) -> list[dict]:
    """Regroupe les mots par ligne Tesseract ; taille de police médiane de la ligne."""
    groups: dict[str, list[dict]] = {}
    for word in words:
        groups.setdefault(word["line"], []).append(word)
    out = []
    for group in groups.values():
        group.sort(key=lambda w: w["x"])
        x0, y0 = min(w["x"] for w in group), min(w["y"] for w in group)
        x1, y1 = max(w["x"] + w["width"] for w in group), max(w["y"] + w["height"] for w in group)
        sizes = sorted(font_px(w) for w in group)
        out.append({"text": " ".join(w["text"] for w in group), "x": x0, "y": y0, "width": x1 - x0, "height": y1 - y0,
                    "font_px": round(sizes[len(sizes) // 2], 1), "words": group})
    return sorted(out, key=lambda line: (line["y"], line["x"]))


def texts(image, arr, frames_: list[dict], page_bands: list[dict], langs: str, side: dict | None = None) -> list[dict]:
    """Lignes de texte de la page ; les aplats sans texte reconnu sont relus seuls (texte clair sur fond coloré)."""
    from PIL import ImageOps
    words = ocr(image, langs)
    found = lines_of(words)
    for frame in frames_:
        if frame["kind"] != "fill" or frame["height"] > 120:
            continue
        if any(inside(line, frame) for line in found):
            continue
        crop = image.crop((frame["x"], frame["y"], frame["x"] + frame["width"], frame["y"] + frame["height"]))
        gray = crop.convert("L")
        if sum(frame_rgb(frame)) / 3 < 160:  # fond foncé ou saturé : texte clair, inversé pour Tesseract
            gray = ImageOps.invert(gray)
        extra = ocr(gray.convert("RGB"), langs, psm=7, zoom=3)
        for word in extra:
            word["x"] += frame["x"]
            word["y"] += frame["y"]
            word["line"] = f"f{frame['x']}.{frame['y']}"
        found += lines_of(extra)
    for line in found:
        band = band_at(page_bands, line["y"] + line["height"] / 2)
        background = page_bands[band]["rgb"] if band is not None else (255, 255, 255)
        if side and line["x"] + line["width"] / 2 < side["width"]:
            background = side["rgb"]
        line["color"] = ink(arr, line, background)
        for word in line["words"]:
            word.pop("line", None)
    return sorted(found, key=lambda line: (line["y"], line["x"]))


def frame_rgb(frame: dict) -> tuple[int, int, int]:
    return tuple(int(frame["color"][i:i + 2], 16) for i in (1, 3, 5))


def inside(box: dict, frame: dict, margin: int = 2) -> bool:
    cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] / 2
    return (frame["x"] - margin <= cx <= frame["x"] + frame["width"] + margin
            and frame["y"] - margin <= cy <= frame["y"] + frame["height"] + margin)


def band_at(page_bands: list[dict], y: float) -> int | None:
    for i, band in enumerate(page_bands):
        if band["y"] <= y < band["y"] + band["height"]:
            return i
    return None


# --- Analyse complète --------------------------------------------------------------------------------------

def cluster(values: list[float], tolerance: float = 0.12) -> list[int]:
    """Valeurs récurrentes : regroupées à tolérance relative, les plus fréquentes d'abord."""
    groups: list[list[float]] = []
    for value in sorted(v for v in values if v > 0):
        if groups and value <= groups[-1][0] * (1 + tolerance) + 1:
            groups[-1].append(value)
        else:
            groups.append([value])
    groups.sort(key=len, reverse=True)
    return sorted({round(sorted(g)[len(g) // 2]) for g in groups[:8]})


def sidebar(arr) -> dict | None:
    """Barre latérale à gauche : colonnes de même fond sur presque toute la hauteur, distinct du reste de la page."""
    height, width = arr.shape[:2]
    step_y = max(1, height // 240)
    cols = [mode_color(arr[::step_y, x]) for x in range(0, min(width, 420), 2)]
    rest, _ = mode_color(arr[::step_y, min(width - 1, 420)::4])
    first, share = cols[0]
    if share < 0.6 or distance(first, rest) <= 12:
        return None
    edge = 0
    for i, (color, part) in enumerate(cols):
        if distance(color, first) > 8 or part < 0.6:
            break
        edge = (i + 1) * 2
    if not 120 <= edge <= min(360, 0.35 * width):
        return None
    border = arr[::step_y, edge:edge + 3]
    line, part = mode_color(border)
    if part >= 0.8 and distance(line, rest) > 8 and distance(line, first) > 8:
        edge += next((k for k in range(3) if distance(mode_color(arr[::step_y, edge + k])[0], rest) <= 8), 3)
    return {"x": 0, "y": 0, "width": edge, "height": height, "rgb": first, "background": hexa(first)}


def analyze(image, langs: str | None) -> dict:
    """Bandes, colonnes, cadres, textes et mesures récurrentes d'une image (maquette ou rendu).

    Une barre latérale repérée à gauche est mesurée à part ; les bandes ne couvrent que la zone principale.
    """
    from PIL import Image
    image = image.convert("RGB") if hasattr(image, "convert") else Image.open(image).convert("RGB")
    full = load(image)
    height, width = full.shape[:2]
    side = sidebar(full)
    x0 = side["width"] if side else 0
    arr = full[:, x0:]
    page_bands = bands(arr)
    all_frames: list[dict] = []
    gaps: list[float] = []
    if side:
        side_frames = frames(full[:, :x0], {**side, "border": None}, x0)
        side["frames"] = side_frames
        all_frames += side_frames
    for band in page_bands:
        sub = arr[band["y"]:band["y"] + band["height"]]
        mask = content_mask(sub, band["rgb"])
        if band.get("border"):
            mask[-4:] = False
        band["columns"] = columns(mask, x0)
        for col in band["columns"]:
            col["top"] += band["y"]
            col["bottom"] += band["y"]
        if band["columns"]:
            top = min(c["top"] for c in band["columns"]) - band["y"]
            band["padding"] = [top, band["y"] + band["height"] - max(c["bottom"] for c in band["columns"])]
            gaps += [top] + [b["x"] - (a["x"] + a["width"]) for a, b in zip(band["columns"], band["columns"][1:])]
        else:
            band["padding"] = [0, 0]
        band_frames = frames(arr, band, width - x0)
        for frame in band_frames:
            frame["x"] += x0
        all_frames += band_frames
    page_texts = texts(image, full, all_frames, page_bands, langs, side) if langs else []
    for i, band in enumerate(page_bands):
        band.pop("rgb", None)
        band["x"] = x0
    if side:
        side.pop("rgb", None)
    sizes = [line["font_px"] for line in page_texts]
    return {"width": width, "height": height, "background": page_bands[0]["background"] if page_bands else "#ffffff",
            "sidebar": side, "bands": page_bands, "frames": all_frames, "texts": page_texts, "ocr": bool(langs),
            "measures": {"font_px": cluster(sizes), "spacing": cluster(gaps, 0.2),
                         "radii": cluster([f["radius"] for f in all_frames if f["kind"] != "image"], 0.3)}}


# --- Ébauche de description --------------------------------------------------------------------------------

class Draft:
    """Ébauche de description de page tirée de l'analyse ; tokens les plus proches du design system."""

    def __init__(self, analysis: dict, theme: dict, scale: float):
        self.a, self.theme, self.scale = analysis, theme, scale
        self.warnings: list[str] = []
        self.h1 = False
        sizes = sorted(line["font_px"] for line in analysis["texts"]) or [16.0]
        self.body_px = sizes[len(sizes) // 2]
        self.max_px = sizes[-1]

    def px(self, value: float) -> float:
        return value / self.scale

    def nearest(self, kind: str, value: float) -> str:
        scale = {"text": self.theme["font_sizes"], "space": self.theme["spacing"]}[kind]
        name = min(scale, key=lambda n: (abs(scale[n] - value), scale[n]))
        if abs(scale[name] - value) > max(8, 0.25 * value):
            label = {"text": "taille de police", "space": "espacement"}[kind]
            group = {"text": "font_sizes", "space": "spacing"}[kind]
            note = (f"{label} mesurée {round(value)} px, token le plus proche {name} ({scale[name]}) : ajoutez un token "
                    f"à {group} du design system (≈ {4 * round(value / 4)})")
            if note not in self.warnings:
                self.warnings.append(note)
        return name

    def color(self, value: str, where: str) -> str:
        from_hex = lambda h: tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))  # noqa: E731
        name, best = None, 10 ** 6
        for token, hex_ in self.theme["colors"].items():
            if isinstance(hex_, str) and hex_.startswith("#") and len(hex_) == 7:
                gap = distance(from_hex(hex_), from_hex(value))
                if gap < best:
                    name, best = token, gap
        if name is not None and best <= 36:
            return name
        self.warnings.append(f"{where} : couleur {value} sans token proche (design system à compléter)")
        return value

    def text_node(self, line: dict, column: dict | None) -> dict:
        size = self.px(line["font_px"])
        node: dict = {"text": line["text"]}
        if line["font_px"] >= 1.25 * self.body_px:
            level = 2
            if not self.h1 and line["font_px"] >= 0.9 * self.max_px:
                level, self.h1 = 1, True
            node = {"type": "heading", "level": level, **node, "size": self.nearest("text", size)}
        else:
            node = {"type": "text", **node}
            if abs(size - self.theme["font_sizes"].get("md", 16)) > 1.5:
                node["size"] = self.nearest("text", size)
            gray = line.get("color", "#000000")
            rgb = [int(gray[i:i + 2], 16) for i in (1, 3, 5)]
            if max(rgb) - min(rgb) < 40 and 70 < sum(rgb) / 3 < 170:
                node["muted"] = True
        if column and column["width"] > 3 * line["width"]:
            centre = line["x"] + line["width"] / 2 - (column["x"] + column["width"] / 2)
            if abs(centre) < 8 and line["x"] - column["x"] > 16:
                node["align"] = "center"
        return node

    def paragraphs(self, lines: list[dict]) -> list[dict]:
        """Lignes successives de même taille et proches : un seul paragraphe."""
        out: list[dict] = []
        for line in lines:
            last = out[-1] if out else None
            if (last and abs(last["font_px"] - line["font_px"]) < 2 and abs(last["x"] - line["x"]) < 8
                    and line["y"] - (last["y"] + last["height"]) < 0.8 * line["font_px"]):
                last.update(text=f"{last['text']} {line['text']}", height=line["y"] + line["height"] - last["y"],
                            width=max(last["width"], line["width"]))
            else:
                out.append(dict(line))
        return out

    def button(self, frame: dict, label: str) -> dict:
        variant = {"primary": "primary", "secondary": "secondary", "danger": "danger"}.get(
            self.color(frame["color"], "bouton"), "primary")
        return {"text": label, "variant": variant}

    def wide(self, frame: dict, label: str, node: dict) -> dict:
        """Bouton nettement plus large que son libellé : largeur reprise de la maquette."""
        guess = len(label) * self.body_px * 0.55 + 2 * 20 * self.scale
        if frame["width"] > 1.3 * guess:
            node["width"] = round(self.px(frame["width"]))
        return node

    def content(self, region: dict, lines: list[dict], frames_: list[dict]) -> list[dict]:
        """Blocs d'une colonne de haut en bas ; éléments alignés en lignes : grille, rangée, statistiques, tableau."""
        entries: list[dict] = []  # y, x, h, w, node
        used: set[int] = set()
        for frame in frames_:
            label = [line for line in lines if inside(line, frame)]
            box = {"y": frame["y"], "x": frame["x"], "h": frame["height"], "w": frame["width"]}
            if frame["kind"] == "fill" and label and frame["height"] <= 80:
                used.update(id(line) for line in label)
                text = " ".join(l["text"] for l in label)
                entries.append({**box, "button": self.wide(frame, text, self.button(frame, text))})
            elif frame["kind"] in ("fill", "image") and not label:
                image = {"type": "image", "crop": [frame["x"], frame["y"], frame["width"], frame["height"]], "alt": ""}
                if frame["width"] < 0.8 * region["width"]:  # image plus étroite que sa colonne : taille gardée
                    image.update(width=round(self.px(frame["width"])), height=round(self.px(frame["height"])))
                entries.append({**box, "node": image})
        for line in self.paragraphs([line for line in lines if id(line) not in used]):
            entries.append({"y": line["y"], "x": line["x"], "h": line["height"], "w": line["width"],
                            "px": line["font_px"], "node": self.text_node(line, region)})
        rows: list[list[dict]] = []
        for entry in sorted(entries, key=lambda e: (e["y"], e["x"])):
            last = rows[-1] if rows else None
            if last and abs(entry["y"] - last[0]["y"]) <= max(8 * self.scale, 0.6 * min(entry["h"], last[0]["h"])):
                last.append(entry)
            else:
                rows.append([entry])
        for row in rows:
            row.sort(key=lambda e: e["x"])
        out: list[dict] = []
        i = 0
        while i < len(rows):
            row = rows[i]
            if len(row) < 2 or all("button" in e for e in row):
                for entry in row:
                    self.append(out, entry)
                i += 1
                continue
            j = i + 1
            while j < len(rows) and len(rows[j]) == len(row) and \
                    all(abs(a["x"] - b["x"]) <= 16 * self.scale for a, b in zip(rows[j], row)):
                j += 1
            run = rows[i:j]
            texts_only = all(e.get("node", {}).get("type") in ("text", "heading") for r in run for e in r)
            if texts_only and len(run) >= 3:
                out.append(self.table(run))
            elif texts_only and len(run) == 2 and all(a["px"] < b["px"] for a, b in zip(run[0], run[1])):
                stats = [{"type": "stat", "label": a["node"]["text"], "value": b["node"]["text"]} for a, b in zip(run[0], run[1])]
                out.append({"type": "grid", "columns": len(stats), "children": stats})
            else:
                for r in run:
                    out.append(self.line(r, region))
            i = j
        return out

    def append(self, out: list[dict], entry: dict) -> None:
        if "button" in entry and "width" in entry["button"]:
            out.append({"type": "button", **entry["button"]})
        elif "button" in entry:
            if out and out[-1].get("type") == "buttons":
                out[-1]["items"].append(entry["button"])
            else:
                out.append({"type": "buttons", "items": [entry["button"]]})
        else:
            out.append(entry["node"])

    def line(self, row: list[dict], region: dict) -> dict:
        """Éléments côte à côte : rangée aux proportions de leurs positions."""
        right = region["x"] + region["width"]
        spans = [max(1, (b["x"] if b is not None else right) - a["x"]) for a, b in zip(row, row[1:] + [None])]
        base = min(spans)
        children = []
        for entry in row:
            holder: list[dict] = []
            self.append(holder, entry)
            children.append(holder[0])
        return {"type": "row", "columns": [round(s / base, 1) for s in spans], "valign": "center", "children": children}

    def table(self, run: list[list[dict]]) -> dict:
        """Lignes alignées sur les mêmes colonnes : tableau ; première ligne en en-tête si plus petite ou atténuée."""
        cells = [[e["node"]["text"] for e in r] for r in run]
        head = run[0]
        node: dict = {"type": "table"}
        if all(e["node"].get("muted") or e["px"] < run[1][0]["px"] * 0.95 for e in head):
            node["headers"] = cells.pop(0)
        node["rows"] = cells
        return node

    def card(self, frame: dict, lines: list[dict], frames_: list[dict]) -> dict:
        inner = [line for line in lines if inside(line, frame)]
        node: dict = {"type": "card", "height": round(self.px(frame["height"]))}
        if inner:
            node["title"] = inner[0]["text"]
            rest = self.paragraphs(inner[1:])
            if rest:
                node["text"] = " ".join(line["text"] for line in rest)
        others = [f for f in frames_ if f is not frame and inside(f, frame)]
        buttons = [self.button(f, " ".join(l["text"] for l in inner if inside(l, f))) for f in others
                   if f["kind"] == "fill" and any(inside(l, f) for l in inner)]
        if buttons:
            node["actions"] = buttons
            labels = {b["text"] for b in buttons}
            if node.get("text") in labels:
                node.pop("text")
        return node

    def column(self, column: dict, lines: list[dict], frames_: list[dict]) -> list[dict]:
        box = next((f for f in frames_ if f["kind"] == "outline" and f["width"] >= 0.8 * column["width"]
                    and f["x"] <= column["x"] + 4 and f["height"] >= 48), None)
        if box:
            return [self.card(box, lines, frames_)]
        return self.content(column, lines, [f for f in frames_ if f["kind"] != "outline"])

    def band(self, i: int, band: dict) -> dict | None:
        a = self.a
        y0, y1 = band["y"], band["y"] + band["height"]
        x0 = band.get("x", 0)
        lines = [line for line in a["texts"] if y0 <= line["y"] + line["height"] / 2 < y1
                 and line["x"] + line["width"] / 2 >= x0]
        frames_ = [f for f in a["frames"] if y0 <= f["y"] + f["height"] / 2 < y1 and f["x"] + f["width"] / 2 >= x0]
        where = f"bande {i + 1}"
        if i == 0 and band["height"] <= 120 * self.scale and lines and len(a["bands"]) > 1:
            return self.header(band, lines, frames_)
        if i == len(a["bands"]) - 1 and i > 0 and lines and band["height"] <= 200 * self.scale \
                and all(line["font_px"] <= self.body_px * 1.1 for line in lines):
            return {"type": "footer", "text": " ".join(line["text"] for line in self.paragraphs(lines))}
        if not lines and not frames_:
            return None
        node: dict = {"type": "section"}
        if band["background"] != a["background"]:
            node["background"] = self.color(band["background"], f"{where}/background")
        pad = self.px(band["padding"][0])
        if pad > 4:
            node["padding"] = self.nearest("space", pad)
        cols = band["columns"]
        if len(cols) >= 2:
            groups = [self.column(c, [l for l in lines if c["x"] - 4 <= l["x"] + l["width"] / 2 <= c["x"] + c["width"] + 4],
                                  [f for f in frames_ if c["x"] - 4 <= f["x"] + f["width"] / 2 <= c["x"] + c["width"] + 4])
                      for c in cols]
            widths = [c["width"] for c in cols]
            gap = self.nearest("space", self.px(min(b["x"] - a_["x"] - a_["width"] for a_, b in zip(cols, cols[1:]))))
            children = [g[0] if len(g) == 1 else {"type": "stack", "children": g} for g in groups if g]
            if len(children) != len(cols):
                node["children"] = [n for g in groups for n in g]
            elif max(widths) / max(1, min(widths)) < 1.25:
                node["children"] = [{"type": "grid", "columns": len(cols), "gap": gap, "children": children}]
            else:
                base = min(widths)
                node["children"] = [{"type": "row", "columns": [round(w / base, 1) for w in widths], "gap": gap,
                                     "children": children}]
        else:
            region = cols[0] if cols else {"x": 0, "width": a["width"]}
            node["children"] = self.content(region, lines, [f for f in frames_ if f["kind"] != "outline"]) or \
                [self.card(f, lines, frames_) for f in frames_ if f["kind"] == "outline"]
        return node if node.get("children") else None

    def header(self, band: dict, lines: list[dict], frames_: list[dict]) -> dict:
        node: dict = {"type": "header"}
        width = self.a["width"]
        buttons, rest = [], []
        for line in lines:
            frame = next((f for f in frames_ if f["kind"] == "fill" and inside(line, f)), None)
            (buttons if frame else rest).append((line, frame))
        rest.sort(key=lambda item: item[0]["x"])
        if rest and rest[0][0]["x"] < width * 0.3:
            node["text"] = rest.pop(0)[0]["text"]
        mark = next((f for f in sorted(frames_, key=lambda f: f["x"]) if f["kind"] in ("fill", "image")
                     and not any(inside(l, f) for l in lines) and f["x"] < width * 0.3), None)
        if mark:
            node["crop"] = [mark["x"], mark["y"], mark["width"], mark["height"]]
            node["alt"] = ""
        if rest:
            node["items"] = [line["text"] for line, _ in rest]
        if buttons:
            node["actions"] = [self.button(frame, line["text"]) for line, frame in buttons]
        return node

    def max_width(self) -> int | None:
        """Largeur du conteneur : bord gauche le plus fréquent des contenus, moins la marge intérieure (lg)."""
        lefts = [b["columns"][0]["x"] - b.get("x", 0) for b in self.a["bands"] if b["columns"]]
        if not lefts:
            return None
        area = self.a["width"] - (self.a["sidebar"]["width"] if self.a.get("sidebar") else 0)
        left = max(set(lefts), key=lefts.count) / self.scale
        width = area / self.scale - 2 * max(0, left - self.theme["spacing"].get("lg", 24))
        return int(width) if 320 <= width < area / self.scale else None

    def sidebar(self, children: list[dict]) -> dict:
        """Barre latérale : marque (premier texte en haut), entrées de navigation, entrée active sur un aplat."""
        side = self.a["sidebar"]
        lines = sorted((l for l in self.a["texts"] if l["x"] + l["width"] / 2 < side["width"]), key=lambda l: l["y"])
        node: dict = {"type": "sidebar", "width": round(self.px(side["width"]))}
        if side["background"] != self.a["background"]:
            node["background"] = self.color(side["background"], "sidebar/background")
        if lines and (lines[0]["font_px"] > 1.15 * self.body_px or len(lines) > 1 and lines[1]["y"] - lines[0]["y"] > 40 * self.scale):
            node["text"] = lines.pop(0)["text"]
        items = []
        for line in lines:
            words = line["text"].split()
            if len(words) > 1 and len(words[0]) == 1:  # pictogramme lu comme une lettre
                words = words[1:]
            item: dict = {"text": " ".join(words)}
            if any(f["kind"] == "fill" and inside(line, f) for f in side.get("frames", [])):
                item["active"] = True
            items.append(item)
        node["items"] = items or [{"text": "Accueil"}]
        if not items:
            self.warnings.append("sidebar : aucune entrée lue ; recopiez les entrées de navigation")
        node["children"] = children
        return node

    def page(self, title_hint: str) -> list[dict]:
        body = [n for n in (self.band(i, b) for i, b in enumerate(self.a["bands"])) if n]
        if self.a.get("sidebar"):
            body = [self.sidebar(body)]
        if not self.h1:
            for node in self.walk(body):
                if node.get("type") == "heading":
                    node["level"], self.h1 = 1, True
                    break
        if not self.h1:
            self.warnings.append(f"{title_hint} : aucun titre principal repéré ; ajoutez un heading de niveau 1")
        return body

    def walk(self, nodes: list[dict]):
        for node in nodes:
            yield node
            yield from self.walk(node.get("children", []))


# --- Comparaison structurelle (page_build.py) -----------------------------------------------------------

DOM_SCRIPT = """() => {
  const nodes = [], words = [];
  document.querySelectorAll('[data-node]').forEach(el => {
    const r = el.getBoundingClientRect();
    nodes.push({node: el.dataset.node, x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height});
  });
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let t;
  while ((t = walker.nextNode())) {
    const re = /\\S+/g; let m;
    while ((m = re.exec(t.data))) {
      const range = document.createRange();
      range.setStart(t, m.index); range.setEnd(t, m.index + m[0].length);
      const r = range.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      const host = t.parentElement && t.parentElement.closest('[data-node]');
      words.push({text: m[0], x: r.x + scrollX, y: r.y + scrollY, width: r.width, height: r.height,
                  node: host ? host.dataset.node : null});
    }
  }
  return {nodes, words};
}"""
SEVERITY = {"band-missing": 0, "text-missing": 1, "frame-missing": 2, "frame": 3, "band": 4, "text-size": 5,
            "text-offset": 6, "text-extra": 7}


def norm(word: str) -> str:
    return re.sub(r"[^\w]", "", word.casefold())


def iou(a: dict, b: dict) -> float:
    x0, y0 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x1 = min(a["x"] + a["width"], b["x"] + b["width"])
    y1 = min(a["y"] + a["height"], b["y"] + b["height"])
    inter = max(0, x1 - x0) * max(0, y1 - y0)
    union = a["width"] * a["height"] + b["width"] * b["height"] - inter
    return inter / union if union else 0.0


def overlap(a: dict, b: dict) -> float:
    """Part du plus petit des deux cadres couverte par l'autre."""
    x0, y0 = max(a["x"], b["x"]), max(a["y"], b["y"])
    x1 = min(a["x"] + a["width"], b["x"] + b["width"])
    y1 = min(a["y"] + a["height"], b["y"] + b["height"])
    smallest = min(a["width"] * a["height"], b["width"] * b["height"])
    return max(0, x1 - x0) * max(0, y1 - y0) / smallest if smallest else 0.0


def node_at(dom_nodes: list[dict], box: dict, prefer_small: bool = True) -> str | None:
    """Nœud le plus petit du DOM qui contient le centre du cadre (coordonnées de la maquette)."""
    hits = [n for n in dom_nodes if inside(box, n, 1)]
    if not hits:
        return None
    return min(hits, key=lambda n: n["width"] * n["height"] if prefer_small else -n["width"] * n["height"])["node"]


def short(text: str, size: int = 32) -> str:
    return text if len(text) <= size else text[:size - 1] + "…"


def structure(mockup: dict, render: dict, dom: dict, scale: float, theme: dict | None = None) -> dict:
    """Compare l'analyse de la maquette à celle du rendu ; écarts rattachés aux nœuds de la description.

    Coordonnées en pixels de la maquette ; les messages les donnent en px CSS (divisés par scale).
    """
    css = lambda v: round(v / scale)  # noqa: E731
    dom_nodes = [{**n, **{k: n[k] * scale for k in ("x", "y", "width", "height")}} for n in dom.get("nodes", [])]
    dom_words = [{**w, **{k: w[k] * scale for k in ("x", "y", "width", "height")}} for w in dom.get("words", [])]
    tops = [n for n in dom_nodes if n["node"].count("/") == 1]
    issues: list[dict] = []
    parts: dict = {"texts": None, "positions": None, "bands": None, "frames": None}

    # Bandes : appariées dans l'ordre par couleur de fond ; décalage vertical propagé aux contenus.
    shifts: list[tuple[float, float]] = []  # (y de la bande dans la maquette, décalage du rendu)
    j, weight, got = 0, 0.0, 0.0
    for band in mockup["bands"]:
        if band["height"] < MIN_BAND:
            continue
        weight += band["height"]
        target = from_hex(band["background"])
        match = None
        for k in range(j, len(render["bands"])):
            if distance(from_hex(render["bands"][k]["background"]), target) <= 36:
                match = k
                break
        if match is None:
            same_y = next((b for b in render["bands"] if b["y"] <= band["y"] + band["height"] / 2 < b["y"] + b["height"]), None)
            seen = f" ; le rendu y a le fond {same_y['background']}" if same_y else ""
            node = node_at(tops, {**band, "x": 0, "width": mockup["width"]}) if tops else None
            issues.append({"node": node, "kind": "band-missing",
                           "message": f"bande de fond {band['background']} (y {css(band['y'])}, hauteur "
                                      f"{css(band['height'])} px) absente du rendu{seen} : section ou background à revoir"})
            continue
        j = match + 1
        other = render["bands"][match]
        shifts.append((band["y"], other["y"] - band["y"]))
        gap = other["height"] - band["height"]
        got += band["height"] * max(0.0, 1 - abs(gap) / band["height"])
        if abs(gap) > max(8 * scale, 0.06 * band["height"]):
            node = node_at(tops, {"x": mockup["width"] / 2 - 1, "y": other["y"], "width": 2, "height": other["height"]})
            hint = "padding ou espacements trop grands" if gap > 0 else "padding ou espacements trop petits, contenu manquant"
            issues.append({"node": node, "kind": "band",
                           "message": f"{node or 'bande'} : hauteur {css(other['height'])} px au lieu de "
                                      f"{css(band['height'])} ({hint})"})
    parts["bands"] = round(got / weight, 3) if weight else None

    def shift_at(y: float) -> float:
        best = 0.0
        for top, value in shifts:
            if top <= y:
                best = value
        return best

    # Cadres : meilleur recouvrement, une fois le décalage de la bande retiré.
    area, score = 0.0, 0.0
    for frame in mockup["frames"]:
        size = frame["width"] * frame["height"]
        area += size
        moved = {**frame, "y": frame["y"] + shift_at(frame["y"])}
        candidates = [(iou(moved, f), f) for f in render["frames"] if f["kind"] == frame["kind"] or
                      {f["kind"], frame["kind"]} <= {"fill", "image"}]
        best, other = max(candidates, key=lambda c: (c[0], overlap(moved, c[1])), default=(0.0, None))
        if other is not None and best < 0.3:  # même cadre redimensionné : le plus recouvrant
            near = max(candidates, key=lambda c: overlap(moved, c[1]))
            if overlap(moved, near[1]) >= 0.5:
                best, other = near
            else:  # même taille, à peu de distance : simplement décalé
                close = [c for c in candidates if abs(c[1]["width"] - frame["width"]) <= 0.2 * frame["width"]
                         and abs(c[1]["height"] - frame["height"]) <= 0.2 * frame["height"]
                         and abs(c[1]["x"] - moved["x"]) + abs(c[1]["y"] - moved["y"]) <= 64 * scale]
                if close:
                    best, other = min(close, key=lambda c: abs(c[1]["x"] - moved["x"]) + abs(c[1]["y"] - moved["y"]))
                    best = max(best, 0.3)
        score += size * best
        label = {"fill": "aplat", "outline": "cadre", "image": "image"}[frame["kind"]]
        if other is None or best < 0.3:
            node = node_at(dom_nodes, moved)
            issues.append({"node": node, "kind": "frame-missing",
                           "message": f"{label} {css(frame['width'])}×{css(frame['height'])} ({frame.get('color')}) à "
                                      f"({css(frame['x'])}, {css(frame['y'])}) sans équivalent dans le rendu"
                                      + (f" ; le plus proche : {node}" if node else "")})
        elif best < 0.75:
            node = node_at(dom_nodes, other)
            dx, dy = other["x"] - moved["x"], other["y"] - moved["y"]
            issues.append({"node": node, "kind": "frame",
                           "message": f"{node or label} : {css(other['width'])}×{css(other['height'])} px au lieu de "
                                      f"{css(frame['width'])}×{css(frame['height'])}"
                                      + (f", décalé de ({css(dx)}, {css(dy)})" if abs(dx) + abs(dy) > 6 * scale else "")})
    parts["frames"] = round(score / area, 3) if area else None

    # Textes : présents dans le DOM (texte exact) ; position et taille comparées encre contre encre (OCR des deux).
    if mockup.get("ocr") and mockup["texts"]:
        dom_norms = [norm(w["text"]) for w in dom_words]
        dom_set = set(dom_norms)
        total, present = 0, 0
        for line in mockup["texts"]:
            missing = []
            for word in line["words"]:
                key = norm(word["text"])
                if len(key) < 2:
                    continue
                total += 1
                if key in dom_set or difflib.get_close_matches(key, dom_set, n=1, cutoff=0.8):
                    present += 1
                else:
                    missing.append(word["text"])
            if missing and len(missing) >= max(1, len(line["words"]) // 2):
                node = node_at(dom_nodes, {**line, "y": line["y"] + shift_at(line["y"])})
                issues.append({"node": node, "kind": "text-missing",
                               "message": f"texte « {short(line['text'])} » (y {css(line['y'])}, {css(line['font_px'])} px) "
                                          f"absent du rendu" + (f", près de {node}" if node else "")})
        parts["texts"] = round(present / total, 3) if total else None
        mockup_norms = {norm(w["text"]) for line in mockup["texts"] for w in line["words"]}
        extra: dict[str, list[str]] = {}
        for word, key in zip(dom_words, dom_norms):
            if len(key) >= 3 and key not in mockup_norms and not difflib.get_close_matches(key, mockup_norms, n=1, cutoff=0.8):
                extra.setdefault(word.get("node") or "?", []).append(word["text"])
        for node, words in list(extra.items())[:4]:
            issues.append({"node": None if node == "?" else node, "kind": "text-extra",
                           "message": f"{node} : texte « {short(' '.join(words))} » absent de la maquette (inventé ou mal lu)"})
        checked, good = 0, 0
        seen_nodes: set[str] = set()
        for line in mockup["texts"]:
            options = [(difflib.SequenceMatcher(None, line["text"].casefold(), r["text"].casefold()).ratio(), r)
                       for r in render["texts"]]
            options = [o for o in options if o[0] >= 0.8]
            if not options:
                continue
            ratio, other = min(options, key=lambda o: abs(o[1]["y"] - line["y"]) + abs(o[1]["x"] - line["x"]) - 100 * o[0])
            checked += 1
            dx = other["x"] - line["x"]
            dy = other["y"] - line["y"] - shift_at(line["y"])
            size = other["font_px"] / line["font_px"] if line["font_px"] else 1.0
            word = other["words"][0] if other.get("words") else other
            hit = next((w for w in dom_words if inside(word, w, 2)), None)
            node = hit["node"] if hit else node_at(dom_nodes, other)
            notes = []
            if abs(dy) > max(8 * scale, 0.5 * line["font_px"]):
                notes.append(f"{css(abs(dy))} px trop {'bas' if dy > 0 else 'haut'}")
            if abs(dx) > max(8 * scale, 0.5 * line["font_px"]):
                notes.append(f"{css(abs(dx))} px trop à {'droite' if dx > 0 else 'gauche'}")
            kind = "text-offset"
            if not 0.87 <= size <= 1.15:
                kind = "text-size"
                want = line["font_px"] / scale
                token = ""
                if theme:
                    sizes = theme["font_sizes"]
                    token = min(sizes, key=lambda n: abs(sizes[n] - want))
                    token = f", token {token}"
                notes.append(f"police {'trop grande' if size > 1 else 'trop petite'} ({round(want)} px attendus{token})")
            good += max(0.0, 1 - (abs(dx) + abs(dy)) / (3 * line["font_px"])) * max(0.0, 1 - 2 * abs(size - 1))
            if not notes:
                continue
            if node in seen_nodes:
                continue
            seen_nodes.add(node or "")
            issues.append({"node": node, "kind": kind,
                           "message": f"{node or 'texte'} « {short(line['text'], 24)} » : " + ", ".join(notes)})
        parts["positions"] = round(good / checked, 3) if checked else None
    issues.sort(key=lambda i: SEVERITY[i["kind"]])
    return {"parts": parts, "issues": issues}


def from_hex(value: str) -> tuple[int, int, int]:
    return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))


def theme_of(tokens_path: Path | None, report: dict) -> tuple[dict | None, object]:
    ds = skill_paths.load_module("design-system", "ds_build.py")
    if ds is None:
        report["errors"].append(skill_paths.absent("design-system", "ds_build.py"))
        return None, None
    tokens = {}
    if tokens_path:
        try:
            tokens = json.loads(tokens_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            report["errors"].append(f"tokens : {tokens_path} illisible ({error}) ; ds_extract.py --draft l'écrit")
            return None, ds
        report["errors"] += ds.tokens_errors(tokens)
        if report["errors"]:
            return None, ds
    theme, _ = ds.complete(tokens)
    return theme, ds


def relative(path: Path, start: Path) -> str:
    """Chemin relatif au dossier de la description ; absolu s'ils sont sur deux lecteurs (Windows)."""
    try:
        return Path(os.path.relpath(path.resolve(), start.resolve())).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("images", nargs="*", type=Path)
    parser.add_argument("--tokens", type=Path)
    parser.add_argument("--draft", action="store_true")
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--scale", type=float, default=1.0)
    parser.add_argument("--lang", default="fr")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    report: dict = {"errors": [], "warnings": []}
    if not args.images:
        script_report.print_report([], ["maquette manquante (MAQUETTE.png...)"])
        return 1
    theme, ds = theme_of(args.tokens, report)
    if theme is None:
        script_report.print_report([], report["errors"])
        return 1
    try:
        from PIL import Image
    except ImportError:
        script_report.print_report([], ["Pillow manquant : lancez ce script avec `uv run`"])
        return 1
    langs = tesseract_langs(args.lang)
    warnings = [] if langs else ["textes non mesurés : Tesseract absent (check-prerequisites, groupe maquettes) ; "
                                 "bandes, colonnes et cadres mesurés seuls"]
    results = []
    for path in args.images:
        result: dict = {"input": str(path), "analysis": None, "draft": None, "size": None, "bands": 0, "columns": 0,
                        "frames": 0, "texts": 0, "font_px": [], "spacing": [], "radii": [], "errors": [], "warnings": []}
        results.append(result)
        try:
            image = Image.open(path)
            image.load()
        except OSError as error:
            result["errors"].append(f"maquette illisible ({error})")
            continue
        out_dir = args.out_dir or path.parent
        analysis_path = out_dir / f"{path.stem}.analysis.json"
        draft_path = out_dir / f"{path.stem}.json"
        if args.draft and draft_path.exists() and not args.force:
            result["errors"].append(f"{draft_path.name} existe déjà : --force pour le remplacer, ou --out-dir")
            continue
        analysis = analyze(image, langs)
        analysis["scale"] = args.scale
        out_dir.mkdir(parents=True, exist_ok=True)
        analysis_path.write_text(json.dumps(analysis, ensure_ascii=False), encoding="utf-8")
        m = analysis["measures"]
        result.update(analysis=str(analysis_path), size=[analysis["width"], analysis["height"]],
                      bands=len(analysis["bands"]), columns=sum(len(b["columns"]) for b in analysis["bands"]),
                      frames=len(analysis["frames"]), texts=len(analysis["texts"]),
                      font_px=[round(v / args.scale) for v in m["font_px"]],
                      spacing=[round(v / args.scale) for v in m["spacing"]],
                      radii=[round(v / args.scale) for v in m["radii"]])
        if args.draft:
            draft = Draft(analysis, theme, args.scale)
            title = next((l["text"] for l in sorted(analysis["texts"], key=lambda l: -l["font_px"])), path.stem)
            spec = {"title": title, "mockup": relative(path, out_dir)}
            if args.tokens:
                spec["tokens"] = relative(args.tokens, out_dir)
            if args.scale != 1:
                spec["scale"] = args.scale
            if draft.max_width():
                spec["max_width"] = draft.max_width()
            spec["body"] = draft.page(path.name)
            errors = skill_paths_validate(spec)
            if errors:
                result["errors"] += [f"ébauche hors schéma (à signaler) : {e}" for e in errors[:3]]
                continue
            draft_path.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            result["draft"] = str(draft_path)
            result["warnings"] += draft.warnings[:8]
    script_report.print_report(results, report["errors"], warnings + report["warnings"])
    return 1 if any(r["errors"] for r in results) else 0


def skill_paths_validate(spec: dict) -> list[str]:
    """L'ébauche suit le schéma de page_build.py (même skill)."""
    from spec_schema import validate
    return validate(spec, str(Path(__file__).resolve().parent / "page_build.py"))


if __name__ == "__main__":
    sys.exit(main())
