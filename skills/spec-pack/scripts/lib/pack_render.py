"""Rendu Markdown du dossier de spécifications depuis le modèle de pack_model.

Chaque document se lit seul : il rappelle le produit, les conventions d'identifiants et les autres
documents du dossier, puis porte tout ce qui relève de son aspect. Aucun format d'outil (BMAD, Spec Kit,
Kiro...) : des sections en français, des identifiants stables (FR-n, NFR-n, AD-n, S-n.m) et l'identifiant
d'origine du catalogue entre parenthèses. Une section sans donnée est omise. Chaque fonction rend
(frontmatter, corps).

    readme(m, docs, annexes, missing), fonctionnel(m), architecture(m), tests(m), livraison(m, ux_lines)
    describe(m, name, front, body) -> frontmatter complet, pour qu'un agent choisisse et relie les documents
"""

import re

LINK_KINDS = {"1-1": "||--||", "1-n": "||--o{", "n-n": "}o--o{"}
# Documents du dossier : nom -> (titre, ce qu'il couvre, lecteurs).
DOCS = {
    "fonctionnel.md": ("Spécification fonctionnelle", "vision, utilisateurs, parcours, glossaire, exigences "
                       "fonctionnelles FR-n avec leurs critères d'acceptation, périmètre", "produit, développement, recette"),
    "ux.md": ("Spécification UX", "identité visuelle et tokens, écrans, composants, maquettes, accessibilité, "
              "constats UX", "conception, développement de l'interface"),
    "architecture.md": ("Spécification d'architecture", "option retenue, décisions AD-n, pile technique et versions, "
                        "composants et flux, données, interfaces, exigences non fonctionnelles NFR-n",
                        "développement, exploitation"),
    "tests.md": ("Spécification des tests", "cas de recette, critères d'acceptation, vérification des NFR, "
                 "couverture des exigences", "recette, développement"),
    "livraison.md": ("Plan de livraison", "lots et stories S-n.m, ordre de réalisation, dépendances, définition "
                     "de terminé", "développement, pilotage"),
}
CONVENTIONS = ("FR-n : exigence fonctionnelle ; NFR-n : exigence non fonctionnelle ; AD-n : décision d'architecture ; "
               "S-n.m : story ; UX-n : exigence d'interface ; T-n : cas de recette. L'identifiant d'origine du "
               "catalogue (EF-001, ENF-001...) suit chaque exigence entre parenthèses.")
PRIORITY_ORDER = {"indispensable": 0, "importante": 1, "souhaitable": 2}


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
    """Identifiants du dossier des exigences citées (les autres références sont laissées de côté)."""
    return ", ".join(m["ids"][ref] for ref in refs or [] if ref in m["ids"])


def node(identifier: str) -> str:
    return "n_" + re.sub(r"\W", "_", identifier)


def quoted(text: str) -> str:
    return '"' + str(text).replace('"', "'") + '"'


def tag(req: dict) -> str:
    return f"{req['ref']} ({req['id']}, {req['priority']})"


def intro(m: dict, name: str, extra: str = "") -> str:
    """En-tête commun : ce qu'est le document, le produit, les autres documents, les conventions."""
    title, covers, _ = DOCS.get(name, ("Dossier de spécifications", "", ""))
    others = ", ".join(f"`{other}` ({DOCS[other][0].lower()})" for other in m.get("docs", DOCS) if other != name)
    summary = m["extra"].get("vision") or m["context"] or ""
    return join([
        f"# {title} : {m['name']}",
        f"> Document autonome du dossier de spécifications de « {m['name']} » : il se lit seul et couvre "
        f"{covers}. Autres documents du dossier : {others}. {CONVENTIONS}" if covers else "",
        section("Contexte", join([summary, extra])),
    ]).strip()


def people(m: dict) -> list[str]:
    """Utilisateurs : ceux de specs.json, sinon les personnes de l'option retenue."""
    users = [u for u in m["extra"].get("users", []) if not u.get("non_user")]
    if users:
        return [u["name"] for u in users]
    return [c["label"] for c in (m["option"] or {}).get("components", []) if c.get("role") == "person"]


