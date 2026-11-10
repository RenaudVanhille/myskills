# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.48"]
# ///
"""Exporte des schémas en PNG, SVG ou PDF, ou vérifie seulement qu'ils se rendent.

Formats reconnus :
- `.drawio` : draw.io Desktop, vers `<nom>.drawio.png` ou `.drawio.svg` qui gardent le
  XML et restent donc modifiables dans draw.io ;
- `.mmd`, `.mermaid` : bibliothèque Mermaid dans un navigateur local (Playwright) ;
- `.md` : chaque bloc ```mermaid du fichier, exporté en `<nom>-1.svg`, `<nom>-2.svg`... ;
- `.excalidraw` : bibliothèque Excalidraw dans un navigateur local (Playwright), vers
  `<nom>.excalidraw.png` ou `.excalidraw.svg` qui embarquent la scène ;
- `.c4` ou dossier LikeC4 : LikeC4 (`likec4`, sinon `npx likec4`), une image par vue.

Avec --check, rien n'est écrit : le script rend dans un dossier temporaire et
signale les erreurs. Affiche un rapport JSON. Usage :
    uv run scripts/export.py SCHEMA [...] [--format png|svg|pdf] [--scale 2]
        [--out DOSSIER] [--transparent] [--check]
"""

import argparse
import base64
import json
import mimetypes
import os
import platform
import re
import shutil
import subprocess
import sys
import struct
import tempfile
from contextlib import contextmanager
import zlib
from pathlib import Path
from urllib.parse import quote, unquote

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import local_tools  # noqa: E402
from script_report import print_report  # noqa: E402

LIKEC4 = "likec4@1"
MERMAID_BLOCK = re.compile(r"^```mermaid[ \t]*\n(.*?)^```", re.M | re.S)
DEAD_PROXY = local_tools.DEAD_PROXY
ANSI = re.compile(r"\x1b\[[0-9;]*m")
NO_SANDBOX = local_tools.NO_SANDBOX


class ExportError(Exception):
    pass


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300,
        env: dict | None = None) -> None:
    # Pas de vérification de mise à jour de draw.io Desktop pendant l'export.
    env = {**os.environ, "DRAWIO_DISABLE_UPDATE": "true", **(env or {})}
    try:
        proc = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True,
                              encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        raise ExportError(f"Délai dépassé : {Path(cmd[0]).name}")
    if proc.returncode != 0:
        output = ANSI.sub("", proc.stderr + proc.stdout)
        lines = [l for l in output.splitlines()
                 if l.strip() and not l.lstrip().startswith("at ") and "node_modules" not in l
                 and not re.search(r"\b(INFO|DEBUG)\b", l)]
        raise ExportError("\n".join(lines[-8:]) or f"{Path(cmd[0]).name} : code {proc.returncode}")


def node_tool(binary: str, package: str) -> list[str]:
    """Commande locale si installée, sinon `npx -y paquet`."""
    found = shutil.which(binary)
    if found:
        return [found]
    if local_tools.offline():
        raise ExportError(f"{binary} introuvable (mode hors ligne, npx ne peut rien télécharger) : "
                          f"installez-le avant, `npm install -g {package.split('@')[0] or package}`")
    npx = shutil.which("npx")
    if not npx:
        raise ExportError(f"{binary} introuvable et Node.js absent : installez Node.js "
                          "(https://nodejs.org/), voir le skill check-prerequisites.")
    return [npx, "-y", "-p", package, binary]


def drawio_binary() -> str:
    found = local_tools.drawio_binary()
    if not found:
        raise ExportError("draw.io Desktop introuvable : "
                          "https://github.com/jgraph/drawio-desktop/releases")
    return found


def cache_dir() -> Path:
    return local_tools.cache_dir()


# --- draw.io -----------------------------------------------------------------

# Premier numéro de page de --page-index : 0 avant draw.io Desktop 27.0.2, 1 depuis. Un export en
# base 0 refusé (« pages are numbered from 1 ») fait passer en base 1 pour le reste du traitement.
PAGE_BASE = [0]


