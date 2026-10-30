# /// script
# requires-python = ">=3.10"
# ///
"""Écrit les contrats d'interface (OpenAPI 3.1, AsyncAPI 3.0) d'une description JSON courte et les contrôle.

Le modèle décrit les ressources (champs et types simples), les opérations
REST (méthode, chemin, ressource reçue et rendue, composant qui les porte,
exigences) et les événements (canal, ressource transportée, envoi ou
réception). Le script, et non le modèle, écrit le YAML et contrôle :

- noms uniques, une seule opération par méthode et chemin, chemin qui
  commence par / ;
- types connus (string, integer, number, boolean, date, date-time, uuid,
  email, uri, binary, une ressource, ou une liste `X[]`) et ressources
  citées qui existent ; champs obligatoires déclarés ;
- pas de corps de requête pour GET et DELETE ;
- exigences citées présentes dans exigences.json, exigence fonctionnelle
  indispensable portée par aucune opération ni aucun événement (avertie) ;
- composant porteur présent dans l'option d'architecture (`source`) ;
- opération d'écriture sans sécurité (avertie).

Écrit <nom>.openapi.yaml (s'il y a des opérations), <nom>.asyncapi.yaml
(s'il y a des événements) et <nom>.api.md (tableaux et couverture des
exigences), puis relit chaque YAML écrit : toutes les références $ref
doivent se résoudre.

    uv run scripts/api_build.py API.json [--out-dir DOSSIER] | --schema
"""

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

TYPES = {"string": {"type": "string"}, "integer": {"type": "integer"}, "number": {"type": "number"},
         "boolean": {"type": "boolean"}, "date": {"type": "string", "format": "date"},
         "date-time": {"type": "string", "format": "date-time"}, "uuid": {"type": "string", "format": "uuid"},
         "email": {"type": "string", "format": "email"}, "uri": {"type": "string", "format": "uri"},
         "binary": {"type": "string", "contentEncoding": "base64"}}
SECURITY = {"oauth2": {"type": "oauth2", "flows": {"clientCredentials": {"tokenUrl": "/oauth/token", "scopes": {}}}},
            "oidc": {"type": "openIdConnect", "openIdConnectUrl": "/.well-known/openid-configuration"},
            "bearer": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
            "apikey": {"type": "apiKey", "in": "header", "name": "X-API-Key"}}
WRITE = {"POST", "PUT", "PATCH", "DELETE"}
HTTP_ERRORS = {400: "Requête invalide", 401: "Non authentifié", 403: "Accès refusé", 404: "Introuvable",
               409: "Conflit", 422: "Entité non traitable", 429: "Trop de requêtes", 500: "Erreur interne",
               503: "Service indisponible"}
SIMPLE_KEY = re.compile(r"^[A-Za-z_$][A-Za-z0-9_.$-]*$")


def close(name: str, known) -> str:
    match = difflib.get_close_matches(name, list(known), n=1)
    return f" ; vouliez-vous « {match[0]} » ?" if match else ""


def type_schema(value: str, resources: set[str], where: str, errors: list[str]) -> dict:
    """Schéma OpenAPI d'un type simple, d'une ressource ou d'une liste `X[]`."""
    if value.endswith("[]"):
        return {"type": "array", "items": type_schema(value[:-2], resources, where, errors)}
    if value in TYPES:
        return dict(TYPES[value])
    if value in resources:
        return {"$ref": f"#/components/schemas/{value}"}
    errors.append(f"{where} : type « {value} » inconnu ({', '.join(TYPES)}, une ressource ou X[])"
                  + close(value, [*TYPES, *resources]))
    return {}


def resource_schemas(spec: dict, errors: list[str]) -> dict:
    names = [r["name"] for r in spec.get("resources", [])]
    known = set(names)
    errors += [f"resources : « {n} » en double" for n in sorted({n for n in names if names.count(n) > 1})]
    schemas = {}
    for i, res in enumerate(spec.get("resources", [])):
        where = f"resources/{i} ({res['name']})"
        props = {}
        for field, kind in res["fields"].items():
            props[field] = type_schema(kind, known, f"{where}/fields/{field}", errors)
            if field in res.get("enums", {}):
                props[field]["enum"] = res["enums"][field]
        for field in res.get("required", []):
            if field not in res["fields"]:
                errors.append(f"{where}/required : champ « {field} » absent de fields" + close(field, res["fields"]))
        for field in res.get("enums", {}):
            if field not in res["fields"]:
                errors.append(f"{where}/enums : champ « {field} » absent de fields" + close(field, res["fields"]))
        schema = {"type": "object", "properties": props}
        if res.get("description"):
            schema["description"] = res["description"]
        if res.get("required"):
            schema["required"] = res["required"]
        schemas[res["name"]] = schema
    return schemas


