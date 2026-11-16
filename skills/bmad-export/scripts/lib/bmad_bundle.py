"""Bundle BMAD autonome : copies des pièces citées, liens réécrits vers ces copies, contrôle des liens.

L'export ne garde aucun lien vers la mission ni vers le vault Obsidian : chaque fichier copié (sources/,
mockups/) est relu, ses liens Markdown, wikilinks, attributs HTML (src, href) et url() CSS sont recalés
sur la copie du fichier visé ; une image, une feuille de style ou une page visée qui n'est pas encore dans
le bundle y est copiée (dans sources/, sous son chemin dans la mission) ; un lien vers une note (vault,
autre Markdown de la mission) ou vers un fichier absent devient du texte.

    pack(copies, planning, folder) -> (fichiers à écrire, avertissements)
    escapes(name, text, planning, coming) -> liens qui sortent du bundle ou n'y mènent à rien
    foreign(name, text, roots) -> chemins de la machine (absolus, file:, dossier de la mission) cités
    audit(planning) -> contrôle d'un bundle déjà écrit, où qu'il ait été copié
"""
from __future__ import annotations

import os
import re
import urllib.parse
from pathlib import Path

# Fichiers relus et réécrits ; les autres (images, code) sont copiés tels quels.
TEXT = {".md", ".html", ".htm", ".css", ".scss", ".svg"}
# Fichiers visés par un lien qu'on copie dans le bundle ; une note Markdown visée n'est pas copiée.
ASSETS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".css", ".html", ".htm", ".pdf", ".woff", ".woff2",
          ".ttf", ".otf", ".js", ".yaml", ".yml", ".sql", ".drawio", ".excalidraw"}
MD_LINK = re.compile(r"(!?)\[([^\]\n]*)\]\(\s*<?([^)\s>]+)>?(\s+\"[^\"\n]*\")?\s*\)")
WIKI = re.compile(r"(!?)\[\[([^\]|\n]+?)(?:\|([^\]\n]*))?\]\]")
ATTR = re.compile(r"\b(src|href|poster|data-src)(\s*=\s*)([\"'])([^\"']*)\3", re.I)
CSS_URL = re.compile(r"url\(\s*([\"']?)([^\"')]+)\1\s*\)")
CSS_IMPORT = re.compile(r"(@import\s+)([\"'])([^\"']+)\2")
# Ancre, schéma d'au moins deux lettres (une lettre seule est un lecteur Windows), adresse sans schéma.
# Chemin absolu d'une machine (Unix, macOS, Windows) ou URL file: : sans valeur une fois le bundle copié ailleurs.
ABSOLUTE = re.compile(r"file:/|(?<![\w.~-])/(?:home|Users|tmp|mnt|root|Volumes)/[^\s)\"'`]*"
                      r"|(?<![\w])[A-Za-z]:[\\/]Users[\\/][^\s)\"'`]*")
EXTERNAL = re.compile(r"^(#|[a-z][a-z0-9+.-]+:|//)", re.I)


def external(target: str) -> bool:
    """Ancre, adresse web, mailto:, data: : hors du contrôle (un file: ou un chemin absolu ne l'est pas)."""
    return bool(EXTERNAL.match(target)) and not target.lower().startswith("file:")


def split(target: str) -> tuple[str, str]:
    """Chemin d'un lien et sa suite (#ancre, ?requête)."""
    cut = min((i for i in (target.find("#"), target.find("?")) if i >= 0), default=len(target))
    return urllib.parse.unquote(target[:cut]), target[cut:]


def resolve(target: str, here: Path) -> Path:
    path, _ = split(target)
    if path.lower().startswith("file:"):
        path = urllib.parse.urlparse(path).path
        path = path[1:] if re.match(r"^/[a-z]:", path, re.I) else path
    return (here / path).resolve()


