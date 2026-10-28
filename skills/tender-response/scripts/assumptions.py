# /// script
# requires-python = ">=3.10"
# ///
"""Tient le registre des hypothèses, exclusions, prérequis et questions au client d'une réponse.

Entrée : `registre.json`, une entrée par hypothèse (HYP-), exclusion (EXC-),
prérequis (PRE-) ou question au client (QUE-), avec ses références aux
exigences (exigences.json) et aux éléments du dépouillement (ao.json). Le
script, et non le modèle :
- vérifie la nature de chaque entrée d'après son préfixe, les doublons, et
  que chaque référence existe ;
- exige la réponse d'une question répondue ;
- compte les questions à envoyer avant la date limite des questions du
  dépouillement, et signale une date passée ou proche ;
- écrit `questions-client.md` (questions à envoyer, numérotées, avec la date
  limite) et `<nom>.md` / `<nom>.csv` (hypothèses, exclusions, prérequis et
  réponses reçues, à reprendre dans l'offre).

    uv run scripts/assumptions.py registre.json [--out-dir DOSSIER] [--today AAAA-MM-JJ] | --schema

Avec --draft, le script écrit d'abord le registre (jamais par-dessus un
fichier existant) depuis les livrables du dossier : questions ouvertes
d'exigences.json, hypothèses et exclusions de chiffrage.json, hypothèses et
questions du journal (workflow.json). Le modèle complète, reformule pour le
client et tranche.

    uv run scripts/assumptions.py registre.json --draft
"""

import argparse
import csv
import difflib
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402

KINDS = {"HYP": "hypothese", "EXC": "exclusion", "PRE": "prerequis", "QUE": "question"}
TITLES = {"hypothese": "Hypothèses", "exclusion": "Exclusions", "prerequis": "Prérequis"}
CLOSE_DAYS = 5


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return re.sub(r"\s+", " ", "".join(c for c in text if not unicodedata.combining(c)).lower()).strip(" .;")


def read(path: Path) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) else None


def draft(path: Path) -> dict:
    errors: list[str] = []
    report = {"input": str(path), "outputs": [], "items": 0, "origins": {}, "errors": errors, "warnings": []}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas un registre")
        return report
    base = path.parent
    items, seen, numbers = [], set(), {k: 0 for k in KINDS}

    def add(prefix: str, text: str, origin: str, refs: list[str] | None = None, impact: str | None = None) -> None:
        key = normalize(text)
        if not key or key in seen:
            return
        seen.add(key)
        numbers[prefix] += 1
        item = {"id": f"{prefix}-{numbers[prefix]:02d}", "kind": KINDS[prefix], "text": text.strip()}
        if refs:
            item["refs"] = refs
        if impact:
            item["impact"] = impact
        if prefix == "QUE":
            item["status"] = "a-envoyer"
        item["origin"] = origin
        items.append(item)
        source = origin.split(" ")[0].removesuffix(".json")
        report["origins"][source] = report["origins"].get(source, 0) + 1

    catalog = read(base / "exigences.json") or {}
    for req in catalog.get("requirements", []):
        for question in req.get("questions", []):
            add("QUE", question, "exigences.json", [req["id"]], "solution")
    estimate = read(base / "chiffrage.json") or {}
    for text in estimate.get("assumptions", []):
        add("HYP", text, "chiffrage.json", impact="chiffrage")
    for text in estimate.get("exclusions", []):
        add("EXC", text, "chiffrage.json", impact="chiffrage")
    journal = read(base / "workflow.json") or {}
    for entry in journal.get("entries", []):
        if entry.get("kind") in ("hypothese", "question"):
            add("HYP" if entry["kind"] == "hypothese" else "QUE", entry["text"], f"journal {entry['id']}",
                [r for r in entry.get("refs", []) if isinstance(r, str)] or None)
    if not items:
        report["warnings"].append("aucune hypothèse, exclusion ni question trouvée dans exigences.json, "
                                  "chiffrage.json et workflow.json : registre à écrire")
    spec = {"title": "Hypothèses, exclusions, prérequis et questions",
            **{field: name for field, name in (("tender", "ao.json"), ("requirements", "exigences.json"))
               if (base / name).exists()}, "items": items,
            "_draft": "Brouillon d'assumptions.py --draft. Reformuler chaque question pour le client, ajouter les "
                      "prérequis (accès, données, interlocuteurs) et les questions sur les clauses à risque du "
                      "dépouillement, retirer les doublons."}
    invalid = validate(spec, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], items=len(items))
    return report


