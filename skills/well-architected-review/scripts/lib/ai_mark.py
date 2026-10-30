"""Marque caché « généré par IA » des fichiers produits par les skills (AI Act, art. 50).

Le règlement (UE) 2024/1689 demande que les contenus produits par un système
d'IA soient marqués de façon lisible par une machine. Chaque script marque les
livrables qu'il écrit, jamais un fichier fourni par l'utilisateur : la marque
est invisible au rendu et propre à chaque format.

    .md            frontmatter genere-par-ia: true (et generateur), sinon commentaire HTML en tête,
                   plus une mention visible « Document généré par IA » sous le titre
    .html .htm     <meta name="genere-par-ia"> dans <head>, sinon commentaire
    .svg .xml .vue commentaire XML ; .drawio : attributs de <mxfile>
    .yaml .mmd .c4 .likec4 .css .scss .js .jsx .ts .tsx : commentaire de leur syntaxe
    .excalidraw    clés genere-par-ia et generateur de l'objet racine
    .png           chunks tEXt genere-par-ia et XMP (IPTC DigitalSourceType trainedAlgorithmicMedia)
    .docx .pptx .xlsx  propriétés personnalisées (docProps/custom.xml)

Les autres formats (JSON de données, CSV, PDF...) ne sont pas marqués :
supported() le dit. Marquer est idempotent.

    ai_mark.write_text(chemin, texte)   écrit le texte marqué (UTF-8)
    ai_mark.marked(texte, suffixe)      texte marqué, sans écrire
    ai_mark.mark(chemin)                marque un fichier déjà écrit (outil externe, binaire)
    ai_mark.inherit(source, chemins)    export ou conversion : marque si la source la porte
    ai_mark.is_marked(chemin)           le fichier porte-t-il la marque ?

Un export ou une simple mise en forme (PNG d'un schéma, Word d'un Markdown,
note Obsidian) reprend la marque de sa source : le rendu d'un document de
l'utilisateur n'est pas marqué, celui d'un livrable généré l'est.

Source : shared/scripts/ai_mark.py, copiée par scripts/build.py dans
scripts/lib/ des skills qui l'importent. Ne modifiez pas les copies.
"""

import re
import struct
import zipfile
import zlib
from pathlib import Path

KEY = "genere-par-ia"
NOTICE = "Contenu généré par IA, règlement (UE) 2024/1689 (AI Act), article 50"
# Valeur IPTC des contenus produits par un modèle (https://cv.iptc.org/newscodes/digitalsourcetype/).
SOURCE_TYPE = "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia"
_here = Path(__file__).resolve().parent
# Skill qui a écrit le fichier : la copie vit dans skills/<skill>/scripts/lib/.
GENERATOR = "myskills/" + (_here.parents[1].name if _here.name == "lib" else "myskills")
LINE = f"{KEY}: true · generateur: {GENERATOR} · {NOTICE}"
# Mention visible des Markdown, lisible partout (Obsidian, GitHub, Word après export).
DISCLAIMER = "*Document généré par IA"
DISCLAIMER_TEXT = (f"> {DISCLAIMER} ({GENERATOR}) : à relire et valider avant tout usage. "
                   "Mention de transparence, règlement (UE) 2024/1689 (AI Act), article 50.*\n")

COMMENTS = {".svg": ("<!-- ", " -->"), ".xml": ("<!-- ", " -->"), ".vue": ("<!-- ", " -->"),
            ".yaml": ("# ", ""), ".yml": ("# ", ""), ".mmd": ("%% ", ""), ".c4": ("// ", ""),
            ".likec4": ("// ", ""), ".css": ("/* ", " */"), ".scss": ("/* ", " */"),
            ".js": ("/* ", " */"), ".jsx": ("/* ", " */"), ".ts": ("/* ", " */"), ".tsx": ("/* ", " */")}
