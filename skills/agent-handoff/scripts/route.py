# /// script
# requires-python = ">=3.10"
# ///
"""Liste les agents et workflows qui peuvent répondre à une demande, classés, depuis le catalogue de routage.

Le catalogue (`lib/routes.json`, généré par scripts/build.py depuis les
contrats, les agents et les workflows) donne pour chaque agent, workflow et
skill son niveau, sa description en une phrase et ses entrées : quelques
lignes au lieu de catalog.json. Avec --query, les candidats sont classés
par les mots qu'ils partagent avec la demande (accents et mots vides
ignorés, racines de 5 lettres, mots rares pesant plus) et par les
extensions des fichiers fournis. Le score n'est qu'un indice : l'agent
orientation choisit en lisant les descriptions.

Avec --laya, le modèle local Laya (route_laya.py, dans son propre
environnement) choisit parmi les premiers candidats d'après leur
description ; son choix passe en tête quand sa confiance est d'au moins
LAYA_CONFIDENT, sinon il est seulement donné dans `laya`. Réponses en cache,
classement par mots gardé si Laya est indisponible.

Dans une mission (mission.json, skill mission-workspace, trouvé au-dessus
des fichiers fournis ou du dossier courant), le rapport donne sa nature, ses
workflows et son vault, et ses workflows passent devant à score proche.

    uv run scripts/route.py --query "TEXTE" [--files F1 F2...] [--kind agents|workflows|skills|all] [--top N] [--laya [--laya-cache F]]
    uv run scripts/route.py --list [--kind ...]
"""

import argparse
import hashlib
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workspace  # noqa: E402

ROUTES = Path(__file__).resolve().parent / "lib" / "routes.json"
# Bonus d'un workflow de la mission (mission.json au-dessus des fichiers ou du dossier courant).
MISSION_BONUS = 2.0
LAYA = Path(__file__).resolve().parent / "route_laya.py"
# Candidats soumis à Laya (les premiers du classement par mots), et confiance qui fait passer son choix en tête.
LAYA_CANDIDATES, LAYA_CONFIDENT = 6, 0.6
STOP = set("""a au aux avec ce ces cette d dans de des du elle en et est il je la le les leur lui ma mais me
mes mon ne nos notre nous on ou par pas pour qu que qui sa se ses son sur ta te tes ton tu un une vos votre
vous l j m n s t y fais faire faut peux veux voudrais besoin aide aider moi ici sont avoir etre tout tous plus
quoi comment""".split())
# Extension d'un fichier fourni -> mots qui la rapprochent des bons candidats.
EXTENSIONS = {".pdf": "pdf document convertit", ".docx": "word document convertit",
              ".pptx": "powerpoint presentation document", ".xlsx": "excel document",
              ".png": "image schema", ".jpg": "image", ".md": "markdown documentation",
              ".drawio": "schema drawio", ".tf": "terraform infrastructure code", ".yaml": "kubernetes infrastructure",
              ".yml": "docker compose infrastructure", ".csv": "inventaire applications", ".json": "description"}
KINDS = ("agents", "workflows", "skills")
# Familles de mots de même sens, ramenées à un seul mot avant comparaison.
SYNONYMS = {"coute": "chiff", "budge": "chiff", "prix": "chiff",
            "estim": "chiff", "combi": "chiff", "diagr": "schem", "dessi": "schem", "conve": "conve",
            "impor": "conve", "extra": "conve", "trans": "conve", "secur": "menac", "risqu": "menac", "strid": "menac",
            "exige": "exige", "besoi": "exige", "cahie": "exige", "spec": "exige", "speci": "exige",
            "publi": "publi", "expor": "publi", "infra": "infra", "terra": "infra", "kuber": "infra"}


