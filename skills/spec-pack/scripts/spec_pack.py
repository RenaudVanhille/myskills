# /// script
# requires-python = ">=3.10"
# ///
"""Extrait d'une mission un dossier de spécifications autonome, pour le développement assisté par IA.

Le script, et non le modèle, lit le dossier du workflow (exigences.json obligatoire ; options.json,
decision.json, domaines.json, modele.json, api.json, recette.json, registre.json, design-system.json,
pages/*.json, revue-ux.json, decoupage.json s'ils existent), valide chaque pièce contre le schéma du skill
qui l'a produite, puis écrit un dossier de documents Markdown qui se lisent chacun seul, sans format
propre à un outil (BMAD, Spec Kit, Kiro, Copilot...) :

- `README.md` : index, conventions d'identifiants, traçabilité exigence -> composants -> cas -> story ;
- `fonctionnel.md` : vision, utilisateurs, parcours, glossaire, exigences fonctionnelles FR-n avec leurs
  critères d'acceptation, périmètre, indicateurs, questions, hypothèses ;
- `ux.md` : identité visuelle et tokens, écrans, maquettes HTML et code, composants, accessibilité ;
- `architecture.md` : option retenue, décisions AD-n, pile technique et versions, composants et flux,
  données, interfaces, exigences non fonctionnelles NFR-n, options écartées, risques ;
- `tests.md` : stratégie, cas de recette, vérification des NFR, couverture ;
- `livraison.md` : lots et stories S-n.m, ordre, dépendances, définition de terminé, et le coût IA du
  développement estimé au chiffrage (<nom>.ia.json de solution-estimate) s'il existe.

Le dossier est autonome : les pièces citées sont copiées dans annexes/ et les maquettes dans maquettes/,
leurs liens (Markdown, wikilinks, HTML, CSS) recalés sur les copies, une image ou une feuille de style
qu'elles visent copiée à son tour ; un lien vers une note du vault ou un autre fichier de la mission
devient du texte. Aucun lien ne sort du dossier, aucun chemin de la machine n'y figure : l'export échoue
sinon. `--check` contrôle un dossier déjà copié ailleurs.

Le modèle n'écrit, au besoin, que `specs.json` : ce que la mission ne dit pas (vision, utilisateurs,
parcours, hors-périmètre, indicateurs de succès, regroupement en fonctionnalités, frameworks et versions).

Avant d'écrire, le script relit ce qu'il a produit : chaque exigence a son identifiant dans son document,
chaque FR sa story et sa ligne de couverture, chaque lien mène à un fichier du dossier. Un document modifié
depuis le dernier export n'est pas écrasé sans --force (empreintes dans .spec-pack.json, côté mission).

    uv run scripts/spec_pack.py [DOSSIER] [--out DOSSIER_DES_SPECS] [--file specs.json] [--option ID]
                                [--force] | --check DOSSIER_DES_SPECS | --schema
"""

import argparse
import hashlib
import json
import re
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import pack_bundle  # noqa: E402
from text_tools import data_file  # noqa: E402
import pack_model  # noqa: E402
import pack_render  # noqa: E402
import pack_ux  # noqa: E402
from skill_paths import absent, load_module, schema_of  # noqa: E402
from spec_schema import check, print_schema, schema_option, validate  # noqa: E402

