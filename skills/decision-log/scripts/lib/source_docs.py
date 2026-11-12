"""Documents sources d'un catalogue d'exigences, pour les notes du vault : où une citation se trouve dans
son document (section), l'ancre Obsidian de cette section, les images locales que le document intègre, et
les liens à poser dans la copie d'un livrable Markdown (identifiants, renvois « document.md:ligne »)."""

import re
import unicodedata
from pathlib import Path

IMAGE = re.compile(r"!\[[^\]]*\]\(<?([^)>\s]+)>?(?:\s+\"[^\"]*\")?\)")
HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def normalize(text: str) -> str:
    """Minuscules, sans accents ni mise en forme Markdown, espaces réduits (comme req_build.py)."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("’", "'").replace("«", '"').replace("»", '"')
    text = re.sub(r"[*_`#>|]|\[|\]|\(http[^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load(folder: Path) -> dict[str, list[str]]:
    """Documents Markdown du dossier des sources : chemin relatif -> lignes."""
    if not folder.is_dir():
        return {}
    return {path.relative_to(folder).as_posix(): path.read_text(encoding="utf-8", errors="replace").splitlines()
            for path in sorted(folder.rglob("*.md")) if ".myskills-tmp" not in path.parts}


def body_of(lines: list[str]) -> list[str]:
    """Lignes du document sans son frontmatter YAML."""
    if lines and lines[0].strip() == "---":
        for number, line in enumerate(lines[1:], 1):
            if line.strip() in ("---", "..."):
                return lines[number + 1:]
    return lines


def line_of(lines: list[str], quote: str | None) -> int | None:
    """Ligne (à partir de 1) où commence la citation, même coupée sur plusieurs lignes, sinon None."""
    wanted = normalize(quote or "")
    if not wanted:
        return None
    joined, starts = "", []
    for number, line in enumerate(lines, 1):
        starts.append((len(joined), number))
        joined += normalize(line) + " "
    at = joined.find(wanted)
    return max(number for offset, number in starts if offset <= at) if at >= 0 else None


def section_at(lines: list[str], number: int | None) -> str | None:
    """Titre de la section qui contient la ligne (à partir de 1), sinon None."""
    fenced, found = False, None
    for line in lines[:number or 0]:
        if line.lstrip().startswith(("```", "~~~")):
            fenced = not fenced
        match = None if fenced else HEADING.match(line)
        if match:
            found = match.group(1)
    return found


def anchor(heading: str) -> str:
    """Ancre Obsidian d'un titre : les caractères qu'un wikilink ne porte pas deviennent des espaces."""
    return re.sub(r"\s+", " ", re.sub(r"[#|^:\[\]]|%%", " ", re.sub(r"[*_`]", "", heading))).strip()


def images(lines: list[str], doc: str, folder: Path) -> dict[str, Path]:
    """Images locales intégrées par le document : chemin relatif au dossier des sources -> fichier."""
    found = {}
    root = folder.resolve()
    for target in IMAGE.findall("\n".join(lines)):
        if re.match(r"[a-z][a-z0-9+.-]*:", target, re.I) or target.startswith(("/", "#")):
            continue
        path = (folder / Path(doc).parent / target.replace("%20", " ")).resolve()
        if path.is_file() and root in path.parents:
            found[path.relative_to(root).as_posix()] = path
    return found


def linker(ids: dict[str, str], docs: dict[str, tuple[str, list[str]]], folder: str):
    """Fonction qui pose les wikilinks dans un texte Markdown, sans en changer les mots : un identifiant
    connu (EF-001, D-012) mène à sa note, un renvoi à un document source (« doc.md », « doc.md:30 »,
    `sources/doc.md`) à la note du document, à la section de la ligne citée. Blocs de code, code en ligne,
    titres et autres liens déjà écrits sont laissés tels quels ; dans un tableau, la barre du lien est échappée.
    ids : identifiant -> note ; docs : document -> (note, lignes) ; folder : nom du dossier des sources."""
    parts = [r"(?P<skip>!?\[\[[^\]\n]*\]\]|!?\[[^\]\n]*\]\([^)\n]*\)|<[^>\n]+>)"]
    if docs:
        names = "|".join(re.escape(d) for d in sorted(docs, key=len, reverse=True))
        parts.append(rf"(?P<tick>`)?(?<![\w/])(?:{re.escape(folder)}/)?(?P<doc>{names})(?::(?P<line>\d+))?(?(tick)`)")
    parts.append(r"(?P<code>`[^`\n]*`)")
    if ids:
        parts.append(r"(?<![\w-])(?P<id>" + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True))
                     + r")(?![\w-])")
    pattern = re.compile("|".join(parts))

    def linked(text: str) -> str:
        out, fenced = [], False
        for line in text.split("\n"):
            stripped = line.lstrip()
            if stripped.startswith(("```", "~~~")):
                fenced = not fenced
            if fenced or stripped.startswith(("```", "~~~", "#")):
                out.append(line)
                continue
            bar = "\\|" if stripped.startswith("|") else "|"

            def link(match: re.Match) -> str:
                groups = match.groupdict()
                if groups.get("id"):
                    return f"[[{ids[groups['id']]}{bar}{groups['id']}]]"
                if not groups.get("doc"):
                    # Lien Markdown déjà posé sur un identifiant ou un document (journal.md) : repris en wikilink.
                    inner = re.fullmatch(r"\[([^\]\n]*)\]\([^)\n]*\)", groups.get("skip") or "")
                    text = pattern.sub(link, inner.group(1)) if inner else None
                    return text if text and text != inner.group(1) else match.group(0)
                target, lines = docs[groups["doc"]]
                section = section_at(lines, int(groups["line"])) if groups.get("line") else None
                shown = match.group(0).strip("`")
                return f"[[{target}{'#' + anchor(section) if section else ''}{bar}{shown}]]"
            out.append(pattern.sub(link, line))
        return "\n".join(out)
    return linked
