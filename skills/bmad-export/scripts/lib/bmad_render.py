"""Rendu Markdown des artefacts de planification de BMAD Method (v6) depuis le modèle de bmad_model.

Les titres de section sont ceux des gabarits de BMAD (en anglais : ses agents et son script
sprint_plan.py les reconnaissent) ; le contenu reste celui de la mission, dans sa langue. Une section
sans donnée est omise, comme le demandent les gabarits. Chaque fonction rend (frontmatter, corps).

    brief(m), prd(m), architecture(m), epics(m), addendum(m, companions)
"""

import re

LINK_KINDS = {"1-1": "||--||", "1-n": "||--o{", "n-n": "}o--o{"}
ROLES = {"person": "utilisateur", "external": "système externe", "db": "base de données", "queue": "file"}


def bullets(items) -> str:
    return "\n".join(f"- {item}" for item in items)


def section(title: str, body: str, level: int = 2) -> str:
    """Section titrée, ou rien si elle est vide."""
    return f"{'#' * level} {title}\n\n{body.strip()}" if body and body.strip() else ""


def join(parts) -> str:
    return "\n\n".join(part for part in parts if part) + "\n"


def cell(text) -> str:
    return str(text).replace("|", "\\|").replace("\n", " ")


def table(head: list[str], rows: list[list]) -> str:
    if not rows:
        return ""
    lines = ["| " + " | ".join(head) + " |", "| " + " | ".join("---" for _ in head) + " |"]
    return "\n".join(lines + ["| " + " | ".join(cell(c) for c in row) + " |" for row in rows])


def mapped(refs, m: dict) -> str:
    """Identifiants BMAD des exigences citées (les autres références sont laissées de côté)."""
    return ", ".join(m["ids"][ref] for ref in refs or [] if ref in m["ids"])


def node(identifier: str) -> str:
    return "n_" + re.sub(r"\W", "_", identifier)


def quoted(text: str) -> str:
    return '"' + str(text).replace('"', "'") + '"'


def people(m: dict) -> list[str]:
    """Utilisateurs : ceux de bmad.json, sinon les personnes de l'option retenue."""
    users = [u for u in m["extra"].get("users", []) if not u.get("non_user")]
    if users:
        return [u["name"] for u in users]
    return [c["label"] for c in (m["option"] or {}).get("components", []) if c.get("role") == "person"]


def scope(m: dict) -> tuple[list[str], list[str]]:
    """Dans le périmètre de la première version (indispensable, importante), et reporté (souhaitable)."""
    line = lambda r: f"{r['title']} ({r['bmad']}, {r['priority']})"  # noqa: E731
    reqs = m["frs"] + m["nfrs"]
    return ([line(r) for r in reqs if r["priority"] != "souhaitable"],
            [line(r) + " : souhaitable, reporté" for r in reqs if r["priority"] == "souhaitable"])


def non_goals(m: dict) -> list[str]:
    return (list(m["extra"].get("non_goals", []))
            + [f"{r['title']} : {r.get('reason') or 'hors périmètre'} ({r['id']})" for r in m["excluded"]]
            + [f"{e['text']} ({e['id']})" for e in m["exclusions"]])


def open_questions(m: dict) -> list[str]:
    asked = [f"{q} ({r['bmad']})" for r in m["frs"] + m["nfrs"] for q in r.get("questions", [])]
    return asked + [f"{q['text']} ({q['id']})" for q in m["questions"]]


def assumptions(m: dict) -> list[str]:
    items = [f"{a['text']} ({a['id']}" + (f", {mapped(a.get('refs'), m)})" if mapped(a.get("refs"), m) else ")")
             for a in m["assumptions"]]
    if m["decision"].get("status") == "recommandée":
        items.append(f"L'option {m['decision']['option']} est recommandée, pas encore décidée.")
    return items


def measures(m: dict) -> list[str]:
    return [f"{r['title']} : {r['metric']} ({r['bmad']})" for r in m["nfrs"]
            if r.get("metric") and r["priority"] == "indispensable"]


# --- Product brief -----------------------------------------------------------------------------------------

