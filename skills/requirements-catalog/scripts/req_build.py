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
- écrit `exigences.md` (revue) et `exigences.csv` (tableur, séparateur ;).

    uv run scripts/req_build.py exigences.json [--out-dir DOSSIER] | --schema
"""

import argparse
import csv
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402

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


def sentences(lines: list[str]):
    """(ligne, phrase) normatives des sources."""
    index = index_of(lines)
    for number, text in blocks(lines):
        for part in re.split(r"(?<=[.!?;])\s+", text):
            part = part.strip()
            if len(part) > 12 and NORMATIVE.search(normalize(part)):
                yield find_quote(index, part) or number, part


def cell(text: str) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def render_md(spec: dict, items: list[dict], ignored: list[dict], glossary: list[dict] | None = None) -> str:
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
                     f"{r['priority']} | {cell(r['_where'])} |")
    lines += ["", "## Exigences non fonctionnelles", "",
              "| ID | Exigence | Catégorie | Mesure | Priorité | Source |", "| --- | --- | --- | --- | --- | --- |"]
    for r in non_functional:
        lines.append(f"| {r['id']} | **{cell(r['title'])}** : {cell(r['text'])} | "
                     f"{CATEGORY_LABELS.get(r.get('category', ''), '')} | {cell(r.get('metric', 'à définir'))} | "
                     f"{r['priority']} | {cell(r['_where'])} |")
    questions = [(r["id"], q) for r in kept for q in r.get("questions", [])]
    if questions:
        lines += ["", "## Questions ouvertes", ""] + [f"- **{rid}** : {q}" for rid, q in questions]
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
        lines += [f"| {cell(i['_where'])} | {cell(i['quote'])} | {cell(i['reason'])} |" for i in ignored]
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


def check(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> tuple[list, list, dict]:
    folder = (base / spec.get("sources", "sources")).resolve()
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

    uncovered = []
    for doc, lines in sources.items():
        for number, sentence in sentences(lines):
            text = normalize(sentence)
            if not any(q and (q in text or text in q) for q in quotes):
                uncovered.append(f"{doc}:{number} « {sentence[:120]} »")
    for line in uncovered[:MAX_LISTED]:
        warnings.append(f"phrase normative non reprise ni écartée : {line}")
    if len(uncovered) > MAX_LISTED:
        warnings.append(f"... et {len(uncovered) - MAX_LISTED} autres phrases normatives non reprises")
    return items, ignored, {"documents": len(sources), "uncovered": len(uncovered), "glossary": glossary}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description exigences.json")
    parser.add_argument("--out-dir", type=Path, help="dossier de exigences.md et .csv (défaut : celui du .json)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    invalid = validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    items, ignored, counts = check(spec, args.spec.parent, errors, warnings)
    kept = [r for r in items if r.get("status", "retenue") == "retenue"]
    report = {"input": str(args.spec), "outputs": [],
              "functional": sum(nature(r) == "fonctionnelle" for r in kept),
              "non_functional": sum(nature(r) == "non-fonctionnelle" for r in kept),
              "retired": len(items) - len(kept), "ignored": len(ignored),
              "questions": sum(len(r.get("questions", [])) for r in kept),
              "documents": counts.get("documents", 0), "uncovered": counts.get("uncovered", 0),
              "glossary": len(spec.get("glossary", [])),
              "errors": errors, "warnings": warnings}
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.spec.name.removesuffix(".json")
    md, table = out_dir / f"{stem}.md", out_dir / f"{stem}.csv"
    with open(md, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_md(spec, items, ignored, counts.get("glossary")))
    write_csv(table, items)
    report["outputs"] = [str(md), str(table)]
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
