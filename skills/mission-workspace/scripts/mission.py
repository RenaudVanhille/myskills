# /// script
# requires-python = ">=3.10"
# ///
"""Espace de travail d'une mission : un répertoire, un vault Obsidian, ses workflows et ses dépôts.

Une mission est une avant-vente (documents reçus : définir la solution, et
selon le cas son chiffrage, ses schémas, son POS) ou une revue d'architecture
(documentation et code). `mission.json` à sa racine (schéma
shared/schemas/mission.schema.json) dit sa nature, son vault, ses workflows,
ses dépôts et ses référentiels ; les scripts des autres skills le trouvent en
remontant depuis leurs fichiers et prennent alors le vault de la mission sans
qu'on le leur donne.

    uv run scripts/mission.py init DOSSIER --nature avant-vente|revue --name NOM [--client C] [--echeance AAAA-MM-JJ] [--referentiel DOSSIER] [--file MISSION.json] [--no-git]
    uv run scripts/mission.py repo [DOSSIER] --name NOM [--path P] [--url U] [--component C] [--alias A...]
    uv run scripts/mission.py freeze [DOSSIER]
    uv run scripts/mission.py status [DOSSIER]
    uv run scripts/mission.py check [DOSSIER] [--fail-on haute|moyenne|basse|aucune]
    uv run scripts/mission.py upgrade [DOSSIER] [--apply] [--keep-definition]
    uv run scripts/mission.py tidy [DOSSIER] [--apply]
    uv run scripts/mission.py --schema

- init crée mission.json, documents/, le vault (et code/ pour une revue),
  puis lance le workflow de la nature (journal.py init du skill decision-log,
  vault compris) ; refusé dans une mission existante (pas de mission dans une
  mission). Avec un référentiel du client (`--referentiel`, ou
  `referentiel.path` de la description), ses notes sont copiées dans le
  vault (referentiel.py pull) ; status et check disent ensuite combien de
  notes de la mission restent à y verser (push à blanc, rien n'est écrit).
  En dernier, init crée le dépôt git local de la mission (.gitignore pour
  les fichiers de travail, verrous et dépôts de code) et son premier
  commit ; journal.py y fait ensuite un commit par étape validée. Jamais
  poussé. Sans git, ou dans un dépôt existant, un avertissement et rien
  d'autre ; `--no-git` s'en passe.
- repo ajoute ou met à jour un dépôt ; freeze note le commit courant de
  chaque dépôt (git) : la revue porte sur un commit connu.
- status fait le point (workflows, étape courante, dépôts, référentiels,
  contrôles) et réécrit la note `Mission` du vault, conforme à l'ontologie.
- check contrôle la cohérence entre livrables, sans modèle (règles MIS-xx,
  écarts voulus dans `accept` de mission.json, avec leur raison).
- upgrade remet une mission ouverte avec une version antérieure au niveau
  des scripts actuels : chaque workflow (journal.py upgrade : définition
  livrée reprise sans perdre l'avancement, journal.md, liens des livrables,
  mémoire du vault refaite, entrées des versions remplacées archivées,
  empreinte des entrées ../), couleurs et modèles de notes du vault s'ils y
  étaient déjà installés, dépôt git de la mission s'il manque, puis le
  point de status. À blanc par défaut : le rapport (`upgrade`, phrase
  `summary`) dit ce qui changerait et rien n'est écrit ; `--apply` garde
  d'abord l'état d'avant (commit `before` du dépôt git de la mission, créé
  s'il manque, sinon copie dans .historique/upgrade-DATE/), écrit, puis
  fait le commit de l'état d'après : la mise à niveau se défait. Elle range
  aussi la mission comme tidy (copies de sauvegarde et dossiers de travail
  dans .historique/rangement-DATE/). Rejouable :
  une deuxième passe ne change plus rien.
- tidy range ce qui encombre la mission hors des livrables : copies de
  sauvegarde laissées à côté d'un livrable (chiffrage.avant-droits.csv,
  presentation.v1-sans-tjm.pptx, revue.json.bak : un segment du nom marque
  la version et l'original existe) et dossiers de travail (_tmp,
  .myskills-tmp), déplacés dans .historique/rangement-DATE/ avec leur
  chemin ; les fichiers soumis au journal, documents/, le vault et le code
  ne sont jamais touchés. Les verrous Office (~$...) sont seulement
  signalés. À blanc par défaut, --apply déplace. status, check et upgrade
  disent combien il en reste.
"""

import argparse
import datetime
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workspace  # noqa: E402
from text_tools import data_file  # noqa: E402
from skill_paths import require_module, run_script  # noqa: E402
from spec_schema import check as check_schema, print_schema  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")

