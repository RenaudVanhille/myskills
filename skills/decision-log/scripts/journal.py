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
- une étape ne démarre que si toutes celles dont elle dépend sont validées
  (ou, facultatives dans la définition, sautées à la demande de
  l'utilisateur) : par défaut l'étape précédente, sinon celles de son champ
  `after` dans la définition ; des étapes prêtes en même temps (`ready`)
  peuvent se faire en parallèle ;
- seule une étape en revue peut être validée, et seulement si ses fichiers
  n'ont pas changé depuis la soumission ;
- un retour sur une étape remet à reprendre cette étape et toutes celles qui
  en dépendent, déjà commencées ;
- les commandes d'un même dossier passent l'une après l'autre (verrou
  workflow.lock), pour que des étapes menées en parallèle ne perdent rien ;
- une étape ne démarre pas si un livrable déjà validé a changé depuis ;
- une validation ou un retour est toujours attribué à l'utilisateur ;
- chaque version validée est gardée dans `.historique/ETAPE/DATE/` (dossier
  masqué dans Obsidian) : une étape reprise se refait sur place, sans copie
  de sauvegarde à côté des livrables ;
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

Avec un champ `run` dans une étape de la définition, `check DOSSIER ETAPE`
lance en un seul appel tous les contrôles mécaniques de l'étape (scripts des
skills, une fois par fichier pour `foreach`, avec le vault du workflow pour
`vault`) depuis le dossier du workflow, et rend leurs erreurs : l'agent écrit
toutes ses descriptions, puis contrôle et exporte tout d'un coup. Avec
`--submit`, une étape dont tous les contrôles passent est soumise dans le même
appel (livrables de la définition) : un tour de moins par étape.
`start DOSSIER ETAPE --submit` fait de même dès le démarrage, pour une étape
que ses scripts produisent entièrement à partir des étapes validées
(support de soutenance) : démarrée, contrôlée et soumise en un appel.

`upgrade DOSSIER` remet un workflow ouvert avec une version antérieure au
niveau des scripts actuels, sans rien perdre : la définition gardée dans
`workflow.json` à `init` est remplacée par celle livrée aujourd'hui (étapes
nouvelles « à faire » à leur place, étapes retirées gardées si elles ont
servi, statuts, fichiers et entrées intacts ; `--keep-definition` pour ne
pas y toucher), le vault de la mission est retrouvé si le dossier a été
déplacé, `journal.md` est réécrit, les livrables Markdown reçoivent leurs
liens et la mémoire du vault est refaite. À blanc par défaut : le rapport
(`upgrade`) dit ce qui changerait, `--apply` l'écrit. Rejouable : une
deuxième passe ne change plus rien.

Les messages de passage et rapports finaux d'agent sont validés par le
skill `agent-handoff` (check_message.py), qui les note au journal par
`trace()` quand le dossier est celui d'un workflow.

    uv run scripts/journal.py init DOSSIER [--title TITRE] [--stages a,b,c | --definition NOM|DEF.json] [--vault VAULT [--folder F]]
    uv run scripts/journal.py start DOSSIER ETAPE [--submit]
    uv run scripts/journal.py skip DOSSIER ETAPE --text "mots de l'utilisateur"
    uv run scripts/journal.py log DOSSIER ETAPE --kind choix|hypothese|question|reponse --text T [--why J] [--refs A,B] [--by agent|utilisateur]
    uv run scripts/journal.py submit DOSSIER ETAPE [--files F ...]
    uv run scripts/journal.py review DOSSIER ETAPE --decision valide|retour --text "mots de l'utilisateur" [--refs A,B]
    uv run scripts/journal.py review DOSSIER ETAPE --from-vault
    uv run scripts/journal.py check DOSSIER ETAPE [--submit]
    uv run scripts/journal.py status DOSSIER
    uv run scripts/journal.py upgrade DOSSIER [--apply] [--definition NOM|DEF.json | --keep-definition]
    uv run scripts/journal.py --schema        (schéma de workflow.json)
