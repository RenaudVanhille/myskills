# /// script
# requires-python = ">=3.10"
# ///
"""Construit le catalogue des exigences fonctionnelles et non fonctionnelles.

Entrée : une description JSON courte (`exigences.json`) où chaque exigence a
un identifiant stable (celui des documents s'ils numérotent déjà leurs
exigences, sinon EF-001 fonctionnelle, ENF-001 non fonctionnelle), sa
priorité et la citation exacte de sa source dans un document Markdown du
dossier `sources`. Le script, et non le modèle :
- vérifie que chaque citation existe dans son document et en donne la ligne ;
- repère les phrases normatives des sources (doit, devra, il faut, shall,
  must...) reprises par aucune exigence ni écartées avec une raison ;
- signale une exigence renumérotée alors que sa source porte déjà un
  identifiant, et un identifiant repris absent des sources ;
- signale doublons, exigences non mesurables et questions ouvertes ;
- avec --candidates, écrit toutes les phrases non reprises pour un tri par
  un modèle léger (sous-agent de niveau simple) ; avec son tri (`<nom>.tri.json`,
  lu d'office), seules les phrases qu'il tient pour des exigences sont
  signalées, au lieu de la liste de verbes ;
- écrit `exigences.md` (revue) et `exigences.csv` (tableur, séparateur ;).

    uv run scripts/req_build.py exigences.json [--out-dir DOSSIER] [--candidates [FICHIER]] [--triage FICHIER] | --schema

Avec --draft, le script écrit d'abord la description à trier (jamais par-dessus
un fichier existant) : une exigence par phrase normative des sources, avec sa
citation exacte, l'identifiant du document s'il en porte un, la nature, la
catégorie, la priorité (doit : indispensable, pourra : souhaitable) et la
mesure déduites des mots. Le modèle ne fait que trier, fusionner et corriger.

    uv run scripts/req_build.py exigences.json --draft [--sources DOSSIER]
"""

import argparse
import csv
import difflib
import hashlib
import json
import os
import re
import sys
import unicodedata
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import check as check_schema, print_schema, read_spec, schema_option, validate  # noqa: E402
from text_tools import beside, cell, from_data  # noqa: E402

PRIORITIES = ["indispensable", "importante", "souhaitable", "hors-perimetre"]
CATEGORY_LABELS = {"performance": "Performance", "disponibilite": "Disponibilité", "securite": "Sécurité",
                   "conformite": "Conformité", "exploitabilite": "Exploitabilité",
                   "maintenabilite": "Maintenabilité", "evolutivite": "Évolutivité",
                   "interoperabilite": "Interopérabilité", "utilisabilite": "Utilisabilité",
                   "portabilite": "Portabilité", "cout": "Coût", "autre": "Autre"}
# Phrases qui expriment une exigence, en français ou en anglais.
NORMATIVE = re.compile(
    r"\b(doit|doivent|devra|devront|devrait|devraient|il faut|il faudra|est necessaire|sont necessaires|"
    r"obligatoire\w*|imperatif|exige|exigee?s?|ne pourra pas|pourra|shall|must|should|is required|are required)\b")
MAX_LISTED = 20
# Volumétrie attendue d'un catalogue : chaque dimension est couverte par une exigence retenue (titre, texte,
# mesure) ou une question qui la cite, sinon déclarée sans objet (volumetry, avec sa raison). Motifs sur le texte
# normalisé (sans accents ni majuscules). Sans elle, les volumes ne sont demandés qu'au chiffrage, trop tard.
NUMBER = r"\d[\d  .,]*\s*(?:k|m|millions?|milliers?|mille)?\s*(?:de |d')?"
VOLUMETRY = {
    "utilisateurs": ("nombre d'utilisateurs", rf"{NUMBER}(?:utilisateurs?|usagers?|assures?|clients?|abonnes?|"
                     r"agents?|comptes?|salaries?|collaborateurs?|patients?|adherents?|visiteurs?)"),
    "pointe": ("pic ou utilisateurs simultanés", r"simultan|\bpic\b|pics\b|pointe|afflux|concurren|peak"),
    "debit": ("débit (transactions, requêtes, traitements par unité de temps)",
              rf"{NUMBER}(?!(?:euros?|heures?|minutes?|secondes?|jours?|fois)\b)(?:[a-z']+ ?){{1,3}}?"
              r"(?:par |/ ?)(?:seconde|minute|heure|jour|semaine|mois|an|s|sec|min|h|j)\b|"
              r"\btps\b|\brps\b|\bqps\b|transactions? par|requetes? par"),
    "donnees": ("volume de données ou de fichiers",
                rf"{NUMBER}(?:ko|mo|go|to|po|kb|mb|gb|tb|pb)\b|volumes? de donnees|volumetrie|"
                rf"{NUMBER}(?:enregistrements?|lignes|documents?|fichiers?|dossiers?|contrats?|images?|photos?)"),
    "croissance": ("croissance", r"croissance|augment|doubl|tripl|montee en charge|evolution du volume|"
                   r"\d+ ?% (?:par|l')an|par an"),
    "retention": ("durée de conservation", r"conserv|retention|archiv|purg|historis|\d+ ans\b"),
}

