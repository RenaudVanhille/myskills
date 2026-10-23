# /// script
# requires-python = ">=3.10"
# ///
"""Mesure le coût des agents sur les cas de tests/agent-cases.json, dans Claude Code.

Chaque cas est joué en mode non interactif (`claude -p --output-format json`)
dans un dossier de travail temporaire qui contient ses `inputs`, avec le
plugin chargé depuis ce dépôt. Le script note pour chaque cas le coût, les
tokens, le nombre de tours et si le fichier attendu a été produit, puis
ajoute une ligne par cas à tests/costs.csv. On le lance avant et après une
modification des agents ou des skills pour en chiffrer l'effet.

Un cas peut préparer son dossier : `inputs` copie des fichiers (chaîne, ou
{"from", "to"} pour garder un sous-dossier) et `setup` lance des scripts de
skills avant l'agent (par exemple un workflow déjà soumis à la revue).

Avec --max-increase P, un cas qui coûte plus de P % de plus que sa dernière
mesure avec le même modèle (dans costs.csv) fait échouer la mesure : la
sobriété est vérifiée, pas seulement déclarée.

Rien ne part ailleurs que chez le modèle de la session Claude Code. Les
commandes de l'agent sont acceptées sans confirmation : elles ne touchent
que le dossier temporaire.

Usage :
    uv run tests/cost.py [--only ID[,ID]] [--model sonnet] [--label TEXTE] [--keep] [--max-increase 20]
"""

import argparse
import csv
import datetime
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
CSV = TESTS / "costs.csv"
COLUMNS = ["date", "label", "commit", "case", "agent", "model", "ok", "turns", "cost_usd",
           "input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens",
           "subagents", "duration_s"]


def commit() -> str:
    result = subprocess.run(["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True)
    return result.stdout.strip() or "?"


def prepare(case: dict, work: Path) -> None:
    """Copie les inputs et lance le setup du cas dans le dossier de travail."""
    for item in case["inputs"]:
        source, target = (item, Path(item).name) if isinstance(item, str) else (item["from"], item["to"])
        (work / target).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(TESTS / source, work / target)
    runner = ["uv", "run", "--quiet"] if shutil.which("uv") else [sys.executable]
    for step in case.get("setup", []):
        script = ROOT / "skills" / step["script"]
        subprocess.run(runner + [str(script)] + [a.replace("{work}", str(work)) for a in step.get("args", [])],
                       cwd=work, capture_output=True, text=True, encoding="utf-8", check=True)


def last_costs(model: str) -> dict[str, float]:
    """Dernier coût mesuré de chaque cas avec ce modèle."""
    if not CSV.exists():
        return {}
    with open(CSV, encoding="utf-8", newline="") as handle:
        return {row["case"]: float(row["cost_usd"]) for row in csv.DictReader(handle)
                if row["model"] == model and row["ok"] == "True" and row["cost_usd"]}


def run_case(case: dict, model: str, keep: bool) -> dict:
    work = Path(tempfile.mkdtemp(prefix=f"myskills-cost-{case['id']}-"))
    prepare(case, work)
    command = ["claude", "-p", case["prompt"], "--output-format", "json",
               "--plugin-dir", str(ROOT), "--agent", f"myskills:{case['agent']}",
               "--model", model, "--permission-mode", "bypassPermissions"]
    try:
        result = subprocess.run(command, cwd=work, capture_output=True, text=True,
                                encoding="utf-8", timeout=1800)
        data = json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        data = {"is_error": True, "result": str(error)}
    usage = data.get("usage", {})
    row = {"case": case["id"], "agent": case["agent"], "model": model,
           "ok": (work / case["output"]).exists() and not data.get("is_error"),
           "turns": data.get("num_turns"), "cost_usd": round(data.get("total_cost_usd", 0), 4),
           "input_tokens": usage.get("input_tokens"),
           "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
           "cache_read_tokens": usage.get("cache_read_input_tokens"),
           "output_tokens": usage.get("output_tokens"),
           "subagents": data.get("subagent_stats", {}).get("spawned"),
           "duration_s": round(data.get("duration_ms", 0) / 1000)}
    if keep:
        row["work"] = str(work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    return row


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="identifiants des cas, séparés par des virgules")
    parser.add_argument("--model", default="sonnet",
                        help="modèle fixe, pour comparer deux mesures (défaut : sonnet)")
    parser.add_argument("--label", default="", help="étiquette de la mesure (ex. avant, lot-1)")
    parser.add_argument("--keep", action="store_true",
                        help="garder les dossiers de travail (pour tests/judge.py outputs)")
    parser.add_argument("--max-increase", type=float,
                        help="échec si un cas coûte plus de ce pourcentage de plus que sa dernière mesure")
    args = parser.parse_args()
    if not shutil.which("claude"):
        print("Commande claude introuvable : installez Claude Code.", file=sys.stderr)
        return 1
    previous = last_costs(args.model)

    cases = json.loads((TESTS / "agent-cases.json").read_text(encoding="utf-8"))["cases"]
    only = set(args.only.split(",")) if args.only else None
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    rows = []
    for case in cases:
        if only and case["id"] not in only:
            continue
        row = {"date": stamp, "label": args.label, "commit": commit(), **run_case(case, args.model, args.keep)}
        before = previous.get(case["id"])
        if before and row["ok"]:
            row["increase_pct"] = round((row["cost_usd"] - before) / before * 100, 1)
            if args.max_increase is not None and row["increase_pct"] > args.max_increase:
                row["ok"] = False
                row["regression"] = f"+{row['increase_pct']} % (dernière mesure {before} USD)"
        rows.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    new = not CSV.exists()
    with open(CSV, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)
    total = sum(r["cost_usd"] for r in rows)
    print(f"\n{len(rows)} cas, {sum(r['ok'] for r in rows)} réussis, {total:.4f} USD -> {CSV.name}")
    return 0 if all(r["ok"] for r in rows) else 1


if __name__ == "__main__":
    sys.exit(main())
