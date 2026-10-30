# /// script
# requires-python = ">=3.10"
# ///
"""Qualifie un appel d'offres (go / no-go) sur une grille pondérée : note et recommandation calculées.

Entrée : `qualification.json`, une note de 0 à 5 et sa raison par critère de
la grille (`references/grille-qualification.json`, ou celle de `grid`).
Le script, et non le modèle :
- valide la grille et exige une note justifiée pour chacun de ses critères ;
- calcule la note sur 100 (moyenne pondérée) et la recommandation : go,
  go-conditions ou no-go selon les seuils de la grille, no-go si un critère
  éliminatoire a 1 ou moins ;
- exige la raison d'une décision qui s'écarte de la recommandation ;
- avec --log ETAPE, trace la décision au journal du workflow du dossier
  (journal.py log du skill decision-log) ;
- écrit `<nom>.md` : grille notée, note, recommandation, décision.

    uv run scripts/qualify.py qualification.json [--out-dir DOSSIER] [--log ETAPE] [--today AAAA-MM-JJ] | --schema

Avec --draft, le script écrit d'abord la description (jamais par-dessus un
fichier existant) : un critère par ligne de la grille, sans note, avec ce que
le dépouillement (ao.json) en dit (jours avant la remise, clauses à risque,
pièces, critères de notation). Le modèle note et justifie.

    uv run scripts/qualify.py qualification.json --draft [--today AAAA-MM-JJ]
"""

import argparse
import difflib
import json
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from skill_paths import absent, run_script  # noqa: E402
from spec_schema import check, input_schema, print_schema, validate  # noqa: E402

GRID = Path(__file__).resolve().parent.parent / "references" / "grille-qualification.json"
CHOICES = {"go": "Go", "go-conditions": "Go sous conditions", "no-go": "No-go"}
ELIMINATORY = 1  # note à partir de laquelle (et en dessous) un critère éliminatoire écarte l'affaire


def read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def load_grid(base: Path, spec: dict, errors: list[str]) -> dict | None:
    path = base / spec["grid"] if spec.get("grid") else GRID
    grid = read(path)
    if grid is None:
        errors.append(f"grid : grille illisible {path}")
        return None
    schema = input_schema(__file__)
    invalid = check(grid, schema["$defs"]["grid"], schema)
    ids = [c["id"] for c in grid.get("criteria", []) if isinstance(c, dict) and "id" in c]
    invalid += [f"criteria : identifiant en double « {i} »" for i in sorted({i for i in ids if ids.count(i) > 1})]
    if invalid:
        errors.extend(f"grid : {path.name} : {e}" for e in invalid)
        return None
    return grid


def hints(tender: dict | None, today: date) -> dict[str, str]:
    """Ce que le dépouillement dit de chaque indice de la grille (hint)."""
    if not tender:
        return {}
    said = {}
    remise = next((d for d in tender.get("dates", []) if d.get("kind") == "remise"), None)
    if remise:
        try:
            said["remise"] = f"remise le {remise['date']}, dans {(date.fromisoformat(remise['date']) - today).days} jours"
        except ValueError:
            pass
    clauses = tender.get("clauses", [])
    if clauses:
        levels = {lvl: sum(1 for c in clauses if c.get("level") == lvl) for lvl in ("haute", "moyenne", "basse")}
        said["clauses"] = (f"clauses à risque : {levels['haute']} haut, {levels['moyenne']} moyen, {levels['basse']} bas ("
                           + ", ".join(sorted({c.get('topic', '?') for c in clauses})) + ")")
    pieces = tender.get("pieces", [])
    if pieces:
        said["pieces"] = f"{len(pieces)} pièces à fournir : " + " ; ".join(p.get("label", "") for p in pieces)[:300]
    criteria = tender.get("criteria", [])
    if criteria:
        said["criteres"] = "critères notés : " + " ; ".join(f"{c.get('label')} ({c.get('weight')})" for c in criteria)[:300]
    return said


def draft(path: Path, today: date) -> dict:
    errors: list[str] = []
    report = {"input": str(path), "outputs": [], "criteria": 0, "hints": 0, "errors": errors, "warnings": []}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une qualification")
        return report
    grid = load_grid(path.parent, {}, errors)
    if not grid:
        return report
    tender = read(path.parent / "ao.json")
    said = hints(tender, today)
    scores = []
    for c in grid["criteria"]:
        item = {"id": c["id"]}
        if said.get(c.get("hint", "")):
            item["hint"] = said[c["hint"]]
        scores.append(item)
    spec = {"title": "Qualification go / no-go", **({"tender": "ao.json"} if tender else {}), "scores": scores,
            "_draft": "Brouillon de qualify.py --draft : donner à chaque critère score (0 à 5, 5 le plus favorable) et "
                      "why ; la décision (decision) est celle de l'utilisateur, avec ses mots."}
    invalid = validate(spec, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], criteria=len(scores), hints=sum(1 for s in scores if "hint" in s))
    if not tender:
        report["warnings"].append("ao.json absent : aucun indice tiré du dépouillement")
    return report


