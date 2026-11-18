# /// script
# requires-python = ">=3.10"
# ///
"""Compare deux versions d'un catalogue d'exigences : ajoutées, retirées, modifiées, contextes touchés.

Pour une évolution (demande de changement), le catalogue validé reste la
référence et sa copie de travail reçoit les changements. Le script, et non
le modèle :

- avec --start, copie la référence dans la copie de travail si elle n'existe
  pas encore, avec les documents que citent ses exigences (leurs
  citations restent vérifiables), puis s'arrête ;
- valide les deux catalogues contre le schéma de req_build.py ;
- liste les exigences ajoutées, retirées (absentes ou passées hors du
  périmètre retenu) et modifiées, champ par champ (texte, priorité, mesure,
  catégorie, nature, domaine) ;
- avec --domains (domaines.json de domain-design), donne les contextes
  bornés qui portent chaque exigence changée, et signale une exigence
  ajoutée qu'aucun contexte ne porte encore ;
- écrit l'écart en Markdown (--out).

    uv run scripts/req_diff.py REFERENCE.json COPIE.json [--start] [--schema] [--domains domaines.json] [--out ecarts.md]
"""

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, input_schema, print_schema, schema_option  # noqa: E402
from text_tools import cell, readable_dir  # noqa: E402

FIELDS = {"text": "texte", "priority": "priorité", "metric": "mesure", "category": "catégorie",
          "nature": "nature", "domain": "domaine", "title": "titre"}


def retained(req: dict) -> bool:
    return req.get("status", "retenue") == "retenue" and req.get("priority") != "hors-perimetre"


def load(path: Path, label: str, schema: dict, errors: list[str]) -> dict | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{label} : {path} illisible ({error})")
        return None
    invalid = check(data, schema)
    if invalid:
        errors += [f"{label} : {path.name} : {e}" for e in invalid[:10]]
        return None
    return data


