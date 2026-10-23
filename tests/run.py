# /// script
# requires-python = ">=3.10"
# dependencies = ["jsonschema>=4.18"]
# ///
"""Lance les cas de test des scripts (tests/cases.json) et affiche un bilan.

Sans modèle ni service en ligne : chaque cas lance les scripts des skills sur
les documents de tests/fixtures/ et vérifie codes de sortie, rapports JSON,
fichiers produits et, si un résultat attendu existe, sa ressemblance avec
tests/expected/. Chaque rapport JSON est validé contre le JSON Schema déclaré
dans le contract.json du skill, et le cas `contrats` vérifie les contrats
eux-mêmes et les fichiers qui en sont générés ; le cas `regles` vérifie les
règles mécaniques d'AGENTS.md. Les cas marqués `slow` (gros téléchargements au premier
lancement) ne tournent qu'avec --slow.

Usage :
    uv run tests/run.py [--only ID[,ID]] [--slow] [--keep] [--json]
"""

import argparse
import difflib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
TOKENS = {"{skills}": str(ROOT / "skills"), "{samples}": str(TESTS / "fixtures" / "samples"),
          "{fixtures}": str(TESTS / "fixtures")}
# Ressemblance minimale (0 à 1) entre un fichier produit et son attendu.
MIN_RATIO = 0.9
sys.path.insert(0, str(ROOT / "scripts"))
import contracts_lib  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402
from jsonschema.exceptions import best_match  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

# Schéma du rapport de chaque script, d'après les contract.json (None : pas de JSON).
CONTRACTS = {script["name"]: script["report"].get("schema")
             for contract in contracts_lib.skill_contracts().values() for script in contract["scripts"]}
# Schéma d'entrée (description JSON) de chaque script qui en déclare un.
INPUTS = {script["name"]: script["input"]["schema"]
          for contract in contracts_lib.skill_contracts().values() for script in contract["scripts"]
          if script.get("input")}


def closest(error):
    if not error.context:
        return error
    branches: dict = {}
    for sub in error.context:
        branches.setdefault(sub.schema_path[0], []).append(sub)
    return best_match(min(branches.values(), key=len))


def schema_errors(instance, schema: dict, registry: Registry | None = None) -> list[str]:
    validator = Draft202012Validator(schema, registry=registry) if registry else Draft202012Validator(schema)
    errors = sorted(validator.iter_errors(instance), key=lambda e: list(e.absolute_path))
    # Pour un anyOf (succès ou échec), on montre l'erreur de la variante la plus proche.
    errors = [closest(e) for e in errors[:3]]
    return [f"{'/'.join(map(str, e.absolute_path)) or 'racine'} : {e.message[:160]}" for e in errors]


def expand(value: str, out: Path) -> str:
    for token, path in {**TOKENS, "{out}": str(out)}.items():
        value = value.replace(token, path)
    return value


def runner() -> list[str]:
    return ["uv", "run", "--quiet"] if shutil.which("uv") else [sys.executable]


def lookup(data, dotted: str):
    for part in dotted.split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def run_step(step: dict, out: Path, failures: list[str]) -> None:
    script = expand(step["script"], out)
    command = runner() + [script] + [expand(arg, out) for arg in step.get("args", [])]
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8")
    name = Path(script).name
    if result.returncode != step.get("exit", 0):
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or [""]
        failures.append(f"{name} : code {result.returncode} au lieu de {step.get('exit', 0)} "
                        f"({tail[0][:200]})")
    # La description passée au script (premier argument .json) doit respecter son schéma d'entrée.
    spec_schema = INPUTS.get(name)
    first = expand(step.get("args", [""])[0], out) if step.get("args") else ""
    if spec_schema and first.endswith(".json") and step.get("exit", 0) == 0:
        spec = json.loads(Path(first).read_text(encoding="utf-8"))
        failures += [f"{name} : description {Path(first).name} non conforme au schéma d'entrée, {e}"
                     for e in schema_errors(spec, spec_schema)]
    report_schema = CONTRACTS.get(name)
    if not (step.get("report") or step.get("report_contains") or report_schema):
        return
    try:
        report = json.loads(result.stdout)
    except json.JSONDecodeError:
        failures.append(f"{name} : rapport JSON illisible")
        return
    if report_schema:
        failures += [f"{name} : rapport non conforme au contrat, {e}" for e in schema_errors(report, report_schema)]
    for key, wanted in step.get("report", {}).items():
        try:
            got = lookup(report, key)
        except (KeyError, IndexError, TypeError):
            failures.append(f"{name} : {key} absent du rapport")
            continue
        if got != wanted:
            failures.append(f"{name} : {key} = {got!r}, attendu {wanted!r}")
    for key, text in step.get("report_contains", {}).items():
        try:
            got = lookup(report, key)
        except (KeyError, IndexError, TypeError):
            failures.append(f"{name} : {key} absent du rapport")
            continue
        if text not in json.dumps(got, ensure_ascii=False):
            failures.append(f"{name} : {key} ne contient pas « {text} »")


