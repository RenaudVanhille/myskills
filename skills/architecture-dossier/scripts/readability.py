# /// script
# requires-python = ">=3.10"
# ///
"""Contrôle la lisibilité de documents Markdown pour un public métier et en tire le glossaire.

Pour chaque fichier : phrases trop longues, longueur moyenne, score de
lisibilité (Flesch adapté au français par Kandel et Moles : 60 et plus se lit
facilement, moins de 40 est difficile), sigles employés sans définition et,
pour un public métier, mots de jargon avec leur équivalent simple. Le code,
les liens et les images sont ignorés ; les titres et les tableaux comptent
pour les sigles, pas pour les phrases.

Un sigle est défini s'il figure au dictionnaire livré
(`references/glossaire.json`), dans un fichier de termes (`--terms` :
termes.json, ou le glossaire d'un catalogue d'exigences exigences.json), ou
dans le texte même (« SSO (connexion unique) », « connexion unique (SSO) »).
Avec --glossary, le glossaire des termes rencontrés est écrit en Markdown ;
un sigle sans définition y manque et le rapport le signale (erreur avec
--strict, sans fichier produit).

Un argument à motif (`parcours*.md`) sans fichier est ignoré : les pièces
facultatives d'un workflow se passent sans condition.

    uv run scripts/readability.py FICHIER.md... [--terms termes.json]... [--glossary glossaire.md]
                                  [--audience metier|technique] [--max-words 25] [--strict] | --schema
"""

import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from script_report import failures  # noqa: E402
from skill_paths import absent, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402
from text_tools import cell  # noqa: E402

DICTIONARY = Path(__file__).resolve().parent.parent / "references" / "glossaire.json"
EASY, HARD = 60, 40
VOWELS = re.compile(r"[aeiouyàâäéèêëîïôöùûüœæ]+", re.I)
WORD = re.compile(r"[\wÀ-ÿœæ'’-]+")
# Sigle : au moins deux majuscules, sans tiret ni chiffre qui en ferait un identifiant (EF-001, UJ1).
ACRONYM = re.compile(r"(?<![\w/-])([A-Z][A-Za-z]*[A-Z][A-Za-z]*)(?![\w/-]*\d)(?![-\w])")
IDENTIFIER = re.compile(r"^[A-Z]+\d+$")


def expand(patterns: list[str]) -> list[Path]:
    """Fichiers des arguments : un motif sans fichier est ignoré, un nom simple est gardé tel quel."""
    found: list[Path] = []
    for item in patterns:
        if any(c in item for c in "*?["):
            base = Path(item)
            anchor = Path(base.anchor) if base.is_absolute() else Path(".")
            pattern = str(base.relative_to(anchor)) if base.is_absolute() else item
            found += [p for p in sorted(anchor.glob(pattern)) if p.is_file() and p not in found]
        elif Path(item) not in found:
            found.append(Path(item))
    return found


