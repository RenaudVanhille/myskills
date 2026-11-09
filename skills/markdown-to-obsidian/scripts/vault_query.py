# /// script
# requires-python = ">=3.10"
# ///
"""Interroge les notes typées d'un vault Obsidian et rend un JSON court.

Lecture seule. Pour retrouver une information de la mémoire partagée sans
ouvrir les notes une à une : filtre par type (`--type risque`), par valeur de
propriété (`--where statut=ouvert --where gravite=haute`), par mot du titre ou
du texte (`--text paiement`), ou par voisinage d'une note (`--related "Option
A" --depth 1`, relations typées dans les deux sens, `--relation evalue` pour
n'en suivre qu'une). Une note se désigne par son chemin, son nom, son titre,
un alias ou son `id`. Chaque note rendue donne son chemin, son type, son titre,
ses propriétés (sans tags ni alias) et ses relations (chemins visés) ;
`--fields` limite les propriétés, `--limit` le nombre de notes. Options
vérifiées contre l'ontologie (type, propriété, relation inconnus : valeurs
proches proposées).

    uv run scripts/vault_query.py VAULT [--folder DOSSIER] [--type TYPE] [--where PROP=VALEUR ...]
        [--text MOTS] [--related NOTE [--depth 1] [--relation NOM]] [--fields a,b] [--limit 50]
"""

import argparse
import difflib
import json
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_ontology  # noqa: E402

SKIP_DIRS = {".obsidian", ".trash", ".git", ".myskills-tmp", "node_modules"}
HIDDEN = {"type", "genere", "ontologie", "tags", "aliases", "cssclasses"}


def norm(value) -> str:
    text = unicodedata.normalize("NFKD", str(value))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def close(value: str, choices, what: str) -> str:
    near = difflib.get_close_matches(value, sorted(choices), n=3, cutoff=0.6)
    unknown = "inconnu" if what == "type" else "inconnue"
    hint = f" : {' ou '.join(near)} ?" if near else " (voir vault_check.py --ontology)"
    return f"{what} {unknown} « {value} »{hint}"


def templates_dir(vault: Path) -> str | None:
    """Dossier des modèles de notes (plugin cœur Modèles), ignoré : ses notes ne sont pas de la mémoire."""
    try:
        folder = json.loads((vault / ".obsidian" / "templates.json").read_text(encoding="utf-8")).get("folder")
    except (OSError, ValueError, AttributeError):
        return None
    return str(folder).strip("/") or None if folder else None


def read_vault(vault: Path, folder: str | None) -> dict[str, dict]:
    """Notes typées : chemin sans .md -> {meta, title, body}."""
    root = vault / folder if folder else vault
    templates = templates_dir(vault)
    notes = {}
    for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
        rel = path.relative_to(vault)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]):
            continue
        if templates and (rel.as_posix() + "/").startswith(templates + "/"):
            continue
        data, body, _ = vault_ontology.parse(path.read_text(encoding="utf-8", errors="replace"))
        if data and data.get("type"):
            notes[rel.with_suffix("").as_posix()] = {"meta": data, "title": vault_ontology.heading(body) or path.stem,
                                                      "body": body}
    return notes


def resolver(notes: dict[str, dict]):
    """Note désignée par chemin, nom, titre, alias ou id ; None si inconnue ou ambiguë."""
    keys: dict[str, set[str]] = {}
    for rel, note in notes.items():
        names = [rel, rel.rsplit("/", 1)[-1], note["title"], note["meta"].get("id", "")]
        names += note["meta"].get("aliases") or []
        for name in names:
            if name:
                keys.setdefault(norm(name), set()).add(rel)

    def resolve(target: str) -> str | None:
        found = keys.get(norm(str(target).removesuffix(".md")), set())
        return next(iter(found)) if len(found) == 1 else None
    return resolve


def relations_of(onto: dict, meta: dict, resolve) -> dict[str, list[str]]:
    out = {}
    for name in onto["relations"]:
        found = [resolve(t) or t for t in vault_ontology.targets(meta.get(name))]
        if found:
            out[name] = found
    return out