SEVERITIES = ("haute", "moyenne", "basse")
RULES = {
    "MIS-01": ("haute", "Exigence indispensable non couverte par l'option retenue",
               "Couvrir l'exigence (refs d'un composant dans options.json) ou la déclasser avec l'utilisateur."),
    "MIS-02": ("moyenne", "Composant de l'option retenue sans chiffrage",
               "Ajouter le lot ou la ligne d'infrastructure du composant (component) dans chiffrage.json."),
    "MIS-03": ("moyenne", "Exigence non fonctionnelle indispensable sans scénario de qualité",
               "Ajouter un scénario qui la cite (refs) dans revue.json."),
    "MIS-04": ("haute", "Livrable validé modifié depuis sa validation",
               "Faire revoir l'étape (journal.py review ETAPE --decision retour) ou restaurer le fichier validé (.historique/ETAPE/)."),
    "MIS-05": ("haute", "Livrable portant sur une autre option que celle retenue",
               "Refaire la revue ou le chiffrage sur l'option de decision.json."),
    "MIS-06": ("moyenne", "Dépôt de code introuvable",
               "Cloner le dépôt dans son dossier (path, défaut code/<name>) ou le retirer de mission.json."),
    "MIS-07": ("basse", "Dépôt hors du commit figé",
               "Revenir au commit revu (git checkout) ou figer le nouveau (mission.py freeze)."),
    "MIS-08": ("basse", "Référentiel de la mission introuvable",
               "Déposer le fichier ou corriger references dans mission.json."),
    "MIS-09": ("basse", "Dépôt revu sans commit figé",
               "mission.py freeze : la revue porte alors sur un commit connu et se refait à l'identique."),
}
DELIVERABLES = ("exigences.json", "options.json", "decision.json", "revue.json", "chiffrage.json",
                "dossier-architecture.md")
NOTE = "Mission"
# Segment du nom d'une copie de sauvegarde laissée à côté d'un livrable (chiffrage.avant-droits.csv,
# presentation.v1-sans-tjm.pptx, revue.json.bak), et dossiers de travail : rangés par tidy dans .historique/.
VERSION_MARK = re.compile(r"(avant|apres|before|after|old|ancien|bak|backup|orig|copie|sauvegarde|prev|v\d+)([-_].*)?",
                          re.IGNORECASE)
WORK_DIRS = ("_tmp", ".myskills-tmp", ".tmp")
LOCK_MARKS = ("~$", ".~lock.")


def read_json(path: Path, errors: list[str]) -> dict | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{path.name} illisible : {error}")
        return None