def body(kind: str, known: set[str], where: str, errors: list[str]) -> dict:
    return {"content": {"application/json": {"schema": type_schema(kind, known, where, errors)}}}


def openapi(spec: dict, schemas: dict, errors: list[str], warnings: list[str]) -> dict:
    known, security = set(schemas), spec.get("security", "none")
    doc = {"openapi": "3.1.0", "info": {"title": spec["title"], "version": spec.get("version", "1.0.0")}}
    if spec.get("description"):
        doc["info"]["description"] = spec["description"]
    if spec.get("servers"):
        doc["servers"] = [{"url": url} for url in spec["servers"]]
    paths: dict = {}
    seen: dict = {}
    for i, op in enumerate(spec.get("operations", [])):
        where, method = f"operations/{i} ({op['id']})", op["method"]
        if not op["path"].startswith("/"):
            errors.append(f"{where}/path : « {op['path']} » doit commencer par /")
        key = (method, op["path"])
        if key in seen:
            errors.append(f"{where} : {method} {op['path']} déjà décrite par {seen[key]}")
        seen[key] = op["id"]
        item = {"operationId": op["id"], "summary": op["summary"]}
        if op.get("component"):
            item["tags"] = [op["component"]]
        params = [{"name": p, "in": "path", "required": True, "schema": {"type": "string"}}
                  for p in re.findall(r"\{([^}/]+)\}", op["path"])]
        params += [{"name": name, "in": "query", "required": False,
                    "schema": type_schema(kind, known, f"{where}/query/{name}", errors)}
                   for name, kind in op.get("query", {}).items()]
        if params:
            item["parameters"] = params
        if op.get("request"):
            if method in ("GET", "DELETE"):
                errors.append(f"{where}/request : pas de corps de requête pour {method}")
            item["requestBody"] = {"required": True, **body(op["request"], known, f"{where}/request", errors)}
        status = str(op.get("status", 201 if method == "POST" else 204 if method == "DELETE" and
                                not op.get("response") else 200))
        responses = {status: {"description": "Succès"}}
        if op.get("response"):
            responses[status].update(body(op["response"], known, f"{where}/response", errors))
        for code in op.get("errors", []):
            responses[str(code)] = {"description": HTTP_ERRORS.get(code, "Erreur")}
        item["responses"] = responses
        if op.get("refs"):
            item["x-requirements"] = op["refs"]
        if op.get("public"):
            item["security"] = []
        elif security == "none" and method in WRITE:
            warnings.append(f"{where} : {method} sans sécurité (security : none) ; déclarez security ou public")
        paths.setdefault(op["path"], {})[method.lower()] = item
    doc["paths"] = paths
    doc["components"] = {"schemas": schemas}
    if security != "none":
        doc["components"]["securitySchemes"] = {security: SECURITY[security]}
        doc["security"] = [{security: []}]
    return doc


def asyncapi(spec: dict, schemas: dict, errors: list[str]) -> dict:
    known = set(schemas)
    doc = {"asyncapi": "3.0.0", "info": {"title": spec["title"], "version": spec.get("version", "1.0.0")}}
    channels, operations, messages = {}, {}, {}
    names = [e["name"] for e in spec.get("events", [])]
    errors += [f"events : « {n} » en double" for n in sorted({n for n in names if names.count(n) > 1})]
    for i, event in enumerate(spec.get("events", [])):
        where, name = f"events/{i} ({event['name']})", event["name"]
        channel = re.sub(r"[^A-Za-z0-9_-]", "-", event["channel"])
        messages[name] = {"name": name, "payload": type_schema(event["payload"], known, f"{where}/payload", errors)}
        if event.get("summary"):
            messages[name]["summary"] = event["summary"]
        channels.setdefault(channel, {"address": event["channel"], "messages": {}})["messages"][name] = \
            {"$ref": f"#/components/messages/{name}"}
        operation = {"action": event.get("action", "send"), "channel": {"$ref": f"#/channels/{channel}"},
                     "messages": [{"$ref": f"#/channels/{channel}/messages/{name}"}]}
        if event.get("component"):
            operation["tags"] = [{"name": event["component"]}]
        if event.get("refs"):
            operation["x-requirements"] = event["refs"]
        operations[f"{operation['action']}{name}"] = operation
    doc.update(channels=channels, operations=operations, components={"messages": messages, "schemas": schemas})
    return doc


def scalar(value) -> str:
    return json.dumps(value, ensure_ascii=False)


