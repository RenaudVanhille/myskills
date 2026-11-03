# /// script
# requires-python = ">=3.10,<3.15"
# dependencies = ["laya>=0.4"]
#
# [[tool.uv.index]]
# name = "pytorch-cpu"
# url = "https://download.pytorch.org/whl/cpu"
# explicit = true
#
# [tool.uv.sources]
# torch = { index = "pytorch-cpu" }
# ///
"""Pose au modèle local Laya les questions fermées de req_build.py sur des phrases.

Laya est un petit modèle de décision (licence Apache-2.0) qui tourne sur CPU,
sans service en ligne. Pour chaque élément de la description, il répond à
une question :
- `exigence` : la phrase exprime-t-elle une exigence ? (probabilité de oui) ;
- `categorie` : catégorie de qualité d'une exigence non fonctionnelle.

req_build.py --laya le lance dans son propre environnement (dépendances
lourdes) ; inutile de l'appeler directement. Premier lancement long :
PyTorch CPU (~200 Mo) puis le modèle (~1,3 Go, téléchargé une fois).

    uv run scripts/req_laya.py questions.json | --schema
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402
from skill_paths import require_module  # noqa: E402

model_store = require_module("check-prerequisites", "lib/model_store.py")

# Le modèle lit environ 1 000 tokens : une exigence tient largement.
MAX_CHARS = 2000
# Consignes en anglais, questions qui citent le champ `phrase` : la forme des exemples de Laya, qui
# répond mieux ainsi sur des phrases françaises. Changer une consigne : incrémenter LAYA_PROMPT de
# req_build.py, pour que les réponses en cache ne servent plus.
CATEGORIES = {"performance": "response time, throughput, volume, load",
              "disponibilite": "availability, continuity, disaster recovery, backup",
              "securite": "authentication, access rights, encryption, audit trail, protection",
              "conformite": "law, regulation, GDPR, standards, certification, audit",
              "exploitabilite": "monitoring, logs, alerts, deployment, day-to-day operations",
              "maintenabilite": "ease of change and repair, code quality, tests, documentation, configuration",
              "evolutivite": "scaling up, adding functions, products or users",
              "interoperabilite": "exchanges with other systems, API, formats, protocols, message bus",
              "utilisabilite": "ergonomics, accessibility, languages, ease of use",
              "portabilite": "changing platform, host or cloud, reversibility, open formats",
              "cout": "budget, running or licence cost",
              "autre": "none of the other categories"}
QUESTIONS = {
    "exigence": {"type": "noul",
                 "instructions": "Does `phrase` state a requirement on the system or solution to be built?",
                 "criteria": {"true": "a function, rule, quality or constraint the system must meet",
                              "false": "a fact, context, opinion, meeting, or a task for people, not for the system"}},
    "categorie": {"type": "choice", "instructions": "Which quality of the system does the requirement in `phrase` "
                                                    "address?", "criteria": CATEGORIES},
}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description questions.json")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    report = {"input": str(args.spec), "method": None, "answers": {}, "errors": [], "warnings": []}
    model_store.guard_network(report["warnings"])
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        report["errors"].append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    report["errors"] = validate(spec, __file__)
    if report["errors"]:
        print(json.dumps(report, ensure_ascii=False))
        return 1

    os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")
    try:
        model_store.hub_offline()  # avant l'import : huggingface_hub lit HF_HUB_OFFLINE au chargement
        from laya import Router

        router = Router(models=model_store.laya_models())
    except Exception as error:  # noqa: BLE001 - l'appelant se replie sur la regex
        report["errors"].append(f"Laya indisponible : {type(error).__name__}: {str(error)[:300]}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    for item in spec["items"]:
        question = item["question"]
        try:
            result = router.predict({"phrase": item["text"][:MAX_CHARS]}, {"q": QUESTIONS[question]})
        except Exception as error:  # noqa: BLE001 - une phrase en échec n'arrête pas les autres
            if not report["answers"]:
                # Le modèle se télécharge à la première question : un échec ici veut dire Laya indisponible.
                report["errors"].append(f"Laya indisponible : {type(error).__name__}: {str(error)[:300]}")
                print(json.dumps(report, ensure_ascii=False))
                return 1
            report["warnings"].append(f"{item['key']} : sans réponse ({type(error).__name__}: {str(error)[:120]})")
            continue
        answer = result["answers"]["q"]
        report["method"] = report["method"] or f"laya ({result.get('routing', {}).get('model', '?')})"
        report["answers"][item["key"]] = (
            {"probability": round(float(answer["noul"]), 3)} if question == "exigence"
            else {"choice": answer["choice"], "confidence": round(float(answer.get("confidence", 0.0)), 3)})
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