def words(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    roots = {w[:5] for w in re.findall(r"[a-z0-9]+", plain) if w not in STOP and len(w) > 1}
    return {SYNONYMS.get(r, r) for r in roots}


def entry_text(kind: str, entry: dict) -> str:
    parts = [entry["name"].replace("-", " "), entry.get("title", ""), entry["description"], entry.get("match", ""),
             " ".join(entry.get("receives", []) or entry.get("inputs", [])), " ".join(entry.get("stages", []))]
    return " ".join(parts)


def ask_laya(query: str, candidates: list[dict], cache_path: Path, warnings: list[str]) -> dict | None:
    """Choix de Laya parmi les candidats (cache d'abord) ; None si Laya est indisponible."""
    names = {c["name"]: c["description"] for c in candidates}
    key = hashlib.sha1(json.dumps([" ".join(sorted(words(query))), sorted(names)]).encode("utf-8")).hexdigest()[:16]
    try:
        cache = json.loads(cache_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        cache = {}
    if key in cache.get("answers", {}):
        return {"method": cache.get("method", "laya"), **cache["answers"][key]}
    with tempfile.TemporaryDirectory() as tmp:
        question = Path(tmp) / "question.json"
        question.write_text(json.dumps({"query": query, "candidates": names}, ensure_ascii=False), encoding="utf-8")
        command = ["uv", "run", "--quiet", str(LAYA)] if shutil.which("uv") else [sys.executable, str(LAYA)]
        result = subprocess.run(command + [str(question)], capture_output=True, text=True, encoding="utf-8")
    try:
        report = json.loads(result.stdout)
    except ValueError:
        lines = (result.stderr or "sortie vide").strip().splitlines()
        report = {"errors": [lines[-1][:300] if lines else "?"]}
    if report.get("errors") or report.get("choice") not in names:
        reason = (report.get("errors") or ["aucun choix"])[0]
        warnings.append(f"Laya indisponible, classement par mots : {reason.removeprefix('Laya indisponible : ')}")
        return None
    answer = {"choice": report["choice"], "confidence": report["confidence"]}
    cache.setdefault("answers", {})[key] = answer
    cache["method"] = report.get("method") or cache.get("method")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {"method": cache["method"], **answer}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--query", help="la demande de l'utilisateur, telle quelle")
    parser.add_argument("--files", nargs="*", default=[], help="fichiers fournis avec la demande")
    parser.add_argument("--kind", choices=KINDS + ("all",), default=None,
                        help="candidats à classer (défaut : agents et workflows ; all : avec les skills)")
    parser.add_argument("--top", type=int, default=0,
                        help="nombre de candidats rendus (défaut : tous, classés ; le score n'est qu'un indice)")
    parser.add_argument("--list", action="store_true", help="tous les candidats, sans classement")
    parser.add_argument("--laya", action="store_true",
                        help="faire choisir le modèle local Laya parmi les premiers candidats")
    parser.add_argument("--laya-cache", type=Path,
                        help="cache des réponses de Laya (défaut : .myskills-tmp/route.laya.json du dossier courant)")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    report = {"query": args.query, "candidates": [], "laya": None, "mission": None, "errors": errors,
              "warnings": warnings}
    root = workspace.find(*args.files, Path.cwd())
    if root is not None:
        mission, invalid = workspace.load(root)
        warnings += invalid
        if mission:
            report["mission"] = {"root": str(root), "nature": mission["nature"],
                                 "workflows": [w["definition"] for w in workspace.workflows(mission)],
                                 "vault": str(workspace.path_of(root, mission, "vault"))}
    if not args.query and not args.list:
        errors.append("--query TEXTE (la demande) ou --list")
    try:
        routes = json.loads(ROUTES.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"catalogue de routage illisible ({ROUTES.name}) : {error} ; lancez uv run scripts/build.py")
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    kinds = KINDS if args.kind == "all" else (args.kind,) if args.kind else ("agents", "workflows")
    wanted = words(args.query or "")
    for name in args.files:
        wanted |= words(EXTENSIONS.get(Path(name).suffix.lower(), ""))
    entries = [(kind, entry, words(entry_text(kind, entry))) for kind in kinds for entry in routes[kind]]
    # Poids d'un mot : rare parmi les candidats, il départage ; présent partout (architecture), il ne compte guère.
    frequency = {}
    for _, _, vocabulary in entries:
        for word in vocabulary:
            frequency[word] = frequency.get(word, 0) + 1
    scored = []
    for kind, entry, vocabulary in entries:
        # Un mot court de la demande (doc, appli) vaut pour les mots qui le prolongent (documents, application).
        common = sorted(w for w in wanted if w in vocabulary or len(w) >= 3 and any(v.startswith(w) for v in vocabulary))
        item = {"kind": kind[:-1], "name": entry["name"], "level": entry.get("level"),
                "description": entry["description"]}
        if kind == "workflows":
            item.update(agent=entry["agent"], stages=entry["stages"])
        if not args.list:
            # Un mot du nom même du candidat (schema-designer pour « schéma ») pèse un point de plus.
            named = words(entry["name"].replace("-", " "))
            item["score"] = round(sum(math.log((len(entries) + 1) / frequency.get(w, 1)) + (w in named)
                                      for w in common), 2)
            if kind == "workflows" and report["mission"] and entry["name"] in report["mission"]["workflows"]:
                item["score"] = round(item["score"] + MISSION_BONUS, 2)
            item["matched"] = common
        scored.append(item)
    if args.list:
        report["candidates"] = scored
    else:
        # Un workflow enchaîne plusieurs agents : à score égal, il passe avant un agent seul.
        scored.sort(key=lambda c: (-c["score"], c["kind"] != "workflow", c["name"]))
        decided = False
        if args.laya or args.laya_cache:
            cache = args.laya_cache or Path(".myskills-tmp") / "route.laya.json"
            said = ask_laya(args.query, scored[:LAYA_CANDIDATES], cache, warnings)
            if said:
                report["laya"] = said
                if said["confidence"] >= LAYA_CONFIDENT:
                    chosen = next(c for c in scored if c["name"] == said["choice"])
                    scored, decided = [chosen] + [c for c in scored if c is not chosen], True
                else:
                    warnings.append(f"Laya choisit {said['choice']} sans assurance ({said['confidence']}) : "
                                    "classement par mots gardé")
        report["candidates"] = scored[:args.top] if args.top else scored
        if not report["candidates"] or report["candidates"][0]["score"] == 0:
            warnings.append("aucun candidat ne partage de mot avec la demande : posez la question à l'utilisateur, "
                            "ou relancez avec --list")
        elif not decided and len(report["candidates"]) > 1 and \
                report["candidates"][0]["score"] == report["candidates"][1]["score"]:
            warnings.append(f"{report['candidates'][0]['name']} et {report['candidates'][1]['name']} à égalité : "
                            "départagez par la description, ou posez une question")
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