def export_drawio(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    """Une image par page : <nom>.drawio.png pour la première, <nom>-2.drawio.png...
    pour les suivantes ; un seul PDF avec toutes les pages."""
    xml = src.read_text(encoding="utf-8")
    pages = 1 if fmt == "pdf" else max(1, len(re.findall(r"<diagram[\s>]", xml)))
    targets = []
    for index in range(1, pages + 1):
        suffix = "" if index == 1 else f"-{index}"
        target = out / f"{src.stem}{suffix}.drawio.{fmt}"
        cmd = [drawio_binary(), "--export", "--format", fmt, "--output", str(target)]
        if fmt == "svg":
            cmd.append("--embed-diagram")
        if fmt == "png":
            cmd += ["--scale", str(scale)]
            if transparent:
                cmd.append("--transparent")
        tail = ["--no-sandbox"] if NO_SANDBOX else []
        tail.append(str(src))
        if platform.system() == "Linux" and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
            cmd = ["xvfb-run", "-a"] + cmd
        offline = {k: DEAD_PROXY for k in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy")}
        offline |= {"NO_PROXY": "", "no_proxy": ""}

        def page() -> list[str]:
            return ["--all-pages"] if fmt == "pdf" else ["--page-index", str(index - 1 + PAGE_BASE[0])]
        try:
            run(cmd + page() + tail, env=offline)
        except ExportError as error:
            if fmt == "pdf" or PAGE_BASE[0] or "numbered from 1" not in str(error):
                raise
            PAGE_BASE[0] = 1
            run(cmd + page() + tail, env=offline)
        if not target.is_file():
            raise ExportError("draw.io n'a rien produit (fichier vide ou XML invalide ?)")
        if fmt == "png":
            embed_drawio(target, xml)
        targets.append(target)
    return targets


def embed_drawio(png: Path, xml: str) -> None:
    """Glisse le XML dans le PNG (chunk tEXt « mxfile », lu par draw.io).

    L'option --embed-diagram de draw.io Desktop produit des PNG que certains
    lecteurs refusent ; on exporte donc sans, puis on ajoute le chunk ici.
    """
    data = png.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ExportError("PNG draw.io illisible")
    payload = b"mxfile\x00" + quote(xml, safe="").encode("ascii")
    chunk = struct.pack(">I", len(payload)) + b"tEXt" + payload
    chunk += struct.pack(">I", zlib.crc32(b"tEXt" + payload) & 0xFFFFFFFF)
    end_of_header = 8 + 12 + struct.unpack(">I", data[8:12])[0]
    png.write_bytes(data[:end_of_header] + chunk + data[end_of_header:])


# --- Mermaid -----------------------------------------------------------------

MERMAID_RENDER = """async ({code, transparent}) => {
    if (!window.mermaid) {
        await new Promise((ok, ko) => {
            const s = document.createElement("script");
            s.src = "http://local.myskills/dist/mermaid.min.js";
            s.onload = ok; s.onerror = () => ko(new Error("mermaid.min.js introuvable"));
            document.head.appendChild(s);
        });
        mermaid.initialize({startOnLoad: false, securityLevel: "strict", theme: "default",
                            fontFamily: "Helvetica, Arial, sans-serif"});
    }
    document.body.innerHTML = "";
    document.body.style.background = transparent ? "transparent" : "white";
    try {
        const {svg} = await mermaid.render("schema" + Date.now(), code);
        const box = document.createElement("div");
        box.id = "schema";
        box.style.cssText = "display:inline-block;padding:16px";
        box.innerHTML = svg;
        document.body.appendChild(box);
        return {svg};
    } catch (error) {
        document.querySelectorAll("[id^=dschema]").forEach((n) => n.remove());
        return {error: String(error.message || error)};
    }
}"""


def export_mermaid(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    text = src.read_text(encoding="utf-8")
    if src.suffix.lower() == ".md":
        blocks = MERMAID_BLOCK.findall(text)
        if not blocks:
            raise ExportError("Aucun bloc ```mermaid dans ce fichier")
        names = [f"{src.stem}-{i}" for i in range(1, len(blocks) + 1)]
    else:
        blocks, names = [text], [src.stem]
    package = npm_package("mermaid")
    outputs, errors = [], []
    try:
        with local_page(package, scale) as page:
            for index, (block, name) in enumerate(zip(blocks, names), 1):
                result = page.evaluate(MERMAID_RENDER, {"code": block, "transparent": transparent})
                if result.get("error"):
                    label = f"bloc {index}" if src.suffix.lower() == ".md" else src.name
                    errors.append(f"{label} : {result['error'].strip()}")
                    continue
                target = out / f"{name}.{fmt}"
                if fmt == "svg":
                    target.write_text(result["svg"], encoding="utf-8")
                elif fmt == "png":
                    page.locator("#schema").screenshot(path=str(target), omit_background=transparent)
                else:
                    box = page.locator("#schema").bounding_box()
                    page.pdf(path=str(target), width=f"{int(box['width']) + 2}px",
                             height=f"{int(box['height']) + 2}px", print_background=True,
                             page_ranges="1")
                outputs.append(target)
    except ExportError:
        raise
    except Exception as error:
        raise ExportError("Rendu Mermaid impossible : " + str(error).splitlines()[0])
    if errors:
        raise ExportError("\n".join(errors))
    return outputs


# --- LikeC4 ------------------------------------------------------------------

def export_likec4(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    folder = src if src.is_dir() else src.parent
    tool = node_tool("likec4", LIKEC4)
    run(tool + ["validate", str(folder)])
    if fmt != "png":
        raise ExportError("LikeC4 n'exporte qu'en PNG ; utilisez --format png "
                          "(ou `likec4 gen mermaid` pour du Markdown)")
    before = set(out.glob("*.png"))
    run(tool + ["export", "png", str(folder), "--output", str(out)], timeout=600)
    produced = sorted(set(out.glob("*.png")) - before) or sorted(out.glob("*.png"))
    if not produced:
        raise ExportError("LikeC4 n'a exporté aucune vue (aucun bloc `views` ?)")
    return produced


# --- Excalidraw --------------------------------------------------------------

def npm_package(name: str) -> Path:
    """Paquet npm à version fixée, vérifié par son empreinte (local_tools)."""
    try:
        return local_tools.npm_package(name)
    except local_tools.PackageError as error:
        raise ExportError(str(error)) from error


def launch_browser(pw):
    try:
        return local_tools.launch_chromium(pw)
    except local_tools.PackageError as error:
        raise ExportError(str(error)) from error


@contextmanager
def local_page(package: Path, scale: float = 1):
    """Page Chromium (Playwright) qui ne voit que les fichiers du paquet en cache :
    toute autre requête est bloquée, le rendu reste local."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ExportError("Playwright manquant : lancez ce script avec `uv run`")

    def serve(route):
        rel = unquote(route.request.url.split("://local.myskills/", 1)[1].split("?")[0])
        path = package / rel
        if rel == "page.html":
            route.fulfill(body="<!doctype html><html><head><meta charset='utf-8'></head>"
                               "<body style='margin:0'></body></html>", content_type="text/html")
        elif path.is_file():
            kind = mimetypes.guess_type(path.name)[0] or "application/javascript"
            route.fulfill(body=path.read_bytes(), content_type=kind)
        else:
            route.fulfill(status=404, body="")

    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            page = browser.new_page(device_scale_factor=scale)
            page.route("**/*", lambda route: route.abort())
            page.route("http://local.myskills/**", serve)
            page.goto("http://local.myskills/page.html")
            yield page
        finally:
            browser.close()


def export_excalidraw(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    if fmt == "pdf":
        raise ExportError("Excalidraw s'exporte en PNG ou SVG")
    scene = json.loads(src.read_text(encoding="utf-8"))
    if scene.get("type") != "excalidraw":
        raise ExportError("Ce fichier n'est pas une scène Excalidraw "
                          "(lancez d'abord excalidraw_build.py)")
    package = npm_package("@excalidraw/utils")
    target = out / f"{src.stem}.excalidraw.{fmt}"
    try:
        with local_page(package) as page:
            result = page.evaluate("""async ({scene, fmt, scale, transparent}) => {
                window.EXCALIDRAW_ASSET_PATH = "http://local.myskills/dist/prod/";
                const lib = await import("http://local.myskills/dist/prod/index.js");
                const elements = scene.elements.filter((e) => !e.isDeleted);
                const config = {padding: 20, scale, embedScene: true};
                if (transparent) config.canvasBackgroundColor = false;
                const data = {elements, appState: scene.appState || {}, files: scene.files || {}};
                const output = await lib.exportScene({type: fmt, data, config});
                if (fmt === "svg") return output.outerHTML;
                const bytes = new Uint8Array(await output.arrayBuffer());
                let binary = "";
                for (let i = 0; i < bytes.length; i += 0x8000)
                    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
                return btoa(binary);
            }""", {"scene": scene, "fmt": fmt, "scale": scale, "transparent": transparent})
    except ExportError:
        raise
    except Exception as error:
        raise ExportError("Rendu Excalidraw impossible : " + str(error).splitlines()[0])
    if fmt == "svg":
        target.write_text(result, encoding="utf-8")
    else:
        target.write_bytes(base64.b64decode(result))
    return [target]


# --- Commun ------------------------------------------------------------------

def image_warnings(path: Path) -> list[str]:
    """Contrôle du rendu sans le regarder : image trop petite, presque uniforme (vide),
    SVG sans texte ni tracé. Le modèle n'ouvre l'image que s'il y a un doute ou pour la relecture."""
    name = path.name
    if path.suffix.lower() == ".svg":
        text = path.read_text(encoding="utf-8", errors="replace")
        return [] if re.search(r"<(text|path|foreignObject|rect|line|polygon)\b", text) else \
            [f"{name} : SVG sans texte ni tracé (rendu vide ?)"]
    if path.suffix.lower() != ".png":
        return []
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n" or len(data) < 33:
        return [f"{name} : PNG illisible"]
    width, height, depth, color = struct.unpack(">IIBB", data[16:26])
    warnings = []
    if min(width, height) < 64:
        warnings.append(f"{name} : image de {width} x {height} px, trop petite pour être lue")
    # Taille compressée des pixels rapportée à leur taille brute : une image presque
    # uniforme se compresse à presque rien.
    idat, pos = 0, 8
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        if kind == b"IDAT":
            idat += length
        pos += 12 + length
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}.get(color, 4)
    raw = height * (width * channels * max(depth, 8) // 8 + 1)
    if raw and idat / raw < 0.004:
        warnings.append(f"{name} : image presque uniforme (rendu vide ?)")
    return warnings


EXPORTERS = {
    ".drawio": export_drawio, ".mmd": export_mermaid, ".mermaid": export_mermaid,
    ".md": export_mermaid, ".excalidraw": export_excalidraw, ".c4": export_likec4,
    ".likec4": export_likec4,
}


def kind_of(src: Path) -> str | None:
    if src.is_dir():
        return ".c4" if any(src.glob("*.c4")) or any(src.glob("*.likec4")) else None
    return src.suffix.lower() if src.suffix.lower() in EXPORTERS else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", nargs="+", type=Path)
    parser.add_argument("--format", choices=["png", "svg", "pdf"], default="png")
    parser.add_argument("--scale", type=float, default=2, help="zoom des PNG (défaut : 2)")
    parser.add_argument("--out", type=Path, help="dossier de sortie (défaut : à côté de la source)")
    parser.add_argument("--transparent", action="store_true", help="fond transparent")
    parser.add_argument("--check", action="store_true", help="vérifier le rendu sans rien écrire")
    args = parser.parse_args()

    reports, failed = [], False
    for src in args.sources:
        src = src.resolve()
        report = {"source": str(src), "format": args.format, "outputs": [], "error": None}
        kind = kind_of(src) if src.exists() else None
        if not src.exists():
            report["error"] = "Fichier introuvable"
        elif not kind:
            report["error"] = "Format non reconnu (.drawio, .mmd, .md, .excalidraw, .c4)"
        else:
            fmt = "svg" if args.check and kind != ".c4" else args.format
            if kind == ".c4":
                fmt = "png"
            with tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp) if args.check else (args.out or (src if src.is_dir() else src.parent))
                out = out.resolve()
                out.mkdir(parents=True, exist_ok=True)
                try:
                    files = EXPORTERS[kind](src, out, fmt, args.scale, args.transparent)
                    report["outputs"] = [] if args.check else [str(f) for f in files]
                    report["rendered"] = len(files)
                    report["warnings"] = [w for f in files for w in image_warnings(Path(f))]
                except ExportError as error:
                    report["error"] = str(error)
                except OSError as error:
                    report["error"] = f"{type(error).__name__} : {error}"
        failed = failed or bool(report["error"])
        reports.append(report)
    print_report(reports)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
