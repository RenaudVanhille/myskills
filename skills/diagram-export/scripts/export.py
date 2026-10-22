# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.48"]
# ///
"""Exporte des schémas en PNG, SVG ou PDF, ou vérifie seulement qu'ils se rendent.

Formats reconnus :
- `.drawio` : draw.io Desktop, vers `<nom>.drawio.png` ou `.drawio.svg` qui gardent le
  XML et restent donc modifiables dans draw.io ;
- `.mmd`, `.mermaid` : Mermaid CLI (`mmdc`, sinon `npx @mermaid-js/mermaid-cli`) ;
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
import tarfile
import struct
import tempfile
import zlib
from pathlib import Path
from urllib.parse import quote, unquote

MERMAID_CLI = "@mermaid-js/mermaid-cli@11"
LIKEC4 = "likec4@1"
EXCALIDRAW_UTILS = "0.1.7"
MERMAID_BLOCK = re.compile(r"^```mermaid[ \t]*\n(.*?)^```", re.M | re.S)
ANSI = re.compile(r"\x1b\[[0-9;]*m")
NO_SANDBOX = platform.system() == "Linux" and hasattr(os, "geteuid") and os.geteuid() == 0


class ExportError(Exception):
    pass


def run(cmd: list[str], cwd: Path | None = None, timeout: int = 300) -> None:
    try:
        proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
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
    npx = shutil.which("npx")
    if not npx:
        raise ExportError(f"{binary} introuvable et Node.js absent : installez Node.js "
                          "(https://nodejs.org/), voir le skill check-prerequisites.")
    return [npx, "-y", "-p", package, binary]


def drawio_binary() -> str:
    for name in ("drawio", "draw.io"):
        if shutil.which(name):
            return shutil.which(name)
    candidates = [
        Path("/Applications/draw.io.app/Contents/MacOS/draw.io"),
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "draw.io" / "draw.io.exe",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "draw.io" / "draw.io.exe",
        Path("/opt/drawio/drawio"),
    ]
    for path in candidates:
        if path.is_file():
            return str(path)
    raise ExportError("draw.io Desktop introuvable : "
                      "https://github.com/jgraph/drawio-desktop/releases")


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") if os.name == "nt" else None
    root = Path(base) if base else Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    return root / "myskills"


# --- draw.io -----------------------------------------------------------------

def export_drawio(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    target = out / f"{src.stem}.drawio.{fmt}"
    cmd = [drawio_binary(), "--export", "--format", fmt, "--output", str(target)]
    if fmt == "svg":
        cmd.append("--embed-diagram")
    if fmt == "png":
        cmd += ["--scale", str(scale)]
        if transparent:
            cmd.append("--transparent")
    if NO_SANDBOX:
        cmd.append("--no-sandbox")
    cmd.append(str(src))
    if platform.system() == "Linux" and not os.environ.get("DISPLAY") and shutil.which("xvfb-run"):
        cmd = ["xvfb-run", "-a"] + cmd
    run(cmd)
    if not target.is_file():
        raise ExportError("draw.io n'a rien produit (fichier vide ou XML invalide ?)")
    if fmt == "png":
        embed_drawio(target, src.read_text(encoding="utf-8"))
    return [target]


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

def mermaid_config(work: Path) -> list[str]:
    args = []
    if NO_SANDBOX:
        config = {"args": ["--no-sandbox"]}
        if os.environ.get("PUPPETEER_EXECUTABLE_PATH"):
            config["executablePath"] = os.environ["PUPPETEER_EXECUTABLE_PATH"]
        path = work / "puppeteer.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        args += ["--puppeteerConfigFile", str(path)]
    return args


def export_mermaid(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    text = src.read_text(encoding="utf-8")
    if src.suffix.lower() == ".md":
        blocks = MERMAID_BLOCK.findall(text)
        if not blocks:
            raise ExportError("Aucun bloc ```mermaid dans ce fichier")
        names = [f"{src.stem}-{i}" for i in range(1, len(blocks) + 1)]
    else:
        blocks, names = [text], [src.stem]
    outputs, errors = [], []
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp)
        base = node_tool("mmdc", MERMAID_CLI) + mermaid_config(work)
        for index, (block, name) in enumerate(zip(blocks, names), 1):
            source = work / f"{name}.mmd"
            source.write_text(block, encoding="utf-8")
            target = out / f"{name}.{fmt}"
            cmd = base + ["--input", str(source), "--output", str(target), "--quiet",
                          "--backgroundColor", "transparent" if transparent else "white"]
            if fmt == "png":
                cmd += ["--scale", str(scale)]
            try:
                run(cmd)
                outputs.append(target)
            except ExportError as error:
                label = f"bloc {index}" if len(blocks) > 1 or src.suffix.lower() == ".md" else src.name
                errors.append(f"{label} : {error}")
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

def excalidraw_package() -> Path:
    root = cache_dir() / f"excalidraw-utils-{EXCALIDRAW_UTILS}"
    entry = root / "package" / "dist" / "prod" / "index.js"
    if entry.is_file():
        return root / "package"
    root.mkdir(parents=True, exist_ok=True)
    npm = shutil.which("npm")
    tgz = root / "utils.tgz"
    if npm:
        run([npm, "pack", f"@excalidraw/utils@{EXCALIDRAW_UTILS}", "--pack-destination", str(root),
             "--silent"], cwd=root)
        packed = next(root.glob("excalidraw-utils-*.tgz"), None)
        if packed:
            packed.replace(tgz)
    if not tgz.is_file():
        import urllib.request
        url = f"https://registry.npmjs.org/@excalidraw/utils/-/utils-{EXCALIDRAW_UTILS}.tgz"
        urllib.request.urlretrieve(url, tgz)
    with tarfile.open(tgz) as archive:
        archive.extractall(root, filter="data") if hasattr(tarfile, "data_filter") else archive.extractall(root)
    tgz.unlink()
    return root / "package"


def launch_browser(pw):
    custom = os.environ.get("MYSKILLS_BROWSER")
    args = ["--no-sandbox"] if NO_SANDBOX else []
    attempts = [{"executable_path": custom}] if custom else []
    attempts += [{"channel": "msedge"}, {"channel": "chrome"}, {}]
    last = None
    for options in attempts:
        try:
            return pw.chromium.launch(args=args, **options)
        except Exception as error:  # navigateur absent : on essaie le suivant
            last = error
    raise ExportError("Aucun navigateur trouvé (Edge, Chrome ou Chromium de Playwright) : "
                      "lancez `uvx playwright install chromium`. " + str(last).splitlines()[0])


def export_excalidraw(src: Path, out: Path, fmt: str, scale: float, transparent: bool) -> list[Path]:
    if fmt == "pdf":
        raise ExportError("Excalidraw s'exporte en PNG ou SVG")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise ExportError("Playwright manquant : lancez ce script avec `uv run`")
    scene = json.loads(src.read_text(encoding="utf-8"))
    if scene.get("type") != "excalidraw":
        raise ExportError("Ce fichier n'est pas une scène Excalidraw "
                          "(lancez d'abord excalidraw_build.py)")
    package = excalidraw_package()

    def serve(route):
        rel = unquote(route.request.url.split("://local.myskills/", 1)[1].split("?")[0])
        path = package / rel
        if rel == "page.html":
            route.fulfill(body="<!doctype html><html><body></body></html>", content_type="text/html")
        elif path.is_file():
            kind = mimetypes.guess_type(path.name)[0] or "application/javascript"
            route.fulfill(body=path.read_bytes(), content_type=kind)
        else:
            route.fulfill(status=404, body="")

    target = out / f"{src.stem}.excalidraw.{fmt}"
    with sync_playwright() as pw:
        browser = launch_browser(pw)
        try:
            page = browser.new_page()
            page.route("http://local.myskills/**", serve)
            page.goto("http://local.myskills/page.html")
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
        finally:
            browser.close()
    if fmt == "svg":
        target.write_text(result, encoding="utf-8")
    else:
        target.write_bytes(base64.b64decode(result))
    return [target]


# --- Commun ------------------------------------------------------------------

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
                except ExportError as error:
                    report["error"] = str(error)
                except OSError as error:
                    report["error"] = f"{type(error).__name__} : {error}"
        failed = failed or bool(report["error"])
        reports.append(report)
    print(json.dumps(reports, ensure_ascii=False, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