# Une question n'a pas encore de nombre : ses mots suffisent pour les dimensions qui en exigent un.
VOLUMETRY_ASKED = {
    "utilisateurs": r"(?:combien|nombre) (?:d'|de )?(?:utilisateurs?|usagers?|assures?|clients?|abonnes?|comptes?|"
                    r"agents?|visiteurs?)",
    "debit": r"debit|combien (?:de |d')?\w+ par|(?:transactions?|requetes?) par",
    "donnees": r"volumes?|taille|stockage|\b(?:ko|mo|go|to)\b|combien (?:de |d')?(?:enregistrements?|fichiers?|"
               r"photos?|documents?)",
}


def volumetry(spec: dict, items: list[dict]) -> list[tuple[str, str, str, str]]:
    """(dimension, libellé, état, détail) : couverte (exigences), question (exigences qui la posent), sans objet
    (raison) ou absente."""
    kept = [r for r in items if r.get("status", "retenue") == "retenue"]
    declared = spec.get("volumetry", {})
    rows = []
    for key, (label, pattern) in VOLUMETRY.items():
        stated = [r["id"] for r in kept if re.search(pattern, normalize(
            " ".join([r["title"], r["text"], r.get("metric", "")])))]
        loose = VOLUMETRY_ASKED.get(key, pattern)
        asked = [r["id"] for r in kept if any(re.search(pattern, normalize(q)) or re.search(loose, normalize(q))
                                                for q in r.get("questions", []))]
        if stated:
            rows.append((key, label, "couverte", ", ".join(stated)))
        elif asked:
            rows.append((key, label, "question", ", ".join(asked)))
        elif key in declared:
            rows.append((key, label, "sans objet", declared[key]))
        else:
            rows.append((key, label, "absente", ""))
    return rows


# Tri des phrases non reprises par un modèle léger (sous-agent de niveau simple) : consigne écrite dans le
# fichier des candidats, pour que le sous-agent n'ait besoin de rien d'autre. Mesurée par tests/triage_eval.py.
TRIAGE_INSTRUCTIONS = (
    "Pour chaque phrase de items, tirée des documents d'un projet informatique, dis si elle exprime une exigence "
    "sur le système ou la solution à construire : une fonction, une règle de gestion, une qualité ou une "
    "contrainte, même écrite au présent de l'indicatif (« le système envoie... », « les données sont "
    "chiffrées... »). Ce n'est pas une exigence : un constat sur l'existant, du contexte, une opinion, une "
    "décision ou une organisation de réunion, une tâche pour des personnes du projet. Écris dans le fichier "
    "output un objet JSON key -> true ou false, pour toutes les phrases, sans autre texte.")
TRIAGE_SCHEMA = {"type": "object", "additionalProperties": {"type": "boolean"}}
# Identifiant d'exigence dans un document : REQ-012, EX_F_03, RG.45, RF12...
SOURCE_ID = re.compile(r"\b[A-Z]{1,6}(?:[-_.][A-Z]{1,6}){0,2}[-_.]?\d{1,4}\b")
GENERATED_ID = re.compile(r"^(EF|ENF)-\d{3}$")


