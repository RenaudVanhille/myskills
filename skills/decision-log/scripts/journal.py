# /// script
# requires-python = ">=3.10"
# ///
"""Tient l'état d'un workflow à étapes et le journal de ses décisions.

Un seul fichier d'état, `workflow.json`, dans le dossier du workflow : les
étapes dans un ordre fixe, leur statut, l'empreinte (SHA-256) des fichiers
soumis à la revue, et chaque entrée du journal (choix, hypothèse, question,
soumission, retour, validation, invalidation) avec son auteur et les
exigences ou options qu'elle concerne. `journal.md` en est la version
lisible, réécrite à chaque commande.

Règles appliquées par le script, pas par le modèle :
- une étape ne démarre que si toutes les précédentes sont validées (ou,
  facultatives dans la définition, sautées à la demande de l'utilisateur) ;
- seule une étape en revue peut être validée, et seulement si ses fichiers
  n'ont pas changé depuis la soumission ;
- un retour sur une étape remet à reprendre cette étape et toutes les
  suivantes déjà commencées ;
- une étape ne démarre pas si un livrable déjà validé a changé depuis ;
- une validation ou un retour est toujours attribué à l'utilisateur ;
- à une nouvelle soumission, les exigences, options et fichiers ajoutés,
  retirés ou modifiés depuis la version relue sont listés (revue
  différentielle).

Avec `init --vault VAULT`, chaque commande écrit aussi la mémoire partagée
dans le vault Obsidian (vault_sync.py) : une note par exigence, option et
entrée du journal, reliées par des wikilinks, et une note de revue par étape
soumise, où l'utilisateur valide (propriété `revue`) ; `review --from-vault`
la lit.

Avec `init --definition`, le workflow suit une définition JSON (livrée dans
workflows/ ou fournie) : étapes, skills, livrables attendus et contrôles. Le
rapport donne alors l'étape à produire (`stage`), et `submit` prend les
livrables dans la définition et refuse s'il en manque un.

Les messages de passage et rapports finaux d'agent sont validés par le
skill `agent-handoff` (check_message.py), qui les note au journal par
`trace()` quand le dossier est celui d'un workflow.

    uv run scripts/journal.py init DOSSIER [--title TITRE] [--stages a,b,c | --definition NOM|DEF.json] [--vault VAULT [--folder F]]
    uv run scripts/journal.py start DOSSIER ETAPE
    uv run scripts/journal.py skip DOSSIER ETAPE --text "mots de l'utilisateur"
    uv run scripts/journal.py log DOSSIER ETAPE --kind choix|hypothese|question --text T [--why J] [--refs A,B] [--by agent|utilisateur]
    uv run scripts/journal.py submit DOSSIER ETAPE [--files F ...]
    uv run scripts/journal.py review DOSSIER ETAPE --decision valide|retour --text "mots de l'utilisateur" [--refs A,B]
    uv run scripts/journal.py review DOSSIER ETAPE --from-vault
    uv run scripts/journal.py status DOSSIER
    uv run scripts/journal.py --schema        (schéma de workflow.json)
"""

import argparse
import datetime
import difflib
import fnmatch
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.spec_schema import check, input_schema, print_schema, validate  # noqa: E402
from vault_sync import KIND_LABELS, STATUS_LABELS, review_note, safe_folder, safe_name, sync  # noqa: E402

WORKFLOWS = Path(__file__).resolve().parent.parent / "workflows"

STAGES = ["documents", "exigences", "architectures", "schemas"]
# Étape franchie : validée par l'utilisateur, ou facultative et sautée à sa demande.
DONE = ("validee", "sautee")
# Valeurs de la propriété `revue` d'une note de revue dans le vault.
VAULT_DECISIONS = {"validée": "valide", "validee": "valide", "valide": "valide", "ok": "valide",
                   "retour": "retour", "à reprendre": "retour", "a reprendre": "retour"}
STATE, JOURNAL = "workflow.json", "journal.md"


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def split(value: str | None) -> list[str]:
    return [item.strip() for item in (value or "").split(",") if item.strip()]


