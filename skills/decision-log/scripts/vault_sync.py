# /// script
# requires-python = ">=3.10"
# ///
"""Écrit la mémoire partagée d'un workflow dans un vault Obsidian.

Lit les fichiers qui font foi dans le dossier du workflow (`workflow.json`
et les livrables que la définition du workflow nomme dans `memory` :
catalogue d'exigences, options, décision, ADR) et en tire une note par
exigence, terme du glossaire, option et entrée du journal, une note par
étape soumise avec ses livrables (images et Markdown copiés dans
`Fichiers/` et intégrés), plus une note d'index, reliées par des wikilinks :
un autre agent, une autre session ou l'utilisateur retrouvent dans le vault
l'état du workflow, chaque décision et ce qu'elle concerne. Sans définition,
`memory` vaut celle du workflow `architecture`.

Les notes sont générées (`genere: decision-log` dans le frontmatter) et
réécrites à chaque synchronisation ; celles qui ne correspondent plus à
rien sont supprimées. Aucune autre note du vault n'est touchée. Le vault et
son dossier sont gardés dans `workflow.json` (`journal.py init --vault`) :
`journal.py` synchronise alors après chaque commande.

    uv run scripts/vault_sync.py DOSSIER [--vault VAULT] [--folder DOSSIER_DU_VAULT] [--data DOSSIER_DES_LIVRABLES]
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))
from lib.spec_schema import check, input_schema  # noqa: E402
from skill_paths import require_module, schema_of  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")

# Livrables lus pour les notes métier, par rôle, quand la définition du workflow ne dit rien.
DEFAULT_MEMORY = {"requirements": "exigences.json", "options": "options.json", "decision": "decision.json",
                  "adr": "adr-architecture.md"}
# Schéma de chaque rôle, pris dans le contrat du skill qui écrit le fichier (installé à côté).
WRITERS = {"requirements": ("requirements-catalog", "req_build.py"),
           "options": ("architecture-options", "options_build.py")}
# Livrables d'étape copiés dans le vault et intégrés à la note de l'étape.
EMBEDDED = {".png", ".svg", ".jpg", ".jpeg", ".md"}
IMAGE_WIDTH = 900  # largeur d'affichage des schémas intégrés, en pixels

MARK = "genere: decision-log"
ONTOLOGY = vault_ontology.load()
KIND_LABELS = {"choix": "Choix", "hypothese": "Hypothèse", "question": "Question", "soumission": "Soumission",
               "retour": "Retour", "validation": "Validation", "invalidation": "Invalidation",
               "passage": "Passage de main", "rapport": "Rapport d'agent", "saut": "Étape sautée",
               "annotation": "Annotation"}
REVIEW_HELP = ["Pour valider, mettez la propriété **revue** à `validée`.",
               "Pour demander une reprise, mettez `retour` et écrivez votre retour sous « Votre retour ».",
               "L'agent lit cette note (`journal.py review --from-vault`) : seules la propriété revue et cette "
               "section sont gardées."]
GENERATED = vault_ontology.callout("info", "Note générée", [
    "Mémoire partagée du workflow, générée depuis `workflow.json` et réécrite à chaque étape, sauf la "
    "section « Mes notes » de chaque note : écrivez-y, un callout `> [!question]` ou `> [!retour]` est relu "
    "par l'agent et tracé au journal."], folded=True)
STATUS_LABELS = {"a-faire": "à faire", "en-cours": "en cours", "en-revue": "en revue",
                 "validee": "validée", "a-reprendre": "à reprendre", "sautee": "sautée"}


# Caractères interdits dans un nom de fichier sous Windows, ou qui cassent un wikilink Obsidian.
FORBIDDEN = re.compile(r'[\\/:*?"<>|#^\[\]\x00-\x1f]')
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}


def safe_name(text: str) -> str:
    """Nom de note ou de dossier valable sous Windows, macOS et Linux et dans un wikilink."""
    name = re.sub(r"\s+", " ", FORBIDDEN.sub("-", text)).strip().rstrip(". ")
    if name.split(".")[0].upper() in RESERVED:
        name = f"{name}-"
    return name or "Workflow"


def safe_folder(path: str) -> str:
    """Dossier du vault : chaque niveau (séparé par /) rendu sûr."""
    return "/".join(safe_name(part) for part in re.split(r"[\\/]+", path) if part.strip())


def review_note(target: str, stage: str) -> str:
    """Chemin (sans .md) de la note de revue d'une étape, relatif au vault."""
    return f"{safe_folder(target)}/Revues/Revue {safe_name(stage)}"