def scope(m: dict) -> tuple[list[str], list[str]]:
    """Dans le périmètre de la première version (indispensable, importante), et reporté (souhaitable)."""
    line = lambda r: f"{r['title']} ({r['ref']}, {r['id']}, {r['priority']})"  # noqa: E731
    reqs = m["frs"] + m["nfrs"]
    return ([line(r) for r in reqs if r["priority"] != "souhaitable"],
            [line(r) for r in reqs if r["priority"] == "souhaitable"])


def non_goals(m: dict) -> list[str]:
    return (list(m["extra"].get("non_goals", []))
            + [f"{r['title']} : {r.get('reason') or 'hors périmètre'} ({r['id']})" for r in m["excluded"]]
            + [f"{e['text']} ({e['id']})" for e in m["exclusions"]])


def open_questions(m: dict) -> list[str]:
    asked = [f"{q} ({r['ref']})" for r in m["frs"] + m["nfrs"] for q in r.get("questions", [])]
    return asked + [f"{q['text']} ({q['id']})" for q in m["questions"]]


def assumptions(m: dict) -> list[str]:
    items = [f"{a['text']} ({a['id']}" + (f", {mapped(a.get('refs'), m)})" if mapped(a.get("refs"), m) else ")")
             for a in m["assumptions"]]
    if m["decision"].get("status") == "recommandée":
        items.append(f"L'option {m['decision']['option']} est recommandée, pas encore décidée.")
    return items


def journey(item: dict, index: int, m: dict) -> str:
    lines = [f"- **UJ-{index}. {item['title']}**", f"  - Persona et contexte : {item['persona']}"]
    lines += [f"  - Point de départ : {item['entry']}"] if item.get("entry") else []
    lines.append("  - Étapes : " + " ; ".join(item["path"]))
    lines += [f"  - {label} : {item[key]}" for key, label in
              (("climax", "Moment clé"), ("resolution", "Issue"), ("edge", "Cas limite")) if item.get(key)]
    if mapped(item.get("refs"), m):
        lines.append(f"  - Exigences : {mapped(item['refs'], m)}")
    return "\n".join(lines)


def criteria(req: dict) -> list[str]:
    """Critères d'acceptation Étant donné / Quand / Alors tirés des cas de recette, sinon de la mesure."""
    blocks = [f"**Étant donné** {case.get('preconditions') or 'le contexte nominal'}, **quand** "
              f"{' ; '.join(case['steps'])}, **alors** {case['expected']} ({case['id']})" for case in req["tests"]]
    if not blocks and req.get("metric"):
        blocks = [f"**Alors** {req['metric']} (mesure de l'exigence)"]
    return blocks


def users_section(m: dict) -> str:
    extra = m["extra"]
    jobs = [f"**{u['name']}** : " + " ; ".join(u.get("jobs", [])) if u.get("jobs") else f"**{u['name']}**"
            for u in extra.get("users", []) if not u.get("non_user")] or people(m)
    return join([
        bullets(jobs),
        section("Hors de la première version", bullets(u["name"] for u in extra.get("users", []) if u.get("non_user")), 3),
    ])


def metrics(m: dict) -> str:
    kinds = {"primary": "principal", "secondary": "secondaire", "counter": "garde-fou, à ne pas optimiser"}
    return bullets(f"**SM-{i}** {item['name']} : {item['target']} ({kinds[item.get('kind', 'primary')]})"
                   + (f", valide {mapped(item.get('refs'), m)}" if mapped(item.get("refs"), m) else "")
                   for i, item in enumerate(m["extra"].get("metrics", []), 1))


def nfr_line(r: dict) -> str:
    return (f"**{r['ref']} : {r['title']}** ({r.get('category', 'autre')}) : {r['text']}"
            + (f" Mesure : {r['metric']}." if r.get("metric") else "") + f" *({r['id']}, {r['priority']})*")


# --- Fonctionnel -------------------------------------------------------------------------------------------

def requirement(req: dict) -> str:
    checks = criteria(req)
    return join([
        f"#### {req['ref']} : {req['title']}", req["text"], f"*Origine : {req['id']}, priorité {req['priority']}.*",
        "**Critères d'acceptation :**\n" + bullets(checks) if checks
        else "**Critères d'acceptation :** à écrire, aucun cas de recette ni mesure ne cite cette exigence.",
        "**Questions ouvertes :**\n" + bullets(req["questions"]) if req.get("questions") else "",
    ]).strip()