def nature(req: dict) -> str | None:
    """fonctionnelle ou non-fonctionnelle : champ nature, sinon préfixe EF- ou ENF-."""
    if req.get("nature"):
        return req["nature"]
    return {"EF": "fonctionnelle", "ENF": "non-fonctionnelle"}.get(req["id"].split("-")[0])


def normalize(text: str) -> str:
    """Minuscules, sans accents ni mise en forme Markdown, espaces réduits."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("’", "'").replace("«", '"').replace("»", '"')
    text = re.sub(r"[*_`#>|]|\[|\]|\(http[^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def mentions(text: str, words: list[str]) -> bool:
    """Le texte emploie-t-il un des mots (sans casse ni accents, pluriel en s ou x admis) ?"""
    text = normalize(text)
    return any(re.search(rf"(?<!\w){re.escape(normalize(w))}[sx]?(?!\w)", text) for w in words if normalize(w))


def glossary_refs(spec: dict) -> dict[str, list[str]]:
    """Terme -> exigences retenues qui l'emploient (titre ou texte)."""
    kept = [r for r in spec["requirements"] if r.get("status", "retenue") == "retenue"]
    return {g["term"]: [r["id"] for r in kept if mentions(f"{r['title']} {r['text']}", [g["term"], *g.get("aliases", [])])]
            for g in spec.get("glossary", [])}


def load_sources(folder: Path) -> dict[str, list[str]]:
    return {path.relative_to(folder).as_posix(): path.read_text(encoding="utf-8", errors="replace").splitlines()
            for path in sorted(folder.rglob("*.md")) if ".myskills-tmp" not in path.parts}


def index_of(lines: list[str]) -> tuple[str, list[tuple[int, int]]]:
    """Texte normalisé du document et position de début de chaque ligne."""
    joined, starts = "", []
    for number, line in enumerate(lines, 1):
        starts.append((len(joined), number))
        joined += normalize(line) + " "
    return joined, starts


def find_quote(index: tuple[str, list[tuple[int, int]]], quote: str) -> int | None:
    """Ligne (à partir de 1) où commence la citation, même coupée sur plusieurs lignes."""
    wanted = normalize(quote)
    joined, starts = index
    at = joined.find(wanted) if wanted else -1
    if at < 0:
        return None
    return max(number for offset, number in starts if offset <= at)


def blocks(lines: list[str]):
    """(ligne de début, texte) des paragraphes, éléments de liste et cellules de tableau,
    les lignes coupées d'un même paragraphe réunies ; titres ignorés."""
    start, current = 0, []
    for number, line in enumerate(lines + [""], 1):
        stripped = line.strip()
        is_item = re.match(r"([-*+]|\d+[.)])\s", stripped)
        if not stripped or stripped.startswith(("#", "|")) or is_item:
            if current:
                yield start, " ".join(current)
            current = []
        if stripped.startswith("|") and not set(stripped) <= set("|-: "):
            for part in stripped.split("|"):
                yield number, part.strip()
        elif stripped and not stripped.startswith(("#", "|")):
            if not current:
                start = number
            current.append(stripped.lstrip("-*+ ") if is_item else stripped)


def sentences(lines: list[str], every: bool = False):
    """(ligne, phrase, normative) des phrases des sources : les normatives, ou toutes avec every."""
    index = index_of(lines)
    for number, text in blocks(lines):
        for part in re.split(r"(?<=[.!?;])\s+", text):
            part = part.strip()
            normative = bool(NORMATIVE.search(normalize(part)))
            if len(part) > 12 and (normative or every):
                yield find_quote(index, part) or number, part, normative