def save(root: Path, mission: dict) -> None:
    (root / workspace.MISSION).write_text(json.dumps(mission, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def git_head(path: Path) -> str | None:
    if not (path / ".git").exists() or not shutil.which("git"):
        return None
    result = subprocess.run(["git", "-C", str(path), "rev-parse", "HEAD"], capture_output=True, text=True,
                            encoding="utf-8")
    return (result.stdout.strip() or None) if result.returncode == 0 else None


def repo_rows(root: Path, mission: dict) -> list[dict]:
    rows = []
    for repo in workspace.repos(root, mission):
        path = Path(repo["root"])
        rows.append({"name": repo["name"], "path": path.relative_to(root.resolve()).as_posix(),
                     "component": repo.get("component"), "present": path.is_dir(),
                     "commit": repo.get("commit"), "head": git_head(path) if path.is_dir() else None})
    return rows


def init(args, errors: list[str], warnings: list[str]) -> dict:
    root = args.folder.resolve()
    parent = workspace.find(root)
    if parent is not None:
        errors.append(f"{root} est déjà dans la mission {parent} : une mission ne s'ouvre pas dans une autre")
        return {}
    mission = {}
    if args.file:
        mission = read_json(args.file, errors) or {}
        if errors:
            return {}
    for key, value in (("name", args.name), ("nature", args.nature), ("client", args.client),
                       ("echeance", args.echeance)):
        if value:
            mission[key] = value
    if args.referentiel:
        mission["referentiel"] = {**(mission.get("referentiel") or {}), "path": args.referentiel}
    mission.setdefault("statut", "en-cours")
    invalid = check_schema(mission, workspace.schema())
    if invalid:
        errors += invalid
        return {}
    root.mkdir(parents=True, exist_ok=True)
    save(root, mission)
    mission, invalid = workspace.load(root)
    if invalid:
        (root / workspace.MISSION).unlink()
        errors += invalid
        return {}
    created = []
    folders = [workspace.path_of(root, mission, "documents"), workspace.path_of(root, mission, "vault")]
    if mission["nature"] == "revue":
        folders.append(root / "code")
    for folder in folders:
        if not folder.is_dir():
            folder.mkdir(parents=True)
            created.append(folder.relative_to(root).as_posix())
    vault = workspace.path_of(root, mission, "vault")
    started = []
    for flow in workspace.workflows(mission):
        folder = root / flow["folder"]
        if (folder / workspace.STATE).is_file():
            warnings.append(f"{flow['folder']} : workflow.json existe déjà, gardé")
            continue
        report = run_script("decision-log", "journal.py", ["init", folder, "--definition", flow["definition"],
                                                           "--title", mission["name"], "--vault", vault])
        errors += [f"workflow {flow['definition']} : {e}" for e in report.get("errors", [])]
        started.append({"definition": flow["definition"], "folder": flow["folder"], "current": report.get("current")})
    return {"created": created, "started": started}


def repo(args, root: Path, mission: dict, errors: list[str]) -> dict:
    entry = {"name": args.name, **{k: v for k, v in (("path", args.path), ("url", args.url),
                                                     ("component", args.component)) if v}}
    if args.alias:
        entry["aliases"] = args.alias
    repos = mission.setdefault("repos", [])
    old = next((r for r in repos if r["name"] == args.name), None)
    if old:
        old.update(entry)
    else:
        repos.append(entry)
    invalid = check_schema(mission, workspace.schema())
    if invalid:
        errors += invalid
        return {}
    save(root, mission)
    _, invalid = workspace.load(root)
    errors += invalid
    return {"updated": bool(old)}


def freeze(root: Path, mission: dict, errors: list[str], warnings: list[str]) -> dict:
    frozen = []
    for entry, row in zip(mission.get("repos", []), repo_rows(root, mission)):
        if not row["present"]:
            warnings.append(f"{row['name']} : dépôt introuvable ({row['path']}), commit non figé")
        elif not row["head"]:
            warnings.append(f"{row['name']} : pas un dépôt git (ou git absent), commit non figé")
        else:
            entry["commit"] = row["head"]
            frozen.append(row["name"])
    if not mission.get("repos"):
        errors.append("mission.json : aucun dépôt (repos) ; ajoutez-les avec mission.py repo")
    if frozen:
        save(root, mission)
    return {"frozen": frozen}


def workflow_rows(root: Path, mission: dict, warnings: list[str]) -> list[dict]:
    rows = []
    for flow in workspace.workflows(mission):
        folder = root / flow["folder"]
        row = {"definition": flow["definition"], "folder": flow["folder"], "current": None, "stages": {},
               "questions": 0, "modified": [], "files": [f for f in DELIVERABLES if data_file(folder, f).is_file()],
               "index": None}
        if not (folder / workspace.STATE).is_file():
            warnings.append(f"{flow['folder']} : workflow {flow['definition']} non démarré (journal.py init)")
            rows.append(row)
            continue
        report = run_script("decision-log", "journal.py", ["status", folder])
        warnings += [f"{flow['folder']} : {e}" for e in report.get("errors", [])]
        row["current"], row["questions"] = report.get("current"), report.get("questions", 0)
        row["todo"] = report.get("todo", [])
        for status in report.get("stages", {}).values():
            row["stages"][status] = row["stages"].get(status, 0) + 1
        row["modified"] = [w for w in report.get("warnings", []) if "modifiés après validation" in w]
        state = json.loads((folder / workspace.STATE).read_text(encoding="utf-8"))
        row["title"] = state.get("title")
        row["labels"] = {s["id"]: s.get("label") or s["id"] for s in (state.get("definition") or {}).get("stages", [])}
        memory = state.get("memory") or {}
        if memory.get("folder"):
            row["index"] = f"{memory['folder']}/{index_name(Path(memory['vault']), memory['folder'])}"
        rows.append(row)
    return rows


def index_name(vault: Path, folder: str) -> str | None:
    """Note d'index du workflow (type workflow) dans son dossier du vault."""
    for note in sorted((vault / folder).glob("*.md")):
        meta = vault_ontology.parse(note.read_text(encoding="utf-8", errors="replace"))[0] or {}
        if meta.get("type") == "workflow":
            return note.stem
    return None


def coherence(root: Path, mission: dict, flows: list[dict], repos: list[dict], errors: list[str]) -> list[dict]:
    findings: list[dict] = []
    accept = mission.get("accept", {})

    def add(rule, element, message, severity=None):
        default, title, fix = RULES[rule]
        severity = severity or default
        reason = accept.get(f"{rule}@{element}") or accept.get(rule)
        findings.append({"rule": rule, "severity": severity, "element": element, "message": f"{title} : {message}",
                         "fix": fix, "accepted": reason})

    several = len(flows) > 1
    for flow in flows:
        folder = root / flow["folder"]
        where = f"{flow['folder']}:" if several else ""
        catalog = read_json(data_file(folder, "exigences.json"), errors) or {}
        options = read_json(data_file(folder, "options.json"), errors) or {}
        decision = read_json(data_file(folder, "decision.json"), errors) or {}
        estimate = read_json(data_file(folder, "chiffrage.json"), errors)
        review = read_json(data_file(folder, "revue.json"), errors)
        requirements = catalog.get("requirements", [])
        chosen = decision.get("option")
        option = next((o for o in options.get("options", []) if o.get("id") == chosen), None)
        if option:
            covered = {ref for comp in option.get("components", []) for ref in comp.get("refs", [])}
            for req in requirements:
                if req.get("priority") == "indispensable" and req["id"] not in covered:
                    add("MIS-01", where + req["id"], f"{req['id']} ({req.get('title', '')}) hors des refs de l'option {chosen}")
            if estimate is not None:
                costed = {line.get("component") for key in ("work", "infra") for line in estimate.get(key, [])}
                for comp in option.get("components", []):
                    if comp.get("role") == "person" or comp["id"] in costed:
                        continue
                    external = comp.get("role") == "external"
                    add("MIS-02", where + comp["id"], f"{comp['id']} ({comp.get('label', '')})"
                        + (", intégration au système externe" if external else ""), "basse" if external else None)
        if chosen:
            if estimate is not None and estimate.get("option") and estimate["option"] != chosen:
                add("MIS-05", where + "chiffrage.json", f"option {estimate['option']} chiffrée, {chosen} retenue")
            picked = ((review or {}).get("source") or {}).get("option")
            if picked and picked != chosen:
                add("MIS-05", where + "revue.json", f"option {picked} revue, {chosen} retenue")
        if review is not None:
            tested = {ref for sc in review.get("scenarios", []) for ref in sc.get("refs", [])}
            for req in requirements:
                nonfunctional = req.get("nature") == "non-fonctionnelle" or (
                    req.get("category") and req.get("nature") != "fonctionnelle")
                if nonfunctional and req.get("priority") == "indispensable" and req["id"] not in tested:
                    add("MIS-03", where + req["id"], f"{req['id']} ({req.get('title', '')}) sans scénario dans revue.json")
        for line in flow["modified"]:
            # « etape : fichiers [extérieurs ]modifiés après validation : a, b ; faites-les revoir... » : l'étape
            # par son libellé et les fichiers seuls, le titre de la règle disant déjà le reste.
            stage, _, rest = line.partition(" : ")
            outside = "extérieurs " in rest.split(" : ", 1)[0]
            files = rest.split(" : ", 1)[-1].split(" ;")[0].split(" (")[0]
            add("MIS-04", where + stage, f"« {flow.get('labels', {}).get(stage, stage)} » : "
                + ("entrées d'un autre workflow " if outside else "") + files)
    for row in repos:
        if not row["present"]:
            add("MIS-06", row["name"], f"{row['path']} absent")
        elif row["commit"] and row["head"] and not row["head"].startswith(row["commit"]):
            add("MIS-07", row["name"], f"commit {row['head'][:12]}, {row['commit'][:12]} figé")
        elif not row["commit"]:
            add("MIS-09", row["name"], "aucun commit dans mission.json")
    for key, value in mission.get("references", {}).items():
        if not (root / value).exists():
            add("MIS-08", key, f"{value} introuvable")
    shared = (mission.get("referentiel") or {}).get("path")
    if shared and not (root / shared).is_dir():  # absolu ou relatif à la mission, hors de la mission
        add("MIS-08", "referentiel", f"{shared} introuvable")
    order = {s: i for i, s in enumerate(SEVERITIES)}
    findings.sort(key=lambda f: (f["accepted"] is not None, order[f["severity"]], f["rule"], f["element"]))
    return findings


def counts(findings: list[dict]) -> dict:
    result = {s: sum(1 for f in findings if f["severity"] == s and not f["accepted"]) for s in SEVERITIES}
    result["acceptés"] = sum(1 for f in findings if f["accepted"])
    return result


def cell(text: str) -> str:
    """Texte d'une cellule de tableau Markdown."""
    return " ".join(str(text).split()).replace("|", "\\|")


def write_note(root: Path, mission: dict, flows: list[dict], repos: list[dict], findings: list[dict],
               errors: list[str]) -> str | None:
    vault = workspace.path_of(root, mission, "vault")
    if not vault.is_dir():
        return None
    notes = vault_ontology.Notes(vault, "mission-workspace")
    props = {k: mission[k] for k in ("nature", "client", "statut", "echeance") if mission.get(k)}
    props["constats"] = sum(1 for f in findings if not f["accepted"])
    body = [f"# Mission {mission['name']}", ""]
    v = vault_ontology
    body += [f"- {label} : {v.label(notes.onto, mission[key]) if key in ('nature', 'statut') else mission[key]}"
             for key, label in (("nature", "Nature"), ("client", "Client"), ("statut", "Statut"),
                                ("echeance", "Échéance")) if mission.get(key)]
    opened = [f for f in findings if not f["accepted"]]
    high = sum(f["severity"] == "haute" for f in opened)
    if opened:
        body += [""] + v.callout("warning" if high else "note",
                                 v.count(len(opened), "contrôle de cohérence ouvert", "contrôles de cohérence ouverts")
                                 + (f", dont {v.number(high)} de gravité haute" if high else ""),
                                 ["Détail dans la section « Contrôles de cohérence »."])[:-1]
    # Ce qui fait avancer la mission, en tête : qui fait quoi, avec les libellés des étapes (journal.py status).
    todo = [f"- {flow.get('title') or flow['definition']} : {line}" if len(flows) > 1 else f"- {line}"
            for flow in flows for line in flow.get("todo", [])]
    if todo:
        body += [""] + v.callout("todo", "À faire maintenant", todo)[:-1]
    nested = any(flow["folder"] != "." for flow in flows)  # la colonne Dossier n'apprend rien si tout est à la racine
    body += ["", "## Workflows", "", "| Workflow |" + (" Dossier |" if nested else "") + " Étapes |",
             "| --- |" + (" --- |" if nested else "") + " --- |"]
    for flow in flows:
        name = f"[[{flow['index']}\\|{flow.get('title') or flow['definition']}]]" if flow["index"] else flow["definition"]
        stages = ", ".join(f"{n} {v.label(notes.onto, s)}" for s, n in sorted(flow["stages"].items())) or "non démarré"
        body.append(f"| {name} |" + (f" {flow['folder']} |" if nested else "") + f" {stages} |")
    if repos:
        body += ["", "## Dépôts", "", "| Dépôt | Composant | Commit figé | Commit actuel |", "| --- | --- | --- | --- |"]
        body += [f"| {r['name']} | {r['component'] or '-'} | {(r['commit'] or '-')[:12]} | "
                 f"{(r['head'] or ('absent' if not r['present'] else '-'))[:12]} |" for r in repos]
    if mission.get("references"):
        body += ["", "## Référentiels", ""] + [f"- {k} : `{v}`" for k, v in mission["references"].items()]
    body += ["", "## Contrôles de cohérence", ""]
    if opened:
        # Une ligne par constat ouvert : ce qui ne va pas et quoi faire ; la règle en fin, pour l'accepter.
        body += ["| Gravité | Constat | À faire |", "| --- | --- | --- |"]
        body += [f"| {f['severity']} | {cell(f['message'])} ({f['rule']}) | {cell(f['fix'])} |" for f in opened]
    else:
        body.append("Aucun écart ouvert entre les livrables.")
    accepted = [f for f in findings if f["accepted"]]
    if accepted:
        body += [""] + v.callout("note", v.count(len(accepted), "écart accepté", "écarts acceptés"), [
            f"- {f['message']} ({f['rule']}) : {f['accepted']}" for f in accepted], folded=True)[:-1]
    relations = {"workflows": [(f["index"], f.get("title") or f["definition"]) for f in flows if f["index"]]}
    notes.add(NOTE, "mission", props, relations, body)
    written = notes.write(errors)
    return f"{NOTE}.md" if written is not None else None


def shared(root: Path, mission: dict, command: str, warnings: list[str]) -> dict | None:
    """Référentiel du client : copié dans le vault à l'ouverture (pull), ce qui reste à y verser ensuite (push à blanc)."""
    path = (mission.get("referentiel") or {}).get("path")
    if not path or not (Path(path) if Path(path).is_absolute() else root / path).is_dir():
        return None
    action = "pull" if command == "init" else "push"
    done = subprocess.run([sys.executable, str(Path(__file__).with_name("referentiel.py")), action, str(root)],
                          capture_output=True, text=True, encoding="utf-8")
    try:
        found = json.loads(done.stdout)
    except ValueError:
        warnings.append(f"référentiel : referentiel.py {action} sans rapport lisible")
        return None
    warnings += [f"référentiel : {text}" for text in found.get("errors", []) + found.get("warnings", [])
                 if not text.startswith("à blanc")]
    if action == "pull":
        return {"path": path, "pulled": found.get("notes", 0)}
    return {"path": path, "to_share": len(found.get("added", [])) + len(found.get("updated", [])),
            "conflicts": len(found.get("conflicts", []))}


def snapshot(root: Path, mission: dict, warnings: list[str]) -> tuple[str | None, str]:
    """Garde l'état d'avant la mise à niveau : commit du dépôt git de la mission (créé s'il manque), sinon copie de
    mission.json et de l'état de chaque workflow dans .historique/. Rend (commit ou dossier, état du dépôt)."""
    if workspace.has_git(root):
        workspace.git_commit(root, mission, "avant(upgrade): état avant la mise à niveau")
        return workspace._git(root, "rev-parse", "--short", "HEAD").stdout.strip() or None, "present"
    commit, warning = workspace.git_init(root, mission)
    if commit or workspace.has_git(root):
        return commit, "cree"
    if warning:
        warnings.append(warning)
    target = Path(workspace.HISTORY) / f"upgrade-{datetime.datetime.now().strftime('%Y-%m-%dT%H%M%S')}"
    kept = [Path(workspace.MISSION)] + [Path(f["folder"]) / name for f in workspace.workflows(mission)
                                        for name in (workspace.STATE, "journal.md")]
    for rel in kept:
        if (root / rel).is_file():
            (root / target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(root / rel, root / target / rel)
    return target.as_posix(), "absent"


def summary(done: dict) -> str:
    """Une phrase : ce que la mise à niveau change (à blanc) ou a changé (--apply)."""
    count = vault_ontology.count
    parts = []
    for row in done["workflows"]:
        found = []
        definition = row["definition"] or {}
        for key, one, many in (("added", "étape ajoutée", "étapes ajoutées"),
                               ("removed", "étape retirée", "étapes retirées"),
                               ("updated", "étape mise à jour", "étapes mises à jour")):
            if definition.get(key):
                found.append(f"{count(len(definition[key]), one, many)} ({', '.join(definition[key])})")
        if row["superseded"]:
            found.append(f"{count(row['superseded'], 'entrée archivée', 'entrées archivées')}")
        if row["noise"]:
            found.append(f"{count(row['noise'], 'événement retiré', 'événements retirés')} du journal (validations, soumissions...)")
        if row["external"]:
            found.append(f"entrées ../ suivies pour {count(row['external'], 'étape')}")
        if row.get("moved"):
            found.append(f"{count(row['moved'], 'fichier machine rangé', 'fichiers machine rangés')} dans donnees/")
        if row["vault"]:
            found.append("vault retrouvé")
        if row["links"]:
            found.append(f"{count(row['links'], 'livrable lié', 'livrables liés')}")
        if row["journal"]:
            found.append("journal.md réécrit")
        if found:
            where = "" if row["folder"] == "." else f" ({row['folder']})"
            name = f" {definition['name']}" if definition.get("name") else ""
            parts.append(f"workflow{name}{where} : {', '.join(found)}")
    if done["git"] != "present":
        parts.append("dépôt git de la mission " + ("créé" if done["git"] == "cree" else "à créer"
                                                    if not done["applied"] else "absent"))
    if done["tidy"]["moved"]:
        what = count(done["tidy"]["moved"], "copie ou dossier de travail", "copies ou dossiers de travail")
        parts.append(f"{what} rangé{'s' if done['tidy']['moved'] > 1 else ''} dans {done['tidy']['history']}"
                     if done["tidy"]["history"] else f"{what} à ranger dans .historique/")
    return " ; ".join(parts) or "rien à changer"


def upgrade(args, root: Path, mission: dict, errors: list[str], warnings: list[str]) -> dict:
    """Mise à niveau de chaque workflow de la mission (journal.py upgrade) puis, avec --apply, des couleurs et
    des modèles de notes du vault quand ils y sont déjà (jamais installés d'office). Avec --apply, l'état d'avant
    est gardé d'abord (snapshot) et l'état d'après fait l'objet d'un commit : la mise à niveau se défait."""
    before, git = None, "present" if workspace.has_git(root) else "absent"
    if args.apply:
        before, git = snapshot(root, mission, warnings)
    rows = []
    for flow in workspace.workflows(mission):
        folder = root / flow["folder"]
        if not (folder / workspace.STATE).is_file():
            continue
        report = run_script("decision-log", "journal.py", ["upgrade", folder] + (["--apply"] if args.apply else [])
                            + (["--keep-definition"] if args.keep_definition else []))
        errors += [f"{flow['folder']} : {e}" for e in report.get("errors", [])]
        warnings += [f"{flow['folder']} : {w}" for w in report.get("warnings", [])]
        if report.get("upgrade"):
            done = report["upgrade"]
            rows.append({"folder": flow["folder"], "definition": done["definition"], "vault": done["vault"],
                         "journal": done["journal"], "links": done["links"],
                         "superseded": done.get("superseded", 0), "noise": done.get("noise", 0), "external": done.get("external", 0),
                         "moved": len(done.get("moved", [])),
                         "notes": (report.get("memory") or {}).get("notes")})
    vault = workspace.path_of(root, mission, "vault")
    style = (vault / ".obsidian" / "snippets" / f"{vault_ontology.SNIPPET}.css").is_file()
    folder = vault_ontology.templates_folder(vault)
    templates = bool(folder) and any(vault_ontology.TEMPLATE_MARK in note.read_text(encoding="utf-8", errors="replace")
                                     for note in (vault / folder).glob("*.md"))
    found = clutter(root, mission)
    moved = len(found["copies"]) + len(found["work"])
    history = None
    if args.apply and not errors and moved:
        history = tidy(args, root, mission, warnings)["history"]
    if args.apply and not errors and vault.is_dir():
        onto = vault_ontology.load()
        with vault_ontology.vault_lock(vault):
            if style:
                vault_ontology.write_style(onto, vault)
            if templates:
                vault_ontology.write_templates(onto, vault, folder)
    return {"applied": bool(args.apply and not errors), "workflows": rows, "style": style, "templates": templates,
            "git": git, "before": before, "tidy": {"moved": moved, "history": history}}


def original_of(path: Path) -> Path | None:
    """Livrable dont ce fichier est une copie de sauvegarde (un segment du nom marque la version et le fichier
    sans ce segment existe à côté), sinon None."""
    parts = path.name.split(".")
    for index in range(1, len(parts)):
        if VERSION_MARK.fullmatch(parts[index]):
            original = path.with_name(".".join(parts[:index] + parts[index + 1:]))
            if original != path and original.is_file():
                return original
    return None


def clutter(root: Path, mission: dict) -> dict:
    """Copies de sauvegarde, dossiers de travail et verrous Office de la mission, chemins relatifs à la racine ;
    jamais un fichier soumis au journal, ni documents/, le vault, le code ou un dossier masqué."""
    kept, skipped = {workspace.MISSION, workspace.STATE}, set()
    for flow in workspace.workflows(mission):
        try:
            state = json.loads((root / flow["folder"] / workspace.STATE).read_text(encoding="utf-8"))
            kept |= {(Path(flow["folder"]) / f).as_posix().removeprefix("./")
                     for stage in state["stages"] for f in stage.get("files", {})}
        except (OSError, ValueError, KeyError, TypeError):
            pass
    for key in ("vault", "documents"):
        skipped.add(workspace.path_of(root, mission, key).resolve())
    skipped |= {Path(r["root"]) for r in workspace.repos(root, mission)} | {(root / "code").resolve()}
    found = {"copies": [], "work": [], "locks": []}
    for top, dirs, files in os.walk(root):
        here = Path(top)
        for name in sorted(dirs):
            if name in WORK_DIRS:
                found["work"].append((here / name).relative_to(root).as_posix())
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d not in WORK_DIRS
                         and (here / d).resolve() not in skipped)
        for name in sorted(files):
            rel = (here / name).relative_to(root).as_posix()
            if name.startswith(LOCK_MARKS):
                found["locks"].append(rel)
            elif rel not in kept and original_of(here / name):
                found["copies"].append(rel)
    return found


def tidy(args, root: Path, mission: dict, warnings: list[str]) -> dict:
    """Range les copies de sauvegarde et les dossiers de travail dans .historique/rangement-DATE/ (à blanc sans
    --apply) ; signale les verrous Office."""
    found = clutter(root, mission)
    target = Path(workspace.HISTORY) / f"rangement-{datetime.datetime.now().strftime('%Y-%m-%dT%H%M%S')}"
    moved = found["copies"] + found["work"]
    if args.apply and moved:
        for rel in moved:
            (root / target / rel).parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(root / rel), str(root / target / rel))
    warnings += [f"verrou Office {rel} : fermez le document, puis supprimez ce fichier s'il reste"
                 for rel in found["locks"]]
    return {"applied": bool(args.apply), "history": target.as_posix() if moved else None, **found}


def pending(done: dict) -> bool:
    """Reste-t-il quelque chose qu'une mise à niveau à blanc écrirait ?"""
    return done.get("git") == "absent" or done["tidy"]["moved"] > 0 or any(w["journal"] or w["links"] or w["vault"] or w["superseded"]
                                              or w["noise"] or w["external"] or w.get("moved")
                                              or (w["definition"] or {}).get("changed")
                                              for w in done["workflows"])


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--schema"]:
        print_schema(__file__)
        return 0
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    start = sub.add_parser("init", help="ouvre une mission dans un dossier")
    start.add_argument("folder", type=Path)
    start.add_argument("--nature", choices=sorted(workspace.WORKFLOWS))
    start.add_argument("--name", help="nom court de la mission")
    start.add_argument("--client")
    start.add_argument("--echeance", help="date de remise ou de comité, AAAA-MM-JJ")
    start.add_argument("--referentiel", help="dossier du référentiel du client, copié dans le vault (referentiel.py pull)")
    start.add_argument("--file", type=Path, help="description complète (mission.json), validée contre son schéma")
    start.add_argument("--no-git", action="store_true",
                       help="sans dépôt git local de la mission (défaut : git init, un commit par étape validée)")
    add_repo = sub.add_parser("repo", help="ajoute ou met à jour un dépôt de code")
    add_repo.add_argument("folder", type=Path, nargs="?", default=Path.cwd())
    add_repo.add_argument("--name", required=True)
    add_repo.add_argument("--path", help="dossier du dépôt (défaut : code/<name>)")
    add_repo.add_argument("--url")
    add_repo.add_argument("--component", help="composant de l'architecture que le dépôt réalise")
    add_repo.add_argument("--alias", nargs="*", help="autres noms du service dans la configuration")
    for name in ("freeze", "status", "check", "upgrade", "tidy"):
        command = sub.add_parser(name)
        command.add_argument("folder", type=Path, nargs="?", default=Path.cwd())
        if name == "tidy":
            command.add_argument("--apply", action="store_true",
                                 help="déplacer dans .historique/ (défaut : à blanc, rien n'est déplacé)")
        if name == "upgrade":
            command.add_argument("--apply", action="store_true",
                                 help="écrire les changements (défaut : à blanc, rien n'est écrit)")
            command.add_argument("--keep-definition", action="store_true",
                                 help="garder les étapes et consignes d'origine de chaque workflow")
        if name == "check":
            command.add_argument("--fail-on", choices=SEVERITIES + ("aucune",), default="haute",
                                 help="code 1 dès un contrôle ouvert de cette gravité ou plus (défaut : haute)")
    args = parser.parse_args()

    errors: list[str] = []
    warnings: list[str] = []
    report = {"command": args.command, "mission": None, "nature": None, "vault": None, "workflows": [],
              "repos": [], "findings": [], "counts": None, "note": None, "next": None}
    root = None
    if args.command == "init":
        if not args.file and not (args.nature and args.name):
            parser.error("--nature et --name attendus (ou --file)")
        extra = init(args, errors, warnings)
        if not errors:
            root = args.folder.resolve()
            report["created"], report["started"] = extra["created"], extra["started"]
    else:
        root = workspace.find(args.folder)
        if root is None:
            errors.append(f"aucune mission.json dans {args.folder.resolve()} ni au-dessus : mission.py init d'abord")
    mission = None
    if root is not None and not errors:
        mission, invalid = workspace.load(root)
        errors += invalid
    if mission and args.command == "repo":
        report.update(repo(args, root, mission, errors))
    if mission and args.command == "freeze":
        report.update(freeze(root, mission, errors, warnings))
    if mission and args.command == "tidy":
        report["tidy"] = tidy(args, root, mission, warnings)
        report.update({"mission": str(root / workspace.MISSION), "nature": mission["nature"],
                       "vault": str(workspace.path_of(root, mission, "vault"))})
        moved = len(report["tidy"]["copies"]) + len(report["tidy"]["work"])
        report["next"] = ("montrer cette liste à l'utilisateur, puis relancer mission.py tidy --apply"
                          if moved and not args.apply else "rien à ranger" if not moved else
                          f"{moved} élément(s) rangé(s) dans {report['tidy']['history']}")
        mission = None
    if mission and args.command == "upgrade":
        report["upgrade"] = upgrade(args, root, mission, errors, warnings)
        report["upgrade"]["pending"] = not report["upgrade"]["applied"] and pending(report["upgrade"])
        report["upgrade"]["summary"] = summary(report["upgrade"])
        if not report["upgrade"]["applied"]:  # à blanc : le point de status écrirait dans le vault
            report.update({"mission": str(root / workspace.MISSION), "nature": mission["nature"],
                           "vault": str(workspace.path_of(root, mission, "vault"))})
            if not errors:
                report["next"] = ("mission.py upgrade --apply : l'état d'avant est gardé (commit git, sinon .historique/)"
                                  if report["upgrade"]["pending"] else
                                  "mission à niveau ; mission.py upgrade --apply refait quand même la mémoire du vault")
            mission = None
    if mission and not errors:
        flows = workflow_rows(root, mission, warnings)
        repos = repo_rows(root, mission)
        findings = coherence(root, mission, flows, repos, errors)
        report.update({"mission": str(root / workspace.MISSION), "nature": mission["nature"],
                       "vault": str(workspace.path_of(root, mission, "vault")),
                       "workflows": [{k: f[k] for k in ("definition", "folder", "current", "stages", "questions", "files")}
                                     for f in flows],
                       "repos": repos, "findings": findings, "counts": counts(findings)})
        if args.command in ("init", "status", "check", "upgrade"):
            report["note"] = write_note(root, mission, flows, repos, findings, errors)
        current = next((f for f in flows if f["current"]), None)
        open_ = [f for f in findings if not f["accepted"]]
        if open_:
            report["next"] = f"traiter les contrôles ouverts ({open_[0]['rule']} {open_[0]['element']} d'abord)"
        elif current:
            report["next"] = f"workflow {current['definition']} : étape {current['current']} (journal.py status {current['folder']})"
        else:
            report["next"] = "rien à faire"
        if args.command in ("init", "status", "check", "upgrade"):
            memory = shared(root, mission, args.command, warnings)
            if memory:
                report["referentiel"] = memory
                if memory.get("to_share") and not current and not open_:
                    report["next"] = (f"proposer à l'utilisateur de verser {memory['to_share']} note(s) au référentiel du "
                                      "client : referentiel.py push (à blanc, à lui montrer), puis --apply avec son accord")
        if args.command in ("status", "check", "upgrade"):
            found = clutter(root, mission)
            if found["copies"] or found["work"]:
                warnings.append(f"{len(found['copies'])} copie(s) de sauvegarde et {len(found['work'])} dossier(s) de "
                                "travail à ranger hors des livrables : mission.py tidy (à blanc, puis --apply)")
        if args.command == "upgrade" and report["upgrade"]["applied"]:
            # En dernier : le commit prend la mission mise à niveau, note et mémoire comprises.
            report["upgrade"]["commit"] = workspace.git_commit(root, mission, "upgrade(mission): mise à niveau myskills")
        if mission["nature"] == "revue" and not mission.get("repos"):
            warnings.append("revue sans dépôt : ajoutez le code avec mission.py repo (un par service)")
    if args.command == "init" and root is not None and not errors and not args.no_git:
        # En dernier : le premier commit prend la mission entière (vault, note de mission, workflows).
        report["git"], warning = workspace.git_init(root, mission)
        if warning:
            warnings.append(warning)
    failing = False
    if args.command == "check" and report["counts"] and args.fail_on != "aucune":
        limit = SEVERITIES.index(args.fail_on)
        failing = any(report["counts"][s] for s in SEVERITIES[:limit + 1])
    print(json.dumps({**report, "errors": errors, "warnings": warnings}, ensure_ascii=False))
    return 1 if errors or failing else 0


if __name__ == "__main__":
    sys.exit(main())
