"""Coût par parcours utilisateur : la réalisation répartie entre les parcours, poste par poste, avec ses références.

Rattachement d'un lot, dans cet ordre : les parcours qui le citent (`work`), sinon ceux dont un écran
(`screens`) figure dans son nom, sinon ceux qui partagent ses exigences (celles du lot et de son composant),
au prorata du nombre d'exigences communes. Un lot sans parcours (cadrage, recette, mise en production...)
est partagé : réparti au prorata du coût propre de chaque parcours, de même que le pilotage, l'adoption et
l'outillage IA ; les jetons IA suivent le coût IA de chaque lot ; la provision s'applique à chaque parcours.
Pour chaque hypothèse de production, la somme des parcours redonne la réalisation : contrôlé ici, puis à la
relecture de <nom>.parcours.json (schéma : entrée de journeys_view.py dans contract.json).

Utilisé par estimate_build.py (section du chiffrage, <nom>.parcours.json) et journeys_view.py (restitution).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from estimate_common import days, money, pct, plain
from spec_schema import check, input_schema
from text_tools import cell

POSTS = {"front": "Front", "back": "Back", "donnees": "Données", "tests": "Tests", "transverse": "Transverse",
         "pilotage": "Pilotage", "ia": "IA (adoption, outillage, jetons)", "provision": "Provision"}
FRONT = re.compile(r"\b(react|angular|vue|vuetify|svelte|front|frontend|portail|web|mobile|ihm|ecran|ui|spa|"
                   r"cloudfront|maquette)\b")
SHARED_ROWS = {"pilotage": "pilotage", "adoption": "ia", "outillage": "ia"}
VIEWER = Path(__file__).resolve().parent.parent / "journeys_view.py"


def post_of(task: dict, comp: dict | None) -> str:
    """Poste d'un lot : post donné, sinon tiré de la phase et du composant (front reconnu à son nom ou sa techno)."""
    if task.get("post"):
        return task["post"]
    phase = task["phase"]
    if phase == "tests":
        return "tests"
    if phase == "migration" or (comp or {}).get("role") == "db":
        return "donnees"
    if phase in ("realisation", "integration", "conception") and comp:
        text = plain(" ".join(str(comp.get(k, "")) for k in ("label", "tech", "type")) + " " + task["name"])
        return "front" if FRONT.search(text) else "back"
    return "transverse"


def links(spec: dict, comps: dict, known_refs, errors: list[str], warnings: list[str]) -> dict:
    """Pour chaque lot : comment il se rattache (lot, ecran, exigences, partage) et sa part par parcours."""
    journeys = spec["journeys"]
    lot_ids = [w["id"] for w in spec["work"]]
    seen: set[str] = set()
    for index, j in enumerate(journeys):
        where = f"journeys/{index} ({j['id']})"
        if j["id"] in seen:
            errors.append(f"{where} : parcours « {j['id']} » en double")
        seen.add(j["id"])
        known_refs(j["refs"], f"{where}/refs")
        for lot in j.get("work", []):
            if lot not in lot_ids:
                errors.append(f"{where}/work : lot inconnu « {lot} »" + (f" (lots : {', '.join(lot_ids[:12])})"))
        for screen in j.get("screens", []):
            if not any(plain(screen) in plain(w["name"]) for w in spec["work"]):
                warnings.append(f"{where}/screens : aucun lot ne nomme l'écran « {screen} »")
    out = {}
    for task in spec["work"]:
        by_lot = {j["id"]: 1.0 for j in journeys if task["id"] in j.get("work", [])}
        by_screen = {j["id"]: 1.0 for j in journeys
                     if any(plain(s) in plain(task["name"]) for s in j.get("screens", []))}
        refs = set(task.get("refs", [])) | set(comps.get(task.get("component"), {}).get("refs", []))
        by_refs = {j["id"]: float(len(refs & set(j["refs"]))) for j in journeys if refs & set(j["refs"])}
        how, weights = next(((h, w) for h, w in (("lot", by_lot), ("ecran", by_screen), ("exigences", by_refs)) if w),
                            ("partage", {}))
        total = sum(weights.values())
        out[task["id"]] = {"how": how, "shares": {k: v / total for k, v in weights.items()}}
    for j in journeys:
        if not any(j["id"] in x["shares"] for x in out.values()):
            warnings.append(f"parcours {j['id']} sans lot propre : il ne reçoit que des postes partagés ; "
                            "rattacher ses lots (work, screens ou refs)")
    return out