def to_yaml(value, indent: int = 0) -> list[str]:
    """YAML en bloc, chaînes entre guillemets (sous-ensemble sûr et relu par from_yaml)."""
    pad = "  " * indent
    lines = []
    if isinstance(value, dict):
        if not value:
            return [pad + "{}"]
        for key, item in value.items():
            name = key if SIMPLE_KEY.match(key) else scalar(key)
            if isinstance(item, (dict, list)) and item:
                lines += [f"{pad}{name}:"] + to_yaml(item, indent + 1)
            else:
                lines.append(f"{pad}{name}: {('{}' if item == {} else '[]') if item in ({}, []) else scalar(item)}")
    else:
        for item in value:
            if isinstance(item, (dict, list)) and item:
                lines += [f"{pad}-"] + to_yaml(item, indent + 1)
            else:
                lines.append(f"{pad}- {('{}' if item == {} else '[]') if item in ({}, []) else scalar(item)}")
    return lines


def from_yaml(text: str):
    """Relit le YAML écrit par to_yaml (indentation de 2, chaînes JSON ; commentaires # ignorés)."""
    rows = [(len(line) - len(line.lstrip(" ")), line.strip()) for line in text.splitlines()
            if line.strip() and not line.lstrip().startswith("#")]

    def value_of(raw: str):
        return {} if raw == "{}" else [] if raw == "[]" else json.loads(raw)

    def key_of(raw: str) -> tuple[str, str]:
        if raw.startswith('"'):
            end = raw.index('":') + 1
            return json.loads(raw[:end]), raw[end + 1:].strip()
        name, _, rest = raw.partition(":")
        return name, rest.strip()

    def block(i: int, depth: int):
        if rows[i][1] == "-" or rows[i][1].startswith("- "):
            out = []
            while i < len(rows) and rows[i][0] == depth and (rows[i][1] == "-" or rows[i][1].startswith("- ")):
                if rows[i][1] == "-":
                    item, i = block(i + 1, rows[i + 1][0])
                    out.append(item)
                else:
                    out.append(value_of(rows[i][1][2:]))
                    i += 1
            return out, i
        out = {}
        while i < len(rows) and rows[i][0] == depth:
            key, rest = key_of(rows[i][1])
            if rest:
                out[key] = value_of(rest)
                i += 1
            else:
                out[key], i = block(i + 1, rows[i + 1][0])
        return out, i

    return block(0, 0)[0] if rows else None


