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
skills avant l'agent (par exemple un workflow déjà soumis à la revue) ; `env`
fixe des variables pour l'agent ({tests} = ce dossier), par exemple la
doublure d'un skill externe.

Le coût d'une exécution varie d'une fois à l'autre : --repeat N joue chaque
cas N fois (toutes les lignes vont dans costs.csv) et retient la médiane.
Avec --max-increase P, un cas dont la médiane dépasse de plus de P % celle de
sa dernière mesure avec le même modèle fait échouer la mesure ; un cas qui
porte `max_cost_usd` échoue au-delà de ce plafond. La sobriété est vérifiée,
pas seulement déclarée. --jobs N lance N exécutions en même temps.

Un cas de workflow (`rounds`) joue un workflow de bout en bout : un premier
prompt, puis, tant que des étapes restent et que la précédente a avancé,
le prompt de validation de l'utilisateur simulé (`rounds.next`), au plus
`rounds.max` fois, dans le même dossier. Une ligne par tour, nommée
<cas>/<étapes soumises> : on voit ce que coûte chaque étape. Ces cas ne
tournent qu'avec --workflow ou --only.

--summary ne lance rien : il lit costs.csv et donne, par cas et par modèle,
la médiane de la dernière mesure et l'écart avec la précédente.

Rien ne part ailleurs que chez le modèle de la session Claude Code. Les
commandes de l'agent sont acceptées sans confirmation : elles ne touchent
que le dossier temporaire.

Usage :
    uv run tests/cost.py [--only ID[,ID]] [--model sonnet|agent] [--label TEXTE] [--keep]
        [--max-increase 20] [--repeat N] [--jobs N] [--workflow]
    uv run tests/cost.py --summary [--model agent]
"""

import argparse
import concurrent.futures
import csv
import datetime
import json
import os
import shutil
import statistics
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


def read_rows() -> list[dict]:
    if not CSV.exists():
        return []
    with open(CSV, encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def measures(model: str | None = None) -> dict[tuple[str, str], list[dict]]:
    """Mesures réussies par (cas, modèle), chacune = les lignes d'une même date, dans l'ordre."""
    found: dict[tuple[str, str], dict[str, list[dict]]] = {}
    for row in read_rows():
        if row["ok"] == "True" and row["cost_usd"] and (model is None or row["model"] == model):
            found.setdefault((row["case"], row["model"]), {}).setdefault(row["date"], []).append(row)
    return {key: list(dates.values()) for key, dates in found.items()}


def median(rows: list[dict], field: str) -> float:
    values = [float(r[field]) for r in rows if r.get(field) not in (None, "")]
    return round(statistics.median(values), 4) if values else 0.0


def last_costs(model: str) -> dict[str, float]:
    """Coût médian de la dernière mesure de chaque cas avec ce modèle."""
    return {case: median(runs[-1], "cost_usd") for (case, _), runs in measures(model).items()}


def claude(prompt: str, case: dict, model: str, work: Path, resume: bool = False) -> dict:
    command = ["claude", "-p", prompt, "--output-format", "json",
               "--plugin-dir", str(ROOT), "--agent", f"myskills:{case['agent']}",
               "--permission-mode", "bypassPermissions"] + ([] if model == "agent" else ["--model", model])
    try:
        env = {**os.environ, **{k: v.replace("{tests}", str(TESTS)) for k, v in case.get("env", {}).items()}}
        result = subprocess.run(command, cwd=work, capture_output=True, text=True, encoding="utf-8",
                                timeout=1800, env=env, stdin=subprocess.DEVNULL)
        return json.loads(result.stdout)
    except (subprocess.TimeoutExpired, json.JSONDecodeError) as error:
        return {"is_error": True, "result": str(error)}


def row_of(name: str, case: dict, model: str, data: dict, ok: bool) -> dict:
    usage = data.get("usage", {})
    return {"case": name, "agent": case["agent"], "model": model,
            "ok": ok and not data.get("is_error"),
            "turns": data.get("num_turns"), "cost_usd": round(data.get("total_cost_usd", 0), 4),
            "input_tokens": usage.get("input_tokens"),
            "cache_creation_tokens": usage.get("cache_creation_input_tokens"),
            "cache_read_tokens": usage.get("cache_read_input_tokens"),
            "output_tokens": usage.get("output_tokens"),
            "subagents": data.get("subagent_stats", {}).get("spawned"),
            "duration_s": round(data.get("duration_ms", 0) / 1000)}


def stages(work: Path) -> dict[str, str]:
    try:
        state = json.loads((work / "workflow.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {s["id"]: s["status"] for s in state["stages"]}


def run_case(case: dict, model: str, keep: bool) -> list[dict]:
    """Une exécution d'un cas : une ligne, ou une par tour pour un cas de workflow."""
    work = Path(tempfile.mkdtemp(prefix=f"myskills-cost-{case['id']}-"))
    prepare(case, work)
    rows = []
    if "rounds" not in case:
        data = claude(case["prompt"], case, model, work)
        rows.append(row_of(case["id"], case, model, data, (work / case["output"]).exists()))
    else:
        prompt = case["prompt"]
        for _ in range(case["rounds"].get("max", 12)):
            before = stages(work)
            data = claude(prompt, case, model, work)
            after = stages(work)
            submitted = [s for s, status in after.items() if status == "en-revue" and before.get(s) != "en-revue"]
            done = bool(after) and all(status in ("validee", "sautee") for status in after.values())
            rows.append(row_of(f"{case['id']}/{'+'.join(submitted) or ('fin' if done else 'sans-avancee')}",
                               case, model, data, bool(submitted) or done))
            if done or after == before or data.get("is_error"):
                break
            prompt = case["rounds"]["next"]
        total = {"case": case["id"], "agent": case["agent"], "model": model,
                 "ok": (work / case["output"]).exists() and all(r["ok"] for r in rows)}
        for field in ("turns", "cost_usd", "input_tokens", "cache_creation_tokens", "cache_read_tokens",
                      "output_tokens", "subagents", "duration_s"):
            total[field] = round(sum(r[field] or 0 for r in rows), 4)
        rows.append(total)
    if keep:
        for row in rows:
            row["work"] = str(work)
    else:
        shutil.rmtree(work, ignore_errors=True)
    return rows