TEXT = {".md", ".markdown", ".html", ".htm", ".drawio", ".excalidraw", *COMMENTS}
OFFICE = {".docx", ".pptx", ".xlsx"}
BINARY = {".png", *OFFICE}
HEAD = 4096  # la marque est toujours au début du fichier


def supported(path) -> bool:
    return Path(path).suffix.lower() in TEXT | BINARY


def _frontmatter(text: str) -> int:
    """Position de la ligne --- qui ferme le frontmatter, -1 sans frontmatter."""
    if not text.startswith("---\n") and not text.startswith("---\r\n"):
        return -1
    match = re.search(r"\r?\n---[ \t]*(\r?\n|$)", text[3:])
    return 3 + match.start() + 1 if match else -1


def _has_mark(text: str, suffix: str) -> bool:
    if suffix in (".md", ".markdown"):
        end = _frontmatter(text)
        if end > 0 and re.search(rf"^{KEY}:", text[:end], re.M):
            return True
    return KEY in text[:HEAD]


def _disclaimer(text: str) -> str:
    """Mention visible en tête du document : après le titre # s'il ouvre le texte, sinon avant le texte
    (toujours après le frontmatter et la marque cachée)."""
    if DISCLAIMER in text:
        return text
    end = _frontmatter(text)
    cut = text.index("\n", end) + 1 if end > 0 and "\n" in text[end:] else 0
    comment = re.match(r"<!--[^\n]*-->\r?\n", text[cut:])
    cut += comment.end() if comment else 0
    blank = re.match(r"(\s*\n)?", text[cut:])
    first = cut + blank.end()
    title = re.match(r"# [^\n]*(\n|$)", text[first:])
    if title:
        cut = first + title.end()
        rest = text[cut:]
        gap = "\n" if rest and not rest.startswith(("\n", "\r\n")) else ""
        return text[:cut] + ("" if text[cut - 1:cut] == "\n" else "\n") + "\n" + DISCLAIMER_TEXT + gap + rest
    return text[:cut] + DISCLAIMER_TEXT + "\n" + text[cut:]


def marked(text: str, suffix: str) -> str:
    """Le texte avec la marque de son format ; inchangé s'il la porte déjà ou si le format n'en a pas.
    Un Markdown reçoit aussi la mention visible (DISCLAIMER), une seule fois."""
    suffix = suffix.lower()
    if suffix in (".md", ".markdown"):
        return _disclaimer(_hidden_md(text))
    if suffix not in TEXT or _has_mark(text, suffix):
        return text
    comment = f"<!-- {LINE} -->\n"
    if suffix in (".html", ".htm"):
        head = re.search(r"<head(\s[^>]*)?>", text[:HEAD], re.I)
        if head:
            meta = (f'\n<meta name="{KEY}" content="true">\n<meta name="generateur" content="{GENERATOR}">'
                    f'\n<meta name="mention-ia" content="{NOTICE}">')
            return text[:head.end()] + meta + text[head.end():]
        doctype = re.match(r"\s*<!doctype[^>]*>\s*", text, re.I)
        cut = doctype.end() if doctype else 0
        return text[:cut] + comment + text[cut:]
    if suffix == ".drawio":
        root = re.search(r"<mxfile\b", text[:HEAD])
        if root:
            return text[:root.end()] + f' {KEY}="true" generateur="{GENERATOR}"' + text[root.end():]
        suffix = ".xml"
    if suffix == ".excalidraw":
        brace = text.find("{")
        if brace < 0 or not text[brace + 1:].strip().startswith('"'):
            return text
        return text[:brace + 1] + f'\n  "{KEY}": true,\n  "generateur": "{GENERATOR}",' + text[brace + 1:]
    start, end = COMMENTS[suffix]
    line = f"{start}{LINE}{end}\n"
    cut = 0
    if suffix in (".svg", ".xml"):
        decl = re.match(r"\s*<\?xml[^>]*\?>\s*", text)
        cut = decl.end() if decl else 0
    elif suffix == ".mmd" and _frontmatter(text) > 0:
        # Après le frontmatter de Mermaid, qui doit rester en tête.
        close = text.find("\n", _frontmatter(text))
        cut, line = (close + 1, line) if close >= 0 else (len(text), "\n" + line)
    return text[:cut] + line + text[cut:]


