"""Ontologie du vault Obsidian : construire et vérifier le frontmatter d'une note.

L'ontologie (`vault-ontology.json`, à côté de ce module) définit les types de
notes, leurs propriétés, les relations typées (propriétés dont la valeur est
un wikilink ou une liste de wikilinks) et la forme des tags. Un skill qui
écrit dans le vault construit le frontmatter avec `meta()` et le vérifie
avec `check_meta()` avant d'écrire ; `check_targets()` vérifie le type des
notes visées par les relations. `parse()` lit le frontmatter d'une note
(sous-ensemble YAML écrit par Obsidian et par ces skills). `Notes` rassemble
les notes d'un skill, les vérifie toutes, puis les écrit (rien si une seule
sort de l'ontologie) et retire ses notes devenues sans objet.

Source unique : ce module et `vault-ontology.json` vivent dans le skill
markdown-to-obsidian. Les autres skills les chargent par
`skill_paths.require_module`, avec le module `lib/vault_ontology.py` déclaré
dans le `requires` de leur contrat, sans copie.
"""

import contextlib
import json
import os
import re
import time
import unicodedata
from pathlib import Path

try:
    from .spec_schema import check
except ImportError:
    from spec_schema import check

HERE = Path(__file__).resolve().parent
LINK = re.compile(r"^\[\[([^\[\]|#]+)(#[^\[\]|]*)?(\|[^\[\]]*)?\]\]$")
BODY_LINK = re.compile(r"(?<!!)\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|[^\[\]]*)?\]\]")
# Verrou du vault : un seul script y écrit à la fois (skills lancés en parallèle par un workflow).
LOCK_NAME = ".myskills-vault.lock"
LOCK_STALE = 120  # secondes : au-delà, verrou d'une commande interrompue, repris