def brief(m: dict) -> tuple[dict, str]:
    option, extra = m["option"], m["extra"]
    solution = f"**{option['name']}.** {option['summary']}" if option else ""
    inside, later = scope(m)
    different = bullets((option or {}).get("pros", [])) if option else ""
    if option and m["decision"].get("why"):
        different = join([different, f"Pourquoi cette option : {m['decision']['why']}."]).strip()
    body = join([
        f"# Product Brief: {m['name']}",
        section("Executive Summary", join([extra.get("vision", ""), m["context"]])),
        section("The Problem", extra.get("problem", "")),
        section("The Solution", solution),
        section("What Makes This Different", different),
        section("Who This Serves", bullets(people(m))),
        section("Success Criteria", bullets(measures(m))),
        section("Scope", join([section("In", bullets(inside), 3), section("Out", bullets(later + non_goals(m)), 3)])),
    ])
    return {"title": m["name"], "status": "draft"}, body


# --- PRD ---------------------------------------------------------------------------------------------------

def requirement(req: dict) -> str:
    """Une exigence fonctionnelle au format du gabarit : FR, conséquences testables, notes."""
    sources = ", ".join(dict.fromkeys(s["doc"] for s in req.get("sources", [])))
    origin = f"*Origine : {req['id']}, priorité {req['priority']}" + (f", source {sources}" if sources else "") + ".*"
    checks = [f"{case['expected']} ({case['id']})" for case in req["tests"]]
    if req.get("metric"):
        checks.append(f"Mesure : {req['metric']}")
    return join([
        f"#### {req['bmad']}: {req['title']}", req["text"], origin,
        "**Consequences (testable):**\n" + bullets(checks) if checks else "",
        "**Notes:**\n" + bullets(f"Question ouverte : {q}" for q in req["questions"]) if req.get("questions") else "",
    ]).strip()


def users_section(m: dict) -> str:
    extra = m["extra"]
    jobs = [f"**{u['name']}** : " + " ; ".join(u.get("jobs", [])) if u.get("jobs") else f"**{u['name']}**"
            for u in extra.get("users", []) if not u.get("non_user")] or people(m)
    return join([
        section("2.1 Jobs To Be Done", bullets(jobs), 3),
        section("2.2 Non-Users (v1)", bullets(u["name"] for u in extra.get("users", []) if u.get("non_user")), 3),
        section("2.3 Key User Journeys", "\n".join(journey(j, i, m) for i, j in
                                                   enumerate(extra.get("journeys", []), 1)), 3),
    ])


def journey(item: dict, index: int, m: dict) -> str:
    lines = [f"- **UJ-{index}. {item['title']}**", f"  - **Persona + context:** {item['persona']}"]
    lines += [f"  - **{label}:** {item[key]}" for key, label in
              (("entry", "Entry state"),) if item.get(key)]
    lines.append("  - **Path:** " + " ; ".join(item["path"]))
    lines += [f"  - **{label}:** {item[key]}" for key, label in
              (("climax", "Climax"), ("resolution", "Resolution"), ("edge", "Edge case")) if item.get(key)]
    if mapped(item.get("refs"), m):
        lines.append(f"  - **Realized by:** {mapped(item['refs'], m)}")
    return "\n".join(lines)


def metrics(m: dict) -> str:
    groups = {"primary": "Primary", "secondary": "Secondary", "counter": "Counter-metrics (do not optimize)"}
    parts, count = [], 0
    for kind, title in groups.items():
        lines = []
        count = 0 if kind == "counter" else count
        for item in [x for x in m["extra"].get("metrics", []) if x.get("kind", "primary") == kind]:
            count += 1
            covers = mapped(item.get("refs"), m)
            lines.append(f"- **SM-{'C' if kind == 'counter' else ''}{count}**: {item['name']} : {item['target']}."
                         + (f" Validates {covers}." if covers else ""))
        if lines:
            parts.append(f"**{title}**\n" + "\n".join(lines))
    return join(parts)


def dependencies(m: dict) -> str:
    return bullets(f"**{c['label']}**" + (f" ({mapped(c.get('refs'), m)})" if mapped(c.get("refs"), m) else "")
                   for c in (m["option"] or {}).get("components", []) if c.get("role") == "external")