def matches(meta: dict, prop: str, wanted: str) -> bool:
    value = meta.get(prop)
    values = value if isinstance(value, list) else [value]
    labels = {norm(v) for v in values if v is not None} | {norm(vault_ontology.slug(v)) for v in values if v is not None}
    return norm(wanted) in labels or norm(vault_ontology.slug(wanted)) in labels


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("vault", type=Path, help="racine du vault")
    parser.add_argument("--folder", help="dossier du vault interrogé (défaut : tout le vault)")
    parser.add_argument("--type", help="type de l'ontologie (exigence, risque, decision...)")
    parser.add_argument("--where", action="append", default=[], help="PROP=VALEUR, répétable (toutes vraies)")
    parser.add_argument("--text", help="mots cherchés dans le titre et le texte (tous présents)")
    parser.add_argument("--related", help="note dont on veut les voisines (chemin, nom, titre, alias ou id)")
    parser.add_argument("--depth", type=int, default=1, help="sauts depuis --related (défaut 1, au plus 3)")
    parser.add_argument("--relation", help="seule relation suivie depuis --related")
    parser.add_argument("--fields", help="propriétés rendues, séparées par des virgules (défaut : toutes)")
    parser.add_argument("--limit", type=int, default=50, help="notes rendues au plus (défaut 50)")
    args = parser.parse_args()

    errors: list[str] = []
    report = {"vault": str(args.vault), "count": 0, "truncated": False, "notes": [], "errors": errors,
              "warnings": []}
    onto = vault_ontology.load()
    props = set(onto["common"]) | {p for spec in onto["types"].values() for p in spec.get("properties", {})}
    if not args.vault.is_dir():
        errors.append(f"vault introuvable : {args.vault}")
    if args.type and args.type not in onto["types"]:
        errors.append(close(args.type, onto["types"], "type"))
    if args.relation and args.relation not in onto["relations"]:
        errors.append(close(args.relation, onto["relations"], "relation"))
    where = []
    for item in args.where:
        prop, sep, value = item.partition("=")
        if not sep or not prop.strip():
            errors.append(f"--where « {item} » : attendu PROP=VALEUR (statut=ouvert)")
        elif prop.strip() not in props:
            errors.append(close(prop.strip(), props, "propriété"))
        else:
            where.append((prop.strip(), value.strip()))
    fields = [f.strip() for f in (args.fields or "").split(",") if f.strip()]
    errors += [close(f, props, "propriété") for f in fields if f not in props]
    if not 1 <= args.depth <= 3:
        errors.append(f"--depth {args.depth} : entre 1 et 3")
    if args.limit < 1:
        errors.append(f"--limit {args.limit} : au moins 1")
    if args.folder and args.vault.is_dir() and not (args.vault / args.folder).is_dir():
        errors.append(f"dossier introuvable dans le vault : {args.folder}")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    notes = read_vault(args.vault, args.folder)
    resolve = resolver(notes)
    links = {rel: relations_of(onto, n["meta"], resolve) for rel, n in notes.items()}
    selected = list(notes)
    if args.related:
        start = resolve(args.related)
        if not start:
            near = difflib.get_close_matches(args.related, [n["title"] for n in notes.values()], n=3, cutoff=0.5)
            errors.append(f"note introuvable ou ambiguë « {args.related} »"
                          + (f" : {' ou '.join(near)} ?" if near else ""))
            print(json.dumps(report, ensure_ascii=False))
            return 1
        report["related"] = start
        seen, frontier = {start}, {start}
        for _ in range(args.depth):
            nxt = set()
            for rel in frontier:
                out = [t for name, ts in links[rel].items() if not args.relation or name == args.relation for t in ts]
                into = [r for r, ls in links.items() for name, ts in ls.items()
                        if (not args.relation or name == args.relation) and rel in ts]
                nxt |= {t for t in out + into if t in notes} - seen
            seen |= nxt
            frontier = nxt
        selected = [rel for rel in notes if rel in seen and rel != start]
    words = [norm(w) for w in (args.text or "").split()]
    result = []
    for rel in selected:
        note, meta = notes[rel], notes[rel]["meta"]
        if args.type and meta.get("type") != args.type:
            continue
        if not all(matches(meta, p, v) for p, v in where):
            continue
        if words and not all(w in norm(note["title"] + " " + note["body"]) for w in words):
            continue
        shown = {k: v for k, v in meta.items() if k not in HIDDEN and k not in onto["relations"]
                 and (not fields or k in fields)}
        entry = {"note": rel, "type": meta["type"], "title": note["title"], "props": shown}
        if links[rel]:
            entry["links"] = links[rel]
        result.append(entry)
    report["count"] = len(result)
    report["truncated"] = len(result) > args.limit
    report["notes"] = result[:args.limit]
    if not notes:
        report["warnings"].append("aucune note typée dans " + (args.folder or "le vault"))
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
