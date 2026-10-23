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
LIB_USERS = {"local_tools.py": ["check-prerequisites", "diagram-export", "markdown-publish"],
             "script_report.py": ["doc-to-markdown", "diagram-export", "markdown-publish", "markdown-to-obsidian",
                                  "drawio-diagram"]}


def generated_libs() -> dict[Path, str]:
    """Copie attendue de chaque module partagé et de la charte des couleurs, par chemin."""
    shared = REPO / "shared" / "scripts"
    files: dict[Path, str] = {}
    validator = (shared / "spec_schema.py").read_text(encoding="utf-8")
    for name, contract in skill_contracts().items():
        if any(script.get("input") for script in contract["scripts"]):
            files[REPO / "skills" / name / "scripts" / "lib" / "spec_schema.py"] = validator
    for module, skills in LIB_USERS.items():
        text = (shared / module).read_text(encoding="utf-8")
        for name in skills:
            files[REPO / "skills" / name / "scripts" / "lib" / module] = text
    # Schémas des messages entre agents, pour journal.py handoff et report.
    for name in ("handoff", "agent-report"):
        files[REPO / "skills" / "decision-log" / "scripts" / "lib" / f"{name}.schema.json"] = \
            (SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8")
    # Couleurs de la charte, pour check_drawio.py : une seule source, shared/references/style.md.
    style = (REPO / "shared" / "references" / "style.md").read_text(encoding="utf-8")
    colors = sorted({c.lower() for c in re.findall(r"#[0-9a-fA-F]{6}\b", style)})
    files[REPO / "skills" / "drawio-diagram" / "scripts" / "lib" / "charter.json"] = \
        json.dumps({"_source": "shared/references/style.md, généré par scripts/build.py", "colors": colors},
                   ensure_ascii=False, indent=2) + "\n"
    return files


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


def render_skill(contract: dict) -> str:
    """Section courte : les champs des rapports restent dans contract.json (le
    modèle les lit de toute façon dans la sortie des scripts)."""
    lines = ["## Contrat", "",
             "Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).", "",
             "- **Entrées** : " + " ; ".join(contract["inputs"]) + ".",
             "- **Sorties** : " + " ; ".join(contract["outputs"]) + "."]
    for script in contract["scripts"]:
        report = script["report"]
        tag = " (maintenance du dépôt)" if script.get("maintenance") else ""
        kind = {"json": "rapport JSON", "text": "rapport texte", "none": "pas de rapport"}[report["format"]]
        codes = " ; ".join(f"{code} {meaning}" for code, meaning in script["exit_codes"].items())
        lines.append(f"- **`{script['name']}`**{tag} : {script['role']} {kind[0].upper() + kind[1:]}, "
                     f"codes de sortie : {codes}.")
        if script.get("input"):
            lines.append("  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors "
                         "liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.")
    if not contract["scripts"]:
        lines.append("- **Scripts** : aucun ; la validation passe par le skill suivant.")
    for handoff in contract["handoffs"]:
        target = {"skill": f"au skill `{handoff['to']}`", "agent": f"à l'agent `{handoff['to']}`",
                  "utilisateur": "à l'utilisateur"}[handoff["kind"]]
        lines.append(f"- **Passe la main** {target} : {handoff['when']}.")
    return "\n".join(lines) + "\n"


def render_agent(contract: dict) -> str:
    lines = ["## Contrat", "",
             "Généré depuis `src/agents/" + contract["agent"] + ".contract.json`, qui fait foi.", "",
             "- **Reçoit** : " + " ; ".join(contract["receives"]) + ".",
             "- **Produit** : " + " ; ".join(contract["produces"]) + "."]
    if contract.get("never"):
        lines.append("- **Ne fait jamais** : " + " ; ".join(contract["never"]) + ".")
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
              "avec `journal.py handoff|report DOSSIER --json '<une ligne>'` (skill",
              "`decision-log`, DOSSIER = dossier de travail) et corrige jusqu'à zéro",
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
        body = render_skill(contract).split("\n", 2)[2].replace("](contract.json)", f"](skills/{name}/contract.json)")
        lines += [f"### `{name}`", "", skill_description(name), "", body.strip(), ""]
    return "\n".join(lines).rstrip() + "\n"
