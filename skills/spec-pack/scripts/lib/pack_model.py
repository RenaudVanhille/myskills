"""Modèle neutre d'une mission pour le dossier de spécifications : exigences numérotées FR-n et NFR-n, fonctionnalités,
option retenue, contextes, entités, registre, pile technique, design system, pages et revue UX. Aucune écriture : tout vient des livrables déjà validés.

    build(pieces, extra, name, chosen)  -> (modèle, avertissements)

`pieces` : livrables lus et validés (requirements, options, decision, domains, model, api, tests,
register, design, pages, review, breakdown) ; `extra` : la description facultative specs.json (vision, utilisateurs, parcours...).
"""
from text_tools import requirement_nature

PRIORITIES = ("indispensable", "importante", "souhaitable", "hors-perimetre")
MVP = ("indispensable", "importante")
GENERAL = "Général"
# Bibliothèque d'interface visée par page_build.py et ui_breakdown.py (--target) -> frameworks à citer.
FRONTENDS = {"react-mui": ("React", "MUI"), "react-antd": ("React", "Ant Design"), "vue-vuetify": ("Vue", "Vuetify"),
             "angular-material": ("Angular", "Angular Material"), "bootstrap": ("Bootstrap",)}


def nature(req: dict) -> str:
    """fonctionnelle ou non-fonctionnelle : champ nature, sinon préfixe de numérotation ou catégorie."""
    found = requirement_nature(req)
    if found:
        return found
    return "non-fonctionnelle" if req.get("category") else "fonctionnelle"


def pick_option(pieces: dict, chosen: str | None, warnings: list[str]) -> tuple[dict | None, dict]:
    """Option exportée et sa décision : --option, sinon decision.json, la décision d'options.json,
    puis la recommandation (signalée : pas encore décidée)."""
    options = pieces.get("options")
    if not options:
        return None, {}
    decision = pieces.get("decision") or options.get("decision")
    if chosen:
        basis = {"option": chosen, "why": "option demandée à l'export (--option)", "status": "demandée"}
    elif decision:
        basis = {**decision, "status": "décidée"}
    else:
        basis = {**options["recommendation"], "status": "recommandée"}
        warnings.append(f"option {basis['option']} recommandée mais pas encore décidée : architecture.md la "
                        "reprend comme hypothèse (decision.json, ou --option ID)")
    option = next((o for o in options["options"] if o["id"] == basis["option"]), None)
    return option, basis


def feature_of(req: dict, contexts: list[dict], given: dict) -> str:
    """Fonctionnalité d'une exigence : specs.json, sinon son contexte délimité, sinon son domaine."""
    if req["id"] in given:
        return given[req["id"]]
    context = next((c for c in contexts if req["id"] in c.get("refs", [])), None)
    return context["name"] if context else req.get("domain") or GENERAL


def number(reqs: list[dict], prefix: str, tests: list[dict]) -> list[dict]:
    """Exigences renumérotées (FR-1, NFR-1...) dans l'ordre du catalogue, avec leurs cas de recette."""
    return [{**req, "ref": f"{prefix}-{index}",
             "tests": [case for case in tests if req["id"] in case.get("refs", [])]}
            for index, req in enumerate(reqs, 1)]


def features(frs: list[dict], pieces: dict, extra: dict, warnings: list[str]) -> list[dict]:
    """Fonctionnalités dans l'ordre de première apparition, chacune avec ses FR."""
    contexts = (pieces.get("domains") or {}).get("contexts", [])
    known = {fr["id"] for fr in frs}
    given, described = {}, {c["name"]: c.get("description", "") for c in contexts}
    for feature in extra.get("features", []):
        described[feature["name"]] = feature.get("description", "")
        unknown = [ref for ref in feature["refs"] if ref not in known]
        if unknown:
            warnings.append(f"specs.json : fonctionnalité « {feature['name']} », exigence(s) fonctionnelle(s) "
                            f"inconnue(s) ou hors périmètre : {', '.join(unknown)}")
        given.update({ref: feature["name"] for ref in feature["refs"]})
    groups: dict[str, list[dict]] = {f["name"]: [] for f in extra.get("features", [])}
    for fr in frs:
        groups.setdefault(feature_of(fr, contexts, given), []).append(fr)
    return [{"name": name, "description": described.get(name, ""), "frs": items}
            for name, items in groups.items() if items]


