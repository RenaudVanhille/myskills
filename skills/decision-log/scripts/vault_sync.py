# /// script
# requires-python = ">=3.10"
# ///
"""Écrit la mémoire partagée d'un workflow dans un vault Obsidian.

Lit les fichiers qui font foi dans le dossier du workflow (`workflow.json`
et, s'ils existent, `exigences.json`, `options.json`, `decision.json`,
`adr-architecture.md`) et en tire une note par exigence, terme du glossaire,
option et entrée du journal, plus une note d'index, reliées par des wikilinks : un autre
agent, une autre session ou l'utilisateur retrouvent dans le vault l'état
du workflow, chaque décision et ce qu'elle concerne.

Les notes sont générées (`genere: decision-log` dans le frontmatter) et
réécrites à chaque synchronisation ; celles qui ne correspondent plus à
rien sont supprimées. Aucune autre note du vault n'est touchée. Le vault et
son dossier sont gardés dans `workflow.json` (`journal.py init --vault`) :
`journal.py` synchronise alors après chaque commande.

    uv run scripts/vault_sync.py DOSSIER [--vault VAULT] [--folder DOSSIER_DU_VAULT] [--data DOSSIER_DES_LIVRABLES]
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from lib.spec_schema import check, input_schema  # noqa: E402

# Schéma de chaque fichier lu, pris dans le contrat du skill qui l'écrit (installé à côté).
SKILLS = HERE.parent.parent
SCHEMAS = {"workflow.json": HERE / "journal.py",
           "exigences.json": SKILLS / "requirements-catalog" / "scripts" / "req_build.py",
           "options.json": SKILLS / "architecture-options" / "scripts" / "options_build.py"}

MARK = "genere: decision-log"
KIND_LABELS = {"choix": "Choix", "hypothese": "Hypothèse", "question": "Question", "soumission": "Soumission",
               "retour": "Retour", "validation": "Validation", "invalidation": "Invalidation",
               "passage": "Passage de main", "rapport": "Rapport d'agent"}
REVIEW_HELP = ("Pour valider, mettez la propriété **revue** à `validée` ; pour demander une reprise, mettez "
               "`retour` et écrivez votre retour sous « Votre retour ». L'agent lit cette note "
               "(`journal.py review --from-vault`) : seules la propriété revue et cette section sont gardées.")
STATUS_LABELS = {"a-faire": "à faire", "en-cours": "en cours", "en-revue": "en revue",
                 "validee": "validée", "a-reprendre": "à reprendre"}


# Caractères interdits dans un nom de fichier sous Windows, ou qui cassent un wikilink Obsidian.
FORBIDDEN = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(text: str) -> str:
    """Nom de note ou de dossier valable sous Windows, macOS et Linux et dans un wikilink."""
    name = re.sub(r"\s+", " ", FORBIDDEN.sub("-", text)).strip().rstrip(". ")
    if name.split(".")[0].upper() in RESERVED:
        name = f"{name}-"
    return name or "Workflow"


def safe_folder(path: str) -> str:
    """Dossier du vault : chaque niveau (séparé par /) rendu sûr."""
    return "/".join(safe_name(part) for part in re.split(r"[\\/]+", path) if part.strip())


def review_note(target: str, stage: str) -> str:
    """Chemin (sans .md) de la note de revue d'une étape, relatif au vault."""
    return f"{safe_folder(target)}/Revues/Revue {safe_name(stage)}"


def user_part(path: Path, submission: str) -> tuple[str, str]:
    """Propriété revue et section « Votre retour » déjà remplies par l'utilisateur pour cette soumission."""
    if not path.is_file():
        return "", ""
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text.split("\n---", 1)[0]
    if f"soumission: {json.dumps(submission)}" not in head:
        return "", ""
    value = next((line.split(":", 1)[1].strip() for line in head.splitlines() if line.startswith("revue:")), "")
    feedback = text.split("## Votre retour", 1)[1].strip("\n") if "## Votre retour" in text else ""
    return value.strip('"'), feedback


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def mentions(text: str, words: list[str]) -> bool:
    """Même règle que req_build.py : sans casse ni accents, pluriel en s ou x admis."""
    text = normalize(text)
    return any(re.search(rf"(?<!\w){re.escape(normalize(w))}[sx]?(?!\w)", text) for w in words if normalize(w))


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None


def yaml_value(value) -> str:
    if isinstance(value, list):
        return "[" + ", ".join(yaml_value(v) for v in value) + "]"
    return json.dumps(value, ensure_ascii=False) if isinstance(value, str) else str(value).lower()


