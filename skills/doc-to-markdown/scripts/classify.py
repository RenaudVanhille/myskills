# /// script
# requires-python = ">=3.10"
# dependencies = ["markitdown[docx,pptx,xlsx,pdf]>=0.1.7", "lxml<6.2", "pypdf>=5"]
# ///
"""Classe des documents (type, domaine, moteur conseillé) : règles, puis tri d'un modèle léger.

Le script ne charge aucun modèle. Sans option, il applique des règles (type
d'une présentation, Docling pour un PDF scanné). Le type et le domaine
demandent de lire : --candidates écrit le début de chaque document, les
types et les domaines permis et la consigne, pour un sous-agent de niveau
simple, qui rend le fichier de tri ; --triage relit ce fichier, le valide et
l'applique. Sur le jeu étiqueté de tests/classify_eval.py, ce tri donne le
bon type pour 100 % des documents et le bon domaine pour 90 %.

Affiche un rapport JSON. Usage :
    uv run scripts/classify.py FICHIER|DOSSIER [...] [--domains a,b,c]
        [--candidates FICHIER] [--triage FICHIER] | --schema
"""

import argparse
import difflib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from script_report import print_report  # noqa: E402
from skill_paths import require_module  # noqa: E402
from spec_schema import print_schema, read_spec, schema_option  # noqa: E402

model_store = require_module("check-prerequisites", "lib/model_store.py")

PDF = {".pdf"}
TEXT = {".md", ".markdown", ".txt"}
OFFICE = {".docx", ".pptx", ".xlsx", ".xls", ".doc", ".ppt"}
SUPPORTED = PDF | TEXT | OFFICE
# Le début du document suffit pour le classer.
MAX_CHARS = 1500
MIN_CHARS_PER_PAGE = 30

DOC_TYPES = {
    "specification": "spécification fonctionnelle ou technique, exigences, cahier des charges",
    "architecture": "dossier d'architecture, conception, choix techniques, schémas de composants",
    "procedure": "procédure, guide, mode opératoire, tutoriel, documentation utilisateur",
    "compte-rendu": "compte rendu ou notes de réunion, décisions, actions à mener",
    "presentation": "présentation ou support de diapositives",
    "contrat": "contrat, convention, conditions juridiques, devis, facture",
    "rapport": "rapport, étude, audit, analyse, bilan",
    "autre": "aucune des catégories précédentes",
}
DOMAINS = {
    "architecture": "architecture logicielle ou système",
    "developpement": "développement logiciel, code, API, tests",
    "infrastructure": "infrastructure, cloud, réseau, déploiement, exploitation",
    "securite": "sécurité, conformité, risques, accès",
    "donnees": "données, bases de données, reporting, data science",
    "metier": "processus métier, besoins des utilisateurs, organisation",
    "gestion-projet": "gestion de projet, planning, budget, pilotage",
}
RULE_TYPES = {".pptx": "presentation", ".ppt": "presentation"}


def collect(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*")
                            if p.is_file() and p.suffix.lower() in SUPPORTED)
        else:
            files.append(path)
    return files


def read_start(path: Path) -> tuple[str, dict]:
    """Renvoie le début du texte et, pour un PDF, les pages sans texte."""
    suffix = path.suffix.lower()
    if suffix in TEXT:
        return path.read_text(encoding="utf-8", errors="replace")[:MAX_CHARS], {}
    if suffix in PDF:
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        texts = [(page.extract_text() or "").strip() for page in reader.pages]
        scanned = [i + 1 for i, text in enumerate(texts) if len(text) < MIN_CHARS_PER_PAGE]
        return "\n".join(texts)[:MAX_CHARS], {"pages": len(texts), "scanned_pages": scanned}
    from markitdown import MarkItDown

    return MarkItDown().convert(str(path)).text_content[:MAX_CHARS], {}


def parse_domains(value: str | None) -> dict:
    """`a,b` ou `a:description,b:description`."""
    if not value:
        return DOMAINS
    domains = {}
    for item in value.split(","):
        name, _, description = item.partition(":")
        if name.strip():
            domains[name.strip()] = description.strip() or name.strip()
    return domains


INSTRUCTIONS = (
    "Pour chaque document de `documents`, lis `text` (le début du document) et choisis un `type` parmi "
    "`types` et un `domaine` parmi `domaines` (leurs descriptions disent quand les choisir). Pour un PDF, "
    "ajoute `tableaux` : true si le début montre des tableaux de données ou plusieurs colonnes. Écris "
    "dans le fichier `output` un seul objet JSON : {\"<name>\": {\"type\": ..., \"domaine\": ..., "
    "\"tableaux\": ...}}, une clé par document, sans autre texte.")


