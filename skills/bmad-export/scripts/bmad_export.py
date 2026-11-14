# /// script
# requires-python = ">=3.10"
# ///
"""Exporte les livrables validés d'une mission vers les artefacts de planification de BMAD Method (v6).

Le script, et non le modèle, lit le dossier du workflow (exigences.json obligatoire ; options.json,
decision.json, domaines.json, modele.json, api.json, recette.json, registre.json s'ils existent), valide
chaque pièce contre le schéma du skill qui l'a produite, puis écrit dans le dossier de planification de
BMAD (`_bmad-output/planning-artifacts`, ou celui de la configuration `_bmad/` du projet cible) :

- `brief.md` : product brief (contexte, solution retenue, utilisateurs, périmètre) ;
- `prd.md` : PRD au gabarit BMAD, exigences fonctionnelles FR-n regroupées par fonctionnalité, exigences
  non fonctionnelles NFR-n, glossaire, périmètre, questions ouvertes, hypothèses ;
- `architecture.md` : colonne d'architecture (décisions AD-n, flux en Mermaid, entités, interfaces) ;
- `epics.md` : ébauche des epics et stories, lisible par `sprint_plan.py` de BMAD ;
- `addendum.md` : correspondance des identifiants, options écartées, pièces de la mission ;
- `ux-designs/ux-<nom>/DESIGN.md` et `EXPERIENCE.md` : les deux documents UX de BMAD, quand la mission a
  un design system (design-system.json), des pages décrites d'après les maquettes (pages/*.json), une
  revue UX (revue-ux.json) ou un découpage en composants (decoupage.json) ; maquettes d'origine,
  maquettes HTML (pages, styles, images, code de la bibliothèque visée) et rendus liés, ou copiés dans
  mockups/ quand l'export sort du dossier de la mission.

La pile technique d'architecture.md vient de bmad.json (`stack`, avec les versions), de la bibliothèque
d'interface visée par le découpage des maquettes et de la technologie des composants de l'option, avec
leur version quand options.json la donne (champ version d'un composant).

Le modèle n'écrit, au besoin, que `bmad.json` : ce que la mission ne dit pas (vision, utilisateurs,
parcours, hors-périmètre, indicateurs de succès, regroupement en fonctionnalités).

Avant d'écrire, le script relit ce qu'il a produit : chaque exigence retenue a son identifiant BMAD dans
le PRD, chaque FR sa story, les titres d'epics et de stories passent les expressions de BMAD, chaque lien
local existe. Un fichier modifié depuis le dernier export (par vous ou par un agent BMAD) n'est pas
écrasé sans --force.

    uv run scripts/bmad_export.py [DOSSIER] [--out RACINE] [--file bmad.json] [--option ID]
                                  [--no-epics] [--force] | --schema
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
import unicodedata
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import bmad_model  # noqa: E402
import bmad_render  # noqa: E402
import bmad_ux  # noqa: E402
from skill_paths import absent, load_module, schema_of  # noqa: E402
from spec_schema import check, print_schema, schema_option, validate  # noqa: E402

LAYOUT = "bmad-method-6"
MARK = "myskills bmad-export"
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
    "tests": "recette.json absent : stories sans critère d'acceptation (test-plan : test_build.py recette.json)",
    "design": "design-system.json absent : pas de DESIGN.md (design-system : ds_build.py design-system.json)",
    "pages": "pages/*.json absent : pas d'écrans dans EXPERIENCE.md (mockup-to-html : page_build.py pages/<page>.json)",
    "extra": "bmad.json absent : vision, utilisateurs, parcours et indicateurs de succès non renseignés "
             "(bmad_export.py --schema)",
}
# Pièces de la mission citées en annexe de l'addendum (liées, ou copiées si l'export sort du dossier).
COMPANIONS = ("exigences.md", "options.md", "adr-architecture.md", "domaines.md", "modele.md", "modele.sql",
              "api.openapi.yaml", "api/api.openapi.yaml", "api.sequences.md", "recette.md", "dimensionnement.md",
              "registre.md", "schemas/*.png")
# Fichiers des maquettes HTML (page_build.py) qui accompagnent les pages, et ceux qui sont du code à reprendre.
MOCKUP_FILES = {".css", ".png", ".svg", ".jpg", ".jpeg", ".webp", ".tsx", ".ts", ".vue", ".scss", ".html"}
CODE_FILES = {".tsx", ".ts", ".vue", ".scss"}
BOOTSTRAP = re.compile(r"^bootstrap-(\d[\w.]*)\.min\.css$")
SETTING = re.compile(r"^\s*planning_artifacts\s*[:=]\s*[\"']?([^\"'\n#]+)", re.M)
FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.S)
LINK = re.compile(r"\]\(([^)\s]+)\)")
# Mêmes expressions que sprint_plan.py de BMAD (bmad-sprint-planning) pour les titres d'epics et de stories.
EPIC = re.compile(r"^#{1,3}\s*Epic\s+(\d+)\s*:?\s*(.*?)\s*#*\s*$", re.I | re.M)
STORY = re.compile(r"^#{2,4}\s*Story\s+(\d+)\.(\d+[a-z]?)\s*:?\s*(.*?)\s*#*\s*$", re.I | re.M)


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
        path = next((folder / name for name in names if (folder / name).is_file()), None)
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
    decision = folder / "decision.json"
    if decision.is_file() and "options" in pieces:
        data, schema = read_json(decision, errors), schema_of("architecture-options", "options_build.py")
        invalid = check(data, schema["properties"]["decision"]) if data is not None and schema else []
        errors.extend(f"decision.json : {e}" for e in invalid)
        if data is not None and not invalid:
            pieces["decision"] = data
            used.append("decision.json")
    return pieces, used


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
    breakdown = read_json(folder / "decoupage.json", errors) if (folder / "decoupage.json").is_file() else None
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
    return next((c.resolve() for c in candidates if (c / "exigences.json").is_file()), folder)


def planning_dir(root: Path) -> Path:
    """Dossier de planification du projet BMAD : celui de sa configuration, sinon le défaut de BMAD."""
    for name in ("_bmad/custom/config.toml", "_bmad/config.toml", "_bmad/bmm/config.yaml"):
        path = root / name
        found = SETTING.search(path.read_text(encoding="utf-8")) if path.is_file() else None
        if found:
            value = found.group(1).strip().replace("{project-root}/", "").replace("{project-root}", "")
            return (root / value).resolve()
    return (root / "_bmad-output" / "planning-artifacts").resolve()


def place(paths: list[Path], folder: Path, base: Path, store: str, copies: list, root: Path | None = None) -> list[str]:
    """Liens vers des pièces de la mission, vus du dossier `base` : relatifs si l'export reste dans le
    dossier de la mission, sinon vers leur copie (à faire) dans `base/store`, sous le même chemin que
    dans `root` si elles y sont (une page HTML retrouve ainsi sa feuille de style et ses images)."""
    if base.is_relative_to(folder):
        return [Path(os.path.relpath(p, base)).as_posix() for p in paths]
    names = [p.relative_to(root).as_posix() if root and p.is_relative_to(root) else p.name for p in paths]
    copies += [(p, base / store / name) for p, name in zip(paths, names)]
    return [f"{store}/{name}" for name in names]


def slug(name: str) -> str:
    plain = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-") or "projet"


def screen_links(folder: Path, pages: list, base: Path, copies: list) -> dict:
    """Pour chaque page : liens vers sa maquette d'origine, sa maquette HTML, l'image de son rendu et sa
    comparaison à la maquette, s'ils existent."""
    root, links = folder / "pages", {}
    for name, page in pages:
        found = [("maquette", (root / page["mockup"]).resolve())] if page.get("mockup") else []
        found += [("HTML", root / f"{name}.html"), ("rendu", root / f"{name}.render.png"),
                  ("comparaison", root / f"{name}.compare.png")]
        found = [(label, path) for label, path in found if path.is_file()]
        placed = place([path for _, path in found], folder, base, "mockups", copies, root)
        links[name] = [(label, target) for (label, _), target in zip(found, placed)]
    return links