# État des exports, gardé côté mission (jamais dans le dossier) : empreinte de chaque document écrit.
STATE = ".spec-pack.json"
OUT = "specs"
# Livrable -> (fichiers possibles dans le dossier du workflow, skill et script dont le schéma le valide).
PIECES = {
    "requirements": (("exigences.json",), "requirements-catalog", "req_build.py"),
    "options": (("options.json",), "architecture-options", "options_build.py"),
    "domains": (("domaines.json",), "domain-design", "domain_build.py"),
    "model": (("modele.json",), "data-model", "model_build.py"),
    "api": (("api.json", "api/api.json"), "api-contract", "api_build.py"),
    "tests": (("recette.json",), "test-plan", "test_build.py"),
    "register": (("registre.json",), "tender-response", "assumptions.py"),
    "design": (("design-system.json",), "design-system", "ds_build.py"),
    "review": (("revue-ux.json",), "mockup-to-html", "ux_review.py"),
}
# Ce qu'une pièce absente retire de l'export, et la commande qui la produit.
MISSING = {
    "options": "options.json absent : pas d'architecture.md (architecture-options : options_build.py options.json)",
    "tests": "recette.json absent : exigences sans critère d'acceptation (test-plan : test_build.py recette.json)",
    "design": "design-system.json absent : pas d'identité visuelle dans ux.md (design-system : ds_build.py design-system.json)",
    "pages": "pages/*.json absent : pas d'écrans dans ux.md (mockup-to-html : page_build.py pages/<page>.json)",
    "model": "modele.json absent : pas de modèle de données dans architecture.md (data-model : model_build.py modele.json)",
    "api": "api.json absent : pas d'interfaces dans architecture.md (api-contract : api_build.py api.json)",
    "extra": "specs.json absent : vision, utilisateurs, parcours et indicateurs de succès non renseignés "
             "(spec_pack.py --schema)",
}
# La même lacune, dite dans README.md sans nommer les pièces de la mission.
GAPS = {"options": "architecture non décidée : pas d'architecture.md",
        "tests": "pas de plan de recette : critères d'acceptation à écrire",
        "design": "pas de design system : identité visuelle à définir",
        "pages": "pas d'écrans décrits d'après des maquettes",
        "model": "pas de modèle de données", "api": "pas de contrat d'interface",
        "extra": "vision, utilisateurs, parcours et indicateurs de succès non renseignés"}
# Pièces de la mission jointes en annexe (copiées dans annexes/, liens recalés).
# Ni options.md ni l'ADR : le dossier ne porte que l'architecture retenue, pas les alternatives du cadrage.
COMPANIONS = ("exigences.md", "domaines.md", "domaines.carte.drawio.png", "modele.md", "modele.mmd", "modele.sql",
              "modele.png", "modele-1.png", "api.openapi.yaml", "api/api.openapi.yaml", "api.sequences.md",
              "recette.md", "dimensionnement.md", "registre.md", "schemas/*.png")
# Schémas propres à une option (options_build.py, cloud-architecture, pos_build.py) et pages du schéma des options.
OPTION_FILE = re.compile(r"^(?:pos-)?option-([a-z0-9]+)\b", re.I)
OPTIONS_PAGE = re.compile(r"^architectures(?:-(\d+))?\.drawio\.png$")
# Fichiers des maquettes HTML (page_build.py) qui accompagnent les pages, et ceux qui sont du code à reprendre.
MOCKUP_FILES = {".css", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".tsx", ".ts", ".vue", ".scss", ".html"}
CODE_FILES = {".tsx", ".ts", ".vue", ".scss"}
BOOTSTRAP = re.compile(r"^bootstrap-(\d[\w.]*)\.min\.css$")
UPDATED = re.compile(r"^updated: .*$", re.M)
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
STORY = re.compile(r"^#### S-\d+\.\d+ : ", re.M)


def read_json(path: Path, errors: list[str]):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{path.name} illisible : {error}")
        return None


def load_pieces(folder: Path, errors: list[str], warnings: list[str]) -> tuple[dict, list[str]]:
    """Livrables présents, chacun validé contre le schéma d'entrée du script qui l'a construit."""
    pieces, used = {}, []
    for key, (names, skill, script) in PIECES.items():
        path = next((data_file(folder, n) for n in names if data_file(folder, n).is_file()), None)
        data = read_json(path, errors) if path else None
        if data is None:
            continue
        schema = schema_of(skill, script)
        if schema is None:
            warnings.append(f"{path.name} non vérifié : " + absent(skill, script))
        invalid = check(data, schema) if schema else []
        if invalid:
            errors.extend(f"{path.name} : {e}" for e in invalid[:10])
            continue
        pieces[key] = data
        used.append(path.relative_to(folder).as_posix())
    decision = data_file(folder, "decision.json")
    if decision.is_file() and "options" in pieces:
        data, schema = read_json(decision, errors), schema_of("architecture-options", "options_build.py")
        invalid = check(data, schema["properties"]["decision"]) if data is not None and schema else []
        errors.extend(f"decision.json : {e}" for e in invalid)
        if data is not None and not invalid:
            pieces["decision"] = data
            used.append("decision.json")
    return pieces, used


