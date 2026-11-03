# /// script
# requires-python = ">=3.10"
# ///
"""Écrit le compte rendu d'une réunion (atelier, kick-off, comité) depuis une description JSON courte et le contrôle.

Le modèle lit la transcription (doc-to-markdown, vidéo ou notes) et ne décrit
que ce qui demande du jugement : participants, décisions, actions,
questions ouvertes, exigences entendues, chacune avec sa citation exacte. Le
script, et non le modèle :

- vérifie identifiants uniques (D-, A-, Q-, X-), dates (échéance pas avant la
  réunion), porteur d'action parmi les participants ;
- retrouve chaque citation dans la transcription (casse, accents et espaces
  ignorés) : une citation introuvable est une erreur, une décision sans
  citation un avertissement ;
- écrit <nom>.md (compte rendu daté, prêt pour sources/ de
  requirements-catalog et pour le vault) et <nom>.actions.csv (séparateur ;,
  importable dans Jira ou Azure DevOps), puis relit le CSV.

    uv run scripts/notes_build.py CR.json [--out CHEMIN.md] | --schema
"""

import argparse
import csv
import datetime
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, read_spec  # noqa: E402

KINDS = {"atelier": "Atelier", "kick-off": "Réunion de lancement", "comite": "Comité", "point": "Point d'avancement",
         "entretien": "Entretien", "soutenance": "Soutenance"}
PREFIX = {"decisions": "D-", "actions": "A-", "questions": "Q-", "requirements": "X-"}


def plain(text: str) -> str:
    """Texte comparable : sans accents, casse, ponctuation ni espaces répétés."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", text))


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def markdown(spec: dict) -> str:
    date = datetime.date.fromisoformat(spec["date"])
    lines = [f"# {spec['title']}", "",
             f"{KINDS[spec['kind']]} du {date.strftime('%d/%m/%Y')}"
             + (f", source : `{spec['source']}`" if spec.get("source") else "") + ".", ""]
    present = [p for p in spec["participants"] if p.get("present", True)]
    absent = [p for p in spec["participants"] if not p.get("present", True)]
    who = lambda p: p["name"] + (f" ({', '.join(x for x in (p.get('role'), p.get('org')) if x)})"
                                  if p.get("role") or p.get("org") else "")
    lines += ["## Participants", "", *[f"- {who(p)}" for p in present]]
    if absent:
        lines += ["", "Excusés : " + ", ".join(who(p) for p in absent) + "."]
    if spec.get("agenda"):
        lines += ["", "## Ordre du jour", "", *[f"{i}. {item}" for i, item in enumerate(spec["agenda"], 1)]]
    if spec.get("summary"):
        lines += ["", "## Synthèse", "", spec["summary"]]
    sections = [("decisions", "Décisions", ["Id", "Décision", "Références"]),
                ("actions", "Actions", ["Id", "Action", "Porteur", "Échéance"]),
                ("questions", "Questions ouvertes", ["Id", "Question", "À qui"]),
                ("requirements", "Exigences entendues", ["Id", "Exigence", "Citation"])]
    for key, title, head in sections:
        items = spec.get(key, [])
        if not items:
            continue
        lines += ["", f"## {title}", "", "| " + " | ".join(head) + " |", "|" + " --- |" * len(head)]
        for it in items:
            row = {"decisions": lambda: [it["id"], it["text"], ", ".join(it.get("refs", [])) or "-"],
                   "actions": lambda: [it["id"], it["text"], it["owner"], it.get("due", "-")],
                   "questions": lambda: [it["id"], it["text"], it.get("to", "-")],
                   "requirements": lambda: [it["id"], it["text"], f"« {it['quote']} »"]}[key]()
            lines.append("| " + " | ".join(cell(c) for c in row) + " |")
    quoted = [it for key in ("decisions", "actions") for it in spec.get(key, []) if it.get("quote")]
    if quoted:
        lines += ["", "## Citations", "", *[f"- **{it['id']}** : « {it['quote']} »" for it in quoted]]
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description CR.json")
    parser.add_argument("--out", type=Path, help="compte rendu Markdown (défaut : <description>.md)")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma de la description sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.spec), "outputs": [], "decisions": 0, "actions": 0, "questions": 0,
              "requirements": 0, "quotes_checked": 0, "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.spec:
        errors.append("description CR.json attendue")
        return done(1)
    spec, invalid = read_spec(args.spec, __file__)
    errors += invalid
    if spec is None:
        return done(1)
    if errors:
        return done(1)
    day = datetime.date.fromisoformat(spec["date"])
    names = {plain(p["name"]) for p in spec["participants"]}
    seen: set[str] = set()
    for key, prefix in PREFIX.items():
        for i, it in enumerate(spec.get(key, [])):
            if not it["id"].startswith(prefix):
                errors.append(f"{key}/{i}/id : « {it['id']} » attendu sous la forme {prefix}1")
            if it["id"] in seen:
                errors.append(f"{key}/{i}/id : « {it['id']} » en double")
            seen.add(it["id"])
    for i, act in enumerate(spec.get("actions", [])):
        if act.get("due") and datetime.date.fromisoformat(act["due"]) < day:
            errors.append(f"actions/{i}/due : {act['due']} avant la réunion du {spec['date']}")
        if plain(act["owner"]) not in names:
            warnings.append(f"actions/{i}/owner : « {act['owner']} » absent des participants (porteur externe ?)")
        if not act.get("due"):
            warnings.append(f"actions/{i} ({act['id']}) : sans échéance")
    transcript = None
    if spec.get("source"):
        path = (args.spec.parent / spec["source"])
        try:
            transcript = plain(path.read_text(encoding="utf-8"))
        except OSError as error:
            errors.append(f"source : {path} illisible ({error})")
    for key in ("decisions", "actions", "requirements"):
        for i, it in enumerate(spec.get(key, [])):
            if not it.get("quote"):
                if key == "decisions" and transcript is not None:
                    warnings.append(f"decisions/{i} ({it['id']}) : sans citation de la transcription")
                continue
            if transcript is None:
                warnings.append(f"{key}/{i} ({it['id']}) : citation non vérifiée, pas de source")
                continue
            report["quotes_checked"] += 1
            if plain(it["quote"]) not in transcript:
                errors.append(f"{key}/{i}/quote ({it['id']}) : citation introuvable dans {spec['source']} : "
                              f"« {it['quote'][:80]} » (recopiez-la mot pour mot)")
    if errors:
        return done(1)
    out = args.out or args.spec.with_suffix(".md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(markdown(spec), encoding="utf-8")
    actions_csv = out.with_suffix(".actions.csv")
    rows = [["id", "action", "porteur", "echeance", "references"]] + \
           [[a["id"], a["text"], a["owner"], a.get("due", ""), ",".join(a.get("refs", []))]
            for a in spec.get("actions", [])]
    with actions_csv.open("w", encoding="utf-8", newline="") as handle:
        csv.writer(handle, delimiter=";").writerows(rows)
    with actions_csv.open(encoding="utf-8", newline="") as handle:
        if list(csv.reader(handle, delimiter=";")) != rows:
            errors.append(f"{actions_csv.name} : relecture différente des actions écrites")
    report.update(outputs=[str(out), str(actions_csv)], decisions=len(spec.get("decisions", [])),
                  actions=len(spec.get("actions", [])), questions=len(spec.get("questions", [])),
                  requirements=len(spec.get("requirements", [])))
    return done(1 if errors else 0)


if __name__ == "__main__":
    sys.exit(main())
