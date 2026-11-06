# /// script
# requires-python = ">=3.10"
# ///
"""Écrit le brouillon de modele.json depuis le schéma SQL d'une base existante (CREATE TABLE).

Pour un existant (rétro-documentation, modernisation), le modèle de données
actuel se tire du DDL au lieu d'être réécrit par le modèle. Le script, et
non le modèle :

- lit les CREATE TABLE (PostgreSQL, MySQL, SQL Server, Oracle, SQLite) :
  colonnes, types, NOT NULL, UNIQUE, clés primaires et étrangères, en
  ligne ou en contrainte de table, identifiants entre guillemets ;
- fait une entité par table (nom en PascalCase), un champ par colonne au
  type simple de data-model, une référence (`ref`) par clé étrangère ;
- reconnaît une table d'association (clé primaire faite de deux clés
  étrangères, rien d'autre) et en fait une relation n-n ;
- devine les données personnelles par le nom des colonnes (à relire) ;
- valide le brouillon contre le schéma de model_build.py avant de
  l'écrire, et refuse de réécrire une description existante.

Une instruction illisible est signalée avec sa ligne ; une clé étrangère
vers une table absente du fichier, une clé primaire composée ou absente
sont signalées et laissées à trancher.

    uv run scripts/model_import.py SCHEMA.sql [...] [--out modele.json] [--title TITRE]
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import check, input_schema  # noqa: E402

# Type SQL (premier mot, en minuscules) -> type simple de data-model.
TYPES = {"uuid": "uuid", "uniqueidentifier": "uuid",
         "varchar": "string", "char": "string", "character": "string", "nvarchar": "string", "nchar": "string",
         "varchar2": "string", "nvarchar2": "string", "citext": "string", "enum": "string", "time": "string",
         "text": "text", "clob": "text", "nclob": "text", "longtext": "text", "mediumtext": "text", "ntext": "text",
         "tinytext": "text",
         "int": "integer", "integer": "integer", "bigint": "integer", "smallint": "integer", "tinyint": "integer",
         "mediumint": "integer", "serial": "integer", "bigserial": "integer", "smallserial": "integer",
         "int2": "integer", "int4": "integer", "int8": "integer",
         "numeric": "decimal", "decimal": "decimal", "money": "decimal", "number": "decimal",
         "real": "number", "float": "number", "double": "number", "float4": "number", "float8": "number",
         "bool": "boolean", "boolean": "boolean", "bit": "boolean",
         "date": "date",
         "timestamp": "datetime", "timestamptz": "datetime", "datetime": "datetime", "datetime2": "datetime",
         "smalldatetime": "datetime", "datetimeoffset": "datetime",
         "json": "json", "jsonb": "json", "xml": "text",
         "bytea": "binary", "blob": "binary", "binary": "binary", "varbinary": "binary", "longblob": "binary",
         "image": "binary", "raw": "binary"}
# Nom de colonne -> nature de donnée personnelle devinée (à relire).
PERSONAL = [(re.compile(r"(sante|health|diagnos|patholog|blessure|medical|handicap)"), "sante"),
            (re.compile(r"(iban|bic|carte_?banc|card_?number|salaire|salary|revenu)"), "financier"),
            (re.compile(r"(e_?mail|courriel|telephone|phone|mobile|portable)"), "contact"),
            (re.compile(r"(adresse|address|code_?postal|zip|ville|city|latitude|longitude|geoloc)"), "localisation"),
            (re.compile(r"(^nom$|_nom$|^nom_|prenom|first_?name|last_?name|surname|naissance|birth|"
                        r"^nir$|secu|passeport|passport)"), "identite")]
CREATE = re.compile(r"\bcreate\s+(?:(?:global\s+|local\s+)?(?:temporary|temp)\s+)?table\s+(?:if\s+not\s+exists\s+)?",
                    re.IGNORECASE)
IDENT = r'(?:"[^"]+"|`[^`]+`|\[[^\]]+\]|[\w$]+)'
NAME = re.compile(rf"\s*({IDENT}(?:\s*\.\s*{IDENT})*)\s*\(", re.IGNORECASE)


def unquote(name: str) -> str:
    return name.strip().strip('"`[]')


def last(name: str) -> str:
    """Dernier élément d'un nom qualifié (schéma.table)."""
    return unquote(re.split(r"\s*\.\s*(?=(?:[^\"]*\"[^\"]*\")*[^\"]*$)", name.strip())[-1])


def pascal(name: str) -> str:
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w]
    value = "".join(w[:1].upper() + w[1:] for w in words) or "Table"
    return value if value[0].isalpha() else "T" + value


def snake(name: str) -> str:
    value = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", unquote(name))
    value = re.sub(r"[^a-z0-9_]+", "_", value.lower()).strip("_") or "champ"
    return value if value[0].isalpha() else "c_" + value


def strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", lambda m: re.sub(r"[^\n]", " ", m.group(0)), text, flags=re.DOTALL)
    return re.sub(r"--[^\n]*", "", text)


def split_top(body: str) -> list[str]:
    """Éléments d'une liste séparés par des virgules hors parenthèses et guillemets."""
    items, depth, quote, current = [], 0, None, []
    for char in body:
        if quote:
            current.append(char)
            if char == quote:
                quote = None
            continue
        if char in "\"'`":
            quote = char
        elif char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif char == "," and depth == 0:
            items.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    if "".join(current).strip():
        items.append("".join(current).strip())
    return items


def columns_of(text: str) -> list[str]:
    return [unquote(c) for c in split_top(text)]


def parse(path: Path, errors: list[str], warnings: list[str]) -> list[dict]:
    """Tables d'un fichier SQL : nom, colonnes, clé primaire, uniques, clés étrangères."""
    text = strip_comments(path.read_text(encoding="utf-8", errors="replace"))
    tables = []
    for match in CREATE.finditer(text):
        line = text.count("\n", 0, match.start()) + 1
        head = NAME.match(text, match.end())
        if not head:
            errors.append(f"{path.name}:{line} : CREATE TABLE illisible (nom de table puis parenthèse attendus)")
            continue
        start, depth, end = head.end(), 1, None
        for index in range(start, len(text)):
            depth += {"(": 1, ")": -1}.get(text[index], 0)
            if depth == 0:
                end = index
                break
        if end is None:
            errors.append(f"{path.name}:{line} : parenthèse fermante absente pour la table {head.group(1)}")
            continue
        table = {"name": last(head.group(1)), "qualified": head.group(1).strip(), "line": line, "columns": [],
                 "pk": [], "unique": set(), "fks": {}, "file": path.name}
        for item in split_top(text[start:end]):
            lowered = item.lower()
            constraint = re.sub(rf"^constraint\s+{IDENT}\s+", "", item, flags=re.IGNORECASE)
            low = constraint.lower()
            if low.startswith("primary key"):
                cols = re.search(r"\((.*)\)", constraint, re.DOTALL)
                table["pk"] = columns_of(cols.group(1)) if cols else []
            elif low.startswith("foreign key"):
                fk = re.match(rf"foreign\s+key\s*\((.*?)\)\s*references\s+({IDENT}(?:\s*\.\s*{IDENT})*)",
                              constraint, re.IGNORECASE | re.DOTALL)
                if fk:
                    for col in columns_of(fk.group(1)):
                        table["fks"][col.lower()] = last(fk.group(2))
                else:
                    warnings.append(f"{path.name}:{line} : contrainte FOREIGN KEY illisible dans {table['name']}")
            elif low.startswith("unique"):
                cols = re.search(r"\((.*)\)", constraint, re.DOTALL)
                if cols and len(columns_of(cols.group(1))) == 1:
                    table["unique"].add(columns_of(cols.group(1))[0].lower())
            elif re.match(r"(check|index|key|exclude|fulltext|spatial)\b", low) or lowered.startswith("like "):
                continue
            else:
                col = re.match(rf"({IDENT})\s+([A-Za-z_][\w ]*?)(?:\s*\(|\s|$)(.*)", item, re.DOTALL)
                if not col:
                    warnings.append(f"{path.name}:{line} : colonne illisible dans {table['name']} : {item[:60]}")
                    continue
                name, kind, rest = unquote(col.group(1)), col.group(2).strip().lower(), item[col.end(2):].lower()
                first = kind.split()[0]
                if first == "double" or first == "character" and "varying" in kind:
                    first = "double" if first == "double" else "varchar"
                table["columns"].append({"name": name, "sql": kind, "type": TYPES.get(first),
                                         "required": "not null" in rest, "unique": " unique" in f" {rest}",
                                         "pk": "primary key" in rest})
                ref = re.search(rf"references\s+({IDENT}(?:\s*\.\s*{IDENT})*)", item, re.IGNORECASE)
                if ref:
                    table["fks"][name.lower()] = last(ref.group(1))
        if not table["pk"]:
            table["pk"] = [c["name"] for c in table["columns"] if c["pk"]]
        tables.append(table)
    return tables


