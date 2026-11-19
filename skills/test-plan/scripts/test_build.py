# /// script
# requires-python = ">=3.10"
# ///
"""Écrit et contrôle le plan de recette tiré du catalogue d'exigences : cas de test, couverture et lots de recette.

Le modèle décrit les cas (titre, exigences couvertes, type, priorité, étapes,
résultat attendu) ; avec --draft, le script en écrit d'abord l'ébauche, un
cas par exigence retenue (type tiré de la catégorie, résultat attendu tiré
du texte et de la mesure). Le script, et non le modèle :

- vérifie identifiants (T-1...), exigences citées présentes dans
  exigences.json, exigence indispensable couverte par au moins un cas (erreur
  sinon), exigence importante non couverte (avertie) ;
- vérifie qu'une exigence non fonctionnelle mesurée (metric) a un cas du bon
  type dont le résultat attendu reprend sa mesure (averti sinon) ;
- calcule la charge de recette à trois points (conception par cas,
  exécution par campagne, automatisation des cas automatisés) avec des
  abaques par défaut ou propres (rules) ;
- écrit <nom>.md (cas, matrice exigences × cas, non couvertes),
  <nom>.csv (import Xray, TestRail ou Azure Test Plans, séparateur ;) et
  <nom>.lots.json (lots de recette au format de solution-estimate), relit le
  CSV et contrôle les lots contre le schéma du chiffrage.

    uv run scripts/test_build.py PLAN.json [--out-dir DOSSIER] | --schema
    uv run scripts/test_build.py PLAN.json --draft --requirements exigences.json
"""

import argparse
import csv
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402
from text_tools import beside, cell, from_data  # noqa: E402

KIND_OF = {"performance": "performance", "disponibilite": "exploitation", "securite": "securite",
           "conformite": "securite", "exploitabilite": "exploitation", "utilisabilite": "accessibilite",
           "interoperabilite": "integration", "portabilite": "exploitation", "evolutivite": "performance"}
DEFAULT_RULES = {
    "profile": "testeur", "campaigns": 2,
    # Jours par cas : conception et exécution d'une campagne, [mini, probable, maxi].
    "design": {"fonctionnel": [0.1, 0.2, 0.3], "integration": [0.2, 0.3, 0.5], "bout-en-bout": [0.3, 0.5, 0.8],
               "performance": [1, 2, 3], "securite": [0.5, 1, 2], "accessibilite": [0.2, 0.3, 0.5],
               "reprise": [0.5, 1, 1.5], "exploitation": [0.3, 0.5, 1]},
    "run": {"fonctionnel": [0.05, 0.1, 0.15], "integration": [0.1, 0.15, 0.25], "bout-en-bout": [0.15, 0.25, 0.4],
            "performance": [0.5, 1, 1.5], "securite": [0.3, 0.5, 1], "accessibilite": [0.1, 0.2, 0.3],
            "reprise": [0.3, 0.5, 1], "exploitation": [0.2, 0.3, 0.5]},
    "automation": [0.2, 0.3, 0.5],
}
PHASE = "tests"


def rel(target: Path, base: Path) -> str:
    return Path(os.path.relpath(target.resolve(), base.resolve())).as_posix()


def load_requirements(path: Path, errors: list[str]) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {r["id"]: r for r in data["requirements"] if r.get("status") != "retiree"}
    except (OSError, ValueError, KeyError, TypeError) as error:
        errors.append(f"exigences : {path} illisible ({error})")
        return None


def draft(req_path: Path, plan_path: Path, errors: list[str]) -> dict | None:
    reqs = load_requirements(req_path, errors)
    if reqs is None:
        return None
    cases = []
    for rid, r in reqs.items():
        if r.get("priority") == "hors-perimetre":
            continue
        kind = "fonctionnel" if rid.startswith("EF") else KIND_OF.get(r.get("category", ""), "exploitation")
        expected = r.get("text", r.get("title", rid))
        if r.get("metric"):
            expected = f"{expected} Mesure attendue : {r['metric']}."
        cases.append({"id": f"T-{len(cases) + 1}", "title": f"Vérifier : {r.get('title', rid)}"[:200], "refs": [rid],
                      "kind": kind, "priority": {"indispensable": "haute", "importante": "moyenne"}.get(
                          r.get("priority"), "basse"),
                      "steps": ["à décrire"], "expected": expected[:600]})
    return {"title": f"Plan de recette : {plan_path.stem}", "requirements": rel(req_path, plan_path.parent),
            "cases": cases}


