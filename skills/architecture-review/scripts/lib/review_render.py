"""Principes, scénarios attendus, constats acceptés, avis et rapport Markdown de la revue (arch_review.py)."""
from __future__ import annotations

import re
from review_common import ATTRIBUTES, AXES, DECIDED, OFF_DESCRIPTION, RULES, SEVERITIES, STATUS, count_of, plain
from text_tools import requirement_nature, slash_cell as cell


def fits(item: dict, field: str, value) -> bool:
    if field == "count_min":
        return count_of(item) >= value
    if field == "style":
        return item.get("style", "sync") == value
    return bool(re.search(value, plain(item.get(field, ""))))


def said(item: dict, field: str, value, required: bool) -> str:
    """Écart à un principe, en clair : ce qui est exigé ou interdit, et ce que l'élément a."""
    if field == "count_min":
        return f"{value} instances au moins, {count_of(item)} décrite(s)"
    if field == "style":
        return f"flux {value} " + ("exigé" if required else "interdit")
    have = item.get(field) or "absent"
    return f"{field} « {have} » " + (f"hors de « {value} »" if required else f"interdit (« {value} »)")


def principles(rules: list[dict], comps: list[dict], flows: list[dict]) -> list[tuple[str, str, str]]:
    """(principe/élément, message, gravité) des écarts aux principes d'architecture du client."""
    roles = {c["id"]: c.get("role", "system") for c in comps}
    broken = []
    for rule in rules:
        select = rule.get("select", {})
        if rule["target"] == "composants":
            items = [(c["id"], c) for c in comps
                     if (not select.get("roles") or c.get("role", "system") in select["roles"])]
        else:
            items = [(f"{f['from']}>{f['to']}", f) for f in flows
                     if (not select.get("from_roles") or roles.get(f["from"]) in select["from_roles"])
                     and (not select.get("to_roles") or roles.get(f["to"]) in select["to_roles"])
                     and (not select.get("style") or f.get("style", "sync") == select["style"])]
        for element, item in items:
            if any(not fits(item, key, select[key]) for key in ("tech", "label") if select.get(key)):
                continue
            why = [said(item, k, v, True) for k, v in rule.get("require", {}).items() if not fits(item, k, v)]
            why += [said(item, k, v, False) for k, v in rule.get("forbid", {}).items() if fits(item, k, v)]
            if why:
                broken.append((f"{rule['id']}/{element}", f"{rule['label']} ({', '.join(why)})",
                               rule.get("severity", "moyenne")))
    return broken


def expected(rules: list[dict], catalog: dict, comps: list[dict], scenarios) -> list[dict]:
    """Règles de scénario attendu qui s'appliquent (exigence non fonctionnelle indispensable ou importante de
    la catégorie, rôle de composant) et qu'aucun scénario de leur attribut ne suit."""
    categories = {r.get("category") for r in catalog.values()
                  if r.get("status", "retenue") == "retenue" and r.get("priority") in ("indispensable", "importante")
                  and requirement_nature(r) == "non-fonctionnelle"}
    roles = {c.get("role", "system") for c in comps}
    missing = []
    for rule in rules:
        when = rule.get("when", {})
        if (when.get("categories") and not categories & set(when["categories"])) \
                or (when.get("roles") and not roles & set(when["roles"])):
            continue
        texts = [plain(f"{s['stimulus']} {s.get('environment', '')} {s['response']}")
                 for s in scenarios if s["attribute"] == rule["attribute"]]
        if not any(re.search(rule["pattern"], text) for text in texts):
            missing.append(rule)
    return missing


def accept(findings: list[dict], accepted: dict, warnings: list[str]) -> None:
    used = set()
    for finding in findings:
        for key in (f"{finding['rule']}@{finding['element']}", finding["rule"]):
            if key in accepted:
                finding["accepted"] = accepted[key]
                used.add(key)
                break
    warnings += [f"acceptation « {k} » sans constat correspondant" for k in accepted if k not in used]


def verdict_of(open_: list[dict]) -> str:
    if any(f["severity"] == "haute" for f in open_):
        return "défavorable"
    if any(f["severity"] == "moyenne" for f in open_):
        return "favorable avec réserves"
    return "favorable"