def load_ai_cost(folder: Path, used: list[str], errors: list[str], warnings: list[str]) -> str:
    """Coût IA du développement estimé au chiffrage (<nom>.ia.json de solution-estimate) : section de livraison.md."""
    found = sorted(folder.glob("*.ia.json"))
    if not found:
        return ""
    path = next((p for p in found if p.name == "chiffrage.ia.json"), found[0])
    if len(found) > 1:
        warnings.append(f"plusieurs coûts IA du développement : {path.name} repris, les autres ignorés")
    ai = load_module("solution-estimate", "lib/estimate_ai.py")
    if ai is None:
        warnings.append(f"{path.name} non repris : " + absent("solution-estimate", "lib/estimate_ai.py"))
        return ""
    data = read_json(path, errors)
    invalid = check(data, ai.SUMMARY_SCHEMA, ai.SUMMARY_SCHEMA) if data is not None else []
    errors.extend(f"{path.name} : {e}" for e in invalid[:10])
    if data is None or invalid:
        return ""
    used.append(path.name)
    return "\n".join(ai.markdown(data)[2:])


def load_screens(folder: Path, pieces: dict, used: list[str], errors: list[str], warnings: list[str]) -> None:
    """Pages décrites d'après les maquettes (validées contre le schéma de page_build.py) et découpage en
    composants (decoupage.json, produit par ui_breakdown.py : lu tel quel)."""
    schema = schema_of("mockup-to-html", "page_build.py")
    paths = sorted((folder / "pages").glob("*.json"))
    if paths and schema is None:
        warnings.append("pages/*.json non vérifié : " + absent("mockup-to-html", "page_build.py"))
    for path in paths:
        data = read_json(path, errors)
        invalid = check(data, schema) if data is not None and schema else []
        errors.extend(f"pages/{path.name} : {e}" for e in invalid[:5])
        if data is not None and not invalid:
            pieces.setdefault("pages", []).append((path.stem, data))
            used.append(f"pages/{path.name}")
    breakdown = read_json(data_file(folder, "decoupage.json"), errors) if data_file(folder, "decoupage.json").is_file() else None
    if isinstance(breakdown, dict):
        pieces["breakdown"] = {**breakdown, "versions": pinned_versions(folder)}
        used.append("decoupage.json")


def check_option(pieces: dict, chosen: str | None, errors: list[str]) -> None:
    """L'option demandée ou décidée doit exister dans options.json."""
    options = pieces.get("options")
    if not options:
        return
    wanted = chosen or (pieces.get("decision") or options.get("decision") or options["recommendation"])["option"]
    known = [o["id"] for o in options["options"]]
    if wanted not in known:
        errors.append(f"option inconnue « {wanted} » (options de options.json : {', '.join(known)})")


def mission_of(folder: Path) -> tuple[Path | None, dict]:
    """Racine et mission.json du dossier, lus par mission-workspace s'il est installé."""
    workspace = load_module("mission-workspace", "lib/workspace.py")
    root = workspace.find(folder) if workspace else None
    mission = (workspace.load(root)[0] or {}) if root else {}
    flows = workspace.workflows(mission) if mission else []
    return root, {**mission, "workflows": flows}


def workflow_folder(folder: Path, root: Path | None, mission: dict) -> Path:
    """Dossier qui porte exigences.json : celui reçu, sinon celui d'un workflow de la mission."""
    candidates = [folder] + [root / flow["folder"] for flow in mission.get("workflows", [])]
    return next((c.resolve() for c in candidates if data_file(c, "exigences.json").is_file()), folder)


def place(paths: list[Path], base: Path, store: str, copies: list, root: Path | None = None) -> list[str]:
    """Liens vers la copie (à faire) de pièces de la mission dans `base/store`, jamais vers l'original :
    sous le même chemin que dans `root` si elles y sont (une page HTML retrouve ainsi sa feuille de style
    et ses images)."""
    names = [p.relative_to(root).as_posix() if root and p.is_relative_to(root) else p.name for p in paths]
    copies += [(p, base / store / name) for p, name in zip(paths, names)]
    return [f"{store}/{name}" for name in names]


def screen_links(folder: Path, pages: list, base: Path, copies: list) -> dict:
    """Pour chaque page : liens vers sa maquette d'origine, sa maquette HTML, l'image de son rendu et sa
    comparaison à la maquette, s'ils existent."""
    root, links = folder / "pages", {}
    for name, page in pages:
        found = [("maquette", (root / page["mockup"]).resolve())] if page.get("mockup") else []
        found += [("HTML", root / f"{name}.html"), ("rendu", root / f"{name}.render.png"),
                  ("comparaison", root / f"{name}.compare.png")]
        found = [(label, path) for label, path in found if path.is_file()]
        placed = place([path for _, path in found], base, "maquettes", copies, root)
        links[name] = [(label, target) for (label, _), target in zip(found, placed)]
    return links