"""

import argparse
import contextlib
import datetime
import difflib
import fnmatch
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lib.skill_paths import SKILLS, absent, find_script, require_module  # noqa: E402
from lib.spec_schema import check, input_schema, print_schema, validate  # noqa: E402
from lib import source_docs  # noqa: E402
from lib.text_tools import unlink_notes  # noqa: E402
from lib.workflow_chart import progress_chart  # noqa: E402
from lib.workflow_upgrade import changed, merge_definition  # noqa: E402
from vault_sync import DEFAULT_MEMORY, KIND_LABELS, STATUS_LABELS, answers, open_questions, review_note, safe_folder, safe_name, sync, vault_ontology  # noqa: E402,E501

workspace = require_module("mission-workspace", "lib/workspace.py")

WORKFLOWS = Path(__file__).resolve().parent.parent / "workflows"

STAGES = ["documents", "exigences", "architectures", "schemas"]
# Étape franchie : validée par l'utilisateur, ou facultative et sautée à sa demande.
DONE = ("validee", "sautee")
# Valeurs de la propriété `revue` d'une note de revue dans le vault.
VAULT_DECISIONS = {"validée": "valide", "validee": "valide", "valide": "valide", "ok": "valide",
                   "retour": "retour", "à reprendre": "retour", "a reprendre": "retour"}
STATE, JOURNAL, LOCK = "workflow.json", "journal.md", "workflow.lock"
# Erreurs d'un contrôle reprises dans le rapport de check, au plus.
MAX_CHECK_ERRORS = 5
# Attente maximale du verrou, et âge au-delà duquel un verrou est abandonné (commande interrompue).
LOCK_WAIT, LOCK_STALE = 30, 120


@contextlib.contextmanager
def locked(folder: Path):
    """Verrou du dossier du workflow : une commande à la fois, même lancée par des agents en parallèle."""
    if not folder.is_dir():
        yield
        return
    lock, deadline = folder / LOCK, time.monotonic() + LOCK_WAIT
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
                raise TimeoutError(f"{lock} : verrou tenu depuis plus de {LOCK_WAIT} s ; s'il ne reste aucune "
                                   "commande en cours, supprimez-le")
            time.sleep(0.05)
    try:
        yield
    finally:
        lock.unlink(missing_ok=True)


def now() -> str:
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def digest(path: Path) -> str:
    """Empreinte d'un fichier ; celle d'un Markdown ne dépend pas des liens posés sur ses identifiants d'exigence
    (link_deliverables) : le script qui le régénère sans ces liens ne le fait pas passer pour modifié."""
    data = path.read_bytes()
    if path.suffix.lower() == ".md":
        text = data.decode("utf-8", errors="surrogateescape")
        plain = unlink_notes(text)
        data = plain.encode("utf-8", errors="surrogateescape") if plain != text else data
    return hashlib.sha256(data).hexdigest()


def archive(folder: Path, stage: dict) -> str | None:
    """Garde la version validée des fichiers d'une étape dans .historique/ETAPE/DATE/ (une étape reprise se refait
    sur place) ; rien si la dernière version gardée est la même. Rend le dossier écrit, relatif au workflow."""
    base = folder / workspace.HISTORY / stage["id"]
    last = max((d for d in base.glob("*") if d.is_dir()), default=None, key=lambda d: d.name)
    if last and all((last / f).is_file() and digest(last / f) == sha for f, sha in stage["files"].items()):
        return None
    target = base / datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    for rel in stage["files"]:
        (target / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(folder / rel, target / rel)
    return target.relative_to(folder).as_posix()


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
    for index, stage in enumerate(s for s in definition.get("stages", []) if isinstance(s, dict)):
        for need in stage.get("after", []) if isinstance(stage.get("after"), list) else []:
            if need not in ids[:index]:
                invalid.append(f"stages/{index}/after : « {need} » n'est pas une étape placée avant "
                               f"{stage.get('id')} ({', '.join(map(str, ids[:index])) or 'aucune'})")
        for number, entry in enumerate(stage.get("run", []) if isinstance(stage.get("run"), list) else []):
            if isinstance(entry, dict) and entry.get("skill") and entry.get("script"):
                if entry["skill"] not in stage.get("skills", []):
                    invalid.append(f"stages/{index}/run/{number} : skill « {entry['skill']} » absent des skills "
                                   f"de l'étape {stage.get('id')}")
                elif find_script(entry["skill"], entry["script"]) is None:
                    known = sorted(p.name for p in (SKILLS / entry["skill"] / "scripts").glob("*.py"))
                    close = difflib.get_close_matches(entry["script"], known, n=1)
                    invalid.append(f"stages/{index}/run/{number} : " + (
                        f"script inconnu « {entry['script']} » du skill {entry['skill']} ({', '.join(known)})"
                        + (f" ; vouliez-vous « {close[0]} » ?" if close else "") if known
                        else absent(entry["skill"], entry["script"])))
    errors += [f"{path.name} : {e}" for e in invalid]
    return None if invalid else {k: v for k, v in definition.items() if not k.startswith("_")}


def stage_definition(state: dict, name: str | None) -> dict | None:
    for stage in (state.get("definition") or {}).get("stages", []):
        if stage["id"] == name:
            return {k: v for k, v in stage.items() if not k.startswith("_")}
    return None


def requires(state: dict, name: str) -> list[str]:
    """Étapes dont dépend directement une étape : son champ `after`, sinon l'étape précédente."""
    definition = stage_definition(state, name)
    if definition is not None and "after" in definition:
        return list(definition["after"])
    ids = [s["id"] for s in state["stages"]]
    index = ids.index(name)
    return ids[index - 1:index]


def ancestors(state: dict, name: str) -> list[str]:
    """Toutes les étapes dont une étape dépend, directement ou non, dans l'ordre du workflow."""
    found, todo = set(), requires(state, name)
    while todo:
        current = todo.pop()
        if current not in found:
            found.add(current)
            todo += requires(state, current)
    return [s["id"] for s in state["stages"] if s["id"] in found]


