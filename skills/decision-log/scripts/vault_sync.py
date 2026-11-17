# /// script
# requires-python = ">=3.10"
# ///
"""Écrit la mémoire partagée d'un workflow dans un vault Obsidian.

Lit les fichiers qui font foi dans le dossier du workflow (`workflow.json`
et les livrables que la définition du workflow nomme dans `memory` :
catalogue d'exigences, options, décision, ADR) et en tire une note par
exigence, terme du glossaire, option et entrée du journal, une note par
document du dossier des sources (`Documents/`, vers laquelle chaque exigence
et chaque terme renvoient : relation `extrait-de` et lien vers la section de
la citation), une note par étape soumise avec ses livrables (images et Markdown copiés dans
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
import os
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "lib"))
from lib.spec_schema import check, input_schema  # noqa: E402
from lib import source_docs  # noqa: E402
from lib.workflow_chart import progress_chart  # noqa: E402
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
               "annotation": "Annotation", "reponse": "Réponse"}
def answers(state: dict) -> dict[str, str]:
    """Question -> première réponse (`reponse` dont les refs citent la question)."""
    asked = {e["id"] for e in state["entries"] if e["kind"] == "question"}
    found: dict[str, str] = {}
    for entry in state["entries"]:
        if entry["kind"] == "reponse":
            for ref in entry.get("refs", []):
                if ref in asked:
                    found.setdefault(ref, entry["id"])
    return found


def open_questions(state: dict) -> list[dict]:
    """Questions du journal sans réponse, dans l'ordre."""
    answered = answers(state)
    return [e for e in state["entries"] if e["kind"] == "question" and e["id"] not in answered]


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


