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
lancement) ne tournent qu'avec --slow. Les cas tournent en parallèle, chacun
dans son dossier temporaire (--jobs, par défaut le nombre de cœurs) ; le
bilan garde l'ordre de cases.json.

Usage :
    uv run tests/run.py [--only ID[,ID]] [--slow] [--keep] [--json] [--jobs N]
"""

import argparse
import concurrent.futures
import difflib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS = Path(__file__).resolve().parent
ROOT = TESTS.parent
# Budget de taille d'un SKILL.md et d'un agent source (environ 4 000 tokens) : le coût suit ce que le modèle relit.
MAX_CHARS = 16000
# Au-delà de cette part du budget, regles avertit sans échouer : la prochaine
# évolution du fichier le ferait dépasser.
NEAR_BUDGET = 0.9
TOKENS = {"{skills}": str(ROOT / "skills"), "{samples}": str(TESTS / "fixtures" / "samples"),
          "{fixtures}": str(TESTS / "fixtures"), "{root}": str(ROOT)}
# Ressemblance minimale (0 à 1) entre un fichier produit et son attendu.
MIN_RATIO = 0.9
# Dépendances et extras interdits dans les scripts des skills (cas regles).
FORBIDDEN_DEPS = ("modelscope", "rapidocr", "rapidocr-onnxruntime", "easyocr", "paddleocr", "funasr")
# Vérifie dans un processus à part que model_store.guard_network() filtre les flux (cas regles) :
# hôte non identifié refusé (nom, adresse, tunnel de proxy) et signalé, hôte autorisé, proxy et boucle
# locale permis.
NETWORK_PROBE = r"""
import http.client, socket, sys
sys.path.insert(0, sys.argv[1])
import model_store
warnings = []
model_store.guard_network(warnings)
problems = []
def refused(action, label):
    try:
        action()
        problems.append(label + " permis")
    except ConnectionRefusedError as error:
        if "myskills" not in str(error):
            problems.append(label + " : refus inattendu " + str(error))
    except OSError:
        problems.append(label + " : pas refusé par myskills")
refused(lambda: socket.getaddrinfo("www.modelscope.cn", 443), "résolution de modelscope.cn")
refused(lambda: socket.create_connection(("modelscope.cn", 443), timeout=2), "connexion à modelscope.cn")
refused(lambda: socket.socket().connect(("192.0.2.1", 443)), "connexion à 192.0.2.1")
refused(lambda: socket.socket().connect_ex(("192.0.2.1", 443)), "connect_ex vers 192.0.2.1")
refused(lambda: http.client.HTTPSConnection("127.0.0.1", 9).set_tunnel("modelscope.cn", 443), "tunnel vers modelscope.cn")
http.client.HTTPSConnection("127.0.0.1", 9).set_tunnel("huggingface.co", 443)
try:
    socket.getaddrinfo("huggingface.co", 443)
except ConnectionRefusedError as error:
    problems.append("huggingface.co refusé : " + str(error))
except OSError:
    pass
if not any("modelscope.cn" in w for w in warnings):
    problems.append("flux refusé absent des avertissements")
