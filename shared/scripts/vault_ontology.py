"""Ontologie du vault Obsidian : construire et vérifier le frontmatter d'une note.

L'ontologie (`vault-ontology.json`, à côté de ce module) définit les types de
notes, leurs propriétés, les relations typées (propriétés dont la valeur est
un wikilink ou une liste de wikilinks) et la forme des tags. Un skill qui
écrit dans le vault construit le frontmatter avec `meta()` et le vérifie
avec `check_meta()` avant d'écrire ; `check_targets()` vérifie le type des
notes visées par les relations. `parse()` lit le frontmatter d'une note
(sous-ensemble YAML écrit par Obsidian et par ces skills).

Source : shared/scripts/vault_ontology.py et shared/vault-ontology.json,
copiés dans scripts/lib/ des skills dont le contrat déclare `vault` par
scripts/build.py. Ne modifiez pas les copies.
"""

import json
import re
import unicodedata
from pathlib import Path

try:
    from .spec_schema import check
except ImportError:
    from spec_schema import check

HERE = Path(__file__).resolve().parent
LINK = re.compile(r"^\[\[([^\[\]|#]+)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]$")
BODY_LINK = re.compile(r"(?<!!)\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
FRONTMATTER = re.compile(r"\A---\n(.*?)\n---(?:\n|\Z)", re.S)
KEY = re.compile(r"^([A-Za-z_][\w-]*)\s*:\s*(.*)$")


def load(path: Path | None = None) -> dict:
    return json.loads((path or HERE / "vault-ontology.json").read_text(encoding="utf-8"))


def slug(value) -> str:
    """Valeur de tag : minuscules, sans accents, tirets."""
    text = unicodedata.normalize("NFKD", str(value).lower())
    text = "".join(c for c in text if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9/]+", "-", text).strip("-/") or "x"


def link(path: str, alias: str | None = None) -> str:
    """Wikilink vers une note (chemin relatif au vault, sans .md)."""
    if alias is None or alias == path.rsplit("/", 1)[-1]:
        return f"[[{path}]]"
    return f"[[{path}|{alias.replace('|', '-').replace(']', ')').replace('[', '(')}]]"


def targets(value) -> list[str]:
    """Chemins visés par une valeur de relation (wikilink ou liste de wikilinks)."""
    values = value if isinstance(value, list) else [value]
    return [m.group(1).strip() for v in values if isinstance(v, str) for m in [LINK.match(v.strip())] if m]


def type_tag(onto: dict, kind: str) -> str:
    return f"{onto['tags']['type_prefix']}/{kind}"


def tags_for(onto: dict, kind: str, props: dict, extra=()) -> list[str]:
    """Tags normalisés : type/<type>, une facette par propriété déclarée, puis les tags libres."""
    spec = onto["types"][kind]
    tags = [type_tag(onto, kind)]
    for facet in spec.get("facets", []):
        value = props.get(facet)
        if value not in (None, "", []) and not isinstance(value, (list, dict)):
            tags.append(f"{facet}/{slug(value)}")
    tags += [slug(t) for t in extra if slug(t) not in tags]
    return list(dict.fromkeys(tags))


def meta(onto: dict, kind: str, props: dict | None = None, relations: dict | None = None,
         tags=(), genere: str | None = None) -> dict:
    """Frontmatter ordonné d'une note : type, propriétés, relations (wikilinks), ontologie, genere, tags.
    Les valeurs vides sont omises. relations : nom -> chemin, (chemin, alias) ou liste de ceux-ci."""
    props = {k: v for k, v in (props or {}).items() if v not in (None, "", [])}
    out = {"type": kind, **props}
    for name, value in (relations or {}).items():
        items = value if isinstance(value, list) else [value]
        links = [link(*v) if isinstance(v, tuple) else link(v) for v in items if v]
        if not links:
            continue
        out[name] = links if onto["relations"].get(name, {}).get("many", True) else links[0]
    out["ontologie"] = onto["version"]
    if genere:
        out["genere"] = genere
    out["tags"] = tags_for(onto, kind, props, tags)
    return out


def allowed(names: list[str], kind: str) -> bool:
    return "*" in names or kind in names


def check_meta(onto: dict, data: dict, generated: bool | None = None) -> tuple[list[str], list[str]]:
    """Erreurs et avertissements du frontmatter d'une note au regard de l'ontologie.
    generated : la note est écrite par un skill (défaut : propriété genere présente) ; ses tags sont alors exigés."""
    errors: list[str] = []
    warnings: list[str] = []
    kind = data.get("type")
    types = onto["types"]
    if kind not in types:
        known = ", ".join(types)
        close = [t for t in types if isinstance(kind, str) and (t.startswith(kind[:4]) or kind in t)]
        hint = f" ; vouliez-vous « {close[0]} » ?" if close else ""
        return [f"type : « {kind} » non permis ({known}){hint}"], warnings
    spec = types[kind]
    generated = bool(data.get("genere")) if generated is None else generated
    schemas = {**onto["common"], **spec["properties"]}
    for name in spec.get("required", []):
        if data.get(name) in (None, ""):
            errors.append(f"{name} : propriété obligatoire pour le type {kind}")
    for name, value in data.items():
        if name == "type" or value is None:
            continue
        if name in onto["relations"]:
            relation = onto["relations"][name]
            if not allowed(relation["from"], kind):
                errors.append(f"{name} : relation non permise depuis le type {kind} (types permis : "
                              f"{', '.join(relation['from'])})")
                continue
            items = value if isinstance(value, list) else [value]
            if isinstance(value, list) and not relation["many"]:
                errors.append(f"{name} : un seul wikilink attendu, reçu une liste")
            bad = [v for v in items if not (isinstance(v, str) and LINK.match(v.strip()))]
            errors += [f"{name} : « {v} » n'est pas un wikilink \"[[chemin]]\"" for v in bad]
        elif name in schemas:
            errors += check(value, schemas[name], path=name)
        else:
            warnings.append(f"{name} : propriété hors ontologie (type {kind})")
    tags = data.get("tags") if isinstance(data.get("tags"), list) else []
    pattern = re.compile(onto["tags"]["pattern"])
    errors += [f"tags : « {t} » ne suit pas le format {onto['tags']['pattern']} (proposé : {slug(t)})"
               for t in tags if isinstance(t, str) and not pattern.match(t)]
    prefix = onto["tags"]["type_prefix"] + "/"
    wrong = [t for t in tags if isinstance(t, str) and t.startswith(prefix) and t != type_tag(onto, kind)]
    errors += [f"tags : « {t} » contredit type {kind}" for t in wrong]
    if generated:
        missing = [t for t in tags_for(onto, kind, data) if t not in tags]
        errors += [f"tags : « {t} » manquant (type et facettes)" for t in missing]
    return errors, warnings


def check_targets(onto: dict, data: dict, resolve) -> tuple[list[str], list[str]]:
    """Type des notes visées par les relations. resolve(chemin) -> type de la note (None : sans type),
    ou lève KeyError si la note n'existe pas."""
    errors: list[str] = []
    warnings: list[str] = []
    kind = data.get("type")
    for name, value in data.items():
        relation = onto["relations"].get(name)
        if not relation or not allowed(relation["from"], kind):
            continue
        for path in targets(value):
            try:
                found = resolve(path)
            except KeyError:
                warnings.append(f"{name} : note « {path} » introuvable")
                continue
            expected = [kind] if relation.get("same_type") else relation["to"]
            if not allowed(expected, found or ""):
                errors.append(f"{name} : « {path} » est de type {found or 'absent'}, attendu "
                              f"{' ou '.join(expected)}")
    return errors, warnings


def scalar(text: str):
    text = text.strip()
    if text.startswith('"'):
        try:
            return json.loads(text)
        except ValueError:
            return text.strip('"')
    if text.startswith("'") and text.endswith("'") and len(text) > 1:
        return text[1:-1].replace("''", "'")
    if text in ("", "~", "null"):
        return None
    if text in ("true", "false"):
        return text == "true"
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    return text


def parse(text: str) -> tuple[dict | None, str, list[str]]:
    """Frontmatter (None s'il n'y en a pas), corps de la note et avertissements de lecture."""
    text = text.replace("\r\n", "\n")
    match = FRONTMATTER.match(text)
    if not match:
        return None, text, []
    data: dict = {}
    warnings: list[str] = []
    key = None
    for line in match.group(1).split("\n"):
        item = re.match(r"^\s*-\s*(.*)$", line)
        if item and key is not None:
            if not isinstance(data[key], list):
                data[key] = []
            data[key].append(scalar(item.group(1)))
            continue
        found = KEY.match(line)
        if not found:
            if line.strip() and not line.strip().startswith("#"):
                warnings.append(f"frontmatter : ligne non lue « {line.strip()[:40]} »")
            continue
        key, raw = found.group(1), found.group(2).strip()
        if LINK.match(raw):
            warnings.append(f"{key} : wikilink sans guillemets, Obsidian ne le lit pas comme lien")
            data[key] = raw
        elif raw.startswith("[") and raw.endswith("]"):
            try:
                data[key] = json.loads(raw)
            except ValueError:
                parts = re.findall(r'"(?:\\.|[^"])*"|\'[^\']*\'|[^,]+', raw[1:-1])
                data[key] = [scalar(p) for p in parts if p.strip()]
        else:
            data[key] = scalar(raw)
    return data, text[match.end():], warnings


def body_links(text: str) -> list[str]:
    """Wikilinks du corps (hors images intégrées et blocs de code)."""
    text = re.sub(r"```.*?```|`[^`\n]*`", "", text, flags=re.S)
    return list(dict.fromkeys(m.strip() for m in BODY_LINK.findall(text)))


def summary(onto: dict, kind: str | None = None) -> dict:
    """Ontologie réduite à ce qu'un modèle doit savoir pour écrire une note : propriétés obligatoires,
    valeurs permises, relations et types visés."""
    def short(schema: dict):
        return schema.get("enum") or schema.get("type", "texte")
    types = {}
    for name, spec in onto["types"].items():
        if kind and name != kind:
            continue
        types[name] = {"label": spec["label"], "folder": spec["folder"], "required": spec.get("required", []),
                       "properties": {k: short(v) for k, v in spec["properties"].items()},
                       "relations": {r: ([name] if v.get("same_type") else v["to"])
                                     for r, v in onto["relations"].items() if allowed(v["from"], name)},
                       "facets": spec.get("facets", [])}
    return {"version": onto["version"], "common": list(onto["common"]), "tags": onto["tags"]["pattern"],
            "types": types}


def yaml_value(value) -> str:
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else \
        "null" if value is None else str(value).lower()


def render(data: dict) -> str:
    """Frontmatter YAML (entre ---) : genere en tête, listes en blocs comme Obsidian les écrit."""
    lines = ["---"]
    ordered = ({"genere": data["genere"]} if "genere" in data else {}) | data
    for key, value in ordered.items():
        # genere et tags suivent un motif sûr en YAML : écrits sans guillemets, comme Obsidian.
        write = str if key in ("genere", "tags") else yaml_value
        if isinstance(value, list):
            lines += [f"{key}:"] + [f"  - {write(v)}" for v in value]
        else:
            lines.append(f"{key}: {write(value)}")
    return "\n".join(lines + ["---"]) + "\n"
