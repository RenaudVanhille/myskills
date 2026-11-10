"""Livrables du chiffrage : Markdown, plan de charge, hypothèses, CSV et leur relecture (estimate_build.py)."""
from __future__ import annotations

import csv
from pathlib import Path
from estimate_common import COMPLEXITY, PHASES, days, money, pct
from text_tools import cell


def render_challenge(found: dict) -> list[str]:
    """Section du chiffrage : réemploi et points à challenger, avec les seuils utilisés."""
    ch, reuse = found["challenge"], found["reuse"]
    m, lim = ch["margin"], ch["limits"]
    origin = "abaques fournis" if ch["calibrated"] else "par défaut, à calibrer"
    out = ["## Points à challenger", "", f"Seuils : {origin}.", "", "| Indicateur | Valeur | Seuil |", "| --- | --- | --- |",
           f"| Marges cumulées (pilotage {days(m['pilotage'])} %, provision {days(m['contingency'])} %, maxima des "
           f"trois points {days(m['skew'])} %) | {days(m['total'])} % | {lim['max_margin']:g} % |",
           f"| Part de la réalisation et de l'intégration | {pct(ch['realisation_share'])} | "
           f"au moins {pct(lim['realisation_min_share'])} |",
           f"| Lots de plus de {lim['max_lot_days']:g} j | {', '.join(ch['large']) or 'aucun'} | 0 |",
           f"| Lots semblables sans réemploi | {', '.join('/'.join(p) for p in ch['similar'][:10]) or 'aucun'} | 0 |",
           f"| Taux de réemploi | {pct(reuse['rate'])} ({days(reuse['saved_days'])} j sur {days(reuse['gross_days'])} j bruts) | |"]
    if ch["days_per_requirement"] is not None:
        span = lim.get("days_per_requirement")
        out.append(f"| Jours de lots par exigence retenue | {days(ch['days_per_requirement'])} | "
                   f"{f'{span[0]:g} à {span[1]:g}' if span else 'non fixé'} |")
    out.append("")
    out += [f"- {cell(p)}" for p in ch["points"]] or ["Aucun point au-delà des seuils."]
    if reuse["items"]:
        out += ["", "### Réemploi", "", "| Lot | Réutilise | Part | Jours épargnés | Base |", "| --- | --- | --- | --- | --- |"]
        out += [f"| {r['id']} | {r['from'] or 'existant'} | {r['percent']:g} % | {days(r['saved'])} | {cell(r['basis'])} |"
                for r in reuse["items"]]
    return out + [""]


def render_hosting(spec: dict, found: dict, providers: dict) -> list[str]:
    host, cur = found["totals"]["hosting"], spec.get("currency", "€")
    if not host:
        return []
    out = ["## Hébergement", ""]
    if host["required"]:
        out += [f"Qualifications exigées : {', '.join(host['required'])}"
                + (f" ({', '.join(spec['hosting']['refs'])})" if spec.get("hosting", {}).get("refs") else "") + ".", ""]
    out += ["| Hébergeur | Juridiction | Qualifications | Par an | Ponctuel | Note |", "| --- | --- | --- | --- | --- | --- |"]
    for name, total in host["providers"].items():
        info = providers.get(name, {"name": "non précisé", "jurisdiction": "", "qualifications": []})
        quals = (", ".join(info["qualifications"]) or "aucune") + (f" (en cours : {', '.join(info['pending'])})"
                                                                   if info.get("pending") else "")
        out.append(f"| {info['name']} | {info['jurisdiction']} | {quals} | {money(total['annual'], cur)} | "
                   f"{money(total['one_time'], cur)} | {cell(info.get('note', ''))} |")
    out += ["", "Lignes non conformes aux qualifications exigées : "
            + (", ".join(host["noncompliant"]) if host["noncompliant"] else "aucune") + ".",
            f"Qualifications selon le catalogue des hébergeurs vérifié le {host['checked'] or 'non daté'} : "
            "une qualification porte sur une offre, à confirmer sur la liste de l'ANSSI.", ""]
    return out


