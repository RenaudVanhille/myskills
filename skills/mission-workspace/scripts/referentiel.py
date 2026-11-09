# /// script
# requires-python = ">=3.10"
# ///
"""Référentiel du client partagé entre ses missions : applications du SI, glossaire, ADR.

Le référentiel est un dossier de notes typées (un vault Obsidian ou un de ses
dossiers), hors de la mission, déclaré dans `mission.json` (`referentiel.path`)
ou donné par `--ref`. Un référentiel par client : rien d'un client ne va chez
un autre.

- `pull` copie ses notes des types partagés dans le vault de la mission, sous
  `Référentiel/` (marque `genere: referentiel`, source gardée) : liens,
  recherche et `vault_query.py` les trouvent. Une note retirée du référentiel
  est retirée de la mission au pull suivant.
- `push` verse dans le référentiel les notes de la mission de ces types
  (exigences et workflows exclus) : titre, propriétés et texte d'introduction,
  liens vers des notes non partagées réduits à leur libellé. Une note déjà
  présente (même type et même id, titre ou alias) n'est jamais écrasée : ses
  alias sont complétés, une différence de texte est signalée en conflit. Sans
  `--apply`, rien n'est écrit : le rapport donne ce qui serait versé, à faire
  relire avant de partager.

Chaque note est vérifiée contre l'ontologie avant l'écriture, sous le verrou
du vault.

    uv run scripts/referentiel.py pull [DOSSIER] [--ref REFERENTIEL]
    uv run scripts/referentiel.py push [DOSSIER] [--ref REFERENTIEL] [--types application,terme] [--apply]
"""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import workspace  # noqa: E402
from skill_paths import require_module  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")

SHARED = ("application", "terme", "adr")
MARK = "referentiel"
FOLDER = "Référentiel"
SKIP_DIRS = {".obsidian", ".trash", ".git", ".myskills-tmp", "node_modules"}
LABELED = re.compile(r"(?<!!)\[\[([^\[\]|#]+)(?:#[^\[\]|]*)?(?:\|([^\[\]]*))?\]\]")


def norm(text) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).lower().split())


def typed_notes(root: Path, kinds, skip: str | None = None) -> dict[str, tuple[dict, str]]:
    """Notes des types kinds sous root : chemin relatif sans .md -> (frontmatter, corps)."""
    found = {}
    for path in sorted(root.rglob("*.md")) if root.is_dir() else []:
        rel = path.relative_to(root)
        if any(part in SKIP_DIRS for part in rel.parts[:-1]) or (skip and rel.parts[0] == skip):
            continue
        data, body, _ = vault_ontology.parse(path.read_text(encoding="utf-8", errors="replace"))
        if data and data.get("type") in kinds:
            found[rel.with_suffix("").as_posix()] = (data, body)
    return found


def keys_of(rel: str, data: dict, body: str) -> set[str]:
    """Clés d'identité d'une note : type + id, titre, nom et alias, sans casse ni accents."""
    names = [data.get("id"), vault_ontology.heading(body), rel.rsplit("/", 1)[-1], *(data.get("aliases") or [])]
    return {f"{data['type']}:{norm(n)}" for n in names if n}


def intro(body: str, keep) -> str:
    """Titre et texte d'introduction (avant la première section ##), sans sections générées ; un wikilink
    vers une note que keep(cible) refuse est réduit à son libellé."""
    text = body.split(vault_ontology.HUB, 1)[0]
    lines = []
    for line in text.splitlines():
        if line.startswith("## "):
            break
        lines.append(line)
    out = "\n".join(lines).strip()

    def shorten(match):
        target, label = match.group(1).strip(), match.group(2)
        mapped = keep(target)
        if mapped:
            return f"[[{mapped}|{label}]]" if label else f"[[{mapped}]]"
        return label or target.rsplit("/", 1)[-1]
    out = LABELED.sub(shorten, out)
    # Ligne réduite à un libellé de contexte (« Workflow : Portail ») : retirée.
    return "\n".join(l for l in out.splitlines() if not re.fullmatch(r"\s*Workflow\s*:.*", l)).strip()