def refs_of(value, found: list[str]) -> list[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            if key == "$ref":
                found.append(item)
            else:
                refs_of(item, found)
    elif isinstance(value, list):
        for item in value:
            refs_of(item, found)
    return found


def resolve(doc: dict, ref: str) -> bool:
    node = doc
    for part in ref.removeprefix("#/").split("/"):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


def requirements(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> dict | None:
    """Exigences d'exigences.json (validé par requirements-catalog quand il est installé), ou None."""
    if not spec.get("requirements"):
        if any(item.get("refs") for item in spec.get("operations", []) + spec.get("events", [])):
            warnings.append("exigences citées sans requirements (exigences.json) : non vérifiées")
        return None
    try:
        data = json.loads((base / spec["requirements"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"requirements : {spec['requirements']} illisible ({error})")
        return None
    schema = schema_of("requirements-catalog", "req_build.py")
    if schema is None:
        warnings.append("exigences.json non validé : " + absent("requirements-catalog", "req_build.py"))
    else:
        errors += [f"requirements ({spec['requirements']}) : {e}" for e in check(data, schema)]
    return {r["id"]: r for r in data.get("requirements", []) if isinstance(r, dict) and "id" in r}


def components(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> set[str] | None:
    """Composants de l'option d'architecture citée (source), ou None."""
    source = spec.get("source")
    if not source:
        return None
    try:
        data = json.loads((base / source["options"]).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"source : {source['options']} illisible ({error})")
        return None
    schema = schema_of("architecture-options", "options_build.py")
    if schema is None:
        warnings.append("options.json non validé : " + absent("architecture-options", "options_build.py"))
    else:
        errors += [f"source ({source['options']}) : {e}" for e in check(data, schema)]
    option = next((o for o in data.get("options", []) if o.get("id") == source["option"]), None)
    if option is None:
        errors.append(f"source/option : « {source['option']} » absente de {source['options']}"
                      + close(source["option"], [o.get("id", "") for o in data.get("options", [])]))
        return None
    return {c["id"] for c in option.get("components", [])}


def markdown(spec: dict, covered: dict, uncovered: list[str], outputs: list[Path]) -> str:
    lines = [f"# Contrats d'interface : {spec['title']}", "",
             f"Version {spec.get('version', '1.0.0')}, sécurité : {spec.get('security', 'none')}. "
             "Fichiers écrits par `api_build.py` : " + ", ".join(f"`{p.name}`" for p in outputs) + ".", ""]
    if spec.get("operations"):
        lines += ["## Opérations", "", "| Opération | Méthode | Chemin | Résumé | Reçoit | Rend | Composant | Exigences |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- |"]
        for op in spec["operations"]:
            lines.append(f"| {op['id']} | {op['method']} | `{op['path']}` | {op['summary']} | {op.get('request', '-')} | "
                         f"{op.get('response', '-')} | {op.get('component', '-')} | {', '.join(op.get('refs', [])) or '-'} |")
        lines.append("")
    if spec.get("events"):
        lines += ["## Événements", "", "| Événement | Canal | Action | Contenu | Composant | Exigences |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for e in spec["events"]:
            lines.append(f"| {e['name']} | `{e['channel']}` | {e.get('action', 'send')} | {e['payload']} | "
                         f"{e.get('component', '-')} | {', '.join(e.get('refs', [])) or '-'} |")
        lines.append("")
    lines += ["## Ressources", "", "| Ressource | Champs | Obligatoires |", "| --- | --- | --- |"]
    for res in spec.get("resources", []):
        fields = ", ".join(f"{k} ({v})" for k, v in res["fields"].items())
        lines.append(f"| {res['name']} | {fields} | {', '.join(res.get('required', [])) or '-'} |")
    if covered or uncovered:
        lines += ["", "## Couverture des exigences", ""]
        lines += [f"- **{rid}** : {', '.join(items)}" for rid, items in sorted(covered.items())]
        if uncovered:
            lines += ["", "Exigences fonctionnelles indispensables portées par aucune interface : "
                      + ", ".join(uncovered) + "."]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description API.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.spec), "outputs": [], "operations": 0, "events": 0, "resources": 0,
              "covered": [], "uncovered": [], "errors": errors, "warnings": warnings}
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    errors += validate(spec, __file__)
    if isinstance(spec, dict) and not spec.get("operations") and not spec.get("events"):
        errors.append("description : au moins une opération (operations) ou un événement (events)")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    base = args.spec.parent
    known = requirements(spec, base, errors, warnings)
    comps = components(spec, base, errors, warnings)
    schemas = resource_schemas(spec, errors)
    ids = [op["id"] for op in spec.get("operations", [])]
    errors += [f"operations : « {i} » en double" for i in sorted({i for i in ids if ids.count(i) > 1})]
    items = [("operations", op["id"], op) for op in spec.get("operations", [])] + \
            [("events", e["name"], e) for e in spec.get("events", [])]
    covered: dict = {}
    used = set()
    for group, name, item in items:
        for ref in item.get("refs", []):
            if known is not None and ref not in known:
                errors.append(f"{group} ({name})/refs : exigence « {ref} » absente de {spec['requirements']}"
                              + close(ref, known))
            covered.setdefault(ref, []).append(name)
        if comps is not None and item.get("component") and item["component"] not in comps:
            errors.append(f"{group} ({name})/component : « {item['component']} » absent de l'option "
                          f"{spec['source']['option']}" + close(item["component"], comps))
        for key in ("request", "response", "payload"):
            if item.get(key):
                used.add(item[key].removesuffix("[]"))
    for res in spec.get("resources", []):
        used |= {kind.removesuffix("[]") for kind in res["fields"].values()}
    warnings += [f"resources : « {r['name']} » utilisée par aucune opération ni aucun événement"
                 for r in spec.get("resources", []) if r["name"] not in used]
    uncovered = sorted(rid for rid, r in (known or {}).items()
                       if rid.startswith("EF") and r.get("priority") == "indispensable" and rid not in covered
                       and r.get("status") != "retiree")
    if uncovered:
        warnings.append(f"exigence(s) fonctionnelle(s) indispensable(s) portée(s) par aucune interface : "
                        f"{', '.join(uncovered)} (hors API, ou opération à ajouter)")
    documents = {}
    if spec.get("operations"):
        documents["openapi"] = openapi(spec, schemas, errors, warnings)
    if spec.get("events"):
        documents["asyncapi"] = asyncapi(spec, schemas, errors)
    report.update(operations=len(spec.get("operations", [])), events=len(spec.get("events", [])),
                  resources=len(schemas), covered=sorted(covered), uncovered=uncovered)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    out_dir = args.out_dir or base
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json").removesuffix(".api")
    outputs = []
    for kind, doc in documents.items():
        path = out_dir / f"{stem}.{kind}.yaml"
        ai_mark.write_text(path, "\n".join(to_yaml(doc)) + "\n")
        # Relecture : le YAML écrit redonne le document, et chaque $ref se résout.
        reread = from_yaml(path.read_text(encoding="utf-8"))
        if reread != doc:
            errors.append(f"{path.name} : relecture différente du document écrit")
        errors += [f"{path.name} : $ref « {ref} » sans cible" for ref in refs_of(reread or {}, []) if not resolve(reread, ref)]
        outputs.append(path)
    summary = out_dir / f"{stem}.api.md"
    ai_mark.write_text(summary, markdown(spec, covered, uncovered, outputs))
    report["outputs"] = [str(p) for p in [*outputs, summary]]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