def prd(m: dict, sources: list[str]) -> tuple[dict, str]:
    purpose = (f"PRD de « {m['name']} », généré par myskills (skill bmad-export) depuis les livrables validés de la "
               f"mission : {', '.join(sources)}. Les exigences fonctionnelles sont numérotées FR-n et les exigences "
               "non fonctionnelles NFR-n ; l'identifiant d'origine du catalogue suit chaque exigence, et la table de "
               "correspondance est dans `addendum.md`, avec les options écartées. Le vocabulaire du glossaire "
               "s'impose aux documents suivants.")
    feats = [join([f"### 4.{i} {f['name']}", f"**Description:** {f['description']}" if f["description"] else "",
                   "**Functional Requirements:**"] + [requirement(r) for r in f["frs"]]).strip()
             for i, f in enumerate(m["features"], 1)]
    nfrs = bullets(f"**{r['bmad']}: {r['title']}** ({r.get('category', 'autre')}) : {r['text']}"
                   + (f" Mesure : {r['metric']}." if r.get("metric") else "") + f" *({r['id']}, {r['priority']})*"
                   for r in m["nfrs"])
    inside, later = scope(m)
    body = join([
        f"# PRD: {m['name']}",
        section("0. Document Purpose", purpose),
        section("1. Vision", m["extra"].get("vision") or m["context"]),
        section("2. Target User", users_section(m)),
        section("3. Glossary", bullets(f"**{term}** : {definition}" for term, definition in m["glossary"])),
        section("4. Features", join(feats)),
        section("5. Non-Goals (Explicit)", bullets(non_goals(m))),
        section("6. MVP Scope", join([section("6.1 In Scope", bullets(inside), 3),
                                      section("6.2 Out of Scope for MVP", bullets(later), 3)])),
        section("7. Success Metrics", metrics(m)),
        section("8. Open Questions", "\n".join(f"{i}. {q}" for i, q in enumerate(open_questions(m), 1))),
        section("9. Assumptions Index", bullets(assumptions(m))),
        section("10. Cross-Cutting NFRs", nfrs),
        section("11. Integration and Dependencies", dependencies(m)),
    ])
    return {"title": m["name"], "status": "draft"}, body


# --- Architecture ------------------------------------------------------------------------------------------

def flow_chart(option: dict) -> str:
    """Vue des composants et des flux de l'option, en Mermaid valide (jamais un graphe vide)."""
    lines = ["flowchart LR"] + [f"  {node(c['id'])}[{quoted(c['label'])}]" for c in option["components"]]
    for flow in option.get("flows", []):
        arrow = "-.->" if flow.get("style") == "async" else "-->"
        label = f"|{quoted(flow['label'])}|" if flow.get("label") else ""
        lines.append(f"  {node(flow['from'])} {arrow}{label} {node(flow['to'])}")
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def entity_chart(m: dict) -> str:
    """Entités et relations seulement : le détail des champs reste dans le modèle de données."""
    if not m["entities"]:
        return ""
    name = lambda value: re.sub(r"\W", "_", value)  # noqa: E731
    lines = ["erDiagram"] + [f"  {name(e['name'])}" for e in m["entities"]]
    lines += [f"  {name(link['from'])} {LINK_KINDS[link['kind']]} {name(link['to'])} : {quoted(link['label'])}"
              for link in m["links"]]
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def decisions(m: dict) -> list[dict]:
    """Décisions d'architecture (AD-n) tirées de la mission : option retenue, style, relations entre
    contextes, exigences non fonctionnelles indispensables mesurées."""
    option, decision, items = m["option"], m["decision"], []
    items.append({"title": f"Option {option['id']} : {option['name']}", "binds": "all",
                  "prevents": "; ".join(f"{o['name']} ({'; '.join(o.get('cons', [])) or 'écartée'})"
                                        for o in m["others"]) or "une autre architecture que celle étudiée",
                  "rule": f"{option['summary']} Option {decision['status']} : {decision['why']}."})
    if m["style"]:
        items.append({"title": f"Style {m['style']['style']}", "binds": "all",
                      "prevents": "un découpage de déploiement différent selon les équipes",
                      "rule": m["style"]["why"]})
    names = {c["id"]: c["name"] for c in m["contexts"]}
    for rel in m["relations"]:
        up, down = names.get(rel["upstream"], rel["upstream"]), names.get(rel["downstream"], rel["downstream"])
        items.append({"title": f"{down} dépend de {up}", "binds": f"{up}, {down}",
                      "prevents": f"un accès de {up} vers {down}, ou un couplage direct des modèles",
                      "rule": f"{down} consomme {up} ({', '.join(rel['patterns'])}"
                              + (f", {rel['integration']}" if rel.get("integration") else "") + ")"
                              + (f" : {rel['label']}." if rel.get("label") else ".")})
    for req in m["nfrs"]:
        if req["priority"] == "indispensable" and req.get("metric"):
            items.append({"title": req["title"], "binds": req["bmad"],
                          "prevents": "une réalisation qui ne tient pas cette exigence indispensable",
                          "rule": f"{req['text']} Mesure : {req['metric']}."})
    return items