def fmt(value: float) -> str:
    return f"{value:.1f}".replace(".", ",").removesuffix(",0")


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description qualification.json")
    parser.add_argument("--out-dir", type=Path, help="dossier de <nom>.md (défaut : celui du .json)")
    parser.add_argument("--log", metavar="ETAPE",
                        help="trace la décision au journal du workflow du dossier, à cette étape (decision-log)")
    parser.add_argument("--today", help="date du jour pour les indices (AAAA-MM-JJ, défaut : aujourd'hui)")
    parser.add_argument("--draft", action="store_true", help="écrire le brouillon : un critère par ligne de la grille")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
    except ValueError as error:
        print(json.dumps({"input": str(args.spec), "errors": [f"--today : {error}"], "warnings": []}, ensure_ascii=False))
        return 1
    if args.draft:
        report = draft(args.spec, today)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.spec), "output": None, "total": None, "recommendation": None, "eliminatory": [],
              "decision": None, "logged": None, "errors": errors, "warnings": warnings}
    spec = read(args.spec)
    if spec is None:
        errors.append(f"{args.spec} illisible")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    errors += validate(spec, __file__)
    base = args.spec.resolve().parent
    grid = load_grid(base, spec, errors) if not errors else None
    if errors or not grid:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    criteria = {c["id"]: c for c in grid["criteria"]}
    scores: dict[str, dict] = {}
    for index, item in enumerate(spec["scores"]):
        at = f"scores/{index} ({item['id']})"
        if item["id"] not in criteria:
            close = difflib.get_close_matches(item["id"], list(criteria), n=1, cutoff=0.6)
            errors.append(f"{at} : critère inconnu de la grille" + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            continue
        if item["id"] in scores:
            errors.append(f"{at} : critère noté deux fois")
        if "score" not in item:
            errors.append(f"{at} : score manquant (0 à 5)")
        if not item.get("why", "").strip():
            errors.append(f"{at} : why manquant : justifiez la note")
        scores[item["id"]] = item
    missing = [cid for cid in criteria if cid not in scores]
    if missing:
        errors.append(f"critères non notés : {', '.join(missing)}")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    weights = sum(c["weight"] for c in criteria.values())
    total = round(100 * sum(c["weight"] * scores[cid]["score"] / 5 for cid, c in criteria.items()) / weights, 1)
    eliminatory = [cid for cid, c in criteria.items() if c.get("eliminatory") and scores[cid]["score"] <= ELIMINATORY]
    limits = grid["thresholds"]
    recommendation = "no-go" if eliminatory else "go" if total >= limits["go"] else \
        "go-conditions" if total >= limits["conditions"] else "no-go"
    report.update(total=total, recommendation=recommendation, eliminatory=eliminatory)
    decision = spec.get("decision")
    if decision and decision["choice"] != recommendation and not decision.get("why", "").strip():
        errors.append(f"decision : {decision['choice']} contre la recommandation {recommendation} sans why")
    if decision and decision["choice"] == "go-conditions" and not decision.get("conditions"):
        warnings.append("decision : go sous conditions sans conditions")
    if not decision:
        warnings.append("aucune décision : la recommandation est à soumettre à l'utilisateur")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    out_dir = args.out_dir or base
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{args.spec.stem}.md"
    lines = [f"# {spec.get('title') or 'Qualification go / no-go'}", "",
             f"Fichier généré par `qualify.py` depuis `{args.spec.name}`, qui fait foi. {grid.get('scale', '')}", "",
             "| Critère | Poids | Note | Points | Raison |", "| --- | --- | --- | --- | --- |"]
    for cid, c in criteria.items():
        s = scores[cid]
        mark = " (éliminatoire)" if c.get("eliminatory") else ""
        lines.append(f"| {c['label']}{mark} | {c['weight']} | {s['score']}/5 | "
                     f"{fmt(100 * c['weight'] * s['score'] / 5 / weights)} | {s['why'].replace('|', '/')} |")
    lines += ["", f"**Note : {fmt(total)} / 100.** Seuils : go à {limits['go']}, sous conditions à {limits['conditions']}.",
              "", f"**Recommandation : {CHOICES[recommendation]}.**"
              + (f" Critère éliminatoire : {', '.join(criteria[e]['label'] for e in eliminatory)}." if eliminatory else "")]
    if decision:
        lines += ["", f"**Décision : {CHOICES[decision['choice']]}**, par {decision.get('by', 'utilisateur')}"
                  + (f" : {decision['why']}" if decision.get("why") else ".")]
        lines += [f"- Condition : {c}" for c in decision.get("conditions", [])]
    ai_mark.write_text(out, "\n".join(lines) + "\n")
    report.update(output=str(out), decision=decision["choice"] if decision else None)
    if args.log and decision:
        if not (base / "workflow.json").exists():
            warnings.append("--log : aucun workflow.json dans le dossier, décision non tracée")
        else:
            text = f"Qualification : {CHOICES[decision['choice']]} (note {fmt(total)}/100, recommandation " \
                   f"{CHOICES[recommendation]})"
            logged = run_script("decision-log", "journal.py",
                                ["log", str(base), args.log, "--kind", "choix", "--by", decision.get("by", "utilisateur"),
                                 "--text", text] + (["--why", decision["why"]] if decision.get("why") else []))
            if logged.get("errors"):
                warnings.append("--log : " + "; ".join(logged["errors"])[:300])
            else:
                report["logged"] = logged.get("entry")
    elif args.log:
        warnings.append("--log : aucune décision à tracer")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