def _spread(values: list[float], total: float, step: float) -> list[float]:
    """Arrondit des valeurs au pas donné en gardant leur somme égale au total arrondi (plus forts restes)."""
    units = [v / step for v in values]
    floor = [int(u // 1) for u in units]
    rest = round(total / step) - sum(floor)
    order = sorted(range(len(units)), key=lambda i: units[i] - floor[i], reverse=True)
    for i in order[:max(rest, 0)]:
        floor[i] += 1
    return [round(f * step, 1) if step < 1 else int(f * step) for f in floor]


def _key(direct: dict[str, list[float]], ids: list[str]) -> dict[str, float]:
    """Clé de répartition des postes partagés : coût propre, sinon jours propres, sinon parts égales."""
    for k in (1, 0):
        total = sum(direct[j][k] for j in ids)
        if total > 0:
            return {j: direct[j][k] / total for j in ids}
    return {j: 1 / len(ids) for j in ids}


def allocate(spec: dict, found: dict, option: dict, known_refs, errors: list[str], warnings: list[str]) -> dict | None:
    """Vue par parcours de toutes les hypothèses ; None sans parcours ou en cas d'erreur."""
    if not spec.get("journeys"):
        return None
    comps = {c["id"]: c for c in option["components"]}
    attach = links(spec, comps, known_refs, errors, warnings)
    if errors:
        return None
    ids = [j["id"] for j in spec["journeys"]]
    tasks = {w["id"]: w for w in spec["work"]}
    lot_post = {w["id"]: post_of(w, comps.get(w.get("component"))) for w in spec["work"]}
    ai = {s["id"]: {x["id"]: x["usd"][1] for x in s["lots"]} for s in (found.get("ai_cost") or {}).get("scenarios", [])}
    priced = spec.get("rates") is not None
    totals, per = [], {j: [] for j in ids}
    spread_share, key0 = 0.0, {}
    for s_index, scen in enumerate(found["scenarios"]):
        rows = scen["rows"]
        lot_cost: dict[str, list[float]] = {}
        for r in rows:
            if r["type"] == "lot":
                acc = lot_cost.setdefault(r["id"], [0.0, 0.0])
                acc[0] += r["days"]
                acc[1] += r["cost"]
        direct = {j: [0.0, 0.0] for j in ids}
        for lot, (d, c) in lot_cost.items():
            for j, share in attach[lot]["shares"].items():
                direct[j][0] += d * share
                direct[j][1] += c * share
        key = _key(direct, ids)
        posts = {j: {p: [0.0, 0.0] for p in POSTS} for j in ids}
        lot_part: dict[str, dict[str, float]] = {}
        for lot, (d, c) in lot_cost.items():
            shares = attach[lot]["shares"] or key
            lot_part[lot] = shares
            for j, share in shares.items():
                posts[j][lot_post[lot]][0] += d * share
                posts[j][lot_post[lot]][1] += c * share
        shared = sum(c for lot, (d, c) in lot_cost.items() if not attach[lot]["shares"])
        lots_j = {j: sum(posts[j][p][1] for p in POSTS) for j in ids}
        lots_d = {j: sum(posts[j][p][0] for p in POSTS) for j in ids}
        key2 = _key({j: [lots_d[j], lots_j[j]] for j in ids}, ids)
        tokens = ai.get(scen["id"], {})
        for r in rows:
            amount = r["cost"] if isinstance(r["cost"], (int, float)) else 0.0
            span = r["days"] if isinstance(r["days"], (int, float)) else 0.0
            if r["type"] in SHARED_ROWS:
                for j in ids:
                    posts[j][SHARED_ROWS[r["type"]]][0] += span * key2[j]
                    posts[j][SHARED_ROWS[r["type"]]][1] += amount * key2[j]
                shared += amount
            elif r["type"] == "jetons":
                weight = sum(tokens.values())
                for lot, usd in tokens.items():
                    for j, share in lot_part.get(lot, key2).items():
                        posts[j]["ia"][1] += amount * (usd / weight if weight else 0) * share
                if not weight:
                    for j in ids:
                        posts[j]["ia"][1] += amount * key2[j]
                shared += amount
        contingency = scen["scenario"].get("contingency", spec.get("contingency", 0)) / 100
        for j in ids:
            posts[j]["provision"][1] = sum(posts[j][p][1] for p in POSTS if p != "provision") * contingency
        build = scen["build"]
        cost_f = [sum(posts[j][p][1] for p in POSTS) for j in ids]
        days_f = [sum(posts[j][p][0] for p in POSTS) for j in ids]
        if abs(sum(cost_f) - build["cost"]) > 1 or abs(sum(days_f) - build["days"]) > 0.1:
            errors.append(f"parcours, {scen['name']} : somme des parcours {round(sum(cost_f))} ({days(sum(days_f))} j) "
                          f"au lieu de la réalisation {build['cost']} ({days(build['days'])} j)")
            return None
        if s_index == 0:
            key0 = key
            base = sum(cost_f) or sum(days_f) or 1
            spread_share = (shared * (1 + contingency) if sum(cost_f) else
                            sum(d for lot, (d, c) in lot_cost.items() if not attach[lot]["shares"])) / base
        cost_r, days_r = _spread(cost_f, build["cost"], 1), _spread(days_f, build["days"], 0.1)
        totals.append({"id": scen["id"], "name": scen["name"], "days": build["days"], "cost": build["cost"]})
        for n, j in enumerate(ids):
            names = list(POSTS)
            pc = _spread([posts[j][p][1] for p in names], cost_r[n], 1)
            pd = _spread([posts[j][p][0] for p in names], days_r[n], 0.1)
            per[j].append({"id": scen["id"], "days": days_r[n], "cost": cost_r[n],
                           "share": round(cost_r[n] / build["cost"], 3) if build["cost"] else
                           round(days_r[n] / build["days"], 3) if build["days"] else 0.0,
                           "posts": {p: {"days": pd[i], "cost": pc[i]} for i, p in enumerate(names)
                                     if pd[i] or pc[i]}})
    large = set(found.get("challenge", {}).get("large", []))
    view = {"title": spec.get("title") or "Chiffrage", "option": option["id"],
            "currency": spec.get("currency", "€") if priced else None, "scenarios": totals,
            "spread": round(spread_share, 3), "refs": shared_refs(spec, found), "journeys": []}
    for j in spec["journeys"]:
        own = [(lot, a) for lot, a in attach.items() if j["id"] in a["shares"]]
        lots = [{"id": lot, "name": tasks[lot]["name"], "post": lot_post[lot], "how": a["how"],
                 "share": round(a["shares"][j["id"]], 3), "refs": sorted(set(tasks[lot].get("refs", [])) |
                                                                         set(comps.get(tasks[lot].get("component"), {}).get("refs", []))),
                 **({"note": tasks[lot]["note"]} if tasks[lot].get("note") else {})} for lot, a in own]
        lots += [{"id": lot, "name": tasks[lot]["name"], "post": lot_post[lot], "how": "partage",
                  "share": round(key0[j["id"]], 3), "refs": tasks[lot].get("refs", [])}
                 for lot, a in attach.items() if not a["shares"]]
        touched = [comps[tasks[lot]["component"]] for lot, _ in own if tasks[lot].get("component") in comps]
        checks = [f"estimation incertaine : {lot}" for lot, _ in own if lot in found.get("uncertain", [])]
        checks += [f"lot trop gros : {lot}" for lot, _ in own if lot in large]
        checks += [f"exigence sans lot : {r}" for r in j["refs"] if r in found.get("unestimated", [])]
        touched = list({c["id"]: c for c in touched}.values())
        auto = [f"intégration avec {c['label']}" for c in touched if c.get("role") == "external"]
        first = per[j["id"]][0]
        own_cost = sum(v["cost"] for k, v in first["posts"].items() if k in ("front", "back", "donnees"))
        if first["cost"] and own_cost < first["cost"] / 2:
            checks.append(f"postes partagés : plus de la moitié du coût ({pct(1 - own_cost / first['cost'])})")
        view["journeys"].append({
            "id": j["id"], "title": j["title"], **({"persona": j["persona"]} if j.get("persona") else {}),
            "refs": j["refs"], "path": j.get("path", []),
            "components": [c["label"] for c in touched],
            "lots": lots, "scenarios": per[j["id"]],
            "attention": {"risks": j.get("risks", []), "assumptions": j.get("assumptions", []),
                          "dependencies": j.get("dependencies", []) + [a for a in auto if a not in
                                                                         j.get("dependencies", [])],
                          "checks": checks}})
    return view


def shared_refs(spec: dict, found: dict) -> dict:
    """Références des postes sans lot : pilotage, provision, coût IA."""
    refs = {"pilotage": ", ".join(f"{o['id']} {o['name']} {o['percent']:g} %" for o in spec.get("overheads", [])),
            "provision": f"{spec.get('contingency', 0):g} % de la réalisation"}
    ai = found.get("ai_cost")
    if ai:
        refs["ia"] = f"adoption et outillage (hypotheses-ia.json), jetons : grille du {ai['checked']}, fiabilité {ai['confidence']}"
    return refs


def _lot_ref(item: dict) -> str:
    detail = ", ".join(item["refs"])
    if item.get("note"):
        detail += (" ; " if detail else "") + item["note"][:70]
    share = ("réparti " if item["how"] == "partage" else "") + pct(item["share"])
    how = {"lot": "", "ecran": "écran, ", "exigences": "", "partage": ""}[item["how"]]
    return f"{item['id']} {item['name']} ({how}{detail + ' ; ' if detail else ''}{share})"


def markdown(view: dict) -> list[str]:
    """Section « Coût par parcours utilisateur » du chiffrage (montants, ou jours sans taux)."""
    cur, scen = view["currency"], view["scenarios"]
    value = (lambda v: money(v["cost"], cur)) if cur else (lambda v: f"{days(v['days'])} j")
    out = ["## Coût par parcours utilisateur", "",
           "Un lot va au parcours qui le cite (work), sinon à ceux dont il porte un écran ou des exigences, au "
           "prorata des exigences communes ; les postes partagés (lots sans parcours, pilotage, provision, IA) "
           f"sont répartis au prorata du coût propre de chaque parcours ({pct(view['spread'])} de la réalisation "
           "sans IA). La somme des parcours redonne la réalisation de chaque hypothèse : contrôlé par le script.", "",
           "| Parcours | " + " | ".join(s["name"] for s in scen) + " | Part |", "| --- " * (len(scen) + 2) + "|"]
    for j in view["journeys"]:
        out.append(f"| {j['id']} {cell(j['title'])} | " + " | ".join(value(s) for s in j["scenarios"])
                   + f" | {pct(j['scenarios'][0]['share'])} |")
    out += ["| **Total** | " + " | ".join(f"**{value(s)}**" for s in scen) + " | 100 % |", ""]
    for j in view["journeys"]:
        out += [f"### {j['id']}. {j['title']}", ""]
        head = [f"Persona : {j['persona']}"] if j.get("persona") else []
        line = " ; ".join(head + [f"exigences : {', '.join(j['refs'])}"])
        out += [line[0].upper() + line[1:] + ".", "",
                "| Poste | " + (f"Jours ({scen[0]['name'][0].lower() + scen[0]['name'][1:]}) | " if cur else "")
                + " | ".join(s["name"] for s in scen) + " | Références |", "| --- " * (len(scen) + 2 + bool(cur)) + "|"]
        for post, label in POSTS.items():
            cells = [s["posts"].get(post) if s["posts"].get(post, {}).get("cost" if cur else "days") else None
                     for s in j["scenarios"]]
            if not any(cells):
                continue
            refs = [_lot_ref(x) for x in j["lots"] if x["post"] == post] or [view["refs"].get(post, "")]
            span = (cells[0] or {}).get("days", 0)
            out.append(f"| {label} | " + (f"{days(span) if span else ''} | " if cur else "")
                       + " | ".join(value(c) if c else "" for c in cells) + f" | {cell('<br>'.join(refs))} |")
        points = attention(j)
        out += [""] + ([f"- {cell(p)}" for p in points] if points else []) + [""]
    return out


def attention(j: dict) -> list[str]:
    a = j["attention"]
    return ([f"Risque : {x}" for x in a["risks"]] + [f"Hypothèse : {x}" for x in a["assumptions"]]
            + [f"Dépendance : {x}" for x in a["dependencies"]] + [f"À vérifier : {x}" for x in a["checks"]])


def verify(path: Path) -> list[str]:
    """Relit <nom>.parcours.json : schéma (entrée de journeys_view.py) et somme des parcours par hypothèse."""
    try:
        view = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        return [f"{path.name} illisible : {error}"]
    invalid = check(view, input_schema(VIEWER) or {})
    if invalid:
        return [f"{path.name} : {e}" for e in invalid[:10]]
    return sums(view, path.name)


def sums(view: dict, name: str) -> list[str]:
    errors = []
    for index, total in enumerate(view["scenarios"]):
        got = [j["scenarios"][index] for j in view["journeys"]]
        cost, span = sum(x["cost"] for x in got), round(sum(x["days"] for x in got), 1)
        if cost != total["cost"] or abs(span - total["days"]) > 0.05:
            errors.append(f"{name} : {total['name']}, somme des parcours {cost} ({days(span)} j) au lieu de "
                          f"{total['cost']} ({days(total['days'])} j)")
        for j, x in zip(view["journeys"], got):
            if sum(p["cost"] for p in x["posts"].values()) != x["cost"]:
                errors.append(f"{name} : {j['id']}, {total['name']} : postes de somme différente du parcours")
    return errors