def build(tables: list[dict], title: str, warnings: list[str]) -> tuple[dict, dict]:
    """Description de data-model : entités, références, relations n-n des tables d'association."""
    by_table = {t["name"].lower(): t for t in tables}
    entity = {t["name"].lower(): pascal(t["name"]) for t in tables}
    stats = {"associations": [], "personal": []}
    associations = set()
    for t in tables:
        pk = [c.lower() for c in t["pk"]]
        targets = [t["fks"].get(c) for c in pk]
        if len(pk) == 2 and all(targets) and len(t["columns"]) == 2 \
                and all(x.lower() in by_table for x in targets):
            associations.add(t["name"].lower())
            stats["associations"].append(t["name"])
    entities, relations = [], []
    for t in tables:
        if t["name"].lower() in associations:
            a, b = (t["fks"][c.lower()] for c in t["pk"])
            relations.append({"from": entity[a.lower()], "to": entity[b.lower()], "kind": "n-n",
                              "label": t["name"].replace("_", " ")[:80]})
            continue
        pk = [c.lower() for c in t["pk"]]
        if not pk:
            warnings.append(f"{t['file']}:{t['line']} : table {t['name']} sans clé primaire : "
                            f"clé posée sur la première colonne, à trancher")
            pk = [t["columns"][0]["name"].lower()] if t["columns"] else []
        elif len(pk) > 1:
            warnings.append(f"{t['file']}:{t['line']} : clé primaire composée de {t['name']} ({', '.join(t['pk'])}) : "
                            "clé posée sur sa première colonne, à trancher")
        fields, seen = [], set()
        for c in t["columns"]:
            name = snake(c["name"])
            if name in seen:
                warnings.append(f"{t['name']}.{c['name']} : nom déjà pris une fois normalisé ({name}), colonne ignorée")
                continue
            seen.add(name)
            field = {"name": name, "type": c["type"] or "string"}
            if c["type"] is None:
                warnings.append(f"{t['name']}.{c['name']} : type SQL « {c['sql']} » inconnu, pris pour string")
            if c["name"].lower() == pk[0]:
                field["key"] = True
            elif c["required"]:
                field["required"] = True
            if c["unique"] or c["name"].lower() in t["unique"]:
                if not field.get("key"):
                    field["unique"] = True
            target = t["fks"].get(c["name"].lower())
            if target and not field.get("key"):
                if target.lower() in entity and target.lower() not in associations:
                    field["ref"] = entity[target.lower()]
                else:
                    warnings.append(f"{t['name']}.{c['name']} : clé étrangère vers {target}, table absente du "
                                    "fichier : référence non reprise")
            nature = next((n for rx, n in PERSONAL if rx.search(name)), None)
            if nature:
                field["personal"] = nature
                stats["personal"].append(f"{entity[t['name'].lower()]}.{name}")
            field["description"] = f"colonne {c['name']} ({c['sql']})"[:300]
            fields.append(field)
        item = {"name": entity[t["name"].lower()], "label": t["name"], "fields": fields}
        if t["qualified"] != t["name"]:
            item["description"] = f"table {t['qualified']}"
        entities.append(item)
    if stats["personal"]:
        warnings.append(f"{len(stats['personal'])} donnée(s) personnelle(s) devinée(s) par le nom de colonne, à relire : "
                        + ", ".join(stats["personal"][:8]) + (" ..." if len(stats["personal"]) > 8 else ""))
    return {"title": title, "entities": entities, "relations": relations}, stats


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", type=Path, nargs="+", help="fichiers SQL (DDL) ou dossiers qui en contiennent")
    parser.add_argument("--out", type=Path, help="description écrite (défaut : modele.json à côté de la première source)")
    parser.add_argument("--title", help="titre du modèle (défaut : « Modèle de données actuel »)")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    report = {"inputs": [str(s) for s in args.sources], "output": None, "tables": 0, "entities": 0,
              "relations": 0, "associations": [], "personal_fields": [], "errors": errors, "warnings": warnings}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    files = []
    for source in args.sources:
        if source.is_dir():
            files += sorted(source.rglob("*.sql"))
        elif source.is_file():
            files.append(source)
        else:
            errors.append(f"{source} : introuvable")
    if not files and not errors:
        errors.append("aucun fichier .sql trouvé")
    out = args.out or (files[0].parent / "modele.json" if files else Path("modele.json"))
    if out.exists():
        errors.append(f"{out} existe déjà : model_import.py ne réécrit pas une description")
    if errors:
        return done(1)
    tables = []
    for path in files:
        tables += parse(path, errors, warnings)
    names = [t["name"].lower() for t in tables]
    errors += [f"table « {n} » définie plusieurs fois" for n in sorted({n for n in names if names.count(n) > 1})]
    if not tables and not errors:
        errors.append("aucun CREATE TABLE reconnu")
    if errors:
        return done(1)
    spec, stats = build(tables, args.title or "Modèle de données actuel", warnings)
    if not spec["entities"]:
        errors.append("aucune entité : toutes les tables sont des tables d'association")
        return done(1)
    schema = input_schema(Path(__file__).with_name("model_build.py"))
    errors += [f"brouillon non conforme à model_build.py : {e}" for e in check(spec, schema)]
    if errors:
        return done(1)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(output=str(out), tables=len(tables), entities=len(spec["entities"]),
                  relations=len(spec["relations"]), associations=stats["associations"],
                  personal_fields=stats["personal"])
    warnings.append(f"brouillon : relire les libellés, les données personnelles et les relations, puis "
                    f"model_build.py {out.name}")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