server = socket.socket()
server.bind(("127.0.0.1", 0))
server.listen(1)
client = socket.socket()
client.connect(server.getsockname())
client.close(); server.close()
print("ok" if not problems else " ; ".join(problems))
"""
FORBIDDEN_EXTRAS = ("all", "audio-transcription", "az-doc-intel", "youtube-transcription")
sys.path.insert(0, str(ROOT / "scripts"))
import contracts_lib  # noqa: E402
from jsonschema import Draft202012Validator  # noqa: E402
from jsonschema.exceptions import best_match  # noqa: E402
from referencing import Registry, Resource  # noqa: E402

# Schéma du rapport de chaque script, d'après les contract.json (None : pas de JSON).
CONTRACTS = {script["name"]: script["report"].get("schema")
             for contract in contracts_lib.skill_contracts().values() for script in contract["scripts"]}
CONTRACTS["install.py"] = contracts_lib.schema("install-report")
CONTRACTS["check_commit.py"] = contracts_lib.schema("commit-report")
CONTRACTS["pin_model.py"] = contracts_lib.schema("pin-report")
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
    if "copy" in step:  # prépare un fichier ou un dossier de travail : {"copy": [source, destination]}
        source, target = (Path(expand(p, out)) for p in step["copy"])
        target.parent.mkdir(parents=True, exist_ok=True)
        if source.is_dir():
            shutil.copytree(source, target, dirs_exist_ok=True)
        else:
            shutil.copyfile(source, target)
        return
    script = expand(step["script"], out)
    command = runner() + [script] + [expand(arg, out) for arg in step.get("args", [])]
    # "env" : variables propres à l'étape (cache isolé, mode hors ligne...).
    env = {**os.environ, **{k: expand(v, out) for k, v in step.get("env", {}).items()}}
    result = subprocess.run(command, capture_output=True, text=True, encoding="utf-8", env=env)
    name = Path(script).name
    if step.get("exit", 0) != "any" and result.returncode != step.get("exit", 0):
        tail = (result.stderr or result.stdout).strip().splitlines()[-1:] or [""]
        failures.append(f"{name} : code {result.returncode} au lieu de {step.get('exit', 0)} "
                        f"({tail[0][:200]})")
    # La description passée au script (premier argument .json) doit respecter son schéma d'entrée.
    spec_schema = INPUTS.get(name)
    first = expand(step.get("args", [""])[0], out) if step.get("args") else ""
    if spec_schema and first.endswith(".json") and step.get("exit", 0) == 0 and Path(first).is_file():
        spec = json.loads(Path(first).read_text(encoding="utf-8"))
        failures += [f"{name} : description {Path(first).name} non conforme au schéma d'entrée, {e}"
                     for e in schema_errors(spec, spec_schema)]
    report_schema = CONTRACTS.get(name)
    if not (step.get("report") or step.get("report_contains") or step.get("report_in") or report_schema):
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
            # Les avertissements du rapport disent souvent pourquoi (repli, outil absent).
            failures += [f"{name} : avertissement : {w}"[:400] for w in report_warnings(report)[:3]]
    for key, allowed in step.get("report_in", {}).items():
        try:
            got = lookup(report, key)
        except (KeyError, IndexError, TypeError):
            failures.append(f"{name} : {key} absent du rapport")
            continue
        if got not in allowed:
            failures.append(f"{name} : {key} = {got!r}, attendu l'un de {allowed!r}")
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
               for name in ("skill-contract", "agent-contract", "handoff", "agent-report", "external-skill")}
    registry = Registry().with_resources(
        (f"{name}.schema.json", Resource.from_contents(value)) for name, value in schemas.items())
    skills, agents = contracts_lib.skill_contracts(), contracts_lib.agent_contracts()
    externals = contracts_lib.external_contracts()
    for name, contract in externals.items():
        failures += [f"external/{name}.contract.json : {e}" for e in schema_errors(contract, schemas["external-skill"])]
        if contract.get("skill") != name:
            failures.append(f"external/{name}.contract.json : skill = {contract.get('skill')!r}")
        if name in skills:
            failures.append(f"external/{name} : un skill du dépôt porte déjà ce nom")
        for key in ("plan", "output_schema"):
            try:
                Draft202012Validator.check_schema(contract.get(key, {}))
            except Exception as error:  # noqa: BLE001 - message du validateur
                failures.append(f"external/{name} : schéma {key} invalide ({error})")

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
        # Dépendances déclarées (requires) et schéma d'entrée repris d'un autre skill (same_as).
        required = set()
        for need in contract.get("requires", []):
            target = skills.get(need["skill"])
            required.add((need["skill"], need["script"]))
            if need["skill"] == name or target is None:
                failures.append(f"{name} : requires vise un skill inconnu ou lui-même « {need['skill']} »")
            elif need["script"].startswith("lib/"):
                if not (ROOT / "skills" / need["skill"] / "scripts" / need["script"]).is_file():
                    failures.append(f"{name} : requires vise le module {need['skill']}/scripts/{need['script']}, introuvable")
            elif need["script"] not in {s["name"] for s in target.get("scripts", [])}:
                failures.append(f"{name} : requires vise {need['skill']}/{need['script']}, absent de son contrat")
        for script in contract.get("scripts", []):
            source = (script.get("input") or {}).get("same_as")
            if source and source.startswith("shared/schemas/"):
                if not (ROOT / source).is_file():
                    failures.append(f"{name}/{script['name']} : input.same_as « {source} » introuvable")
            elif source and source.split("/", 1)[0] != name and tuple(source.split("/", 1)) not in required:
                failures.append(f"{name}/{script['name']} : input.same_as « {source} » absent de requires")
        for handoff in contract.get("handoffs", []):
            known = {"skill": skills, "agent": agents, "utilisateur": {"utilisateur"},
                     "externe": externals}[handoff["kind"]]
            if handoff["to"] not in known:
                failures.append(f"{name} : passe la main à {handoff['kind']} inconnu « {handoff['to']} »")
            elif handoff["kind"] == "externe":
                # Le skill externe se lance avec l'interpréteur de l'appelant : ses dépendances
                # doivent figurer dans l'en-tête PEP 723 d'un script du skill.
                headers = " ".join(p.read_text(encoding="utf-8").split("# ///")[1]
                                   for p in (ROOT / "skills" / name / "scripts").glob("*.py")
                                   if p.read_text(encoding="utf-8").startswith("# /// script"))
                failures += [f"{name} : dépendance {d} du skill externe {handoff['to']} absente des en-têtes PEP 723"
                             for d in externals[handoff["to"]].get("dependencies", []) if f'"{d}"' not in headers]

    # Ontologie du vault : conforme à son schéma et cohérente ; types écrits déclarés (vault.writes) existants.
    ontology = json.loads(contracts_lib.VAULT_ONTOLOGY.read_text(encoding="utf-8"))
    failures += [f"vault-ontology.json : {e}" for e in schema_errors(ontology, contracts_lib.schema("vault-ontology"))]
    kinds = set(ontology.get("types", {}))
    for kind, spec in ontology.get("types", {}).items():
        known = {*ontology["common"], *spec["properties"]}
        failures += [f"vault-ontology.json : type {kind}, {p} ({field}) n'est pas une propriété déclarée"
                     for field in ("required", "facets") for p in spec.get(field, []) if p not in known]
        failures += [f"vault-ontology.json : type {kind}, propriété {p} déjà nommée par une relation"
                     for p in spec["properties"] if p in ontology["relations"]]
    for rel, spec in ontology.get("relations", {}).items():
        failures += [f"vault-ontology.json : relation {rel}, type « {k} » inconnu"
                     for k in spec["from"] + spec["to"] if k != "*" and k not in kinds]
    for name, contract in skills.items():
        failures += [f"{name} : vault.writes vise le type « {k} », absent de l'ontologie du vault"
                     for k in contract.get("vault", {}).get("writes", []) if k not in kinds]

    # Workflows livrés : conformes au schéma de définition, skills et agents existants.
    journal_input = next(s["input"]["schema"] for s in skills["decision-log"]["scripts"] if s["name"] == "journal.py")
    definition_schema = {**journal_input["$defs"]["definition"], "$defs": journal_input["$defs"]}
    from agents_lib import parse_agent as parse, split_list as split

    engine = set(split(parse(ROOT / "src" / "agents" / "architecture-workflow.md")[0].get("skills", "")))
    # Chaque workflow a au moins un cas d'agent (id workflow-<nom> ou bout-en-bout-<nom>, ou champ workflow) :
    # sa définition seule ne dit pas si un vrai agent sait la suivre.
    # Chaque script déclaré est lancé par au moins un cas de cases.json (lent compris).
    cases_text = (TESTS / "cases.json").read_text(encoding="utf-8")
    failures += [f"{name} : {script['name']} lancé par aucun cas de tests/cases.json"
                 for name, contract in skills.items() for script in contract.get("scripts", [])
                 if f"/scripts/{script['name']}\"" not in cases_text]
    agent_cases = json.loads((TESTS / "agent-cases.json").read_text(encoding="utf-8"))["cases"]
    played = {c.get("workflow") for c in agent_cases} | {c["id"].removeprefix(p) for c in agent_cases
                                                         for p in ("workflow-", "bout-en-bout-") if c["id"].startswith(p)}
    workflows_doc = (ROOT / "skills" / "decision-log" / "references" / "workflows.md").read_text(encoding="utf-8")
    for path in sorted((ROOT / "skills" / "decision-log" / "workflows").glob("*.json")):
        definition = json.loads(path.read_text(encoding="utf-8"))
        if f"| `{path.stem}` |" not in workflows_doc:
            failures.append(f"workflows/{path.name} : absent du tableau de decision-log/references/workflows.md")
        if path.stem not in played:
            failures.append(f"workflows/{path.name} : aucun cas d'agent dans tests/agent-cases.json "
                            f"(id workflow-{path.stem}, ou champ workflow)")
        for stage in definition.get("stages", []):
            if not stage.get("level"):
                failures.append(f"workflows/{path.name} : étape {stage.get('id')} sans level (simple, moyen, complexe)")
            failures += [f"workflows/{path.name} : étape {stage.get('id')}, skill « {s} » absent des skills "
                         "de l'agent architecture-workflow" for s in stage.get("skills", [])
                         if s in skills and s not in engine]
        failures += [f"workflows/{path.name} : {e}" for e in schema_errors(definition, definition_schema)]
        if definition.get("name") != path.stem:
            failures.append(f"workflows/{path.name} : name = {definition.get('name')!r}, attendu {path.stem!r}")
        seen: list = []
        for stage in definition.get("stages", []):
            # after : des étapes placées avant (pas de cycle possible).
            failures += [f"workflows/{path.name} : étape {stage.get('id')}, after vise « {a} », pas une étape "
                         "placée avant" for a in stage.get("after", []) if a not in seen]
            seen.append(stage.get("id"))
            failures += [f"workflows/{path.name} : étape {stage.get('id')}, skill inconnu « {s} »"
                         for s in stage.get("skills", []) if s not in skills]
            if stage.get("agent") and stage["agent"] not in agents:
                failures.append(f"workflows/{path.name} : étape {stage.get('id')}, agent inconnu « {stage['agent']} »")
            # run : contrôles lancés par journal.py check, scripts déclarés dans le contrat d'un skill de l'étape.
            for entry in stage.get("run", []):
                declared = {s["name"] for s in skills.get(entry.get("skill"), {}).get("scripts", [])}
                if entry.get("skill") not in stage.get("skills", []):
                    failures.append(f"workflows/{path.name} : étape {stage.get('id')}, run vise « {entry.get('skill')} », "
                                    "absent des skills de l'étape")
                elif entry.get("script") not in declared:
                    failures.append(f"workflows/{path.name} : étape {stage.get('id')}, run vise {entry.get('skill')}/"
                                    f"{entry.get('script')}, absent de son contrat")

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
    for copy, text in {**contracts_lib.agent_enums(), **contracts_lib.shared_inputs(), **contracts_lib.generated_libs(),
                       **contracts_lib.plugin_manifests(), **contracts_lib.gitattributes()}.items():
        if not copy.exists() or copy.read_text(encoding="utf-8") != text:
            stale.append(copy.relative_to(ROOT).as_posix())
    from agents_lib import parse_agent, source_agents

    meta = {parse_agent(src)[0]["name"]: parse_agent(src)[0] for src in source_agents()}
    for file, expected in (("CATALOG.md", contracts_lib.build_catalog_md(meta)),
                           ("catalog.json", contracts_lib.build_catalog_json(meta)),
                           ("skills/agent-handoff/scripts/lib/routes.json", contracts_lib.build_routes(meta))):
        target = ROOT / file
        if not target.exists() or target.read_text(encoding="utf-8") != expected:
            stale.append(file)
    from workflow_docs import DOCS, workflow_docs

    docs = workflow_docs()
    for path, expected in docs.items():
        if not path.exists() or path.read_text(encoding="utf-8") != expected:
            stale.append(path.relative_to(ROOT).as_posix())
    stale += [p.relative_to(ROOT).as_posix() for p in DOCS.glob("*.md") if p not in docs]
    if stale:
        failures.append(f"pas à jour, lancez uv run scripts/build.py : {', '.join(stale)}")
    # Fournisseurs des descriptions cloud : les quatre à icônes officielles et les hébergeurs dessinables du
    # catalogue commun (shared/providers.json), partout les mêmes.
    catalog = json.loads((ROOT / "shared" / "providers.json").read_text(encoding="utf-8"))
    expected = ["aws", "azure", "gcp", "k8s"] + [k for k, v in catalog["providers"].items() if "diagram" in v]

    def provider_enums(node, where):
        if isinstance(node, dict):
            if isinstance(node.get("enum"), list) and {"aws", "azure"} <= set(node["enum"]) and None not in node["enum"] \
                    and node["enum"] != expected:
                failures.append(f"{where} : fournisseurs {node['enum']}, attendu {expected} (shared/providers.json)")
            for value in node.values():
                provider_enums(value, where)
        elif isinstance(node, list):
            for value in node:
                provider_enums(value, where)
    for name, contract in skills.items():
        provider_enums(contract, f"skills/{name}/contract.json")
    return {"id": "contrats", "skill": "tous", "ok": not failures, "failures": failures, "out": None}


# Skills d'import et d'export : jamais dans le même agent (AGENTS.md, section 4).
IMPORT_SKILLS = {"doc-to-markdown", "markdown-to-obsidian"}
EXPORT_SKILLS = {"markdown-publish"}
NAME = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


VAULT_IMPORT = (r"^\s*(import\s+(lib\.)?vault_ontology\b|from\s+(lib\.)?vault_ontology\s+import|from\s+lib\s+import\s+.*\bvault_ontology\b"
                r'|vault_ontology\s*=\s*require_module\("markdown-to-obsidian",\s*"lib/vault_ontology\.py"\))')


def check_rules() -> dict:
    """Règles mécaniques d'AGENTS.md, celles marquées « vérifiée »."""
    from agents_lib import parse_agent, render_agent, source_agents, split_list

    failures, notices = [], []
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
        if len(text) > MAX_CHARS:
            failures.append(f"{name}/SKILL.md : {len(text)} caractères, plus que le budget de {MAX_CHARS} (lu à chaque "
                            "appel du skill) : déplacez le détail dans references/")
        elif len(text) > NEAR_BUDGET * MAX_CHARS:
            notices.append(f"{name}/SKILL.md : {len(text)} caractères sur {MAX_CHARS}, "
                           "préparez le déplacement du détail dans references/")
        for script in sorted((folder / "scripts").glob("*.py")):
            if not script.read_text(encoding="utf-8").startswith("# /// script"):
                failures.append(f"{name}/scripts/{script.name} : en-tête PEP 723 (# /// script) manquant")
    # Un script n'atteint un autre skill que par skill_paths, et seulement si requires le déclare.
    contracts, generated = contracts_lib.skill_contracts(), set(contracts_lib.generated_libs())
    for name, contract in contracts.items():
        declared = {(need["skill"], need["script"]) for need in contract.get("requires", [])}
        for path in sorted((ROOT / "skills" / name / "scripts").rglob("*.py")):
            if path in generated:
                continue
            code, where = path.read_text(encoding="utf-8"), f"{name}/{path.relative_to(ROOT / 'skills' / name).as_posix()}"
            if re.search(r"parents\[[2-9]\]|parent\.parent\.parent", code):
                failures.append(f"{where} : chemin vers un autre skill, utilisez skill_paths et requires")
            failures += [f"{where} : chemin vers le skill {other}, utilisez skill_paths et requires"
                         for other in re.findall(r'"([a-z0-9-]+)"\s*/\s*"scripts"', code)
                         if other in contracts and other != name]
            failures += [f"{where} : {call}(\"{skill}\", \"{script}\") absent de requires dans contract.json"
                         for call, skill, script in re.findall(
                             r'(find_script|load_module|require_module|require_file|schema_of|run_script)\("([a-z0-9-]+)",\s*"([^"]+)"[,)]', code)
                         if (skill, script) not in declared]
            if re.search(r"\bexport_image\(", code) and ("diagram-export", "export.py") not in declared:
                failures.append(f"{where} : export_image (diagram-export/export.py) absent de requires dans contract.json")
    # Modules et données à source unique (ontologie du vault, espace de travail, modèles locaux, hébergeurs) :
    # une seule copie, dans le skill porteur ; les autres skills la chargent par skill_paths et requires.
    for file, (owner, _) in contracts_lib.SINGLE_SOURCES.items():
        for copy in sorted((ROOT / "skills").glob(f"*/scripts/lib/{file}")):
            if copy.parents[2].name != owner:
                call = "require_module" if file.endswith(".py") else "require_file"
                failures.append(f"{copy.relative_to(ROOT).as_posix()} : copie d'une source unique, chargez-la par "
                                f"{call}(\"{owner}\", \"lib/{file}\") et requires")
    # Un script qui touche au vault passe par l'ontologie : import de vault_ontology et champ vault du contrat.
    for name, contract in contracts.items():
        for path in sorted((ROOT / "skills" / name / "scripts").glob("*.py")):
            uses = re.search(VAULT_IMPORT, path.read_text(encoding="utf-8"), re.M)
            if uses and not contract.get("vault"):
                failures.append(f"{name}/scripts/{path.name} : utilise l'ontologie du vault sans champ vault dans contract.json")
        if contract.get("vault", {}).get("writes") and not any(
                re.search(VAULT_IMPORT, p.read_text(encoding="utf-8"), re.M)
                for p in (ROOT / "skills" / name / "scripts").glob("*.py")):
            failures.append(f"{name} : écrit dans le vault (vault.writes) sans vérifier ses notes avec vault_ontology")
        # Un script qui écrit dans le vault (option --vault) prend celui de la mission par défaut, et aucun autre.
        if contract.get("vault", {}).get("writes"):
            for path in sorted((ROOT / "skills" / name / "scripts").glob("*.py")):
                code = path.read_text(encoding="utf-8")
                if re.search(r'add_argument\("--vault"', code) and "vault_target(" not in code and "vault_args(" not in code \
                        and "def sync(" not in code:
                    failures.append(f"{name}/scripts/{path.name} : option --vault sans workspace.vault_target "
                                    "(vault de la mission par défaut)")
    for name, contract in contracts.items():
        for script in contract.get("scripts", []):
            if script["report"]["format"] == "json" and not script["report"].get("schema"):
                failures.append(f"{name}/{script['name']} : rapport JSON sans schéma dans le contrat")
            report_schema = script["report"].get("schema") or {}
            variants = report_schema.get("anyOf", [report_schema]) if report_schema else []
            if any(v.get("type") != "object" or not {"errors", "warnings"} <= set(v.get("required", []))
                   for v in variants):
                failures.append(f"{name}/{script['name']} : rapport sans objet à errors et warnings obligatoires")
            # Premier argument du usage en .json : description à valider contre un schéma d'entrée.
            words = script["usage"].split()
            at = next((i for i, w in enumerate(words) if w.endswith(script["name"])), len(words))
            first = (words[at + 1:at + 2] or [""])[0]
            if ".json" in first and not script.get("input"):
                failures.append(f"{name}/{script['name']} : lit {first} sans schéma d'entrée (input) dans le contrat")
            if script.get("input") and "--schema" not in script["usage"]:
                failures.append(f"{name}/{script['name']} : option --schema absente du usage")

    # Commande d'un SKILL.md vers le script d'un skill voisin (../<skill>/scripts/<script>) : le script existe et
    # le skill est déclaré dans le contrat (requires ou passage de main).
    for name, contract in contracts.items():
        text = (ROOT / "skills" / name / "SKILL.md").read_text(encoding="utf-8")
        linked = {need["skill"] for need in contract.get("requires", [])} | \
                 {hand["to"] for hand in contract.get("handoffs", [])}
        for other, script in sorted(set(re.findall(r"\.\./([a-z0-9-]+)/scripts/([\w.-]+\.py)", text))):
            if not (ROOT / "skills" / other / "scripts" / script).exists():
                failures.append(f"{name}/SKILL.md : ../{other}/scripts/{script} introuvable")
            elif other not in linked:
                failures.append(f"{name}/SKILL.md : appelle ../{other}/scripts/{script} sans déclarer {other} "
                                "dans requires ou handoffs du contrat")

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
        size = len(src.read_text(encoding="utf-8"))
        if size > MAX_CHARS:
            failures.append(f"agent {name} : {size} caractères, plus que le budget de {MAX_CHARS} (lu à chaque tour) : "
                            "la logique métier va dans les skills")
        elif size > NEAR_BUDGET * MAX_CHARS:
            notices.append(f"agent {name} : {size} caractères sur {MAX_CHARS}, "
                           "préparez le déplacement de la logique dans les skills")
        if "{{niveaux}}" not in src.read_text(encoding="utf-8"):
            failures.append(f"agent {name} : marqueur {{{{niveaux}}}} absent (niveaux et modèles de shared/models.json)")
        commands = meta.get("commands", "").lower()
        failures += [f"agent {name} : commande réseau autorisée « {c} »"
                     for c in ("curl", "wget", "invoke-webrequest") if c in commands]

    # Versions : release-please les monte toutes ensemble, depuis son manifeste.
    plugin_version = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
    released = json.loads((ROOT / ".release-please-manifest.json").read_text(encoding="utf-8")).get(".")
    if released != plugin_version:
        failures.append(f".release-please-manifest.json : version {released}, plugin.json {plugin_version} ; "
                        "la version ne se change pas à la main, release-please la monte")
    config = json.loads((ROOT / "release-please-config.json").read_text(encoding="utf-8"))
    bumped = {extra["path"] for extra in config["packages"]["."].get("extra-files", [])}
    failures += [f"release-please-config.json : {path} porte une version absente de extra-files"
                 for path in ("plugin.json", ".claude-plugin/plugin.json", ".claude-plugin/marketplace.json")
                 if path not in bumped]
    if re.search(r"^## Non publié", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"), re.M):
        failures.append("CHANGELOG.md : section « Non publié » ; le journal est écrit par release-please "
                        "depuis les titres de PR (Conventional Commits)")

    for path in sorted([*(ROOT / "skills").rglob("*"), *(ROOT / "src").rglob("*")]):
        if path.is_file() and path.suffix in {".md", ".py", ".json"}:
            if "puppeteer" in path.read_text(encoding="utf-8", errors="replace").lower():
                failures.append(f"{path.relative_to(ROOT)} : Puppeteer, utilisez Playwright")
    # Aucun envoi ni téléchargement non maîtrisé : pas de bibliothèque qui tire ses modèles d'une source non
    # épinglée (ModelScope...) ni d'extra MarkItDown qui envoie le contenu à un service ; un script de modèle
    # local ou de conversion filtre ses flux réseau.
    for path in sorted((ROOT / "skills").glob("*/scripts/*.py")):
        code = path.read_text(encoding="utf-8")
        header = re.search(r"^# /// script\n(.*?)^# ///", code, re.M | re.S)
        deps = header.group(1).lower() if header else ""
        where = path.relative_to(ROOT).as_posix()
        failures += [f"{where} : dépendance {dep} interdite (modèles téléchargés hors des sources épinglées)"
                     for dep in FORBIDDEN_DEPS if re.search(rf'"{re.escape(dep)}[\[<>=~!"]', deps)]
        failures += [f"{where} : extra markitdown[{extra}] interdit (contenu envoyé à un service)"
                     for extra in FORBIDDEN_EXTRAS if re.search(rf"markitdown\[[^\]]*\b{extra}\b", deps)]
        if re.search(r'"(faster-whisper|ctranslate2|laya|markitdown|docling)', deps) \
                and "model_store.guard_network(" not in code:
            failures.append(f"{where} : bibliothèque de modèle ou de conversion sans model_store.guard_network()")
        # Aucun modèle téléchargé pendant un run : Laya et Docling lisent le cache vérifié.
        if re.search(r'"laya[\[<>=~!"]', deps) and "model_store.laya_models()" not in code:
            failures.append(f"{where} : Laya sans model_store.laya_models() (modèle téléchargé pendant le run)")
        if re.search(r'\["docling"\]|"--from", f?"docling', code) and ("--artifacts-path" not in code or "docling==" not in code):
            failures.append(f"{where} : Docling sans version épinglée ni --artifacts-path "
                            "(modèles téléchargés pendant le run)")
    # Et guard_network() tient.
    guard = ROOT / "skills" / "check-prerequisites" / "scripts" / "lib"  # copie unique de model_store.py
    probe = subprocess.run([sys.executable, "-I", "-c", NETWORK_PROBE, str(guard)],
                           capture_output=True, text=True, encoding="utf-8", timeout=60,
                           env={**os.environ, "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9"})
    if probe.stdout.strip() != "ok":
        failures.append(f"model_store.guard_network() ne filtre pas les flux : {(probe.stdout + probe.stderr).strip()[-300:]}")
    return {"id": "regles", "skill": "tous", "ok": not failures, "failures": failures, "out": None,
            "notices": notices}


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


def report_warnings(report) -> list[str]:
    """Avertissements d'un rapport, ceux de chaque résultat compris."""
    found = list(report.get("warnings", [])) if isinstance(report, dict) else []
    for result in (report.get("results", []) if isinstance(report, dict) else []):
        if isinstance(result, dict):
            found += [str(w) for w in result.get("warnings", [])]
    return found


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    # Règles de complétude de l'utilisateur (~/.myskills/regles.json) ignorées : résultats reproductibles.
    os.environ["MYSKILLS_REGLES"] = ""
    os.environ["MYSKILLS_ABAQUES"] = ""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--only", help="identifiants des cas, séparés par des virgules")
    parser.add_argument("--slow", action="store_true", help="lancer aussi les cas lents")
    parser.add_argument("--keep", action="store_true", help="garder les dossiers de sortie")
    parser.add_argument("--json", action="store_true", help="rapport JSON au lieu du bilan")
    parser.add_argument("--jobs", type=int, default=os.cpu_count() or 1,
                        help="cas lancés en même temps (1 : un par un)")
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
            for notice in results[-1].get("notices", []):
                print(f"      ! {notice}")
    selected = []
    for case in cases:
        if only and case["id"] not in only:
            continue
        if case.get("slow") and not args.slow and not only:
            skipped.append(case["id"])
            continue
        selected.append(case)
    # Les cas sont indépendants (dossier temporaire chacun) : on les lance en
    # parallèle et on affiche les résultats dans l'ordre de cases.json.
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.jobs)) as pool:
        futures = [pool.submit(run_case, case, args.keep) for case in selected]
        for case, future in zip(selected, futures):
            results.append(future.result())
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
