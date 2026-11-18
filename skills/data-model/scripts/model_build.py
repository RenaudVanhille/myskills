# /// script
# requires-python = ">=3.10"
# ///
"""Écrit le modèle de données (diagramme entité-relation Mermaid, dictionnaire, DDL SQL) d'une description JSON et le contrôle.

Le modèle décrit les entités (champs, type simple, clé, obligatoire, donnée
personnelle et sa nature) et les relations (1-1, 1-n, n-n). Le script, et
non le modèle :

- vérifie noms uniques, une clé par entité, références (`ref`) et extrémités
  de relations existantes, exigences citées présentes dans exigences.json ;
- signale entité isolée, relation n-n (table d'association générée),
  données personnelles (registre et AIPD : data-protection) et données
  sensibles (santé, au sens de l'article 9 du RGPD) ;
- écrit <nom>.mmd (erDiagram), <nom>.md (dictionnaire de données et
  diagramme) et <nom>.sql (PostgreSQL : tables, clés, clés étrangères des
  relations 1-n et 1-1, tables d'association n-n), puis relit le diagramme :
  chaque entité et chaque relation doit y figurer.

Avec `domains` (domaines.json de domain-design) et le champ `context` de
chaque entité, le modèle se tient par contexte borné, après le découpage :
contexte connu, propriétaire conforme au découpage, un schéma PostgreSQL par
contexte et aucune clé étrangère d'un contexte à l'autre. Un lien entre deux
contextes devient un identifiant de référence sans contrainte, signalé avec
la relation de la carte des contextes qui le porte, ou son absence.

    uv run scripts/model_build.py MODELE.json [--out-dir DOSSIER] | --schema
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, read_spec  # noqa: E402
from text_tools import beside, cell, from_data, near as hint  # noqa: E402

SQL = {"uuid": "uuid", "string": "varchar(255)", "text": "text", "integer": "integer", "number": "double precision",
       "decimal": "numeric(14,2)", "boolean": "boolean", "date": "date", "datetime": "timestamptz", "json": "jsonb",
       "binary": "bytea"}
CARD = {"1-1": "||--||", "1-n": "||--o{", "n-n": "}o--o{"}
SENSITIVE = {"sante"}


def snake(name: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()


def schema_name(context: str) -> str:
    return context.replace("-", "_")


def table(entity: dict) -> str:
    """Nom SQL de la table, qualifié par le schéma de son contexte borné s'il en a un."""
    name = snake(entity["name"])
    return f"{schema_name(entity['context'])}.{name}" if entity.get("context") else name


def crosses(a: dict, b: dict) -> bool:
    """Vrai si deux entités appartiennent à deux contextes bornés différents."""
    return bool(a.get("context") and b.get("context") and a["context"] != b["context"])


def target(src: dict, dst: dict) -> tuple[str, str]:
    """Contrainte vers `dst` : clé étrangère dans un même contexte, simple référence commentée entre deux."""
    if crosses(src, dst):
        return "", f"référence vers {table(dst)} (contexte {dst['context']}), sans clé étrangère"
    return f" REFERENCES {table(dst)}", ""


def columns(rows: list[tuple[str, str]]) -> str:
    """Colonnes séparées par des virgules, la virgule avant le commentaire éventuel."""
    out = []
    for i, (col, note) in enumerate(rows):
        line = col + ("," if i < len(rows) - 1 else "")
        out.append(f"{line} -- {note}" if note else line)
    return "\n".join(out)


def key_of(entity: dict) -> dict:
    return next(f for f in entity["fields"] if f.get("key"))


def mermaid(spec: dict) -> str:
    lines = ["---", f"title: {spec['title']}", "---", "erDiagram"]
    for r in spec.get("relations", []):
        lines.append(f'  {r["from"]} {CARD[r["kind"]]} {r["to"]} : "{r["label"].replace(chr(34), "")}"')
    for e in spec["entities"]:
        lines.append(f"  {e['name']} {{")
        for f in e["fields"]:
            marks = ",".join(m for m, on in (("PK", f.get("key")), ("FK", f.get("ref")), ("UK", f.get("unique"))) if on)
            note = ' "donnée personnelle"' if f.get("personal") else ""
            lines.append(f"    {f['type']} {f['name']}{(' ' + marks) if marks else ''}{note}")
        lines.append("  }")
    return "\n".join(lines) + "\n"


