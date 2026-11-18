"""Mise à niveau de l'état d'un workflow (`workflow.json`) : la définition gardée à `init` est remplacée par
celle livrée aujourd'hui, sans rien perdre de l'avancement. Fonctions pures : rien n'est lu ni écrit ici."""

import copy


def merge_definition(state: dict, new: dict, stage_keys) -> tuple[dict, dict]:
    """État avec la définition `new` à la place de l'ancienne, et ce qui change.

    Chaque étape déjà connue garde son statut, ses fichiers et ses entrées. Une étape nouvelle arrive « à
    faire », à sa place dans la définition. Une étape retirée de la définition disparaît si rien n'y a été
    fait ; sinon elle reste, avec son ancienne définition réduite aux champs encore admis (`stage_keys`),
    juste après l'étape qui la précédait.
    """
    old = state.get("definition") or {}
    old_stages = {s["id"]: s for s in old.get("stages", []) if isinstance(s, dict) and "id" in s}
    records = {s["id"]: s for s in state.get("stages", [])}
    used = {e.get("stage") for e in state.get("entries", []) + state.get("archive", [])}
    definition = copy.deepcopy(new)
    stages = definition["stages"]
    new_ids = [s["id"] for s in stages]
    added = [i for i in new_ids if i not in records]
    removed, kept = [], []
    previous = None
    for record in state.get("stages", []):
        name = record["id"]
        if name in new_ids:
            previous = name
            continue
        if record.get("status", "a-faire") == "a-faire" and name not in used:
            removed.append(name)
            continue
        kept.append(name)
        stage = {k: copy.deepcopy(v) for k, v in old_stages.get(name, {}).items() if k in stage_keys}
        stage.setdefault("id", name)
        stage.setdefault("deliverables", sorted(record.get("files", {})) or ["*"])
        position = [s["id"] for s in stages].index(previous) + 1 if previous else 0
        stages.insert(position, stage)
        previous = name
    ids = [s["id"] for s in stages]
    for stage in stages:  # une dépendance vers une étape disparue ne bloque plus rien
        if "after" in stage:
            stage["after"] = [a for a in stage["after"] if a in ids[:ids.index(stage["id"])]]
    updated = [i for i in new_ids if i in records and i in old_stages
               and _public(old_stages[i]) != _public(next(s for s in new["stages"] if s["id"] == i))]
    other = sorted(k for k in set(old) | set(new) if k != "stages" and not k.startswith("_") and old.get(k) != new.get(k))
    result = dict(state)
    result["definition"] = definition
    result["stages"] = [records.get(i) or {"id": i, "status": "a-faire"} for i in ids]
    changes = {"name": new["name"], "changed": definition != old, "added": added, "removed": removed, "kept": kept,
               "updated": updated, "fields": other}
    return result, changes


def _public(stage: dict) -> dict:
    return {k: v for k, v in stage.items() if not k.startswith("_")}


def changed(changes: dict | None) -> bool:
    return bool(changes) and changes["changed"]