def dependents(state: dict, name: str) -> list[str]:
    """Étapes qui dépendent, directement ou non, d'une étape."""
    return [s["id"] for s in state["stages"] if name in ancestors(state, s["id"])]


def ready(state: dict) -> list[str]:
    """Étapes qui peuvent démarrer maintenant : toutes celles dont elles dépendent sont franchies."""
    status = {s["id"]: s["status"] for s in state["stages"]}
    return [s["id"] for s in state["stages"] if s["status"] in ("a-faire", "a-reprendre")
            and all(status[a] in DONE for a in ancestors(state, s["id"]))]


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


def run_checks(folder: Path, state: dict, stage: dict, errors: list[str]) -> list[dict]:
    """Lance les contrôles `run` de l'étape depuis le dossier du workflow ; une ligne par commande lancée
    ou sautée, et une erreur par commande en échec (ses premières erreurs)."""
    definition = stage_definition(state, stage["id"]) or {}
    if not definition.get("run"):
        errors.append(f"{stage['id']} : pas de champ run dans la définition ; lancez les checks un par un")
        return []
    if stage["status"] not in ("en-cours", "en-revue"):
        errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : check se lance sur une étape "
                      "démarrée (start d'abord)")
        return []
    memory = state.get("memory")
    runner = ["uv", "run", "--quiet"] if shutil.which("uv") else [sys.executable]
    results = []
    for entry in definition["run"]:
        script = find_script(entry["skill"], entry["script"])
        label = f"{entry['script']} {' '.join(entry.get('args', []))}".strip()
        if entry.get("if") and not any(folder.glob(entry["if"])):
            results.append({"command": label, "status": "saute", "why": f"aucun fichier {entry['if']}"})
            continue
        files = sorted(p.relative_to(folder).as_posix() for p in folder.glob(entry["foreach"])) \
            if entry.get("foreach") else [None]
        if not files:
            results.append({"command": label, "status": "saute", "why": f"aucun fichier {entry['foreach']}"})
            continue
        for rel in files:
            name = Path(rel).name.split(".")[0] if rel else ""
            args = [a.replace("{file}", rel or "").replace("{name}", name) for a in entry.get("args", [])]
            # Un argument à motif (pages/*.json) devient la liste triée de ses fichiers.
            args = [x for a in args for x in (sorted(q.relative_to(folder).as_posix() for q in folder.glob(a))
                                              or [a] if any(c in a for c in "*?[") else [a])]
            if entry.get("vault") and memory:
                args += ["--vault", memory["vault"], "--folder", memory["folder"]]
            command = f"{entry['script']} {' '.join(args)}".strip()
            if script is None:
                errors.append(f"{command} : {absent(entry['skill'], entry['script'])}")
                results.append({"command": command, "status": "echec", "errors": 1, "warnings": 0})
                continue
            before = {s["id"]: set(changed_files(folder, s)) for s in state["stages"]
                      if s["status"] == "validee" and s is not stage}
            done = subprocess.run(runner + [str(script)] + args, cwd=folder, capture_output=True, text=True,
                                  encoding="utf-8", errors="replace")
            # Un contrôle ne réécrit jamais le livrable d'une étape validée : il bloquerait les suivantes.
            for other in state["stages"]:
                if other["id"] in before:
                    for rel in sorted(set(changed_files(folder, other)) - before[other["id"]]):
                        errors.append(f"{command} : a modifié {rel}, livrable validé de l'étape {other['id']} ; "
                                      "écrire dans un autre fichier (--out), ou revenir sur l'étape (review --decision retour)")
            try:
                report = json.loads(done.stdout)
                found, warned = list(report.get("errors", [])), len(report.get("warnings", []))
            except ValueError:
                tail = (done.stderr or done.stdout).strip().splitlines()[-1:] or ["sans sortie"]
                found, warned = [f"rapport illisible ({tail[0][:200]})"], 0
            if done.returncode and not found:
                found = [f"code de sortie {done.returncode}"]
            errors += [f"{command} : {e}" for e in found[:MAX_CHECK_ERRORS]]
            if len(found) > MAX_CHECK_ERRORS:
                errors.append(f"{command} : et {len(found) - MAX_CHECK_ERRORS} autre(s) erreur(s)")
            results.append({"command": command, "status": "echec" if found else "ok",
                            "errors": len(found), "warnings": warned})
    return results


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


def chart(state: dict) -> list[str]:
    """Schéma Mermaid des étapes : obligatoire ou facultative, statut, dépendances."""
    stages = [stage_definition(state, s["id"]) or {"id": s["id"]} for s in state["stages"]]
    return progress_chart(stages, {s["id"]: s["status"] for s in state["stages"]}, state["title"])


def md_link(text: str, target: Path, folder: Path) -> str:
    """Lien Markdown standard vers un fichier, relatif au dossier du journal (lisible dans Obsidian ouvert à la
    racine du projet comme à l'export) ; le texte seul si le fichier n'est pas joignable par un chemin relatif."""
    try:
        relative = Path(os.path.relpath(target, folder)).as_posix()
    except ValueError:  # autre lecteur sous Windows
        return text
    return f"[{text}]({urllib.parse.quote(relative)})"


