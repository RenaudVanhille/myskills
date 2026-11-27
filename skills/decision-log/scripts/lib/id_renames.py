"""Renumérotation par catégorie des exigences non fonctionnelles d'un workflow ouvert avant les préfixes de
catégorie (ENF-004 -> SECU-01), à la mise à niveau (`journal.py upgrade`).

La correspondance vient du catalogue d'exigences du workflow, ou de celui d'un autre workflow de la mission
lu par une entrée `../` (`text_tools.category_renames`) : un identifiant cité par les documents sources est leur
numérotation et ne change pas. Elle s'applique, en mots entiers, aux fichiers texte du dossier du workflow
(hors sources, .historique/, .git/ et dossiers d'autres workflows), à l'état (`workflow.json` : entrées, refs)
et au dossier du projet dans le vault (notes renommées, liens suivis, « Mes notes » gardées). Les empreintes
des fichiers réécrits sont recalculées : la reprise d'étapes ne les voit pas comme modifiés. Le catalogue garde
la correspondance dans son champ `renamed`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from lib.text_tools import category_renames, data_file, from_data, id_pattern, rename_ids, unlink_notes

TEXT = (".md", ".json", ".csv", ".mmd", ".yaml", ".yml", ".txt", ".canvas", ".base", ".html")
SKIP_DIRS = {".historique", ".git", ".myskills-tmp", ".obsidian", "node_modules", ".trash"}


def text_digest(text: str, suffix: str) -> str:
    """Empreinte d'un contenu comme journal.digest l'aurait calculée pour un fichier de ce suffixe."""
    if suffix.lower() == ".md":
        text = unlink_notes(text)
    return hashlib.sha256(text.encode("utf-8", errors="surrogateescape")).hexdigest()


def catalog_path(folder: Path, state: dict, names: str | None) -> Path | None:
    """Catalogue d'exigences du workflow (memory.requirements de la définition), sinon celui qu'une étape lit
    par une entrée `../` (workflow parent ou voisin de la mission)."""
    if not names:
        return None
    own = data_file(folder, names)
    if own.is_file():
        return own
    base = Path(names).name
    for stage in state.get("stages", []):
        for rel in stage.get("external") or {}:
            if Path(rel).name == base and (folder / rel).is_file():
                return folder / rel
    return None


def mapping_of(catalog: Path) -> tuple[dict[str, str], Path | None]:
    """Correspondance ancien -> nouvel identifiant du catalogue (vide s'il est illisible) et dossier de ses
    documents sources, qui ne changent pas."""
    try:
        spec = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}, None
    if not isinstance(spec, dict) or not isinstance(spec.get("requirements"), list):
        return {}, None
    sources = from_data(catalog.parent, spec.get("sources", "sources"))
    text = "\n".join(p.read_text(encoding="utf-8", errors="replace") for p in sorted(sources.glob("**/*.md"))) \
        if sources.is_dir() else ""
    return category_renames(spec, text), sources if sources.is_dir() else None


def text_files(root: Path, skip: set[Path], own_state: bool) -> list[Path]:
    """Fichiers texte sous root, hors dossiers ignorés, dossiers `skip` et dossiers d'un autre workflow."""
    found = []
    for path in sorted(root.iterdir()):
        if path.is_dir():
            if path.name in SKIP_DIRS or path.resolve() in skip or (path / "workflow.json").is_file():
                continue
            found += text_files(path, skip, False)
        elif path.suffix.lower() in TEXT and not (own_state and path.name == "workflow.json"):
            found.append(path)
    return found


def rewrite_catalog(path: Path, mapping: dict[str, str], write: bool) -> bool:
    """Catalogue renuméroté, la correspondance complète gardée dans `renamed` (jamais elle-même renommée)."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    recorded = spec.pop("renamed", None) or {}
    body = json.dumps(spec, ensure_ascii=False, indent=1)
    renamed = rename_ids(body, mapping)
    if renamed == body and recorded == mapping:
        return False
    if write:
        spec = json.loads(renamed)
        spec["renamed"] = {**recorded, **mapping}
        path.write_text(json.dumps(spec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return True


def rewrite(path: Path, mapping: dict[str, str], write: bool) -> bool:
    with open(path, encoding="utf-8", errors="surrogateescape", newline="") as handle:
        text = handle.read()
    renamed = rename_ids(text, mapping)
    if renamed == text:
        return False
    if write:
        with open(path, "w", encoding="utf-8", errors="surrogateescape", newline="") as handle:
            handle.write(renamed)
    return True


def apply(folder: Path, state: dict, mapping: dict[str, str], catalog: Path | None, sources: Path | None,
          vault_base: Path | None, digest, items_of, write: bool) -> tuple[dict, int]:
    """Renomme partout (write faux : compte seulement). Rend l'état renommé et le nombre de fichiers touchés."""
    if not mapping:
        return state, 0
    pattern = id_pattern(mapping)
    skip = {p.resolve() for p in (sources, vault_base) if p}
    own_catalog = catalog if catalog and folder.resolve() in catalog.resolve().parents else None
    before: dict[Path, str] = {}
    touched = 0
    for path in text_files(folder, skip, True):
        if own_catalog and path.resolve() == own_catalog.resolve():
            continue
        old = digest(path)
        if rewrite(path, mapping, write):
            before[path.resolve()] = old
            touched += 1
    if own_catalog:
        old = digest(own_catalog)
        if rewrite_catalog(own_catalog, mapping, write):
            before[own_catalog.resolve()] = old
            touched += 1
    if vault_base and vault_base.is_dir():
        for path in text_files(vault_base, set(), False):
            touched += rewrite(path, mapping, write)
            new = mapping.get(path.stem)
            if new and pattern.fullmatch(path.stem) and not (path.parent / f"{new}{path.suffix}").exists():
                touched += 1
                if write:
                    path.rename(path.parent / f"{new}{path.suffix}")
    dumped = json.dumps(state, ensure_ascii=False)
    if pattern.search(dumped):
        state = json.loads(rename_ids(dumped, mapping))
        touched += 1
    if not write:
        return state, touched
    # Empreintes : un fichier inchangé avant le renommage reste inchangé pour le suivi des étapes.
    swap = {old: digest(path) for path, old in before.items()}
    reverse = {new: old for old, new in mapping.items()}
    for stage in state["stages"]:
        for rel, sha in list((stage.get("external") or {}).items()):  # renommé par la mise à niveau d'un autre workflow
            path = folder / rel
            if path.is_file() and digest(path) != sha:
                text = path.read_bytes().decode("utf-8", errors="surrogateescape")
                if text_digest(rename_ids(text, reverse), path.suffix) == sha:
                    swap[sha] = digest(path)

    def fresh(value):
        if isinstance(value, dict):
            return {k: fresh(v) for k, v in value.items()}
        if isinstance(value, list):
            return [fresh(v) for v in value]
        return swap.get(value, value) if isinstance(value, str) else value
    state["stages"] = fresh(state["stages"])
    for stage in state["stages"]:
        for rel in stage.get("items") or {}:
            if (folder / rel).resolve() in before and (found := items_of(folder / rel)):
                stage["items"][rel] = found
    return state, touched