def summary(model: str | None) -> int:
    """Tableau des dernières mesures (médianes) et écart avec la précédente, depuis costs.csv."""
    lines = [f"{'cas':42} {'modèle':7} {'n':>2} {'coût $':>8} {'écart':>7} {'tours':>5} {'durée s':>7}  date"]
    total = 0.0
    for (case, model_name), runs in sorted(measures(model).items()):
        last = runs[-1]
        cost = median(last, "cost_usd")
        delta = ""
        if len(runs) > 1 and median(runs[-2], "cost_usd"):
            delta = f"{(cost - median(runs[-2], 'cost_usd')) / median(runs[-2], 'cost_usd') * 100:+.0f} %"
        if "/" not in case:
            total += cost
        lines.append(f"{case[:42]:42} {model_name:7} {len(last):>2} {cost:>8.4f} {delta:>7} "
                     f"{median(last, 'turns'):>5.0f} {median(last, 'duration_s'):>7.0f}  {last[0]['date'][:10]}")
    print("\n".join(lines) + f"\n\nTotal des cas (dernières médianes, tours de workflow à part) : {total:.4f} USD")
    return 0


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="identifiants des cas, séparés par des virgules")
    parser.add_argument("--model", default=None,
                        help="modèle fixe, pour comparer deux mesures (défaut : sonnet) ; « agent » : le "
                             "modèle du niveau de chaque agent (shared/models.json)")
    parser.add_argument("--label", default="", help="étiquette de la mesure (ex. avant, lot-1)")
    parser.add_argument("--keep", action="store_true",
                        help="garder les dossiers de travail (pour tests/judge.py outputs)")
    parser.add_argument("--max-increase", type=float,
                        help="échec si la médiane d'un cas dépasse de ce pourcentage sa dernière mesure")
    parser.add_argument("--repeat", type=int, default=1, help="exécutions par cas ; on retient la médiane")
    parser.add_argument("--jobs", type=int, default=1, help="exécutions lancées en même temps")
    parser.add_argument("--workflow", action="store_true", help="jouer aussi les cas de workflow de bout en bout")
    parser.add_argument("--summary", action="store_true", help="résumé de costs.csv, sans rien lancer")
    args = parser.parse_args()
    if args.summary:
        return summary(args.model)
    model = args.model or "sonnet"
    if not shutil.which("claude"):
        print("Commande claude introuvable : installez Claude Code.", file=sys.stderr)
        return 1
    previous = last_costs(model)

    cases = json.loads((TESTS / "agent-cases.json").read_text(encoding="utf-8"))["cases"]
    only = set(args.only.split(",")) if args.only else None
    selected = [c for c in cases if (c["id"] in only if only else (args.workflow or "rounds" not in c))]
    stamp = datetime.datetime.now().isoformat(timespec="seconds")
    sha = commit()
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = {case["id"]: [pool.submit(run_case, case, model, args.keep) for _ in range(max(1, args.repeat))]
                   for case in selected}
        runs = {case_id: [f.result() for f in jobs] for case_id, jobs in futures.items()}

    rows, results = [], []
    for case in selected:
        for run in runs[case["id"]]:
            rows += [{"date": stamp, "label": args.label, "commit": sha, **row} for row in run]
        # Médiane du cas (ligne totale pour un cas de workflow) sur ses exécutions réussies.
        totals = [run[-1] for run in runs[case["id"]]]
        good = [r for r in totals if r["ok"]] or totals
        result = {"case": case["id"], "runs": len(totals), "ok": all(r["ok"] for r in totals),
                  "cost_usd": median(good, "cost_usd"), "turns": median(good, "turns"),
                  "duration_s": median(good, "duration_s")}
        before = previous.get(case["id"])
        if before and result["ok"]:
            result["increase_pct"] = round((result["cost_usd"] - before) / before * 100, 1)
            if args.max_increase is not None and result["increase_pct"] > args.max_increase:
                result["ok"] = False
                result["regression"] = f"+{result['increase_pct']} % (dernière mesure {before} USD)"
        if case.get("max_cost_usd") is not None and result["cost_usd"] > case["max_cost_usd"]:
            result["ok"] = False
            result["budget"] = f"{result['cost_usd']} USD au-delà du plafond de {case['max_cost_usd']} USD"
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    new = not CSV.exists()
    with open(CSV, "a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=COLUMNS, extrasaction="ignore", lineterminator="\n")
        if new:
            writer.writeheader()
        writer.writerows(rows)
    total = sum(r["cost_usd"] for r in results)
    spent = sum(r["cost_usd"] for r in rows if "/" not in r["case"])
    print(f"\n{len(results)} cas, {sum(r['ok'] for r in results)} réussis, médianes {total:.4f} USD "
          f"(dépensé {spent:.4f} USD) -> {CSV.name}")
    return 0 if all(r["ok"] for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