def check_outputs(case: dict, out: Path, failures: list[str]) -> None:
    for rel in case.get("files", []):
        if not (out / rel).exists():
            failures.append(f"fichier manquant : {rel}")
    for rel in case.get("absent", []):
        if (out / rel).exists():
            failures.append(f"fichier qui aurait dû disparaître : {rel}")
    for rel, texts in case.get("contains", {}).items():
        path = out / rel
        if not path.exists():
            continue
        content = path.read_text(encoding="utf-8", errors="replace")
        failures += [f"{rel} ne contient pas « {text} »" for text in texts if text not in content]
    for rel, expected in case.get("expected", {}).items():
        path = out / rel
        if not path.exists():
            continue
        got = path.read_text(encoding="utf-8").strip()
        want = (TESTS / "expected" / expected).read_text(encoding="utf-8").strip()
        ratio = difflib.SequenceMatcher(None, got, want).ratio()
        if ratio < MIN_RATIO:
            failures.append(f"{rel} ressemble à {ratio:.0%} à expected/{expected} "
                            f"(minimum {MIN_RATIO:.0%})")


def check_contracts() -> dict:
    """Contrats valides, cohérents entre eux, et fichiers générés à jour."""
    failures = []
    schemas = {name: contracts_lib.schema(name)
               for name in ("skill-contract", "agent-contract", "handoff", "agent-report")}
    registry = Registry().with_resources(
        (f"{name}.schema.json", Resource.from_contents(value)) for name, value in schemas.items())
    skills, agents = contracts_lib.skill_contracts(), contracts_lib.agent_contracts()

    for folder in sorted((ROOT / "skills").glob("*/")):
        if folder.name not in skills:
            failures.append(f"{folder.name} : pas de contract.json")
    for name, contract in skills.items():
        failures += [f"{name}/contract.json : {e}" for e in schema_errors(contract, schemas["skill-contract"])]
        if contract.get("skill") != name:
            failures.append(f"{name}/contract.json : skill = {contract.get('skill')!r}")
        declared = {script["name"] for script in contract.get("scripts", [])}
        present = {p.name for p in (ROOT / "skills" / name / "scripts").glob("*.py")}
        failures += [f"{name} : script {s} absent du contrat" for s in sorted(present - declared)]
        failures += [f"{name} : script {s} du contrat introuvable" for s in sorted(declared - present)]
        for script in contract.get("scripts", []):
            if script.get("input"):
                try:
                    Draft202012Validator.check_schema(script["input"]["schema"])
                except Exception as error:  # noqa: BLE001 - message du validateur
                    failures.append(f"{name}/{script['name']} : schéma d'entrée invalide ({error})")
            if script["report"]["format"] == "json":
                try:
                    Draft202012Validator.check_schema(script["report"].get("schema", {}))
                except Exception as error:  # noqa: BLE001 - message du validateur
                    failures.append(f"{name}/{script['name']} : schéma de rapport invalide ({error})")
        for handoff in contract.get("handoffs", []):
            known = {"skill": skills, "agent": agents, "utilisateur": {"utilisateur"}}[handoff["kind"]]
            if handoff["to"] not in known:
                failures.append(f"{name} : passe la main à {handoff['kind']} inconnu « {handoff['to']} »")

    for path in contracts_lib.REPO.joinpath("src", "agents").glob("*.md"):
        if path.stem not in agents:
            failures.append(f"agent {path.stem} : pas de {path.stem}.contract.json")
    for name, contract in agents.items():
        failures += [f"agent {name} : {e}" for e in schema_errors(contract, schemas["agent-contract"])]

    failures += [f"exemple de message de passage : {e}"
                 for e in schema_errors(contracts_lib.HANDOFF_EXAMPLE, schemas["handoff"])]
    failures += [f"exemple de rapport final : {e}"
                 for e in schema_errors(contracts_lib.REPORT_EXAMPLE, schemas["agent-report"], registry)]

    stale = []
    for name, contract in skills.items():
        if contracts_lib.render_skill(contract) not in (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8"):
            stale.append(f"skills/{name}/SKILL.md")
    for name, contract in agents.items():
        if contracts_lib.render_agent(contract) not in (ROOT / "src" / "agents" / f"{name}.md").read_text(encoding="utf-8"):
            stale.append(f"src/agents/{name}.md")
    for copy, text in {**contracts_lib.generated_libs(), **contracts_lib.plugin_manifests()}.items():
        if not copy.exists() or copy.read_text(encoding="utf-8") != text:
            stale.append(copy.relative_to(ROOT).as_posix())
    from agents_lib import parse_agent, source_agents

    meta = {parse_agent(src)[0]["name"]: parse_agent(src)[0] for src in source_agents()}
    for file, expected in (("CATALOG.md", contracts_lib.build_catalog_md(meta)),
                           ("catalog.json", contracts_lib.build_catalog_json(meta))):
        target = ROOT / file
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            stale.append(file)
    if stale:
        failures.append(f"pas à jour, lancez uv run scripts/build.py : {', '.join(stale)}")
    return {"id": "contrats", "skill": "tous", "ok": not failures, "failures": failures, "out": None}


# Skills d'import et d'export : jamais dans le même agent (AGENTS.md, section 4).
IMPORT_SKILLS = {"doc-to-markdown", "markdown-to-obsidian"}
EXPORT_SKILLS = {"markdown-publish"}
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def check_rules() -> dict:
    """Règles mécaniques d'AGENTS.md, celles marquées « vérifiée »."""
    from agents_lib import parse_agent, render_agent, source_agents, split_list

    failures = []
    for folder in sorted((ROOT / "skills").glob("*/")):
        name, skill_md = folder.name, folder / "SKILL.md"
        if not NAME.match(name):
            failures.append(f"{name} : nom en minuscules avec tirets attendu")
        if not skill_md.exists():
            failures.append(f"{name} : pas de SKILL.md")
            continue
        text = skill_md.read_text(encoding="utf-8")
        head = contracts_lib.FRONTMATTER.match(text)
        meta = dict(re.findall(r'^(\w+):\s*"?(.*?)"?\s*$', head.group(1), re.M)) if head else {}
        if meta.get("name") != name:
            failures.append(f"{name}/SKILL.md : name = {meta.get('name')!r}, attendu le nom du dossier")
        if not 0 < len(meta.get("description", "")) <= 1024:
            failures.append(f"{name}/SKILL.md : description absente ou de plus de 1024 caractères")
        if text.count("\n") > 500:
            failures.append(f"{name}/SKILL.md : plus de 500 lignes, déplacez le détail dans references/")
        for script in sorted((folder / "scripts").glob("*.py")):
            if not script.read_text(encoding="utf-8").startswith("# /// script"):
                failures.append(f"{name}/scripts/{script.name} : en-tête PEP 723 (# /// script) manquant")
    for name, contract in contracts_lib.skill_contracts().items():
        for script in contract.get("scripts", []):
            if script["report"]["format"] == "json" and not script["report"].get("schema"):
                failures.append(f"{name}/{script['name']} : rapport JSON sans schéma dans le contrat")
            # Premier argument du usage en .json : description à valider contre un schéma d'entrée.
            words = script["usage"].split()
            at = next((i for i, w in enumerate(words) if w.endswith(script["name"])), len(words))
            first = (words[at + 1:at + 2] or [""])[0]
            if ".json" in first and not script.get("input"):
                failures.append(f"{name}/{script['name']} : lit {first} sans schéma d'entrée (input) dans le contrat")
            if script.get("input") and "--schema" not in script["usage"]:
                failures.append(f"{name}/{script['name']} : option --schema absente du usage")

    for src in source_agents():
        meta = parse_agent(src)[0]
        name, skills = meta.get("name", src.stem), set(split_list(meta.get("skills", "")))
        if not NAME.match(name):
            failures.append(f"agent {name} : nom en minuscules avec tirets attendu")
        if skills & IMPORT_SKILLS and skills & EXPORT_SKILLS:
            failures.append(f"agent {name} : importe et exporte, séparez en deux agents")
        for flavor in ("claude", "copilot"):
            tools = next((line for line in render_agent(src, flavor).splitlines() if line.startswith("tools:")), "")
            if "web" in tools.lower():
                failures.append(f"agent {name} : outil web autorisé ({flavor})")
        commands = meta.get("commands", "").lower()
        failures += [f"agent {name} : commande réseau autorisée « {c} »"
                     for c in ("curl", "wget", "invoke-webrequest") if c in commands]

    for path in sorted([*(ROOT / "skills").rglob("*"), *(ROOT / "src").rglob("*")]):
        if path.is_file() and path.suffix in {".md", ".py", ".json"}:
            if "puppeteer" in path.read_text(encoding="utf-8", errors="replace").lower():
                failures.append(f"{path.relative_to(ROOT)} : Puppeteer, utilisez Playwright")
    return {"id": "regles", "skill": "tous", "ok": not failures, "failures": failures, "out": None}


def run_case(case: dict, keep: bool) -> dict:
    out = Path(tempfile.mkdtemp(prefix=f"myskills-{case['id']}-"))
    failures: list[str] = []
    try:
        for step in case["steps"]:
            run_step(step, out, failures)
        check_outputs(case, out, failures)
    finally:
        if not keep:
            shutil.rmtree(out, ignore_errors=True)
    return {"id": case["id"], "skill": case["skill"], "ok": not failures,
            "failures": failures, "out": str(out) if keep else None}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="identifiants des cas, séparés par des virgules")
    parser.add_argument("--slow", action="store_true", help="lancer aussi les cas lents")
    parser.add_argument("--keep", action="store_true", help="garder les dossiers de sortie")
    parser.add_argument("--json", action="store_true", help="rapport JSON au lieu du bilan")
    args = parser.parse_args()

    cases = json.loads((TESTS / "cases.json").read_text(encoding="utf-8"))["cases"]
    only = set(args.only.split(",")) if args.only else None
    results, skipped = [], []
    for case_id, check in (("contrats", check_contracts), ("regles", check_rules)):
        if only and case_id not in only:
            continue
        results.append(check())
        if not args.json:
            print(f"{'OK  ' if results[-1]['ok'] else 'ÉCHEC'} {case_id} (tous)", flush=True)
            for failure in results[-1]["failures"]:
                print(f"      - {failure}")
    for case in cases:
        if only and case["id"] not in only:
            continue
        if case.get("slow") and not args.slow and not only:
            skipped.append(case["id"])
            continue
        results.append(run_case(case, args.keep))
        if not args.json:
            mark = "OK  " if results[-1]["ok"] else "ÉCHEC"
            print(f"{mark} {case['id']} ({case['skill']})", flush=True)
            for failure in results[-1]["failures"]:
                print(f"      - {failure}")
            if results[-1]["out"]:
                print(f"      sortie : {results[-1]['out']}")

    passed = sum(r["ok"] for r in results)
    if args.json:
        print(json.dumps({"results": results, "skipped": skipped}, ensure_ascii=False, indent=2))
    else:
        print(f"\n{passed}/{len(results)} cas réussis"
              + (f", {len(skipped)} lents ignorés (--slow) : {', '.join(skipped)}" if skipped else ""))
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
