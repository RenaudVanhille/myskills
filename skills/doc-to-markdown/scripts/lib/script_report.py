"""Rapport JSON commun des scripts qui traitent plusieurs fichiers.

Forme unique, comme les autres scripts : un objet avec `results` (un objet par
fichier, une ligne chacun), `errors` et `warnings` toujours présents. `errors`
reprend en une ligne chaque fichier en échec : l'agent lit d'abord ce champ.

Source : shared/scripts/script_report.py, copiée dans scripts/lib/ des skills
qui s'en servent par scripts/build.py. Ne modifiez pas les copies.
"""

import json
from pathlib import Path


def label(result: dict) -> str:
    source = result.get("input") or result.get("file") or result.get("source") or "?"
    return Path(str(source)).name


def failures(results: list[dict]) -> list[str]:
    """Une ligne par fichier en échec : son erreur, ou sa première erreur et le nombre des autres."""
    lines = []
    for result in results:
        if result.get("error"):
            lines.append(f"{label(result)} : {result['error']}")
        elif result.get("errors"):
            more = len(result["errors"]) - 1
            lines.append(f"{label(result)} : {result['errors'][0]}" + (f" (+{more})" if more else ""))
    return lines


def render(results: list[dict], errors: list[str] | None = None, warnings: list[str] | None = None) -> str:
    dump = lambda value: json.dumps(value, ensure_ascii=False)  # noqa: E731
    rows = ",\n".join(dump(r) for r in results)
    return ('{"results": [\n' + rows + ("\n" if rows else "") + '], "errors": '
            + dump(list(errors or []) + failures(results)) + ', "warnings": ' + dump(list(warnings or [])) + "}")


def print_report(results: list[dict], errors: list[str] | None = None, warnings: list[str] | None = None) -> None:
    print(render(results, errors, warnings))
