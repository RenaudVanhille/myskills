# /// script
# requires-python = ">=3.10"
# ///
"""Dépouille un dossier de consultation (appel d'offres) décrit en JSON, citations vérifiées.

Entrée : `ao.json`, description courte du dossier de consultation (règlement,
cahier des charges, bordereau de prix en Markdown dans `sources/`) : dates,
critères de notation et leurs poids, pièces à fournir, format de réponse et
clauses à risque, chacun avec la citation exacte de sa source. Le script, et
non le modèle :
- vérifie chaque citation dans son document et en donne la ligne ;
- contrôle les poids (critères de premier niveau sur 100, sous-critères égaux
  à leur critère), l'ordre des dates et le temps qui reste avant chaque date
  limite (questions au client, remise de l'offre) ;
- signale une clause à risque haute sans note, et tout élément des sources
  (date, critère, pièce, clause) repris par aucune entrée ni écarté avec sa
  raison ;
- écrit `ao.md` : calendrier, critères, pièces à fournir (liste à cocher),
  format de réponse, clauses à risque par niveau.

    uv run scripts/tender_build.py ao.json [--out-dir DOSSIER] [--today AAAA-MM-JJ] | --schema

Avec --draft, le script écrit d'abord la description (jamais par-dessus un
fichier existant) : dates, tableaux de pondération, listes de pièces, phrases
sur le format et clauses à risque repérées dans les sources, avec leur
citation exacte. Le modèle ne fait que corriger, noter le risque et écarter.

    uv run scripts/tender_build.py ao.json --draft [--sources DOSSIER]
"""

import argparse
import difflib
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import ai_mark  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

MONTHS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7, "aout": 8,
          "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
DATE_TEXT = re.compile(r"\b(\d{1,2})(?:er)?\s+(" + "|".join(MONTHS) + r")\s+(\d{4})\b")
DATE_NUM = re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b")
TIME = re.compile(r"\b(\d{1,2})\s*(?:h|:)\s*(\d{2})?\b")
# Nature d'une date d'après les mots de sa phrase (texte normalisé), dans l'ordre.
DATE_KINDS = [("questions", r"question|demandes? de (precision|renseignement)|eclaircissement"),
              ("remise", r"remise des offres|reception des offres|depot des offres|remettre .{0,20}offre|date limite"),
              ("soutenance", r"soutenance|audition|\boral\b"),
              ("visite", r"visite"),
              ("demarrage", r"demarrage|debut des prestations|lancement|notification")]
# Thème d'un critère (et d'une section du mémoire technique), dans l'ordre.
TOPICS = [("prix", r"\bprix\b|cout|financ|montant"),
          ("securite", r"securit|hebergement|protection des donnees|rgpd|confidentialit"),
          ("methode", r"methodolog|planning|gestion de projet|conduite du projet|organisation du projet"),
          ("maintenance", r"maintenance|niveaux? de service|support|exploitation|assistance"),
          ("equipe", r"equipe|moyens humains|\bcv\b|competence|intervenants"),
          ("environnement", r"environnement|durable|\brse\b|carbone|sobriete"),
          ("solution", r"architecture|technique|solution|exigences|fonctionnel|qualite")]
PIECE_KINDS = [("administratif", r"dume|\bdc\d|kbis|attestation|assurance|candidature|pouvoir"),
               ("financier", r"\bbpu\b|\bdqe\b|prix|financ|devis|decomposition"),
               ("technique", r"memoire|planning|\bcv\b|reference|technique|methodolog")]
# Clauses à risque : thème, motif (texte normalisé), niveau par défaut. Le modèle corrige le niveau et note.
CLAUSES = [("penalites", r"penalit", "haute"),
           ("responsabilite", r"responsabilite (illimitee|sans plafond)|dommages indirects", "haute"),
           ("irregularite", r"irreguliere|irrecevable|sera (eliminee|rejetee|ecartee)", "haute"),
           ("engagement", r"en moins de \d|dans un delai (maximal |maximum )?de \d|delai (maximal|maximum) de", "moyenne"),
           ("propriete", r"propriete intellectuelle|cession des droits|droits d.auteur|deviennent la propriete", "moyenne"),
           ("reversibilite", r"reversibilit|restituer|restitution des donnees|nouveau titulaire", "moyenne"),
           ("resiliation", r"resiliation|resilier", "moyenne"),
           ("confidentialite", r"confidentialit", "basse"),
           ("sous-traitance", r"sous-trait", "basse"),
           ("garantie", r"periode de garantie|garantie (de parfait|des vices)", "basse"),
           ("paiement", r"delai de paiement|retenue de garantie|revision des prix|avance forfaitaire", "basse")]