def note(meta: dict, body: list[str]) -> str:
    head = ["---", MARK] + [f"{k}: {yaml_value(v)}" for k, v in meta.items() if v not in (None, "", [])] + ["---", ""]
    return "\n".join(head + body).rstrip() + "\n"


def schema_for(name: str) -> dict | None:
    script = SCHEMAS[name]
    return input_schema(script) if (script.parent.parent / "contract.json").exists() else None


def checked(path: Path, schema: dict | None, errors: list[str], warnings: list[str]):
    """Contenu du fichier s'il est conforme à son schéma ; sinon None et les erreurs."""
    value = load(path)
    if value is None:
        if path.exists():
            errors.append(f"{path.name} : JSON illisible")
        return None
    if schema is None:
        warnings.append(f"{path.name} non vérifié : skill qui l'écrit absent")
        return value
    invalid = check(value, schema)
    errors += [f"{path.name} : {e}" for e in invalid[:10]]
    return None if invalid else value


def sync(folder: Path, vault: Path, target: str, data: Path | None = None) -> dict:
    """Écrit les notes ; renvoie le rapport (notes écrites, supprimées, liens cassés)."""
    errors: list[str] = []
    warnings: list[str] = []
    state = checked(folder / "workflow.json", schema_for("workflow.json"), errors, warnings)
    if not state:
        return {"vault": str(vault), "folder": target, "notes": 0, "removed": 0,
                "errors": errors or [f"{folder / 'workflow.json'} illisible : lancez journal.py init"],
                "warnings": warnings}
    if not vault.is_dir():
        return {"vault": str(vault), "folder": target, "notes": 0, "removed": 0,
                "errors": [f"vault introuvable : {vault}"], "warnings": warnings}
    data = data or folder
    catalog = checked(data / "exigences.json", schema_for("exigences.json"), errors, warnings) or {}
    options_schema = schema_for("options.json")
    options = checked(data / "options.json", options_schema, errors, warnings) or {}
    decision_schema = options_schema["properties"]["decision"] if options_schema else None
    decision = checked(data / "decision.json", decision_schema, errors, warnings) or options.get("decision")
    base = safe_folder(target)
    names: dict[str, str] = {}  # identifiant -> chemin de la note (sans .md), pour les wikilinks

    def link(ref: str) -> str:
        return f"[[{names[ref]}|{ref}]]" if ref in names else ref

    def alias(text: str) -> str:
        return text.replace("|", "-").replace("]", ")").replace("[", "(")

    for req in catalog.get("requirements", []):
        names[req["id"]] = f"{base}/Exigences/{req['id']}"
    for opt in options.get("options", []):
        names[opt["id"]] = f"{base}/Options/Option {opt['id']}"
    glossary = catalog.get("glossary", [])
    for entry in glossary:
        names["terme:" + entry["term"]] = f"{base}/Glossaire/{safe_name(entry['term'])}"
    kept = [r for r in catalog.get("requirements", []) if r.get("status", "retenue") == "retenue"]
    uses = {g["term"]: [r["id"] for r in kept if mentions(f"{r['title']} {r['text']}", [g["term"], *g.get("aliases", [])])]
            for g in glossary}
    for entry in state["entries"]:
        names[entry["id"]] = f"{base}/Décisions/{entry['id']}"
    index = f"{base}/{safe_name(state['title'])}"
    adr = data / "adr-architecture.md"
    if adr.exists():
        names["ADR"] = f"{base}/ADR architecture"

    by_ref: dict[str, list[dict]] = {}
    for entry in state["entries"]:
        for ref in entry.get("refs", []):
            by_ref.setdefault(ref, []).append(entry)
    gaps = {(g, o["id"]): v for o in options.get("options", []) for g, v in o.get("gaps", {}).items()}
    notes: dict[str, str] = {}
    up = f"Workflow : [[{index}|{alias(state['title'])}]]"

    for req in catalog.get("requirements", []):
        rid = req["id"]
        sources = [s["doc"] + (f" : « {s['quote']} »" if s.get("quote") else "") for s in req.get("sources", [])]
        body = [f"# {rid} {req['title']}", "", req["text"], "", up, ""]
        if req.get("metric"):
            body += [f"**Mesure** : {req['metric']}", ""]
        terms = [g["term"] for g in glossary if rid in uses[g["term"]]]
        if terms:
            body += ["**Termes** : " + ", ".join(f"[[{names['terme:' + term]}|{alias(term)}]]" for term in terms), ""]
        body += ["## Sources", ""] + [f"- {s}" for s in sources] + ([f"- déduite : {req['derived']}"]
                                                                   if req.get("derived") else [])
        if req.get("questions"):
            body += ["", "## Questions", ""] + [f"- {q}" for q in req["questions"]]
        covered = [f"- Option {link(o['id'])} : {'partielle' if gaps[(rid, o['id'])]['level'] == 'partiel' else 'non couverte'}"
                   f", {gaps[(rid, o['id'])]['note']}" for o in options.get("options", []) if (rid, o["id"]) in gaps]
        if covered:
            body += ["", "## Écarts des options", ""] + covered
        if by_ref.get(rid):
            body += ["", "## Décisions", ""] + [f"- {link(e['id'])} {KIND_LABELS[e['kind']]} : {e['text']}"
                                               for e in by_ref[rid]]
        notes[names[rid]] = note({"id": rid, "type": "exigence",
                                  "nature": req.get("nature") or ("fonctionnelle" if rid.startswith("EF-")
                                                                   else "non-fonctionnelle"),
                                  "priorite": req["priority"], "categorie": req.get("category"),
                                  "domaine": req.get("domain"), "statut": req.get("status", "retenue"),
                                  "tags": ["exigence"]}, body)

    for opt in options.get("options", []):
        chosen = bool(decision and decision.get("option") == opt["id"])
        body = [f"# Option {opt['id']} : {opt['name']}", "", opt["summary"], "", up, "",
                "## Composants", ""] + [f"- {c['label']}" + (f" ({c['tech']})" if c.get("tech") else "")
                                        for c in opt["components"]]
        if opt.get("gaps"):
            body += ["", "## Écarts", ""] + [f"- {link(g)} {v['level']} : {v['note']}" for g, v in opt["gaps"].items()]
        for key, label in (("pros", "Avantages"), ("cons", "Inconvénients"), ("risks", "Risques")):
            if opt.get(key):
                body += ["", f"## {label}", ""] + [f"- {item}" for item in opt[key]]
        if by_ref.get(opt["id"]):
            body += ["", "## Décisions", ""] + [f"- {link(e['id'])} {KIND_LABELS[e['kind']]} : {e['text']}"
                                               for e in by_ref[opt["id"]]]
        if chosen and "ADR" in names:
            body += ["", f"Retenue : [[{names['ADR']}|ADR]]"]
        notes[names[opt["id"]]] = note({"id": f"option-{opt['id']}", "type": "option-architecture",
                                        "retenue": chosen, "tags": ["architecture"]}, body)

    for entry in glossary:
        sources = [s["doc"] + (f" : « {s['quote']} »" if s.get("quote") else "") for s in entry.get("sources", [])]
        body = [f"# {entry['term']}", "", entry["definition"], "", up]
        if sources:
            body += ["", "## Sources", ""] + [f"- {s}" for s in sources]
        if uses[entry["term"]]:
            body += ["", "## Exigences", ""] + [f"- {link(r)}" for r in uses[entry["term"]]]
        notes[names["terme:" + entry["term"]]] = note({"type": "terme", "aliases": entry.get("aliases", []),
                                                         "tags": ["glossaire"]}, body)

    for entry in state["entries"]:
        refs = [link(r) for r in entry.get("refs", [])]
        body = [f"# {entry['id']} {KIND_LABELS[entry['kind']]}", "", entry["text"], "", up, ""]
        if entry.get("why"):
            body += [f"**Justification** : {entry['why']}", ""]
        if refs:
            body += ["**Concerne** : " + ", ".join(refs), ""]
        if entry.get("files"):
            body += ["**Fichiers** : " + ", ".join(f"`{f}`" for f in entry["files"])]
        if entry.get("via") == "obsidian":
            body += ["", "Décision prise par l'utilisateur dans sa note de revue Obsidian."]
        notes[names[entry["id"]]] = note({"id": entry["id"], "type": "decision", "nature": entry["kind"],
                                          "etape": entry["stage"], "par": entry["by"], "date": entry["date"],
                                          "tags": ["decision"]}, body)

    if "ADR" in names:
        text = adr.read_text(encoding="utf-8")
        ids = sorted((r["id"] for r in catalog.get("requirements", [])), key=len, reverse=True)
        for ref in ids:
            text = re.sub(rf"(?<![\[|/\w-]){re.escape(ref)}(?![\w-])", lambda _, r=ref: link(r), text)
        notes[names["ADR"]] = note({"type": "adr", "statut": "acceptée", "tags": ["adr", "architecture"]},
                                   [text, "", up])

    reviews = []
    for stage in state["stages"]:
        if stage["status"] != "en-revue":
            continue
        submission = next((e for e in reversed(state["entries"])
                           if e["stage"] == stage["id"] and e["kind"] == "soumission"), None)
        if not submission:
            continue
        rel = review_note(target, stage["id"])
        value, feedback = user_part(vault / f"{rel}.md", submission["id"])
        body = [f"# Revue de l'étape {stage['id']}", "", up, "", f"Soumission {link(submission['id'])} : "
                f"{submission['text']}.", "", "**Fichiers** : " + ", ".join(f"`{f}`" for f in stage.get("files", {})),
                "", REVIEW_HELP, "", "## Votre retour", "", feedback]
        notes[rel] = note({"type": "revue", "etape": stage["id"], "soumission": submission["id"],
                           "tags": ["revue"]}, body).replace("\n---\n", f"\nrevue: {json.dumps(value)}\n---\n", 1)
        reviews.append(rel)

    body = [f"# {state['title']}", "", "Mémoire partagée du workflow, générée depuis `workflow.json` : "
            "ne modifiez pas ces notes, elles sont réécrites à chaque étape.", "",
            "## Étapes", "", "| Étape | Statut |", "| --- | --- |"]
    body += [f"| {s['id']} | {STATUS_LABELS[s['status']]} |" for s in state["stages"]]
    groups = (("Exigences", [r["id"] for r in catalog.get("requirements", [])]),
              ("Options", [o["id"] for o in options.get("options", [])]))
    for title, refs in groups:
        if refs:
            body += ["", f"## {title}", ""] + [f"- {link(r)}" for r in refs]
    if glossary:
        body += ["", "## Glossaire", ""] + [f"- [[{names['terme:' + g['term']]}|{alias(g['term'])}]]"
                                           for g in sorted(glossary, key=lambda g: normalize(g["term"]))]
    if reviews:
        body += ["", "## Revues en attente", ""] + [f"- [[{rel}|{rel.rsplit('/', 1)[-1]}]]" for rel in reviews]
    if "ADR" in names:
        body += ["", "## Décision d'architecture", "", f"- [[{names['ADR']}|ADR]]"]
    if state["entries"]:
        body += ["", "## Journal", ""] + [f"- {link(e['id'])} {e['stage']}, {KIND_LABELS[e['kind']].lower()} "
                                         f"({e['by']}) : {e['text']}" for e in state["entries"]]
    notes[index] = note({"type": "workflow", "tags": ["workflow"]}, body)

    # Écriture, puis suppression des notes générées qui ne correspondent plus à rien.
    # Une note inchangée n'est pas réécrite : pas de bruit pour Obsidian Sync ou git.
    for rel, text in notes.items():
        path = vault / f"{rel}.md"
        if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    removed = 0
    for path in (vault / base).rglob("*.md"):
        rel = path.relative_to(vault).with_suffix("").as_posix()
        if rel not in notes and path.read_text(encoding="utf-8", errors="replace").startswith(f"---\n{MARK}\n"):
            path.unlink()
            removed += 1
    # Vérification : chaque wikilink écrit pointe vers une note qui existe.
    broken = sorted({target for text in notes.values() for target in re.findall(r"\[\[([^|\]]+)", text)
                     if not (vault / f"{target}.md").exists()})
    errors += [f"lien cassé : [[{target}]]" for target in broken]
    return {"vault": str(vault), "folder": base, "notes": len(notes), "removed": removed,
            "errors": errors, "warnings": warnings}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="dossier du workflow (workflow.json)")
    parser.add_argument("--vault", type=Path, help="vault Obsidian (défaut : celui de workflow.json)")
    parser.add_argument("--folder", dest="target", help="dossier des notes dans le vault (défaut : celui de "
                                                         "workflow.json, sinon Workflows/<titre>)")
    parser.add_argument("--data", type=Path, help="dossier des livrables (exigences.json, options.json, "
                                                   "decision.json, adr-architecture.md), défaut : DOSSIER")
    args = parser.parse_args()
    state = load(args.folder / "workflow.json") or {}
    memory = state.get("memory") or {}
    vault = args.vault or (Path(memory["vault"]) if memory.get("vault") else None)
    if not vault:
        print(json.dumps({"vault": "", "folder": "", "notes": 0, "removed": 0,
                          "errors": ["vault inconnu : --vault, ou journal.py init --vault"], "warnings": []},
                         ensure_ascii=False))
        return 1
    target = args.target or memory.get("folder") or f"Workflows/{safe_name(state.get('title', args.folder.resolve().name))}"
    report = sync(args.folder, vault, target, args.data)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
