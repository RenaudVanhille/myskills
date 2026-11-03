# /// script
# requires-python = ">=3.10"
# ///
"""Contrôle l'évaluation 6R d'un portefeuille d'applications et calcule les vagues de migration.

Le modèle décrit chaque application (criticité, technologie, hébergement,
dépendances, fin de support, données) et choisit sa stratégie parmi les 6R
(rehost, replatform, refactor, repurchase, retire, retain) en disant
pourquoi, avec l'effort et le risque. Le script, et non le modèle, contrôle
et calcule :

- dépendances connues et sans cycle ; une application retirée dont une
  application gardée dépend encore ;
- cohérences : refactor d'effort S, rehost d'une technologie hors support,
  repurchase sans solution cible, application critique à risque élevé sans
  parade, données sensibles chez un hébergeur cible soumis à des lois
  extraterritoriales (catalogue commun des hébergeurs) ;
- références vers les exigences (exigences.json) ;
- vagues : une application migre après les applications migrées dont elle
  dépend ; à rang égal, les moins critiques d'abord (pilote) ; --max-per-wave
  borne la taille d'une vague.

Écrit <nom>.md (synthèse, tableau des applications, vagues, points
d'attention), <nom>.csv et <nom>.waves.json (vagues, repris par
transition-roadmap).

    uv run scripts/assess_build.py MIGRATION.json [--out-dir DOSSIER] [--max-per-wave N] [--today AAAA-MM-JJ] | --schema
"""

import argparse
import csv
import difflib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402
from skill_paths import require_file  # noqa: E402

PROVIDERS = require_file("cloud-architecture", "lib/providers.json")
STRATEGIES = {"rehost": "Réhéberger (lift and shift)", "replatform": "Replateformer (lift, tinker and shift)",
              "refactor": "Refondre (cloud natif)", "repurchase": "Racheter (SaaS ou progiciel)",
              "retire": "Retirer", "retain": "Conserver en l'état"}
MOVING = ("rehost", "replatform", "refactor", "repurchase")
CRITICALITY = {"basse": 0, "moyenne": 1, "haute": 2}
EFFORT = {"S": 0, "M": 1, "L": 2, "XL": 3}


def close(name: str, known) -> str:
    match = difflib.get_close_matches(name, list(known), n=1)
    return f" ; vouliez-vous « {match[0]} » ?" if match else ""


def cycle(apps: dict) -> list[str] | None:
    """Premier cycle de dépendances trouvé, ou None."""
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for dep in apps[node].get("depends_on", []):
            if dep not in apps:
                continue
            if state.get(dep) == 1:
                return stack[stack.index(dep):] + [dep]
            if not state.get(dep):
                found = visit(dep)
                if found:
                    return found
        stack.pop()
        state[node] = 2
        return None

    for node in apps:
        if not state.get(node):
            found = visit(node)
            if found:
                return found
    return None


def check(spec: dict, base: Path, today: date, errors: list[str], warnings: list[str]) -> None:
    apps = {a["id"]: a for a in spec["applications"]}
    if len(apps) != len(spec["applications"]):
        errors.append("applications : identifiant en double")
    for a in spec["applications"]:
        for dep in a.get("depends_on", []):
            if dep not in apps:
                errors.append(f"applications/{a['id']}/depends_on : application inconnue « {dep} »{close(dep, apps)}")
            elif dep == a["id"]:
                errors.append(f"applications/{a['id']}/depends_on : l'application dépend d'elle-même")
    loop = cycle(apps)
    if loop and len(loop) > 2:
        errors.append(f"dépendances en cycle : {' -> '.join(loop)} ; une dépendance est à retirer ou à inverser")
    for a in spec["applications"]:
        where = f"applications/{a['id']}"
        if a["strategy"] == "retire":
            users = [b["id"] for b in spec["applications"] if a["id"] in b.get("depends_on", [])
                     and b["strategy"] != "retire"]
            if users:
                errors.append(f"{where} : retirée alors que {', '.join(users)} en dépend ; remplacer la dépendance "
                              "ou retirer aussi ces applications")
        if a["strategy"] == "refactor" and a["effort"] == "S":
            warnings.append(f"{where} : refactor d'effort S, à vérifier (une refonte cloud native coûte rarement peu)")
        if a["strategy"] == "repurchase" and not a.get("target_service"):
            warnings.append(f"{where} : repurchase sans solution cible (target_service)")
        eos = a.get("end_of_support")
        if eos and date.fromisoformat(eos) <= today and a["strategy"] in ("rehost", "retain"):
            warnings.append(f"{where} : {a['strategy']} d'une technologie hors support depuis le {eos} : "
                            "l'obsolescence est déplacée, pas traitée")
        if a["criticality"] == "haute" and a["risk"] == "eleve" and not a.get("mitigations"):
            warnings.append(f"{where} : application critique à risque élevé sans parade (mitigations)")
    target = spec.get("target", {}).get("provider")
    if target:
        try:
            catalog = json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]
        except (OSError, ValueError) as error:
            errors.append(f"catalogue des hébergeurs illisible : {error}")
            catalog = None
        if catalog is not None and target not in catalog:
            errors.append(f"target/provider : hébergeur inconnu « {target} »"
                          + (close(target, catalog) or f" ({', '.join(catalog)})"))
        elif catalog is not None and catalog[target].get("jurisdiction") == "hors-ue":
            sensitive = [a["id"] for a in spec["applications"] if a.get("data") == "sensibles"
                         and a["strategy"] in ("rehost", "replatform", "refactor")]
            if sensitive:
                warnings.append(f"{', '.join(sensitive)} : données sensibles chez {catalog[target]['name']}, soumis à "
                                "des lois extraterritoriales ; à couvrir par l'analyse d'impact (data-protection)")
    if spec.get("requirements"):
        try:
            known = {r["id"] for r in json.loads((base / spec["requirements"]).read_text(encoding="utf-8"))
                     .get("requirements", [])}
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"requirements : {spec['requirements']} illisible ({error})")
            return
        for a in spec["applications"]:
            for ref in a.get("refs", []):
                if ref not in known:
                    errors.append(f"applications/{a['id']}/refs : exigence inconnue « {ref} »{close(ref, known)}")


