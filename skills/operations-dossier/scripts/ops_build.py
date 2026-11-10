# /// script
# requires-python = ">=3.10"
# ///
"""Écrit et contrôle le dossier d'exploitation d'une solution : engagements, supervision, sauvegardes, astreinte, fiches réflexes.

Le modèle décrit les services et leurs engagements (disponibilité, RPO, RTO),
les alertes, les sauvegardes, l'astreinte et les fiches réflexes (runbooks).
Le script, et non le modèle :

- vérifie les références (service, fiche, niveau d'astreinte, exigence) et
  propose le nom proche ;
- calcule le budget d'indisponibilité de chaque service (minutes par
  fenêtre, tirées de sa disponibilité cible) et le compare à son RTO ;
- confronte chaque sauvegarde au RPO de son service (erreur si elle est
  moins fréquente que le RPO) ;
- relève les trous de couverture (règles OPS-xx) : service critique sans
  engagement, sans alerte ou sans fiche réflexe, alerte sans fiche,
  restauration jamais testée, astreinte en heures ouvrées pour un service
  très disponible, exigence d'exploitation portée par aucun service ;
- écrit <nom>.md : le dossier d'exploitation, points ouverts compris.

    uv run scripts/ops_build.py EXPLOITATION.json [--out-dir DOSSIER] [--strict] | --schema

Une référence inconnue ou une sauvegarde incompatible avec le RPO est une
erreur : rien n'est écrit. Un trou de couverture est un constat (`findings`),
écrit dans le dossier ; avec --strict, un constat de gravité haute donne le
code 1.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402
from text_tools import cell, near  # noqa: E402

SEVERITIES = ("haute", "moyenne", "basse")
RULES = {
    "OPS-01": ("haute", "Service critique sans engagement de disponibilité",
               "Donner slo.availability (repris de l'exigence de disponibilité) ou baisser sa criticité."),
    "OPS-02": ("haute", "Service critique sans alerte critique",
               "Ajouter dans monitoring une alerte de gravité critique sur le signal qui montre la panne."),
    "OPS-03": ("haute", "Alerte critique ou majeure sans fiche réflexe",
               "Écrire la fiche (runbooks) et la citer dans runbook : celui qui est réveillé sait quoi faire."),
    "OPS-04": ("haute", "Service avec RPO mais sans sauvegarde",
               "Décrire la sauvegarde du service (backups) ou retirer le RPO s'il ne garde aucune donnée."),
    "OPS-05": ("moyenne", "Restauration jamais testée",
               "Planifier un test de restauration (restore_test) : une sauvegarde non restaurée n'est pas une preuve."),
    "OPS-06": ("moyenne", "Astreinte en heures ouvrées pour une disponibilité de 99,9 % ou plus",
               "Étendre l'astreinte (oncall.hours) ou revoir l'engagement avec l'utilisateur."),
    "OPS-07": ("moyenne", "Un seul incident au RTO épuise le budget d'indisponibilité",
               "Réduire le RTO (bascule automatique, reprise testée) ou revoir la disponibilité cible."),
    "OPS-08": ("basse", "Fiche réflexe citée par aucune alerte",
               "Relier la fiche à l'alerte qui la déclenche, ou la retirer."),
    "OPS-09": ("moyenne", "Exigence de disponibilité ou d'exploitation portée par aucun service",
               "Citer l'exigence dans refs du service qui la tient, ou dire à l'utilisateur qu'elle n'est pas tenue."),
    "OPS-10": ("basse", "Sauvegarde gardée sur le seul site du service",
               "Prévoir une copie hors site (offsite) : un sinistre du site emporte données et sauvegardes."),
}
OPS_CATEGORIES = ("disponibilite", "exploitabilite")
CRITICAL = "critique"


def number(value: float, digits: int = 1) -> str:
    """Nombre à la française : virgule décimale, espace des milliers, sans zéro inutile."""
    text = f"{value:,.{digits}f}".replace(",", "\u202f").replace(".", ",")
    return text.rstrip("0").rstrip(",") if "," in text else text


def duration(minutes: float) -> str:
    if minutes >= 120:
        return f"{number(minutes / 60)} h"
    return f"{number(minutes, 0)} min"


def every(hours: float) -> str:
    return "toutes les heures" if hours == 1 else f"toutes les {number(hours)} h"


def budget(service: dict) -> float | None:
    """Minutes d'indisponibilité permises sur la fenêtre de l'engagement."""
    slo = service.get("slo") or {}
    if "availability" not in slo:
        return None
    return (100 - slo["availability"]) / 100 * slo.get("window_days", 30) * 24 * 60


def check(spec: dict, reqs: dict | None, errors: list[str]) -> list[dict]:
    """Erreurs de référence et de cohérence, puis constats de couverture (règles OPS)."""
    findings = []

    def find(rule: str, element: str, text: str) -> None:
        findings.append({"rule": rule, "severity": RULES[rule][0], "element": element, "text": text,
                         "fix": RULES[rule][2]})

    def unique(key: str) -> dict:
        found = {}
        for index, item in enumerate(spec.get(key, [])):
            if item["id"] in found:
                errors.append(f"{key}/{index}/id : « {item['id']} » en double")
            found[item["id"]] = item
        return found
    services, runbooks = unique("services"), unique("runbooks")
    alerts = unique("monitoring")
    oncall = spec.get("oncall") or {}
    levels = {level["level"] for level in oncall.get("levels", [])}

    for key in ("monitoring", "backups", "runbooks"):
        for index, item in enumerate(spec.get(key, [])):
            if item["service"] not in services:
                errors.append(f"{key}/{index}/service : service inconnu « {item['service']} »"
                              f"{near(item['service'], services, n=2)}")
    for index, alert in enumerate(spec.get("monitoring", [])):
        if alert.get("runbook") and alert["runbook"] not in runbooks:
            errors.append(f"monitoring/{index}/runbook : fiche inconnue « {alert['runbook']} »"
                          f"{near(alert['runbook'], runbooks, n=2)}")
        if alert.get("notify") and levels and alert["notify"] not in levels:
            errors.append(f"monitoring/{index}/notify : niveau d'astreinte inconnu « {alert['notify']} »"
                          f"{near(alert['notify'], levels, n=2)}")
    for index, runbook in enumerate(spec.get("runbooks", [])):
        if runbook.get("escalation") and levels and runbook["escalation"] not in levels:
            errors.append(f"runbooks/{index}/escalation : niveau d'astreinte inconnu « {runbook['escalation']} »"
                          f"{near(runbook['escalation'], levels, n=2)}")
    for index, service in enumerate(spec["services"]):
        for ref in service.get("refs", []):
            if reqs is not None and ref not in reqs:
                errors.append(f"services/{index}/refs : exigence « {ref} » absente de {spec['requirements']}"
                              f"{near(ref, reqs, n=2)}")
    for index, backup in enumerate(spec.get("backups", [])):
        rpo = services.get(backup["service"], {}).get("rpo_hours")
        if rpo is not None and backup["frequency_hours"] > rpo:
            errors.append(f"backups/{index} : une sauvegarde toutes les {number(backup['frequency_hours'])} h ne tient "
                          f"pas le RPO de {number(rpo)} h du service {backup['service']}")
    if errors:
        return []

    saved = {b["service"] for b in spec.get("backups", [])}
    cited = {a["runbook"] for a in alerts.values() if a.get("runbook")}
    for sid, service in services.items():
        critical = service.get("criticality") == CRITICAL
        allowed = budget(service)
        if critical and allowed is None:
            find("OPS-01", sid, f"{service['name']} est critique sans disponibilité cible")
        if critical and not any(a["service"] == sid and a["severity"] == CRITICAL for a in alerts.values()):
            find("OPS-02", sid, f"aucune alerte critique ne signale la panne de {service['name']}")
        if service.get("rpo_hours") is not None and sid not in saved:
            find("OPS-04", sid, f"{service['name']} a un RPO de {number(service['rpo_hours'])} h et aucune sauvegarde")
        if allowed is not None and service.get("rto_hours") is not None and service["rto_hours"] * 60 > allowed:
            find("OPS-07", sid, f"RTO de {number(service['rto_hours'])} h pour un budget de {duration(allowed)} "
                                f"sur {service['slo'].get('window_days', 30)} jours")
        if (service.get("slo") or {}).get("availability", 0) >= 99.9 and oncall.get("hours") == "heures ouvrées":
            find("OPS-06", sid, f"{service['name']} vise {number(service['slo']['availability'], 3)} % avec une "
                                "astreinte en heures ouvrées")
    for aid, alert in alerts.items():
        if alert["severity"] in (CRITICAL, "majeure") and not alert.get("runbook"):
            find("OPS-03", aid, f"alerte {alert['severity']} « {alert['signal']} » sans fiche réflexe")
    for backup in spec.get("backups", []):
        name = f"{backup['service']} ({backup['what']})"
        if not backup.get("restore_test"):
            find("OPS-05", backup["service"], f"sauvegarde {name} : aucun test de restauration prévu")
        if not backup.get("offsite"):
            find("OPS-10", backup["service"], f"sauvegarde {name} sans copie hors site")
    for rid in runbooks:
        if rid not in cited:
            find("OPS-08", rid, f"fiche {rid} « {runbooks[rid]['title']} » déclenchée par aucune alerte")
    carried = {ref for service in services.values() for ref in service.get("refs", [])}
    for rid, req in (reqs or {}).items():
        if req.get("category") in OPS_CATEGORIES and req.get("priority") != "hors-perimetre" and rid not in carried:
            find("OPS-09", rid, f"{rid} « {req.get('title', '')} » ({req.get('metric') or 'sans mesure'}) "
                                "n'est citée par aucun service")
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["rule"], f["element"]))
    return findings


def markdown(spec: dict, findings: list[dict]) -> str:
    services = {s["id"]: s for s in spec["services"]}
    name = {sid: s["name"] for sid, s in services.items()}
    lines = [f"# {spec['title']}", ""]
    if spec.get("context"):
        lines += [spec["context"], ""]
    lines += ["## Services et engagements", "",
              "| Service | Criticité | Disponibilité cible | Indisponibilité permise | RPO | RTO | Responsable | Exigences |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for service in spec["services"]:
        slo, allowed = service.get("slo") or {}, budget(service)
        target = f"{number(slo['availability'], 3)} % sur {slo.get('window_days', 30)} jours" if allowed is not None else "-"
        hours = lambda key: f"{number(service[key])} h" if service.get(key) is not None else "-"  # noqa: E731
        lines.append(f"| {cell(service['name'])} | {service.get('criticality', 'standard')} | {target} | "
                     f"{duration(allowed) if allowed is not None else '-'} | {hours('rpo_hours')} | {hours('rto_hours')} | "
                     f"{cell(service.get('owner', '-'))} | {', '.join(service.get('refs', [])) or '-'} |")
    latency = [s for s in spec["services"] if (s.get("slo") or {}).get("latency_ms")]
    if latency:
        lines += ["", "Temps de réponse cibles : " + " ; ".join(
            f"{s['name']} {number(s['slo']['latency_ms'], 0)} ms" for s in latency) + "."]
    if spec.get("monitoring"):
        lines += ["", "## Supervision et alertes", "",
                  "| Id | Service | Signal | Seuil | Gravité | Prévenu | Fiche réflexe |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        lines += [f"| {a['id']} | {cell(name[a['service']])} | {cell(a['signal'])} | {cell(a['threshold'])} | "
                  f"{a['severity']} | {a.get('notify', '-')} | {a.get('runbook') or '**aucune**'} |"
                  for a in spec["monitoring"]]
    if spec.get("backups"):
        lines += ["", "## Sauvegardes et restauration", "",
                  "| Service | Données | Fréquence | Conservation | Hors site | Test de restauration |",
                  "| --- | --- | --- | --- | --- | --- |"]
        lines += [f"| {cell(name[b['service']])} | {cell(b['what'])} | {every(b['frequency_hours'])} | "
                  f"{b['retention_days']} jours | {'oui' if b.get('offsite') else 'non'} | "
                  f"{cell(b.get('restore_test') or '**jamais**')} |" for b in spec["backups"]]
    oncall = spec.get("oncall")
    if oncall:
        lines += ["", "## Astreinte et escalade", "", f"Couverture : {oncall['hours']}.", "",
                  "| Niveau | Qui | Prise en charge sous |", "| --- | --- | --- |"]
        lines += [f"| {level['level']} | {cell(level['who'])} | {level['delay_minutes']} min |"
                  for level in oncall.get("levels", [])]
    if spec.get("runbooks"):
        lines += ["", "## Fiches réflexes"]
        for runbook in spec["runbooks"]:
            triggers = [a["id"] for a in spec.get("monitoring", []) if a.get("runbook") == runbook["id"]]
            lines += ["", f"### {runbook['id']} : {runbook['title']}", "",
                      f"Service : {name[runbook['service']]}. Déclenchée par : {', '.join(triggers) or 'aucune alerte'}."
                      + (f" Escalade : {runbook['escalation']}." if runbook.get("escalation") else "")]
            for title, key in (("Symptômes", "symptoms"), ("Diagnostic", "diagnosis"), ("Actions", "actions")):
                if runbook.get(key):
                    ordered = key != "symptoms"
                    lines += ["", f"**{title}**", ""]
                    lines += [f"{f'{i}.' if ordered else '-'} {step}" for i, step in enumerate(runbook[key], 1)]
            if runbook.get("rollback"):
                lines += ["", f"**Retour arrière** : {runbook['rollback']}"]
    if spec.get("operations"):
        lines += ["", "## Opérations récurrentes", "", "| Opération | Fréquence | Créneau | Étapes |",
                  "| --- | --- | --- | --- |"]
        lines += [f"| {cell(o['name'])} | {cell(o['frequency'])} | {cell(o.get('window', '-'))} | "
                  f"{cell(' ; '.join(o.get('steps', [])) or '-')} |" for o in spec["operations"]]
    lines += ["", "## Points ouverts", ""]
    if findings:
        lines += ["| Règle | Gravité | Élément | Constat | Correction |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {f['rule']} | {f['severity']} | {f['element']} | {cell(f['text'])} | {cell(f['fix'])} |"
                  for f in findings]
    else:
        lines.append("Aucun : chaque service critique a son engagement, son alerte, sa fiche et sa sauvegarde testée.")
    return "\n".join(lines) + "\n"


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description EXPLOITATION.json")
    parser.add_argument("--out-dir", type=Path, help="dossier du fichier produit (défaut : celui de la description)")
    parser.add_argument("--strict", action="store_true", help="code 1 dès un constat de gravité haute")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma de la description sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.spec), "output": None, "services": 0, "alerts": 0, "runbooks": 0, "backups": 0,
              "findings": [], "counts": {s: 0 for s in SEVERITIES}, "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.spec:
        errors.append("description EXPLOITATION.json attendue")
        return done(1)
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{args.spec} illisible ({error})")
        return done(1)
    errors += validate(spec, __file__)
    if errors:
        return done(1)
    reqs = None
    if spec.get("requirements"):
        path = args.spec.parent / spec["requirements"]
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            reqs = {r["id"]: r for r in data["requirements"] if r.get("status") != "retiree"}
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"requirements : {path} illisible ({error})")
            return done(1)
    else:
        warnings.append("sans requirements : exigences de disponibilité et d'exploitation non confrontées (OPS-09)")
    findings = check(spec, reqs, errors)
    report.update(services=len(spec["services"]), alerts=len(spec.get("monitoring", [])),
                  runbooks=len(spec.get("runbooks", [])), backups=len(spec.get("backups", [])))
    if errors:
        return done(1)
    for finding in findings:
        report["counts"][finding["severity"]] += 1
    report["findings"] = [{k: f[k] for k in ("rule", "severity", "element", "text")} for f in findings]
    out_dir = args.out_dir or args.spec.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / (args.spec.name.removesuffix(".json") + ".md")
    out.write_text(markdown(spec, findings), encoding="utf-8")
    report["output"] = str(out)
    return done(1 if args.strict and report["counts"]["haute"] else 0)


if __name__ == "__main__":
    sys.exit(main())