def linker(folder: Path, state: dict):
    """Fonction qui lie une référence du journal : un fichier du dossier vers lui-même, une entrée, une exigence
    ou une option vers sa note du vault quand le workflow en a un."""
    memory = state.get("memory") or {}
    base = Path(memory["vault"]) / safe_folder(memory["folder"]) if memory.get("vault") else None
    entries = {e["id"] for e in state["entries"]}

    def link(ref: str, code: bool = False) -> str:
        shown = f"`{ref}`" if code else ref.replace("|", "\\|")
        if (folder / ref).is_file():
            return md_link(shown, folder / ref, folder)
        if not base or ref != safe_name(ref):
            return shown
        notes = [base / "Décisions" / f"{ref}.md"] if ref in entries else \
            [n for n in (base / "Exigences" / f"{ref}.md", base / "Options" / f"Option {ref}.md") if n.is_file()]
        return md_link(shown, notes[0], folder) if notes else shown
    return link


def render(state: dict, folder: Path | None = None) -> str:
    link = linker(folder, state) if folder else (lambda ref, code=False: f"`{ref}`" if code else ref)
    lines = [f"# Journal : {state['title']}", "",
             "Fichier généré par `journal.py` depuis `workflow.json`, qui fait foi.", "",
             "## Étapes", "", "| Étape | Statut | Fichiers soumis |", "| --- | --- | --- |"]
    for stage in state["stages"]:
        files = ", ".join(link(f, code=True) for f in stage.get("files", {})) or "-"
        lines.append(f"| {stage['id']} | {STATUS_LABELS[stage['status']]} | {files} |")
    lines += ["", "## Avancement", ""] + chart(state)
    lines += ["", "## Décisions et revues", "",
              "| ID | Date | Étape | Type | Par | Texte | Justification | Concerne |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for entry in state["entries"]:
        cells = [entry["date"][:16].replace("T", " "), entry["stage"], KIND_LABELS[entry["kind"]],
                 entry["by"], entry["text"], entry.get("why", "")]
        cells = [link(entry["id"])] + [c.replace("|", "\\|").replace("\n", " ") for c in cells] \
            + [", ".join(link(ref) for ref in entry.get("refs", [])).replace("\n", " ")]
        lines.append("| " + " | ".join(cells) + " |")
    waiting = open_questions(state)
    if waiting:
        lines += ["", "## Questions ouvertes", ""]
        lines += [f"- **{link(e['id'])}** ({e['stage']}) : {e['text']}" for e in waiting]
    answered = answers(state)
    if answered:
        texts = {e["id"]: e for e in state["entries"]}
        lines += ["", "## Questions répondues", ""]
        lines += [f"- **{link(q)}** ({texts[q]['stage']}) : {texts[q]['text']} ; réponse {link(r)} : "
                  f"{texts[r]['text']}" for q, r in answered.items()]
    return "\n".join(lines) + "\n"


def save(folder: Path, state: dict) -> None:
    with open(folder / STATE, "w", encoding="utf-8", newline="\n") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    with open(folder / JOURNAL, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render(state, folder))


def read_review(note: Path) -> tuple[str | None, str]:
    """Propriété `revue` et texte sous « Votre retour » d'une note de revue du vault."""
    if not note.is_file():
        return None, ""
    text = note.read_text(encoding="utf-8", errors="replace")
    head = text.split("\n---", 1)[0] if text.startswith("---") else ""
    value = next((line.split(":", 1)[1].strip().strip('"').strip("'").lower() for line in head.splitlines()
                  if line.startswith("revue:")), "")
    feedback = text.split("## Votre retour", 1)[1] if "## Votre retour" in text else ""
    feedback = feedback.split(vault_ontology.USER_TITLE, 1)[0].split(vault_ontology.HUB, 1)[0].strip()
    return value or None, " ".join(feedback.split())


def pick_annotations(state: dict) -> list[dict]:
    """Callouts [!question] et [!retour] écrits par l'utilisateur sous « Mes notes » dans les notes du
    workflow : chacun, pas encore tracé, devient une entrée du journal (question ou annotation, via obsidian)
    de l'étape courante. Rend les entrées ajoutées : [{id, kind, note, text}]."""
    memory = state.get("memory")
    if not memory or not Path(memory["vault"]).is_dir():
        return []
    seen = {((e.get("refs") or [""])[0], e["text"]) for e in state["entries"] if e.get("via") == "obsidian"}
    stage = next_action(state)[0] or state["stages"][-1]["id"]
    added = []
    for found in vault_ontology.vault_annotations(Path(memory["vault"]), memory["folder"]):
        if (found["note"], found["text"]) in seen:
            continue
        seen.add((found["note"], found["text"]))
        kind = "question" if found["kind"] == "question" else "annotation"
        entry = add_entry(state, stage, kind, "utilisateur", found["text"], refs=[found["note"]], via="obsidian")
        added.append({"id": entry, "kind": kind, "note": found["note"], "text": found["text"]})
    return added


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


def link_deliverables(folder: Path, state: dict, write: bool = True) -> int:
    """Pose, dans les livrables Markdown soumis, un lien Markdown standard de chaque identifiant d'exigence vers
    sa note du vault (`write` faux : compte seulement) : les fichiers du dossier du workflow se lisent liés dans Obsidian ouvert à la racine du
    projet. Les documents sources et le texte ne changent pas ; l'empreinte des fichiers non plus (digest) et
    l'export les retire (markdown-publish). Rend le nombre de fichiers réécrits."""
    memory = state["memory"]
    definition = state.get("definition")
    names = (definition.get("memory", {}) if definition else DEFAULT_MEMORY).get("requirements")
    try:
        catalog = json.loads((folder / names).read_text(encoding="utf-8")) if names else {}
        notes = Path(memory["vault"]) / safe_folder(memory["folder"]) / "Exigences"
        ids = {r["id"]: notes / f"{r['id']}.md" for r in catalog.get("requirements", [])}
        sources = (folder / catalog.get("sources", "sources")).resolve()
    except (OSError, ValueError, KeyError, TypeError, AttributeError):
        return 0
    written = 0
    for rel in dict.fromkeys(f for stage in state["stages"] for f in stage.get("files", {})) if ids else []:
        path = folder / rel
        if path.suffix.lower() != ".md" or not path.is_file() or sources in path.resolve().parents:
            continue
        with open(path, encoding="utf-8", errors="surrogateescape", newline="") as handle:
            text = handle.read()
        linked = source_docs.linker(ids, {}, "", lambda target, _, shown, bar: md_link(shown, target, path.parent),
                                    relink=False)(text)
        if linked != text:
            if write:
                with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as handle:
                    handle.write(linked)
            written += 1
    return written


def synchronize(folder: Path, state: dict, warnings: list[str]) -> dict | None:
    """Mémoire partagée dans le vault, s'il y en a un ; avertissements en cas d'échec."""
    if not state.get("memory"):
        return None
    link_deliverables(folder, state)
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
    with locked(folder):
        return _trace(folder, kind, message, errors, warnings)


def _trace(folder: Path, kind: str, message: dict, errors: list[str], warnings: list[str]) -> dict:
    state = load_state(folder, errors)
    if state is None:
        return {"entry": None, "errors": errors, "warnings": warnings}
    # Avec des étapes en parallèle, le message va à l'étape en cours dont il cite un livrable, sinon à la
    # première étape en cours ou à l'étape courante.
    running = [s["id"] for s in state["stages"] if s["status"] == "en-cours"]
    named = [s for s in running if any(fnmatch.fnmatch(f, pattern) for f in message.get("files", [])
                                       for pattern in (lambda d: d["deliverables"] + d.get("optional", []))(
                                           stage_definition(state, s) or {"deliverables": []}))]
    current = (named or running or [next_action(state)[0] or state["stages"][-1]["id"]])[0]
    if kind == "handoff":
        text = f"vers {message['agent']} : {message['objective']}"
    else:
        text = f"{message['agent']} : {message['status']}, {len(message['files'])} fichier{'s' if len(message['files']) > 1 else ''}" + (
            f", à faire : {'; '.join(message['todo'])}" if message["todo"] else "")
    entry = add_entry(state, current, "passage" if kind == "handoff" else "rapport", "agent", text,
                      files=message["files"])
    save(folder, state)
    synchronize(folder, state, warnings)
    return {"entry": entry, "errors": errors, "warnings": warnings}


class Refused(Exception):
    """La commande s'arrête là : l'erreur est déjà dans errors, l'état n'est pas enregistré."""


def init_workflow(args, folder: Path, errors: list[str]) -> dict:
    if (folder / STATE).exists():
        errors.append(f"{folder / STATE} existe déjà : utilisez status pour reprendre le workflow")
        raise Refused
    definition = None
    if args.definition:
        definition = load_definition(args.definition, errors)
        if not definition:
            raise Refused
        stages = [s["id"] for s in definition["stages"]]
    else:
        stages = split(args.stages) or STAGES
    if len(set(stages)) != len(stages):
        errors.append("étapes en double dans --stages")
        raise Refused
    folder.mkdir(parents=True, exist_ok=True)
    state = {"title": args.title or (definition or {}).get("title") or folder.resolve().name, "created": now(),
             "stages": [{"id": s, "status": "a-faire"} for s in stages], "entries": []}
    if definition:
        state["definition"] = definition
    # Dans une mission (mission.json au-dessus du dossier), son vault par défaut, et aucun autre.
    args.vault, _, scoped = workspace.vault_target(args.vault, None, [folder], default_folder=None)
    if scoped:
        errors += scoped
        raise Refused
    if args.vault:
        if not args.vault.is_dir():
            errors.append(f"vault introuvable : {args.vault}")
            raise Refused
        state["memory"] = {"vault": str(args.vault.resolve()),
                           "folder": safe_folder(args.folder_in_vault or f"Workflows/{safe_name(state['title'])}")}
    return state


def start_or_skip(args, folder: Path, state: dict, stage: dict, errors: list[str]) -> str | None:
    """Démarre ou saute une étape dont les étapes amont sont validées et inchangées."""
    before = [s for s in state["stages"] if s["id"] in ancestors(state, stage["id"])]
    blocking = [s["id"] for s in before if s["status"] not in DONE]
    stale = [f"{s['id']} ({', '.join(changed_files(folder, s))})" for s in before
             if s["status"] == "validee" and changed_files(folder, s)]
    if blocking:
        errors.append(f"{stage['id']} ne peut pas démarrer : étape(s) dont elle dépend non validée(s) : "
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
        return add_entry(state, stage["id"], "saut", "utilisateur", args.text)
    else:
        stage["status"] = "en-cours"
    return None


def submit(args, folder: Path, state: dict, stage: dict, errors: list[str]) -> str | None:
    """Soumet les livrables de l'étape à la revue, avec leurs empreintes et l'écart à la version relue."""
    if stage["status"] not in ("en-cours", "en-revue"):
        errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : seule une étape en cours "
                      "ou en revue se soumet")
    expected = stage_definition(state, stage["id"])
    if not args.files and not expected:
        errors.append("submit : --files (pas de définition de workflow qui donne les livrables)")
        raise Refused
    if args.files:
        missing = [f for f in args.files if not (folder / f).is_file()]
        errors += [f"fichier introuvable : {f} (chemin relatif au dossier du workflow)" for f in missing]
        submitted = [Path(f).as_posix() for f in args.files]
        if expected:
            errors += [f"livrable attendu non soumis : {p} (étape {stage['id']})"
                       for p in uncovered(submitted, expected)]
    else:
        submitted = deliverables(folder, expected, errors)
    if errors:
        return None
    files = sorted(dict.fromkeys(submitted))
    hashes = {f: digest(folder / f) for f in files}
    items = {f: found for f in files if (found := items_of(folder / f))}
    changes = differences(stage, hashes, items)
    stage["files"], stage["status"] = hashes, "en-revue"
    if items:
        stage["items"] = items
    else:
        stage.pop("items", None)
    text = f"{len(files)} fichier{'s soumis' if len(files) > 1 else ' soumis'} à la revue"
    if changes is not None:
        text += f" ; depuis la version relue : {describe(changes)}"
        args.changes = changes
    return add_entry(state, stage["id"], "soumission", "agent", text, files=files,
                     refs=(changes["added"] + changes["modified"]) if changes else None)


def review_from_vault(args, state: dict, stage: dict, errors: list[str]) -> None:
    """Lit la revue écrite dans la note Obsidian de l'étape : décision et texte passent dans args."""
    memory = state.get("memory")
    if not memory:
        errors.append("pas de vault pour ce workflow : review --decision ... --text ...")
        raise Refused
    if stage["status"] != "en-revue":
        errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : pas de revue en attente")
        raise Refused
    note = Path(memory["vault"]) / f"{review_note(memory['folder'], stage['id'])}.md"
    value, text = read_review(note)
    if value is None:
        errors.append(f"pas encore de revue dans {note} : propriété revue à « validée » ou « retour »")
        raise Refused
    args.decision = VAULT_DECISIONS.get(value)
    if not args.decision:
        errors.append(f"{note.name} : revue « {value} » non permise (validée, retour)")
        raise Refused
    args.text = text or ("validé dans Obsidian" if args.decision == "valide" else "")
    if not args.text:
        errors.append(f"{note.name} : retour sans texte sous « Votre retour »")
        raise Refused


def review(args, folder: Path, state: dict, stage: dict, errors: list[str]) -> str | None:
    """Validation ou retour de l'utilisateur ; un retour remet à reprendre les étapes qui en dépendent."""
    via = None
    if not args.from_vault and not (args.decision and args.text):
        errors.append("review : --decision et --text (les mots de l'utilisateur), ou --from-vault")
        raise Refused
    if args.from_vault:
        review_from_vault(args, state, stage, errors)
        via = "obsidian"
    if args.decision == "valide":
        if stage["status"] != "en-revue":
            errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : seule une étape en revue "
                          "se valide")
            return None
        changed = changed_files(folder, stage)
        if changed:
            errors.append(f"fichiers modifiés depuis la soumission : {', '.join(changed)} ; "
                          "soumettez-les à nouveau")
            return None
        stage["status"] = "validee"
        args.archived = archive(folder, stage)
        return add_entry(state, stage["id"], "validation", "utilisateur", args.text,
                         refs=split(args.refs), files=list(stage["files"]), via=via)
    if stage["status"] not in ("en-revue", "validee", "en-cours"):
        errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : rien à reprendre")
        return None
    stage["status"] = "a-reprendre"
    entry = add_entry(state, stage["id"], "retour", "utilisateur", args.text, refs=split(args.refs), via=via)
    for later in (s for s in state["stages"] if s["id"] in dependents(state, stage["id"])):
        # Une étape sautée le reste : l'utilisateur y a renoncé, le retour n'y change rien.
        if later["status"] not in ("a-faire", "sautee"):
            later["status"] = "a-reprendre"
            add_entry(state, later["id"], "invalidation", "agent",
                      f"à reprendre après le retour {entry} sur {stage['id']}", refs=[entry])
    return entry