def markdown(spec: dict, found: dict, verdict: str) -> str:
    findings, scenarios = found["findings"], found["scenarios"]
    open_ = [f for f in findings if not f["accepted"]]
    lines = [f"# Revue d'architecture : {spec['title']}", ""]
    if spec.get("context"):
        lines += [spec["context"], ""]
    if spec.get("source"):
        lines += [f"Option revue : {spec['source']['option']} (`{spec['source']['options']}`).", ""]
    lines += [f"**Avis : {verdict}** ({sum(f['severity'] == 'haute' for f in open_)} constat(s) haut(s), "
              f"{sum(f['severity'] == 'moyenne' for f in open_)} moyen(s), "
              f"{sum(f['severity'] == 'basse' for f in open_)} bas ouverts ; "
              f"{len(findings) - len(open_)} accepté(s)).", "",
              f"Contrôle par `arch_review.py` ({found['rules']} règles) de la description écrite pour la revue : "
              f"{len(found['comps'])} composants, {len(found['flows'])} flux, {len(scenarios)} scénarios de qualité. "
              "Les points hors de la description sont listés à la fin.", "",
              "## Synthèse", "", "| Axe | Haute | Moyenne | Basse | Acceptés |", "| --- | --- | --- | --- | --- |"]
    for key, name in AXES.items():
        mine = [f for f in findings if f["axis"] == key]
        if key in ("code", "well-architected") and not mine and not found[{"code": "code", "well-architected": "cloud"}[key]]:
            continue
        still = [f for f in mine if not f["accepted"]]
        lines.append(f"| {name} | " + " | ".join(str(sum(f["severity"] == s for f in still)) for s in SEVERITIES)
                     + f" | {len(mine) - len(still)} |")

    lines += ["", "## Arbre d'utilité", ""]
    if not scenarios:
        lines.append("Aucun scénario de qualité.")
    for attr, name in ATTRIBUTES.items():
        mine = [s for s in scenarios.values() if s["attribute"] == attr]
        if not mine:
            continue
        lines += [f"### {name}", "", "| ID | Scénario | Mesure | Importance / difficulté | Exigences | Évaluation |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for s in mine:
            text = s["stimulus"] + (f" ({s['environment']})" if s.get("environment") else "") + f" : {s['response']}"
            weight = f"{s.get('importance', '-')} / {s.get('difficulty', '-')}"
            status = STATUS[s["status"]] + (f" : {s['note']}" if s.get("note") else "")
            lines.append(f"| {s['id']} | {cell(text)} | {cell(s.get('measure', '-'))} | {weight} | "
                         f"{', '.join(s.get('refs', [])) or '-'} | {cell(status)} |")
        lines.append("")
    if lines[-1] == "":
        lines.pop()

    lines += ["", "## Constats", ""]
    if not findings:
        lines.append("Aucun constat.")
    else:
        lines += ["| ID | Règle | Axe | Gravité | Élément | Constat | Correction | Référence | Statut |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for index, f in enumerate(findings, 1):
            status = f"accepté : {f['accepted']}" if f["accepted"] else "à traiter"
            lines.append(f"| C{index:02d} | {f['rule']} | {AXES[f['axis']]} | {f['severity']} | {cell(f['element'])} | "
                         f"{cell(f['message'])} | {cell(f['fix'])} | {cell(f['ref'])} | {cell(status)} |")

    lines += ["", "## Risques", ""]
    if not spec.get("risks"):
        lines.append("Aucun risque noté.")
    else:
        accepted = {f["element"]: f["accepted"] for f in findings if f["rule"] in ("RSK-01", "RSK-03")}
        lines += ["| ID | Risque | Gravité | Scénarios | Atténuation | Responsable | Statut |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        for r in spec["risks"]:
            status = f"accepté : {accepted[r['id']]}" if accepted.get(r["id"]) else "ouvert"
            lines.append(f"| {r['id']} | {cell(r['text'])} | {r['severity']} | {', '.join(r.get('scenarios', [])) or '-'} | "
                         f"{cell(r.get('mitigation', 'à définir'))} | {cell(r.get('owner', 'à désigner'))} | "
                         f"{cell(status)} |")
    if spec.get("sensitivities") or spec.get("tradeoffs"):
        lines += ["", "## Points de sensibilité et compromis", ""]
        for item in spec.get("sensitivities", []):
            where = ", ".join(item.get("components", []) + item.get("scenarios", []))
            lines.append(f"- Sensibilité : {item['text']}" + (f" ({where})" if where else ""))
        for item in spec.get("tradeoffs", []):
            names = " contre ".join(ATTRIBUTES[a] for a in item["attributes"])
            lines.append(f"- Compromis {names} : {item['text']}"
                         + (f" (décision {item['decision']})" if item.get("decision") else " (sans décision)"))
    lines += ["", "## Décisions", ""]
    if not found["decisions"]:
        lines.append("Aucune décision documentée.")
    else:
        lines += ["| ID | Décision | Statut | Exigences | Composants |", "| --- | --- | --- | --- | --- |"]
        for d in found["decisions"].values():
            title = d["title"] + (f" (`{d['file']}`)" if d.get("file") else "")
            lines.append(f"| {d['id']} | {cell(title)} | {DECIDED[d['status']]} | {', '.join(d.get('refs', [])) or '-'} | "
                         f"{', '.join(d.get('components', [])) or '-'} |")
    if found["trace"]:
        lines += ["", "## Traçabilité des exigences", "",
                  "| Exigence | Titre | Priorité | Composants | Décisions | Scénarios |",
                  "| --- | --- | --- | --- | --- | --- |"]
        for req, by in found["trace"]["rows"]:
            lines.append(f"| {req['id']} | {cell(req.get('title', ''))} | {req.get('priority', '-')} | "
                         + " | ".join(", ".join(by.get(k, [])) or "-" for k in ("components", "decisions", "scenarios"))
                         + " |")
    if found["code"]:
        code = found["code"]
        lines += ["", "## Code et architecture", "",
                  f"Graphe du code par graphify (analyse locale du code ; seuls les liens extraits du code comptent) : "
                  f"`{code['graph']}`. "
                  f"{code['files']} fichier(s), dont {code['unmapped']} non rattaché(s) ; "
                  f"{code['dependencies']} dépendance(s) entre composants, dont {len(code['undeclared'])} "
                  "absente(s) de l'architecture."]
        if "repos" in code:
            lines += ["", f"{code['repos']} dépôt(s). Appels entre services lus dans la configuration et les contrats "
                      f"(URL d'un autre service, canaux AsyncAPI) : {len(code['calls'])}.", ""]
            lines += [f"- {cell(c)}" for c in code["calls"]] or ["- aucun"]
            if code["shared_databases"]:
                lines += ["", "Bases citées par plusieurs dépôts :", ""] + [f"- {cell(s)}" for s in code["shared_databases"]]
    lines += ["", "## À vérifier hors de la description", ""]
    lines += [f"- **{k}** : {v}." for k, v in OFF_DESCRIPTION.items()]
    return "\n".join(lines) + "\n"


def list_rules() -> str:
    return "\n".join(f"{rule} {AXES[a]} ({s}) : {title}" for rule, (a, s, title, _, _) in RULES.items())
