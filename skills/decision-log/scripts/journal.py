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
- une étape ne démarre que si toutes les précédentes sont validées ;
- seule une étape en revue peut être validée, et seulement si ses fichiers
  n'ont pas changé depuis la soumission ;
- un retour sur une étape remet à reprendre cette étape et toutes les
  suivantes déjà commencées ;
- une validation ou un retour est toujours attribué à l'utilisateur.

    uv run scripts/journal.py init DOSSIER [--title TITRE] [--stages a,b,c]
    uv run scripts/journal.py start DOSSIER ETAPE
    uv run scripts/journal.py log DOSSIER ETAPE --kind choix|hypothese|question --text T [--why J] [--refs A,B] [--by agent|utilisateur]
    uv run scripts/journal.py submit DOSSIER ETAPE --files F [F ...]
    uv run scripts/journal.py review DOSSIER ETAPE --decision valide|retour --text "mots de l'utilisateur" [--refs A,B]
    uv run scripts/journal.py status DOSSIER
"""

import argparse
import datetime
import hashlib
import json
import sys
from pathlib import Path

STAGES = ["documents", "exigences", "architectures", "schemas"]
STATUS_LABELS = {"a-faire": "à faire", "en-cours": "en cours", "en-revue": "en revue",
                 "validee": "validée", "a-reprendre": "à reprendre"}
KIND_LABELS = {"choix": "Choix", "hypothese": "Hypothèse", "question": "Question", "soumission": "Soumission",
               "retour": "Retour", "validation": "Validation", "invalidation": "Invalidation"}
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
              refs: list[str] | None = None, files: list[str] | None = None) -> str:
    entry_id = f"D-{len(state['entries']) + 1:03d}"
    entry = {"id": entry_id, "date": now(), "stage": stage, "kind": kind, "by": by, "text": text}
    if why:
        entry["why"] = why
    if refs:
        entry["refs"] = refs
    if files:
        entry["files"] = files
    state["entries"].append(entry)
    return entry_id


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
        if status == "validee":
            continue
        if status in ("a-faire", "a-reprendre"):
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


def run(args, errors: list[str], warnings: list[str]) -> tuple[dict | None, str | None]:
    folder: Path = args.folder
    if args.command == "init":
        if (folder / STATE).exists():
            errors.append(f"{folder / STATE} existe déjà : utilisez status pour reprendre le workflow")
            return None, None
        stages = split(args.stages) or STAGES
        if len(set(stages)) != len(stages):
            errors.append("étapes en double dans --stages")
            return None, None
        folder.mkdir(parents=True, exist_ok=True)
        state = {"title": args.title or folder.resolve().name, "created": now(),
                 "stages": [{"id": s, "status": "a-faire"} for s in stages], "entries": []}
        return state, None

    try:
        state = json.loads((folder / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{folder / STATE} illisible ({error}) : lancez init d'abord")
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
    if args.command == "start":
        blocking = [s["id"] for s in state["stages"][:index] if s["status"] != "validee"]
        if blocking:
            errors.append(f"{stage['id']} ne peut pas démarrer : étape(s) non validée(s) avant elle : "
                          f"{', '.join(blocking)}")
        elif stage["status"] not in ("a-faire", "a-reprendre"):
            errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]}, pas à démarrer")
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
        missing = [f for f in args.files if not (folder / f).is_file()]
        errors += [f"fichier introuvable : {f} (chemin relatif au dossier du workflow)" for f in missing]
        if not errors:
            files = sorted(dict.fromkeys(Path(f).as_posix() for f in args.files))
            stage["files"] = {f: digest(folder / f) for f in files}
            stage["status"] = "en-revue"
            entry = add_entry(state, stage["id"], "soumission", "agent", f"{len(files)} fichier(s) soumis à la revue",
                              files=files)
    elif args.command == "review":
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
                                      refs=split(args.refs), files=list(stage["files"]))
        else:
            if stage["status"] not in ("en-revue", "validee", "en-cours"):
                errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : rien à reprendre")
            else:
                stage["status"] = "a-reprendre"
                entry = add_entry(state, stage["id"], "retour", "utilisateur", args.text, refs=split(args.refs))
                for later in state["stages"][index + 1:]:
                    if later["status"] != "a-faire":
                        later["status"] = "a-reprendre"
                        add_entry(state, later["id"], "invalidation", "agent",
                                  f"à reprendre après le retour {entry} sur {stage['id']}", refs=[entry])
    return state, entry


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    init = sub.add_parser("init", help="crée workflow.json")
    init.add_argument("folder", type=Path)
    init.add_argument("--title", help="titre du workflow (défaut : nom du dossier)")
    init.add_argument("--stages", help=f"étapes dans l'ordre (défaut : {','.join(STAGES)})")
    status = sub.add_parser("status", help="état, prochaine action, fichiers validés modifiés")
    status.add_argument("folder", type=Path)
    for name in ("start", "log", "submit", "review"):
        command = sub.add_parser(name)
        command.add_argument("folder", type=Path)
        command.add_argument("stage")
        if name == "log":
            command.add_argument("--kind", required=True, choices=["choix", "hypothese", "question"])
            command.add_argument("--text", required=True)
            command.add_argument("--why", help="justification")
            command.add_argument("--refs", help="exigences, options ou entrées concernées, séparées par des virgules")
            command.add_argument("--by", choices=["agent", "utilisateur"], default="agent")
        if name == "submit":
            command.add_argument("--files", nargs="+", required=True, help="chemins relatifs au dossier")
        if name == "review":
            command.add_argument("--decision", required=True, choices=["valide", "retour"])
            command.add_argument("--text", required=True, help="les mots de l'utilisateur")
            command.add_argument("--refs", help="exigences, options ou fichiers concernés")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    state, entry = run(args, errors, warnings)
    if state and not errors and args.command != "status":
        save(args.folder, state)
    current, action = next_action(state) if state else (None, "corriger l'erreur")
    report = {"workflow": str(args.folder / STATE), "command": args.command,
              "stages": [{"id": s["id"], "status": s["status"]} for s in state["stages"]] if state else [],
              "current": current, "next": action, "entry": entry,
              "questions": sum(e["kind"] == "question" for e in state["entries"]) if state else 0,
              "errors": errors, "warnings": warnings}
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