def clean_meta(onto: dict, data: dict, keep, source: str) -> dict:
    """Frontmatter partagé : sans marque d'origine ni tags de facette périmés, relations vers des notes
    partagées seulement (chemins réécrits par keep), marque referentiel et source."""
    props = {k: v for k, v in data.items() if k not in ("type", "genere", "source", "tags", "ontologie")
             and k not in onto["relations"]}
    relations = {}
    for name in onto["relations"]:
        kept = [t for t in (keep(t) for t in vault_ontology.targets(data.get(name))) if t]
        if kept:
            relations[name] = kept if onto["relations"][name].get("many") else kept[0]
    extra = [t for t in (data.get("tags") or []) if isinstance(t, str) and "/" not in t]
    meta = vault_ontology.meta(onto, data["type"], props, relations, extra, genere=MARK)
    meta["source"] = source
    return meta


def note_text(meta: dict, body: str) -> str:
    return vault_ontology.render(meta) + "\n" + body.rstrip() + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["pull", "push"])
    parser.add_argument("folder", nargs="?", type=Path, default=Path("."), help="dossier de la mission")
    parser.add_argument("--ref", type=Path, help="dossier du référentiel (défaut : referentiel.path de mission.json)")
    parser.add_argument("--types", help=f"types partagés, séparés par des virgules (défaut : {', '.join(SHARED)})")
    parser.add_argument("--apply", action="store_true", help="push : écrire dans le référentiel (sinon à blanc)")
    args = parser.parse_args()
    errors: list[str] = []
    warnings: list[str] = []
    report = {"command": args.command, "referentiel": "", "vault": "", "notes": 0, "added": [], "updated": [],
              "conflicts": [], "removed": 0, "applied": args.command == "pull" or args.apply,
              "errors": errors, "warnings": warnings}

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    root = workspace.find(args.folder)
    if not root:
        errors.append(f"pas de mission ({workspace.MISSION}) dans {args.folder} ni au-dessus : mission.py init")
        return done(1)
    mission, invalid = workspace.load(root)
    if invalid:
        errors += invalid
        return done(1)
    declared = mission.get("referentiel") or {}
    ref = args.ref or (Path(declared["path"]) if declared.get("path") else None)
    if ref is None:
        errors.append("aucun référentiel : referentiel.path dans mission.json, ou --ref")
        return done(1)
    ref = ref if ref.is_absolute() else (root / ref if not args.ref else ref)
    vault = workspace.path_of(root, mission, "vault")
    report["referentiel"], report["vault"] = str(ref), str(vault)
    onto = vault_ontology.load()
    kinds = [k.strip() for k in (args.types.split(",") if args.types else declared.get("types") or SHARED)
             if k.strip()]
    unknown = [k for k in kinds if k not in SHARED]
    if unknown:
        errors.append(f"--types : {', '.join(unknown)} non partageable(s) ({', '.join(SHARED)})")
    if not ref.is_dir():
        errors.append(f"référentiel introuvable : {ref}")
    if not vault.is_dir():
        errors.append(f"vault de la mission introuvable : {vault}")
    if errors:
        return done(1)

    try:
        if args.command == "pull":
            with vault_ontology.vault_lock(vault):
                return done(pull(onto, ref, vault, kinds, report))
        with vault_ontology.vault_lock(ref):
            return done(push(onto, mission, ref, vault, kinds, args.apply, report))
    except TimeoutError as error:
        errors.append(str(error))
        return done(1)