def ddl(spec: dict, warnings: list[str]) -> str:
    by = {e["name"]: e for e in spec["entities"]}
    extra: dict[str, list[tuple[str, str]]] = {e["name"]: [] for e in spec["entities"]}
    joins = []
    for r in spec.get("relations", []):
        src, dst = by[r["from"]], by[r["to"]]
        if r["kind"] == "n-n":
            # Table d'association dans le contexte de « from » ; vers un autre contexte, sans clé étrangère.
            a, b = key_of(src), key_of(dst)
            name = f"{snake(src['name'])}_{snake(dst['name'])}"
            name = f"{schema_name(src['context'])}.{name}" if src.get("context") else name
            far, note = target(src, dst)
            rows = [(f"  {snake(src['name'])}_{a['name']} {SQL[a['type']]} NOT NULL REFERENCES {table(src)}", ""),
                    (f"  {snake(dst['name'])}_{b['name']} {SQL[b['type']]} NOT NULL{far}", note),
                    (f"  PRIMARY KEY ({snake(src['name'])}_{a['name']}, {snake(dst['name'])}_{b['name']})", "")]
            joins.append(f"CREATE TABLE {name} (\n{columns(rows)}\n);")
            continue
        # 1-n et 1-1 : clé étrangère côté « to », sauf si un champ ref la porte déjà.
        if any(f.get("ref") == src["name"] for f in dst["fields"]):
            continue
        k = key_of(src)
        null = " NOT NULL" if r.get("required") else ""
        unique = " UNIQUE" if r["kind"] == "1-1" else ""
        far, note = target(dst, src)
        extra[dst["name"]].append((f"  {snake(src['name'])}_{k['name']} {SQL[k['type']]}{null}{unique}{far}", note))
    out = [f"-- {spec['title']} : schéma PostgreSQL généré par model_build.py (data-model)."]
    schemas = sorted({schema_name(e["context"]) for e in spec["entities"] if e.get("context")})
    if schemas:
        out.append("\n".join(f"CREATE SCHEMA IF NOT EXISTS {s};" for s in schemas))
    for e in spec["entities"]:
        rows = []
        for f in e["fields"]:
            col, note = f"  {f['name']} {SQL[f['type']]}", ""
            if f.get("key"):
                col += " PRIMARY KEY"
            elif f.get("required"):
                col += " NOT NULL"
            if f.get("unique") and not f.get("key"):
                col += " UNIQUE"
            if f.get("ref"):
                far, note = target(e, by[f["ref"]])
                col += far
            rows.append((col, note))
        out.append(f"CREATE TABLE {table(e)} (\n{columns(rows + extra[e['name']])}\n);")
        personal = [f["name"] for f in e["fields"] if f.get("personal")]
        if personal:
            out.append(f"COMMENT ON TABLE {table(e)} IS 'Données personnelles : {', '.join(personal)}';")
    return "\n\n".join(out + joins) + "\n"