def markdown(report: dict, old: dict, new: dict, title: str) -> str:
    lines = [f"# Écart d'exigences : {title}", "",
             f"{len(report['added'])} ajoutée(s), {len(report['modified'])} modifiée(s), "
             f"{len(report['removed'])} retirée(s), par rapport à la version validée.", ""]
    contexts = report["contexts"]
    where = (lambda rid: ", ".join(contexts.get(rid, [])) or "à rattacher") if contexts is not None else None
    if report["added"]:
        lines += ["## Ajoutées", "", "| Exigence | Priorité | Texte |" + (" Contextes |" if where else ""),
                  "| --- | --- | --- |" + (" --- |" if where else "")]
        for rid in report["added"]:
            r = new[rid]
            lines.append(f"| {rid} {cell(r['title'])} | {r['priority']} | {cell(r['text'])} |"
                         + (f" {where(rid)} |" if where else ""))
        lines.append("")
    if report["modified"]:
        lines += ["## Modifiées", "", "| Exigence | Champ | Avant | Après |" + (" Contextes |" if where else ""),
                  "| --- | --- | --- | --- |" + (" --- |" if where else "")]
        for item in report["changes"]:
            lines.append(f"| {item['id']} | {FIELDS[item['field']]} | {cell(item['before'])} | {cell(item['after'])} |"
                         + (f" {where(item['id'])} |" if where else ""))
        lines.append("")
    if report["removed"]:
        lines += ["## Retirées", "", "| Exigence | Titre |" + (" Contextes |" if where else ""),
                  "| --- | --- |" + (" --- |" if where else "")]
        lines += [f"| {rid} | {cell(old[rid]['title'])} |" + (f" {where(rid)} |" if where else "")
                  for rid in report["removed"]]
        lines.append("")
    if not (report["added"] or report["modified"] or report["removed"]):
        lines += ["Aucun écart.", ""]
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("reference", type=Path, nargs="?", help="catalogue validé (exigences.json de référence)")
    parser.add_argument("copy", type=Path, nargs="?", help="copie de travail qui reçoit les changements")
    parser.add_argument("--start", action="store_true", help="copie la référence dans COPIE.json si elle manque")
    parser.add_argument("--domains", type=Path, help="domaines.json (domain-design) : contextes qui portent les exigences")
    parser.add_argument("--out", type=Path, help="écart en Markdown")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if args.copy is None:
        parser.error("REFERENCE.json et COPIE.json attendus")
    errors: list[str] = []
    warnings: list[str] = []
    report = {"reference": str(args.reference), "copy": str(args.copy), "output": None, "added": [], "removed": [],
              "modified": [], "changes": [], "contexts": None, "copied_sources": [], "errors": errors, "warnings": warnings}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    schema = input_schema(Path(__file__).with_name("req_build.py"))
    if args.start:
        if args.copy.exists():
            warnings.append(f"{args.copy} existe déjà : copie de travail gardée telle quelle")
        else:
            old = load(args.reference, "référence", schema, errors)
            if old is not None:
                args.copy.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(args.reference, args.copy)
                report["output"] = str(args.copy)
                # Les citations des exigences reprises restent vérifiables : leurs documents vont dans les
                # sources de la copie, à côté de ceux de la demande.
                src = readable_dir(args.reference.parent) / old.get("sources", "sources")
                dst = readable_dir(args.copy.parent) / old.get("sources", "sources")
                cited = sorted({s["doc"] for r in old["requirements"] for s in r.get("sources", [])})
                for doc in cited:
                    if (src / doc).is_file() and not (dst / doc).exists():
                        dst.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(src / doc, dst / doc)
                        report["copied_sources"].append(doc)
                    elif not (src / doc).is_file():
                        warnings.append(f"{doc} : document cité absent de {src}, citation non vérifiable dans la copie")
        return done(1 if errors else 0)
    old = load(args.reference, "référence", schema, errors)
    new = load(args.copy, "copie", schema, errors)
    domains = None
    if args.domains:
        try:
            domains = json.loads(args.domains.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"--domains : {args.domains} illisible ({error})")
        else:
            dschema = schema_of("domain-design", "domain_build.py")
            if dschema is None:
                warnings.append("--domains : découpage non vérifié : " + absent("domain-design", "domain_build.py"))
            else:
                errors += [f"--domains : {args.domains.name} : {e}" for e in check(domains, dschema)[:10]]
    if errors:
        return done(1)
    before = {r["id"]: r for r in old["requirements"]}
    after = {r["id"]: r for r in new["requirements"]}
    for rid, req in after.items():
        if rid not in before or not retained(before[rid]):
            if retained(req):
                report["added"].append(rid)
            continue
        if not retained(req):
            report["removed"].append(rid)
            continue
        fields = [f for f in FIELDS if before[rid].get(f) != req.get(f)]
        if fields:
            report["modified"].append(rid)
            report["changes"] += [{"id": rid, "field": f, "before": before[rid].get(f, ""), "after": req.get(f, "")}
                                  for f in fields]
    report["removed"] += [rid for rid, req in before.items() if rid not in after and retained(req)]
    for rid in report["added"]:
        if not after[rid].get("sources"):
            warnings.append(f"{rid} : exigence ajoutée sans source (citation de la demande)")
    if domains is not None:
        carriers: dict[str, list[str]] = {}
        for ctx in domains.get("contexts", []):
            for ref in ctx.get("refs", []):
                carriers.setdefault(ref, []).append(ctx["id"])
        changed = report["added"] + report["modified"] + report["removed"]
        report["contexts"] = {rid: carriers.get(rid, []) for rid in changed}
        orphans = [rid for rid in report["added"] if not carriers.get(rid)]
        if orphans:
            warnings.append(f"{len(orphans)} exigence(s) ajoutée(s) sans contexte borné : {', '.join(orphans)} "
                            "(refs d'un contexte de domaines.json à compléter)")
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(markdown(report, before, after, new.get("title", "catalogue")), encoding="utf-8")
        report["output"] = str(args.out)
    if not (report["added"] or report["modified"] or report["removed"]):
        warnings.append("aucun écart entre la référence et la copie de travail")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