def _hidden_md(text: str) -> str:
    """Marque cachée d'un Markdown : clés du frontmatter, sinon commentaire HTML en tête."""
    if _has_mark(text, ".md"):
        return text
    end = _frontmatter(text)
    if end < 0:
        return f"<!-- {LINE} -->\n" + text
    newline = "\r\n" if "\r\n" in text[:end] else "\n"
    owner = "" if re.search(r"^genere:", text[:end], re.M) else f"generateur: {GENERATOR}{newline}"
    return text[:end] + f"{KEY}: true{newline}{owner}" + text[end:]


def write_text(path, text: str) -> Path:
    """Écrit le texte marqué selon le format du chemin, en UTF-8 avec des fins de ligne \\n."""
    path = Path(path)
    with open(path, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(marked(text, path.suffix))
    return path


# --- PNG -----------------------------------------------------------------------------------------

def _chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _png_chunks(data: bytes):
    pos = 8
    while pos + 8 <= len(data):
        size, kind = struct.unpack(">I4s", data[pos:pos + 8])
        yield pos, kind, data[pos + 8:pos + 8 + size]
        pos += 12 + size


def _xmp() -> str:
    return ('<?xpacket begin="﻿" id="W5M0MpCehiHzreSzNTczkc9d"?>'
            '<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#">'
            '<rdf:Description rdf:about="" xmlns:Iptc4xmpExt="http://iptc.org/std/Iptc4xmpExt/2008-02-29/"'
            ' xmlns:xmp="http://ns.adobe.com/xap/1.0/" xmlns:dc="http://purl.org/dc/elements/1.1/"'
            f' Iptc4xmpExt:DigitalSourceType="{SOURCE_TYPE}" xmp:CreatorTool="{GENERATOR}">'
            f'<dc:description><rdf:Alt><rdf:li xml:lang="fr">{NOTICE}</rdf:li></rdf:Alt></dc:description>'
            '</rdf:Description></rdf:RDF></x:xmpmeta><?xpacket end="r"?>')


def _mark_png(path: Path) -> bool:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return False
    chunks = list(_png_chunks(data))
    if any(kind == b"tEXt" and body.startswith(KEY.encode() + b"\0") for _, kind, body in chunks):
        return True
    first = next((pos for pos, kind, _ in chunks if kind == b"IDAT"), None)
    if first is None:
        return False
    value = LINE.removeprefix(KEY + ": ")
    extra = _chunk(b"tEXt", KEY.encode() + b"\0" + value.encode("latin-1", "replace"))
    if not any(kind == b"iTXt" and body.startswith(b"XML:com.adobe.xmp\0") for _, kind, body in chunks):
        extra += _chunk(b"iTXt", b"XML:com.adobe.xmp\0\0\0\0\0" + _xmp().encode("utf-8"))
    path.write_bytes(data[:first] + extra + data[first:])
    return True


# --- Word, PowerPoint, Excel ---------------------------------------------------------------------

CUSTOM = "docProps/custom.xml"
CUSTOM_TYPE = "application/vnd.openxmlformats-officedocument.custom-properties+xml"
CUSTOM_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships/custom-properties"
FMTID = "{D5CDD505-2E9C-101B-9397-08002B2CF9AE}"


def _custom_props(existing: str | None) -> str:
    props = [(KEY, "vt:bool", "true"), ("generateur", "vt:lpwstr", GENERATOR), ("mention-ia", "vt:lpwstr", NOTICE)]
    body = existing or ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<Properties xmlns='
                        '"http://schemas.openxmlformats.org/officeDocument/2006/custom-properties" xmlns:vt='
                        '"http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes"></Properties>')
    pids = [int(p) for p in re.findall(r'pid="(\d+)"', body)]
    pid = max(pids + [1]) + 1
    added = ""
    for offset, (name, kind, value) in enumerate(props):
        added += f'<property fmtid="{FMTID}" pid="{pid + offset}" name="{name}"><{kind}>{value}</{kind}></property>'
    if body.rstrip().endswith("/>"):  # <Properties .../> vide
        body = re.sub(r"/>\s*$", ">", body) + "</Properties>"
    return body.replace("</Properties>", added + "</Properties>")


