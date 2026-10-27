# /// script
# requires-python = ">=3.10"
# ///
"""Capitalise les retours de revue : leçons par mission, retours récurrents, règles de complétude.

Lit les retours (`retour`) du journal de chaque workflow des missions données
(workflow.json, skill decision-log) et, sans modèle :
- les regroupe par mission et par étape, en rapprochant les retours qui
  disent la même chose (mêmes mots significatifs) ;
- repère ceux qui reviennent dans plusieurs missions (--min-missions, 2 par
  défaut) et, pour une étape de chiffrage ou de revue, propose la règle de
  complétude qui les attraperait (poste attendu de solution-estimate,
  scénario attendu d'architecture-review), sauf si une règle en place les
  couvre déjà ;
- écrit `lecons.md` (relecture) et `lecons.json` (propositions), sans toucher
  aux règles.

L'utilisateur décide : les règles retenues, relues et corrigées, vont dans un
fichier de règles (même schéma que les règles, shared/schemas/rules.schema.json)
que `--apply` ajoute à celles de la mission (`--to mission` :
`references.regles` de mission.json, `regles.json` par défaut) ou à celles de
l'utilisateur, communes à ses missions (`--to utilisateur` : MYSKILLS_REGLES,
sinon ~/.myskills/regles.json). Une règle de même id est remplacée.

    uv run scripts/lessons.py DOSSIER [DOSSIER...] [--min-missions 2] [--out-dir DOSSIER]
    uv run scripts/lessons.py --apply retenues.json --to mission|utilisateur [--mission DOSSIER] | --schema

DOSSIER : racine d'une mission (mission.json, tous ses workflows) ou dossier
d'un workflow (workflow.json).
"""

import argparse
import json
import os
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, load_module  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402
import workspace  # noqa: E402

STATE = "workflow.json"
# Mots sans portée pour rapprocher deux retours (après suppression des accents).
STOP = set("""avec dans pour plus sans mais cette ces sont etre fait faire tout tous toute toutes leur leurs comme
aussi encore ajouter ajoute ajoutez manque manquent manquant manquante oublie oublies oubli faut doit doivent
peut pourrait pourquoi quand quel quelle quels quelles elle elles nous vous ils sur sous entre chaque autre
autres meme deja bien tres trop peu etat etape cela celle celui ceux avoir votre notre revoir reprendre
reprise merci voir ici non oui apres avant deux trois""".split())
STEM = 6          # lettres gardées d'un mot pour le rapprocher de ses variantes (tests, test ; charges, charge)
SAME = 2          # mots significatifs en commun pour dire que deux retours parlent de la même chose
KINDS = {"solution-estimate": "chiffrage", "architecture-review": "revue"}
PREFIX = {"chiffrage": "CHF", "revue": "REV"}


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def stems(text: str) -> list[str]:
    seen: list[str] = []
    for word in re.findall(r"[a-z]{4,}", plain(text)):
        if word not in STOP and word[:STEM] not in STOP and word[:STEM] not in seen:
            seen.append(word[:STEM])
    return seen


def workflow_dirs(folder: Path, errors: list[str]) -> tuple[str, list[Path]]:
    """Nom de la mission et dossiers de ses workflows (ou le seul workflow du dossier)."""
    root = workspace.find(folder)
    if root is not None:
        mission, invalid = workspace.load(root)
        if invalid:
            errors += [f"{folder} : {e}" for e in invalid]
            return str(folder), []
        dirs = [(root / w["folder"]).resolve() for w in workspace.workflows(mission)]
        return mission["name"], [d for d in dirs if (d / STATE).is_file()]
    if (folder / STATE).is_file():
        try:
            title = json.loads((folder / STATE).read_text(encoding="utf-8")).get("title")
        except (OSError, ValueError):
            title = None
        return title or folder.resolve().name, [folder.resolve()]
    errors.append(f"{folder} : ni mission (mission.json) ni workflow ({STATE})")
    return str(folder), []