class Packer:
    def __init__(self, copies: list, planning: Path, folder: Path):
        self.planning, self.folder, self.warnings = planning, folder, []
        self.dest = {}
        for source, target in copies:
            self.dest.setdefault(source.resolve(), target)
        self.taken = set(self.dest.values())

    def adopt(self, path: Path) -> Path:
        """Copie dans sources/ d'un fichier visé qui n'est pas encore dans le bundle."""
        if path not in self.dest:
            name = path.relative_to(self.folder).as_posix() if path.is_relative_to(self.folder) else path.name
            target, n = self.planning / "sources" / name, 1
            while target in self.taken:
                n += 1
                target = target.with_name(f"{path.stem}-{n}{path.suffix}")
            self.dest[path] = target
            self.taken.add(target)
        return self.dest[path]

    def relink(self, target: str, source: Path, out: Path) -> str | None:
        """Lien recalé sur la copie, None s'il doit tomber (note, fichier absent, dossier)."""
        path = resolve(target, source.parent)
        if path not in self.dest:
            if not path.is_file() or path.suffix.lower() not in ASSETS or path.is_relative_to(self.planning):
                return None
            self.adopt(path)
        rest = split(target)[1]
        return urllib.parse.quote(Path(os.path.relpath(self.dest[path], out.parent)).as_posix()) + rest

    def rewrite(self, text: str, source: Path, out: Path) -> str:
        dropped = []

        def markdown(match: re.Match) -> str:
            bang, label, target, title = match.group(1), match.group(2), match.group(3), match.group(4) or ""
            if external(target):
                return match.group(0)
            new = self.relink(target, source, out)
            if new is None:
                dropped.append(target)
                return label
            return f"{bang}[{label}]({new}{title})"

        def wiki(match: re.Match) -> str:
            bang, target, label = match.group(1), match.group(2).strip(), match.group(3)
            shown = (label or target.split("#")[0].rsplit("/", 1)[-1].removesuffix(".md")).strip()
            new = self.relink(target, source, out) if bang else None
            if new is None:
                dropped.append(f"[[{target}]]")
            return f"![{shown}]({new})" if new else shown

        def attribute(match: re.Match) -> str:
            name, eq, quote, target = match.groups()
            if not target or external(target):
                return match.group(0)
            new = self.relink(target, source, out)
            if new is None:
                dropped.append(target)
                new = "#"
            return f"{name}{eq}{quote}{new}{quote}"

        def css(match: re.Match) -> str:
            quote, target = match.groups()
            if external(target):
                return match.group(0)
            new = self.relink(target.strip(), source, out)
            if new is None:
                dropped.append(target)
                return "none"
            return f"url({quote}{new}{quote})"

        def css_import(match: re.Match) -> str:
            prefix, quote, target = match.groups()
            new = None if external(target) else self.relink(target, source, out)
            return match.group(0) if external(target) or new is None else f"{prefix}{quote}{new}{quote}"

        suffix = source.suffix.lower()
        if suffix == ".md":
            text = WIKI.sub(wiki, MD_LINK.sub(markdown, text))
        if suffix in {".md", ".html", ".htm", ".svg"}:
            text = ATTR.sub(attribute, text)
        if suffix in {".html", ".htm", ".css", ".scss", ".svg"}:
            text = CSS_URL.sub(css, CSS_IMPORT.sub(css_import, text))
        if dropped:
            self.warnings.append(f"{out.relative_to(self.planning).as_posix()} : {len(dropped)} lien(s) hors du "
                                 f"bundle retiré(s) ({', '.join(dict.fromkeys(dropped[:3]))})")
        return text


def pack(copies: list, planning: Path, folder: Path) -> tuple[list, list[str]]:
    """Fichiers du bundle (destination, octets), liens recalés ; les fichiers visés suivent, de proche en proche."""
    packer, files, done = Packer(copies, planning.resolve(), folder.resolve()), [], set()
    while len(done) < len(packer.dest):
        for source, target in list(packer.dest.items()):
            if source in done:
                continue
            done.add(source)
            data = source.read_bytes()
            if source.suffix.lower() in TEXT:
                text = data.decode("utf-8", errors="surrogateescape")
                data = packer.rewrite(text, source, target).encode("utf-8", errors="surrogateescape")
            files.append((target, data))
    return files, packer.warnings


def escapes(name: str, text: str, planning: Path, coming: set[Path]) -> list[str]:
    """Liens d'un fichier du bundle qui en sortent, mènent à un fichier absent, ou sont des wikilinks."""
    here, suffix = (planning / name).parent, Path(name).suffix.lower()
    targets = [m.group(3) for m in MD_LINK.finditer(text)] if suffix == ".md" else []
    targets += [m.group(4) for m in ATTR.finditer(text)] if suffix in {".md", ".html", ".htm", ".svg"} else []
    if suffix in {".html", ".htm", ".css", ".scss", ".svg"}:
        targets += [m.group(2).strip() for m in CSS_URL.finditer(text)] + [m.group(3) for m in CSS_IMPORT.finditer(text)]
    found = [f"{name} : wikilink {m.group(0)} (propre à Obsidian, hors du bundle) : écrivez le texte sans crochets" for m in WIKI.finditer(text)] if suffix == ".md" else []
    for target in targets:
        if not target or external(target):
            continue
        path = resolve(target, here)
        if not path.is_relative_to(planning):
            found.append(f"{name} : lien hors du bundle {target} : l'export doit rester autonome, retirez ce lien "
                         "de sa source (bmad.json ou pièce de la mission)")
        elif path not in coming and not path.exists():
            found.append(f"{name} : lien introuvable {target}")
    return found


def foreign(name: str, text: str, roots: list[Path]) -> list[str]:
    """Chemins de la machine cités dans un fichier du bundle : chemin absolu, URL file:, dossier de la mission."""
    found = [f"{name} : chemin absolu {m.group(0)[:80]} : sans valeur une fois le bundle copié ailleurs"
             for m in ABSOLUTE.finditer(text)]
    found += [f"{name} : chemin de la mission {root.as_posix()}" for root in dict.fromkeys(roots)
              if root.as_posix() in text.replace("\\", "/")]
    return found


def audit(planning: Path) -> tuple[int, list[str]]:
    """Contrôle d'un bundle sur disque : chaque lien mène à un fichier du bundle, aucun wikilink ni chemin de
    la machine. Rend le nombre de fichiers lus et les erreurs."""
    files = [p for p in sorted(planning.rglob("*")) if p.is_file()]
    errors = []
    for path in files:
        if path.suffix.lower() in TEXT:
            name, text = path.relative_to(planning).as_posix(), path.read_text(encoding="utf-8", errors="replace")
            errors += escapes(name, text, planning, set()) + foreign(name, text, [])
    return len(files), errors