# Brouillon (--draft) : catégorie d'une phrase non fonctionnelle d'après ses mots (texte normalisé), dans
# l'ordre ; aucune : exigence fonctionnelle.
DRAFT_CATEGORIES = [
    ("performance", r"temps de reponse|secondes?\b|\bms\b|simultan|requetes|debit|latence|performan"),
    ("disponibilite", r"disponibilit|panne|\bpra\b|reprise d.activite|\brto\b|\brpo\b|sauvegard"),
    ("securite", r"authentif|chiffr|intrusion|mot de passe|habilitation|securit|journalis|tracabilit"),
    ("cout", r"euros?\b|€|\bcout|budget"),
    ("conformite", r"rgpd|donnees personnelles|heberge|secnumcloud|\bhds\b|conserv|supprim|reglement"),
    ("utilisabilite", r"rgaa|accessib|ergonom"),
    ("exploitabilite", r"supervision|anomalie|corrig|astreinte|exploitation|incident"),
    ("portabilite", r"reversibil|restitu|format ouvert|portabilit"),
    ("interoperabilite", r"format d.echange|interoperab|norme d.echange"),
    ("evolutivite", r"evolutivit|montee en charge|croissance"),
    ("maintenabilite", r"maintenabilit|documentation|code source"),
]
METRIC = re.compile(r"\d[\d  ,.]*\s*(?:%|secondes?|ms\b|heures?(?: ouvrées)?|h\b|minutes?|jours?|mois|ans?\b|"
                    r"euros?|€|utilisateurs?(?: simultanés)?|requêtes)", re.I)


def draft(path: Path, sources_name: str) -> dict:
    """Brouillon d'exigences.json : une exigence par phrase normative des sources, citation exacte, identifiant
    des documents s'il y en a un, nature, catégorie, priorité et mesure déduites des mots ; à trier par le modèle."""
    errors: list[str] = []
    report = {"input": str(path), "outputs": [], "requirements": 0, "functional": 0, "non_functional": 0,
              "documents": 0, "errors": errors, "warnings": []}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une description")
        return report
    folder = from_data(path.parent, sources_name)
    sources = load_sources(folder) if folder.is_dir() else {}
    if not sources:
        errors.append(f"sources : aucun fichier .md dans {folder}")
        return report
    requirements, seen, numbers = [], set(), {"EF": 0, "ENF": 0}
    for doc, lines in sources.items():
        for number, sentence, _ in sentences(lines):
            key = normalize(sentence)
            if key in seen:
                continue
            seen.add(key)
            category = next((c for c, pattern in DRAFT_CATEGORIES if re.search(pattern, key)), None)
            prefix = "ENF" if category else "EF"
            given = SOURCE_ID.search(sentence) or SOURCE_ID.search(lines[number - 1] if number <= len(lines) else "")
            if given and not GENERATED_ID.match(given.group()):
                rid = given.group()
            else:
                numbers[prefix] += 1
                rid = f"{prefix}-{numbers[prefix]:03d}"
            words = sentence.rstrip(".;:").split()
            req = {"id": rid, "title": " ".join(words[:9]) + ("..." if len(words) > 9 else ""), "text": sentence}
            if category:
                req["category"] = category
                if not rid.startswith(("EF-", "ENF-")):
                    req["nature"] = "non-fonctionnelle"
            elif not rid.startswith(("EF-", "ENF-")):
                req["nature"] = "fonctionnelle"
            metric = METRIC.findall(sentence)
            if metric and category:
                req["metric"] = ", ".join(m.strip() for m in metric)
            req["priority"] = "souhaitable" if re.search(r"\b(pourra|devrait|should)\b", key) else "indispensable" \
                if re.search(r"\b(doit|doivent|obligatoire\w*|imperatif|shall|must)\b", key) else "importante"
            req["sources"] = [{"doc": doc, "quote": sentence}]
            requirements.append(req)
    ids = [r["id"] for r in requirements]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        report["warnings"].append(f"identifiant {dup} repris de plusieurs phrases : à fusionner ou renuméroter")
    spec = {"title": "Exigences", "sources": sources_name, "requirements": requirements,
            "_draft": "Brouillon de req_build.py --draft : une exigence par phrase normative. À trier : retirer ce qui "
                      "n'est pas une exigence de la solution (ou le passer dans ignored avec sa raison), fusionner, "
                      "corriger titres, catégories, priorités et mesures ; ajouter les exigences sans verbe normatif."}
    invalid = validate(spec, __file__) if requirements else []
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], requirements=len(requirements), documents=len(sources),
                  functional=sum(1 for r in requirements if not r.get("category")),
                  non_functional=sum(1 for r in requirements if r.get("category")))
    return report


