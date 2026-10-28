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
"""Demande au modèle local Laya quel candidat répond le mieux à une demande.

Laya est un petit modèle de décision (licence Apache-2.0) qui tourne sur CPU,
sans service en ligne. Il choisit parmi les candidats (agents, workflows,
skills) d'après leur description, et donne sa confiance. route.py --laya le
lance dans son propre environnement (dépendances lourdes) ; inutile de
l'appeler directement. Premier lancement long : PyTorch CPU (~200 Mo) puis
le modèle (~1,3 Go, téléchargé une fois).

    uv run scripts/route_laya.py question.json | --schema
"""

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import model_store  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

# Le modèle lit environ 1 000 tokens : demande et descriptions sont tronquées.
MAX_QUERY, MAX_DESCRIPTION = 600, 300


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description question.json")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    report = {"input": str(args.spec), "method": None, "choice": None, "confidence": None, "errors": [],
              "warnings": []}
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
    question = {"type": "choice", "instructions": "Quel agent, workflow ou skill doit traiter cette demande ?",
                "criteria": {name: text[:MAX_DESCRIPTION] for name, text in spec["candidates"].items()}}
    try:
        from laya import Router

        result = Router().predict({"demande": spec["query"][:MAX_QUERY]}, {"q": question})
    except Exception as error:  # noqa: BLE001 - route.py garde alors son classement par mots
        report["errors"].append(f"Laya indisponible : {type(error).__name__}: {str(error)[:300]}")
        print(json.dumps(report, ensure_ascii=False))
        return 1
    answer = result["answers"]["q"]
    report["method"] = f"laya ({result.get('routing', {}).get('model', '?')})"
    report["choice"], report["confidence"] = answer["choice"], round(float(answer.get("confidence", 0.0)), 3)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