def keys_of(files: list[Path]) -> dict[Path, str]:
    """Clé de chaque document dans le tri : son nom, ou son chemin si deux documents portent ce nom."""
    names = [path.name for path in files]
    return {path: path.name if names.count(path.name) == 1 else path.as_posix() for path in files}


def triage_entry(triage: dict, key: str) -> tuple[str | None, dict | None]:
    """Entrée du tri pour ce document : par sa clé, sinon par son nom sans extension (note
    Markdown tirée du document trié) quand une seule entrée le porte."""
    if key in triage:
        return key, triage[key]
    same = [name for name in triage if Path(name).stem == Path(key).stem]
    return (same[0], triage[same[0]]) if len(same) == 1 else (None, None)


def triage_errors(triage: dict, domains: dict) -> list[str]:
    """Domaines hors de la liste permise (elle dépend de --domains : le schéma ne la connaît pas)."""
    errors = []
    for name, entry in triage.items():
        domain = entry.get("domaine")
        if domain is not None and domain not in domains:
            close = difflib.get_close_matches(domain, list(domains), 1)
            errors.append(f"tri : {name}/domaine : « {domain} » n'est pas permis"
                          + (f" ({close[0]} ?)" if close else "") + f" ; permis : {', '.join(domains)}")
    return errors


def write_candidates(target: Path, starts: dict[str, str], domains: dict) -> None:
    output = target.with_name(target.name.removesuffix(".json").removesuffix(".candidats") + ".tri.json")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({
        "instructions": INSTRUCTIONS, "output": output.name, "types": DOC_TYPES, "domaines": domains,
        "documents": [{"name": key, "text": text} for key, text in starts.items()]},
        ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def classify(path: Path, key: str, triage: dict | None) -> tuple[dict, str, str | None]:
    """Rapport du document, début de son texte et clé du tri qui l'a classé."""
    suffix = path.suffix.lower()
    text, profile = read_start(path)
    scanned = profile.get("scanned_pages", [])
    report = {"input": str(path), "type": RULE_TYPES.get(suffix), "domaine": None, "tables": None,
              "engine": None, "method": "regles", "warnings": []}
    if scanned:
        report["warnings"].append(f"Pages sans texte (scannées ?) : {scanned}")
    used, entry = triage_entry(triage, key) if triage is not None else (None, None)
    if entry is not None:
        report.update(type=entry["type"], domaine=entry.get("domaine"), method="tri",
                      tables=entry.get("tableaux") if suffix in PDF else None)
    elif triage is not None:
        report["warnings"].append("Absent du tri : classé par les règles")
    report["engine"] = "docling" if suffix in PDF and (scanned or report["tables"]) else "markitdown"
    return report, text, used


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="*", type=Path, help="fichiers ou dossiers")
    parser.add_argument("--domains", help="domaines possibles : a,b ou a:description,b:description")
    parser.add_argument("--candidates", type=Path,
                        help="écrit le début des documents et la consigne de tri pour un sous-agent de niveau simple")
    parser.add_argument("--triage", type=Path, help="tri rendu par ce sous-agent : {nom: {type, domaine, tableaux}}")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.paths:
        print_report([], ["Aucun document : donnez des fichiers ou des dossiers"])
        return 1
    warnings: list[str] = []
    model_store.guard_network(warnings)

    domains = parse_domains(args.domains)
    triage = None
    if args.triage:
        triage, errors = read_spec(args.triage, __file__)
        errors = errors or triage_errors(triage, domains)
        if errors:
            print_report([], errors)
            return 1
    files = collect(args.paths)
    keys = keys_of(files)
    reports, starts, used, failed = [], {}, set(), False
    for path in files:
        if not path.is_file():
            reports.append({"input": str(path), "error": "Fichier introuvable"})
            failed = True
            continue
        try:
            report, text, key = classify(path.resolve(), keys[path], triage)
        except Exception as error:  # noqa: BLE001 - le rapport doit lister chaque échec
            reports.append({"input": str(path), "error": f"{type(error).__name__}: {error}"})
            failed = True
            continue
        used.add(key)
        if report["method"] == "regles" and len(text.strip()) >= 20:
            starts[keys[path]] = text
        reports.append(report)
    unknown = sorted(set(triage or {}) - used)
    if unknown:
        warnings.append(f"Tri : {len(unknown)} entrée(s) sans document dans le lot : {', '.join(unknown[:5])}")
    if args.candidates and not failed:
        write_candidates(args.candidates, starts, domains)
        warnings.append(f"{len(starts)} document(s) à trier dans {args.candidates.name}")
    print_report(reports, warnings=warnings)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