def triage_key(text: str) -> str:
    return f"tri:{hashlib.sha1(normalize(text).encode('utf-8')).hexdigest()[:16]}"


HEADING = re.compile(r"^#{1,6}\s+(.+?)\s*#*\s*$")


def source_links(sources: dict[str, list[str]], folder: Path, out_dir: Path):
    """Fonction qui écrit les renvois « document.md:ligne » d'une cellule en liens Markdown standards vers le
    document, à la section de la ligne : lisibles dans Obsidian ouvert à la racine du projet comme à l'export."""
    names = "|".join(re.escape(d) for d in sorted(sources, key=len, reverse=True))
    pattern = re.compile(rf"({names})(?::(\d+))?((?: \(p\. \d+\)| p\. \d+)?)") if names else None

    def link(match: re.Match) -> str:
        doc, line, page = match.groups()
        section = None
        for text in sources[doc][:int(line)] if line else []:
            found = HEADING.match(text)
            section = found.group(1) if found else section
        anchor = re.sub(r"\s+", " ", re.sub(r"[#|^:\[\]*_`]|%%", " ", section)).strip() if section else ""
        try:
            relative = Path(os.path.relpath(folder / doc, out_dir)).as_posix()
        except ValueError:  # autre lecteur sous Windows
            return match.group(0)
        return (f"[{cell(doc + (':' + line if line else ''))}]({urllib.parse.quote(relative)}"
                f"{'#' + urllib.parse.quote(anchor) if anchor else ''}){page}")
    return lambda where: pattern.sub(link, where) if pattern else cell(where)


def render_md(spec: dict, items: list[dict], ignored: list[dict], glossary: list[dict] | None = None,
              where=cell, volume: list | None = None) -> str:
    kept = [r for r in items if r.get("status", "retenue") == "retenue"]
    functional = [r for r in kept if nature(r) == "fonctionnelle"]
    non_functional = [r for r in kept if nature(r) == "non-fonctionnelle"]
    lines = [f"# {spec.get('title') or 'Exigences'}", "",
             "Fichier généré par `req_build.py` depuis `exigences.json`, qui fait foi.", "",
             f"{len(functional)} exigences fonctionnelles, {len(non_functional)} non fonctionnelles, "
             f"{sum(len(r.get('questions', [])) for r in kept)} questions ouvertes.", "",
             "## Exigences fonctionnelles", "",
             "| ID | Exigence | Domaine | Priorité | Source |", "| --- | --- | --- | --- | --- |"]
    for r in functional:
        lines.append(f"| {r['id']} | **{cell(r['title'])}** : {cell(r['text'])} | {cell(r.get('domain', ''))} | "
                     f"{r['priority']} | {where(r['_where'])} |")
    lines += ["", "## Exigences non fonctionnelles", "",
              "| ID | Exigence | Catégorie | Mesure | Priorité | Source |", "| --- | --- | --- | --- | --- | --- |"]
    for r in non_functional:
        lines.append(f"| {r['id']} | **{cell(r['title'])}** : {cell(r['text'])} | "
                     f"{CATEGORY_LABELS.get(r.get('category', ''), '')} | {cell(r.get('metric', 'à définir'))} | "
                     f"{r['priority']} | {where(r['_where'])} |")
    questions = [(r["id"], q) for r in kept for q in r.get("questions", [])]
    if questions:
        lines += ["", "## Questions ouvertes", ""] + [f"- **{rid}** : {q}" for rid, q in questions]
    if volume:
        lines += ["", "## Volumétrie", "", "| Dimension | État | Exigences ou raison |", "| --- | --- | --- |"]
        lines += [f"| {label} | {'**absente : à demander**' if state == 'absente' else state} | {cell(detail) or '-'} |"
                  for _, label, state, detail in volume]
    derived = [r for r in kept if r.get("derived")]
    if derived:
        lines += ["", "## Exigences déduites, à confirmer", ""]
        lines += [f"- **{r['id']}** : {r['derived']}" for r in derived]
    retired = [r for r in items if r.get("status") == "retiree"]
    if retired:
        lines += ["", "## Exigences retirées", ""] + [f"- **{r['id']}** {r['title']} : {r['reason']}" for r in retired]
    if glossary:
        lines += ["", "## Glossaire", "", "| Terme | Définition | Exigences |", "| --- | --- | --- |"]
        for g in sorted(glossary, key=lambda g: normalize(g["term"])):
            term = g["term"] + (f" ({', '.join(g['aliases'])})" if g.get("aliases") else "")
            lines.append(f"| **{cell(term)}** | {cell(g['definition'])} | {', '.join(g['_refs']) or '-'} |")
    if ignored:
        lines += ["", "## Phrases des sources écartées", "", "| Source | Phrase | Raison |", "| --- | --- | --- |"]
        lines += [f"| {where(i['_where'])} | {cell(i['quote'])} | {cell(i['reason'])} |" for i in ignored]
    return "\n".join(lines) + "\n"


