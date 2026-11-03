# /// script
# requires-python = ">=3.10"
# ///
"""Vérifie les notes typées d'un vault Obsidian contre l'ontologie et exporte leur graphe.

Lit le vault (sans le modifier). Chaque note dont le frontmatter a une
propriété `type` est vérifiée contre l'ontologie (`scripts/lib/vault-ontology.json`,
source unique de l'ontologie) : type connu, propriétés obligatoires,
valeurs permises, relations (wikilinks) permises depuis ce type et visant une
note du bon type, tags normalisés. Les notes sans `type` sont comptées, pas
vérifiées. Une note générée (propriété `genere`) est aussi relue pour sa lisibilité
(avertissements « lisibilité : » : lien libellé par un simple identifiant, accord
« (s) », montant sans séparateur des milliers). Avec `--graph`, écrit le graphe des notes au format node-link de
NetworkX (`nodes`, `links` avec `relation` ; `lien` pour un wikilink du corps),
lisible par networkx, graphify ou un autre agent sans relire le vault.
`--ontology` affiche l'ontologie résumée sur une ligne, pour écrire une note
sans lire le fichier.

    uv run scripts/vault_check.py VAULT [--folder DOSSIER] [--graph graphe.json] [--strict]
    uv run scripts/vault_check.py --ontology [TYPE]
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_ontology  # noqa: E402

SKIP_DIRS = {".obsidian", ".trash", ".git", ".myskills-tmp", "node_modules"}


def notes_of(vault: Path) -> dict[str, Path]:
    """Notes du vault : chemin relatif sans .md -> fichier."""
    found = {}
    for path in sorted(vault.rglob("*.md")):
        relative = path.relative_to(vault)
        if not any(part in SKIP_DIRS for part in relative.parts[:-1]):
            found[relative.with_suffix("").as_posix()] = path
    return found


def resolver(paths: dict[str, Path]):
    """Résolution d'un wikilink comme Obsidian : chemin complet, sinon nom de note s'il est unique."""
    by_name: dict[str, list[str]] = {}
    for rel in paths:
        by_name.setdefault(rel.rsplit("/", 1)[-1].lower(), []).append(rel)
    lowered = {rel.lower(): rel for rel in paths}

    def resolve(target: str) -> str | None:
        target = target.strip().removesuffix(".md")
        if target.lower() in lowered:
            return lowered[target.lower()]
        names = by_name.get(target.rsplit("/", 1)[-1].lower(), [])
        return names[0] if len(names) == 1 else None
    return resolve


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("vault", type=Path, nargs="?")
    parser.add_argument("--folder", help="ne vérifier que les notes de ce dossier du vault (liens résolus dans tout le vault)")
    parser.add_argument("--graph", type=Path, help="écrire le graphe des notes (node-link NetworkX) dans ce fichier JSON")
    parser.add_argument("--strict", action="store_true", help="code de sortie 1 aussi sur un avertissement")
    parser.add_argument("--ontology", nargs="?", const="", metavar="TYPE",
                        help="afficher l'ontologie résumée (ou celle d'un type) et s'arrêter")
    args = parser.parse_args()
    onto = vault_ontology.load()
    if args.ontology is not None:
        if args.ontology and args.ontology not in onto["types"]:
            print(json.dumps({"errors": [f"type « {args.ontology} » inconnu ({', '.join(onto['types'])})"],
                              "warnings": []}, ensure_ascii=False))
            return 1
        print(json.dumps({**vault_ontology.summary(onto, args.ontology or None), "errors": [], "warnings": []},
                         ensure_ascii=False, separators=(",", ":")))
        return 0
    if not args.vault or not args.vault.is_dir():
        print(json.dumps({"vault": str(args.vault or ""), "errors": [f"vault introuvable : {args.vault or '(absent)'}"],
                          "warnings": []}, ensure_ascii=False))
        return 1
    vault = args.vault.resolve()
    paths = notes_of(vault)
    resolve = resolver(paths)
    parsed = {rel: vault_ontology.parse(path.read_text(encoding="utf-8", errors="replace"))
              for rel, path in paths.items()}

    def type_of(target: str):
        rel = resolve(target)
        if rel is None:
            raise KeyError(target)
        return (parsed[rel][0] or {}).get("type")

    def title_of(target: str):
        rel = resolve(target)
        return vault_ontology.heading(parsed[rel][1]) if rel else None

    prefix = (args.folder or "").strip("/\\").replace("\\", "/")
    scope = [rel for rel in paths if not prefix or rel == prefix or rel.startswith(prefix + "/")]
    results, kinds, untyped, relations = [], Counter(), 0, 0
    for rel in scope:
        data, _, read_warnings = parsed[rel]
        if not data or "type" not in data:
            untyped += 1
            continue
        kinds[str(data["type"])] += 1
        errors, warnings = vault_ontology.check_meta(onto, data)
        found, missing = vault_ontology.check_targets(onto, data, type_of)
        errors, warnings = errors + found, warnings + missing
        relations += sum(len(vault_ontology.targets(v)) for k, v in data.items() if k in onto["relations"])
        warnings = read_warnings + warnings
        if data.get("genere"):
            warnings += vault_ontology.readability(parsed[rel][1], title_of)
        if errors or warnings:
            results.append({"note": rel, "type": str(data["type"]), "errors": errors, "warnings": warnings})

    graph = None
    if args.graph:
        nodes, links = [], []
        for rel in scope:
            data, body, _ = parsed[rel]
            data = data or {}
            heading = next((line[2:].strip() for line in body.splitlines() if line.startswith("# ")), None)
            props = {k: v for k, v in data.items() if k not in onto["relations"] and k != "type"}
            if "id" in props:
                props["ref"] = props.pop("id")
            nodes.append({"id": rel, "type": data.get("type"), "label": heading or rel.rsplit("/", 1)[-1], **props})
            typed = set()
            for name, value in data.items():
                if name in onto["relations"]:
                    for target in vault_ontology.targets(value):
                        found = resolve(target)
                        if found:
                            links.append({"source": rel, "target": found, "relation": name})
                            typed.add(found)
            for target in vault_ontology.body_links(body):
                found = resolve(target)
                if found and found != rel and found not in typed:
                    links.append({"source": rel, "target": found, "relation": "lien"})
                    typed.add(found)
        in_scope = set(scope)
        nodes += [{"id": rel, "type": (parsed[rel][0] or {}).get("type"), "label": rel.rsplit("/", 1)[-1]}
                  for rel in sorted({link["target"] for link in links} - in_scope)]
        args.graph.parent.mkdir(parents=True, exist_ok=True)
        args.graph.write_text(json.dumps({"directed": True, "multigraph": True,
                                          "graph": {"vault": vault.name, "ontologie": onto["version"]},
                                          "nodes": nodes, "links": links}, ensure_ascii=False, indent=1) + "\n",
                              encoding="utf-8")
        graph = {"file": str(args.graph), "nodes": len(nodes), "links": len(links)}

    failed = [r["note"] for r in results if r["errors"]]
    errors = [f"{len(failed)} note(s) hors ontologie, détail dans results : {', '.join(failed[:10])}"
              + (" ..." if len(failed) > 10 else "")] if failed else []
    report = {"vault": str(vault), "notes": len(scope), "typed": sum(kinds.values()), "untyped": untyped,
              "types": dict(kinds.most_common()), "relations": relations, "graph": graph, "results": results,
              "errors": errors,
              "warnings": [] if scope else ["aucune note dans le périmètre"]}
    print(json.dumps(report, ensure_ascii=False))
    warned = any(r["warnings"] for r in results)
    return 1 if errors or (args.strict and warned) else 0


if __name__ == "__main__":
    sys.exit(main())