def stage_of(state: dict, name: str, errors: list[str]) -> dict | None:
    for stage in state["stages"]:
        if stage["id"] == name:
            return stage
    errors.append(f"étape inconnue « {name} » ({', '.join(s['id'] for s in state['stages'])})")
    return None


def add_entry(state: dict, stage: str, kind: str, by: str, text: str, why: str = "",
              refs: list[str] | None = None, files: list[str] | None = None, via: str | None = None) -> str:
    entry_id = f"D-{len(state['entries']) + 1:03d}"
    entry = {"id": entry_id, "date": now(), "stage": stage, "kind": kind, "by": by, "text": text}
    if why:
        entry["why"] = why
    if refs:
        entry["refs"] = refs
    if files:
        entry["files"] = files
    if via:
        entry["via"] = via
    state["entries"].append(entry)
    return entry_id


def items_of(path: Path) -> dict[str, str]:
    """Empreinte de chaque élément identifié (exigence, option...) d'un livrable JSON."""
    if path.suffix.lower() != ".json":
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    found = {}
    for value in (data.values() if isinstance(data, dict) else []):
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    canonical = json.dumps(item, ensure_ascii=False, sort_keys=True)
                    found[item["id"]] = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return found


def differences(stage: dict, files: dict[str, str], items: dict[str, dict]) -> dict | None:
    """Ce qui a changé depuis la soumission précédente de l'étape (None à la première)."""
    if not stage.get("files"):
        return None
    before, after = stage.get("items", {}), items
    old = {i: h for f in before.values() for i, h in f.items()}
    new = {i: h for f in after.values() for i, h in f.items()}
    return {"added": sorted(new.keys() - old.keys()), "removed": sorted(old.keys() - new.keys()),
            "modified": sorted(i for i in new.keys() & old.keys() if new[i] != old[i]),
            "files": sorted(f for f in files.keys() | stage["files"].keys()
                            if files.get(f) != stage["files"].get(f))}


def describe(changes: dict) -> str:
    parts = [f"{label} : {', '.join(changes[key])}" for key, label in
             (("added", "ajoutés"), ("removed", "retirés"), ("modified", "modifiés")) if changes[key]]
    return "; ".join(parts) or ("fichiers modifiés : " + ", ".join(changes["files"]) if changes["files"]
                                else "aucun changement")