def fonctionnel(m: dict) -> tuple[dict, str]:
    feats = [join([f"### {i}. {f['name']}", f["description"]] + [requirement(r) for r in f["frs"]]).strip()
             for i, f in enumerate(m["features"], 1)]
    inside, later = scope(m)
    body = join([
        intro(m, "fonctionnel.md"),
        section("Problème", m["extra"].get("problem", "")),
        section("Utilisateurs", users_section(m)),
        section("Parcours clés", "\n".join(journey(j, i, m) for i, j in enumerate(m["extra"].get("journeys", []), 1))),
        section("Glossaire", bullets(f"**{term}** : {definition}" for term, definition in m["glossary"])),
        section("Exigences fonctionnelles", join(feats)),
        section("Exigences non fonctionnelles", "Rappel ; leur prise en compte est détaillée dans `architecture.md` "
                "et leur vérification dans `tests.md`.\n\n" + bullets(nfr_line(r) for r in m["nfrs"])
                if m["nfrs"] else ""),
        section("Périmètre", join([section("Première version", bullets(inside), 3),
                                   section("Reporté (souhaitable)", bullets(later), 3),
                                   section("Hors périmètre", bullets(non_goals(m)), 3)])),
        section("Indicateurs de succès", metrics(m)),
        section("Questions ouvertes", "\n".join(f"{i}. {q}" for i, q in enumerate(open_questions(m), 1))),
        section("Hypothèses et prérequis", bullets(assumptions(m))),
    ])
    return {"title": f"Spécification fonctionnelle : {m['name']}", "type": "fonctionnel"}, body


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
    if not m["entities"]:
        return ""
    name = lambda value: re.sub(r"\W", "_", value)  # noqa: E731
    lines = ["erDiagram"] + [f"  {name(e['name'])}" for e in m["entities"]]
    lines += [f"  {name(link['from'])} {LINK_KINDS[link['kind']]} {name(link['to'])} : {quoted(link['label'])}"
              for link in m["links"]]
    return "```mermaid\n" + "\n".join(lines) + "\n```"


def entities(m: dict) -> str:
    def field(f: dict) -> str:
        marks = [mark for mark, on in (("clé", f.get("key")), ("obligatoire", f.get("required")),
                                       ("unique", f.get("unique"))) if on]
        marks += [f"donnée personnelle : {f['personal']}"] if f.get("personal") else []
        return f"`{f['name']}` {f.get('type', '')}" + (f" ({', '.join(marks)})" if marks else "")
    return table(["Entité", "Libellé", "Champs"],
                 [[e["name"], e.get("label", ""), " ; ".join(field(f) for f in e.get("fields", []))]
                  for e in m["entities"]])


def decisions(m: dict) -> list[dict]:
    """Décisions d'architecture (AD-n) : option retenue, style, relations entre contextes, exigences non
    fonctionnelles indispensables mesurées."""
    option, decision, items = m["option"], m["decision"], []
    items.append({"title": f"Option {option['id']} : {option['name']}", "binds": "tout le produit",
                  "prevents": "; ".join(f"{o['name']} ({'; '.join(o.get('cons', [])) or 'écartée'})"
                                        for o in m["others"]) or "une autre architecture que celle étudiée",
                  "rule": f"{option['summary']} Option {decision['status']} : {decision['why']}."})
    if m["style"]:
        items.append({"title": f"Style {m['style']['style']}", "binds": "tout le produit",
                      "prevents": "un découpage de déploiement différent selon les équipes", "rule": m["style"]["why"]})
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
            items.append({"title": req["title"], "binds": req["ref"],
                          "prevents": "une réalisation qui ne tient pas cette exigence indispensable",
                          "rule": f"{req['text']} Mesure : {req['metric']}."})
    return items


def components(m: dict) -> str:
    return table(["Composant", "Rôle", "Technologie", "Exigences"],
                 [[c["label"], c.get("role", "service"), " ".join(filter(None, (c.get("tech"), c.get("version")))),
                   mapped(c.get("refs"), m)] for c in m["option"]["components"]])