def strip(text: str) -> tuple[str, str]:
    """(texte complet sans code ni liens, texte des seules phrases) : titres et tableaux hors phrases."""
    text = re.sub(r"\A---\n.*?\n---\n", "", text, count=1, flags=re.S)
    text = re.sub(r"^(```|~~~).*?^\1[^\n]*$", "", text, flags=re.S | re.M)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    text = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", text)
    text = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`[^`\n]*`", "", text)
    text = re.sub(r"https?://\S+", "", text)
    prose = []
    for line in text.splitlines():
        line = re.sub(r"^\s*(>\s*)*(\[![\w-]+\][+-]?\s*)?", "", line)
        if not line.strip() or line.lstrip().startswith(("#", "|")):
            prose.append("")
            continue
        prose.append(re.sub(r"^\s*([-*+]|\d+[.)])\s+", "", line))
    return text, "\n".join(prose)


def sentences(prose: str) -> list[str]:
    """Phrases : un paragraphe ou un élément de liste se coupe sur . ! ? … suivi d'une majuscule."""
    found = []
    for block in re.split(r"\n\s*\n|\n(?=\S)", prose):
        block = " ".join(block.split())
        found += [s for s in re.split(r"(?<=[.!?…])\s+(?=[A-ZÀ-Ý«\"(])", block) if WORD.search(s)]
    return found


def syllables(word: str) -> int:
    """Syllabes estimées : groupes de voyelles, e muet final retiré."""
    count = len(VOWELS.findall(word))
    if count > 1 and re.search(r"[^aeiouy]e(s|nt)?$", word.lower()):
        count -= 1
    return max(1, count)


def load_terms(path: Path, errors: list[str]) -> dict:
    """Termes d'un fichier : termes.json (schéma du script) ou glossaire d'un catalogue d'exigences."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"--terms : fichier illisible {path} ({error})")
        return {}
    if isinstance(data, dict) and "requirements" in data:
        schema = schema_of("requirements-catalog", "req_build.py")
        invalid = check(data, schema) if schema else [absent("requirements-catalog", "req_build.py")]
        if invalid:
            errors.extend(f"--terms : {path.name} : {e}" for e in invalid[:5])
            return {}
        return {"terms": {g["term"]: g["definition"] for g in data.get("glossary", [])}}
    invalid = validate(data, __file__)
    errors.extend(f"--terms : {path.name} : {e}" for e in invalid)
    return {} if invalid else data


def defined_in_text(term: str, text: str) -> str | None:
    """Définition donnée dans le texte : « SSO (connexion unique) » ou « connexion unique (SSO) »."""
    after = re.search(rf"(?<!\w){re.escape(term)}s?\s*\(([^)]{{4,120}})\)", text)
    if after and not ACRONYM.fullmatch(after.group(1).strip()):
        return after.group(1).strip()
    before = re.search(rf"([\w'’ -]{{4,80}})\s*\(\s*{re.escape(term)}\s*\)", text)
    return " ".join(before.group(1).split()[-6:]) if before else None


def analyse(path: Path, words_max: int, audience: str, known: dict, jargon: dict, ignore: set) -> dict:
    """Mesures d'un fichier et termes rencontrés (sigles et termes du dictionnaire)."""
    result = {"file": str(path), "words": 0, "sentences": 0, "avg_words": 0, "long_sentences": 0,
              "examples": [], "score": None, "terms": [], "undefined": [], "jargon": [], "errors": []}
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as error:
        result["errors"].append(f"fichier illisible ({error})")
        return result
    text, prose = strip(raw)
    phrases = sentences(prose)
    counts = [len(WORD.findall(s)) for s in phrases]
    words = [w for s in phrases for w in WORD.findall(s)]
    result.update(words=len(words), sentences=len(phrases),
                  avg_words=round(len(words) / len(phrases), 1) if phrases else 0)
    longs = [s for s, n in zip(phrases, counts) if n > words_max]
    result["long_sentences"] = len(longs)
    result["examples"] = [(s[:77] + "...") if len(s) > 80 else s for s in longs[:3]]
    if words:
        per_sentence = len(words) / len(phrases)
        per_word = sum(syllables(w) for w in words) / len(words)
        result["score"] = round(207 - 1.015 * per_sentence - 73.6 * per_word)
    seen: dict[str, str | None] = {}
    scan = text
    for term in sorted(known, key=len, reverse=True):
        pattern = rf"(?<![\w/-]){re.escape(term)}s?(?![\w/-])"
        if re.search(pattern, scan):
            seen[term] = known[term]
            scan = re.sub(pattern, " ", scan)
    for match in ACRONYM.finditer(scan):
        token = match.group(1)
        base = token[:-1] if token.endswith("s") and len(token) > 2 else token
        upper = sum(c.isupper() for c in base)
        # Sigle : plus de majuscules que de minuscules (SaaS, IaC) ; pas un nom propre (PowerPoint), ni un identifiant.
        if base in seen or base in ignore or IDENTIFIER.match(base) or upper < len(base) - upper:
            continue
        seen[base] = known.get(base)
    for term in list(seen):
        if not seen[term]:
            seen[term] = defined_in_text(term, text)
    result["terms"] = sorted(t for t in seen if seen[t])
    result["undefined"] = sorted(t for t in seen if not seen[t])
    result["_definitions"] = seen
    if audience == "metier":
        for word, plain in jargon.items():
            if re.search(rf"(?<![\w-]){re.escape(word)}s?(?![\w-])", text, re.I):
                result["jargon"].append(f"{word} : préférer « {plain} »")
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*", help="documents Markdown (motifs acceptés ; un motif sans fichier est ignoré)")
    parser.add_argument("--terms", action="append", default=[],
                        help="termes et définitions : termes.json, ou exigences.json (son glossaire) ; répétable, "
                             "motif sans fichier ignoré")
    parser.add_argument("--glossary", type=Path, help="glossaire Markdown des termes rencontrés")
    parser.add_argument("--audience", choices=["metier", "technique"], default="metier",
                        help="metier (défaut) : jargon signalé ; technique : sigles et phrases seulement")
    parser.add_argument("--max-words", type=int, default=25, help="mots au plus par phrase (défaut 25)")
    parser.add_argument("--strict", action="store_true",
                        help="sigle sans définition : erreur, et aucun glossaire produit")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON du fichier de termes sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    errors: list[str] = []
    warnings: list[str] = []
    report = {"results": [], "glossary": None, "errors": errors, "warnings": warnings}
    files = expand(args.files)
    if not files:
        errors.append("aucun document : donnez au moins un fichier Markdown existant")
    dictionary = json.loads(DICTIONARY.read_text(encoding="utf-8"))
    known, jargon = dict(dictionary["terms"]), dict(dictionary["jargon"])
    ignore = set(dictionary.get("ignore", []))
    for path in expand(args.terms):
        extra = load_terms(path, errors)
        known.update(extra.get("terms", {}))
        jargon.update(extra.get("jargon", {}))
        ignore.update(extra.get("ignore", []))
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    definitions: dict[str, str | None] = {}
    for path in files:
        if not path.is_file():
            report["results"].append({"file": str(path), "errors": ["fichier introuvable"]})
            continue
        result = analyse(path, args.max_words, args.audience, known, jargon, ignore)
        for term, value in result.pop("_definitions").items():
            definitions[term] = definitions.get(term) or value
        report["results"].append(result)
        name = path.name
        if result["long_sentences"]:
            warnings.append(f"{name} : {result['long_sentences']} phrase(s) de plus de {args.max_words} mots, "
                            f"à couper (« {result['examples'][0]} »)")
        if result["score"] is not None and result["score"] < HARD and args.audience == "metier":
            warnings.append(f"{name} : lecture difficile (score {result['score']}, viser {EASY} ou plus) : "
                            "phrases plus courtes, mots plus simples")
        if result["jargon"]:
            warnings.append(f"{name} : jargon pour un public métier : {' ; '.join(result['jargon'][:5])}")
    undefined = sorted(t for t, d in definitions.items() if not d)
    if undefined:
        message = (f"{len(undefined)} sigle(s) sans définition : {', '.join(undefined[:10])} ; définissez-les "
                   "à la première occurrence (« SSO (connexion unique) ») ou dans termes.json "
                   "({\"terms\": {\"SIGLE\": \"définition\"}}), ou écartez-les (ignore)")
        (errors if args.strict else warnings).append(message)
    errors += failures(report["results"])
    if args.glossary and not errors:
        rows = sorted(((t, d) for t, d in definitions.items() if d), key=lambda x: x[0].lower())
        md = ["# Glossaire", "", "Sigles et termes techniques employés dans ce document, avec leur définition.", ""]
        md += ["| Terme | Définition |", "| --- | --- |"] + [f"| {cell(t)} | {cell(d)} |" for t, d in rows]
        if not rows:
            md = md[:2] + ["Aucun sigle ni terme technique relevé."]
        args.glossary.parent.mkdir(parents=True, exist_ok=True)
        args.glossary.write_text("\n".join(md) + "\n", encoding="utf-8", newline="\n")
        # Relecture : une ligne par terme défini.
        written = args.glossary.read_text(encoding="utf-8").count("\n| ") - 2 if rows else 0
        if written != len(rows):
            errors.append(f"{args.glossary.name} : {written} terme(s) écrits au lieu de {len(rows)}")
        report["glossary"] = {"output": str(args.glossary), "terms": len(rows), "undefined": undefined}
    elif args.glossary is None:
        report["glossary"] = {"output": None, "terms": sum(1 for d in definitions.values() if d),
                              "undefined": undefined}
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