def check_contexts(spec: dict, base: Path, report: dict) -> None:
    """Modèle par contexte borné : contextes et propriétaires repris du découpage, liens entre contextes signalés."""
    errors, warnings = report["errors"], report["warnings"]
    placed = [e for e in spec["entities"] if e.get("context")]
    if not spec.get("domains"):
        if placed:
            warnings.append("context des entités sans découpage (domains) : contextes non vérifiés")
        return
    path = from_data(base, spec["domains"])
    try:
        domains = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"domains : {spec['domains']} illisible ({error})")
        return
    schema = schema_of("domain-design", "domain_build.py")
    if schema is None:
        warnings.append(f"domains : {path.name} non vérifié : " + absent("domain-design", "domain_build.py"))
    else:
        invalid = check(domains, schema)
        if invalid:
            errors += [f"domains : {path.name} : {e}" for e in invalid[:10]]
            return
    contexts = {c["id"]: c for c in domains.get("contexts", [])}
    owner = {name: c["id"] for c in contexts.values() for name in c.get("entities", [])}
    for i, e in enumerate(spec["entities"]):
        where = f"entities/{i} ({e['name']})"
        if not e.get("context"):
            errors.append(f"{where}/context : contexte borné attendu avec domains ("
                          + (f"« {owner[e['name']]} » d'après le découpage" if e["name"] in owner
                             else ", ".join(contexts)) + ")")
        elif e["context"] not in contexts:
            errors.append(f"{where}/context : contexte inconnu « {e['context']} » de {path.name}"
                          + hint(e["context"], contexts))
        elif e["name"] in owner and owner[e["name"]] != e["context"]:
            errors.append(f"{where}/context : « {e['context']} », alors que le découpage la donne à "
                          f"« {owner[e['name']]} » : corriger l'un ou l'autre")
    names = {e["name"] for e in spec["entities"]}
    lost = [n for n in owner if n not in names]
    if lost:
        warnings.append(f"{len(lost)} entité(s) possédée(s) dans le découpage absente(s) du modèle : " + ", ".join(lost))
    if errors:
        return
    by = {e["name"]: e for e in spec["entities"]}
    mapped = {frozenset((r["upstream"], r["downstream"])): r for r in domains.get("relations", [])}
    links = [(r["from"], r["to"], r["label"]) for r in spec.get("relations", [])]
    links += [(f["ref"], e["name"], f["name"]) for e in spec["entities"] for f in e["fields"] if f.get("ref")]
    seen = set()
    for a, b, label in links:
        if not crosses(by[a], by[b]) or (a, b) in seen:
            continue
        seen.add((a, b))
        ca, cb = by[a]["context"], by[b]["context"]
        report["cross_context"].append(f"{a} ({ca}) > {b} ({cb})")
        rel = mapped.get(frozenset((ca, cb)))
        warnings.append(f"lien {a} > {b} « {label} » entre les contextes {ca} et {cb} : identifiant de référence "
                        "sans clé étrangère dans le SQL, " + (
                            f"lu par la relation {rel['upstream']} > {rel['downstream']} de la carte "
                            f"({rel.get('integration', 'sync')})" if rel else
                            "et aucune relation de la carte des contextes ne le porte : déclarer la relation "
                            "(domain-design) ou revoir le propriétaire de l'entité"))
    report["contexts"] = len({e["context"] for e in spec["entities"]})