def interfaces(m: dict) -> str:
    rows = [[f"{op['method']} {op['path']}", op.get("summary", ""), mapped(op.get("refs"), m)]
            for op in m["operations"]]
    rows += [[f"événement {ev['name']}", ev.get("summary", ""), mapped(ev.get("refs"), m)] for ev in m["events"]]
    return table(["Interface", "Rôle", "Exigences"], rows)


def rejected(m: dict) -> str:
    return join([join([f"### {o['id']} : {o['name']}", o["summary"],
                       "Limites :\n" + bullets(o["cons"]) if o.get("cons") else "",
                       "Exigences non couvertes :\n" + bullets(
                           f"{mapped([ref], m) or ref} ({gap.get('level', '')}) : {gap.get('note', '')}"
                           for ref, gap in o["gaps"].items()) if o.get("gaps") else ""]).strip()
                 for o in m["others"]])


def pending(m: dict) -> str:
    option = m["option"]
    items = [f"Risque à traiter : {risk}" for risk in option.get("risks", [])]
    items += [f"{m['ids'].get(ref, ref)} couverte {gap.get('level', 'en partie')} : {gap.get('note', '')}"
              for ref, gap in option.get("gaps", {}).items()]
    items += [f"Version à fixer : {name}" + (f" ({role})" if role else "") for name, version, role in m["stack"]
              if not version]
    return bullets(items)


def architecture(m: dict) -> tuple[dict, str]:
    option = m["option"]
    ads = [f"### AD-{i} : {d['title']}\n\n- **Règle :** {d['rule']}\n- **Portée :** {d['binds']}\n"
           f"- **Évite :** {d['prevents']}" for i, d in enumerate(decisions(m), 1)]
    stack = table(["Technologie", "Version", "Rôle"], [[name, version or "à fixer", role] for name, version, role in m["stack"]])
    body = join([
        intro(m, "architecture.md", f"Option retenue : **{option['name']}** ({m['decision']['status']}). "
                                    f"{option['summary']}"),
        section("Décisions d'architecture", join(ads)),
        section("Pile technique", stack),
        section("Composants et flux", join([components(m), flow_chart(option)])),
        section("Données", join([entity_chart(m), entities(m)])),
        section("Interfaces", interfaces(m)),
        section("Exigences non fonctionnelles", bullets(nfr_line(r) for r in m["nfrs"])),
        section("Options écartées", rejected(m)),
        section("Risques et points à fixer", pending(m)),
    ])
    return {"title": f"Spécification d'architecture : {m['name']}", "type": "architecture"}, body


# --- Tests -------------------------------------------------------------------------------------------------

def case_block(case: dict, m: dict) -> str:
    return join([
        f"#### {case['id']} : {case['title']}",
        bullets([f"Exigences : {mapped(case.get('refs'), m) or ', '.join(case.get('refs', []))}",
                 f"Type : {case.get('kind', 'fonctionnel')}, priorité {case.get('priority', 'normale')}"]
                + ([f"Préconditions : {case['preconditions']}"] if case.get("preconditions") else [])),
        "\n".join(f"{i}. {step}" for i, step in enumerate(case["steps"], 1)),
        f"**Résultat attendu :** {case['expected']}",
    ]).strip()