def _mark_office(path: Path) -> bool:
    try:
        with zipfile.ZipFile(path) as source:
            items = [(info, source.read(info.filename)) for info in source.infolist()]
    except zipfile.BadZipFile:
        return False
    files = {info.filename: data for info, data in items}
    custom = files.get(CUSTOM, b"").decode("utf-8")
    if f'name="{KEY}"' in custom:
        return True
    files[CUSTOM] = _custom_props(custom or None).encode("utf-8")
    types = files["[Content_Types].xml"].decode("utf-8")
    if "/docProps/custom.xml" not in types:
        override = f'<Override PartName="/docProps/custom.xml" ContentType="{CUSTOM_TYPE}"/>'
        types = types.replace("</Types>", override + "</Types>")
        files["[Content_Types].xml"] = types.encode("utf-8")
    rels = files.get("_rels/.rels", b"").decode("utf-8")
    if CUSTOM_REL not in rels:
        ids = re.findall(r'Id="rId(\d+)"', rels)
        rid = f"rId{max([int(i) for i in ids] + [0]) + 1}"
        relation = f'<Relationship Id="{rid}" Type="{CUSTOM_REL}" Target="docProps/custom.xml"/>'
        rels = rels.replace("</Relationships>", relation + "</Relationships>")
        files["_rels/.rels"] = rels.encode("utf-8")
    order = [info.filename for info, _ in items]
    order += [] if CUSTOM in order else [CUSTOM]
    temp = path.with_name(path.name + ".tmp")
    with zipfile.ZipFile(temp, "w", zipfile.ZIP_DEFLATED) as target:
        for name in order:
            # Ordre d'origine gardé : [Content_Types].xml en tête.
            target.writestr(zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0)), files[name],
                            compress_type=zipfile.ZIP_DEFLATED)
    temp.replace(path)
    return True


def mark(path) -> bool:
    """Marque un fichier déjà écrit. True : il porte la marque ; False : format sans marque possible."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in TEXT:
        text = path.read_text(encoding="utf-8")
        if marked(text, suffix) != text:
            write_text(path, text)
        return True
    if suffix == ".png":
        return _mark_png(path)
    if suffix in OFFICE:
        return _mark_office(path)
    return False


def mark_all(paths) -> list[str]:
    """Marque chaque fichier qui existe ; renvoie les fichiers dont le format ne permet pas de marque."""
    return [str(p) for p in paths if Path(p).is_file() and supported(p) and not mark(p)]


def inherit(source, paths) -> bool:
    """Marque les fichiers produits depuis source (export, conversion) si source porte la marque ;
    un dossier source la porte si l'un de ses fichiers la porte. Renvoie True si la marque est reprise."""
    source = Path(source)
    files = [p for p in source.iterdir() if p.is_file()] if source.is_dir() else [source]
    if not any(supported(p) and is_marked(p) for p in files):
        return False
    mark_all(paths)
    return True


def is_marked(path) -> bool:
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix in TEXT:
        text = path.read_text(encoding="utf-8", errors="replace")
        return _has_mark(text, suffix)
    if suffix == ".png":
        return any(kind == b"tEXt" and body.startswith(KEY.encode() + b"\0")
                   for _, kind, body in _png_chunks(path.read_bytes()))
    if suffix in OFFICE:
        try:
            with zipfile.ZipFile(path) as source:
                return CUSTOM in source.namelist() and f'name="{KEY}"' in source.read(CUSTOM).decode("utf-8")
        except zipfile.BadZipFile:
            return False
    return False