def load_definition(value: str, errors: list[str]) -> dict | None:
    """Définition d'un workflow : nom d'un workflow livré (workflows/<nom>.json) ou fichier JSON."""
    path = Path(value)
    if not path.is_file():
        known = sorted(p.stem for p in WORKFLOWS.glob("*.json"))
        if value not in known:
            close = difflib.get_close_matches(value, known, n=1)
            errors.append(f"définition introuvable « {value} » : fichier JSON ou workflow livré ("
                          f"{', '.join(known)})" + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            return None
        path = WORKFLOWS / f"{value}.json"
    try:
        definition = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{path.name} illisible : {error}")
        return None
    schema = input_schema(__file__)
    invalid = check(definition, schema["$defs"]["definition"], schema)
    ids = [s.get("id") for s in definition.get("stages", []) if isinstance(s, dict)]
    invalid += [f"stages : étape « {i} » en double" for i in sorted({i for i in ids if ids.count(i) > 1})]
    errors += [f"{path.name} : {e}" for e in invalid]
    return None if invalid else {k: v for k, v in definition.items() if not k.startswith("_")}


def stage_definition(state: dict, name: str | None) -> dict | None:
    for stage in (state.get("definition") or {}).get("stages", []):
        if stage["id"] == name:
            return {k: v for k, v in stage.items() if not k.startswith("_")}
    return None


def deliverables(folder: Path, definition: dict, errors: list[str]) -> list[str]:
    """Fichiers qui correspondent aux livrables de l'étape ; une erreur par livrable attendu absent."""
    files = []
    for pattern in definition["deliverables"] + definition.get("optional", []):
        found = sorted(p.relative_to(folder).as_posix() for p in folder.glob(pattern) if p.is_file())
        if not found and pattern in definition["deliverables"]:
            errors.append(f"livrable attendu introuvable : {pattern} (étape {definition['id']})")
        files += [f for f in found if f not in files]
    return files


def uncovered(files: list[str], definition: dict) -> list[str]:
    """Livrables attendus qu'aucun fichier soumis ne couvre."""
    return [p for p in definition["deliverables"] if not any(fnmatch.fnmatch(f, p) for f in files)]


def changed_files(folder: Path, stage: dict) -> list[str]:
    """Fichiers soumis ou validés qui ont changé ou disparu depuis."""
    changed = []
    for rel, sha in stage.get("files", {}).items():
        path = folder / rel
        if not path.exists() or digest(path) != sha:
            changed.append(rel)
    return changed


def next_action(state: dict) -> tuple[str | None, str]:
    """Étape courante et prochaine action attendue, déduites de l'état seul."""
    for stage in state["stages"]:
        status, name = stage["status"], stage["id"]
        if status in DONE:
            continue
        if status in ("a-faire", "a-reprendre"):
            if (stage_definition(state, name) or {}).get("facultative"):
                return name, (f"demander à l'utilisateur s'il veut l'étape facultative {name} : la démarrer (start) "
                              "ou la sauter (skip, avec ses mots)")
            return name, f"démarrer l'étape {name} (start)"
        if status == "en-cours":
            return name, f"produire les livrables de {name}, puis les soumettre (submit)"
        return name, f"présenter {name} à l'utilisateur et attendre sa revue (review)"
    return None, "workflow terminé : toutes les étapes sont validées"


def render(state: dict) -> str:
    lines = [f"# Journal : {state['title']}", "",
             "Fichier généré par `journal.py` depuis `workflow.json`, qui fait foi.", "",
             "## Étapes", "", "| Étape | Statut | Fichiers soumis |", "| --- | --- | --- |"]
    for stage in state["stages"]:
        files = ", ".join(f"`{f}`" for f in stage.get("files", {})) or "-"
        lines.append(f"| {stage['id']} | {STATUS_LABELS[stage['status']]} | {files} |")
    lines += ["", "## Décisions et revues", "",
              "| ID | Date | Étape | Type | Par | Texte | Justification | Concerne |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for entry in state["entries"]:
        cells = [entry["id"], entry["date"][:16].replace("T", " "), entry["stage"], KIND_LABELS[entry["kind"]],
                 entry["by"], entry["text"], entry.get("why", ""), ", ".join(entry.get("refs", []))]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    questions = [e for e in state["entries"] if e["kind"] == "question"]
    if questions:
        lines += ["", "## Questions posées", ""]
        lines += [f"- **{e['id']}** ({e['stage']}) : {e['text']}" for e in questions]
    return "\n".join(lines) + "\n"


def save(folder: Path, state: dict) -> None:
    with open(folder / STATE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(folder / JOURNAL, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(state))


def read_review(note: Path) -> tuple[str | None, str]:
    """Propriété `revue` et texte sous « Votre retour » d'une note de revue du vault."""
    if not note.is_file():
        return None, ""
    text = note.read_text(encoding="utf-8", errors="replace")
    head = text.split("\n---", 1)[0] if text.startswith("---") else ""
    value = next((line.split(":", 1)[1].strip().strip('"').strip("'").lower() for line in head.splitlines()
                  if line.startswith("revue:")), "")
    feedback = text.split("## Votre retour", 1)[1].strip() if "## Votre retour" in text else ""
    return value or None, " ".join(feedback.split())


def load_state(folder: Path, errors: list[str]) -> dict | None:
    """workflow.json du dossier, validé contre son schéma ; None et les erreurs sinon."""
    try:
        state = json.loads((folder / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{folder / STATE} illisible ({error}) : lancez init d'abord")
        return None
    invalid = validate(state, __file__)
    if invalid:
        errors += [e.replace("description :", f"{STATE} :", 1) for e in invalid]
        return None
    return state


def synchronize(folder: Path, state: dict, warnings: list[str]) -> dict | None:
    """Mémoire partagée dans le vault, s'il y en a un ; avertissements en cas d'échec."""
    if not state.get("memory"):
        return None
    synced = sync(folder, Path(state["memory"]["vault"]), state["memory"]["folder"])
    warnings += [f"vault : {e}" for e in synced["errors"]]
    warnings += [f"vault : {w}" for w in synced["warnings"]]
    return {"folder": synced["folder"], "notes": synced["notes"]}


def trace(folder: Path, kind: str, message: dict) -> dict:
    """Note au journal un message de passage (handoff) ou un rapport final d'agent (report) déjà
    validé par le skill agent-handoff, à l'étape courante. Renvoie l'entrée, les erreurs et
    les avertissements."""
    errors: list[str] = []
    warnings: list[str] = []
    state = load_state(folder, errors)
    if state is None:
        return {"entry": None, "errors": errors, "warnings": warnings}
    current = next_action(state)[0] or state["stages"][-1]["id"]
    if kind == "handoff":
        text = f"vers {message['agent']} : {message['objective']}"
    else:
        text = f"{message['agent']} : {message['status']}, {len(message['files'])} fichier(s)" + (
            f", à faire : {'; '.join(message['todo'])}" if message["todo"] else "")
    entry = add_entry(state, current, "passage" if kind == "handoff" else "rapport", "agent", text,
                      files=message["files"])
    save(folder, state)
    synchronize(folder, state, warnings)
    return {"entry": entry, "errors": errors, "warnings": warnings}


def run(args, errors: list[str], warnings: list[str]) -> tuple[dict | None, str | None]:
    folder: Path = args.folder
    if args.command == "init":
        if (folder / STATE).exists():
            errors.append(f"{folder / STATE} existe déjà : utilisez status pour reprendre le workflow")
            return None, None
        definition = None
        if args.definition:
            definition = load_definition(args.definition, errors)
            if not definition:
                return None, None
            stages = [s["id"] for s in definition["stages"]]
        else:
            stages = split(args.stages) or STAGES
        if len(set(stages)) != len(stages):
            errors.append("étapes en double dans --stages")
            return None, None
        folder.mkdir(parents=True, exist_ok=True)
        state = {"title": args.title or (definition or {}).get("title") or folder.resolve().name, "created": now(),
                 "stages": [{"id": s, "status": "a-faire"} for s in stages], "entries": []}
        if definition:
            state["definition"] = definition
        if args.vault:
            if not args.vault.is_dir():
                errors.append(f"vault introuvable : {args.vault}")
                return None, None
            state["memory"] = {"vault": str(args.vault.resolve()),
                               "folder": safe_folder(args.folder_in_vault or f"Workflows/{safe_name(state['title'])}")}
        return state, None

    state = load_state(folder, errors)
    if state is None:
        return None, None
    for stage in state["stages"]:
        if stage["status"] == "validee":
            changed = changed_files(folder, stage)
            if changed:
                warnings.append(f"{stage['id']} : fichiers modifiés après validation : {', '.join(changed)} ; "
                                "faites-les revoir (review --decision retour)")
    if args.command == "status":
        return state, None

    stage = stage_of(state, args.stage, errors)
    if not stage:
        return None, None
    index = state["stages"].index(stage)
    entry = None
    if args.command in ("start", "skip"):
        blocking = [s["id"] for s in state["stages"][:index] if s["status"] not in DONE]
        stale = [f"{s['id']} ({', '.join(changed_files(folder, s))})" for s in state["stages"][:index]
                 if s["status"] == "validee" and changed_files(folder, s)]
        if blocking:
            errors.append(f"{stage['id']} ne peut pas démarrer : étape(s) non validée(s) avant elle : "
                          f"{', '.join(blocking)}")
        elif stale:
            errors.append(f"{stage['id']} ne peut pas démarrer : livrable(s) validé(s) modifié(s) depuis : "
                          f"{'; '.join(stale)} ; faites-les revoir (review --decision retour)")
        elif args.command == "skip" and not (stage_definition(state, stage["id"]) or {}).get("facultative"):
            errors.append(f"{stage['id']} n'est pas facultative dans la définition du workflow : elle ne se saute pas")
        elif args.command == "skip" and not args.text:
            errors.append("skip : --text (les mots de l'utilisateur qui renonce à l'étape)")
        elif stage["status"] not in ("a-faire", "a-reprendre") + (("sautee",) if args.command == "start" else ()):
            errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]}, pas à "
                          + ("démarrer" if args.command == "start" else "sauter"))
        elif args.command == "skip":
            stage["status"] = "sautee"
            entry = add_entry(state, stage["id"], "saut", "utilisateur", args.text)
        else:
            stage["status"] = "en-cours"
    elif args.command == "log":
        if args.kind != "question" and stage["status"] != "en-cours":
            errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : un {args.kind} se note "
                          "pendant l'étape (start d'abord)")
        else:
            entry = add_entry(state, stage["id"], args.kind, args.by, args.text, args.why or "", split(args.refs))
    elif args.command == "submit":
        if stage["status"] != "en-cours":
            errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : seule une étape en cours se soumet")
        expected = stage_definition(state, stage["id"])
        if not args.files and not expected:
            errors.append("submit : --files (pas de définition de workflow qui donne les livrables)")
            return None, None
        if args.files:
            missing = [f for f in args.files if not (folder / f).is_file()]
            errors += [f"fichier introuvable : {f} (chemin relatif au dossier du workflow)" for f in missing]
            submitted = [Path(f).as_posix() for f in args.files]
            if expected:
                errors += [f"livrable attendu non soumis : {p} (étape {stage['id']})"
                           for p in uncovered(submitted, expected)]
        else:
            submitted = deliverables(folder, expected, errors)
        if not errors:
            files = sorted(dict.fromkeys(submitted))
            hashes = {f: digest(folder / f) for f in files}
            items = {f: found for f in files if (found := items_of(folder / f))}
            changes = differences(stage, hashes, items)
            stage["files"], stage["status"] = hashes, "en-revue"
            if items:
                stage["items"] = items
            else:
                stage.pop("items", None)
            text = f"{len(files)} fichier(s) soumis à la revue"
            if changes is not None:
                text += f" ; depuis la version relue : {describe(changes)}"
                args.changes = changes
            entry = add_entry(state, stage["id"], "soumission", "agent", text, files=files,
                              refs=(changes["added"] + changes["modified"]) if changes else None)
    elif args.command == "review":
        via = None
        if not args.from_vault and not (args.decision and args.text):
            errors.append("review : --decision et --text (les mots de l'utilisateur), ou --from-vault")
            return None, None
        if args.from_vault:
            memory = state.get("memory")
            if not memory:
                errors.append("pas de vault pour ce workflow : review --decision ... --text ...")
                return None, None
            if stage["status"] != "en-revue":
                errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : pas de revue en attente")
                return None, None
            note = Path(memory["vault"]) / f"{review_note(memory['folder'], stage['id'])}.md"
            value, text = read_review(note)
            if value is None:
                errors.append(f"pas encore de revue dans {note} : propriété revue à « validée » ou « retour »")
                return None, None
            args.decision = VAULT_DECISIONS.get(value)
            if not args.decision:
                errors.append(f"{note.name} : revue « {value} » non permise (validée, retour)")
                return None, None
            args.text = text or ("validé dans Obsidian" if args.decision == "valide" else "")
            if not args.text:
                errors.append(f"{note.name} : retour sans texte sous « Votre retour »")
                return None, None
            via = "obsidian"
        if args.decision == "valide":
            if stage["status"] != "en-revue":
                errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : seule une étape en revue "
                              "se valide")
            else:
                changed = changed_files(folder, stage)
                if changed:
                    errors.append(f"fichiers modifiés depuis la soumission : {', '.join(changed)} ; "
                                  "soumettez-les à nouveau")
                else:
                    stage["status"] = "validee"
                    entry = add_entry(state, stage["id"], "validation", "utilisateur", args.text,
                                      refs=split(args.refs), files=list(stage["files"]), via=via)
        else:
            if stage["status"] not in ("en-revue", "validee", "en-cours"):
                errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : rien à reprendre")
            else:
                stage["status"] = "a-reprendre"
                entry = add_entry(state, stage["id"], "retour", "utilisateur", args.text, refs=split(args.refs),
                                  via=via)
                for later in state["stages"][index + 1:]:
                    # Une étape sautée le reste : l'utilisateur y a renoncé, le retour n'y change rien.
                    if later["status"] not in ("a-faire", "sautee"):
                        later["status"] = "a-reprendre"
                        add_entry(state, later["id"], "invalidation", "agent",
                                  f"à reprendre après le retour {entry} sur {stage['id']}", refs=[entry])
    return state, entry


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--schema"]:
        print_schema(__file__)
        return 0
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="crée workflow.json")
    init.add_argument("folder", type=Path)
    init.add_argument("--title", help="titre du workflow (défaut : nom du dossier)")
    shape = init.add_mutually_exclusive_group()
    shape.add_argument("--stages", help=f"étapes dans l'ordre (défaut : {','.join(STAGES)})")
    shape.add_argument("--definition", help="workflow livré (" + ", ".join(sorted(p.stem for p in WORKFLOWS.glob("*.json")))
                       + ") ou fichier JSON de définition")
    init.add_argument("--vault", type=Path, help="vault Obsidian où écrire la mémoire partagée")
    init.add_argument("--folder", dest="folder_in_vault", help="dossier des notes dans le vault "
                                                                "(défaut : Workflows/<titre>)")
    status = sub.add_parser("status", help="état, prochaine action, fichiers validés modifiés")
    status.add_argument("folder", type=Path)
    for name in ("start", "skip", "log", "submit", "review"):
        command = sub.add_parser(name)
        command.add_argument("folder", type=Path)
        command.add_argument("stage")
        if name == "skip":
            command.add_argument("--text", help="les mots de l'utilisateur qui renonce à l'étape")
        if name == "log":
            command.add_argument("--kind", required=True, choices=["choix", "hypothese", "question"])
            command.add_argument("--text", required=True)
            command.add_argument("--why", help="justification")
            command.add_argument("--refs", help="exigences, options ou entrées concernées, séparées par des virgules")
            command.add_argument("--by", choices=["agent", "utilisateur"], default="agent")
        if name == "submit":
            command.add_argument("--files", nargs="+", help="chemins relatifs au dossier (défaut : livrables de la "
                                                              "définition du workflow)")
        if name == "review":
            command.add_argument("--decision", choices=["valide", "retour"])
            command.add_argument("--text", help="les mots de l'utilisateur")
            command.add_argument("--refs", help="exigences, options ou fichiers concernés")
            command.add_argument("--from-vault", action="store_true",
                                 help="lire la décision dans la note de revue du vault (propriété revue)")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    state, entry = run(args, errors, warnings)
    if state and not errors and args.command != "status":
        save(args.folder, state)
    memory = synchronize(args.folder, state, warnings) if state and not errors else None
    current, action = next_action(state) if state else (None, "corriger l'erreur")
    # L'étape à produire, seulement quand l'agent en a besoin : au démarrage ou à la reprise.
    todo = state and current and args.command in ("init", "start", "status") and \
        next(s for s in state["stages"] if s["id"] == current)["status"] != "en-revue"
    report = {"workflow": str(args.folder / STATE), "command": args.command,
              "stages": [{"id": s["id"], "status": s["status"]} for s in state["stages"]] if state else [],
              "current": current, "next": action, "entry": entry, "changes": getattr(args, "changes", None),
              "stage": stage_definition(state, current) if todo else None,
              "ask": ((state.get("definition") or {}).get("ask") or None) if state and args.command == "init" else None,
              "questions": sum(e["kind"] == "question" for e in state["entries"]) if state else 0,
              "memory": memory,
              "errors": errors, "warnings": warnings}
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