FORMAT = re.compile(r"format|voie electronique|profil acheteur|plateforme de depot|variante|langue francaise|"
                    r"signature electronique|\bpdf\b|support papier|copie de sauvegarde")
PIECES_HEADING = re.compile(r"pieces|contenu de l.offre|composition (de l.offre|du dossier|des plis)|"
                            r"documents? a (fournir|remettre|produire)|dossier de (candidature|reponse)")
CRITERIA_HEADING = re.compile(r"criteres?")
WEIGHT_HEADER = re.compile(r"ponderation|poids|coefficient|points|bareme")
WEIGHT = re.compile(r"^(\d+(?:[.,]\d+)?)\s*(%|points?|pts)?$")
BULLET_WEIGHT = re.compile(r"^(.+?)\s*[:(–-]\s*(\d+(?:[.,]\d+)?)\s*(%|points?|pts)\)?\.?$")
LEVELS = ["haute", "moyenne", "basse"]
LEVEL_LABELS = {"haute": "haut", "moyenne": "moyen", "basse": "bas"}
KIND_LABELS = {"questions": "Questions au client", "remise": "Remise de l'offre", "soutenance": "Soutenance",
               "visite": "Visite", "demarrage": "Démarrage", "autre": "Autre"}
CLOSE_DAYS = 5  # date limite proche : signalée en dessous de ce nombre de jours
MAX_LISTED = 15


