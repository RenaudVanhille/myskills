# /// script
# requires-python = ">=3.10"
# ///
"""Rassemble en un plan d'actions unique les points ouverts des revues d'un dossier de workflow.

Le script lit les livrables Markdown déjà produits par les autres skills,
sans que le modèle les relise : constats ouverts des revues Well-Architected
(*.wa.md) et d'architecture (*revue.md : constats et risques), menaces dont
la mesure est retenue mais pas encore en place (*.threats.md), risques de
l'AIPD à mesure prévue ou à risque résiduel élevé (*.aipd.md). Les constats
d'une même règle (par exemple quatre flux à chiffrer) donnent une seule
action qui liste leurs éléments. Priorité : P1 pour une gravité haute ou un
risque résiduel élevé, P2 pour moyenne ou significatif, P3 sinon.

Sortie : <sortie>.md (tableau par priorité) et <sortie>.csv (une ligne par
action, colonnes reprises par un import Jira ou Azure DevOps : Résumé,
Description, Priorité, Étiquettes, Responsable, Échéance). Avec --assign, un
JSON court donne le responsable et l'échéance par défaut, ou par clé
d'action (colonne Clé : regle:SEC-03, risque:R-01, aipd:R-01...) ; une clé
inconnue est signalée.

    uv run scripts/actions.py DOSSIER [--assign AFFECTATION.json] [--out plan-actions] | --schema
"""

import argparse
import csv
import difflib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

PRIORITY = {"haute": "P1", "moyenne": "P2", "basse": "P3",
            "élevé": "P1", "eleve": "P1", "significatif": "P2", "limité": "P3", "limite": "P3"}
# Statut d'une menace ou d'un constat qui ne demande plus d'action.
CLOSED = re.compile(r"^(accept|trait|corrig|écart|ecart|non pertinent|fait|en place|clos)", re.I)
COLUMNS = ["Clé", "Résumé", "Description", "Priorité", "Étiquettes", "Responsable", "Échéance", "Origine"]


def tables(text: str) -> list[list[dict]]:
    """Tableaux Markdown d'un fichier, chacun en lignes {en-tête: cellule}."""
    found, header, rows = [], None, []
    for line in text.splitlines() + [""]:
        if line.startswith("|") and line.rstrip().endswith("|"):
            cells = [c.strip().replace("\\|", "|") for c in re.split(r"(?<!\\)\|", line.strip())[1:-1]]
            if header is None:
                header = cells
            elif not all(re.fullmatch(r":?-{3,}:?", c) for c in cells):
                rows.append(dict(zip(header, cells)))
            continue
        if header is not None:
            found.append(rows)
        header, rows = None, []
    return found


