# /// script
# requires-python = ">=3.10"
# dependencies = ["laya>=0.4", "markitdown[docx,pptx,xlsx,pdf]>=0.1.7", "pypdf>=5"]
#
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
#
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# ///
"""Classe des documents en local (type, domaine, moteur conseillé) avec Laya.

Laya est un petit modèle de décision (licence Apache-2.0) qui tourne sur CPU,
sans service en ligne. Il répond à des questions fermées sur le début de
chaque document. Si Laya ne peut pas être chargé (premier téléchargement
impossible, par exemple), le script se replie sur des règles simples et le
signale dans `method` et `warnings`.

Affiche un rapport JSON. Usage :
    uv run scripts/classify.py FICHIER|DOSSIER [...] [--domains a,b,c] [--min-confidence 0.5]

Premier lancement long : PyTorch CPU (~200 Mo) puis le modèle (~1,3 Go,
téléchargé une fois depuis Hugging Face).
"""

import argparse
import json
import os
import sys
from pathlib import Path

PDF = {".pdf"}
TEXT = {".md", ".markdown", ".txt"}
OFFICE = {".docx", ".pptx", ".xlsx", ".xls", ".doc", ".ppt"}
SUPPORTED = PDF | TEXT | OFFICE
# Le modèle lit environ 1 000 tokens : le début du document suffit pour le classer.
MAX_CHARS = 4000
MIN_CHARS_PER_PAGE = 30
# Au-delà de cette probabilité, un PDF « à tableaux ou colonnes » part sur Docling.
TABLES_THRESHOLD = 0.7

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


class LayaError(Exception):
    """Laya n'a pas pu répondre (modèle non téléchargé, par exemple)."""


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


def questions(domains: dict, pdf: bool) -> dict:
    asked = {
        "type": {"type": "choice", "instructions": "Quel est le type de ce document ?",
                 "criteria": DOC_TYPES},
        "domaine": {"type": "choice", "instructions": "Quel est le domaine principal du document ?",
                    "criteria": domains},
    }
    if pdf:
        asked["tableaux"] = {"type": "noul", "instructions":
                             "Le document contient des tableaux de données ou une mise en page "
                             "en plusieurs colonnes."}
    return asked


def load_router():
    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    from laya import Router

    return Router()


def engine_for(suffix: str, scanned: list[int], tables: float | None) -> str:
    if suffix not in PDF:
        return "markitdown"
    if scanned or (tables is not None and tables >= TABLES_THRESHOLD):
        return "docling"
    return "markitdown"


def classify(path: Path, router, domains: dict, min_confidence: float) -> dict:
    suffix = path.suffix.lower()
    text, profile = read_start(path)
    scanned = profile.get("scanned_pages", [])
    report = {"input": str(path), "type": RULE_TYPES.get(suffix), "type_confidence": None,
              "domaine": None, "domaine_confidence": None, "tables": None,
              "engine": None, "method": "regles", "warnings": []}
    if scanned:
        report["warnings"].append(f"Pages sans texte (scannées ?) : {scanned}")

    if router is not None and len(text.strip()) >= 20:
        state = {"fichier": path.name, "debut": text}
        try:
            result = router.predict(state, questions(domains, suffix in PDF))
        except Exception as error:  # noqa: BLE001 - l'appelant se replie sur les règles
            raise LayaError(f"{type(error).__name__}: {error}") from error
        answers = result["answers"]
        for key in ("type", "domaine"):
            confidence = round(float(answers[key].get("confidence", 0.0)), 3)
            report[f"{key}_confidence"] = confidence
            if confidence >= min_confidence:
                report[key] = answers[key]["choice"]
            else:
                report["warnings"].append(
                    f"{key} incertain ({answers[key]['choice']}, confiance {confidence}) : non retenu")
        if "tableaux" in answers:
            report["tables"] = round(float(answers["tableaux"]["noul"]), 3)
        report["method"] = f"laya ({result.get('routing', {}).get('model', '?')})"
    elif router is not None:
        report["warnings"].append("Pas assez de texte pour classer : document scanné ?")

    report["engine"] = engine_for(suffix, scanned, report["tables"])
    return report


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("paths", nargs="+", type=Path, help="fichiers ou dossiers")
    parser.add_argument("--domains", help="domaines possibles : a,b ou a:description,b:description")
    parser.add_argument("--min-confidence", type=float, default=0.5,
                        help="confiance minimale pour retenir un type ou un domaine (défaut : 0.5)")
    parser.add_argument("--rules-only", action="store_true", help="ne pas charger Laya")
    args = parser.parse_args()

    router, load_warning = None, None
    if not args.rules_only:
        try:
            router = load_router()
        except Exception as error:  # noqa: BLE001 - repli sur les règles
            load_warning = f"Laya indisponible, repli sur les règles : {type(error).__name__}: {error}"

    domains = parse_domains(args.domains)
    reports, failed = [], False
    for path in collect(args.paths):
        if not path.is_file():
            reports.append({"input": str(path), "error": "Fichier introuvable"})
            failed = True
            continue
        try:
            try:
                report = classify(path.resolve(), router, domains, args.min_confidence)
            except LayaError as error:
                router = None
                load_warning = f"Laya indisponible, repli sur les règles : {error}"
                report = classify(path.resolve(), router, domains, args.min_confidence)
        except Exception as error:  # noqa: BLE001 - le rapport doit lister chaque échec
            reports.append({"input": str(path), "error": f"{type(error).__name__}: {error}"})
            failed = True
            continue
        if load_warning:
            report["warnings"].insert(0, load_warning[:300])
        reports.append(report)
    # Un objet par ligne : lisible, et sans l'indentation qui coûte des tokens.
    print("[\n" + ",\n".join(json.dumps(r, ensure_ascii=False) for r in reports) + "\n]")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