@contextlib.contextmanager
def vault_lock(vault: Path, wait: float | None = None):
    """Verrou du vault pour une écriture : lecture des notes visées, vérification, écriture, sections
    générées et tableaux, d'un seul tenant. Attend wait secondes (défaut : MYSKILLS_VAULT_LOCK_WAIT, sinon
    60), puis lève TimeoutError ; un verrou plus vieux que LOCK_STALE est repris."""
    wait = float(os.environ.get("MYSKILLS_VAULT_LOCK_WAIT", 60)) if wait is None else wait
    lock, deadline = Path(vault) / LOCK_NAME, time.monotonic() + wait
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    lock.unlink(missing_ok=True)
                    continue
            except OSError:
                continue
            if time.monotonic() > deadline:
                raise TimeoutError(f"vault occupé par un autre script depuis plus de {wait:g} s ({lock}) : "
                                   "relancez, ou supprimez ce fichier si aucun script ne tourne") from None
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def save(path: Path, data: str | bytes) -> None:
    """Écriture atomique (fichier temporaire puis remplacement) : un autre script ou Obsidian ne lit jamais une
    note à moitié écrite."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_bytes(data.encode("utf-8") if isinstance(data, str) else data)
    for _ in range(10):
        try:
            os.replace(tmp, path)
            return
        except PermissionError:  # Windows : fichier ouvert un instant par un autre programme
            time.sleep(0.1)
    os.replace(tmp, path)


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
        # Propriété vide (laissée vide dans Obsidian ou par un modèle) : comme absente.
        if name == "type" or value is None or value == "" or value == []:
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
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
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


# Caractères interdits dans un nom de fichier sous Windows, ou qui cassent un wikilink Obsidian.
FORBIDDEN = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')


def safe_name(text, default: str = "note") -> str:
    """Nom de note valable sous Windows, macOS et Linux et dans un wikilink."""
    return re.sub(r"\s+", " ", FORBIDDEN.sub("-", str(text))).strip().rstrip(". ") or default


def safe_folder(folder: str) -> str:
    """Dossier du vault (chemin relatif, séparateurs / ou \\), chaque partie rendue sûre."""
    return "/".join(safe_name(p) for p in re.split(r"[\\/]+", str(folder)) if p.strip())


LINKING = {"de", "du", "des", "d'", "la", "le", "les", "l'", "et", "à", "au", "aux", "en", "pour", "sur", "par",
           "un", "une", "-"}


def folder_key(title, default: str = "notes", limit: int = 40) -> str:
    """Sous-dossier court tiré d'un titre (constats, risques, lots, rapports) : « Option A - Application web
    dans le cloud européen » donne « Option A » ; un autre titre est coupé au mot sous limit caractères."""
    name = safe_name(title, default)
    found = re.match(r"(Option\s+[\w.-]+)\s+-\s+", name)
    if found:
        return found.group(1)
    if len(name) <= limit:
        return name
    words = name[:limit + 1].split(" ")[:-1] or [name[:limit]]
    while len(words) > 1 and words[-1].lower() in LINKING:
        words.pop()  # pas de « Chiffrage du portail de » : le dernier mot porte le sens
    return " ".join(words).rstrip(" ,;-.")


def folders_of(base: str, kind: str, title, default: str = "notes") -> tuple[str, tuple[str, ...]]:
    """Dossier court des notes d'un titre, et dossiers à nettoyer : lui et l'ancien dossier au titre long
    (migration des vaults écrits avant les dossiers courts : leurs notes générées y sont retirées)."""
    key, old = folder_key(title, default), safe_name(title, default)
    folder = f"{base}/{kind}/{key}"
    return folder, (folder,) + ((f"{base}/{kind}/{old}",) if old != key else ())


SNIPPET = "myskills-types"


def write_style(onto: dict, vault: Path) -> dict:
    """Couleurs des types (champ color de l'ontologie), à la demande seulement : groupes de couleurs de la vue
    graphe (.obsidian/graph.json, par tag type/<type>, les autres groupes et réglages gardés) et extrait CSS
    qui colore les tags type/<type> (.obsidian/snippets, activé dans appearance.json)."""
    prefix = onto["tags"]["type_prefix"]
    colored = [(kind, spec["color"]) for kind, spec in onto["types"].items() if spec.get("color")]
    config = Path(vault) / ".obsidian"
    config.mkdir(exist_ok=True)

    def read(name: str) -> dict:
        try:
            data = json.loads((config / name).read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    graph = read("graph.json")
    ours = f"tag:#{prefix}/"
    kept = [g for g in graph.get("colorGroups", []) if not str(g.get("query", "")).startswith(ours)]
    graph["colorGroups"] = kept + [{"query": f"{ours}{kind}", "color": {"a": 1, "rgb": int(color[1:], 16)}}
                                   for kind, color in colored]
    (config / "graph.json").write_text(json.dumps(graph, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    css = ["/* myskills : couleur des tags type/<type>, tirée de l'ontologie du vault ; réécrit par",
           "   vault_check.py --style. */"]
    css += [f'a.tag[href="#{prefix}/{kind}"] {{ background-color: {color}26; color: {color}; }}'
            for kind, color in colored]
    (config / "snippets").mkdir(exist_ok=True)
    snippet = config / "snippets" / f"{SNIPPET}.css"
    snippet.write_text("\n".join(css) + "\n", encoding="utf-8")
    appearance = read("appearance.json")
    enabled = [s for s in appearance.get("enabledCssSnippets", []) if s != SNIPPET] + [SNIPPET]
    appearance["enabledCssSnippets"] = enabled
    (config / "appearance.json").write_text(json.dumps(appearance, ensure_ascii=False, indent=2) + "\n",
                                            encoding="utf-8")
    return {"graph": str(config / "graph.json"), "groups": len(colored), "kept": len(kept), "snippet": str(snippet)}


TEMPLATES = "Modèles"
TEMPLATE_MARK = "myskills-modele"


def templates_folder(vault: Path) -> str | None:
    """Dossier des modèles du vault (.obsidian/templates.json du plugin cœur Modèles), sinon None."""
    try:
        folder = json.loads((Path(vault) / ".obsidian" / "templates.json").read_text(encoding="utf-8")).get("folder")
    except (OSError, ValueError, AttributeError):
        return None
    return str(folder).strip("/") or None if folder else None


def property_kind(schema: dict) -> str | None:
    """Type de propriété Obsidian (types.json) d'un schéma de l'ontologie, None s'il n'y en a pas d'évident."""
    if schema.get("type") == "array":
        return "multitext"
    if schema.get("type") in ("integer", "number"):
        return "number"
    if schema.get("type") == "boolean":
        return "checkbox"
    if str(schema.get("pattern", "")).startswith("^\\d{4}-\\d{2}-\\d{2}"):
        return "date"
    return "text" if schema.get("type") == "string" or "enum" in schema else None


def property_types(onto: dict) -> dict[str, str]:
    """Type Obsidian de chaque propriété et relation de l'ontologie ; une propriété aux types divergents
    d'un type de note à l'autre est laissée à Obsidian."""
    found: dict[str, set[str]] = {}
    schemas = [onto["common"]] + [spec.get("properties", {}) for spec in onto["types"].values()]
    for props in schemas:
        for name, schema in props.items():
            kind = property_kind(schema)
            if kind and name not in ("type", "genere"):
                found.setdefault(name, set()).add(kind)
    for name, spec in onto["relations"].items():
        found.setdefault(name, set()).add("multitext" if spec.get("many") else "text")
    out = {name: kinds.pop() for name, kinds in sorted(found.items()) if len(kinds) == 1}
    out["aliases"], out["tags"] = "aliases", "tags"
    return out


def template_text(onto: dict, kind: str) -> str:
    """Modèle de note d'un type (plugin cœur Modèles) : frontmatter avec ses propriétés obligatoires et ses
    relations à remplir, tag type/<type>, aide en callout sur les valeurs permises."""
    spec = onto["types"][kind]
    props = {**onto["common"], **spec.get("properties", {})}
    relations = [name for name, rel in onto["relations"].items()
                 if kind in rel.get("from", []) or "*" in rel.get("from", [])]
    lines = ["---", f"type: {json.dumps(kind)}"]
    for name in [n for n in spec.get("required", []) if n != "type"]:
        schema = props.get(name, {})
        value = '"{{date:YYYY-MM-DD}}"' if property_kind(schema) == "date" else \
            ("[]" if schema.get("type") == "array" else '""')
        lines.append(f"{name}: {value}")
    lines += [f"{name}: []" if onto["relations"][name].get("many") else f'{name}: ""' for name in relations]
    lines += [f"ontologie: {onto['version']}", "tags:", f"  - {type_tag(onto, kind)}", "---", "", "# {{title}}", ""]
    help_ = [spec.get("description", "")]
    allowed = [f"**{n}** : {', '.join(map(str, props[n]['enum']))}" for n in spec.get("required", []) + [
        n for n in spec.get("properties", {}) if n not in spec.get("required", [])] if "enum" in props.get(n, {})]
    help_ += ["Valeurs permises : " + " ; ".join(dict.fromkeys(allowed)) + "."] if allowed else []
    if relations:
        help_.append("Relations en wikilinks entre guillemets (\"[[Note]]\") : " + ", ".join(
            f"**{n}** vers {', '.join(onto['relations'][n]['to'])}" for n in relations) + ".")
    help_.append(f"Vérifiez la note avec `vault_check.py` (skill markdown-to-obsidian). %% {TEMPLATE_MARK} %%")
    return "\n".join(lines + callout("info", f"Modèle : {spec.get('label', kind)}", help_, folded=True)) + "\n"


def write_templates(onto: dict, vault: Path, folder: str = TEMPLATES) -> dict:
    """À la demande : un modèle par type dans folder (réglé dans .obsidian/templates.json pour le plugin cœur
    Modèles, activé dans core-plugins.json s'il existe) et le type Obsidian des propriétés de l'ontologie dans
    .obsidian/types.json (types que l'utilisateur a réglés lui-même gardés). Seuls les modèles de myskills
    (marque myskills-modele) sont réécrits."""
    vault, config = Path(vault), Path(vault) / ".obsidian"
    config.mkdir(exist_ok=True)

    def read(name: str):
        try:
            return json.loads((config / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None

    def dump(name: str, data) -> None:
        (config / name).write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    target, written, kept = vault / safe_folder(folder), 0, []
    target.mkdir(parents=True, exist_ok=True)
    for kind, spec in onto["types"].items():
        path = target / f"{safe_name(spec.get('label', kind))}.md"
        if path.is_file() and TEMPLATE_MARK not in path.read_text(encoding="utf-8", errors="replace"):
            kept.append(path.name)  # modèle de l'utilisateur au même nom : jamais écrasé
            continue
        path.write_text(template_text(onto, kind), encoding="utf-8", newline="\n")
        written += 1
    settings = read("templates.json")
    settings = settings if isinstance(settings, dict) else {}
    settings["folder"] = safe_folder(folder)
    settings.setdefault("dateFormat", "YYYY-MM-DD")
    dump("templates.json", settings)
    plugins, enabled = read("core-plugins.json"), False
    if isinstance(plugins, dict):
        plugins["templates"], enabled = True, True
        dump("core-plugins.json", plugins)
    elif isinstance(plugins, list):
        plugins, enabled = list(dict.fromkeys(plugins + ["templates"])), True
        dump("core-plugins.json", plugins)
    types = read("types.json")
    types = types if isinstance(types, dict) else {}
    current = types.get("types") if isinstance(types.get("types"), dict) else {}
    ours = property_types(onto)
    types["types"] = {**ours, **current}  # un type réglé par l'utilisateur l'emporte
    dump("types.json", types)
    return {"folder": safe_folder(folder), "templates": written, "kept": kept, "properties": len(ours),
            "plugin": enabled}


# --- Lisibilité dans Obsidian : nombres, libellés, callouts, titres et section des liens générés ---

THIN = " "  # espace fine insécable : séparateur des milliers en français


def number(value, decimals: int | None = None) -> str:
    """Nombre à la française : 264 857, 169,1 (décimales inutiles retirées si decimals est None)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if decimals is None:
        text = f"{value:,.2f}".rstrip("0").rstrip(".") if isinstance(value, float) else f"{value:,}"
    else:
        text = f"{value:,.{decimals}f}"
    return text.replace(",", "\x00").replace(".", ",").replace("\x00", THIN)


def plural(words: str) -> str:
    """Pluriel simple, mot à mot (constat ouvert : constats ouverts)."""
    return " ".join(w if w[-1:] in "sxz" or not w[-1:].isalpha() else w + "s" for w in words.split(" "))


def count(n, singular: str, many: str | None = None) -> str:
    """Nombre et nom accordés : 0 constat, 1 constat, 5 constats (pluriel donné ou mot à mot)."""
    return f"{number(n)} {singular if abs(n) < 2 else many or plural(singular)}"


def label(onto: dict, value) -> str:
    """Libellé affiché d'une valeur ou d'un nom de propriété : a-faire : à faire, true : oui."""
    if isinstance(value, bool):
        return "oui" if value else "non"
    if isinstance(value, (int, float)):
        return number(value)
    text = str(value)
    return onto.get("labels", {}).get(text) or text.replace("-", " ")


def callout(kind: str, title: str = "", lines=(), folded: bool = False) -> list[str]:
    """Callout Obsidian (> [!kind] titre), replié si folded, suivi d'une ligne vide."""
    head = f"> [!{kind}]{'-' if folded else ''} {title}".rstrip()
    return [head] + [f"> {line}".rstrip() for line in lines] + [""]


def short(text: str, limit: int = 80) -> str:
    """Libellé court : la première partie d'au moins trois mots avant un « : » (« Sécurité : Point d'entrée
    public sans WAF : F1 » donne « Point d'entrée public sans WAF »), coupée au mot sous limit caractères."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    parts = text.split(" : ")
    text = next((p for p in parts if len(p.split()) >= 3), text).rstrip(" .")
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0].rstrip(" ,;") + "…"


def detail(text: str, fallback: str = "", limit: int = 100) -> str:
    """Phrase de contexte d'un élément listé : ce qui suit le libellé court (short) du message, sinon fallback
    (« Scénario non satisfait sans risque noté : la connexion est refusée » donne « la connexion est refusée »)."""
    text = re.sub(r"\s+", " ", str(text)).strip()
    head = short(text, 10 ** 6)
    rest = text.split(head, 1)[1].lstrip(" :.") if head in text else ""
    rest = rest.rstrip(" .")
    if not rest or len(rest.split()) < 2:
        return fallback
    return rest if len(rest) <= limit else rest[:limit].rsplit(" ", 1)[0].rstrip(" ,;") + "…"


def heading(body: str) -> str | None:
    """Titre de la note : sa première ligne « # »."""
    return next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), None)


def with_alias(data: dict, title: str | None, rel: str) -> dict:
    """Frontmatter avec le titre de la note en alias s'il diffère du nom du fichier : le sélecteur rapide
    et la vue graphe trouvent la note par son titre."""
    name = rel.rsplit("/", 1)[-1]
    if not title or title == name:
        return data
    aliases = [a for a in (data.get("aliases") or []) if a != title]
    out = {}
    for key, value in data.items():
        if key == "ontologie":
            out["aliases"] = [title] + aliases
        if key != "aliases":
            out[key] = value
    out.setdefault("aliases", [title] + aliases)
    return out


LABELED_LINK = re.compile(r"(?<!!)\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\\?\|([^\[\]]*))?\]\]")
RAW_PLURAL = re.compile(r"\w\((?:s|e|es)\)")
RAW_AMOUNT = re.compile(r"(?<![\d.,  ])\d{4,}(?:[.,]\d+)?\s?(?:€|\$|£|euros?\b)")


def readability(body: str, title_of) -> list[str]:
    """Avertissements de lisibilité d'une note générée : lien libellé par un simple identifiant alors que la
    note visée a un titre (EF-001 au lieu de « EF-001 Déclarer un sinistre »), accord écrit « (s) », montant
    sans séparateur des milliers. title_of(cible) -> titre de la note visée ou None."""
    text = re.sub(r"```.*?```|`[^`\n]*`|%%.*?%%", "", body, flags=re.S)
    warnings = []
    for target, alias in LABELED_LINK.findall(text):
        shown = (alias or target.rsplit("/", 1)[-1]).strip()
        title = title_of(target.strip())
        if title and shown != title and shown not in title.split(" : ") and len(shown) * 2 < len(title) \
                and len(shown.split()) < 2:
            warnings.append(f"lisibilité : lien « {shown} » vers « {title} » : libellez-le avec le titre")
    warnings += [f"lisibilité : accord « {m} » : accordez selon le nombre (count)"
                 for m in dict.fromkeys(RAW_PLURAL.findall(text))]
    warnings += [f"lisibilité : montant « {m.strip()} » sans séparateur des milliers (number)"
                 for m in dict.fromkeys(RAW_AMOUNT.findall(text))]
    return warnings[:10]


HUB = "%% myskills : section générée, réécrite à chaque passage %%"
HUB_TITLE = "## Revues et analyses"
# Section de l'utilisateur dans une note générée : gardée à chaque réécriture, ses callouts relus par l'agent.
USER_TITLE = "## Mes notes"
USER_HINT = ("%% myskills : écrivez sous ce titre, la section est gardée à chaque passage ; "
             "un callout > [!question] ou > [!retour] est relu par l'agent %%")
ANNOTATION = re.compile(r"^>\s*\[!(question|retour)\][-+]?\s*(.*)$", re.I)


def user_section(text: str) -> str:
    """Ce que l'utilisateur a écrit sous « Mes notes » (sans le titre ni la consigne), vide sinon."""
    if USER_TITLE not in text:
        return ""
    part = text.split(USER_TITLE, 1)[1].split(HUB, 1)[0]
    return part.replace(USER_HINT, "").strip()


def with_user(text: str, section: str = "") -> str:
    """Texte d'une note générée terminé par sa section « Mes notes » (vide ou reprise de l'ancienne note),
    avant la section générée éventuelle."""
    hub = (HUB + text.split(HUB, 1)[1]) if HUB in text else ""
    base = text.split(HUB, 1)[0].split(USER_TITLE, 1)[0].rstrip()
    user = "\n".join([USER_TITLE, "", USER_HINT] + (["", section.strip()] if section.strip() else []))
    return base + "\n\n" + user + "\n" + ("\n" + hub.rstrip() + "\n" if hub else "")


def annotations(text: str) -> list[dict]:
    """Callouts [!question] et [!retour] de la section « Mes notes » : [{kind, text}], texte sur une ligne."""
    found, lines, i = [], user_section(text).splitlines(), 0
    while i < len(lines):
        match = ANNOTATION.match(lines[i].strip())
        i += 1
        if not match:
            continue
        parts = [match.group(2).strip()]
        while i < len(lines) and lines[i].lstrip().startswith(">"):
            parts.append(lines[i].lstrip().lstrip(">").strip())
            i += 1
        words = " ".join(p for p in parts if p)
        if words:
            found.append({"kind": match.group(1).lower(), "text": words})
    return found


def vault_annotations(vault: Path, folder: str) -> list[dict]:
    """Annotations des notes générées d'un dossier du vault : [{note, title, kind, text}], par note."""
    root, found = Path(vault) / folder if folder else Path(vault), []
    for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
        rel = path.relative_to(vault).with_suffix("").as_posix()
        if rel.split("/", 1)[0].startswith("."):
            continue
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        if USER_TITLE not in text or not text.startswith("---\ngenere:"):
            continue
        title = heading(parse(text)[1]) or path.stem
        found += [{"note": rel, "title": title, **a} for a in annotations(text)]
    return found


def hub_relations(onto: dict) -> list[str]:
    return [name for name, spec in onto["relations"].items() if spec.get("hub")]


def scan(vault: Path, folder: str) -> dict[str, tuple[dict, str]]:
    """Notes typées d'un dossier du vault : chemin -> (frontmatter, titre)."""
    root = Path(vault) / folder if folder else Path(vault)
    found = {}
    for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
        rel = path.relative_to(vault).with_suffix("").as_posix()
        if rel.split("/", 1)[0].startswith("."):
            continue
        data, body, _ = parse(path.read_text(encoding="utf-8", errors="replace"))
        if data and data.get("type"):
            found[rel] = (data, heading(body) or path.stem)
    return found


def hub_lines(onto: dict, rel: str, kind: str, notes: dict[str, tuple[dict, str]]) -> list[str]:
    """Section « Revues et analyses » d'une note : pour une note workflow, les revues et analyses de son
    dossier ; sinon les notes qui l'évaluent ou portent sur elle (relations hub de l'ontologie). Les notes
    issues d'une note listée (constats d'une revue, lots d'un chiffrage) y sont comptées, pas listées."""
    hubs = hub_relations(onto)
    sources = {t for name in hubs for t in onto["relations"][name]["from"]}
    types = onto["types"]

    def parent(meta):
        found = targets(meta.get("issu-de"))
        return found[0] if found else None
    tables = []
    if kind == "workflow":
        incoming = [r for r, (m, _) in notes.items() if m.get("type") in sources and not parent(m)]
        kinds = view_kinds(onto, notes)
        if kinds:
            names = [v["name"].lower() for k in kinds for v in types[k]["views"]]
            tables = [f"- Tableaux filtrables : {link(rel.rsplit('/', 1)[0] + '/' + BASE, 'Tableaux')} "
                      f"({', '.join(names)})"]
    else:
        incoming = [r for r, (m, _) in notes.items() if r != rel and any(rel in targets(m.get(n)) for n in hubs)]
    if not incoming:
        return [HUB, "", HUB_TITLE, ""] + tables if tables else []
    listed = set(incoming)
    incoming = [r for r in incoming if parent(notes[r][0]) not in listed]
    listed = set(incoming)
    children: dict[str, list[dict]] = {}
    for r, (m, _) in notes.items():
        if parent(m) in listed:
            children.setdefault(parent(m), []).append(m)

    def severity(meta):
        enum = types.get(meta.get("type"), {}).get("properties", {}).get("gravite", {}).get("enum", [])
        value = meta.get("gravite")
        return enum.index(value) if value in enum else len(enum)

    def is_open(meta):
        enum = types.get(meta.get("type"), {}).get("properties", {}).get("statut", {}).get("enum", [])
        return "ouvert" not in enum or meta.get("statut") in (None, "ouvert")

    def facets(meta):
        spec = types.get(meta.get("type"), {})
        values = [f"{label(onto, f)} {label(onto, meta[f])}" for f in spec.get("facets", [])
                  if meta.get(f) not in (None, "", []) and not isinstance(meta[f], (list, dict))]
        return f" ({', '.join(values)})" if values else ""

    def summary(items):
        parts = []
        for kind_ in dict.fromkeys(m.get("type") for m in items):
            group = [m for m in items if m.get("type") == kind_]
            spec = types.get(kind_, {})
            name = spec.get("label", kind_).lower()
            opened = [m for m in group if is_open(m)]
            ouvert = "ouvert" in spec.get("properties", {}).get("statut", {}).get("enum", [])
            text = count(len(opened), name + (" ouvert" if ouvert else ""),
                         (spec.get("folder") or plural(name)).lower() + (" ouverts" if ouvert else ""))
            high = sum(m.get("gravite") == "haute" for m in opened)
            parts.append(text + (f", dont {number(high)} de gravité haute" if high else ""))
        return " : " + " ; ".join(parts) if parts else ""

    def title(r):
        meta, text = notes[r]
        prefix = types.get(meta.get("type"), {}).get("label", "") + " : "
        return text.removeprefix(prefix) or r.rsplit("/", 1)[-1]

    order = sorted(incoming, key=lambda r: (types.get(notes[r][0].get("type"), {}).get("label", ""),
                                            severity(notes[r][0]), title(r)))
    lines, shown = [], {}
    for r in order:
        meta = notes[r][0]
        kind_ = meta.get("type")
        shown[kind_] = shown.get(kind_, 0) + 1
        if shown[kind_] > 10:
            continue
        lines.append(f"- {types.get(kind_, {}).get('label', kind_)} : {link(r, title(r))}{facets(meta)}"
                     f"{summary(children.get(r, []))}")
    for kind_, n in shown.items():
        if n > 10:
            lines.append(f"- et {count(n - 10, 'autre note', 'autres notes')} de type "
                         f"{types.get(kind_, {}).get('label', kind_).lower()}")
    return [HUB, "", HUB_TITLE, ""] + tables + lines


BASE = "Tableaux.base"
BASE_MARK = "# myskills : tableaux générés depuis l'ontologie du vault, réécrits à chaque passage"


def yaml_text(text) -> str:
    return "'" + str(text).replace("'", "''") + "'"


def view_kinds(onto: dict, notes: dict[str, tuple[dict, str]]) -> list[str]:
    """Types qui ont des vues (views de l'ontologie) et des notes parmi notes, dans l'ordre de l'ontologie."""
    present = {m.get("type") for m, _ in notes.values()}
    return [k for k, spec in onto["types"].items() if spec.get("views") and k in present]


def base_text(onto: dict, folder: str, kinds: list[str]) -> str:
    """Fichier Obsidian Bases (YAML) : une vue tableau par vue de l'ontologie des types kinds, sur les notes
    du dossier folder. Une énumération se trie dans son ordre (formule rang_<propriété>)."""
    formulas, shown, views = {}, {}, []
    for kind in kinds:
        spec = onto["types"][kind]
        schema = {**onto.get("common", {}), **spec.get("properties", {})}
        for view in spec["views"]:
            filters = [f'file.hasTag("{type_tag(onto, kind)}")']
            filters += [" || ".join(f"{name} == {json.dumps(v, ensure_ascii=False)}" for v in values)
                        for name, values in view.get("filter", {}).items()]
            sort = []
            for name in view.get("sort", []):
                enum = schema.get(name, {}).get("enum")
                if not enum:
                    sort.append(name if name.startswith("file.") else f"note.{name}")
                    continue
                formula = "rang_" + name.replace("-", "_")
                expr = str(len(enum) + 1)
                for rank, value in reversed(list(enumerate(enum, 1))):
                    expr = f"if({name} == {json.dumps(value, ensure_ascii=False)}, {rank}, {expr})"
                formulas[formula] = expr
                sort.append(f"formula.{formula}")
            for name in view["columns"]:
                shown[f"note.{name}"] = label(onto, name).capitalize()
            views += ["  - type: table", f"    name: {yaml_text(view['name'])}", "    filters:", "      and:"]
            views += [f"        - {yaml_text(f)}" for f in filters]
            views += ["    order:", "      - file.name", "      - note.aliases"]
            views += [f"      - note.{name}" for name in view["columns"]]
            if sort:
                views += ["    sort:"] + [line for prop in sort for line in
                                          (f"      - property: {prop}", "        direction: ASC")]
    lines = [BASE_MARK, "filters:", "  and:",
             f"    - {yaml_text('file.inFolder(' + json.dumps(folder, ensure_ascii=False) + ')')}"]
    if formulas:
        lines += ["formulas:"] + [f"  {name}: {yaml_text(expr)}" for name, expr in formulas.items()]
    lines += ["properties:", "  note.aliases:", "    displayName: Titre"]
    lines += [line for prop, name in shown.items() for line in (f"  {prop}:", f"    displayName: {yaml_text(name)}")]
    return "\n".join(lines + ["views:"] + views) + "\n"


def write_base(onto: dict, vault: Path, folder: str, notes: dict[str, tuple[dict, str]] | None = None) -> str | None:
    """Écrit (ou retire) <folder>/Tableaux.base selon les notes du dossier ; rend son chemin s'il existe.
    Un fichier Tableaux.base sans la marque de myskills appartient à l'utilisateur : jamais touché."""
    if not folder:
        return None
    path = Path(vault) / folder / BASE
    if path.is_file() and not path.read_text(encoding="utf-8", errors="replace").startswith(BASE_MARK):
        return None
    kinds = view_kinds(onto, scan(vault, folder) if notes is None else notes)
    if not kinds:
        if path.is_file():
            path.unlink()
        return None
    text = base_text(onto, folder, kinds)
    if not path.is_file() or path.read_text(encoding="utf-8") != text:
        save(path, text)
    return f"{folder}/{BASE}"


def with_hub(text: str, lines: list[str]) -> str:
    """Texte d'une note avec sa section générée remplacée (retirée si lines est vide)."""
    base = text.split(HUB, 1)[0].rstrip()
    return base + ("\n\n" + "\n".join(lines) if lines else "") + "\n"


def workflow_of(vault: Path, rel: str) -> str | None:
    """Note workflow la plus proche au-dessus de rel (même dossier ou dossiers parents)."""
    parts = rel.split("/")[:-1]
    while parts:
        folder = Path(vault, *parts)
        for path in sorted(folder.glob("*.md")):
            with open(path, encoding="utf-8", errors="replace") as handle:
                head = handle.read(400)
            if re.search(r'^type: "?workflow"?$', head, re.M):
                return "/".join(parts + [path.stem])
        parts.pop()
    return None


def hub_scope(vault: Path, rel: str, kind: str | None) -> str:
    """Dossier dont les notes alimentent la section générée de rel : celui de sa note workflow, sinon le
    dossier au-dessus du sien (Exigences/EF-001 : le dossier du workflow)."""
    flow = rel if kind == "workflow" else workflow_of(vault, rel)
    parts = (flow or rel).split("/")
    return "/".join(parts[:-1] if flow else parts[:-2])


class Hubs:
    """Sections générées « Revues et analyses » : notes du dossier lues une fois, notes en attente
    d'écriture (pending : chemin -> (frontmatter, titre)) prises à la place de leur version sur disque."""

    def __init__(self, onto: dict, vault: Path, pending: dict[str, tuple[dict, str]] | None = None):
        self.onto, self.vault, self.pending, self.cache = onto, Path(vault), pending or {}, {}

    def lines(self, rel: str, kind: str | None) -> list[str]:
        folder = hub_scope(self.vault, rel, kind)
        if folder not in self.cache:
            notes = scan(self.vault, folder)
            notes.update({r: v for r, v in self.pending.items() if not folder or r.startswith(folder + "/")})
            self.cache[folder] = notes
        return hub_lines(self.onto, rel, kind or "", self.cache[folder])

    def text(self, rel: str, kind: str | None, text: str) -> str:
        return with_hub(text, self.lines(rel, kind))


def refresh_hubs(onto: dict, vault: Path, written: dict[str, dict], hubs: "Hubs | None" = None) -> int:
    """Réécrit la section générée des notes visées par les notes écrites (relations hub) et de la note
    workflow de leur dossier, hors notes écrites. Seules les notes générées (propriété genere) sont touchées."""
    vault = Path(vault)
    wanted = {t for meta in written.values() for name in hub_relations(onto) for t in targets(meta.get(name))}
    wanted |= {w for w in (workflow_of(vault, r) for r in [*written, *wanted]) if w}
    hubs = hubs or Hubs(onto, vault)
    changed = 0
    for rel in sorted(wanted - set(written)):
        path = vault / f"{rel}.md"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
        data = parse(text)[0] or {}
        if not data.get("genere"):
            continue
        new = hubs.text(rel, data.get("type"), text)
        if new != text:
            save(path, new)
            changed += 1
    return changed


class Notes:
    """Notes typées écrites par un skill dans un vault : toutes vérifiées contre l'ontologie avant l'écriture."""

    def __init__(self, vault: Path, genere: str, onto: dict | None = None):
        self.vault, self.genere, self.onto = Path(vault), genere, onto or load()
        self.pending: dict[str, tuple] = {}
        self.metas: dict[str, dict] = {}
        self.texts: dict[str, str] = {}
        self.files: dict[str, Path] = {}  # copie dans le vault (chemin avec extension) -> fichier source

    def exists(self, rel: str) -> bool:
        return rel in self.pending or (self.vault / f"{rel}.md").is_file()

    def add(self, rel: str, kind: str, props: dict, relations: dict | None, body: list[str], tags=()) -> None:
        """Note rel (chemin relatif au vault, sans .md). À l'écriture, les relations vers une note absente
        (ni dans le vault, ni ajoutée) sont omises."""
        self.pending[rel] = (kind, props, relations or {}, body, tags)

    def title(self, rel: str, default: str) -> str:
        """Titre d'une note ajoutée ou déjà dans le vault (sa ligne « # »), pour libeller un lien vers elle."""
        if rel in self.pending:
            return heading("\n".join(self.pending[rel][3])) or default
        path = self.vault / f"{rel}.md"
        if path.is_file():
            return heading(parse(path.read_text(encoding="utf-8", errors="replace"))[1]) or default
        return default

    def attach(self, rel: str, source: Path) -> str:
        """Copie un livrable dans le vault (rel : chemin avec extension) pour le lier depuis une note ;
        un Markdown copié porte la marque genere et sa source. Rend le wikilink vers la copie, libellé par le
        titre du livrable."""
        source = Path(source)
        self.files[rel] = source
        title = heading(source.read_text(encoding="utf-8", errors="replace")) if source.suffix.lower() == ".md" \
            else None
        return link(rel.removesuffix(".md"), title or source.name)

    def build(self) -> None:
        for rel, (kind, props, relations, body, tags) in self.pending.items():
            kept = {}
            for name, value in relations.items():
                items = [v for v in (value if isinstance(value, list) else [value]) if v]
                items = [v for v in items if self.exists(v[0] if isinstance(v, tuple) else v)]
                if items:
                    kept[name] = items if isinstance(value, list) else items[0]
            self.metas[rel] = with_alias(meta(self.onto, kind, props, kept, tags, genere=self.genere),
                                         heading("\n".join(body)), rel)
            text = render(self.metas[rel]) + "\n" + "\n".join(body).rstrip() + "\n"
            path = self.vault / f"{rel}.md"
            old = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n") if path.is_file() else ""
            self.texts[rel] = with_user(text, user_section(old))

    def resolve(self, path: str):
        if path in self.metas:
            return self.metas[path]["type"]
        if not (self.vault / f"{path}.md").is_file():
            raise KeyError(path)
        return (parse((self.vault / f"{path}.md").read_text(encoding="utf-8", errors="replace"))[0] or {}).get("type")

    def write(self, errors: list[str], cleanup=(), warnings: list[str] | None = None) -> dict | None:
        """Vérifie puis écrit toutes les notes ; retire des dossiers cleanup les notes de ce skill non réécrites,
        sauf celles où l'utilisateur a écrit sous « Mes notes » (gardées, signalées dans warnings) ;
        met à jour la section « Revues et analyses » des notes écrites et des notes qu'elles visent. Le tout sous
        le verrou du vault : des skills lancés en parallèle ne perdent ni note ni section."""
        try:
            with vault_lock(self.vault):
                return self._write(errors, cleanup, warnings)
        except TimeoutError as error:
            errors.append(f"vault : {error}")
            return None

    def _write(self, errors: list[str], cleanup=(), warnings: list[str] | None = None) -> dict | None:
        self.build()
        invalid = [f"{rel} : {e}" for rel, m in self.metas.items()
                   for e in check_meta(self.onto, m, generated=True)[0] + check_targets(self.onto, m, self.resolve)[0]]
        if invalid:
            errors += ["vault : note hors ontologie, rien n'est écrit : " + e for e in invalid[:10]]
            return None
        removed, kept = 0, []
        mark = f"---\ngenere: {self.genere}\n"
        for sub in cleanup:
            folder = self.vault / sub
            for path in sorted(folder.glob("*.md")) if folder.is_dir() else []:
                rel = path.relative_to(self.vault).with_suffix("").as_posix()
                old = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
                if rel not in self.texts and old.startswith(mark):
                    if user_section(old):
                        kept.append(rel)  # note obsolète, mais l'utilisateur y a écrit : gardée
                        continue
                    path.unlink()
                    removed += 1
            if folder.is_dir() and not any(folder.iterdir()):
                folder.rmdir()  # ancien dossier vidé (migration vers les dossiers courts)
        # Section générée : chaque note visée (option, exigence, workflow) liste ce qui l'évalue.
        hubs = Hubs(self.onto, self.vault, {r: (m, heading(self.texts[r]) or r.rsplit("/", 1)[-1])
                                            for r, m in self.metas.items()})
        self.texts = {rel: hubs.text(rel, self.metas[rel]["type"], text) for rel, text in self.texts.items()}
        for rel, text in self.texts.items():
            path = self.vault / f"{rel}.md"
            if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
                continue
            save(path, text)
        for rel, source in self.files.items():
            path = self.vault / rel
            data = f"---\ngenere: {self.genere}\nsource: {json.dumps(source.name, ensure_ascii=False)}\n---\n\n" \
                .encode("utf-8") + source.read_bytes() if source.suffix.lower() == ".md" else source.read_bytes()
            if path.is_file() and path.read_bytes() == data:
                continue
            save(path, data)
        refresh_hubs(self.onto, self.vault, self.metas)
        for folder in sorted({hub_scope(self.vault, rel, m.get("type")) for rel, m in self.metas.items()}):
            write_base(self.onto, self.vault, folder)
        if warnings is not None:
            warnings += [f"vault : {rel} n'a plus lieu d'être, gardée pour vos notes : déplacez-les puis "
                         "supprimez-la" for rel in kept]
        return {"vault": str(self.vault), "notes": len(self.texts), "removed": removed}