def plain(text: str) -> str:
    return " ".join(text.lower().replace("\u202f", " ").replace("\xa0", " ").split())


def lots(spec: dict, rules: dict) -> dict:
    kinds: dict[str, int] = {}
    for c in spec["cases"]:
        kinds[c["kind"]] = kinds.get(c["kind"], 0) + 1
    work, profile, n = [], rules["profile"], rules["campaigns"]
    for kind, count in sorted(kinds.items()):
        work.append({"id": f"R{len(work) + 1}", "name": f"Conception des cas de test {kind} ({count})", "phase": PHASE,
                     "effort": {profile: [round(v * count, 2) for v in rules["design"][kind]]},
                     "note": f"{count} cas ; abaque design {kind}"})
        work.append({"id": f"R{len(work) + 1}", "name": f"Exécution des cas {kind} : {n} campagne(s)", "phase": PHASE,
                     "effort": {profile: [round(v * count * n, 2) for v in rules["run"][kind]]},
                     "note": f"{count} cas x {n} campagne(s) ; abaque run {kind}"})
    auto = sum(1 for c in spec["cases"] if c.get("automated"))
    if auto:
        work.append({"id": f"R{len(work) + 1}", "name": f"Automatisation de {auto} cas", "phase": PHASE,
                     "effort": {profile: [round(v * auto, 2) for v in rules["automation"]]},
                     "note": f"{auto} cas automatisés ; abaque automation"})
    return {"domain": "recette", "profile": profile, "work": work}