TENDER_ID = re.compile(r"^[DCPFR]-[0-9]+$")


def known_refs(base: Path, spec: dict, warnings: list[str]) -> dict[bool, set[str] | None]:
    """Identifiants connus, par source : éléments du dépouillement (True), exigences (False) ; None si absente."""
    known: dict[bool, set[str] | None] = {}
    for tender, field, name in ((False, "requirements", "exigences.json"), (True, "tender", "ao.json")):
        path = base / spec.get(field, name)
        data = read(path)
        if data is None:
            known[tender] = None
            if field in spec:
                warnings.append(f"{field} : {path.name} illisible ou absent, références non vérifiées")
            continue
        ids = {r["id"] for r in data.get("requirements", []) if isinstance(r, dict) and "id" in r}
        for key in ("dates", "criteria", "pieces", "format", "clauses"):
            ids |= {i["id"] for i in data.get(key, []) if isinstance(i, dict) and "id" in i}
        known[tender] = ids
    return known


def deadline(base: Path, spec: dict) -> dict | None:
    data = read(base / spec.get("tender", "ao.json")) or {}
    dated = [d for d in data.get("dates", []) if isinstance(d, dict) and d.get("kind") == "questions"]
    if not dated:
        return None
    try:
        return {"date": dated[0]["date"], "time": dated[0].get("time"), "_date": date.fromisoformat(dated[0]["date"])}
    except (KeyError, ValueError):
        return None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="registre registre.json")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui du .json)")
    parser.add_argument("--today", help="date du jour pour le temps restant (AAAA-MM-JJ, défaut : aujourd'hui)")
    parser.add_argument("--draft", action="store_true", help="écrire le brouillon depuis les livrables du dossier")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON du registre sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("registre JSON attendu")
    if args.draft:
        report = draft(args.spec)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.spec), "outputs": [], "counts": {k: 0 for k in KINDS.values()},
              "questions": {"a-envoyer": 0, "envoyee": 0, "repondue": 0, "sans-reponse": 0}, "deadline": None,
              "errors": errors, "warnings": warnings}
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    errors += validate(spec, __file__)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    base = args.spec.resolve().parent
    known = known_refs(base, spec, warnings)
    ids = set()
    for index, item in enumerate(spec["items"]):
        at = f"items/{index} ({item['id']})"
        kind = KINDS[item["id"].split("-")[0]]
        if item["id"] in ids:
            errors.append(f"{at} : identifiant en double")
        ids.add(item["id"])
        if item["kind"] != kind:
            errors.append(f"{at} : nature {item['kind']} pour un identifiant {item['id'].split('-')[0]}- ({kind})")
        if kind != "question" and (item.get("status") or item.get("answer")):
            errors.append(f"{at} : status et answer ne valent que pour une question")
        if kind == "question":
            status = item.get("status", "a-envoyer")
            if status == "repondue" and not item.get("answer", "").strip():
                errors.append(f"{at} : question répondue sans answer")
            if item.get("answer") and status != "repondue":
                warnings.append(f"{at} : answer présente, status {status} au lieu de repondue")
            report["questions"][status] += 1
        for ref in item.get("refs", []):
            pool = known[bool(TENDER_ID.match(ref))]
            if pool is not None and ref not in pool:
                close = difflib.get_close_matches(ref, sorted(pool), n=1, cutoff=0.6)
                errors.append(f"{at} : référence inconnue « {ref} »" + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
        report["counts"][kind] += 1
    limit = deadline(base, spec)
    to_send = report["questions"]["a-envoyer"]
    if limit:
        left = (limit["_date"] - today).days
        report["deadline"] = {"date": limit["date"], "days_left": left}
        if to_send and left < 0:
            warnings.append(f"{to_send} question(s) à envoyer, date limite des questions passée ({limit['date']}) : "
                            "les passer en hypothèses")
        elif to_send and left < CLOSE_DAYS:
            warnings.append(f"{to_send} question(s) à envoyer avant le {limit['date']}, dans {left} jour(s)")
    elif to_send:
        warnings.append("date limite des questions inconnue (aucune date questions dans ao.json)")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    out_dir = args.out_dir or base
    out_dir.mkdir(parents=True, exist_ok=True)
    items = spec["items"]
    refs = lambda i: f" ({', '.join(i['refs'])})" if i.get("refs") else ""  # noqa: E731
    open_questions = [i for i in items if i["kind"] == "question" and i.get("status", "a-envoyer") in ("a-envoyer", "envoyee")]
    when = f" avant le {limit['date']}" + (f" à {limit['time']}" if limit and limit.get("time") else "") if limit else ""
    questions_md = out_dir / "questions-client.md"
    lines = ["# Questions au client", "", f"Fichier généré par `assumptions.py` depuis `{args.spec.name}`. "
             f"{len(open_questions)} question(s) à poser{when}.", ""]
    lines += [f"{n}. {i['text']}{refs(i)}" + (" *(envoyée)*" if i.get("status") == "envoyee" else "")
              for n, i in enumerate(open_questions, 1)] or ["Aucune question en attente."]
    questions_md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    register_md = out_dir / f"{args.spec.stem}.md"
    lines = [f"# {spec.get('title') or 'Hypothèses, exclusions et prérequis'}", "",
             f"Fichier généré par `assumptions.py` depuis `{args.spec.name}`, qui fait foi : à reprendre dans l'offre."]
    for kind, title in TITLES.items():
        chosen = [i for i in items if i["kind"] == kind]
        if chosen:
            lines += ["", f"## {title}", ""] + [f"- **{i['id']}** {i['text']}{refs(i)}" for i in chosen]
    answered = [i for i in items if i["kind"] == "question" and i.get("status") == "repondue"]
    if answered:
        lines += ["", "## Réponses du client", ""] + [f"- **{i['id']}** {i['text']} Réponse : {i['answer']}"
                                                      for i in answered]
    unanswered = [i for i in items if i["kind"] == "question" and i.get("status") == "sans-reponse"]
    if unanswered:
        lines += ["", "## Questions restées sans réponse", ""] + [f"- **{i['id']}** {i['text']}{refs(i)}"
                                                                  for i in unanswered]
    register_md.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    register_csv = out_dir / f"{args.spec.stem}.csv"
    with open(register_csv, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id", "nature", "texte", "references", "impact", "statut", "reponse", "origine"])
        for i in items:
            writer.writerow([i["id"], i["kind"], i["text"], " ".join(i.get("refs", [])), i.get("impact", ""),
                             i.get("status", "a-envoyer" if i["kind"] == "question" else ""), i.get("answer", ""),
                             i.get("origin", "")])
    # Relecture : chaque entrée figure dans le CSV.
    with open(register_csv, encoding="utf-8-sig", newline="") as handle:
        written = {row[0] for row in csv.reader(handle, delimiter=";")}
    if not ids <= written:
        errors.append(f"{register_csv.name} incomplet : {', '.join(sorted(ids - written)[:5])}")
    report["outputs"] = [str(questions_md), str(register_md), str(register_csv)]
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