def _cited(item: dict) -> list[str]:
    """Documents cités par une exigence ou un terme, sans doublon, dans l'ordre."""
    return list(dict.fromkeys(s["doc"] for s in item.get("sources", [])))


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
        self.docs_dir = f"{self.base}/Documents"
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
        self.name_documents()
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

    def name_documents(self) -> None:
        """Une note par document du dossier des sources, et par document cité qui n'y est plus : les exigences
        et les termes y renvoient (relation extrait-de), le document entre dans le graphe du vault."""
        self.sources_dir = self.data / self.catalog.get("sources", "sources") if self.catalog else None
        self.docs = source_docs.load(self.sources_dir) if self.sources_dir else {}
        items = self.catalog.get("requirements", []) + self.glossary
        self.missing_docs = sorted({d for item in items for d in _cited(item)} - set(self.docs))
        for doc in [*self.docs, *self.missing_docs]:
            parts = Path(doc).with_suffix("").parts
            self.names["doc:" + doc] = "/".join([self.docs_dir, *(safe_name(p) for p in parts)])
            self.titles["doc:" + doc] = vault_ontology.heading(
                "\n".join(source_docs.body_of(self.docs.get(doc, [])))) or parts[-1]
        self.extracted = {doc: [r["id"] for r in self.catalog.get("requirements", []) if doc in _cited(r)]
                          for doc in self.docs}
        if self.missing_docs:
            self.warnings.append(f"{vault_ontology.count(len(self.missing_docs), 'document cité')} hors de "
                                 f"{self.sources_dir} : {', '.join(self.missing_docs[:5])}")

    def source_lines(self, item: dict, rel: str) -> list[str]:
        """Sources d'une exigence ou d'un terme (note rel) : lien vers le document, à la section de la citation ;
        vers l'original quand le vault est dans le projet, sinon vers la note qui en porte le texte."""
        lines = []
        for ref in item.get("sources", []):
            doc, quote = ref["doc"], ref.get("quote")
            text = self.docs.get(doc, [])
            section = source_docs.section_at(text, source_docs.line_of(text, quote))
            title = self.titles["doc:" + doc]
            shown = _alias(title if not section or section == title else f"{title}, {section}")
            url = self.outside(self.sources_dir / doc, rel) if doc in self.docs else None
            anchor = source_docs.anchor(section) if section else ""
            target = f"[{shown}]({url}{'#' + urllib.parse.quote(anchor) if anchor else ''})" if url else \
                f"[[{self.names['doc:' + doc]}{'#' + anchor if anchor else ''}|{shown}]]"
            lines.append(f"- {target}" + (f" : « {quote} »" if quote else ""))
        return lines

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
        return [(self.names[r], self.titles[r] if r.startswith("doc:") else r.removeprefix("terme:"))
                if r in self.names else (r, self.note_title(r))
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
        self.document_notes()
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
            body += ["## Sources", ""] + self.source_lines(req, names[rid]) + ([f"- déduite : {req['derived']}"]
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
                        "statut": req.get("status", "retenue"), "deduite": req.get("derived")}, body,
                       {"termes": self.linked("terme:" + term for term in terms),
                        "extrait-de": self.linked("doc:" + doc for doc in _cited(req))})

    def document_notes(self) -> None:
        """Note de chaque document source, avec ce que le workflow en a tiré. Vault dans le projet : une fiche
        qui renvoie à l'original, seule version du texte ; sinon la note porte le texte du document."""
        for doc in [*self.docs, *self.missing_docs]:
            rel, lines = self.names["doc:" + doc], source_docs.body_of(self.docs.get(doc, []))
            original = self.outside(self.sources_dir / doc, rel) if doc in self.docs else None
            body = [f"# {self.titles['doc:' + doc]}"] if original or not vault_ontology.heading("\n".join(lines)) \
                else []
            body += [] if original else ["", *lines] if body else list(lines)
            if original:
                pass
            elif doc in self.missing_docs:
                body += [""] + vault_ontology.callout("warning", "Document introuvable", [
                    f"`{doc}` est cité par le catalogue d'exigences mais n'est plus dans le dossier des sources."])
            else:
                for image, path in source_docs.images(lines, doc, self.sources_dir).items():
                    self.copies[f"{self.docs_dir}/{image}"] = path
            body += ["", "## Dans le workflow", "", self.up, "",
                     f"Document source : [{doc}]({original})." if original else
                     f"Copie de `{doc}` : modifiez l'original, cette note est réécrite."]
            if self.extracted.get(doc):
                body += ["", "Exigences tirées de ce document :", ""] + [f"- {self.link(r)}"
                                                                        for r in self.extracted[doc]]
            terms = [g["term"] for g in self.glossary if doc in _cited(g)]
            if terms:
                body += ["", "Termes : " + ", ".join(f"[[{self.names['terme:' + t]}|{_alias(t)}]]" for t in terms)]
            self.typed(rel, "document", {"source": doc}, body)

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
            sources = self.source_lines(entry, self.names["terme:" + entry["term"]])
            body = [f"# {entry['term']}", "", entry["definition"], "", self.up]
            if sources:
                body += ["", "## Sources", ""] + sources
            if self.uses[entry["term"]]:
                body += ["", "## Exigences", ""] + [f"- {self.link(r)}" for r in self.uses[entry["term"]]]
            self.typed(self.names["terme:" + entry["term"]], "terme", {"aliases": entry.get("aliases", [])}, body,
                       {"extrait-de": self.linked("doc:" + doc for doc in _cited(entry))}, tags=["glossaire"])

    def entry_notes(self) -> None:
        answered = answers(self.state)
        for entry in self.state["entries"]:
            refs = [self.link(r) for r in entry.get("refs", [])]
            body = [f"# {entry['id']} {KIND_LABELS[entry['kind']]}", "", entry["text"], "", self.up, ""]
            if entry.get("why"):
                body += [f"**Justification** : {entry['why']}", ""]
            if refs:
                body += ["**Concerne** : " + ", ".join(refs), ""]
            if entry.get("files"):
                body += ["**Fichiers** : " + ", ".join(f"`{f}`" for f in entry["files"])]
            if entry["kind"] == "question":
                body += ([f"**Réponse** : {self.link(answered[entry['id']])}", ""] if entry["id"] in answered
                         else vault_ontology.callout("question", "Question ouverte", [
                             "Répondez sous « Mes notes », ou à l'agent à la prochaine revue."]))
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

    def drawio_source(self, file: str, rel: str) -> list[str]:
        """Lien vers la source draw.io d'un PNG exporté (x.drawio.png -> x.drawio)."""
        if not file.lower().endswith(".drawio.png") or not (self.folder / file[:-4]).is_file():
            return []
        return [f"Source modifiable : {self.file_link(file[:-4], rel, Path(file[:-4]).name)} (draw.io).", ""]

    def outside(self, target: Path, rel: str) -> str | None:
        """Chemin relatif d'un fichier du projet depuis la note rel quand le vault est dans le dossier du projet
        (une seule version du fichier : la note renvoie à l'original), sinon None."""
        return vault_ontology.original(self.vault, target, rel)

    def file_link(self, file: str, rel: str, label: str | None = None, code: bool = True) -> str:
        """Lien, depuis la note rel, vers un fichier du workflow : la note de son document source, l'original
        (vault dans le projet), sinon sa copie dans Fichiers/ ; le nom seul s'il n'est ni lisible ni présent."""
        source, shown = self.folder / file, label or file
        if self.document_of(file):
            return self.link(self.document_of(file))
        url = self.outside(source, rel)
        if url:
            return f"[{shown}]({url})"
        if source.suffix.lower() in EMBEDDED | {".drawio"} and source.is_file():
            self.copies[f"{self.files_dir}/{file}"] = source
            return f"[[{self.files_dir}/{file}|{shown}]]"
        return f"`{shown}`" if code else shown

    def picture(self, file: str, rel: str) -> str:
        """Image du workflow intégrée à la note rel : l'original (vault dans le projet), sinon sa copie."""
        url = self.outside(self.folder / file, rel)
        if url:
            return f"![{Path(file).name}|{IMAGE_WIDTH}]({url})"
        self.copies[f"{self.files_dir}/{file}"] = self.folder / file
        return f"![[{self.files_dir}/{file}|{IMAGE_WIDTH}]]"

    def rebased(self, text: str, source: Path, rel: str) -> str:
        """Liens Markdown relatifs d'un livrable copié : vers une note ou un fichier du vault, un wikilink ;
        vers un fichier du projet, le chemin depuis la copie s'il est joignable, sinon le texte seul."""
        vault = self.vault.resolve()

        def link(match: re.Match) -> str:
            image, shown, url = match.groups()
            path, _, anchor = urllib.parse.unquote(url).partition("#")
            if not path or re.match(r"[a-z][a-z0-9+.-]*:|/", path, re.I):
                return match.group(0)
            target = (source.parent / path).resolve()
            bar = "\\|" if match.string[:match.start()].rsplit("\n", 1)[-1].lstrip().startswith("|") else "|"
            if vault in target.parents and target.is_file():
                inside = target.relative_to(vault)
                inside = inside.with_suffix("") if inside.suffix.lower() == ".md" else inside
                return f"![[{inside.as_posix()}]]" if image else \
                    f"[[{inside.as_posix()}{'#' + anchor if anchor else ''}{bar}{shown}]]"
            copy = next((c for c, s in self.copies.items() if s.resolve() == target), None)
            if copy:
                return f"![[{copy}]]" if image else f"[[{copy}{bar}{shown}]]"
            if image:
                return match.group(0)
            there = self.outside(target, rel)
            return f"[{shown}]({there}{'#' + urllib.parse.quote(anchor) if anchor else ''})" if there else shown
        return re.sub(r"(!?)\[([^\]\n]*)\]\(([^)\s]+)\)", link, text)

    def link_ids(self) -> dict[str, str]:
        """Identifiant -> note, pour lier les copies des livrables : exigences, entrées du journal, et notes des
        autres skills (constats, risques, lots...) dont l'identifiant est unique dans le dossier du workflow."""
        ids: dict[str, str | None] = {}
        for rel, (meta, _) in vault_ontology.scan(self.vault, self.base).items():
            ref = meta.get("id")
            if isinstance(ref, str) and re.fullmatch(r"[A-Za-z][\w.]*[-_.]?\d[\w.-]*", ref):
                ids[ref] = None if ref in ids else rel
        own = [r["id"] for r in self.catalog.get("requirements", [])] + [e["id"] for e in self.state["entries"]]
        ids.update({ref: self.names[ref] for ref in own})
        return {ref: rel for ref, rel in ids.items() if rel}

    def document_of(self, file: str) -> str | None:
        """Référence de la note du document quand un livrable d'étape est un document source."""
        if not self.docs:
            return None
        try:
            doc = (self.folder / file).resolve().relative_to(self.sources_dir.resolve()).as_posix()
        except ValueError:
            return None
        return "doc:" + doc if doc in self.docs else None

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
                embedded = source.suffix.lower() in EMBEDDED and source.is_file() and not self.document_of(file)
                if embedded and source.suffix.lower() != ".md":
                    body += [f"### {file}", "", self.picture(file, rel), ""] + self.drawio_source(file, rel)
                elif embedded and not self.outside(source, rel):
                    self.copies[f"{files_dir}/{file}"] = source
                    body += [f"### {file}", "", f"![[{files_dir}/{file}]]", ""]
                else:
                    body.append(f"- {self.file_link(file, rel)}")
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
                caption = [f"*Schéma de l'option {opt['id']} : {opt.get('name', opt['id'])}.*", ""] \
                    + self.drawio_source(found, names[opt["id"]])
                notes[names[opt["id"]]] = notes[names[opt["id"]]].rstrip() + "\n\n" + "\n".join(
                    ["## Schéma", "", self.picture(found, names[opt["id"]]), ""] + caption).rstrip() + "\n"

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
            shown = [self.file_link(f, rel) if self.document_of(f) or self.outside(self.folder / f, rel)
                     or f"{files_dir}/{f}" in self.copies else f"`{f}`" for f in stage.get("files", {})]
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
        stages = [next((d for d in (self.definition or {}).get("stages", []) if d["id"] == s["id"]),
                       {"id": s["id"]}) for s in state["stages"]]
        body += ["", "## Avancement", ""] + progress_chart(
            stages, {s["id"]: s["status"] for s in state["stages"]}, state["title"])
        if self.reviews:
            body += [""] + vault_ontology.callout("todo", "Revues en attente", [
                f"- [[{rel}|{rel.rsplit('/', 1)[-1]}]]" for rel in self.reviews])[:-1]
        waiting = open_questions(state)
        if waiting:
            body += [""] + vault_ontology.callout("question", "Questions ouvertes", [
                f"- {link(e['id'])} ({labels.get(e['stage'], e['stage'])}) : {e['text']}" for e in waiting])[:-1]
        requirements = self.catalog.get("requirements", [])
        if requirements:
            body += ["", "## Exigences", "", "| Exigence | Priorité | Statut |", "| --- | --- | --- |"]
            body += [f"| [[{names[r['id']]}\\|{_alias(self.titles[r['id']])}]] | "
                     f"{vault_ontology.label(ONTOLOGY, r['priority'])} | "
                     f"{vault_ontology.label(ONTOLOGY, r.get('status', 'retenue'))} |" for r in requirements]
        if self.docs or self.missing_docs:
            body += ["", "## Documents", ""] + [
                f"- {link('doc:' + doc)} : "
                + vault_ontology.count(len(self.extracted.get(doc, [])), "exigence")
                for doc in [*self.docs, *self.missing_docs]]
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
            journal = self.file_link("journal.md", self.index, "Journal complet") \
                if (self.folder / "journal.md").is_file() else None
            body += ["", "## Journal", ""] + ([f"{journal} (journal.md, identifiants liés aux notes).", ""]
                                              if journal else []) + [f"- {link(e['id'])} ({labels.get(e['stage'], e['stage'])}, {e['by']}) : "
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
        linked = source_docs.linker(self.link_ids(), {doc: (self.names["doc:" + doc], lines)
                                                      for doc, lines in self.docs.items()},
                                    self.catalog.get("sources", "sources"))
        for rel, source in self.copies.items():
            path = self.vault / rel
            content = source.read_bytes()
            if source.suffix.lower() == ".md":
                # Copie liée : identifiants et renvois aux documents deviennent des liens, l'original reste tel quel.
                text = self.rebased(linked(content.decode("utf-8", errors="replace").replace("\r\n", "\n")),
                                    source, rel)
                content = (f"---\n{MARK}\nsource: {json.dumps(source.name)}\n---\n\n" + text).encode("utf-8")
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
        for folder in (self.files_dir, self.docs_dir):
            for path in sorted((vault / folder).rglob("*"), reverse=True) if (vault / folder).is_dir() else []:
                if folder == self.docs_dir and path.suffix.lower() == ".md":
                    continue  # notes des documents : traitées plus haut
                if path.is_file() and path.relative_to(vault).as_posix() not in self.copies:
                    path.unlink()
                    removed += 1
                elif path.is_dir() and not any(path.iterdir()):
                    path.rmdir()
            if (vault / folder).is_dir() and not any((vault / folder).iterdir()):
                (vault / folder).rmdir()
        return removed

    def broken(self) -> list[str]:
        """Wikilinks écrits qui ne pointent vers aucune note ni aucun fichier."""
        return sorted({target for text in self.notes.values() for target in re.findall(r"\[\[([^|\]\\#]+)", text)
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