def tests(m: dict) -> tuple[dict, str]:
    reqs = m["frs"] + m["nfrs"]
    cases = list({case["id"]: case for r in reqs for case in r["tests"]}.values())
    groups = [(f["name"], [c for c in cases if any(r["id"] in c.get("refs", []) for r in f["frs"])]) for f in m["features"]]
    shown = {c["id"] for _, group in groups for c in group}
    groups.append(("Exigences non fonctionnelles", [c for c in cases if c["id"] not in shown]))
    covered = sum(1 for r in reqs if r["tests"])
    strategy = bullets([
        f"{len(cases)} cas de recette ; {covered} exigence(s) sur {len(reqs)} couvertes par au moins un cas.",
        "Chaque exigence fonctionnelle se vérifie par ses critères d'acceptation (cas cités) ; chaque exigence non "
        "fonctionnelle mesurée se vérifie par sa mesure, en charge ou en revue.",
        "Les cas s'automatisent quand c'est possible ; un cas manuel le reste en connaissance de cause."])
    uncovered = [f"{r['title']} ({r['ref']}, {r['id']}, {r['priority']})" + (f" : vérifier la mesure « {r['metric']} »" if r.get("metric") else "")
                 for r in reqs if not r["tests"]]
    matrix = table(["Exigence", "Origine", "Titre", "Priorité", "Cas"],
                   [[r["ref"], r["id"], r["title"], r["priority"], ", ".join(c["id"] for c in r["tests"]) or "à écrire"]
                    for r in reqs])
    body = join([
        intro(m, "tests.md"),
        section("Stratégie", strategy),
        section("Cas de recette", join(section(name, join(case_block(c, m) for c in group), 3)
                                       for name, group in groups if group)),
        section("Vérification des exigences non fonctionnelles", bullets(
            f"{r['ref']} {r['title']} : {r.get('metric') or r['text']} ({r['id']})" for r in m["nfrs"])),
        section("Exigences sans cas de recette", bullets(uncovered)),
        section("Couverture", matrix),
    ])
    return {"title": f"Spécification des tests : {m['name']}", "type": "tests"}, body


# --- Livraison ---------------------------------------------------------------------------------------------

def livraison(m: dict, ux_lines: list[str]) -> tuple[dict, str]:
    lots, order = [], []
    for n, feature in enumerate(m["features"], 1):
        stories = []
        for s, req in enumerate(sorted(feature["frs"], key=lambda r: PRIORITY_ORDER.get(r["priority"], 3)), 1):
            checks = criteria(req)
            stories.append(join([
                f"#### S-{n}.{s} : {req['title']}", req["text"], f"*Exigence : {tag(req)}.*",
                "**Critères d'acceptation :**\n" + bullets(checks) if checks
                else "**Critères d'acceptation :** à écrire avant de commencer (voir `tests.md`).",
            ]).strip())
            order.append((PRIORITY_ORDER.get(req["priority"], 3), n, s, req))
        lots.append(join([f"### Lot {n} : {feature['name']}", feature["description"]] + stories).strip())
    sequence = [f"S-{n}.{s} {req['title']} ({req['priority']})" for _, n, s, req in sorted(order, key=lambda o: o[:3])]
    externals = [c["label"] for c in (m["option"] or {}).get("components", []) if c.get("role") == "external"]
    deps = [f"Respecter les décisions AD-1 à AD-{len(decisions(m))} de `architecture.md`." if m["option"] else ""]
    deps += [f"Intégration avec {label} : à disposition dès le premier lot qui l'utilise." for label in externals]
    deps += [f"Version à fixer avant de commencer : {name}" for name, version, _ in m["stack"] if not version]
    done = ["Critères d'acceptation de la story vérifiés, cas de recette de `tests.md` passés (automatisés si possible).",
            "Exigences non fonctionnelles concernées tenues (mesures de `architecture.md`).",
            "Décisions d'architecture et pile technique respectées, sans nouvelle dépendance non décidée."]
    done += ["Écrans conformes à `ux.md` (tokens, composants, accessibilité)."] if ux_lines else []
    body = join([
        intro(m, "livraison.md"),
        section("Principes", bullets([
            "Un lot par fonctionnalité, une story par exigence fonctionnelle ; découpage à affiner (taille, "
            "dépendances) par l'équipe ou l'outil de développement.",
            "Ordre : indispensable, puis importante, puis souhaitable ; une story n'est commencée qu'avec ses "
            "critères d'acceptation."])),
        section("Lots et stories", join(lots)),
        section("Exigences d'interface", bullets(ux_lines)),
        section("Ordre de réalisation suggéré", "\n".join(f"{i}. {line}" for i, line in enumerate(sequence, 1))),
        section("Dépendances et préalables", bullets(d for d in deps if d)),
        section("Définition de terminé", bullets(done)),
        section("Coût IA du développement", m.get("ai_cost", "")),
    ])
    return {"title": f"Plan de livraison : {m['name']}", "type": "livraison"}, body


# --- Index -------------------------------------------------------------------------------------------------