def collect(folders: list[Path], errors: list[str], warnings: list[str]) -> list[dict]:
    """Retours du journal de chaque workflow : mission, étape, nature (chiffrage, revue), texte."""
    items = []
    for folder in folders:
        name, dirs = workflow_dirs(folder, errors)
        if not dirs and not errors:
            warnings.append(f"{folder} : aucun workflow démarré")
        for directory in dirs:
            try:
                state = json.loads((directory / STATE).read_text(encoding="utf-8"))
            except (OSError, ValueError) as error:
                errors.append(f"{directory / STATE} illisible : {error}")
                continue
            stages = {s["id"]: s for s in (state.get("definition") or {}).get("stages", [])}
            for entry in state.get("entries", []):
                if entry.get("kind") != "retour":
                    continue
                skills = stages.get(entry.get("stage"), {}).get("skills", [])
                kind = next((KINDS[s] for s in skills if s in KINDS), None)
                items.append({"mission": name, "workflow": state.get("title", directory.name),
                              "stage": entry.get("stage"), "entry": entry["id"], "date": entry.get("date", ""),
                              "kind": kind, "text": entry.get("text", ""), "stems": stems(entry.get("text", ""))})
    return items


def cluster(items: list[dict]) -> list[list[dict]]:
    """Retours qui disent la même chose : mêmes nature et au moins SAME mots significatifs en commun
    (ou tous ceux du plus court), regroupés de proche en proche."""
    parent = list(range(len(items)))

    def top(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i, a in enumerate(items):
        for j in range(i + 1, len(items)):
            b = items[j]
            common = set(a["stems"]) & set(b["stems"])
            if a["kind"] == b["kind"] and common and \
                    len(common) >= min(SAME, len(a["stems"]), len(b["stems"])):
                parent[top(j)] = top(i)
    groups: dict[int, list[dict]] = {}
    for i, item in enumerate(items):
        groups.setdefault(top(i), []).append(item)
    return list(groups.values())


def builtin_rules(kind: str, warnings: list[str]) -> Path | None:
    """Règles livrées du skill de cette nature (references/ de solution-estimate ou d'architecture-review)."""
    skill, script = {"chiffrage": ("solution-estimate", "estimate_build.py"),
                     "revue": ("architecture-review", "arch_review.py")}[kind]
    module = load_module(skill, script)
    if module is None:
        warnings.append(f"règles {kind} en place non lues : {absent(skill, script)}")
        return None
    return module.EXPECTED


def common_stems(group: list[dict]) -> list[str]:
    return [s for s in group[0]["stems"] if all(s in g["stems"] for g in group)] or group[0]["stems"][:3]


def covered(group: list[dict], rules: list[dict]) -> str | None:
    """Règle en place qui attrape déjà le sujet de chaque retour du groupe : ce que son motif trouve dans le
    retour couvre son premier mot commun au groupe (le sujet), ou au moins la moitié de ces mots. Un mot
    secondaire (« après la bascule ») ne suffit pas."""
    common = common_stems(group)
    for rule in rules:
        hits = 0
        for item in group:
            text = plain(item["text"])
            spans = [m.span() for m in re.finditer(rule["pattern"], text)]
            words = [w for w in re.finditer(r"[a-z]{4,}", text) if w.group()[:STEM] in common]
            inside = {w.group()[:STEM] for w in words if any(a <= w.start() < b for a, b in spans)}
            hits += bool(words) and words[0].group()[:STEM] in inside or 2 * len(inside) >= len(common)
        if hits == len(group):
            return rule["id"]
    return None


# Attribut de qualité d'un scénario proposé, d'après les mots des retours (premier trouvé).
ATTRIBUTES = [("performance", r"charge|perform|latence|temps de reponse|debit"),
              ("disponibilite", r"panne|disponib|interruption|reprise|sinistre|secours"),
              ("securite", r"secur|attaqu|intrusion|acces|authentif|chiffrement"),
              ("exploitabilite", r"version|deploi|supervision|exploitation|incident|journa"),
              ("evolutivite", r"croissance|volume|evoluti"),
              ("conformite", r"rgpd|conformit|reglement|donnees personnelles")]


def proposal(group: list[dict], kind: str, taken: set[str]) -> dict:
    """Règle de complétude à relire : mots communs du groupe en libellé et en motif."""
    common = common_stems(group)
    base = f"{PREFIX[kind]}-{'-'.join(common[:2])}"
    rule_id, n = base, 2
    while rule_id in taken:
        rule_id, n = f"{base}-{n}", n + 1
    taken.add(rule_id)
    source = "retours " + ", ".join(f"{g['entry']} ({g['mission']})" for g in group)
    rule = {"id": rule_id, "label": group[0]["text"][:120], "pattern": "|".join(common[:4]), "source": source}
    if kind == "revue":
        text = plain(" ".join(g["text"] for g in group))
        rule["attribute"] = next((a for a, pattern in ATTRIBUTES if re.search(pattern, text)), "autre")
        if rule["attribute"] != "autre":
            rule["when"] = {"categories": [rule["attribute"]]}
    return rule


def analyse(folders: list[Path], min_missions: int, out_dir: Path, errors: list[str],
            warnings: list[str]) -> dict:
    items = collect(folders, errors, warnings)
    groups = cluster(items)
    rules = {}
    for kind in PREFIX:
        path = builtin_rules(kind, warnings)
        loaded, _, invalid = workspace.rules(kind, path, folders) if path else ([], [], [])
        errors += invalid
        rules[kind] = loaded
    lessons, recurring, taken = [], [], {r["id"] for k in rules.values() for r in k}
    for number, group in enumerate(sorted(groups, key=lambda g: (-len({i["mission"] for i in g}), g[0]["entry"])), 1):
        missions = sorted({i["mission"] for i in group})
        lesson = {"id": f"L-{number:02d}", "kind": group[0]["kind"], "missions": missions,
                  "stages": sorted({i["stage"] for i in group}),
                  "retours": [{k: i[k] for k in ("mission", "entry", "stage", "text")} for i in group]}
        if len(missions) >= min_missions:
            kind = group[0]["kind"]
            if kind:
                lesson["covered_by"] = covered(group, rules[kind])
                if not lesson["covered_by"]:
                    lesson["rule"] = proposal(group, kind, taken)
            recurring.append(lesson["id"])
        lessons.append(lesson)
    return {"items": items, "lessons": lessons, "recurring": recurring}


def render(found: dict, min_missions: int) -> str:
    lines = ["# Leçons des revues", "",
             f"{len(found['items'])} retour(s), {len(found['lessons'])} leçon(s), "
             f"{len(found['recurring'])} récurrente(s) (au moins {min_missions} missions).", ""]
    proposed = [l for l in found["lessons"] if l.get("rule")]
    if proposed:
        lines += ["## Règles proposées", "",
                  "À relire : gardez, corrigez ou écartez chaque règle, puis appliquez les retenues "
                  "(`lessons.py --apply`).", "",
                  "| Leçon | Nature | Règle | Libellé | Motif | Missions |", "|---|---|---|---|---|---|"]
        for l in proposed:
            r = l["rule"]
            lines.append(f"| {l['id']} | {l['kind']} | {r['id']} | {r['label']} | `{r['pattern']}` | "
                         f"{', '.join(l['missions'])} |")
        lines.append("")
    done = [l for l in found["lessons"] if l.get("covered_by")]
    if done:
        lines += ["## Déjà couvertes par une règle", ""]
        lines += [f"- {l['id']} : {l['covered_by']} ({', '.join(l['missions'])})" for l in done]
        lines.append("")
    by_mission: dict[str, list] = {}
    for l in found["lessons"]:
        for r in l["retours"]:
            by_mission.setdefault(r["mission"], []).append((l["id"], r))
    for mission, rows in sorted(by_mission.items()):
        lines += [f"## {mission}", "", "| Leçon | Étape | Entrée | Retour |", "|---|---|---|---|"]
        lines += [f"| {lid} | {r['stage']} | {r['entry']} | {' '.join(r['text'].split()).replace('|', '/')} |"
                  for lid, r in sorted(rows, key=lambda x: (x[1]['stage'] or '', x[1]['entry']))]
        lines.append("")
    return "\n".join(lines)


def apply(path: Path, to: str, mission_dir: Path | None, errors: list[str], warnings: list[str]) -> dict:
    """Ajoute les règles retenues au fichier de la mission ou de l'utilisateur, validé avant l'écriture."""
    report = {"input": str(path), "target": None, "added": [], "replaced": [], "errors": errors,
              "warnings": warnings}
    try:
        decisions = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{path} illisible : {error}")
        return report
    invalid = validate(decisions, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    if to == "mission":
        root = workspace.find(mission_dir or path)
        if root is None:
            errors.append(f"target mission : aucune mission (mission.json) au-dessus de {mission_dir or path}")
            return report
        mission, invalid = workspace.load(root)
        if invalid:
            errors.extend(invalid)
            return report
        name = mission.get("references", {}).get("regles")
        target = root / (name or "regles.json")
        if not name:
            mission.setdefault("references", {})["regles"] = "regles.json"
            (root / workspace.MISSION).write_text(json.dumps(mission, ensure_ascii=False, indent=2) + "\n",
                                                  encoding="utf-8")
            warnings.append("references.regles ajouté à mission.json : regles.json")
    else:
        target = Path(os.environ.get(workspace.RULES_ENV) or Path.home() / ".myskills" / "regles.json")
    report["target"] = str(target)
    current = {}
    if target.is_file():
        try:
            current = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"{target} illisible : {error}")
            return report
    for kind in PREFIX:
        for rule in decisions.get(kind, []):
            existing = current.setdefault(kind, [])
            ids = [r["id"] for r in existing]
            if rule["id"] in ids:
                existing[ids.index(rule["id"])] = rule
                report["replaced"].append(rule["id"])
            else:
                existing.append(rule)
                report["added"].append(rule["id"])
    schema = json.loads((Path(workspace.__file__).parent / "rules.schema.json").read_text(encoding="utf-8"))
    invalid = [f"{target.name} : {e}" for e in check(current, schema)]
    for kind in PREFIX:
        for index, rule in enumerate(current.get(kind, [])):
            try:
                re.compile(rule.get("pattern", ""))
            except re.error as error:
                invalid.append(f"{kind}/{index}/pattern : expression invalide ({error})")
    if invalid:
        errors.extend(invalid)
        report["added"], report["replaced"] = [], []
        return report
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(current, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", type=Path, nargs="*", help="missions ou dossiers de workflow")
    parser.add_argument("--min-missions", type=int, default=2,
                        help="missions où un retour doit revenir pour proposer une règle (défaut : 2)")
    parser.add_argument("--out-dir", type=Path, help="dossier de lecons.md et lecons.json (défaut : le premier)")
    parser.add_argument("--apply", type=Path, help="règles retenues à ajouter (schéma des règles de complétude)")
    parser.add_argument("--to", choices=["mission", "utilisateur"],
                        help="avec --apply : règles de la mission, ou de l'utilisateur (toutes ses missions)")
    parser.add_argument("--mission", type=Path, help="avec --apply : dossier de la mission (défaut : celui des "
                                                     "décisions)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON des règles retenues sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    errors: list[str] = []
    warnings: list[str] = []
    if args.apply:
        if not args.to:
            parser.error("--apply demande --to mission ou --to utilisateur")
        report = apply(args.apply, args.to, args.mission, errors, warnings)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if errors else 0
    if not args.folders:
        parser.error("au moins un dossier de mission ou de workflow attendu (ou --apply)")
    out_dir = args.out_dir or args.folders[0]
    found = analyse(args.folders, args.min_missions, out_dir, errors, warnings)
    report = {"missions": len({i["mission"] for i in found["items"]}), "retours": len(found["items"]),
              "lessons": len(found["lessons"]), "recurring": found["recurring"],
              "proposed": [l["rule"]["id"] for l in found["lessons"] if l.get("rule")],
              "covered": {l["id"]: l["covered_by"] for l in found["lessons"] if l.get("covered_by")},
              "outputs": [], "errors": errors, "warnings": warnings}
    if not errors:
        out_dir.mkdir(parents=True, exist_ok=True)
        md, data = out_dir / "lecons.md", out_dir / "lecons.json"
        md.write_text(render(found, args.min_missions) + "\n", encoding="utf-8")
        data.write_text(json.dumps({"lessons": found["lessons"]}, ensure_ascii=False, indent=1) + "\n",
                        encoding="utf-8")
        # Relu : chaque leçon et chaque règle proposée figurent dans le Markdown écrit.
        text = md.read_text(encoding="utf-8")
        errors += [f"lecons.md : {l['id']} absente" for l in found["lessons"] if f"| {l['id']} |" not in text
                   and f"- {l['id']} :" not in text]
        report["outputs"] = [str(md), str(data)]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