def plain(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<br\s*/?>|\*", " ", text)).strip()


def add(actions: dict, key: str, title: str, priority: str, label: str, origin: str, element: str, detail: str):
    """Ajoute une action, ou un élément de plus à l'action de même clé (dédoublonnage)."""
    action = actions.setdefault(key, {"key": key, "title": title, "priority": priority, "labels": label,
                                      "origins": [], "elements": [], "details": []})
    action["priority"] = min(action["priority"], priority)
    if label not in action["labels"].split(","):
        action["labels"] += f",{label}"
    for field, value in (("origins", origin), ("elements", element), ("details", detail)):
        if value and value not in action[field]:
            action[field].append(value)


def collect(folder: Path, actions: dict, counts: dict, warnings: list[str]) -> None:
    files = sorted(p for p in folder.rglob("*.md") if ".myskills-tmp" not in p.parts)
    for path in files:
        name, rel = path.name, path.relative_to(folder).as_posix()
        kind = ("wa" if name.endswith(".wa.md") else "menace" if name.endswith(".threats.md")
                else "aipd" if name.endswith(".aipd.md") else "revue" if name.endswith("revue.md") else None)
        if not kind:
            continue
        before = len(actions)
        for rows in tables(path.read_text(encoding="utf-8", errors="replace")):
            head = set(rows[0]) if rows else set()
            if {"Règle", "Gravité", "Correction", "Statut"} <= head:  # constats (Well-Architected, revue)
                for r in rows:
                    if CLOSED.match(r["Statut"]):
                        continue
                    tag = "well-architected" if kind == "wa" else "revue"
                    # Même règle dans la revue d'architecture et la revue Well-Architected : une seule action.
                    add(actions, f"regle:{r['Règle']}", plain(r["Correction"]), PRIORITY.get(r["Gravité"], "P3"),
                        tag, f"{r['ID']} ({rel})", plain(r["Élément"]), plain(r["Constat"]))
            elif {"Menace", "Mesure retenue", "Statut"} <= head:  # menaces STRIDE
                todo = [r for r in rows if not r["Mesure retenue"] and not CLOSED.match(r["Statut"])]
                if todo:
                    counts["to_analyze"] += len(todo)
                    warnings.append(f"{rel} : {len(todo)} menace(s) sans mesure retenue, à analyser avec "
                                    "architecture-reviewer avant le plan")
                for r in rows:
                    if r["Mesure retenue"] and not CLOSED.match(r["Statut"]):
                        add(actions, f"menace:{plain(r['Mesure retenue']).lower()[:60]}", plain(r["Mesure retenue"]),
                            "P2", "securite", f"{r['ID']} ({rel})", plain(r["Élément"]), plain(r["Menace"]))
            elif {"Risque", "Résiduel", "Mesures"} <= head:  # risques de l'AIPD
                for r in rows:
                    residual = r["Résiduel"].split(":")[-1].strip()
                    planned = [plain(m.replace("*(prévue)*", "")) for m in re.split(r"<br\s*/?>", r["Mesures"])
                               if "(prévue)" in m]
                    if residual in ("élevé", "eleve"):
                        add(actions, f"aipd:{r['Risque']}", f"Réduire le risque {r['Risque']} ({plain(r['Événement redouté'])}) "
                            "ou consulter la CNIL", "P1", "rgpd", f"{r['Risque']} ({rel})", r["Traitement"],
                            f"risque résiduel {r['Résiduel']}")
                    if residual == "à évaluer" or r["Mesures"].strip() == "aucune":
                        add(actions, f"aipd:{r['Risque']}", f"Définir les mesures du risque {r['Risque']} "
                            f"({plain(r['Événement redouté'])})", PRIORITY.get(r["Niveau"], "P2"), "rgpd",
                            f"{r['Risque']} ({rel})", r["Traitement"], "aucune mesure")
                    for measure in planned:
                        add(actions, f"aipd-mesure:{measure.lower()[:60]}", f"Mettre en place : {measure}",
                            PRIORITY.get(residual, PRIORITY.get(r["Niveau"], "P2")), "rgpd",
                            f"{r['Risque']} ({rel})", r["Traitement"], "mesure prévue")
            elif {"Risque", "Atténuation", "Responsable"} <= head:  # risques de la revue d'architecture
                for r in rows:
                    mitigation = plain(r["Atténuation"])
                    title = mitigation if mitigation and mitigation != "à définir" else \
                        f"Définir l'atténuation du risque {r['ID']}"
                    add(actions, f"risque:{r['ID']}", title, PRIORITY.get(r["Gravité"], "P3"), "revue",
                        f"{r['ID']} ({rel})", "", plain(r["Risque"]))
                    if r["Responsable"] not in ("", "à désigner"):
                        actions[f"risque:{r['ID']}"].setdefault("owner", r["Responsable"])
        counts["sources"][rel] = len(actions) - before


def assign(actions: dict, spec: dict, warnings: list[str]) -> None:
    keys = list(actions)
    for key, values in spec.get("actions", {}).items():
        if key not in actions:
            close = difflib.get_close_matches(key, keys, n=1)
            warnings.append(f"--assign : action « {key} » inconnue" + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            continue
        actions[key].update({k: v for k, v in values.items()})
    for action in actions.values():
        action.setdefault("owner", spec.get("owner", ""))
        action.setdefault("due", spec.get("due", ""))


def render(title: str, ordered: list[dict]) -> str:
    lines = [f"# Plan d'actions : {title}", "",
             f"{len(ordered)} action(s) tirée(s) des revues du dossier par `actions.py` : "
             + ", ".join(f"{sum(a['priority'] == p for a in ordered)} {p}" for p in ("P1", "P2", "P3")) + ".", ""]
    if not ordered:
        return "\n".join(lines + ["Aucune action ouverte."]) + "\n"
    lines += ["| N° | Priorité | Action | Éléments | Origine | Responsable | Échéance | Statut |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for index, a in enumerate(ordered, 1):
        cells = [f"A{index:02d}", a["priority"], a["title"], ", ".join(a["elements"]) or "-",
                 ", ".join(a["origins"]), a.get("owner") or "à désigner", a.get("due") or "-",
                 a.get("status", "à faire")]
        lines.append("| " + " | ".join(c.replace("|", "\\|") for c in cells) + " |")
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if sys.argv[1:] == ["--schema"]:
        print_schema(__file__)
        return 0
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path)
    parser.add_argument("--assign", type=Path, help="responsable et échéance, par défaut ou par clé d'action (JSON)")
    parser.add_argument("--out", help="nom des fichiers produits, sans extension (défaut : DOSSIER/plan-actions)")
    parser.add_argument("--title", help="titre (défaut : titre du workflow, sinon nom du dossier)")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.folder), "outputs": [], "actions": 0, "priorities": {}, "sources": {},
              "to_analyze": 0, "errors": errors, "warnings": warnings}
    spec = {}
    if not args.folder.is_dir():
        errors.append(f"dossier introuvable : {args.folder}")
    if args.assign:
        try:
            spec = json.loads(args.assign.read_text(encoding="utf-8"))
            errors += validate(spec, __file__)
        except (OSError, ValueError) as error:
            errors.append(f"--assign : {args.assign} illisible ({error})")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    actions: dict = {}
    counts = {"sources": {}, "to_analyze": 0}
    collect(args.folder, actions, counts, warnings)
    if not counts["sources"]:
        warnings.append("aucune revue trouvée (*.wa.md, *.threats.md, *.aipd.md, revue.md) : plan vide")
    assign(actions, spec, warnings)
    ordered = sorted(actions.values(), key=lambda a: (a["priority"], a["key"]))
    title = args.title
    if not title:
        try:
            title = json.loads((args.folder / "workflow.json").read_text(encoding="utf-8"))["title"]
        except (OSError, ValueError, KeyError):
            title = args.folder.resolve().name
    base = Path(args.out) if args.out else args.folder / "plan-actions"
    base.parent.mkdir(parents=True, exist_ok=True)
    md, table = base.with_name(base.name + ".md"), base.with_name(base.name + ".csv")
    ai_mark.write_text(md, render(title, ordered))
    with open(table, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(COLUMNS)
        for a in ordered:
            writer.writerow([a["key"], a["title"], "; ".join(a["details"])
                             + (f" ({', '.join(a['elements'])})" if a["elements"] else ""),
                             a["priority"], a["labels"], a.get("owner", ""), a.get("due", ""), ", ".join(a["origins"])])
    # Relecture : le CSV a autant de lignes que d'actions.
    with open(table, encoding="utf-8-sig", newline="") as handle:
        if sum(1 for _ in csv.reader(handle, delimiter=";")) != len(ordered) + 1:
            errors.append(f"{table.name} : nombre de lignes différent du nombre d'actions")
    report.update(outputs=[str(md), str(table)], actions=len(ordered),
                  priorities={p: sum(a["priority"] == p for a in ordered) for p in ("P1", "P2", "P3")},
                  sources=counts["sources"], to_analyze=counts["to_analyze"])
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