def render_scenarios(spec: dict, found: dict) -> list[str]:
    """Comparaison des trois hypothèses de production, facteurs par phase et base de chaque hypothèse."""
    cur, items = spec.get("currency", "€"), found["scenarios"]
    if not items:
        return []
    horizon = found["totals"]["tco"]["years"]
    head = "| Poste | " + " | ".join(i["name"] for i in items) + " |"
    rule = "| --- |" + " --- |" * len(items)

    def row(label: str, value) -> str:
        return f"| {label} | " + " | ".join(value(i) for i in items) + " |"

    out = ["## Hypothèses de production", "",
           "Même périmètre chiffré trois fois : sans IA (charges saisies), avec IA (développement assisté) et "
           "dev IA natif (agents qui écrivent le code, l'équipe spécifie et valide). Les gains réduisent la charge "
           "et sont eux-mêmes incertains (incertitude sur le gain, commune à tous les lots, ajoutée à la fourchette) : "
           "ils restent à confirmer sur un lot pilote.", "", head, rule,
           row("Réalisation, charge", lambda i: f"{days(i['build']['days'])} j ({days(i['build']['days_low'])} à "
                                                f"{days(i['build']['days_high'])})"),
           row("Réalisation, coût", lambda i: f"{money(i['build']['cost'], cur)} ({money(i['build']['cost_low'], cur)}"
                                              f" à {money(i['build']['cost_high'], cur)})"),
           row("dont adoption de l'IA", lambda i: money(i["build"]["setup"], cur)),
           row("dont outillage IA (licences, jetons)", lambda i: money(i["build"]["tooling"], cur)),
           row("Run par an", lambda i: money(i["run"]["annual"], cur)),
           row("Fonctionnement par mois", lambda i: money(i["operate"]["monthly"], cur)),
           row(f"**Coût total sur {years(horizon)}**", lambda i: f"**{money(i['tco']['total'], cur)}**"),
           row("Écart avec sans IA", lambda i: "référence" if i["id"] == "sans-ia"
               else f"{i['delta']:+.1f} %".replace(".", ","))]
    if spec.get("budget"):
        out.append(row("Budget", lambda i: ("dépassé : " + ", ".join(i["budget_over"])) if i["budget_over"] else "tenu"))
    phases = [p for p in PHASES if any(line["phase"] == p for line in found["lines"] if line["type"] == "lot")]
    out += ["", "### Facteurs appliqués à la charge sans IA", "",
            "| Phase | " + " | ".join(i["name"] for i in items[1:]) + " |", "| --- |" + " --- |" * (len(items) - 1)]
    out += [f"| {PHASES[p]} | " + " | ".join(num(i["scenario"]["factors"].get(p, 1)) for i in items[1:]) + " |"
            for p in phases]
    for label, key, fmt in (("Incertitude sur le gain (écart type relatif)", "gain_uncertainty", num),
                            ("Adoption, % de la charge des lots", "setup_percent", num),
                            (f"Outillage IA par jour travaillé ({cur})", "tooling_per_day", num),
                            ("Facteur du run", "run_factor", num)):
        out.append(f"| {label} | " + " | ".join(fmt(i["scenario"].get(key, 0 if key in ("setup_percent", "tooling_per_day", "gain_uncertainty") else 1))
                                              for i in items[1:]) + " |")
    lots = [t for t in spec["work"] if t.get("ai")]
    if lots:
        out += ["", "Facteurs propres à un lot : " + " ; ".join(
            f"{t['id']} " + ", ".join(f"{k} {num(v)}" for k, v in t["ai"].items())
            + (f" ({cell(t['note'])})" if t.get("note") else "") for t in lots) + "."]
    out += [""] + [f"- **{i['name']}** : {cell(i['scenario']['description'])} Base : {cell(i['scenario']['basis'])}"
                   + (f" (valeurs du projet : {', '.join(i['scenario']['own'])})" if i["scenario"]["own"] else "")
                   + "." for i in items] + [""]
    return out


