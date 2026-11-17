"""Contrats d'interface : lecture des contract.json et rendu en Markdown.

Les fichiers JSON font foi :
    skills/<nom>/contract.json            contrat d'un skill (shared/schemas/skill-contract.schema.json)
    src/agents/<nom>.contract.json        contrat d'un agent (shared/schemas/agent-contract.schema.json)
    shared/schemas/handoff.schema.json    message de passage entre agents
    shared/schemas/agent-report.schema.json  rapport final d'un agent
La section « Contrat » des SKILL.md et des agents, CATALOG.md et catalog.json
en sont générés par scripts/build.py.
"""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCHEMAS = REPO / "shared" / "schemas"
SECTION = re.compile(r"^## Contrat\n.*?(?=^## |\Z)", re.S | re.M)
FRONTMATTER = re.compile(r"^---\n(.*?)\n---\n", re.S)

# Modules partagés (shared/scripts/) copiés dans scripts/lib/ des skills qui s'en servent.
LIB_USERS = {"local_tools.py": ["check-prerequisites", "diagram-export", "markdown-publish", "mockup-to-html"],
             "script_report.py": ["architecture-dossier", "doc-to-markdown", "diagram-export", "markdown-publish", "markdown-to-obsidian",
                                  "drawio-diagram", "mockup-to-html"],
             "external_skill.py": ["check-prerequisites", "markdown-publish", "architecture-review"],
             "text_tools.py": ["architecture-dossier", "architecture-options", "architecture-review", "data-model", "decision-log",
                               "domain-design", "markdown-publish", "meeting-notes", "operations-dossier", "process-diagram", "requirements-catalog",
                               "solution-estimate", "tender-response", "test-plan", "threat-model",
                               "well-architected-review"],
             "workflow_chart.py": ["decision-log"],
             "drawio_xml.py": ["drawio-diagram", "cloud-architecture", "urbanization-map", "process-diagram"]}
# Modules et données partagés à source unique : une seule copie, dans le skill porteur ; les autres skills
# les chargent par skill_paths (require_module, require_file) et les déclarent dans requires.
# Fichier de scripts/lib/ -> (skill porteur, source dans shared/ ou None si elle vit dans le skill).
SINGLE_SOURCES = {
    "vault_ontology.py": ("markdown-to-obsidian", None),
    "vault-ontology.json": ("markdown-to-obsidian", None),
    "workspace.py": ("mission-workspace", REPO / "shared" / "scripts" / "workspace.py"),
    "mission.schema.json": ("mission-workspace", SCHEMAS / "mission.schema.json"),
    "rules.schema.json": ("mission-workspace", SCHEMAS / "rules.schema.json"),
    "abaques.schema.json": ("mission-workspace", SCHEMAS / "abaques.schema.json"),
    "model_store.py": ("check-prerequisites", REPO / "shared" / "scripts" / "model_store.py"),
    "model-sources.json": ("check-prerequisites", REPO / "shared" / "model-sources.json"),
    "model-sources.schema.json": ("check-prerequisites", SCHEMAS / "model-sources.schema.json"),
    "providers.json": ("cloud-architecture", REPO / "shared" / "providers.json"),
}
VAULT_SKILL = SINGLE_SOURCES["vault_ontology.py"][0]
VAULT_ONTOLOGY = REPO / "skills" / VAULT_SKILL / "scripts" / "lib" / "vault-ontology.json"
VAULT_MODULE = "lib/vault_ontology.py"
# Skills qui chargent l'espace de travail (workspace.py) en plus de ceux à champ vault : ils gardent leur
# copie de spec_schema.py, que workspace.py importe.
WORKSPACE_USERS = ["agent-handoff", "api-contract", "mockup-to-html"]