def mockup_code(folder: Path, base: Path, copies: list) -> list[str]:
    """Maquettes HTML au complet : feuilles de style, images découpées (assets/), Bootstrap embarqué
    (vendor/) et code de la bibliothèque visée (TSX, Vue, Angular) suivent les pages HTML ; rend les
    liens vers les fichiers de code, cités dans ux.md."""
    root = folder / "pages"
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith(".")
             and p.suffix.lower() in MOCKUP_FILES]
    placed = place(files, base, "maquettes", copies, root)
    return [link for path, link in zip(files, placed) if path.suffix in CODE_FILES or ".component." in path.name]


def pinned_versions(folder: Path) -> dict:
    """Versions que les maquettes fixent déjà : le Bootstrap embarqué par page_build.py --target bootstrap."""
    found = [BOOTSTRAP.match(p.name) for p in sorted((folder / "pages" / "vendor").glob("bootstrap-*.min.css"))]
    return {"Bootstrap": found[0].group(1)} if found and found[0] else {}


def digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def document(front: dict, body: str, created: str) -> str:
    """Fichier complet : frontmatter court (valeurs en JSON, donc en YAML valide), sans trace de la mission
    ni de l'outil ; l'empreinte du corps est gardée dans l'état de l'export, côté mission."""
    meta = {**front, "created": created, "updated": date.today().isoformat()}
    lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in meta.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def previous(path: Path, known: str | None) -> tuple[str | None, str | None]:
    """Date de création d'un document déjà exporté, et son corps s'il a été modifié depuis le dernier export
    (empreinte `known` de l'état ; sans elle, le document ne vient pas de cet export)."""
    if not path.is_file():
        return None, None
    text = path.read_text(encoding="utf-8")
    head = FRONT.match(text)
    meta = dict(re.findall(r'^(\w+):\s*"?([^"\n]*)"?\s*$', head.group(1), re.M)) if head else {}
    body = text[head.end():].lstrip("\n") if head else text
    return meta.get("created"), None if known == digest(body) else body


def load_state(folder: Path, out: Path) -> dict:
    """Empreintes du dernier export vers ce dossier de spécifications."""
    try:
        state = json.loads((folder / STATE).read_text(encoding="utf-8"))
        return state.get("exports", {}).get(out.as_posix(), {}).get("files", {})
    except (OSError, ValueError, AttributeError):
        return {}