def mockup_code(folder: Path, base: Path, copies: list) -> list[str]:
    """Maquettes HTML au complet : feuilles de style, images découpées (assets/), Bootstrap embarqué
    (vendor/) et code de la bibliothèque visée (TSX, Vue, Angular) suivent les pages HTML ; rend les
    liens vers les fichiers de code, cités dans EXPERIENCE.md."""
    root = folder / "pages"
    files = [p for p in sorted(root.rglob("*")) if p.is_file() and not p.name.startswith(".")
             and p.suffix.lower() in MOCKUP_FILES]
    placed = place(files, folder, base, "mockups", copies, root)
    return [link for path, link in zip(files, placed) if path.suffix in CODE_FILES or ".component." in path.name]


def pinned_versions(folder: Path) -> dict:
    """Versions que les maquettes fixent déjà : le Bootstrap embarqué par page_build.py --target bootstrap."""
    found = [BOOTSTRAP.match(p.name) for p in sorted((folder / "pages" / "vendor").glob("bootstrap-*.min.css"))]
    return {"Bootstrap": found[0].group(1)} if found and found[0] else {}


def digest(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def document(front: dict, body: str, created: str) -> str:
    """Fichier complet : frontmatter (valeurs en JSON, donc en YAML valide), marque et empreinte du corps."""
    meta = {**front, "created": created, "updated": date.today().isoformat(),
            "generated_by": MARK, "export_hash": digest(body)}
    lines = [f"{key}: {json.dumps(value, ensure_ascii=False)}" for key, value in meta.items()]
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


def previous(path: Path) -> tuple[str | None, bool]:
    """Date de création d'un fichier déjà exporté, et s'il a été modifié depuis (empreinte différente,
    ou fichier qui ne vient pas de cet export)."""
    if not path.is_file():
        return None, False
    text = path.read_text(encoding="utf-8")
    head = FRONT.match(text)
    meta = dict(re.findall(r'^(\w+):\s*"?([^"\n]*)"?\s*$', head.group(1), re.M)) if head else {}
    body = text[head.end():].lstrip("\n") if head else text
    return meta.get("created"), meta.get("generated_by") != MARK or meta.get("export_hash") != digest(body)


def render_ux(model: dict, folder: Path, planning: Path, copies: list) -> dict:
    """Documents UX de BMAD, dans ux-designs/ux-<nom>/ : DESIGN.md s'il y a un design system,
    EXPERIENCE.md s'il y a des pages, une revue UX ou un découpage."""
    where = f"ux-designs/ux-{slug(model['name'])}"
    docs = {f"{where}/DESIGN.md": bmad_ux.design(model)} if model["design"] else {}
    if model["pages"] or model["review"] or model["breakdown"]:
        links = screen_links(folder, model["pages"], planning / where, copies)
        code = mockup_code(folder, planning / where, copies)
        docs[f"{where}/EXPERIENCE.md"] = bmad_ux.experience(model, links, code, "../../prd.md")
    return docs


def render(model: dict, used: list[str], linked: list[str], ux: dict, epics: bool) -> dict:
    """Artefacts à écrire : chemin dans le dossier de planification -> (frontmatter, corps)."""
    docs = {"brief.md": bmad_render.brief(model), "prd.md": bmad_render.prd(model, used)}
    inputs = ["prd.md"]
    if model["option"]:
        docs["architecture.md"] = bmad_render.architecture(model, ["addendum.md"] + linked)
        inputs.append("architecture.md")
    if epics:
        docs["epics.md"] = bmad_render.epics(model, inputs + list(ux), bmad_ux.requirements(model))
    docs["addendum.md"] = bmad_render.addendum(model, linked + list(ux))
    return {**docs, **ux}


def verify(docs: dict, model: dict, planning: Path, copies: list) -> list[str]:
    """Relecture des artefacts avant écriture : identifiants, stories, titres reconnus par BMAD, liens."""
    errors = []
    prd = docs["prd.md"][1]
    errors += [f"prd.md : {r['id']} ({r['bmad']}) absente" for r in model["frs"] + model["nfrs"]
               if f"{r['bmad']}: " not in prd or r["id"] not in prd]
    if "epics.md" in docs:
        text = docs["epics.md"][1]
        if len(EPIC.findall(text)) != len(model["features"]) or len(STORY.findall(text)) != len(model["frs"]):
            errors.append(f"epics.md : {len(EPIC.findall(text))} epics et {len(STORY.findall(text))} stories "
                          f"reconnues, {len(model['features'])} et {len(model['frs'])} attendues")
    coming = {target.resolve() for _, target in copies} | {(planning / name).resolve() for name in docs}
    for name, (_, body) in docs.items():
        if "```mermaid\n```" in body:
            errors.append(f"{name} : schéma Mermaid vide")
        for target in LINK.findall(body):
            path = ((planning / name).parent / target).resolve()
            if not re.match(r"^([a-z]+:|#)", target) and not path.exists() and path not in coming:
                errors.append(f"{name} : lien introuvable {target}")
    return errors


def write(docs: dict, planning: Path, copies: list, force: bool, warnings: list[str]) -> list[dict]:
    """Écrit les artefacts ; garde un fichier modifié depuis le dernier export, sauf --force."""
    planning.mkdir(parents=True, exist_ok=True)
    files = []
    for name, (front, body) in docs.items():
        path = planning / name
        path.parent.mkdir(parents=True, exist_ok=True)
        created, changed = previous(path)
        if changed and not force:
            warnings.append(f"{name} modifié depuis le dernier export (ou écrit par BMAD) : gardé tel quel, "
                            "--force pour l'écraser")
            files.append({"file": name, "status": "garde"})
            continue
        text = document(front, body, created or date.today().isoformat())
        same = path.is_file() and FRONT.sub("", path.read_text(encoding="utf-8"), count=1).lstrip("\n") == body
        if not same:
            path.write_text(text, encoding="utf-8", newline="\n")
        files.append({"file": name, "status": "inchange" if same else "ecrit"})
    for source, target in copies:
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    return files


def counts(model: dict) -> dict:
    return {"features": len(model["features"]), "fr": len(model["frs"]), "nfr": len(model["nfrs"]),
            "stories": len(model["frs"]), "glossary": len(model["glossary"]),
            "decisions": len(bmad_render.decisions(model)) if model["option"] else 0,
            "questions": len(bmad_render.open_questions(model)),
            "stack": len(model["stack"]), "stack_without_version": sum(1 for _, version, _ in model["stack"] if not version),
            "screens": len(model["pages"]), "ux_findings": len(model["review"].get("findings", [])),
            "without_criteria": sum(1 for r in model["frs"] if not r["tests"] and not r.get("metric"))}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folder", nargs="?", type=Path, default=Path("."), help="dossier du workflow ou de la mission")
    parser.add_argument("--out", type=Path, help="racine du projet BMAD cible (défaut : le dossier)")
    parser.add_argument("--file", type=Path, help="description facultative (défaut : bmad.json du dossier)")
    parser.add_argument("--option", help="option d'architecture à exporter (défaut : celle de la décision)")
    parser.add_argument("--no-epics", action="store_true", help="n'écrit pas l'ébauche epics.md")
    parser.add_argument("--force", action="store_true", help="écrase un artefact modifié depuis le dernier export")
    schema_option(parser)
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    root, mission = mission_of(args.folder.resolve())
    folder = workflow_folder(args.folder.resolve(), root, mission)
    report = {"input": str(args.folder), "layout": LAYOUT, "output": None, "option": None, "files": [],
              "counts": {}, "missing": [], "next": "", "errors": [], "warnings": []}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    errors, warnings = report["errors"], report["warnings"]
    if not (folder / "exigences.json").is_file():
        errors.append(f"exigences.json introuvable dans {args.folder} : menez d'abord l'étape des exigences "
                      "(requirements-catalog : req_build.py exigences.json)")
        return done(1)
    spec_path = args.file or folder / "bmad.json"
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
    model, notes = bmad_model.build(pieces, extra, name, args.option)
    warnings += notes
    planning = planning_dir((args.out or folder).resolve())
    copies: list = []
    found = [p for pattern in COMPANIONS for p in sorted(folder.glob(pattern)) if p.is_file()]
    linked = place(found, folder, planning, "sources", copies)
    docs = render(model, used, linked, render_ux(model, folder, planning, copies), not args.no_epics)
    errors += verify(docs, model, planning, copies)
    if errors:
        return done(1)
    report["files"] = write(docs, planning, copies, args.force, warnings)
    report["output"] = str(planning)
    report["option"] = (model["option"] or {}).get("id")
    report["counts"] = counts(model)
    report["missing"] = [text for key, text in MISSING.items()
                         if (key == "extra" and not extra) or (key != "extra" and key not in pieces)]
    loose = report["counts"]["stack_without_version"]
    if loose:
        report["missing"].append(f"{loose} framework(s) ou technologie(s) sans version dans architecture.md : "
                                 "champ stack de bmad.json (nom, version, rôle)")
    report["next"] = ("BMAD installé dans le projet cible (npx bmad-method install) : bmad-prd pour valider le PRD, "
                      "bmad-ux pour reprendre DESIGN.md et EXPERIENCE.md, bmad-create-epics-and-stories pour l'ébauche d'epics, puis "
                      "bmad-sprint-planning et bmad-build")
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