def upgrade(args, folder: Path, errors: list[str], warnings: list[str]) -> tuple[dict | None, dict | None]:
    """Remet un workflow ouvert avec une version antérieure au niveau des scripts d'aujourd'hui : définition
    livrée reprise sans perdre l'avancement, vault de la mission retrouvé si le dossier a bougé, puis ce qui
    reste à réécrire (journal.md, liens des livrables). N'écrit rien : main enregistre avec --apply."""
    try:
        state = json.loads((folder / STATE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{folder / STATE} illisible ({error}) : lancez init d'abord")
        return None, None
    info = {"applied": False, "definition": None, "vault": None, "journal": False, "links": 0}
    old = state.get("definition") if isinstance(state, dict) else None
    name = args.definition or (old.get("name") if isinstance(old, dict) else None)
    if name and not args.keep_definition:
        new = load_definition(name, errors)
        if not new:
            errors.append("upgrade : donnez la définition à suivre (--definition NOM|DEF.json) ou gardez celle du "
                          "workflow (--keep-definition)")
            return None, None
        keys = input_schema(__file__)["$defs"]["definition"]["properties"]["stages"]["items"]["properties"]
        try:
            state, info["definition"] = merge_definition(state, new, keys)
        except (KeyError, TypeError, AttributeError):
            pass  # état trop abîmé pour être fusionné : la validation ci-dessous dit où
    invalid = validate(state, __file__)
    if invalid:
        errors += [e.replace("description :", f"{STATE} :", 1) for e in invalid]
        return None, None
    memory = state.get("memory")
    if memory and not Path(memory["vault"]).is_dir():
        vault = workspace.vault_target(None, None, [folder], default_folder=None)[0]
        if vault and Path(vault).is_dir():
            memory["vault"] = info["vault"] = str(Path(vault).resolve())
        else:
            warnings.append(f"vault introuvable : {memory['vault']} ; mémoire partagée non resynchronisée")
    try:
        written = (folder / JOURNAL).read_text(encoding="utf-8")
    except OSError:
        written = None
    info["journal"] = render(state, folder) != written
    info["links"] = link_deliverables(folder, state, write=False)
    return state, info


def run(args, errors: list[str], warnings: list[str]) -> tuple[dict | None, str | None]:
    try:
        return _run(args, errors, warnings)
    except Refused:
        return None, None


def _run(args, errors: list[str], warnings: list[str]) -> tuple[dict | None, str | None]:
    folder: Path = args.folder
    if args.command == "init":
        return init_workflow(args, folder, errors), None

    state = load_state(folder, errors)
    if state is None:
        return None, None
    # Ce que l'utilisateur a écrit dans Obsidian depuis le dernier passage, tracé avant toute commande.
    args.annotations = (getattr(args, "annotations", None) or []) + pick_annotations(state)
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
    entry = None
    if args.command in ("start", "skip"):
        entry = start_or_skip(args, folder, state, stage, errors)
    elif args.command == "log":
        waiting = {e["id"] for e in open_questions(state)}
        if args.kind == "reponse" and not waiting & set(split(args.refs)):
            errors.append("log --kind reponse : --refs doit citer une question ouverte"
                          + (f" ({', '.join(sorted(waiting))})" if waiting else " (aucune question ouverte)"))
        elif args.kind not in ("question", "reponse") and stage["status"] != "en-cours":
            errors.append(f"{stage['id']} est {STATUS_LABELS[stage['status']]} : un {args.kind} se note "
                          "pendant l'étape (start d'abord)")
        else:
            entry = add_entry(state, stage["id"], args.kind, args.by, args.text, args.why or "", split(args.refs))
    elif args.command == "submit":
        entry = submit(args, folder, state, stage, errors)
    elif args.command == "review":
        entry = review(args, folder, state, stage, errors)
        waiting = [e["id"] for e in open_questions(state) if e["stage"] == stage["id"]]
        if entry and args.decision == "valide" and waiting:
            warnings.append(f"{stage['id']} validée avec {len(waiting)} question(s) ouverte(s) : {', '.join(waiting)} ; "
                            "notez la réponse de l'utilisateur (log --kind reponse --refs)")
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
    up = sub.add_parser("upgrade", help="remet un workflow existant au niveau des scripts actuels (à blanc sans --apply)")
    up.add_argument("folder", type=Path)
    up.add_argument("--apply", action="store_true", help="écrire les changements (défaut : à blanc, rien n'est écrit)")
    choice = up.add_mutually_exclusive_group()
    choice.add_argument("--definition", help="définition à suivre désormais (défaut : celle livrée du même nom)")
    choice.add_argument("--keep-definition", action="store_true",
                        help="garder les étapes et consignes d'origine du workflow")
    for name in ("start", "skip", "log", "submit", "review", "check"):
        command = sub.add_parser(name)
        command.add_argument("folder", type=Path)
        command.add_argument("stage")
        if name == "skip":
            command.add_argument("--text", help="les mots de l'utilisateur qui renonce à l'étape")
        if name == "log":
            command.add_argument("--kind", required=True, choices=["choix", "hypothese", "question", "reponse"])
            command.add_argument("--text", required=True)
            command.add_argument("--why", help="justification")
            command.add_argument("--refs", help="exigences, options ou entrées concernées, séparées par des virgules")
            command.add_argument("--by", choices=["agent", "utilisateur"], default="agent")
        if name in ("check", "start"):
            command.add_argument("--submit", action="store_true",
                                 help="soumettre l'étape dans le même appel si tous ses contrôles passent"
                                      + (" (start : démarrer, lancer les contrôles run, puis soumettre ; pour une "
                                         "étape dont le script produit tout)" if name == "start" else ""))
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
    checks, memory, upgraded = None, None, None
    try:
        if args.command == "upgrade":
            with locked(args.folder):
                state, upgraded = upgrade(args, args.folder, errors, warnings)
                entry = None
                if state and args.apply:
                    save(args.folder, state)
                    upgraded["links"] = link_deliverables(args.folder, state)
                    if state.get("memory") and Path(state["memory"]["vault"]).is_dir():
                        memory = synchronize(args.folder, state, warnings)
                        save(args.folder, state)  # journal.md lié aux notes que la synchronisation vient d'écrire
                    upgraded["applied"] = True
        elif args.command == "check":
            # Hors verrou : les contrôles peuvent durer, et des étapes en parallèle continuent d'écrire le journal.
            state, entry = load_state(args.folder, errors), None
            stage = stage_of(state, args.stage, errors) if state else None
            checks = run_checks(args.folder, state, stage, errors) if stage else []
            if args.submit and checks and not errors:
                args.command, args.files = "submit", None
        if args.command not in ("check", "upgrade"):
            with locked(args.folder):
                state, entry = run(args, errors, warnings)
                if state and not errors and (args.command != "status" or getattr(args, "annotations", None)):
                    save(args.folder, state)
                memory = synchronize(args.folder, state, warnings) if state and not errors else None
        if args.command == "start" and getattr(args, "submit", False) and state and not errors:
            # Étape produite par ses seuls scripts : démarrage, contrôles et soumission en un appel.
            stage = stage_of(state, args.stage, errors)
            checks = run_checks(args.folder, state, stage, errors) if stage else []
            if checks and not errors:
                args.command, args.files = "submit", None
                with locked(args.folder):
                    state, entry = run(args, errors, warnings)
                    if state and not errors:
                        save(args.folder, state)
                    memory = synchronize(args.folder, state, warnings) if state and not errors else None
    except TimeoutError as error:
        state, entry, memory = None, None, None
        errors.append(str(error))
    current, action = next_action(state) if state else (None, "corriger l'erreur")
    if upgraded and not upgraded["applied"] and (changed(upgraded["definition"]) or upgraded["vault"]
                                                 or upgraded["journal"] or upgraded["links"]):
        action = f"montrer ces changements à l'utilisateur, puis relancer upgrade {args.folder} --apply"
    if checks and (errors or args.command == "check"):
        action = (f"corriger les descriptions en erreur, puis relancer check {args.stage}" if errors
                  else f"soumettre {args.stage} (submit)")
    startable = ready(state) if state and not errors else []
    others = [s for s in startable if s != current]
    if others:
        action += f" ; en parallèle, étape(s) prête(s) : {', '.join(others)}"
    # L'étape à produire, seulement quand l'agent en a besoin : au démarrage (celle démarrée) ou à la reprise.
    if args.command == "start" and not errors:
        current_stage = args.stage
    else:
        current_stage = current if state and current and args.command in ("init", "status") and \
            next(s for s in state["stages"] if s["id"] == current)["status"] != "en-revue" else None
    todo = bool(current_stage)
    # Rapport court, lu à chaque commande : statut par étape (dans l'ordre), champs vides omis.
    optional = {"entry": entry, "changes": getattr(args, "changes", None),
                "stage": stage_definition(state, current_stage) if todo else None,
                "ask": ((state.get("definition") or {}).get("ask") or None) if state and args.command == "init" else None,
                "memory": memory, "checks": checks, "upgrade": upgraded, "archived": getattr(args, "archived", None),
                "annotations": getattr(args, "annotations", None) or None}
    report = {"workflow": str(args.folder / STATE), "command": args.command,
              "stages": {s["id"]: s["status"] for s in state["stages"]} if state else {},
              "current": current, "next": action, "ready": startable,
              "questions": len(open_questions(state)) if state else 0,
              **{key: value for key, value in optional.items() if value is not None},
              "errors": errors, "warnings": warnings}
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