def markdown(spec: dict, reqs: dict, coverage: dict, uncovered: list[str], total: list[float]) -> str:
    lines = [f"# {spec['title']}", "", f"{len(spec['cases'])} cas de test ; charge de recette "
             f"{total[0]:g} / {total[1]:g} / {total[2]:g} jours (mini, probable, maxi).", "",
             "## Cas de test", "", "| Id | Cas | Type | Priorité | Exigences | Résultat attendu |",
             "| --- | --- | --- | --- | --- | --- |"]
    lines += [f"| {c['id']} | {cell(c['title'])} | {c['kind']} | {c['priority']} | {', '.join(c['refs'])} | "
              f"{cell(c['expected'])} |" for c in spec["cases"]]
    lines += ["", "## Couverture des exigences", "", "| Exigence | Priorité | Cas |", "| --- | --- | --- |"]
    lines += [f"| {rid} {cell(r.get('title', ''))} | {r.get('priority', '-')} | {', '.join(coverage.get(rid, [])) or '**aucun**'} |"
              for rid, r in reqs.items() if r.get("priority") != "hors-perimetre"]
    if uncovered:
        lines += ["", "Exigences non couvertes : " + ", ".join(uncovered) + "."]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("plan", type=Path, nargs="?", help="description PLAN.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du plan)")
    parser.add_argument("--draft", action="store_true", help="écrit l'ébauche du plan depuis les exigences")
    parser.add_argument("--requirements", type=Path, help="exigences.json, pour --draft")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma du plan sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.plan), "outputs": [], "cases": 0, "covered": 0, "uncovered": [], "days": [],
              "draft": bool(args.draft), "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.plan:
        errors.append("description PLAN.json attendue")
        return done(1)
    if args.draft:
        if args.plan.exists():
            errors.append(f"{args.plan} existe déjà : l'ébauche n'écrit jamais par-dessus un plan")
        elif not args.requirements:
            errors.append("--draft demande --requirements exigences.json")
        else:
            spec = draft(args.requirements, args.plan, errors)
            if spec is not None:
                errors += validate(spec, __file__)
            if not errors:
                args.plan.parent.mkdir(parents=True, exist_ok=True)
                args.plan.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
                report.update(outputs=[str(args.plan)], cases=len(spec["cases"]))
                warnings.append("ébauche : étapes, données et résultats attendus à écrire cas par cas")
        return done(1 if errors else 0)
    try:
        spec = json.loads(args.plan.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{args.plan} illisible ({error})")
        return done(1)
    errors += validate(spec, __file__)
    if errors:
        return done(1)
    rules = {**DEFAULT_RULES, **{k: ({**DEFAULT_RULES[k], **v} if isinstance(v, dict) else v)
                                 for k, v in spec.get("rules", {}).items()}}
    reqs = load_requirements(from_data(args.plan.parent, spec["requirements"]), errors)
    if reqs is None:
        return done(1)
    ids, coverage = set(), {}
    for i, c in enumerate(spec["cases"]):
        if c["id"] in ids:
            errors.append(f"cases/{i}/id : « {c['id']} » en double")
        ids.add(c["id"])
        for ref in c["refs"]:
            if ref not in reqs:
                errors.append(f"cases/{i}/refs ({c['id']}) : exigence « {ref} » absente de {spec['requirements']}")
            coverage.setdefault(ref, []).append(c["id"])
    todo = [c["id"] for c in spec["cases"] if c["steps"] == ["à décrire"]]
    if todo:
        warnings.append(f"étapes à décrire : {', '.join(todo)}")
    uncovered = [rid for rid, r in reqs.items() if rid not in coverage and r.get("priority") != "hors-perimetre"]
    for rid in uncovered:
        (errors if reqs[rid].get("priority") == "indispensable" else warnings).append(
            f"exigence {reqs[rid].get('priority', '')} {rid} couverte par aucun cas".replace("  ", " "))
    for rid, r in reqs.items():
        if r.get("metric") and rid in coverage:
            mine = [c for c in spec["cases"] if rid in c["refs"]]
            if not any(plain(r["metric"]) in plain(c["expected"]) for c in mine):
                warnings.append(f"{rid} : aucun cas ne reprend sa mesure « {r['metric']} » dans son résultat attendu")
    if errors:
        return done(1)
    plan_lots = lots(spec, rules)
    estimate = schema_of("solution-estimate", "estimate_build.py")
    if estimate is None:
        warnings.append(f"lots non contrôlés : {absent('solution-estimate', 'estimate_build.py')}")
    else:
        item = {**estimate["properties"]["work"]["items"], "$defs": estimate.get("$defs", {})}
        for w in plan_lots["work"]:
            errors += [f"lots/{w['id']} : {e}" for e in check(w, item)]
    if errors:
        return done(1)
    total = [round(sum(w["effort"][rules["profile"]][i] for w in plan_lots["work"]), 2) for i in range(3)]
    out_dir = args.out_dir or args.plan.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.plan.name.removesuffix(".json")
    md, csv_path, lots_path = beside(out_dir / f"{stem}.md"), out_dir / f"{stem}.csv", out_dir / f"{stem}.lots.json"
    md.write_text(markdown(spec, reqs, coverage, uncovered, total), encoding="utf-8")
    rows = [["id", "titre", "type", "priorite", "preconditions", "etapes", "resultat_attendu", "exigences", "automatise"]]
    rows += [[c["id"], c["title"], c["kind"], c["priority"], c.get("preconditions", ""), " / ".join(c["steps"]),
              c["expected"], ",".join(c["refs"]), "oui" if c.get("automated") else "non"] for c in spec["cases"]]
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    with csv_path.open(encoding="utf-8", newline="") as handle:
        if list(csv.reader(handle, delimiter=";")) != rows:
            errors.append(f"{csv_path.name} : relecture différente des cas écrits")
    plan_lots["source"] = [str(args.plan)]
    lots_path.write_text(json.dumps(plan_lots, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    if rules is DEFAULT_RULES or not spec.get("rules"):
        warnings.append("abaques de recette par défaut, à calibrer (rules)")
    report.update(outputs=[str(md), str(csv_path), str(lots_path)], cases=len(spec["cases"]),
                  covered=len([r for r in reqs if r in coverage]), uncovered=uncovered, days=total)
    return done(1 if errors else 0)


if __name__ == "__main__":
    sys.exit(main())