def normalize(text: str) -> str:
    """Minuscules, sans accents ni mise en forme Markdown, espaces réduits."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c)).lower()
    text = text.replace("’", "'").replace("«", '"').replace("»", '"')
    text = re.sub(r"[*_`#>|]|\[|\]|\(http[^)]*\)", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def load_sources(folder: Path) -> dict[str, list[str]]:
    return {path.relative_to(folder).as_posix(): path.read_text(encoding="utf-8", errors="replace").splitlines()
            for path in sorted(folder.rglob("*.md")) if ".myskills-tmp" not in path.parts}


def find_quote(lines: list[str], quote: str) -> int | None:
    """Ligne (à partir de 1) où commence la citation, même coupée sur plusieurs lignes."""
    joined, starts = "", []
    for number, line in enumerate(lines, 1):
        starts.append((len(joined), number))
        joined += normalize(line) + " "
    wanted = normalize(quote)
    at = joined.find(wanted) if wanted else -1
    return max(number for offset, number in starts if offset <= at) if at >= 0 else None


def topic_of(text: str, table: list) -> str:
    key = normalize(text)
    return next((name for name, pattern, *_ in table if re.search(pattern, key)), "autre")


def number(text: str) -> float:
    value = float(text.replace(",", "."))
    return int(value) if value.is_integer() else value


def sections(lines: list[str]):
    """(titre normalisé, numéro de ligne, ligne) de chaque ligne, sous le dernier titre rencontré."""
    heading = ""
    for index, line in enumerate(lines, 1):
        if line.lstrip().startswith("#"):
            heading = normalize(line)
        yield heading, index, line


def sentences(lines: list[str]):
    """(ligne, phrase) des paragraphes et éléments de liste, lignes coupées réunies ; titres et tableaux à part."""
    start, current = 0, []
    for index, line in enumerate(lines + [""], 1):
        stripped = line.strip()
        item = re.match(r"([-*+]|\d+[.)])\s", stripped)
        if not stripped or stripped.startswith(("#", "|")) or item:
            if current:
                for part in re.split(r"(?<=[.!?;])\s+", " ".join(current)):
                    if len(part.strip()) > 12:
                        yield start, part.strip()
            current = []
        if stripped and not stripped.startswith(("#", "|")):
            if not current:
                start = index
            current.append(re.sub(r"^([-*+]|\d+[.)])\s+", "", stripped))


def tables(lines: list[str]):
    """(titre, en-têtes, [(ligne, cellules)]) des tableaux Markdown."""
    rows, header, heading = [], None, ""
    for title, index, line in list(sections(lines)) + [("", len(lines) + 1, "")]:
        stripped = line.strip()
        if stripped.startswith("|"):
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            if set(stripped) <= set("|-: "):
                continue
            if header is None:
                header, heading = cells, title
            else:
                rows.append((index, cells))
            continue
        if header is not None:
            yield heading, header, rows
        rows, header = [], None


def source(doc: str, quote: str) -> dict:
    return {"doc": doc, "quote": quote}


def extract(sources: dict[str, list[str]]) -> dict:
    """Dates, critères, pièces, format et clauses repérés dans les sources, avec leur citation."""
    found = {"dates": [], "criteria": [], "pieces": [], "format": [], "clauses": []}
    seen: set[str] = set()
    for doc, lines in sources.items():
        # Critères en tableau : colonne de poids, sous-critères rattachés au critère dont ils font la somme.
        for heading, header, rows in tables(lines):
            column = next((i for i, h in enumerate(header) if WEIGHT_HEADER.search(normalize(h))), None)
            if column is None:
                continue
            batch = []
            for index, cells in rows:
                weight = WEIGHT.match(cells[column]) if column < len(cells) else None
                label = next((c for i, c in enumerate(cells) if i != column and c and not WEIGHT.match(c)), "")
                if weight and label:
                    batch.append({"label": label, "weight": number(weight.group(1)),
                                  "source": source(doc, " | ".join(c for c in cells if c))})
            total = sum(c["weight"] for c in batch)
            parent = next((c for c in found["criteria"] if c["weight"] == total and total != 100
                           and not any(o.get("parent") == c["id"] for o in found["criteria"])), None)
            for item in batch:
                item["id"] = f"C-{len(found['criteria']) + 1:02d}"
                if parent:
                    item["parent"] = parent["id"]
                item["topic"] = topic_of(item["label"], TOPICS)
                found["criteria"].append({k: item[k] for k in ("id", "label", "weight", "parent", "topic", "source")
                                          if k in item})
                seen.add(normalize(item["source"]["quote"]))
        for heading, index, line in sections(lines):
            stripped = line.strip()
            item = re.match(r"([-*+]|\d+[.)])\s+(.*)$", stripped)
            if not item:
                continue
            text = item.group(2).rstrip(" ;.")
            if CRITERIA_HEADING.search(heading) and BULLET_WEIGHT.match(text):
                label, weight = BULLET_WEIGHT.match(text).group(1, 2)
                found["criteria"].append({"id": f"C-{len(found['criteria']) + 1:02d}", "label": label.strip(),
                                          "weight": number(weight), "topic": topic_of(label, TOPICS),
                                          "source": source(doc, text)})
                seen.add(normalize(text))
            elif PIECES_HEADING.search(heading) and not DATE_TEXT.search(normalize(text)):
                piece = {"id": f"P-{len(found['pieces']) + 1:02d}", "label": text[:1].upper() + text[1:],
                         "kind": topic_of(text, PIECE_KINDS)}
                if piece["kind"] == "autre":
                    piece["kind"] = "technique"
                pages = re.search(r"(\d+)\s*pages", text)
                if pages:
                    piece["pages"] = int(pages.group(1))
                if "memoire technique" in normalize(text):
                    piece["memoire"] = True
                piece["source"] = source(doc, text)
                found["pieces"].append(piece)
                seen.add(normalize(text))
        for index, sentence in sentences(lines):
            key = normalize(sentence)
            if key in seen or any(key in s or s in key for s in seen if len(s) > 20):
                continue
            seen.add(key)
            when = DATE_TEXT.search(key) or DATE_NUM.search(key)
            clause = next(((t, lvl) for t, pattern, lvl in CLAUSES if re.search(pattern, key)), None)
            if when:
                if DATE_TEXT.search(key):
                    day, month, year = int(when.group(1)), MONTHS[when.group(2)], int(when.group(3))
                else:
                    day, month, year = int(when.group(1)), int(when.group(2)), int(when.group(3))
                try:
                    iso = date(year, month, day).isoformat()
                except ValueError:
                    continue
                label = sentence.split(":")[0].strip().rstrip(".") if ":" in sentence else \
                    " ".join(sentence.split()[:8])
                entry = {"id": f"D-{len(found['dates']) + 1:02d}", "kind": topic_of(sentence, DATE_KINDS),
                         "label": label, "date": iso}
                hour = TIME.search(key[when.end():])
                if hour:
                    entry["time"] = f"{int(hour.group(1)):02d}:{hour.group(2) or '00'}"
                entry["source"] = source(doc, sentence)
                found["dates"].append(entry)
            elif clause:
                level = "moyenne" if clause[0] == "penalites" and "plafonn" in key else clause[1]
                found["clauses"].append({"id": f"R-{len(found['clauses']) + 1:02d}", "topic": clause[0],
                                         "text": sentence, "level": level, "source": source(doc, sentence)})
            elif FORMAT.search(key):
                found["format"].append({"id": f"F-{len(found['format']) + 1:02d}", "text": sentence,
                                        "source": source(doc, sentence)})
    return found


def draft(path: Path, sources_name: str) -> dict:
    errors: list[str] = []
    report = {"input": str(path), "outputs": [], "dates": 0, "criteria": 0, "pieces": 0, "format": 0,
              "clauses": 0, "documents": 0, "errors": errors, "warnings": []}
    if path.exists():
        errors.append(f"{path} existe déjà : --draft ne réécrit pas une description")
        return report
    folder = path.parent / sources_name
    sources = load_sources(folder) if folder.is_dir() else {}
    if not sources:
        errors.append(f"sources : aucun fichier .md dans {folder}")
        return report
    found = extract(sources)
    spec = {"title": "Dépouillement de l'appel d'offres", "sources": sources_name, **found,
            "_draft": "Brouillon de tender_build.py --draft. À relire : corriger libellés, natures de dates, thèmes "
                      "et rattachement des critères ; noter chaque clause (note : pourquoi c'est un risque, que "
                      "faire) et ajuster son niveau ; passer dans ignored, avec sa raison, ce qui ne sert pas."}
    invalid = validate(spec, __file__)
    if invalid:
        errors.extend(invalid)
        return report
    path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    report.update(outputs=[str(path)], documents=len(sources), **{k: len(v) for k, v in found.items()})
    if not found["criteria"]:
        report["warnings"].append("aucun tableau ou liste de pondération trouvé : critères à saisir")
    if not any(d["kind"] == "remise" for d in found["dates"]):
        report["warnings"].append("date limite de remise des offres non trouvée : à saisir")
    return report


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def fmt(value) -> str:
    return str(value).replace(".", ",")


def check(spec: dict, base: Path, today: date, errors: list[str], warnings: list[str]) -> dict:
    folder = (base / spec.get("sources", "sources")).resolve()
    sources = load_sources(folder) if folder.is_dir() else {}
    if not sources:
        errors.append(f"sources : aucun fichier .md dans {folder}")
        return {}
    quotes: set[str] = set()

    def locate(where: str, ref: dict) -> str:
        doc = ref["doc"].replace("\\", "/")
        if doc not in sources:
            close = difflib.get_close_matches(doc, list(sources), n=1, cutoff=0.5)
            errors.append(f"{where} : document « {doc} » absent des sources"
                          + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
            return doc
        line = find_quote(sources[doc], ref["quote"])
        if line is None:
            close = difflib.get_close_matches(ref["quote"], [l.strip() for l in sources[doc] if l.strip()],
                                              n=1, cutoff=0.4)
            errors.append(f"{where} : citation introuvable dans {doc} : « {ref['quote'][:80]} »"
                          + (f" ; ligne proche : « {close[0][:80]} »" if close else ""))
            return doc
        quotes.add(normalize(ref["quote"]))
        return f"{doc}:{line}"

    for field in ("dates", "criteria", "pieces", "format", "clauses"):
        ids = [item["id"] for item in spec.get(field, [])]
        errors += [f"{field} : identifiant en double {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
        for index, item in enumerate(spec.get(field, [])):
            item["_where"] = locate(f"{field}/{index} ({item['id']})", item["source"])
    for index, item in enumerate(spec.get("ignored", [])):
        item["_where"] = locate(f"ignored/{index}", item)

    # Critères : parents connus, premier niveau sur 100, sous-critères égaux à leur critère.
    criteria = spec.get("criteria", [])
    by_id = {c["id"]: c for c in criteria}
    for index, c in enumerate(criteria):
        if c.get("parent") and c["parent"] not in by_id:
            close = difflib.get_close_matches(c["parent"], list(by_id), n=1, cutoff=0.6)
            errors.append(f"criteria/{index} ({c['id']}) : parent inconnu « {c['parent']} »"
                          + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
    top = [c for c in criteria if not c.get("parent")]
    if criteria and abs(sum(c["weight"] for c in top) - 100) > 0.01:
        warnings.append(f"critères de premier niveau : total {fmt(sum(c['weight'] for c in top))} au lieu de 100")
    for c in criteria:
        children = [o for o in criteria if o.get("parent") == c["id"]]
        if children and abs(sum(o["weight"] for o in children) - c["weight"]) > 0.01:
            warnings.append(f"critère {c['id']} : sous-critères à {fmt(sum(o['weight'] for o in children))} pour un "
                            f"poids de {fmt(c['weight'])}")
    if not criteria:
        warnings.append("aucun critère de notation : la réponse ne peut pas suivre la grille")

    # Dates : remise présente, questions avant remise, temps restant.
    dated = {}
    for index, d in enumerate(spec.get("dates", [])):
        try:
            d["_date"] = date.fromisoformat(d["date"])
        except ValueError:
            errors.append(f"dates/{index} ({d['id']}) : date invalide « {d['date']} » (AAAA-MM-JJ)")
            continue
        dated.setdefault(d["kind"], d)
    if "remise" not in dated:
        warnings.append("date limite de remise des offres absente")
    if "questions" in dated and "remise" in dated and dated["questions"]["_date"] > dated["remise"]["_date"]:
        warnings.append("date limite des questions postérieure à la remise des offres")
    deadlines = {}
    for kind in ("questions", "remise"):
        if kind in dated:
            left = (dated[kind]["_date"] - today).days
            deadlines[kind] = {"date": dated[kind]["date"], "days_left": left}
            label = KIND_LABELS[kind].lower()
            if left < 0:
                warnings.append(f"date limite passée ({label}) : {dated[kind]['date']}")
            elif left < CLOSE_DAYS:
                warnings.append(f"date limite proche ({label}) : {dated[kind]['date']}, dans {left} jour(s)")

    # Clauses : une clause haute se note ; pièces : le mémoire et son budget de pages.
    for c in spec.get("clauses", []):
        if c["level"] == "haute" and not c.get("note"):
            warnings.append(f"clause {c['id']} ({c['topic']}) de risque haut sans note : pourquoi, que faire")
    memoire = next((p for p in spec.get("pieces", []) if p.get("memoire")), None)
    if spec.get("pieces") and not memoire:
        warnings.append("aucune pièce marquée memoire : le budget de pages du mémoire technique est inconnu")

    # Éléments des sources repris par aucune entrée ni écartés.
    found = extract(sources)
    uncovered = [f"{item['source']['doc']}:{find_quote(sources[item['source']['doc']], item['source']['quote'])} "
                 f"« {item['source']['quote'][:100]} »"
                 for field in found.values() for item in field
                 if not any(normalize(item["source"]["quote"]) in q or q in normalize(item["source"]["quote"])
                            for q in quotes)]
    warnings += [f"élément du dossier non repris ni écarté : {u}" for u in uncovered[:MAX_LISTED]]
    if len(uncovered) > MAX_LISTED:
        warnings.append(f"... et {len(uncovered) - MAX_LISTED} autres éléments non repris")
    return {"deadlines": deadlines, "uncovered": len(uncovered), "documents": len(sources),
            "memoire_pages": memoire.get("pages") if memoire else None}


def render(spec: dict, today: date) -> str:
    lines = [f"# {spec.get('title') or 'Dépouillement'}", "",
             "Fichier généré par `tender_build.py` depuis `ao.json`, qui fait foi."]
    if spec.get("reference") or spec.get("buyer"):
        lines += ["", " ; ".join(x for x in (spec.get("buyer"), spec.get("reference") and
                                               f"référence {spec['reference']}") if x) + "."]
    lines += ["", "## Calendrier", "", "| Date | Heure | Échéance | Objet | Nature | Source |",
              "| --- | --- | --- | --- | --- | --- |"]
    for d in sorted(spec.get("dates", []), key=lambda d: d["date"]):
        left = (d["_date"] - today).days if "_date" in d else None
        due = "" if left is None else ("passée" if left < 0 else f"J-{left}")
        lines.append(f"| {d['date']} | {d.get('time', '')} | {due} | {cell(d['label'])} | "
                     f"{KIND_LABELS[d['kind']]} | {d['_where']} |")
    criteria = spec.get("criteria", [])
    lines += ["", "## Critères de notation", "", "| Critère | Poids | Thème | Source |", "| --- | --- | --- | --- |"]
    for c in [c for c in criteria if not c.get("parent")]:
        lines.append(f"| **{c['id']} {cell(c['label'])}** | {fmt(c['weight'])} | {c['topic']} | {c['_where']} |")
        for o in [o for o in criteria if o.get("parent") == c["id"]]:
            lines.append(f"| {o['id']} ↳ {cell(o['label'])} | {fmt(o['weight'])} | {o['topic']} | {o['_where']} |")
    lines += ["", "## Pièces à fournir", ""]
    for p in spec.get("pieces", []):
        extra = f", {p['pages']} pages au plus" if p.get("pages") else ""
        lines.append(f"- [ ] **{p['id']}** {p['label']} ({p['kind']}{extra}) : {p['_where']}")
    if spec.get("format"):
        lines += ["", "## Format de réponse", ""] + [f"- {f['text']} ({f['_where']})" for f in spec["format"]]
    lines += ["", "## Clauses à risque", ""]
    for level in LEVELS:
        items = [c for c in spec.get("clauses", []) if c["level"] == level]
        if items:
            lines += [f"### Risque {LEVEL_LABELS[level]}", "", "| Clause | Thème | Texte | Note | Source |",
                      "| --- | --- | --- | --- | --- |"]
            lines += [f"| {c['id']} | {c['topic']} | {cell(c['text'])} | {cell(c.get('note', 'à noter'))} | "
                      f"{c['_where']} |" for c in items]
            lines.append("")
    if spec.get("ignored"):
        lines += ["## Éléments écartés", ""] + [f"- {i['_where']} « {i['quote'][:100]} » : {i['reason']}"
                                                for i in spec["ignored"]]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).rstrip() + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description ao.json")
    parser.add_argument("--out-dir", type=Path, help="dossier de ao.md (défaut : celui du .json)")
    parser.add_argument("--today", help="date du jour pour le temps restant (AAAA-MM-JJ, défaut : aujourd'hui)")
    parser.add_argument("--draft", action="store_true", help="écrire le brouillon de la description depuis les sources")
    parser.add_argument("--sources", default="sources", help="avec --draft : dossier des sources (défaut : sources)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
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
    errors: list[str] = []
    warnings: list[str] = []
    report = {"input": str(args.spec), "output": None, "dates": 0, "criteria": 0, "pieces": 0, "clauses": {},
              "deadlines": {}, "memoire_pages": None, "uncovered": 0, "errors": errors, "warnings": warnings}
    try:
        today = date.fromisoformat(args.today) if args.today else date.today()
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        print(json.dumps(report, ensure_ascii=False))
        return 1
    errors += validate(spec, __file__)
    if not errors:
        report.update(check(spec, args.spec.resolve().parent, today, errors, warnings))
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    out = (args.out_dir or args.spec.resolve().parent) / f"{args.spec.stem}.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    text = render(spec, today)
    ai_mark.write_text(out, text)
    # Relecture : chaque identifiant figure dans le fichier produit.
    written = out.read_text(encoding="utf-8")
    missing = [i["id"] for f in ("dates", "criteria", "pieces", "clauses") for i in spec.get(f, [])
               if f == "dates" and i["date"] not in written or f != "dates" and i["id"] not in written]
    if missing:
        errors.append(f"{out.name} incomplet : {', '.join(missing[:5])}")
    report.update(output=str(out), dates=len(spec.get("dates", [])), criteria=len(spec.get("criteria", [])),
                  pieces=len(spec.get("pieces", [])),
                  clauses={level: sum(1 for c in spec.get("clauses", []) if c["level"] == level) for level in LEVELS})
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