def waves(spec: dict, limit: int) -> list[list[dict]]:
    """Vagues de migration : après ses dépendances migrées ; à rang égal, moins critique et plus léger d'abord."""
    apps = {a["id"]: a for a in spec["applications"] if a["strategy"] in MOVING}
    rank: dict[str, int] = {}

    def need(app_id: str) -> int:
        if app_id not in rank:
            deps = [d for d in apps[app_id].get("depends_on", []) if d in apps]
            rank[app_id] = 1 + max((need(d) for d in deps), default=0)
        return rank[app_id]

    order = sorted(apps, key=lambda i: (need(i), CRITICALITY[apps[i]["criticality"]], EFFORT[apps[i]["effort"]], i))
    placed: dict[str, int] = {}
    result: list[list[dict]] = []
    for app_id in order:
        wave = max((placed[d] + 1 for d in apps[app_id].get("depends_on", []) if d in placed), default=0)
        while limit and wave < len(result) and len(result[wave]) >= limit:
            wave += 1
        while len(result) <= wave:
            result.append([])
        result[wave].append(apps[app_id])
        placed[app_id] = wave
    return result


def write(spec: dict, plan: list[list[dict]], out_dir: Path, stem: str, warnings: list[str]) -> list[str]:
    apps = spec["applications"]
    counts = {s: sum(a["strategy"] == s for a in apps) for s in STRATEGIES}
    wave_of = {a["id"]: f"V{i + 1}" for i, wave in enumerate(plan) for a in wave}
    lines = [f"# Évaluation de migration : {spec['title']}", ""]
    if spec.get("target", {}).get("provider"):
        lines += [f"Cible : {spec['target']['provider']}"
                  + (f" ({spec['target']['note']})" if spec["target"].get("note") else "") + ".", ""]
    lines += [f"{len(apps)} applications ; " + ", ".join(f"{s} : {n}" for s, n in counts.items() if n)
              + f" ; {len(plan)} vague(s) de migration.", "", "## Stratégies", "",
              "| Stratégie | Applications |", "| --- | --- |"]
    lines += [f"| {STRATEGIES[s]} | {', '.join(a['id'] for a in apps if a['strategy'] == s)} |"
              for s in STRATEGIES if counts[s]]
    lines += ["", "## Applications", "", "| Id | Application | Criticité | Stratégie | Cible | Effort | Risque | Vague "
              "| Pourquoi |", "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for a in apps:
        lines.append(f"| {a['id']} | {a['name']} | {a['criticality']} | {a['strategy']} | {a.get('target_service', '')} "
                     f"| {a['effort']} | {a['risk']} | {wave_of.get(a['id'], '')} | {a['why']} |")
    lines += ["", "## Vagues", ""]
    for i, wave in enumerate(plan):
        lines.append(f"- **V{i + 1}** : " + ", ".join(f"{a['id']} {a['name']} ({a['strategy']}, {a['effort']})"
                                                     for a in wave))
    blockers = [(a["id"], b) for a in apps for b in a.get("blockers", [])]
    if blockers or warnings:
        lines += ["", "## Points d'attention", ""]
        lines += [f"- {app_id} : {b}" for app_id, b in blockers]
        lines += [f"- {w}" for w in warnings]
    outputs = []
    md = out_dir / f"{stem}.md"
    md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    outputs.append(str(md))
    path = out_dir / f"{stem}.csv"
    with open(path, "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id", "application", "criticite", "strategie", "cible", "effort", "risque", "vague", "pourquoi"])
        for a in apps:
            writer.writerow([a["id"], a["name"], a["criticality"], a["strategy"], a.get("target_service", ""),
                             a["effort"], a["risk"], wave_of.get(a["id"], ""), a["why"]])
    outputs.append(str(path))
    path = out_dir / f"{stem}.waves.json"
    data = {"title": spec["title"], "source": f"{stem}.json",
            "waves": [{"id": f"V{i + 1}", "applications": [{k: a[k] for k in ("id", "name", "strategy", "effort")}
                                                            for a in wave]} for i, wave in enumerate(plan)]}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    outputs.append(str(path))
    return outputs


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description MIGRATION.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--max-per-wave", type=int, default=0, help="nombre maximal d'applications par vague")
    parser.add_argument("--today", help="date du jour pour les fins de support (défaut : aujourd'hui)")
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
    report = {"input": str(args.spec), "outputs": [], "applications": 0, "strategies": {}, "waves": 0,
              "errors": errors, "warnings": warnings}
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError:
        errors.append(f"--today : date invalide « {args.today} » (AAAA-MM-JJ)")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        spec = None
    if spec is not None:
        # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
        errors += validate(spec, __file__)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    check(spec, args.spec.resolve().parent, today, errors, warnings)
    report["applications"] = len(spec["applications"])
    report["strategies"] = {s: n for s in STRATEGIES if (n := sum(a["strategy"] == s for a in spec["applications"]))}
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    plan = waves(spec, args.max_per_wave)
    report["waves"] = len(plan)
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    report["outputs"] = write(spec, plan, out_dir, args.spec.name.removesuffix(".json"), warnings)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