def render_md(spec: dict, option: dict, status: str, found: dict, providers: dict) -> str:
    cur, t = spec.get("currency", "€"), found["totals"]
    build, horizon = t["build"], t["tco"]["years"]
    out = [f"# {spec.get('title') or 'Chiffrage'}", ""]
    if spec.get("context"):
        out += [spec["context"], ""]
    out += [f"Option {option['id']} : {option['name']}, {status}. Fourchette P10-P90 calculée sur les "
            "estimations à trois points (lots indépendants). Prix d'infrastructure : hypothèses saisies "
            "avec leur base, aucun tarif consulté en ligne.", "",
            "## Synthèse", "", "| Poste | Montant |", "| --- | --- |",
            f"| Réalisation, charge | {days(build['days'])} j (de {days(build['days_low'])} à {days(build['days_high'])} j) |",
            f"| Réalisation, coût | {money(build['cost'], cur)} (de {money(build['cost_low'], cur)} à "
            f"{money(build['cost_high'], cur)}), dont provision {money(build['contingency'], cur)} |",
            f"| Infrastructure ponctuelle | {money(t['infra']['one_time'], cur)} |",
            f"| Infrastructure récurrente | {money(t['infra']['annual'], cur)} par an "
            f"({money(t['infra']['monthly'], cur)} par mois) |",
            f"| Maintenance et exploitation | {money(t['run']['annual'], cur)} par an |",
            f"| Fonctionnement (infrastructure et run) | {money(t['operate']['monthly'], cur)} par mois |",
            f"| **Coût total sur {years(horizon)}** | **{money(t['tco']['total'], cur)}** |", ""]
    budget = spec.get("budget")
    if budget:
        values = {"build": build["cost"], "monthly": t["operate"]["monthly"], "tco": t["tco"]["total"]}
        labels = {"build": "Réalisation", "monthly": "Fonctionnement par mois", "tco": f"Coût total sur {years(horizon)}"}
        out += ["### Budget", "", "| Poste | Budget | Chiffré | Écart |", "| --- | --- | --- | --- |"]
        for key in ("build", "monthly", "tco"):
            if key in budget:
                gap = values[key] - budget[key]
                verdict = f"dépassé de {money(gap, cur)}" if gap > 0 else "tenu"
                out.append(f"| {labels[key]} | {money(budget[key], cur)} | {money(values[key], cur)} | {verdict} |")
        if budget.get("refs"):
            out.append(f"\nExigences : {', '.join(budget['refs'])}.")
        out.append("")

    out += render_scenarios(spec, found)
    tasks = [line for line in found["lines"] if line["type"] == "lot"]
    out += ["## Réalisation par lot", "",
            "| Lot | Phase | Composant | Exigences | Profil | Mini | Probable | Maxi | Espérés | Coût |",
            "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
    for line in tasks:
        out.append(f"| {line['id']} {cell(line['name'])} | {PHASES[line['phase']]} | {line['component']} | "
                   f"{', '.join(line['refs'])} | {line['profile']} | {days(line['low'])} | {days(line['likely'])} | "
                   f"{days(line['high'])} | {days(line['days'])} | {money(line['cost'], cur)} |")
    for line in (x for x in found["lines"] if x["type"] == "pilotage"):
        out.append(f"| {line['id']} {cell(line['name'])} | Pilotage |  |  | {line['profile']} | "
                   f"{line['percent']} % |  |  | {days(line['days'])} | {money(line['cost'], cur)} |")
    out.append("")

    by_phase: dict[str, list[float]] = {}
    by_profile: dict[str, list[float]] = {}
    for line in found["lines"]:
        by_phase.setdefault(line["phase"], [0.0, 0.0])
        by_profile.setdefault(line["profile"], [0.0, 0.0])
        for target in (by_phase[line["phase"]], by_profile[line["profile"]]):
            target[0] += line["days"]
            target[1] += line["cost"]
    out += ["### Par phase", "", "| Phase | Jours | Coût |", "| --- | --- | --- |"]
    out += [f"| {PHASES[k]} | {days(v[0])} | {money(v[1], cur)} |" for k, v in
            sorted(by_phase.items(), key=lambda kv: list(PHASES).index(kv[0]))]
    out += ["", "### Par profil", "", "| Profil | Taux journalier | Jours | Coût |", "| --- | --- | --- | --- |"]
    out += [f"| {k} | {money(spec['rates'][k], cur)} | {days(v[0])} | {money(v[1], cur)} |"
            for k, v in by_profile.items()]
    if build["contingency"]:
        out += ["", f"Provision pour risques : {spec['contingency']} % du coût de réalisation, "
                f"{money(build['contingency'], cur)}."]
    out.append("")

    if found["infra"]:
        out += ["## Infrastructure", "",
                "| Ligne | Composant | Hébergeur | Environnement | Nature | Quantité | Prix unitaire | Période | Par an | Ponctuel | Base du prix |",
                "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for item in found["infra"]:
            out.append(f"| {item['id']} {cell(item['name'])} | {item.get('component', '')} | {item.get('host', '')} | "
                       f"{item.get('environment', 'production')} | {item['kind']} | {item.get('quantity', 1)} | "
                       f"{money(item['unit_cost'], cur)} | {item['period']} | {money(item['annual'], cur)} | "
                       f"{money(item['one_time'], cur)} | {cell(item['basis'])} |")
        out.append("")
    out += render_hosting(spec, found, providers)
    if found["run"]:
        out += ["## Maintenance et exploitation", "", "| Poste | Base | Par an |", "| --- | --- | --- |"]
        for item in found["run"]:
            base = (f"{days(item['days_per_year'])} j par an, {item['profile']}" if "days_per_year" in item
                    else f"{item['percent_of_build']} % de la réalisation hors provision")
            out.append(f"| {item['id']} {cell(item['name'])} | {base} | {money(item['annual'], cur)} |")
        out.append("")

    yearly = t["infra"]["annual"] + t["run"]["annual"]
    out += [f"## Coût total sur {years(horizon)}", "", "| Année | Réalisation | Infrastructure | Run | Total |",
            "| --- | --- | --- | --- | --- |",
            f"| 0 | {money(build['cost'], cur)} | {money(t['infra']['one_time'], cur)} |  | "
            f"{money(build['cost'] + t['infra']['one_time'], cur)} |"]
    out += [f"| {year} |  | {money(t['infra']['annual'], cur)} | {money(t['run']['annual'], cur)} | "
            f"{money(yearly, cur)} |" for year in range(1, horizon + 1)]
    out += [f"| **Total** | | | | **{money(t['tco']['total'], cur)}** |", ""]

    out += render_challenge(found)
    out += ["## Couverture", ""]
    out.append("- Exigences retenues qu'aucun lot ne porte : "
               + (", ".join(found["unestimated"]) if found["unestimated"] else "aucune") + ".")
    out.append("- Composants de l'option sans lot ni ligne d'infrastructure : "
               + (", ".join(found["uncovered"]) if found["uncovered"] else "aucun") + ".")
    if found["uncertain"]:
        out.append(f"- Estimations très incertaines : {', '.join(found['uncertain'])}.")
    out.append("")
    for key, label in (("assumptions", "Hypothèses"), ("exclusions", "Exclusions")):
        if spec.get(key):
            out += [f"## {label}", ""] + [f"- {cell(x)}" for x in spec[key]] + [""]
    return "\n".join(out)


CSV_HEAD = ["type", "id", "libellé", "phase", "composant", "profil", "mini", "probable", "maxi", "jours",
            "taux", "par an", "ponctuel", "coût réalisation", "exigences", "base", "hébergeur"]


def num(value) -> str:
    """Nombre du CSV avec la virgule décimale (séparateur point-virgule, tableurs en français)."""
    return value if isinstance(value, str) else str(round(value, 2)).replace(".", ",").removesuffix(",0")


def csv_rows(found: dict) -> list[list]:
    rows = [CSV_HEAD]
    for line in found["lines"]:
        rows.append([line["type"], line["id"], line["name"], line["phase"], line["component"], line["profile"],
                     line["low"], line["likely"], line["high"], line["days"], line["rate"], 0, 0,
                     line["cost"], " ".join(line["refs"]), "", ""])
    for item in found["infra"]:
        rows.append(["infra", item["id"], item["name"], "", item.get("component", ""), "", "", "", "", "",
                     item["unit_cost"], item["annual"], item["one_time"], 0, "", item["basis"], item.get("host", "")])
    for item in found["run"]:
        rows.append(["run", item["id"], item["name"], "", "", item.get("profile", ""), "", "", "",
                     item.get("days_per_year", ""), item.get("rate", ""), item["annual"], 0, 0, "", "", ""])
    return [[num(v) if isinstance(v, (int, float)) else v for v in row] for row in rows]


def hrs(value: float, per_day: float) -> str:
    return f"{round(value * per_day):,}".replace(",", " ")


def render_charges(spec: dict, option: dict, status: str, found: dict) -> str:
    """Plan de charge sans montant : tâches, complexité, jours et heures, par hypothèse de production."""
    ch, scen = found["charges"], found["scenarios"]
    per_day = ch["hours_per_day"]
    names = [x["name"] for x in scen[1:]]
    out = [f"# Charges : {spec.get('title') or 'Chiffrage'}", ""]
    if spec.get("context"):
        out += [spec["context"], ""]
    out += [f"Option {option['id']} : {option['name']}, {status}. Charges en jours et en heures ({num(per_day)} h "
            "par jour), sans taux journalier : la valorisation se fait à part. Fourchette P10-P90 calculée sur les "
            "estimations à trois points.", "", "## Synthèse", "",
            "| Hypothèse | Jours | Fourchette P10-P90 | Heures |", "| --- | --- | --- | --- |"]
    out += [f"| {x['name']} | {days(x['days'])} | {days(x['days_low'])} à {days(x['days_high'])} | {hrs(x['days'], per_day)} |"
            for x in ch["scenarios"]]
    out += ["", f"{ch['tasks']} tâches : " + ", ".join(f"{n} {COMPLEXITY[c].lower()}" for c, n in ch["by_complexity"].items()
                                                        if n) + "."]
    if ch["run_days_per_year"]:
        out.append(f"Maintenance et exploitation : {days(ch['run_days_per_year'])} j par an sans IA "
                   f"({hrs(ch['run_days_per_year'], per_day)} h).")
    out += ["", "## Détail par tâche", "",
            "| Tâche | Phase | Composant | Complexité | Profil | Mini | Probable | Maxi | Jours | Heures | "
            + " | ".join(f"{n} (j)" for n in names) + " |", "| --- " * (10 + len(names)) + "|"]
    for row in charge_rows(found):
        if row["type"] == "adoption":
            continue
        complexity = COMPLEXITY.get(row["complexity"], "") + (" (déduite)" if row.get("deduced") else "")
        out.append(f"| {row['id']} {cell(row['name'])} | {PHASES.get(row['phase'], '')} | {row['component']} | "
                   f"{complexity} | {row['profile']} | {days(row['low']) if row['low'] != '' else ''} | "
                   f"{days(row['likely']) if row['likely'] != '' else str(row.get('percent', '')) + ' %'} | "
                   f"{days(row['high']) if row['high'] != '' else ''} | {days(row['days'])} | {hrs(row['days'], per_day)} | "
                   + " | ".join(days(v) for v in row["by_scenario"][1:]) + " |")
    setup = [next((r["days"] for r in x["rows"] if r["type"] == "adoption"), 0) for x in scen]
    if any(setup):
        out.append("| Adoption de l'IA : outillage, garde-fous, formation |  |  |  |  |  |  |  |  |  | "
                   + " | ".join(days(v) for v in setup[1:]) + " |")
    for label, key in (("Par phase", "phase"), ("Par profil", "profile")):
        groups: dict[str, list[float]] = {}
        for row in charge_rows(found):
            if row["type"] != "adoption":
                acc = groups.setdefault(row[key], [0.0] * len(scen))
                for i, v in enumerate(row["by_scenario"]):
                    acc[i] += v
        out += ["", f"### {label}", "", f"| {label[4:].capitalize()} | Jours | Heures | " + " | ".join(f"{n} (j)" for n in names)
                + " |", "| --- " * (3 + len(names)) + "|"]
        out += [f"| {PHASES.get(k, k)} | {days(v[0])} | {hrs(v[0], per_day)} | " + " | ".join(days(x) for x in v[1:]) + " |"
                for k, v in groups.items()]
    out.append("")
    out += render_challenge(found)
    for key, label in (("assumptions", "Hypothèses"), ("exclusions", "Exclusions")):
        if spec.get(key):
            out += [f"## {label}", ""] + [f"- {cell(x)}" for x in spec[key]] + [""]
    return "\n".join(out)


def charge_rows(found: dict) -> list[dict]:
    """Lignes de charge (tâche par profil, pilotage, adoption) avec leurs jours dans chaque hypothèse."""
    scen = found["scenarios"]
    rows = []
    for index, line in enumerate(x for x in found["lines"] if x["type"] in ("lot", "pilotage")):
        mine = [[r for r in x["rows"] if r["type"] in ("lot", "pilotage")][index]["days"] for x in scen]
        rows.append({**line, "complexity": line.get("complexity") or "", "by_scenario": mine})
    setup = [next((r["days"] for r in x["rows"] if r["type"] == "adoption"), 0.0) for x in scen]
    if any(setup):
        rows.append({"type": "adoption", "id": "A", "name": "Adoption de l'IA", "phase": "", "component": "",
                     "complexity": "", "profile": "", "low": "", "likely": "", "high": "", "days": 0.0,
                     "by_scenario": setup})
    return rows


CHARGE_HEAD = ["type", "id", "tâche", "phase", "composant", "complexité", "profil", "mini", "probable", "maxi",
               "jours", "heures"]


def charge_csv(found: dict) -> list[list]:
    per_day, scen = found["charges"]["hours_per_day"], found["scenarios"]
    rows = [CHARGE_HEAD + [f"jours {x['id']}" for x in scen[1:]]]
    for r in charge_rows(found):
        rows.append([r["type"], r["id"], r["name"], r["phase"], r["component"], r["complexity"], r["profile"],
                     r["low"], r["likely"], r["high"], r["days"], r["days"] * per_day] + r["by_scenario"][1:])
    return [[num(v) if isinstance(v, (int, float)) else v for v in row] for row in rows]


def verify_charges(path: Path, found: dict) -> list[str]:
    """Relit le CSV des charges : chaque colonne de jours redonne la charge de son hypothèse."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    errors = []
    for item in found["scenarios"]:
        column = "jours" if item["id"] == "sans-ia" else f"jours {item['id']}"
        got = sum(float(r[column].replace(",", ".") or 0) for r in rows)
        if abs(got - item["build"]["days"]) > 0.2:
            errors.append(f"{path.name} : {item['id']}, total {round(got, 1)} j au lieu de {item['build']['days']}")
    return errors


SCENARIO_HEAD = ["hypothèse", "type", "id", "libellé", "phase", "profil", "facteur", "jours", "taux",
                 "coût réalisation", "par an"]


def scenario_rows(found: dict) -> list[list]:
    rows = [SCENARIO_HEAD]
    for item in found["scenarios"]:
        rows += [[item["id"], r["type"], r["id"], r["name"], r["phase"], r["profile"], r["factor"], r["days"],
                  r["rate"], r["cost"], r["annual"]] for r in item["rows"]]
    return [[num(v) if isinstance(v, (int, float)) else v for v in row] for row in rows]


def verify_scenarios(path: Path, found: dict, spec: dict) -> list[str]:
    """Relit le CSV des hypothèses : chaque hypothèse redonne sa réalisation et son run."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    errors = []
    for item in found["scenarios"]:
        mine = [r for r in rows if r["hypothèse"] == item["id"]]
        contingency = item["scenario"].get("contingency", spec.get("contingency", 0)) / 100
        build = sum(float(r["coût réalisation"].replace(",", ".") or 0) for r in mine) * (1 + contingency)
        annual = sum(float(r["par an"].replace(",", ".") or 0) for r in mine)
        for label, got, want in (("réalisation", build, item["build"]["cost"]), ("run", annual, item["run"]["annual"])):
            if abs(got - want) > 1:
                errors.append(f"{path.name} : {item['id']}, total {label} {round(got)} au lieu de {want}")
    return errors


def verify_csv(path: Path, totals: dict, contingency: float) -> list[str]:
    """Relit le CSV écrit et vérifie que ses montants redonnent les totaux du rapport."""
    with open(path, encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter=";"))
    def total(column: str) -> float:
        return sum(float(r[column].replace(",", ".") or 0) for r in rows)

    build, annual, once = total("coût réalisation") * (1 + contingency), total("par an"), total("ponctuel")
    expected = (totals["build"]["cost"], totals["infra"]["annual"] + totals["run"]["annual"],
                totals["infra"]["one_time"])
    labels = ("réalisation", "par an", "ponctuel")
    return [f"{path.name} : total {label} {round(got)} au lieu de {want}"
            for label, got, want in zip(labels, (build, annual, once), expected) if abs(got - want) > 1]


def years(horizon) -> str:
    """Durée accordée : 1 an, 3 ans."""
    return f"{horizon} an" + ("s" if horizon >= 2 else "")
