"""Validation d'une description JSON contre le schéma d'entrée du contract.json du skill.

Sans dépendance : couvre le sous-ensemble de JSON Schema utilisé par les
contrats (type, required, properties, patternProperties,
additionalProperties, items, enum, minimum, maximum, minItems, maxItems,
minLength, pattern, anyOf, $ref vers #/$defs). Les messages donnent le chemin de l'erreur et, pour une
clé inconnue, la clé attendue la plus proche : l'agent corrige en une fois.

Source : shared/scripts/spec_schema.py, copiée dans scripts/lib/ des skills
par scripts/build.py. Ne modifiez pas les copies.
"""

import difflib
import json
import re
from pathlib import Path

NAMES = {"string": "texte", "integer": "entier", "number": "nombre", "boolean": "booléen",
         "array": "liste", "object": "objet", "null": "null"}
MAX_ERRORS = 10


def input_schema(script: str | Path) -> dict | None:
    """Schéma d'entrée du script, lu dans le contract.json de son skill."""
    script = Path(script).resolve()
    contract = json.loads((script.parent.parent / "contract.json").read_text(encoding="utf-8"))
    for entry in contract.get("scripts", []):
        if entry["name"] == script.name:
            return (entry.get("input") or {}).get("schema")
    return None


def kind_of(value) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    return {float: "number", str: "string", list: "array", dict: "object", type(None): "null"}[type(value)]


def is_type(value, expected: str) -> bool:
    actual = kind_of(value)
    return actual == expected or (expected == "number" and actual == "integer")


def check(value, schema: dict, root: dict | None = None, path: str = "") -> list[str]:
    """Liste des erreurs, en français, préfixées par le chemin (racine si vide)."""
    root = root or schema
    where = path or "racine"
    if "$ref" in schema:
        name = schema["$ref"].split("/")[-1]
        return check(value, root["$defs"][name], root, path)
    if "anyOf" in schema:
        variants = [check(value, variant, root, path) for variant in schema["anyOf"]]
        if any(not errors for errors in variants):
            return []
        return min(variants, key=len)
    types = schema.get("type")
    if types:
        types = types if isinstance(types, list) else [types]
        if not any(is_type(value, t) for t in types):
            wanted = " ou ".join(NAMES.get(t, t) for t in types)
            return [f"{where} : {wanted} attendu, reçu {NAMES[kind_of(value)]} {json.dumps(value, ensure_ascii=False)[:40]}"]
    errors = []
    if "enum" in schema and value not in schema["enum"]:
        allowed = ", ".join(json.dumps(v, ensure_ascii=False) for v in schema["enum"])
        errors.append(f"{where} : « {value} » non permis ({allowed})")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "minimum" in schema \
            and value < schema["minimum"]:
        errors.append(f"{where} : {value} inférieur au minimum {schema['minimum']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool) and "maximum" in schema \
            and value > schema["maximum"]:
        errors.append(f"{where} : {value} supérieur au maximum {schema['maximum']}")
    if isinstance(value, str) and len(value) < schema.get("minLength", 0):
        errors.append(f"{where} : texte vide")
    if isinstance(value, str) and "pattern" in schema and not re.search(schema["pattern"], value):
        errors.append(f"{where} : « {value} » ne suit pas le format {schema['pattern']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{where} : au moins {schema['minItems']} élément(s) attendu(s)")
        if len(value) > schema.get("maxItems", len(value)):
            errors.append(f"{where} : au plus {schema['maxItems']} élément(s) attendu(s), reçu {len(value)}")
        if "items" in schema:
            for index, item in enumerate(value):
                errors += check(item, schema["items"], root, f"{path}/{index}" if path else str(index))
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        for name in schema.get("required", []):
            if name not in value:
                errors.append(f"{where} : champ « {name} » manquant")
        for name, item in value.items():
            sub = f"{path}/{name}" if path else name
            if name in properties:
                errors += check(item, properties[name], root, sub)
                continue
            patterns = [p for p in schema.get("patternProperties", {}) if re.search(p, name)]
            if patterns:
                errors += check(item, schema["patternProperties"][patterns[0]], root, sub)
            elif schema.get("additionalProperties") is False:
                close = difflib.get_close_matches(name, list(properties), n=1, cutoff=0.6)
                hint = f" ; vouliez-vous « {close[0]} » ?" if close else f" (permis : {', '.join(properties)})"
                errors.append(f"{where} : clé inconnue « {name} »{hint}")
            elif isinstance(schema.get("additionalProperties"), dict):
                errors += check(item, schema["additionalProperties"], root, sub)
    return errors


def validate(spec, script: str | Path) -> list[str]:
    """Erreurs de la description au regard du schéma d'entrée du script (au plus MAX_ERRORS)."""
    schema = input_schema(script)
    if not schema:
        return []
    errors = check(spec, schema)
    if len(errors) > MAX_ERRORS:
        errors = errors[:MAX_ERRORS] + [f"... et {len(errors) - MAX_ERRORS} autres erreurs"]
    return [f"description : {e}" for e in errors]


def print_schema(script: str | Path) -> None:
    """Affiche le schéma d'entrée sur une ligne (option --schema des scripts)."""
    print(json.dumps(input_schema(script), ensure_ascii=False, separators=(",", ":")))