def readme(m: dict, docs: list[str], annexes: list[str], missing: list[str]) -> tuple[dict, str]:
    feature_of = {req["id"]: feature["name"] for feature in m["features"] for req in feature["frs"]}
    story = {req["id"]: f"S-{n}.{s}" for n, f in enumerate(m["features"], 1)
             for s, req in enumerate(sorted(f["frs"], key=lambda r: PRIORITY_ORDER.get(r["priority"], 3)), 1)}
    where = {}
    for component in (m["option"] or {}).get("components", []):
        for ref in component.get("refs", []):
            where.setdefault(ref, []).append(component["label"])
    rows = [[r["ref"], r["id"], r["title"], r["priority"], feature_of.get(r["id"], ""),
             ", ".join(where.get(r["id"], [])), ", ".join(c["id"] for c in r["tests"]), story.get(r["id"], "")]
            for r in m["frs"] + m["nfrs"]]
    listed = table(["Document", "Contenu", "Pour"], [[f"[{d}]({d})", DOCS[d][1], DOCS[d][2]] for d in docs if d in DOCS])
    use = bullets([
        "Chaque document se suffit : donnez à l'outil de développement (agent IA, framework de spécification, "
        "équipe) ce README et le document de l'aspect traité, ou tout le dossier.",
        "Les identifiants sont stables d'un export à l'autre : citez-les dans les tâches, les commits et les tests.",
        "En cas d'écart, le texte des exigences (`fonctionnel.md`, `architecture.md`) prime sur les maquettes et "
        "les annexes."])
    body = join([
        f"# Dossier de spécifications : {m['name']}",
        join([m["extra"].get("vision") or m["context"] or "", m["context"] if m["extra"].get("vision") else ""]),
        section("Documents", listed),
        section("Utilisation", use),
        section("Conventions", CONVENTIONS),
        section("Traçabilité", table(["Exigence", "Origine", "Titre", "Priorité", "Fonctionnalité", "Composants",
                                      "Cas", "Story"], rows)),
        section("Annexes", bullets(f"[{path.split('/', 1)[-1]}]({path})" for path in annexes)),
        section("À compléter", bullets(missing)),
    ])
    return {"title": f"Dossier de spécifications : {m['name']}", "type": "index"}, body


# --- Frontmatter -------------------------------------------------------------------------------------------

DEFINED = re.compile(r"^(?:#{2,4} |- \*\*|- |\*\*)((?:FR|NFR|AD|S|T|UX)-[\w.]*\w)(?: :|\*\* :| ·)", re.M)
CITED = re.compile(r"\b((?:FR|NFR)-\d+)\b")
# Identifiants dont chaque document est la source (un autre document peut les rappeler, sans les définir).
OWNS = {"fonctionnel.md": ("FR",), "ux.md": ("UX",), "architecture.md": ("AD", "NFR"), "tests.md": ("T",),
        "livraison.md": ("S",)}
KINDS = {"README.md": "index", "fonctionnel.md": "fonctionnel", "ux.md": "ux", "architecture.md": "architecture",
         "tests.md": "tests", "livraison.md": "livraison"}


def describe(m: dict, name: str, front: dict, body: str) -> dict:
    """Frontmatter lisible par tout agent, sans format d'outil : quoi (type, description), pour qui (audience),
    ce que le document définit (defines) et les exigences qu'il traite (covers), les documents du dossier
    qu'il cite (related). Le titre et le type viennent du rendu."""
    title, covers_text, audience = DOCS.get(name, ("Index du dossier de spécifications", "liste des documents, "
                                                   "conventions, traçabilité des exigences", "tous"))
    defined = [ref for ref in dict.fromkeys(DEFINED.findall(body)) if ref.split("-")[0] in OWNS.get(name, ())]
    cited = sorted(set(CITED.findall(body)) - set(defined), key=lambda ref: (ref.split("-")[0], int(ref.split("-")[1])))
    related = [doc for doc in ["README.md", *m.get("docs", DOCS)] if doc != name and (doc in body or doc == "README.md")]
    meta = {"title": front.get("title", title), "type": KINDS.get(name, "spec"), "product": m["name"],
            "description": f"{title} de « {m['name']} » : {covers_text}.", "audience": audience.split(", "),
            "language": "fr", "status": "draft"}
    meta.update({"defines": defined} if defined else {})
    meta.update({"covers": cited} if cited else {})
    meta.update({"related": related} if related else {})
    return meta