def glossary(pieces: dict) -> list[tuple[str, str]]:
    """Termes du catalogue, puis ceux des contextes délimités absents du catalogue (sens par contexte)."""
    terms = [(g["term"], g["definition"]) for g in pieces["requirements"].get("glossary", [])]
    seen = {term.lower() for term, _ in terms}
    for context in (pieces.get("domains") or {}).get("contexts", []):
        for term, meaning in context.get("terms", {}).items():
            if term.lower() in seen:
                terms.append((f"{term} ({context['name']})", meaning))
            else:
                terms.append((term, meaning))
                seen.add(term.lower())
    return terms


def stack(option: dict | None, breakdown: dict, extra: dict) -> list[tuple[str, str, str]]:
    """Pile technique (nom, version, rôle) : specs.json d'abord, puis la bibliothèque d'interface visée par le
    découpage des maquettes, puis la technologie et la version de chaque composant de l'option (options.json) ;
    un nom n'apparaît qu'une fois."""
    rows = [(s["name"], s.get("version", ""), s.get("role", "")) for s in extra.get("stack", [])]
    pinned = breakdown.get("versions", {})
    rows += [(name, pinned.get(name, ""), "interface (cible des maquettes)")
             for name in FRONTENDS.get(breakdown.get("target"), ())]
    rows += [(c["tech"], c.get("version", ""), c["label"]) for c in (option or {}).get("components", []) if c.get("tech")]
    # Une technologie citée deux fois garde la première ligne, complétée de la version connue plus bas.
    known = {name.lower(): version for name, version, _ in rows if version}
    rows = [(name, version or known.get(name.lower(), ""), role) for name, version, role in rows]
    seen: set[str] = set()
    return [row for row in rows if not (row[0].lower() in seen or seen.add(row[0].lower()))]


def register(pieces: dict, kind: str) -> list[dict]:
    return [item for item in (pieces.get("register") or {}).get("items", []) if item["kind"] == kind]


def build(pieces: dict, extra: dict, name: str, chosen: str | None) -> tuple[dict, list[str]]:
    warnings: list[str] = []
    catalog = pieces["requirements"]
    kept = [r for r in catalog["requirements"] if r.get("status") != "retiree"]
    scope = [r for r in kept if r["priority"] != "hors-perimetre"]
    tests = (pieces.get("tests") or {}).get("cases", [])
    frs = number([r for r in scope if nature(r) == "fonctionnelle"], "FR", tests)
    nfrs = number([r for r in scope if nature(r) != "fonctionnelle"], "NFR", tests)
    option, decision = pick_option(pieces, chosen, warnings)
    domains = pieces.get("domains") or {}
    model = {
        "name": extra.get("project") or name, "extra": extra,
        "context": (pieces.get("options") or {}).get("context") or domains.get("context") or "",
        "frs": frs, "nfrs": nfrs, "ids": {r["id"]: r["ref"] for r in frs + nfrs},
        "features": features(frs, pieces, extra, warnings),
        "excluded": [r for r in kept if r["priority"] == "hors-perimetre"],
        "glossary": glossary(pieces),
        "option": option, "decision": decision,
        "others": [o for o in (pieces.get("options") or {}).get("options", []) if o is not option],
        "contexts": domains.get("contexts", []), "relations": domains.get("relations", []),
        "style": domains.get("decision") or {},
        "entities": (pieces.get("model") or {}).get("entities", []),
        "links": (pieces.get("model") or {}).get("relations", []),
        "operations": (pieces.get("api") or {}).get("operations", []),
        "events": (pieces.get("api") or {}).get("events", []),
        "stack": stack(option, pieces.get("breakdown") or {}, extra),
        "design": pieces.get("design"), "pages": pieces.get("pages", []),
        "review": pieces.get("review") or {}, "breakdown": pieces.get("breakdown") or {},
        "assumptions": register(pieces, "hypothese") + register(pieces, "prerequis"),
        "exclusions": register(pieces, "exclusion"),
        "questions": [q for q in register(pieces, "question") if not q.get("answer")],
    }
    return model, warnings