def save_state(folder: Path, out: Path, hashes: dict, used: list[str]) -> None:
    path = folder / STATE
    try:
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
    except ValueError:
        state = {}
    state.setdefault("exports", {})[out.as_posix()] = {"date": date.today().isoformat(), "pieces": used,
                                                       "files": hashes}
    path.write_text(json.dumps(state, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def retained(path: Path, model: dict) -> bool:
    """Un schéma d'option n'est joint que pour l'option retenue (page de architectures.drawio comprise)."""
    option = model["option"]
    if path.parent.name != "schemas":
        return True
    own, page = OPTION_FILE.match(path.name), OPTIONS_PAGE.match(path.name)
    if not option:
        return not own and not page
    if own:
        return own.group(1).lower() == option["id"].lower()
    if page:
        index = [o["id"] for o in model["all_options"]].index(option["id"]) + 1
        return int(page.group(1) or 1) == index
    return True


def render(model: dict, folder: Path, out: Path, copies: list, missing: list[str]) -> dict:
    """Documents à écrire : nom dans le dossier -> (frontmatter, corps). ux.md et architecture.md seulement si
    la mission en porte les sources ; README.md en dernier, il les liste."""
    found = [p for pattern in COMPANIONS for p in sorted(folder.glob(pattern)) if p.is_file() and retained(p, model)]
    annexes = place(found, out, "annexes", copies, folder)
    model["images"] = {"model": [a for a in annexes if re.match(r"annexes/modele(-1)?\.png$", a)],
                       "option": [a for a in annexes if a.startswith("annexes/schemas/") and a.endswith(".png")],
                       "domains": [a for a in annexes if a.endswith("domaines.carte.drawio.png")]}
    has_ux = bool(model["design"] or model["pages"] or model["review"] or model["breakdown"])
    model["docs"] = [name for name in pack_render.DOCS
                     if (name != "ux.md" or has_ux) and (name != "architecture.md" or model["option"])]
    docs = {"fonctionnel.md": pack_render.fonctionnel(model)}
    ux_lines = pack_ux.requirements(model)
    if has_ux:
        links = screen_links(folder, model["pages"], out, copies)
        docs["ux.md"] = pack_ux.ux(model, links, mockup_code(folder, out, copies))
    if model["option"]:
        docs["architecture.md"] = pack_render.architecture(model)
    docs["tests.md"] = pack_render.tests(model)
    docs["livraison.md"] = pack_render.livraison(model, ux_lines)
    docs = {"README.md": pack_render.readme(model, list(docs), annexes, missing), **docs}
    return {name: (pack_render.describe(model, name, front, body), body) for name, (front, body) in docs.items()}


def verify(docs: dict, model: dict, out: Path, bundle: list, roots: list[Path]) -> list[str]:
    """Relecture avant écriture : chaque exigence dans son document, chaque FR sa story et sa ligne de
    couverture, liens restés dans le dossier (documents et copies), aucun chemin de la machine."""
    errors = []
    body = lambda name: docs[name][1] if name in docs else ""  # noqa: E731
    errors += [f"fonctionnel.md : {r['ref']} ({r['id']}) absente" for r in model["frs"]
               if f"#### {r['ref']} : " not in body("fonctionnel.md")]
    if "architecture.md" in docs:
        errors += [f"architecture.md : {r['ref']} ({r['id']}) absente" for r in model["nfrs"]
                   if f"**{r['ref']} : " not in body("architecture.md")]
    stories = len(STORY.findall(body("livraison.md")))
    if stories != len(model["frs"]):
        errors.append(f"livraison.md : {stories} stories, {len(model['frs'])} attendues (une par exigence fonctionnelle)")
    errors += [f"tests.md : {r['ref']} absente de la couverture" for r in model["frs"] + model["nfrs"]
               if f"| {r['ref']} | {r['id']} |" not in body("tests.md")]
    coming = {target.resolve() for target, _ in bundle} | {(out / name).resolve() for name in docs}
    texts = [(name, document(front, text, "")) for name, (front, text) in docs.items()]
    texts += [(target.relative_to(out).as_posix(), data.decode("utf-8", errors="replace"))
              for target, data in bundle if target.suffix.lower() in pack_bundle.TEXT]
    for name, text in texts:
        if "```mermaid\n```" in text:
            errors.append(f"{name} : schéma Mermaid vide")
        errors += pack_bundle.escapes(name, text, out, coming)
        errors += pack_bundle.foreign(name, text, roots)
    return errors


def write(docs: dict, out: Path, bundle: list, force: bool, hashes: dict, warnings: list[str]) -> list[dict]:
    """Écrit les documents ; garde un document modifié depuis le dernier export, sauf --force. `hashes` (état
    de l'export) reçoit l'empreinte de chaque document écrit ou inchangé."""
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for name, (front, body) in docs.items():
        path = out / name
        created, edited = previous(path, hashes.get(name))
        if edited is not None and edited != body and not force:
            warnings.append(f"{name} modifié depuis le dernier export : gardé tel quel, --force pour l'écraser")
            files.append({"file": name, "status": "garde"})
            continue
        old = path.read_text(encoding="utf-8") if path.is_file() else ""
        text = document(front, body, created or date.today().isoformat())
        same = UPDATED.sub("", old) == UPDATED.sub("", text)
        if not same:
            path.write_text(text, encoding="utf-8", newline="\n")
        hashes[name] = digest(body)
        files.append({"file": name, "status": "inchange" if same else "ecrit"})
    for target, data in bundle:
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.is_file() or target.read_bytes() != data:
            target.write_bytes(data)
    return files


def counts(model: dict) -> dict:
    return {"features": len(model["features"]), "fr": len(model["frs"]), "nfr": len(model["nfrs"]),
            "stories": len(model["frs"]), "glossary": len(model["glossary"]),
            "decisions": len(pack_render.decisions(model)) if model["option"] else 0,
            "questions": len(pack_render.open_questions(model)),
            "stack": len(model["stack"]), "stack_without_version": sum(1 for _, version, _ in model["stack"] if not version),
            "screens": len(model["pages"]), "ux_findings": len(model["review"].get("findings", [])),
            "test_cases": len({c["id"] for r in model["frs"] + model["nfrs"] for c in r["tests"]}),
            "without_criteria": sum(1 for r in model["frs"] if not r["tests"] and not r.get("metric"))}


def missing_of(model: dict, pieces: dict, extra: dict) -> tuple[list[str], list[str]]:
    """Lacunes : pour le rapport (avec la commande qui les comble), et pour README.md (sans la mission)."""
    keys = [key for key in MISSING if (key == "extra" and not extra) or (key != "extra" and key not in pieces)]
    report, readme = [MISSING[key] for key in keys], [GAPS[key] for key in keys]
    loose = [name for name, version, _ in model["stack"] if not version]
    if loose:
        report.append(f"{len(loose)} framework(s) ou technologie(s) sans version dans architecture.md : champ stack "
                      "de specs.json (nom, version, rôle) ou version d'un composant d'options.json")
        readme.append(f"version à fixer : {', '.join(loose)}")
    return report, readme


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", nargs="?", type=Path, default=Path("."), help="dossier du workflow ou de la mission")
    parser.add_argument("--out", type=Path, help=f"dossier des spécifications (défaut : DOSSIER/{OUT})")
    parser.add_argument("--file", type=Path, help="description facultative (défaut : specs.json du dossier)")
    parser.add_argument("--option", help="option d'architecture à exporter (défaut : celle de la décision)")
    parser.add_argument("--force", action="store_true", help="écrase un document modifié depuis le dernier export")
    parser.add_argument("--check", type=Path, metavar="DOSSIER_DES_SPECS",
                        help="contrôle seul un dossier déjà écrit, où qu'il soit copié (liens internes, aucun chemin "
                             "de la machine), sans rien exporter")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.check or args.folder), "output": None, "option": None, "files": [],
              "counts": {}, "missing": [], "next": "", "errors": [], "warnings": []}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    errors, warnings = report["errors"], report["warnings"]
    if args.check:
        if not args.check.is_dir():
            errors.append(f"{args.check} : dossier introuvable")
            return done(1)
        read, found = pack_bundle.audit(args.check.resolve())
        errors += found
        report.update(output=str(args.check.resolve()), counts={"files": read},
                      next="" if found else "dossier autonome : il peut être copié ou transmis seul")
        return done(1 if found else 0)
    root, mission = mission_of(args.folder.resolve())
    folder = workflow_folder(args.folder.resolve(), root, mission)
    if not data_file(folder, "exigences.json").is_file():
        errors.append(f"exigences.json introuvable dans {args.folder} : menez d'abord l'étape des exigences "
                      "(requirements-catalog : req_build.py exigences.json)")
        return done(1)
    spec_path = args.file or data_file(folder, "specs.json")
    extra = (read_json(spec_path, errors) if spec_path.is_file() else None) or {}
    if args.file and not spec_path.is_file():
        errors.append(f"{args.file} introuvable")
    errors += validate(extra, __file__)
    pieces, used = load_pieces(folder, errors, warnings)
    load_screens(folder, pieces, used, errors, warnings)
    check_option(pieces, args.option, errors)
    if errors:
        return done(1)
    name = mission.get("name") or pieces["requirements"].get("title") or folder.name
    model, notes = pack_model.build(pieces, extra, name, args.option)
    builder = load_module("data-model", "model_build.py") if pieces.get("model") else None
    model["er"] = builder.mermaid(pieces["model"]) if builder else ""
    model["all_options"] = (pieces.get("options") or {}).get("options", [])
    warnings += notes
    model["ai_cost"] = load_ai_cost(folder, used, errors, warnings)
    if errors:
        return done(1)
    out = (args.out or folder / OUT).resolve()
    copies: list = []
    report["missing"], gaps = missing_of(model, pieces, extra)
    docs = render(model, folder, out, copies, gaps)
    bundle, notes = pack_bundle.pack(copies, out, folder)
    warnings += notes
    errors += verify(docs, model, out, bundle, [folder, out, root or folder])
    if errors:
        return done(1)
    hashes = load_state(folder, out)
    report["files"] = write(docs, out, bundle, args.force, hashes, warnings)
    save_state(folder, out, hashes, used)
    report["output"] = str(out)
    report["option"] = (model["option"] or {}).get("id")
    report["counts"] = {**counts(model), "copies": len(bundle)}
    report["next"] = ("Donnez README.md et le document de l'aspect traité (ou tout le dossier) à l'outil de "
                      "développement IA, quel qu'il soit ; avant de transmettre une copie : spec_pack.py --check DOSSIER")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