def pull(onto: dict, ref: Path, vault: Path, kinds, report: dict) -> int:
    """Copie des notes du référentiel dans <vault>/Référentiel/, chemins et liens réécrits."""
    source = typed_notes(ref, kinds)
    target = {rel: f"{FOLDER}/{rel}" for rel in source}

    def keep(path: str) -> str | None:
        return target.get(path) or next((t for r, t in target.items() if r.rsplit("/", 1)[-1] == path), None)
    texts = {}
    for rel, (data, body) in source.items():
        meta = clean_meta(onto, data, keep, f"{ref.name}/{rel}.md")
        found = vault_ontology.check_meta(onto, meta, generated=True)[0]
        if found:
            report["warnings"].append(f"{rel} : hors ontologie, non copiée : {found[0]}")
            continue
        texts[target[rel]] = note_text(meta, LABELED.sub(lambda m: (
            f"[[{keep(m.group(1).strip())}|{m.group(2)}]]" if keep(m.group(1).strip()) and m.group(2) else
            f"[[{keep(m.group(1).strip())}]]" if keep(m.group(1).strip()) else
            (m.group(2) or m.group(1).rsplit("/", 1)[-1])), body))
    for rel, text in texts.items():
        path = vault / f"{rel}.md"
        if path.is_file() and path.read_text(encoding="utf-8", errors="replace") == text:
            continue
        (report["updated"] if path.is_file() else report["added"]).append(rel)
        vault_ontology.save(path, text)
    mark = f"---\ngenere: {MARK}\n"
    for path in sorted((vault / FOLDER).rglob("*.md")) if (vault / FOLDER).is_dir() else []:
        rel = path.relative_to(vault).with_suffix("").as_posix()
        if rel not in texts and path.read_text(encoding="utf-8", errors="replace").startswith(mark):
            path.unlink()
            report["removed"] += 1
    report["notes"] = len(texts)
    return 0


def push(onto: dict, mission: dict, ref: Path, vault: Path, kinds, apply: bool, report: dict) -> int:
    """Versement des notes de la mission dans le référentiel : ajout, alias complétés, conflits signalés."""
    local = typed_notes(vault, kinds, skip=FOLDER)
    existing = typed_notes(ref, kinds)
    index = {}
    for rel, (data, body) in existing.items():
        for key in keys_of(rel, data, body):
            index.setdefault(key, rel)
    folders = {k: vault_ontology.safe_folder(onto["types"][k].get("folder", k)) for k in kinds}
    planned = {}  # chemin dans la mission -> chemin dans le référentiel
    for rel, (data, body) in local.items():
        hit = next((index[k] for k in keys_of(rel, data, body) if k in index), None)
        planned[rel] = hit or f"{folders[data['type']]}/{vault_ontology.safe_name(rel.rsplit('/', 1)[-1])}"

    def keep(path: str) -> str | None:
        return planned.get(path) or next((t for r, t in planned.items() if r.rsplit("/", 1)[-1] == path), None)
    source = mission.get("name", "mission")
    writes = {}
    for rel, (data, body) in local.items():
        target = planned[rel]
        if target in existing:
            old, old_body = existing[target]
            aliases = [a for a in (data.get("aliases") or []) if a not in (old.get("aliases") or [])]
            if norm(intro(body, keep)) != norm(intro(old_body, lambda t: t)):
                report["conflicts"].append(f"{target} : texte différent dans la mission « {source} » ({rel}), "
                                           "référentiel gardé")
            if aliases and old.get("genere") == MARK:
                merged = {**old, "aliases": (old.get("aliases") or []) + aliases}
                writes[target] = note_text(merged, old_body)
                report["updated"].append(target)
            elif aliases:
                report["conflicts"].append(f"{target} : note tenue à la main, alias {', '.join(aliases)} non ajoutés")
            continue
        meta = clean_meta(onto, data, keep, source)
        found = vault_ontology.check_meta(onto, meta, generated=True)[0]
        if found:
            report["warnings"].append(f"{rel} : hors ontologie, non versée : {found[0]}")
            continue
        writes[target] = note_text(meta, intro(body, keep))
        report["added"].append(target)
    report["notes"] = len(local)
    if apply:
        for rel, text in writes.items():
            vault_ontology.save(ref / f"{rel}.md", text)
    elif writes:
        report["warnings"].append(f"à blanc : {vault_ontology.count(len(writes), 'note')} à verser ; relisez "
                                  "added et conflicts, puis relancez avec --apply")
    return 0


if __name__ == "__main__":
    sys.exit(main())