def markdown(spec: dict, diagram: str) -> str:
    lines = [f"# {spec['title']}", "", "```mermaid", diagram.rstrip(), "```", "", "## Dictionnaire de données"]
    for e in spec["entities"]:
        lines += ["", f"### {e.get('label', e['name'])} (`{table(e)}`)", ""]
        if e.get("context"):
            lines += [f"Contexte borné : {e['context']}.", ""]
        if e.get("description"):
            lines += [e["description"], ""]
        lines += ["| Champ | Type | Clé | Obligatoire | Donnée personnelle | Description |", "| --- | --- | --- | --- | --- | --- |"]
        for f in e["fields"]:
            keyed = "PK" if f.get("key") else (f"FK {f['ref']}" if f.get("ref") else "")
            lines.append(f"| {f['name']} | {f['type']} | {keyed} | {'oui' if f.get('required') or f.get('key') else 'non'} "
                         f"| {f.get('personal', '')} | {cell(f.get('description', ''))} |")
    if spec.get("relations"):
        lines += ["", "## Relations", "", "| De | Vers | Cardinalité | Libellé |", "| --- | --- | --- | --- |"]
        lines += [f"| {r['from']} | {r['to']} | {r['kind']} | {cell(r['label'])} |" for r in spec["relations"]]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description MODELE.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui de la description)")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma de la description sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.spec), "outputs": [], "entities": 0, "relations": 0, "personal_fields": [],
              "sensitive_fields": [], "contexts": 0, "cross_context": [], "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.spec:
        errors.append("description MODELE.json attendue")
        return done(1)
    spec, invalid = read_spec(args.spec, __file__)
    errors += invalid
    if spec is None:
        return done(1)
    if errors:
        return done(1)
    names = [e["name"] for e in spec["entities"]]
    errors += [f"entities : « {n} » en double" for n in sorted({n for n in names if names.count(n) > 1})]
    known = set(names)
    for i, e in enumerate(spec["entities"]):
        fields = [f["name"] for f in e["fields"]]
        errors += [f"entities/{i} ({e['name']}) : champ « {n} » en double"
                   for n in sorted({n for n in fields if fields.count(n) > 1})]
        keys = [f for f in e["fields"] if f.get("key")]
        if len(keys) != 1:
            errors.append(f"entities/{i} ({e['name']}) : {len(keys)} clé(s), une seule attendue (key: true)")
        for j, f in enumerate(e["fields"]):
            if f.get("ref") and f["ref"] not in known:
                errors.append(f"entities/{i}/fields/{j}/ref : entité « {f['ref']} » absente")
            if f.get("personal"):
                report["personal_fields"].append(f"{e['name']}.{f['name']}")
            if f.get("personal") in SENSITIVE:
                report["sensitive_fields"].append(f"{e['name']}.{f['name']}")
    linked = set()
    for i, r in enumerate(spec.get("relations", [])):
        for end in ("from", "to"):
            if r[end] not in known:
                errors.append(f"relations/{i}/{end} : entité « {r[end]} » absente")
        linked |= {r["from"], r["to"]}
        if r["kind"] == "n-n":
            warnings.append(f"relations/{i} : {r['from']} n-n {r['to']} : table d'association générée dans le SQL")
    linked |= {f["ref"] for e in spec["entities"] for f in e["fields"] if f.get("ref")}
    linked |= {e["name"] for e in spec["entities"] if any(f.get("ref") for f in e["fields"])}
    if len(known) > 1:
        warnings += [f"entité « {n} » reliée à aucune autre" for n in names if n not in linked]
    if spec.get("requirements"):
        try:
            catalog = json.loads((from_data(args.spec.parent, spec["requirements"])).read_text(encoding="utf-8"))
            ids = {r["id"] for r in catalog["requirements"]}
            for i, e in enumerate(spec["entities"]):
                errors += [f"entities/{i}/refs : exigence « {ref} » absente de {spec['requirements']}"
                           for ref in e.get("refs", []) if ref not in ids]
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"requirements : {spec['requirements']} illisible ({error})")
    if errors:
        return done(1)
    check_contexts(spec, args.spec.parent, report)
    if errors:
        return done(1)
    if report["personal_fields"]:
        warnings.append(f"{len(report['personal_fields'])} donnée(s) personnelle(s) : registre des traitements et "
                        "AIPD (skill data-protection)")
    if report["sensitive_fields"]:
        warnings.append(f"donnée(s) de santé ({', '.join(report['sensitive_fields'])}) : données sensibles "
                        "(RGPD art. 9), hébergement HDS à vérifier")
    diagram = mermaid(spec)
    # Relecture : chaque entité et chaque relation figure dans le diagramme écrit.
    missing = [e["name"] for e in spec["entities"] if f"  {e['name']} {{" not in diagram]
    missing += [f"{r['from']}-{r['to']}" for r in spec.get("relations", [])
                if f"{r['from']} {CARD[r['kind']]} {r['to']}" not in diagram]
    if missing:
        errors.append(f"diagramme : absent(s) après écriture : {', '.join(missing)}")
        return done(1)
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    files = {out_dir / f"{stem}.mmd": diagram, beside(out_dir / f"{stem}.md"): markdown(spec, diagram),
             out_dir / f"{stem}.sql": ddl(spec, warnings)}
    for path, text in files.items():
        path.write_text(text, encoding="utf-8")
    warnings.append("rendu Mermaid non vérifié ici : export par diagram-export si une image est demandée")
    report.update(outputs=[str(p) for p in files], entities=len(names), relations=len(spec.get("relations", [])))
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