def user_part(path: Path, submission: str) -> tuple[str, str]:
    """Propriété revue et section « Votre retour » déjà remplies par l'utilisateur pour cette soumission."""
    if not path.is_file():
        return "", ""
    text = path.read_text(encoding="utf-8", errors="replace")
    head = text.split("\n---", 1)[0]
    if f"soumission: {json.dumps(submission)}" not in head:
        return "", ""
    value = next((line.split(":", 1)[1].strip() for line in head.splitlines() if line.startswith("revue:")), "")
    feedback = text.split("## Votre retour", 1)[1].strip("\n") if "## Votre retour" in text else ""
    return value.strip('"'), feedback.split(vault_ontology.USER_TITLE, 1)[0].rstrip()


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def mentions(text: str, words: list[str]) -> bool:
    """Même règle que req_build.py : sans casse ni accents, pluriel en s ou x admis."""
    text = normalize(text)
    return any(re.search(rf"(?<!\w){re.escape(normalize(w))}[sx]?(?!\w)", text) for w in words if normalize(w))


def load(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    except ValueError:
        return None


def note(meta: dict, body: list[str]) -> str:
    return vault_ontology.render(meta) + "\n" + "\n".join(body).rstrip() + "\n"


def schema_for(role: str) -> dict | None:
    if role == "workflow":
        return input_schema(HERE / "journal.py")
    return schema_of(*WRITERS[role])


def checked(path: Path, schema: dict | None, errors: list[str], warnings: list[str]):
    """Contenu du fichier s'il est conforme à son schéma ; sinon None et les erreurs."""
    value = load(path)
    if value is None:
        if path.exists():
            errors.append(f"{path.name} : JSON illisible")
        return None
    if schema is None:
        warnings.append(f"{path.name} non vérifié : skill qui l'écrit absent")
        return value
    invalid = check(value, schema)
    errors += [f"{path.name} : {e}" for e in invalid[:10]]
    return None if invalid else value


def sync(folder: Path, vault: Path, target: str, data: Path | None = None) -> dict:
    """Écrit les notes ; renvoie le rapport (notes écrites, supprimées, liens cassés). Sous le verrou du vault,
    que partagent tous les skills qui y écrivent."""
    if not Path(vault).is_dir():
        return {"vault": str(vault), "folder": target, "notes": 0, "removed": 0,
                "errors": [f"vault introuvable : {vault}"], "warnings": []}
    try:
        with vault_ontology.vault_lock(vault):
            return _sync(folder, vault, target, data)
    except TimeoutError as error:
        return {"vault": str(vault), "folder": target, "notes": 0, "removed": 0, "errors": [str(error)],
                "warnings": []}


PLACEMENT_LABELS = {"nouvelle": "à créer", "a-faire-evoluer": "à faire évoluer", "a-remplacer": "à remplacer",
                    "en-place": "réutilisée", "externe": "externe"}


def _failed(vault: Path, folder: str, errors: list[str], warnings: list[str]) -> dict:
    return {"vault": str(vault), "folder": folder, "notes": 0, "removed": 0, "errors": errors, "warnings": warnings}


def _alias(text: str) -> str:
    return text.replace("|", "-").replace("]", ")").replace("[", "(")


def _sources(item: dict) -> list[str]:
    return [s["doc"] + (f" : « {s['quote']} »" if s.get("quote") else "") for s in item.get("sources", [])]


class _Sync:
    """Une synchronisation : lit le workflow, compose les notes, les vérifie puis les écrit."""

    def __init__(self, folder: Path, vault: Path, target: str, data: Path | None, state: dict,
                 errors: list[str], warnings: list[str]) -> None:
        self.folder, self.vault, self.target, self.state = folder, vault, target, state
        self.errors, self.warnings = errors, warnings
        data = self.data = data or folder
        self.definition = state.get("definition")
        memory = self.memory = self.definition.get("memory", {}) if self.definition else DEFAULT_MEMORY
        self.catalog = checked(data / memory["requirements"], schema_for("requirements"), errors, warnings) or {} \
            if memory.get("requirements") else {}
        options_schema = schema_for("options") if memory.get("options") else None
        self.options = checked(data / memory["options"], options_schema, errors, warnings) or {} \
            if memory.get("options") else {}
        decision_schema = options_schema["properties"]["decision"] if options_schema else None
        self.decision = (checked(data / memory["decision"], decision_schema, errors, warnings)
                         if memory.get("decision") else None) or self.options.get("decision")
        self.base = safe_folder(target)
        self.files_dir = f"{self.base}/Fichiers"
        self.names: dict[str, str] = {}  # identifiant -> chemin de la note (sans .md), pour les wikilinks
        self.titles: dict[str, str] = {}  # identifiant -> libellé lisible des liens (EF-001 Déclarer un sinistre)
        self.notes: dict[str, str] = {}
        self.metas: dict[str, dict] = {}  # chemin -> frontmatter, vérifié contre l'ontologie avant l'écriture
        self.copies: dict[str, Path] = {}  # chemin dans le vault -> fichier du workflow
        self.stage_notes: list[str] = []
        self.reviews: list[str] = []
        self.name_notes()

    def name_notes(self) -> None:
        """Chemin et libellé de chaque note à venir, pour que les liens se résolvent dans les deux sens."""
        base, names, titles, state = self.base, self.names, self.titles, self.state
        for req in self.catalog.get("requirements", []):
            names[req["id"]] = f"{base}/Exigences/{req['id']}"
            titles[req["id"]] = f"{req['id']} {req['title']}"
        for opt in self.options.get("options", []):
            names[opt["id"]] = f"{base}/Options/Option {opt['id']}"
            titles[opt["id"]] = f"Option {opt['id']} : {opt['name']}"
        self.glossary = self.catalog.get("glossary", [])
        for entry in self.glossary:
            names["terme:" + entry["term"]] = f"{base}/Glossaire/{safe_name(entry['term'])}"
        kept = [r for r in self.catalog.get("requirements", []) if r.get("status", "retenue") == "retenue"]
        self.uses = {g["term"]: [r["id"] for r in kept
                                 if mentions(f"{r['title']} {r['text']}", [g["term"], *g.get("aliases", [])])]
                     for g in self.glossary}
        for entry in state["entries"]:
            names[entry["id"]] = f"{base}/Décisions/{entry['id']}"
            titles[entry["id"]] = f"{entry['id']} {KIND_LABELS[entry['kind']]}"
        self.index = f"{base}/{safe_name(state['title'])}"
        self.labels = {s["id"]: s.get("label") or s["id"] for s in (self.definition or {}).get("stages", [])}
        self.adr = self.data / self.memory["adr"] if self.memory.get("adr") else None
        if self.adr and self.adr.exists():
            names["ADR"] = f"{base}/ADR architecture"
        self.by_ref: dict[str, list[dict]] = {}
        for entry in state["entries"]:
            for ref in entry.get("refs", []):
                self.by_ref.setdefault(ref, []).append(entry)
        self.gaps = {(g, o["id"]): v for o in self.options.get("options", []) for g, v in o.get("gaps", {}).items()}
        self.up = f"Workflow : [[{self.index}|{_alias(state['title'])}]]"

    # Liens

    def note_title(self, ref: str) -> str | None:
        """Titre d'une note du vault citée par son chemin (annotation écrite dans Obsidian), sinon None."""
        path = self.vault / f"{ref}.md"
        if "/" not in ref or not path.is_file():
            return None
        return vault_ontology.heading(vault_ontology.parse(path.read_text(encoding="utf-8", errors="replace"))[1]) \
            or path.stem

    def link(self, ref: str) -> str:
        if ref in self.names:
            return f"[[{self.names[ref]}|{_alias(self.titles.get(ref, ref))}]]"
        title = self.note_title(ref)
        return f"[[{ref}|{_alias(title)}]]" if title else ref

    def linked(self, ids) -> list[tuple[str, str]]:
        return [(self.names[r], r.removeprefix("terme:")) if r in self.names else (r, self.note_title(r))
                for r in ids if r in self.names or self.note_title(r)]

    def decisions(self, ref: str) -> list[str]:
        """Section « Décisions » d'une note citée par des entrées du journal."""
        if not self.by_ref.get(ref):
            return []
        return ["", "## Décisions", ""] + [f"- {self.link(e['id'])} : {e['text']}" for e in self.by_ref[ref]]

    def typed(self, rel: str, kind: str, props: dict, body: list[str], relations: dict | None = None,
              tags=()) -> None:
        """Note typée selon l'ontologie du vault : frontmatter, relations (wikilinks) et tags normalisés."""
        rels = {} if kind == "workflow" else {"workflow": (self.index, self.state["title"])}
        self.metas[rel] = vault_ontology.with_alias(
            vault_ontology.meta(ONTOLOGY, kind, props, {**rels, **(relations or {})}, tags, genere="decision-log"),
            vault_ontology.heading("\n".join(body)), rel)
        self.notes[rel] = note(self.metas[rel], body)

    # Notes

    def compose(self) -> None:
        self.requirement_notes()
        self.option_notes()
        self.glossary_notes()
        self.entry_notes()
        self.adr_note()
        self.stage_notes_()
        self.option_pictures()
        self.review_notes()
        self.index_note()
        # Section « Revues et analyses » : revues, chiffrages, modèles de menaces écrits par d'autres skills.
        hubs = vault_ontology.Hubs(ONTOLOGY, self.vault, {rel: (meta, vault_ontology.heading(self.notes[rel]) or rel)
                                                          for rel, meta in self.metas.items()})
        self.notes = {rel: hubs.text(rel, self.metas[rel]["type"], text) for rel, text in self.notes.items()}

    def requirement_notes(self) -> None:
        names, gaps, link = self.names, self.gaps, self.link
        for req in self.catalog.get("requirements", []):
            rid = req["id"]
            body = [f"# {rid} {req['title']}", "", req["text"], "", self.up, ""]
            if req.get("metric"):
                body += [f"**Mesure** : {req['metric']}", ""]
            terms = [g["term"] for g in self.glossary if rid in self.uses[g["term"]]]
            if terms:
                body += ["**Termes** : " + ", ".join(f"[[{names['terme:' + term]}|{_alias(term)}]]"
                                                     for term in terms), ""]
            body += ["## Sources", ""] + [f"- {s}" for s in _sources(req)] + ([f"- déduite : {req['derived']}"]
                                                                             if req.get("derived") else [])
            if req.get("questions"):
                body += ["", "## Questions", ""] + [f"- {q}" for q in req["questions"]]
            covered = [f"- {link(o['id'])} : "
                       f"{'partielle' if gaps[(rid, o['id'])]['level'] == 'partiel' else 'non couverte'}"
                       f", {gaps[(rid, o['id'])]['note']}"
                       for o in self.options.get("options", []) if (rid, o["id"]) in gaps]
            if covered:
                body += ["", "## Écarts des options", ""] + covered
            body += self.decisions(rid)
            self.typed(names[rid], "exigence",
                       {"id": rid, "nature": req.get("nature") or ("fonctionnelle" if rid.startswith("EF-")
                                                                   else "non-fonctionnelle"),
                        "priorite": req["priority"], "categorie": req.get("category"), "domaine": req.get("domain"),
                        "statut": req.get("status", "retenue")}, body,
                       {"termes": self.linked("terme:" + term for term in terms)})

    def option_notes(self) -> None:
        names, link, decision = self.names, self.link, self.decision
        for opt in self.options.get("options", []):
            chosen = bool(decision and decision.get("option") == opt["id"])
            body = [f"# Option {opt['id']} : {opt['name']}", "", opt["summary"], "", self.up, "",
                    "## Composants", ""] + [f"- {c['label']}" + (f" ({c['tech']})" if c.get("tech") else "")
                                            for c in opt["components"]]
            if opt.get("gaps"):
                body += ["", "## Écarts", ""] + [f"- {link(g)} : couverture {v['level']}e, {v['note']}"
                                                 for g, v in opt["gaps"].items()]
            if opt.get("placement"):
                body += ["", "## Position dans le SI (POS)", ""] + [
                    f"- {p['app']} : {PLACEMENT_LABELS[p['change']]}"
                    + (" dans " + " / ".join(p[k] for k in ("zone", "quartier", "ilot") if p.get(k))
                       if p.get("zone") else "") + (f" (coexiste : {p['coexists']})" if p.get("coexists") else "")
                    for p in opt["placement"]]
            for key, label in (("pros", "Avantages"), ("cons", "Inconvénients"), ("risks", "Risques")):
                if opt.get(key):
                    body += ["", f"## {label}", ""] + [f"- {item}" for item in opt[key]]
            body += self.decisions(opt["id"])
            if chosen and "ADR" in names:
                body += ["", f"Retenue : [[{names['ADR']}|ADR]]"]
            self.typed(names[opt["id"]], "option-architecture", {"id": f"option-{opt['id']}", "retenue": chosen},
                       body, {"ecarts": self.linked(opt.get("gaps", {})),
                              "adr": self.linked(["ADR"]) if chosen else []}, ["architecture"])

    def glossary_notes(self) -> None:
        for entry in self.glossary:
            sources = _sources(entry)
            body = [f"# {entry['term']}", "", entry["definition"], "", self.up]
            if sources:
                body += ["", "## Sources", ""] + [f"- {s}" for s in sources]
            if self.uses[entry["term"]]:
                body += ["", "## Exigences", ""] + [f"- {self.link(r)}" for r in self.uses[entry["term"]]]
            self.typed(self.names["terme:" + entry["term"]], "terme", {"aliases": entry.get("aliases", [])}, body,
                       tags=["glossaire"])

    def entry_notes(self) -> None:
        for entry in self.state["entries"]:
            refs = [self.link(r) for r in entry.get("refs", [])]
            body = [f"# {entry['id']} {KIND_LABELS[entry['kind']]}", "", entry["text"], "", self.up, ""]
            if entry.get("why"):
                body += [f"**Justification** : {entry['why']}", ""]
            if refs:
                body += ["**Concerne** : " + ", ".join(refs), ""]
            if entry.get("files"):
                body += ["**Fichiers** : " + ", ".join(f"`{f}`" for f in entry["files"])]
            if entry.get("via") == "obsidian":
                body += ["", "Écrite par l'utilisateur sous « Mes notes » dans Obsidian." if entry["kind"] in
                         ("annotation", "question")
                         else "Décision prise par l'utilisateur dans sa note de revue Obsidian."]
            self.typed(self.names[entry["id"]], "decision",
                       {"id": entry["id"], "nature": entry["kind"], "etape": entry["stage"],
                        "par": entry["by"], "date": entry["date"]}, body,
                       {"concerne": self.linked(entry.get("refs", []))})

    def adr_note(self) -> None:
        if "ADR" not in self.names:
            return
        text = self.adr.read_text(encoding="utf-8")
        ids = sorted((r["id"] for r in self.catalog.get("requirements", [])), key=len, reverse=True)
        for ref in ids:
            text = re.sub(rf"(?<![\[|/\w-]){re.escape(ref)}(?![\w-])", lambda _, r=ref: self.link(r), text)
        cited = [r for r in ids if f"[[{self.names[r]}|" in text]
        self.typed(self.names["ADR"], "adr", {"statut": "acceptee"}, [text, "", self.up],
                   {"option": self.linked([self.decision["option"]] if self.decision else []),
                    "exigences": self.linked(sorted(cited))}, ["architecture"])

    def drawio_source(self, file: str) -> list[str]:
        """Lien vers la source draw.io d'un PNG exporté (x.drawio.png -> x.drawio), copiée à côté."""
        if not file.lower().endswith(".drawio.png") or not (self.folder / file[:-4]).is_file():
            return []
        self.copies[f"{self.files_dir}/{file[:-4]}"] = self.folder / file[:-4]
        name = Path(file[:-4]).name
        return [f"Source modifiable : [[{self.files_dir}/{file[:-4]}|{name}]] (draw.io).", ""]

    def stage_notes_(self) -> None:
        """Une note par étape soumise : ses livrables, images et Markdown copiés dans Fichiers/ et intégrés."""
        labels, files_dir = self.labels, self.files_dir
        for stage in self.state["stages"]:
            if not stage.get("files"):
                continue
            rel = f"{self.base}/Étapes/{safe_name(labels.get(stage['id'], stage['id']))}"
            body = [f"# {labels.get(stage['id'], stage['id'])}", "", self.up, "",
                    f"Statut : **{STATUS_LABELS[stage['status']]}**.", "", "## Livrables", ""]
            for file in stage["files"]:
                source = self.folder / file
                if source.suffix.lower() in EMBEDDED and source.is_file():
                    copy = f"{files_dir}/{file}"
                    self.copies[copy] = source
                    body += [f"### {file}", "", f"![[{copy}]]" if source.suffix.lower() == ".md"
                             else f"![[{copy}|{IMAGE_WIDTH}]]", ""] + self.drawio_source(file)
                else:
                    body.append(f"- `{file}`")
            self.typed(rel, "etape", {"etape": stage["id"], "statut": stage["status"]}, body)
            self.stage_notes.append(rel)

    def option_pictures(self) -> None:
        """Schéma de chaque option, s'il a été exporté (comme deck_build.py) : intégré à la note de l'option."""
        names, notes, files_dir = self.names, self.notes, self.files_dir
        for index, opt in enumerate(self.options.get("options", [])):
            pictures = [f"schemas/option-{opt['id'].lower()}.drawio.png",
                        "schemas/architectures.drawio.png" if index == 0 else
                        f"schemas/architectures-{index + 1}.drawio.png"]
            found = next((p for p in pictures if (self.folder / p).is_file()), None)
            if found and names.get(opt["id"]) in notes:
                self.copies[f"{files_dir}/{found}"] = self.folder / found
                caption = [f"*Schéma de l'option {opt['id']} : {opt.get('name', opt['id'])}.*", ""] \
                    + self.drawio_source(found)
                notes[names[opt["id"]]] = notes[names[opt["id"]]].rstrip() + "\n\n" + "\n".join(
                    ["## Schéma", "", f"![[{files_dir}/{found}|{IMAGE_WIDTH}]]", ""] + caption).rstrip() + "\n"

    def review_notes(self) -> None:
        state, labels, files_dir = self.state, self.labels, self.files_dir
        for stage in state["stages"]:
            if stage["status"] != "en-revue":
                continue
            submission = next((e for e in reversed(state["entries"])
                               if e["stage"] == stage["id"] and e["kind"] == "soumission"), None)
            if not submission:
                continue
            rel = review_note(self.target, stage["id"])
            value, feedback = user_part(self.vault / f"{rel}.md", submission["id"])
            shown = [f"[[{files_dir}/{f}|{f}]]" if f"{files_dir}/{f}" in self.copies else f"`{f}`"
                     for f in stage.get("files", {})]
            body = [f"# Revue de l'étape {labels.get(stage['id'], stage['id'])}", "", self.up, ""]
            body += vault_ontology.callout("todo", "À vous de relire", REVIEW_HELP)
            body += [f"Soumission {self.link(submission['id'])} : {submission['text']}.", "", "**Fichiers** : "
                     + ", ".join(shown), "", "## Votre retour", "", feedback]
            self.typed(rel, "revue", {"etape": stage["id"], "soumission": submission["id"]}, body)
            self.metas[rel]["revue"] = value  # toujours présente, même vide : l'utilisateur la remplit dans Obsidian
            self.notes[rel] = note(self.metas[rel], body)
            self.reviews.append(rel)

    def index_note(self) -> None:
        state, names, labels, link, decision = self.state, self.names, self.labels, self.link, self.decision
        body = [f"# {state['title']}", ""] + GENERATED + ["## Étapes", "", "| Étape | Statut |", "| --- | --- |"]
        stage_rel = {rel.rsplit("/", 1)[-1]: rel for rel in self.stage_notes}
        for s in state["stages"]:
            name = labels.get(s["id"], s["id"])
            shown = f"[[{stage_rel[safe_name(name)]}\\|{_alias(name)}]]" if safe_name(name) in stage_rel else name
            body.append(f"| {shown} | {STATUS_LABELS[s['status']]} |")
        if self.reviews:
            body += [""] + vault_ontology.callout("todo", "Revues en attente", [
                f"- [[{rel}|{rel.rsplit('/', 1)[-1]}]]" for rel in self.reviews])[:-1]
        requirements = self.catalog.get("requirements", [])
        if requirements:
            body += ["", "## Exigences", "", "| Exigence | Priorité | Statut |", "| --- | --- | --- |"]
            body += [f"| [[{names[r['id']]}\\|{_alias(self.titles[r['id']])}]] | "
                     f"{vault_ontology.label(ONTOLOGY, r['priority'])} | "
                     f"{vault_ontology.label(ONTOLOGY, r.get('status', 'retenue'))} |" for r in requirements]
        if self.options.get("options"):
            body += ["", "## Options", ""] + [f"- {link(o['id'])}" + (" (retenue)" if decision and
                                                                     decision.get("option") == o["id"] else "")
                                             for o in self.options["options"]]
        if self.glossary:
            body += ["", "## Glossaire", ""] + [f"- [[{names['terme:' + g['term']]}|{_alias(g['term'])}]]"
                                               for g in sorted(self.glossary, key=lambda g: normalize(g["term"]))]
        if "ADR" in names:
            body += ["", "## Décision d'architecture", "", f"- [[{names['ADR']}|ADR]]"]
        if state["entries"]:
            body += ["", "## Journal", ""] + [f"- {link(e['id'])} ({labels.get(e['stage'], e['stage'])}, {e['by']}) : "
                                             f"{e['text']}" for e in state["entries"]]
        self.typed(self.index, "workflow", {}, body)

    # Contrôle et écriture

    def invalid(self) -> list[str]:
        """Écarts à l'ontologie du vault (types, propriétés, relations, tags) : s'il y en a, rien n'est écrit."""
        def resolve(path: str):
            if path in self.metas:
                return self.metas[path]["type"]
            if not (self.vault / f"{path}.md").is_file():
                raise KeyError(path)
            return (vault_ontology.parse((self.vault / f"{path}.md").read_text(encoding="utf-8", errors="replace"))[0]
                    or {}).get("type")
        found = []
        for rel, meta in self.metas.items():
            found += [f"{rel} : {e}" for e in vault_ontology.check_meta(ONTOLOGY, meta, generated=True)[0]
                      + vault_ontology.check_targets(ONTOLOGY, meta, resolve)[0]]
        return found

    def write(self) -> None:
        """Écrit notes et copies ; un fichier inchangé n'est pas réécrit (pas de bruit pour Obsidian Sync ou git)."""
        for rel, text in self.notes.items():
            path = self.vault / f"{rel}.md"
            old = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n") if path.is_file() else None
            # La section « Mes notes » de l'utilisateur est reprise de la note en place.
            self.notes[rel] = text = vault_ontology.with_user(text, vault_ontology.user_section(old or ""))
            if old == text:
                continue
            vault_ontology.save(path, text)
        # Copies des livrables : Fichiers/ est entièrement généré (un Markdown copié porte la marque).
        for rel, source in self.copies.items():
            path = self.vault / rel
            content = source.read_bytes()
            if source.suffix.lower() == ".md":
                content = (f"---\n{MARK}\nsource: {json.dumps(source.name)}\n---\n\n").encode("utf-8") + content
            if path.is_file() and path.read_bytes() == content:
                continue
            vault_ontology.save(path, content)

    def clean(self) -> int:
        """Supprime les notes et copies générées qui ne correspondent plus à rien ; rend leur nombre."""
        vault, removed = self.vault, 0
        for path in (vault / self.base).rglob("*.md"):
            rel = path.relative_to(vault).with_suffix("").as_posix()
            if rel not in self.notes and path.relative_to(vault).as_posix() not in self.copies:
                old = path.read_text(encoding="utf-8", errors="replace").replace("\r\n", "\n")
                if not old.startswith(f"---\n{MARK}\n"):
                    continue
                if vault_ontology.user_section(old):
                    self.warnings.append(f"{rel} n'a plus lieu d'être, gardée pour vos notes : "
                                         "déplacez-les puis supprimez-la")
                    continue
                path.unlink()
                removed += 1
        if (vault / self.files_dir).is_dir():
            for path in sorted((vault / self.files_dir).rglob("*"), reverse=True):
                if path.is_file() and path.relative_to(vault).as_posix() not in self.copies:
                    path.unlink()
                    removed += 1
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
        return removed

    def broken(self) -> list[str]:
        """Wikilinks écrits qui ne pointent vers aucune note ni aucun fichier."""
        return sorted({target for text in self.notes.values() for target in re.findall(r"\[\[([^|\]\\]+)", text)
                       if not (self.vault / f"{target}.md").exists() and not (self.vault / target).is_file()})


def _sync(folder: Path, vault: Path, target: str, data: Path | None = None) -> dict:
    errors: list[str] = []
    warnings: list[str] = []
    state = checked(folder / "workflow.json", schema_for("workflow"), errors, warnings)
    if not state:
        return _failed(vault, target, errors or [f"{folder / 'workflow.json'} illisible : lancez journal.py init"],
                       warnings)
    if not vault.is_dir():
        return _failed(vault, target, [f"vault introuvable : {vault}"], warnings)
    sync = _Sync(folder, vault, target, data, state, errors, warnings)
    sync.compose()
    invalid = sync.invalid()
    if invalid:
        return _failed(vault, sync.base, errors + ["note hors ontologie, rien n'est écrit : " + e
                                                   for e in invalid[:10]], warnings)
    sync.write()
    removed = sync.clean()
    # Tableaux Obsidian Bases du workflow (vues de l'ontologie), avant la vérification des liens.
    vault_ontology.write_base(ONTOLOGY, vault, sync.base)
    errors += [f"lien cassé : [[{target}]]" for target in sync.broken()]
    return {"vault": str(vault), "folder": sync.base, "notes": len(sync.notes), "removed": removed,
            "errors": errors, "warnings": warnings}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", type=Path, help="dossier du workflow (workflow.json)")
    parser.add_argument("--vault", type=Path, help="vault Obsidian (défaut : celui de workflow.json)")
    parser.add_argument("--folder", dest="target", help="dossier des notes dans le vault (défaut : celui de "
                                                         "workflow.json, sinon Workflows/<titre>)")
    parser.add_argument("--data", type=Path, help="dossier des livrables (exigences.json, options.json, "
                                                   "decision.json, adr-architecture.md), défaut : DOSSIER")
    args = parser.parse_args()
    state = load(args.folder / "workflow.json") or {}
    memory = state.get("memory") or {}
    vault = args.vault or (Path(memory["vault"]) if memory.get("vault") else None)
    if not vault:
        print(json.dumps({"vault": "", "folder": "", "notes": 0, "removed": 0,
                          "errors": ["vault inconnu : --vault, ou journal.py init --vault"], "warnings": []},
                         ensure_ascii=False))
        return 1
    target = args.target or memory.get("folder") or f"Workflows/{safe_name(state.get('title', args.folder.resolve().name))}"
    report = sync(args.folder, vault, target, args.data)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