def capability_map(m: dict) -> str:
    rows = []
    for component in m["option"]["components"]:
        covers = mapped(component.get("refs"), m)
        if covers:
            rows.append([covers, component["label"] + (f" ({component['tech']})" if component.get("tech") else ""),
                         "AD-1"])
    return table(["Capability / Area", "Lives in", "Governed by"], rows)


def interfaces(m: dict) -> str:
    rows = [[f"{op['method']} {op['path']}", op.get("summary", ""), mapped(op.get("refs"), m)]
            for op in m["operations"]]
    rows += [[f"événement {ev['name']}", ev.get("summary", ""), mapped(ev.get("refs"), m)] for ev in m["events"]]
    return table(["Interface", "Rôle", "Exigences"], rows)


def deferred(m: dict) -> str:
    option = m["option"]
    items = [f"Risque à traiter : {risk}" for risk in option.get("risks", [])]
    items += [f"{ref} couverte {gap.get('level', 'en partie')} : {gap.get('note', '')}"
              for ref, gap in option.get("gaps", {}).items()]
    items += [f"Version à fixer : {c['tech']} ({c['label']})" for c in option["components"] if c.get("tech")]
    return bullets(items)


def architecture(m: dict, companions: list[str]) -> tuple[dict, str]:
    option = m["option"]
    paradigm = (m["style"].get("style") or option["name"])
    ads = [f"### AD-{i} — {d['title']}\n\n- **Binds:** {d['binds']}\n- **Prevents:** {d['prevents']}\n"
           f"- **Rule:** {d['rule']}" for i, d in enumerate(decisions(m), 1)]
    stack = table(["Name", "Version"], [[c["tech"], "à fixer"] for c in option["components"] if c.get("tech")])
    body = join([
        f"# Architecture Spine — {m['name']}",
        section("Design Paradigm", f"{paradigm} : {option['summary']}"),
        section("Invariants & Rules", join(ads + [flow_chart(option)])),
        section("Stack", stack),
        section("Structural Seed", join([entity_chart(m), interfaces(m)])),
        section("Capability → Architecture Map", capability_map(m)),
        section("Deferred", deferred(m)),
    ])
    front = {"name": m["name"], "type": "architecture-spine", "purpose": "build-substrate", "altitude": "initiative",
             "paradigm": paradigm, "scope": m["name"], "status": "draft",
             "binds": [r["bmad"] for r in m["frs"] + m["nfrs"]], "sources": ["prd.md"], "companions": companions}
    return front, body


# --- Epics et stories --------------------------------------------------------------------------------------

def criteria(req: dict) -> str:
    """Critères d'acceptation Given / When / Then tirés des cas de recette, sinon de la mesure."""
    blocks = [f"**Given** {case.get('preconditions') or 'le contexte nominal'}\n"
              f"**When** {' ; '.join(case['steps'])}\n**Then** {case['expected']} ({case['id']})"
              for case in req["tests"]]
    if not blocks and req.get("metric"):
        blocks = [f"**Given** le contexte nominal\n**When** l'exigence est vérifiée\n**Then** {req['metric']}"]
    return "\n\n".join(blocks) or "À écrire avec `bmad-create-epics-and-stories` : aucun cas de recette ne cite cette exigence."