def generated_libs() -> dict[Path, str]:
    """Copie attendue de chaque module partagé et de la charte des couleurs, par chemin."""
    shared = REPO / "shared" / "scripts"
    files: dict[Path, str] = {}
    validator = (shared / "spec_schema.py").read_text(encoding="utf-8")
    for name, contract in skill_contracts().items():
        # Aussi pour un skill qui valide l'entrée d'un skill requis (requires), ou le plan rendu par un
        # skill externe (markdown-publish).
        if any(script.get("input") for script in contract["scripts"]) or contract.get("requires") \
                or contract.get("vault") or name == "markdown-publish":
            files[REPO / "skills" / name / "scripts" / "lib" / "spec_schema.py"] = validator
    for module, skills in LIB_USERS.items():
        text = (shared / module).read_text(encoding="utf-8")
        for name in skills:
            files[REPO / "skills" / name / "scripts" / "lib" / module] = text
    # Sources uniques : la seule copie, dans le skill porteur.
    for module, (owner, source) in SINGLE_SOURCES.items():
        if source is not None:
            files[REPO / "skills" / owner / "scripts" / "lib" / module] = source.read_text(encoding="utf-8")
    # spec_schema.py, importé par workspace.py et model_store.py, pour leurs porteurs et les skills qui les chargent.
    for name, contract in skill_contracts().items():
        if contract.get("vault") or name in WORKSPACE_USERS + ["mission-workspace", "check-prerequisites"]:
            files[REPO / "skills" / name / "scripts" / "lib" / "spec_schema.py"] = validator
    # Accès déclaré aux scripts des autres skills (champ requires du contrat).
    paths = (shared / "skill_paths.py").read_text(encoding="utf-8")
    for name, contract in skill_contracts().items():
        if contract.get("requires"):
            files[REPO / "skills" / name / "scripts" / "lib" / "skill_paths.py"] = paths
    # Contrats des skills externes (shared/external/), lus par external_skill.py.
    for path in sorted((REPO / "shared" / "external").glob("*.contract.json")):
        for name in LIB_USERS["external_skill.py"]:
            files[REPO / "skills" / name / "scripts" / "lib" / path.name] = path.read_text(encoding="utf-8")
    # Schémas des messages entre agents, pour check_message.py (agent-handoff), liste des agents à jour.
    enums = agent_enums()
    for name in ("handoff", "agent-report"):
        files[REPO / "skills" / "agent-handoff" / "scripts" / "lib" / f"{name}.schema.json"] = \
            enums[SCHEMAS / f"{name}.schema.json"]
    # Couleurs de la charte, pour check_drawio.py : une seule source, shared/references/style.md.
    style = (REPO / "shared" / "references" / "style.md").read_text(encoding="utf-8")
    colors = sorted({c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", style)})
    files[REPO / "skills" / "drawio-diagram" / "scripts" / "lib" / "charter.json"] = \
        json.dumps({"_source": "shared/references/style.md, généré par scripts/build.py", "colors": colors},
                   ensure_ascii=False, indent=2) + "\n"
    return files


def shared_inputs() -> dict[Path, str]:
    """Contrats dont un script lit la même entrée qu'un autre script, du même skill ou d'un autre (`input.same_as`) :
    le schéma est recopié de la source, une seule définition à faire évoluer."""
    contracts = skill_contracts()
    files: dict[Path, str] = {}
    for name, contract in contracts.items():
        changed = False
        for script in contract["scripts"]:
            source = (script.get("input") or {}).get("same_as")
            if not source:
                continue
            if source.startswith("shared/schemas/"):
                schema_ = json.loads((REPO / source).read_text(encoding="utf-8"))
            else:
                skill, _, file = source.partition("/")
                origin = next((s for s in contracts.get(skill, {}).get("scripts", []) if s["name"] == file), None)
                schema_ = ((origin or {}).get("input") or {}).get("schema")
            if schema_ is not None and script["input"].get("schema") != schema_:
                script["input"]["schema"], changed = schema_, True
        if changed:
            files[REPO / "skills" / name / "contract.json"] = json.dumps(contract, ensure_ascii=False, indent=2) + "\n"
    return files


AGENT_ENUM = re.compile(r'"enum": \[((?:"[a-z0-9-]+", )*"[a-z0-9-]+")\]')


def agent_enums() -> dict[Path, str]:
    """Schémas des messages et des contrats d'agent, avec la liste des agents à jour :
    ajouter un agent (src/agents/<nom>.contract.json) suffit, build.py met les listes à jour."""
    agents = sorted(agent_contracts())
    files: dict[Path, str] = {}
    for name in ("agent-contract", "handoff", "agent-report"):
        path = SCHEMAS / f"{name}.schema.json"
        text = path.read_text(encoding="utf-8")

        def fix(match: re.Match) -> str:
            old = json.loads(f"[{match.group(1)}]")
            if sum(value in agents for value in old) * 2 < len(old):
                return match.group(0)  # liste d'autre chose que des agents
            new = [a for a in old if a in agents] + [a for a in agents if a not in old]
            return '"enum": ' + json.dumps(new, ensure_ascii=False)

        files[path] = AGENT_ENUM.sub(fix, text)
    return files


GENERATED_MARK = "# Copies générées par scripts/build.py (ne pas modifier) : repliées dans les diffs de PR."


def gitattributes() -> dict[Path, str]:
    """.gitattributes : les copies de generated_libs() marquées linguist-generated, pour que GitHub replie
    leurs diffs ; un motif par nom de fichier quand toutes ses occurrences sont des copies."""
    path = REPO / ".gitattributes"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    head = text.split(GENERATED_MARK)[0].rstrip("\n")
    generated = {p.relative_to(REPO).as_posix() for p in generated_libs()}
    names = sorted({p.rsplit("/", 1)[1] for p in generated if p.startswith("skills/")})
    lines = []
    for name in names:
        every = {p.relative_to(REPO).as_posix() for p in REPO.glob(f"skills/*/scripts/lib/{name}")}
        mine = {p for p in generated if p.endswith("/" + name)}
        lines += [f"skills/*/scripts/lib/{name} linguist-generated=true"] if every <= mine \
            else [f"{p} linguist-generated=true" for p in sorted(mine)]
    return {path: "\n".join(([head, ""] if head else []) + [GENERATED_MARK] + lines) + "\n"}


def plugin_manifests() -> dict[Path, str]:
    """Manifestes Claude Code générés depuis plugin.json (Agent Plugins), qui fait foi :
    même nom, version, description et mots-clés partout."""
    source = json.loads((REPO / "plugin.json").read_text(encoding="utf-8"))
    claude = {"name": source["name"], "version": source["version"], "description": source["description"],
              "license": source["license"], "author": {"name": "RenaudVanhille"},
              "repository": "https://github.com/RenaudVanhille/myskills", "keywords": source["keywords"]}
    market = {"name": source["name"], "description": source["description"], "owner": {"name": "RenaudVanhille"},
              "plugins": [{"name": source["name"], "source": "./", "version": source["version"],
                           "description": source["description"]}]}
    dump = lambda value: json.dumps(value, ensure_ascii=False, indent=2) + "\n"  # noqa: E731
    return {REPO / ".claude-plugin" / "plugin.json": dump(claude),
            REPO / ".claude-plugin" / "marketplace.json": dump(market)}


# Exemples remplis, montrés aux agents et vérifiés contre les schémas par tests/run.py.
HANDOFF_EXAMPLE = {
    "agent": "schema-designer",
    "objective": "Recréer en draw.io le schéma du flux de paiement extrait du document.",
    "files": ["sortie/attachments/architecture-1.png", "sortie/architecture.md"],
    "audience": "technique",
    "destination": "confluence",
    "output": "sortie/schemas/",
    "constraints": ["garder les noms des composants du document"],
}
REPORT_EXAMPLE = {
    "agent": "document-extractor",
    "status": "partiel",
    "files": ["sortie/architecture.md", "sortie/attachments/architecture-1.png"],
    "tools": "MarkItDown : document Word avec texte, tableaux et images.",
    "level": "moyen",
    "corrections": ["en-tête de tableau vide remplacé par la première ligne"],
    "todo": ["le schéma reste une image"],
    "next": HANDOFF_EXAMPLE,
}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def skill_contracts() -> dict[str, dict]:
    return {path.parent.name: load(path) for path in sorted((REPO / "skills").glob("*/contract.json"))}


def external_contracts() -> dict[str, dict]:
    """Skills installés à part, connus par leur seul contrat d'interface (shared/external/)."""
    return {path.name.removesuffix(".contract.json"): load(path)
            for path in sorted((REPO / "shared" / "external").glob("*.contract.json"))}


def agent_contracts() -> dict[str, dict]:
    return {path.name.removesuffix(".contract.json"): load(path)
            for path in sorted((REPO / "src" / "agents").glob("*.contract.json"))}


def schema(name: str) -> dict:
    return load(SCHEMAS / f"{name}.schema.json")


def type_label(prop: dict) -> str:
    if "enum" in prop:
        return " | ".join("null" if v is None else str(v) for v in prop["enum"])
    kind = prop.get("type", "objet")
    kinds = kind if isinstance(kind, list) else [kind]
    names = {"string": "texte", "integer": "entier", "number": "nombre", "boolean": "booléen",
             "array": "liste", "object": "objet", "null": "null"}
    return " ou ".join(names.get(k, k) for k in kinds)


def object_variants(report_schema: dict) -> list[dict]:
    """Variantes d'objet d'un rapport (liste d'objets ou objet, avec anyOf)."""
    node = report_schema.get("items", report_schema)
    return node.get("anyOf", [node])


def fields_line(obj: dict) -> str:
    required = obj.get("required", [])
    parts = [f"`{name}` ({type_label(prop)})" for name, prop in obj.get("properties", {}).items()
             if name in required]
    optional = [f"`{name}`" for name in obj.get("properties", {}) if name not in required]
    return ", ".join(parts) + (f" ; facultatifs : {', '.join(optional)}" if optional else "")


def render_skill(contract: dict, full: bool = False) -> str:
    """Section courte : les champs des rapports restent dans contract.json (le
    modèle les lit de toute façon dans la sortie des scripts). Dans SKILL.md,
    lu à chaque appel du skill, les codes de sortie sont résumés (0 succès,
    1 erreur, rapport à lire) ; CATALOG.md (full) les garde en entier."""
    lines = ["## Contrat", "",
             "Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).", "",
             f"- **Niveau** : {contract['level']} ({LEVEL_HINTS[contract['level']]}).",
             "- **Entrées** : " + " ; ".join(contract["inputs"]) + ".",
             "- **Sorties** : " + " ; ".join(contract["outputs"]) + "."]
    for script in contract["scripts"]:
        report = script["report"]
        tag = " (maintenance du dépôt)" if script.get("maintenance") else ""
        kind = {"json": "rapport JSON", "text": "rapport texte", "none": "pas de rapport"}[report["format"]]
        codes = " ; ".join(f"{code} {meaning}" for code, meaning in script["exit_codes"].items())
        if full:
            lines.append(f"- **`{script['name']}`**{tag} : {script['role']} {kind[0].upper() + kind[1:]}, "
                         f"codes de sortie : {codes}.")
            if script.get("input"):
                lines.append("  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors "
                             "liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.")
            continue
        checked = " ; description validée, `--schema` affiche son JSON Schema" if script.get("input") else ""
        lines.append(f"- **`{script['name']}`**{tag} : {script['role']} {kind[0].upper() + kind[1:]} "
                     f"(0 succès, 1 erreur{checked}).")
    if contract["scripts"] and not full:
        lines.append("- **Lancement** : `uv run \"<dossier du skill>/scripts/<script>\" ...`, chemin complet écrit "
                     "dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent "
                     "y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du "
                     "dossier de travail, jamais dans le dossier temporaire du système.")
    if not contract["scripts"]:
        lines.append("- **Scripts** : aucun ; la validation passe par le skill suivant.")
    for need in contract.get("requires", []):
        mode = "facultatif : sans lui, avertissement" if need.get("optional") else "obligatoire"
        lines.append(f"- **Dépend de** `{need['skill']}` (`{need['script']}`, {mode}) : {need['why']}.")
    vault = contract.get("vault")
    if vault:
        parts = [f"écrit les notes de type {', '.join(f'`{k}`' for k in vault['writes'])}"] if vault.get("writes") else []
        parts += ["lit les notes typées"] if vault.get("reads") else []
        lines.append(f"- **Vault Obsidian** : {' ; '.join(parts)}, selon l'ontologie du vault "
                     "(`vault_ontology.py` du skill markdown-to-obsidian).")
    for handoff in contract["handoffs"]:
        target = {"skill": f"au skill `{handoff['to']}`", "agent": f"à l'agent `{handoff['to']}`",
                  "utilisateur": "à l'utilisateur",
                  "externe": f"au skill externe `{handoff['to']}` (installé à part, contrat "
                             f"`shared/external/{handoff['to']}.contract.json`)"}[handoff["kind"]]
        lines.append(f"- **Passe la main** {target} : {handoff['when']}.")
    return "\n".join(lines) + "\n"


LEVEL_HINTS = {"simple": "modèle léger", "moyen": "modèle standard", "complexe": "modèle puissant"}


def render_agent(contract: dict) -> str:
    lines = ["## Contrat", "",
             "Généré depuis `src/agents/" + contract["agent"] + ".contract.json`, qui fait foi.", "",
             f"- **Niveau** : {contract['level']} ({LEVEL_HINTS[contract['level']]}, `shared/models.json`).",
             "- **Reçoit** : " + " ; ".join(contract["receives"]) + ".",
             "- **Produit** : " + " ; ".join(contract["produces"]) + "."]
    if contract.get("never"):
        lines.append("- **Ne fait jamais** : " + " ; ".join(contract["never"]) + ".")
    lines.append("- **Fichiers** : un livrable se reprend sur place, sans copie de sauvegarde à côté (`.avant-*`, "
                 "`.v1-*`, `.before-*`) : `journal.py` garde chaque version validée dans `.historique/`. Les fichiers "
                 "de travail (descriptions provisoires, rendus et sorties de vérification) vont dans `.myskills-tmp/` du "
                 "dossier de travail, jamais dans le dossier temporaire du système (`/tmp`, `%TEMP%`) : hors du "
                 "dossier, chaque écriture demande une approbation. Dans un workflow, `journal.py submit` le vide ; "
                 "sinon, supprime-le avant de rendre la main.")
    lines += ["- **Passe la main** :", "", "| Agent | Quand | À transmettre |", "| --- | --- | --- |"]
    lines += [f"| `{h['to']}` | {h['when']} | {' ; '.join(h['send'])} |" for h in contract["handoffs"]]
    handoff, report = schema("handoff"), schema("agent-report")
    lines += ["", "Les demandes que tu reçois et celles que tu envoies suivent le **message de",
              "passage** (JSON). Champs : " + fields_line(handoff) + ". Si ton outil permet",
              "d'appeler un autre agent, envoie-lui ce message ; sinon, donne-le à",
              "l'utilisateur en lui indiquant l'agent à lancer.", "",
              "Termine toujours par le **rapport final**, en JSON sur une ligne. Champs : "
              + fields_line(report) + " ; `next` est un message de passage, ou null s'il n'y a",
              "rien à passer. Exemple, avec un message de passage dans `next` :", "",
              "```json", json.dumps(REPORT_EXAMPLE, ensure_ascii=False), "```", "",
              "Avant de l'envoyer, valide chaque message de passage et le rapport final",
              "avec `check_message.py handoff|report DOSSIER --json '<une ligne>'`",
              "(skill `agent-handoff`, DOSSIER = dossier de travail) et corrige jusqu'à zéro",
              "erreur : schéma respecté, fichiers cités existants. Dans un dossier de",
              "workflow, la commande les trace aussi au journal."]
    return "\n".join(lines) + "\n"


def replace_section(text: str, section: str, before: str | None = None) -> str:
    """Remplace la section « Contrat », ou l'insère avant le titre `before`
    (sinon avant le premier titre de niveau 2, sinon à la fin)."""
    if SECTION.search(text):
        return SECTION.sub(lambda _: section + "\n", text, count=1)
    anchor = text.find(f"\n{before}\n") if before else -1
    if anchor == -1:
        anchor = text.find("\n## ")
    if anchor == -1:
        return text.rstrip() + "\n\n" + section
    return text[:anchor + 1] + section + "\n" + text[anchor + 1:]


def skill_description(skill: str) -> str:
    text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    meta = dict(re.findall(r'^(\w+):\s*"?(.*?)"?\s*$', FRONTMATTER.match(text).group(1), re.M))
    return meta["description"]


def build_catalog_json(agents_meta: dict[str, dict]) -> str:
    data = {
        "name": "myskills",
        "schemas": {name: f"shared/schemas/{name}.schema.json"
                    for name in ("skill-contract", "agent-contract", "handoff", "agent-report")},
        "agents": [{**contract, "description": agents_meta[name]["description"].strip('"'),
                    "skills": [s.strip() for s in agents_meta[name].get("skills", "").split(",") if s.strip()]}
                   for name, contract in agent_contracts().items()],
        "skills": [{**contract, "description": skill_description(name), "path": f"skills/{name}"}
                   for name, contract in skill_contracts().items()],
    }
    return json.dumps(data, ensure_ascii=False, indent=2) + "\n"


def build_routes(agents_meta: dict[str, dict]) -> str:
    """Catalogue réduit au routage (agents, workflows, skills : nom, niveau, description, entrées), pour
    route.py (agent-handoff) : l'agent orientation choisit sans lire catalog.json en entier. Le niveau d'un
    workflow est celui de l'agent qui le déroule : l'agent orientation le lance à ce niveau."""
    def short(text: str) -> str:
        text = text.strip('"')
        return text.split(". ")[0].rstrip(".") + "."
    workflows = []
    for path in sorted((REPO / "skills" / "decision-log" / "workflows").glob("*.json")):
        definition = load(path)
        workflows.append({"name": definition["name"], "agent": "architecture-workflow",
                          "level": agent_contracts()["architecture-workflow"]["level"], "title": definition["title"],
                          "description": definition["description"],
                          "stages": [s["id"] + (" (facultative)" if s.get("facultative") else "")
                                     for s in definition["stages"]],
                          "inputs": definition["stages"][0].get("inputs", []),
                          # Les skills d'une étape confiée à un agent spécialisé (schema-designer...) restent à cet
                          # agent : ils ne font pas concurrence à l'agent sur son propre vocabulaire.
                          "match": " ".join([s["label"] + ("" if s.get("agent") else " " + " ".join(s.get("skills", [])))
                                             for s in definition["stages"]] + definition.get("keywords", []))})
    data = {
        "_doc": "Fichier généré par scripts/build.py depuis les contrats, les agents et les workflows : ne pas modifier.",
        "agents": [{"name": name, "level": contract["level"], "description": short(agents_meta[name]["description"]),
                    "receives": contract["receives"],
                    # Texte de classement seulement (route.py ne le rend pas) : la description entière.
                    "match": agents_meta[name]["description"].strip('"')}
                   for name, contract in agent_contracts().items() if name != "orientation"],
        "workflows": workflows,
        "skills": [{"name": name, "level": contract["level"], "description": short(skill_description(name)),
                    "inputs": contract["inputs"], "match": skill_description(name)}
                   for name, contract in skill_contracts().items()],
    }
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def build_catalog_md(agents_meta: dict[str, dict]) -> str:
    lines = ["# Catalogue des agents et des skills", "",
             "Fichier généré par `scripts/build.py` : ne pas le modifier à la main. Les",
             "contrats qui font foi sont en JSON : `skills/<nom>/contract.json`,",
             "`src/agents/<nom>.contract.json` et les schémas de `shared/schemas/`. La",
             "version machine de ce catalogue est [`catalog.json`](catalog.json).", "",
             "## Messages entre agents", "",
             "- Message de passage : [`shared/schemas/handoff.schema.json`](shared/schemas/handoff.schema.json).",
             "  Champs : " + fields_line(schema("handoff")) + ".",
             "- Rapport final : [`shared/schemas/agent-report.schema.json`](shared/schemas/agent-report.schema.json).",
             "  Champs : " + fields_line(schema("agent-report")) + ".", "", "## Agents", ""]
    for name, contract in agent_contracts().items():
        meta = agents_meta[name]
        body = render_agent(contract).split("\n", 2)[2]
        body = body[:body.index("\nLes demandes que tu reçois")].strip()
        skills = ", ".join(f"`{s.strip()}`" for s in meta.get("skills", "").split(",") if s.strip())
        lines += [f"### `{name}`", "", meta["description"].strip('"'), "", f"**Skills** : {skills}", "", body, ""]
    lines += ["## Skills", ""]
    for name, contract in skill_contracts().items():
        body = render_skill(contract, full=True).split("\n", 2)[2].replace("](contract.json)", f"](skills/{name}/contract.json)")
        lines += [f"### `{name}`", "", skill_description(name), "", body.strip(), ""]
    return "\n".join(lines).rstrip() + "\n"