def write_csv(path: Path, items: list[dict]) -> None:
    # utf-8-sig : Excel sous Windows reconnaît alors les accents.
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle, delimiter=";")
        writer.writerow(["id", "type", "titre", "texte", "domaine_ou_categorie", "priorite", "mesure", "statut",
                         "sources", "questions"])
        for r in items:
            kind = nature(r).replace("-", " ")
            writer.writerow([r["id"], kind, r["title"], r["text"], r.get("domain") or r.get("category", ""),
                             r["priority"], r.get("metric", ""), r.get("status", "retenue"), r["_where"],
                             " / ".join(r.get("questions", []))])


def check(spec: dict, base: Path, errors: list[str], warnings: list[str],
          triage: dict | None = None,
          candidates_out: Path | None = None) -> tuple[list, list, dict]:
    folder = from_data(base, spec.get("sources", "sources")).resolve()
    if not folder.is_dir():
        errors.append(f"sources : dossier introuvable {folder}")
        return [], [], {}
    sources = load_sources(folder)
    indexes = {doc: index_of(lines) for doc, lines in sources.items()}
    if not sources:
        errors.append(f"sources : aucun fichier .md dans {folder}")
    quotes: dict[str, str] = {}

    def locate(where: str, ref: dict) -> str:
        doc = ref["doc"].replace("\\", "/")
        if doc not in sources:
            close = difflib.get_close_matches(doc, list(sources), n=1, cutoff=0.5)
            errors.append(f"{where} : document « {doc} » absent des sources"
                          + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            return doc
        if not ref.get("quote"):
            return doc + (f" p. {ref['page']}" if ref.get("page") else "")
        line = find_quote(indexes[doc], ref["quote"])
        if line is None:
            close = difflib.get_close_matches(ref["quote"], [l.strip() for l in sources[doc] if l.strip()],
                                              n=1, cutoff=0.4)
            errors.append(f"{where} : citation introuvable dans {doc} : « {ref['quote'][:80]} »"
                          + (f" ; ligne proche : « {close[0][:80]} »" if close else ""))
            return doc
        return f"{doc}:{line}" + (f" (p. {ref['page']})" if ref.get("page") else "")

    items, seen = [], set()
    for index, req in enumerate(spec["requirements"]):
        where = f"requirements/{index} ({req['id']})"
        if req["id"] in seen:
            errors.append(f"{where} : identifiant en double")
        seen.add(req["id"])
        if nature(req) is None:
            errors.append(f"{where} : nature manquante (fonctionnelle ou non-fonctionnelle) pour un identifiant "
                          "repris des documents")
            continue
        functional = nature(req) == "fonctionnelle"
        if not functional and not req.get("category"):
            errors.append(f"{where} : category manquante pour une exigence non fonctionnelle "
                          f"({', '.join(CATEGORY_LABELS)})")
        if functional and req.get("category"):
            warnings.append(f"{where} : category ignorée pour une exigence fonctionnelle (domain attendu)")
        if req.get("status") == "retiree" and not req.get("reason"):
            errors.append(f"{where} : reason manquante pour une exigence retirée")
        if not req.get("sources") and not req.get("derived"):
            errors.append(f"{where} : ni sources ni derived : citez le document ou expliquez la déduction")
        refs = [locate(f"{where}/sources/{i}", ref) for i, ref in enumerate(req.get("sources", []))]
        # Numérotation existante : on la garde, et on vérifie qu'elle vient bien des documents.
        if GENERATED_ID.match(req["id"]):
            for ref in req.get("sources", []):
                doc = ref["doc"].replace("\\", "/")
                line = find_quote(indexes[doc], ref["quote"]) if doc in sources and ref.get("quote") else None
                found = SOURCE_ID.findall(sources[doc][line - 1]) if line else []
                found = [f for f in found if not GENERATED_ID.match(f)]
                if found:
                    warnings.append(f"{where} : la source {doc}:{line} porte déjà l'identifiant {found[0]}, "
                                    "conservez-le comme id")
        elif not any(re.search(rf"(?<![\w-]){re.escape(req['id'])}(?![\w-])", "\n".join(lines))
                     for lines in sources.values()):
            warnings.append(f"{where} : identifiant {req['id']} absent des sources : numérotation existante "
                            "ou EF-/ENF- ?")
        if req.get("sources") and not any(ref.get("quote") for ref in req["sources"]) and not req.get("derived"):
            warnings.append(f"{where} : aucune citation, source non vérifiable")
        for ref in req.get("sources", []):
            if ref.get("quote"):
                key = normalize(ref["quote"])
                if key in quotes and quotes[key] != req["id"]:
                    warnings.append(f"{where} : même citation que {quotes[key]}, doublon possible")
                quotes.setdefault(key, req["id"])
        if not functional and req.get("status", "retenue") == "retenue" and not req.get("metric"):
            warnings.append(f"{where} : non mesurable, ajoutez metric ou une question")
        items.append({**req, "_where": ", ".join(refs) or "déduite"})

    ignored = []
    for index, item in enumerate(spec.get("ignored", [])):
        where = locate(f"ignored/{index}", item)
        ignored.append({**item, "_where": where})
        quotes.setdefault(normalize(item["quote"]), "écartée")

    glossary, names = [], {}
    refs_of = glossary_refs(spec)
    for index, entry in enumerate(spec.get("glossary", [])):
        where = f"glossary/{index} ({entry['term']})"
        for word in [entry["term"], *entry.get("aliases", [])]:
            key = normalize(word)
            if key in names and names[key] != entry["term"]:
                errors.append(f"{where} : « {word} » déjà défini par « {names[key]} »")
            elif key in names:
                warnings.append(f"{where} : « {word} » répété")
            names.setdefault(key, entry["term"])
        for i, ref in enumerate(entry.get("sources", [])):
            locate(f"{where}/sources/{i}", ref)
        if not refs_of[entry["term"]]:
            warnings.append(f"{where} : terme employé par aucune exigence retenue")
        glossary.append({**entry, "_refs": refs_of[entry["term"]]})

    candidates = [(doc, number, sentence, normative)
                  for doc, lines in sources.items()
                  for number, sentence, normative in sentences(
                      lines, every=triage is not None or candidates_out is not None)
                  if not any(q and (q in normalize(sentence) or normalize(sentence) in q) for q in quotes)]
    method, dismissed = "regles", 0

    triage = triage or {}
    if triage and any(triage_key(c[2]) in triage for c in candidates):
        method = "tri"
    pending = [{"key": triage_key(sentence), "where": f"{doc}:{number}", "text": sentence}
               for doc, number, sentence, _ in candidates if triage_key(sentence) not in triage]
    if candidates_out is not None:
        candidates_out.parent.mkdir(parents=True, exist_ok=True)
        output = candidates_out.with_name(candidates_out.name.replace(".candidats.json", "") + ".tri.json") \
            if candidates_out.name.endswith(".candidats.json") else candidates_out.with_suffix(".tri.json")
        candidates_out.write_text(json.dumps({"instructions": TRIAGE_INSTRUCTIONS, "output": output.name,
                                              "items": pending}, ensure_ascii=False, indent=1) + "\n",
                                  encoding="utf-8")

    uncovered = []
    for doc, number, sentence, normative in candidates:
        sorted_as = triage.get(triage_key(sentence))
        if sorted_as is not None:
            # Tri d'un modèle léger : il décide seul, la regex ne sert qu'aux phrases non triées.
            if sorted_as:
                uncovered.append(f"phrase d'exigence non reprise ni écartée (tri) : {doc}:{number} "
                                 f"« {sentence[:120]} »")
            else:
                dismissed += normative
        elif normative:
            uncovered.append(f"phrase normative non reprise ni écartée : {doc}:{number} « {sentence[:120]} »")
    warnings += uncovered[:MAX_LISTED]
    if len(uncovered) > MAX_LISTED:
        warnings.append(f"... et {len(uncovered) - MAX_LISTED} autres phrases d'exigence non reprises")
    return items, ignored, {"documents": len(sources), "uncovered": len(uncovered), "glossary": glossary,
                            "method": method, "dismissed": dismissed,
                            "candidates": len(pending) if candidates_out is not None else 0}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description exigences.json")
    parser.add_argument("--out-dir", type=Path, help="dossier de exigences.md et .csv (défaut : celui du .json)")
    schema_option(parser)
    parser.add_argument("--candidates", type=Path, nargs="?", const=True,
                        help="écrit les phrases non reprises à trier (défaut : <nom>.candidats.json à côté du .json)")
    parser.add_argument("--triage", type=Path,
                        help="tri des phrases par un modèle léger (défaut : <nom>.tri.json à côté du .json, s'il existe)")
    parser.add_argument("--draft", action="store_true",
                        help="écrire le brouillon de la description : une exigence par phrase normative des sources")
    parser.add_argument("--sources", default="sources", help="avec --draft : dossier des sources (défaut : sources)")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    if args.draft:
        report = draft(args.spec, args.sources)
        print(json.dumps(report, ensure_ascii=False))
        return 1 if report["errors"] else 0
    spec, invalid = read_spec(args.spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    triage, stem = None, args.spec.name.removesuffix(".json")
    triage_path = args.triage or args.spec.parent / f"{stem}.tri.json"
    if args.triage or triage_path.is_file():
        try:
            triage = json.loads(triage_path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            errors.append(f"tri : {triage_path} illisible : {error}")
        else:
            errors += [f"tri : {e}" for e in check_schema(triage, TRIAGE_SCHEMA)][:10]
    candidates = args.spec.parent / f"{stem}.candidats.json" if args.candidates is True else args.candidates
    items, ignored, counts = check(spec, args.spec.parent, errors, warnings,
                                   triage if not errors else None, candidates)
    kept = [r for r in items if r.get("status", "retenue") == "retenue"]
    volume = volumetry(spec, items) if not errors else []
    missing = [key for key, _, state, _ in volume if state == "absente"]
    if missing:
        warnings.append("volumétrie absente des exigences : " + ", ".join(VOLUMETRY[k][0] for k in missing)
                        + " ; demandez-la à l'utilisateur (une question dans l'exigence la plus proche) ou "
                        "déclarez-la sans objet (volumetry, avec sa raison)")
    for key in spec.get("volumetry", {}):
        if key not in missing and any(k == key and state != "sans objet" for k, _, state, _ in volume):
            warnings.append(f"volumetry/{key} : déclarée sans objet alors que des exigences la couvrent")
    report = {"input": str(args.spec), "outputs": [],
              "functional": sum(nature(r) == "fonctionnelle" for r in kept),
              "non_functional": sum(nature(r) == "non-fonctionnelle" for r in kept),
              "retired": len(items) - len(kept), "ignored": len(ignored),
              "questions": sum(len(r.get("questions", [])) for r in kept),
              "documents": counts.get("documents", 0), "uncovered": counts.get("uncovered", 0),
              "glossary": len(spec.get("glossary", [])),
              "method": counts.get("method", "regles"), "dismissed": counts.get("dismissed", 0),
              "candidates": counts.get("candidates", 0), "volumetry_missing": missing,
              "errors": errors, "warnings": warnings}
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md, table = beside(out_dir / f"{stem}.md"), out_dir / f"{stem}.csv"
    with open(md, "w", encoding="utf-8", newline="\n") as handle:
        folder = from_data(args.spec.parent, spec.get("sources", "sources")).resolve()
        handle.write(render_md(spec, items, ignored, counts.get("glossary"),
                               source_links(load_sources(folder), folder, md.parent.resolve()), volume))
    write_csv(table, items)
    report["outputs"] = [str(md), str(table)]
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