def epics(m: dict, inputs: list[str]) -> tuple[dict, str]:
    coverage, parts = [], []
    for n, feature in enumerate(m["features"], 1):
        stories = [f"### Story {n}.{s}: {req['title']}\n\n{req['text']}\n\n*Exigence : {req['bmad']} "
                   f"({req['id']}, {req['priority']}).*\n\n**Acceptance Criteria:**\n\n{criteria(req)}"
                   for s, req in enumerate(feature["frs"], 1)]
        coverage += [f"{req['bmad']}: Epic {n}, Story {n}.{s}" for s, req in enumerate(feature["frs"], 1)]
        parts.append(join([f"## Epic {n}: {feature['name']}", feature["description"]] + stories).strip())
    line = lambda r: f"{r['bmad']}: {r['title']}" + (f" ({r['metric']})" if r.get("metric") else "")  # noqa: E731
    inventory = join([
        section("Functional Requirements", bullets(line(r) for r in m["frs"]), 3),
        section("NonFunctional Requirements", bullets(line(r) for r in m["nfrs"]), 3),
        section("Additional Requirements", bullets(f"AD-{i}: {d['title']}" for i, d in
                                                   enumerate(decisions(m) if m["option"] else [], 1)), 3),
        section("FR Coverage Map", bullets(coverage), 3),
    ])
    overview = (f"Ébauche du découpage de {m['name']} en epics et stories, générée depuis le catalogue d'exigences : "
                "une epic par fonctionnalité du PRD, une story par exigence fonctionnelle, dans l'ordre du "
                "catalogue. À reprendre avec `bmad-create-epics-and-stories` (taille des stories, dépendances, "
                "formulation utilisateur) avant `bmad-sprint-planning`.")
    body = join([
        f"# {m['name']} - Epic Breakdown",
        section("Overview", overview),
        section("Requirements Inventory", inventory),
        section("Epic List", bullets(f"Epic {n}: {f['name']} ({len(f['frs'])} stor{'y' if len(f['frs']) == 1 else 'ies'})"
                                     for n, f in enumerate(m["features"], 1))),
    ] + parts)
    return {"status": "draft", "stepsCompleted": [], "inputDocuments": inputs}, body


# --- Addendum ----------------------------------------------------------------------------------------------

def addendum(m: dict, companions: list[str]) -> tuple[dict, str]:
    feature_of = {req["id"]: feature["name"] for feature in m["features"] for req in feature["frs"]}
    where = {}
    for component in (m["option"] or {}).get("components", []):
        for ref in component.get("refs", []):
            where.setdefault(ref, []).append(component["label"])
    rows = [[r["bmad"], r["id"], r["title"], r["priority"], feature_of.get(r["id"], ""),
             ", ".join(where.get(r["id"], [])), ", ".join(case["id"] for case in r["tests"])]
            for r in m["frs"] + m["nfrs"]]
    rejected = [join([f"### {o['id']} : {o['name']}", o["summary"],
                      "Limites :\n" + bullets(o["cons"]) if o.get("cons") else "",
                      "Exigences non couvertes :\n" + bullets(
                          f"{mapped([ref], m) or ref} ({gap.get('level', '')}) : {gap.get('note', '')}"
                          for ref, gap in o["gaps"].items()) if o.get("gaps") else ""]).strip()
                for o in m["others"]]
    body = join([
        f"# Addendum: {m['name']}",
        "Détail qui n'a pas sa place dans le PRD : correspondance des identifiants, options écartées et pièces "
        "de la mission à lire à la demande.",
        section("Requirement Traceability", table(
            ["BMAD", "Origine", "Exigence", "Priorité", "Fonctionnalité", "Composants", "Cas de recette"], rows)),
        section("Rejected Alternatives", join(rejected)),
        section("Source Documents", bullets(f"[{path.rsplit('/', 1)[-1]}]({path})" for path in companions)),
    ])
    return {"title": f"Addendum : {m['name']}", "status": "draft"}, body
