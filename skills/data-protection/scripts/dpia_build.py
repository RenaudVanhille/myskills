# /// script
# requires-python = ">=3.10"
# ///
"""Construit le registre des traitements (RGPD, art. 30) et l'analyse d'impact (AIPD, art. 35) d'une description JSON.

Le modèle décrit les traitements (finalité, base légale, personnes,
données, destinataires, durée de conservation, transferts) et les risques
pour les personnes (événement redouté, sources, impacts, gravité et
vraisemblance de 1 à 4, mesures et risque résiduel). Le script, et non le
modèle, contrôle et calcule :

- nécessité de l'AIPD : au moins deux critères des lignes directrices du
  CEPD (données sensibles, grande échelle, personnes vulnérables...) ;
- base légale, données sensibles de l'article 9, durée de conservation ;
- transferts hors de l'Espace économique européen sans garantie
  (chapitre V) et hébergeur soumis à des lois extraterritoriales
  (catalogue commun des hébergeurs, shared/providers.json) ;
- trois événements redoutés couverts par traitement (accès illégitime,
  modification non désirée, disparition) ;
- niveau de chaque risque (carte gravité × vraisemblance), risque résiduel
  jamais supérieur au risque initial, risque résiduel élevé qui appelle la
  consultation préalable de la CNIL (art. 36) ;
- références des mesures vers les exigences (exigences.json) et les
  menaces STRIDE (M001... du .threats.md de threat-model).

Ce qui se déduit sans jugement est proposé par le script : critères du
CEPD tirés des données (données sensibles, personnes vulnérables) et, pour
chaque risque, sources de risque, impacts et mesures quand le modèle ne les
donne pas. Les mesures viennent des exigences de sécurité, de conformité et
de disponibilité et des menaces STRIDE des flux du traitement et des
stockages (mesure retenue d'une menace traitée : existante ; sinon mesure
type : prévue). Avec --draft, le script écrit seulement <nom>.draft.json :
un risque par traitement et par événement redouté encore sans risque, avec
ses propositions ; le modèle n'y ajoute que la cotation (gravité,
vraisemblance, résiduel) dans la description.

Écrit <nom>.registre.md et <nom>.aipd.md ; avec --vault, une note
`traitement` par traitement et une note `risque` par risque.

    uv run scripts/dpia_build.py AIPD.json [--draft] [--out-dir DOSSIER] [--vault VAULT --folder DOSSIER_DU_VAULT] | --schema
"""

import argparse
import difflib
import json
import re
import sys
import unicodedata
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import vault_ontology  # noqa: E402
import workspace  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

PROVIDERS = Path(__file__).resolve().parent / "lib" / "providers.json"
CRITERIA = {
    "evaluation": "évaluation ou notation (profilage, scoring)",
    "decision-automatique": "décision automatique avec effet juridique ou similaire",
    "surveillance": "surveillance systématique",
    "donnees-sensibles": "données sensibles ou à caractère hautement personnel",
    "grande-echelle": "traitement à grande échelle",
    "croisement": "croisement ou combinaison de jeux de données",
    "personnes-vulnerables": "personnes vulnérables (patients, salariés, enfants...)",
    "usage-innovant": "usage innovant ou nouvelle solution technologique",
    "exclusion": "traitement qui empêche d'exercer un droit ou de bénéficier d'un service ou d'un contrat",
}
EVENTS = {"acces-illegitime": "Accès illégitime aux données", "modification-non-desiree": "Modification non désirée",
          "disparition": "Disparition des données"}
BASES = {"consentement": "consentement (art. 6.1.a)", "contrat": "exécution d'un contrat (art. 6.1.b)",
         "obligation-legale": "obligation légale (art. 6.1.c)", "interet-vital": "intérêts vitaux (art. 6.1.d)",
         "mission-publique": "mission d'intérêt public (art. 6.1.e)", "interet-legitime": "intérêt légitime (art. 6.1.f)"}
MECHANISMS = {"adequation": "décision d'adéquation", "clauses-types": "clauses contractuelles types",
              "bcr": "règles d'entreprise contraignantes", "derogation": "dérogation de l'article 49",
              "aucun": "aucune garantie"}
# Événement redouté -> catégories STRIDE et catégories d'exigences qui le couvrent.
EVENT_STRIDE = {"acces-illegitime": "SIE", "modification-non-desiree": "T", "disparition": "D"}
EVENT_CATEGORIES = {"acces-illegitime": {"securite", "conformite"}, "modification-non-desiree": {"securite"},
                    "disparition": {"disponibilite"}}
EVENT_SOURCES = {"acces-illegitime": ["attaquant externe", "personne interne malveillante ou négligente"],
                 "modification-non-desiree": ["attaquant externe", "erreur d'un utilisateur ou d'un gestionnaire"],
                 "disparition": ["panne ou sinistre", "rançongiciel", "erreur de manipulation"]}
EVENT_IMPACTS = {"acces-illegitime": "divulgation de {data}",
                 "modification-non-desiree": "décisions prises sur des données fausses ({data})",
                 "disparition": "perte de {data}, démarches des personnes interrompues"}
VULNERABLE = ("patient", "salarie", "employe", "agent", "enfant", "mineur", "eleve", "etudiant", "age",
              "demandeur", "handicap", "malade")
MAX_MEASURES = 6
SCALE = {1: "négligeable", 2: "limitée", 3: "importante", 4: "maximale"}
# Espace économique européen : les 27 États membres, l'Islande, le Liechtenstein et la Norvège (codes ISO et noms).
EEA = {"at", "be", "bg", "cy", "cz", "de", "dk", "ee", "es", "fi", "fr", "gr", "hr", "hu", "ie", "it", "lt", "lu",
       "lv", "mt", "nl", "pl", "pt", "ro", "se", "si", "sk", "is", "li", "no", "ue", "eee",
       "allemagne", "autriche", "belgique", "bulgarie", "chypre", "croatie", "danemark", "espagne", "estonie",
       "finlande", "france", "grece", "hongrie", "irlande", "italie", "lettonie", "lituanie", "luxembourg", "malte",
       "pays-bas", "pologne", "portugal", "republique tcheque", "roumanie", "slovaquie", "slovenie", "suede",
       "islande", "liechtenstein", "norvege", "union europeenne"}


def plain(text: str) -> str:
    return unicodedata.normalize("NFKD", text.lower().strip()).encode("ascii", "ignore").decode()


def level(gravity: int, likelihood: int) -> str:
    """Zone de la carte des risques : élevé, significatif ou limité."""
    if gravity >= 3 and likelihood >= 3:
        return "élevé"
    if gravity >= 3 or likelihood >= 3:
        return "significatif"
    return "limité"


def known_refs(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> set[str] | None:
    """Identifiants des exigences et des menaces citables par les mesures ; None si aucune source donnée."""
    refs: set[str] = set()
    given = False
    if spec.get("requirements"):
        given = True
        try:
            catalog = json.loads((base / spec["requirements"]).read_text(encoding="utf-8"))
            refs |= {r["id"] for r in catalog.get("requirements", [])}
        except (OSError, ValueError, KeyError, TypeError) as error:
            errors.append(f"requirements : {spec['requirements']} illisible ({error})")
    if spec.get("threats"):
        given = True
        try:
            refs |= set(re.findall(r"\|\s*(M\d{3})\s*\|", (base / spec["threats"]).read_text(encoding="utf-8")))
        except OSError as error:
            errors.append(f"threats : {spec['threats']} illisible ({error})")
    return refs if given else None


def threat_rows(spec: dict, base: Path) -> list[dict]:
    """Menaces de stride.py (.threats.json) avec la mesure retenue et le statut du .threats.md relu."""
    if not spec.get("threats"):
        return []
    md = base / spec["threats"]
    try:
        items = json.loads(md.with_suffix(".json").read_text(encoding="utf-8"))["threats"]
        text = md.read_text(encoding="utf-8")
    except (OSError, ValueError, KeyError, TypeError):
        return []
    decided = {}
    for row in re.findall(r"^\|\s*(M\d{3,})\s*\|(.*)\|\s*$", text, re.M):
        cells = [c.strip() for c in row[1].split("|")]
        if len(cells) >= 6:
            decided[row[0]] = (cells[4], cells[5])
    rows = []
    for item in items:
        retained, status = decided.get(item["id"], ("", ""))
        if status.startswith("écartée") or item["id"] not in decided:
            continue
        rows.append({**item, "retained": retained.split(" (accepté")[0].strip(), "status": status})
    return rows


def proposal(spec: dict, base: Path) -> dict:
    """Sources, impacts et mesures proposés pour chaque (traitement, événement redouté), sans jugement."""
    hors_ue = False
    if spec.get("hosting", {}).get("provider"):
        try:
            catalog = json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]
            hors_ue = catalog.get(spec["hosting"]["provider"], {}).get("jurisdiction") == "hors-ue"
        except (OSError, ValueError):
            pass
    requirements = []
    if spec.get("requirements"):
        try:
            catalog = json.loads((base / spec["requirements"]).read_text(encoding="utf-8"))
            requirements = [r for r in catalog.get("requirements", []) if r.get("status") != "retiree"]
        except (OSError, ValueError, TypeError):
            pass
    threats = threat_rows(spec, base)
    result = {}
    for t in spec["treatments"]:
        data = ", ".join(d["category"] for d in t["data"])
        for event in EVENTS:
            measures: dict[str, dict] = {}

            def add(text: str, ref: str, kind: str) -> None:
                entry = measures.setdefault(text, {"text": text, "kind": kind, "refs": []})
                if ref not in entry["refs"]:
                    entry["refs"].append(ref)
                if kind == "existante":
                    entry["kind"] = kind

            for item in threats:
                if item["stride"] not in EVENT_STRIDE[event]:
                    continue
                if not (item.get("kind") == "store" or (item.get("flow") and item["flow"] in t.get("flows", []))):
                    continue
                if item["status"].startswith("traitée") and item["retained"]:
                    add(item["retained"], item["id"], "existante")
                else:
                    add(item["measure"], item["id"], "prevue")
            for r in requirements:
                if r.get("category") in EVENT_CATEGORIES[event]:
                    add(f"{r['title']} : {r['text']}".rstrip("."), r["id"], "prevue")
            # Mesures existantes d'abord, puis les plus citées.
            ranked = sorted(measures.values(), key=lambda m: (m["kind"] != "existante", -len(m["refs"])))
            sources = EVENT_SOURCES[event] + (["autorité étrangère (lois extraterritoriales de l'hébergeur)"]
                                              if hors_ue and event == "acces-illegitime" else [])
            result[(t["id"], event)] = {"sources": sources, "impacts": EVENT_IMPACTS[event].format(data=data),
                                        "measures": ranked[:MAX_MEASURES]}
    return result


def deduced_criteria(spec: dict) -> list[str]:
    found = []
    if any(d.get("sensitive") for t in spec["treatments"] for d in t["data"]):
        found.append("donnees-sensibles")
    if any(word in plain(subject) for t in spec["treatments"] for subject in t["subjects"] for word in VULNERABLE):
        found.append("personnes-vulnerables")
    return [c for c in found if c not in spec.get("criteria", [])]


def complete(spec: dict, base: Path) -> tuple[int, list[str]]:
    """Ajoute critères déduits et propositions manquantes des risques ; renvoie le nombre de champs proposés."""
    added = deduced_criteria(spec)
    spec["criteria"] = spec.get("criteria", []) + added
    proposed = 0
    if spec.get("risks"):
        ideas = proposal(spec, base)
        for r in spec["risks"]:
            idea = ideas.get((r["treatment"], r["event"]))
            if not idea:
                continue
            for key in ("sources", "impacts", "measures"):
                if key not in r and idea[key]:
                    r[key] = idea[key]
                    proposed += 1
    return proposed, added


def draft(spec: dict, base: Path) -> dict:
    """Risques encore à analyser (un par traitement et événement), avec leurs propositions, sans cotation."""
    ideas = proposal(spec, base)
    covered = {(r["treatment"], r["event"]) for r in spec.get("risks", [])}
    taken = {r["id"] for r in spec.get("risks", [])}
    risks, n = [], 0
    for (treatment, event), idea in ideas.items():
        if (treatment, event) in covered:
            continue
        n += 1
        while f"R-{n:02d}" in taken:
            n += 1
        risks.append({"id": f"R-{n:02d}", "treatment": treatment, "event": event, **idea})
    return {"criteria": spec.get("criteria", []), "risks": risks,
            "_a_faire": "Reprendre chaque risque dans la description avec gravity, likelihood et residual (1 à 4) ; "
                        "sources, impacts et measures n'y sont à écrire que pour corriger la proposition."}


def check(spec: dict, base: Path, errors: list[str], warnings: list[str]) -> dict:
    treatments = {t["id"]: t for t in spec["treatments"]}
    if len(treatments) != len(spec["treatments"]):
        errors.append("treatments : identifiant en double")
    risks = spec.get("risks", [])
    if len({r["id"] for r in risks}) != len(risks):
        errors.append("risks : identifiant en double")
    criteria = spec.get("criteria", [])
    aipd = "requise" if len(set(criteria)) >= 2 else "non-requise"
    if aipd == "non-requise":
        warnings.append(f"{len(set(criteria))} critère(s) du CEPD : AIPD non obligatoire (deux au moins) ; "
                        "l'analyse reste une bonne pratique, à justifier au registre")
    # Hébergeur et juridiction.
    hosting = spec.get("hosting", {})
    jurisdiction = None
    if hosting.get("provider"):
        try:
            catalog = json.loads(PROVIDERS.read_text(encoding="utf-8"))["providers"]
            if hosting["provider"] in catalog:
                jurisdiction = catalog[hosting["provider"]].get("jurisdiction")
                if jurisdiction == "hors-ue":
                    warnings.append(f"hébergeur {catalog[hosting['provider']]['name']} soumis à des lois "
                                    "extraterritoriales : accès d'autorités hors UE possible, à couvrir par un "
                                    "risque d'accès illégitime et ses mesures (chiffrement, clés maîtrisées)")
            else:
                close = difflib.get_close_matches(hosting["provider"], list(catalog), n=1)
                errors.append(f"hosting/provider : hébergeur inconnu « {hosting['provider']} »"
                              + (f" ; vouliez-vous « {close[0]} » ?" if close else f" ({', '.join(catalog)})"))
        except (OSError, ValueError) as error:
            errors.append(f"catalogue des hébergeurs illisible : {error}")
    out_transfers = 0
    for t in spec["treatments"]:
        where = f"treatments/{t['id']}"
        if any(d.get("sensitive") for d in t["data"]) and not t.get("art9_exception"):
            warnings.append(f"{where} : données sensibles (art. 9) sans exception de l'article 9.2 (art9_exception)")
        if not t.get("retention", "").strip():
            errors.append(f"{where} : durée de conservation manquante (retention)")
        for i, transfer in enumerate(t.get("transfers", [])):
            if plain(transfer["country"]) in EEA:
                continue
            out_transfers += 1
            if transfer.get("mechanism", "aucun") == "aucun":
                errors.append(f"{where}/transfers/{i} : transfert vers {transfer['country']} hors de l'EEE sans "
                              "garantie (chapitre V) : adequation, clauses-types, bcr ou derogation")
        covered = {r["event"] for r in risks if r["treatment"] == t["id"]}
        missing = [EVENTS[e] for e in EVENTS if e not in covered]
        if aipd == "requise" and missing:
            warnings.append(f"{where} : événement(s) redouté(s) sans risque analysé : {', '.join(missing)} "
                            "(--draft les propose)")
    refs = known_refs(spec, base, errors, warnings)
    high = 0
    for r in risks:
        where = f"risks/{r['id']}"
        if r["treatment"] not in treatments:
            close = difflib.get_close_matches(r["treatment"], list(treatments), n=1)
            errors.append(f"{where}/treatment : traitement inconnu « {r['treatment']} »"
                          + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
        residual = r.get("residual") or {"gravity": r["gravity"], "likelihood": r["likelihood"]}
        if residual["gravity"] > r["gravity"] or residual["likelihood"] > r["likelihood"]:
            errors.append(f"{where}/residual : risque résiduel supérieur au risque initial")
        if not r.get("measures"):
            warnings.append(f"{where} : aucune mesure")
        elif not r.get("residual"):
            warnings.append(f"{where} : mesures sans risque résiduel évalué (residual)")
        if level(residual["gravity"], residual["likelihood"]) == "élevé":
            high += 1
            warnings.append(f"{where} : risque résiduel élevé : mesures à renforcer, sinon consultation préalable "
                            "de la CNIL (art. 36)")
        for m, measure in enumerate(r.get("measures", [])):
            for ref in measure.get("refs", []):
                if refs is not None and ref not in refs:
                    close = difflib.get_close_matches(ref, sorted(refs), n=1)
                    errors.append(f"{where}/measures/{m}/refs : « {ref} » inconnu (exigences, menaces)"
                                  + (f" ; vouliez-vous « {close[0]} » ?" if close else ""))
        if refs is None and any(m.get("refs") for m in r.get("measures", [])):
            warnings.append(f"{where} : références non vérifiées (ni requirements ni threats dans la description)")
    return {"aipd": aipd, "jurisdiction": jurisdiction, "transfers_out": out_transfers, "residual_high": high}


def registre(spec: dict) -> str:
    lines = [f"# Registre des traitements : {spec['title']}", "",
             f"Responsable du traitement : {spec['controller']}"
             + (f" ; délégué à la protection des données : {spec['dpo']}" if spec.get("dpo") else "") + ".", ""]
    for t in spec["treatments"]:
        data = "; ".join(d["category"] + (" (sensible, art. 9)" if d.get("sensitive") else "")
                         + (f" : {d['examples']}" if d.get("examples") else "") for d in t["data"])
        transfers = "; ".join(f"{x['country']} ({MECHANISMS[x.get('mechanism', 'aucun')]})"
                              for x in t.get("transfers", []) if plain(x["country"]) not in EEA) or "aucun"
        rows = [("Finalité", t["purpose"]), ("Base légale", BASES[t["legal_basis"]]),
                ("Exception de l'article 9.2", t.get("art9_exception", "")),
                ("Personnes concernées", "; ".join(t["subjects"])), ("Données", data),
                ("Destinataires", "; ".join(t.get("recipients", [])) or "aucun"),
                ("Transferts hors UE", transfers), ("Durée de conservation", t["retention"]),
                ("Minimisation", t.get("minimisation", "")), ("Flux de l'architecture", ", ".join(t.get("flows", []))),
                ("Exigences", ", ".join(t.get("refs", [])))]
        lines += [f"## {t['id']} : {t['name']}", "", "| Rubrique | Contenu |", "| --- | --- |"]
        lines += [f"| {k} | {v} |" for k, v in rows if v]
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def aipd(spec: dict, result: dict) -> str:
    criteria = spec.get("criteria", [])
    lines = [f"# Analyse d'impact relative à la protection des données : {spec['title']}", "",
             f"**AIPD {result['aipd']}** : {len(set(criteria))} critère(s) du CEPD"
             + (" (" + "; ".join(CRITERIA[c] for c in criteria) + ")" if criteria else "") + ".", "",
             f"Traitements : {len(spec['treatments'])} ; risques analysés : {len(spec.get('risks', []))} ; "
             f"risques résiduels élevés : {result['residual_high']} ; transferts hors EEE : {result['transfers_out']}.", ""]
    if spec.get("hosting", {}).get("provider"):
        lines += [f"Hébergement : {spec['hosting']['provider']}"
                  + (f", juridiction {result['jurisdiction']}" if result["jurisdiction"] else "") + ".", ""]
    lines += ["## Risques pour les personnes", "",
              "| Risque | Traitement | Événement redouté | Gravité | Vraisemblance | Niveau | Mesures | Résiduel |",
              "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for r in spec.get("risks", []):
        residual = r.get("residual")
        measures = "<br>".join(m["text"] + (f" ({', '.join(m['refs'])})" if m.get("refs") else "")
                               + (" *(prévue)*" if m.get("kind") == "prevue" else "") for m in r.get("measures", []))
        lines.append(f"| {r['id']} | {r['treatment']} | {EVENTS[r['event']]} | {r['gravity']} ({SCALE[r['gravity']]}) | "
                     f"{r['likelihood']} ({SCALE[r['likelihood']]}) | {level(r['gravity'], r['likelihood'])} | "
                     f"{measures or 'aucune'} | "
                     + (f"{residual['gravity']} × {residual['likelihood']} : {level(residual['gravity'], residual['likelihood'])}"
                        if residual else "à évaluer") + " |")
    lines += ["", "## Carte des risques", "", "Gravité en ligne, vraisemblance en colonne ; initial → résiduel.", "",
              "| Gravité \\ Vraisemblance | 1 | 2 | 3 | 4 |", "| --- | --- | --- | --- | --- |"]
    for g in (4, 3, 2, 1):
        cells = []
        for v in (1, 2, 3, 4):
            here = [r["id"] for r in spec.get("risks", []) if r["gravity"] == g and r["likelihood"] == v]
            after = [r["id"] + "'" for r in spec.get("risks", []) if r.get("residual")
                     and r["residual"]["gravity"] == g and r["residual"]["likelihood"] == v]
            cells.append(", ".join(here + after))
        lines.append(f"| {g} ({SCALE[g]}) | " + " | ".join(cells) + " |")
    lines += ["", "## Sources et impacts", ""]
    for r in spec.get("risks", []):
        lines.append(f"- **{r['id']}** : sources {', '.join(r.get('sources', [])) or 'non précisées'} ; "
                     f"impacts : {r.get('impacts', 'non précisés')}.")
    lines += ["", "## À valider", "",
              "- Avis du délégué à la protection des données et, le cas échéant, des personnes concernées.",
              "- Plan d'action des mesures prévues, avec responsable et échéance.",
              "- Revue de l'analyse à chaque évolution du traitement."]
    return "\n".join(lines).rstrip() + "\n"


def write_vault(vault: Path, folder: str, spec: dict, result: dict, errors: list[str]) -> dict | None:
    notes = vault_ontology.Notes(vault, "data-protection")
    base = vault_ontology.safe_folder(folder)
    for t in spec["treatments"]:
        transfers = [x for x in t.get("transfers", []) if plain(x["country"]) not in EEA]
        props = {"base-legale": t["legal_basis"], "sensibles": "oui" if any(d.get("sensitive") for d in t["data"]) else "non",
                 "aipd": result["aipd"],
                 "transferts": "aucun" if not transfers else
                 "non-encadres" if any(x.get("mechanism", "aucun") == "aucun" for x in transfers) else "encadres"}
        relations = {"porte-sur": [(f"{base}/Exigences/{ref}", ref) for ref in t.get("refs", [])]}
        body = [f"# {t['id']} : {t['name']}", "", t["purpose"], "",
                f"Base légale : {BASES[t['legal_basis']]}. Conservation : {t['retention']}."]
        notes.add(f"{base}/Traitements/{vault_ontology.safe_name(t['id'])}", "traitement", {"id": t["id"], **props},
                  relations, body, ["rgpd"])
    for r in spec.get("risks", []):
        residual = r.get("residual") or {"gravity": r["gravity"], "likelihood": r["likelihood"]}
        zone = level(residual["gravity"], residual["likelihood"])
        status = r.get("status") or ("ouvert" if zone == "élevé" or not r.get("measures") else "attenue")
        exigences = [ref for m in r.get("measures", []) for ref in m.get("refs", []) if not re.match(r"^M\d{3}$", ref)]
        relations = {"porte-sur": [(f"{base}/Traitements/{vault_ontology.safe_name(r['treatment'])}", r["treatment"])]
                     + [(f"{base}/Exigences/{ref}", ref) for ref in dict.fromkeys(exigences)]}
        body = [f"# {r['id']} : {EVENTS[r['event']]} ({r['treatment']})", "", r.get("impacts", ""), "",
                f"Initial {r['gravity']} × {r['likelihood']}, résiduel {residual['gravity']} × "
                f"{residual['likelihood']} : {zone}."]
        notes.add(f"{base}/Risques/{vault_ontology.safe_name(spec['title'])}/{vault_ontology.safe_name(r['id'])}",
                  "risque", {"id": r["id"], "statut": status,
                             "gravite": {"élevé": "haute", "significatif": "moyenne", "limité": "basse"}[zone]},
                  relations, body, ["rgpd"])
    written = notes.write(errors)
    return {**written, "folder": base} if written else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?", help="description AIPD.json")
    parser.add_argument("--out-dir", type=Path, help="dossier du registre et de l'AIPD (défaut : celui du .json)")
    parser.add_argument("--draft", action="store_true",
                        help="écrire seulement <nom>.draft.json : risques à coter avec leurs propositions")
    parser.add_argument("--vault", type=Path, help="vault Obsidian où écrire les notes traitement et risque")
    parser.add_argument("--folder", help="dossier des notes dans le vault, celui du workflow (Workflows/<titre>)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    # Dans une mission (mission.json au-dessus de la description) : son vault et le dossier du workflow par défaut.
    args.vault, args.folder, scoped = workspace.vault_target(args.vault, args.folder, [args.spec])
    if bool(args.vault) != bool(args.folder):
        parser.error("--vault et --folder vont ensemble")
    errors: list[str] = scoped
    warnings: list[str] = []
    report = {"input": str(args.spec), "outputs": [], "treatments": 0, "risks": 0, "aipd": None,
              "residual_high": 0, "transfers_out": 0, "proposed": 0, "criteria_added": [], "draft": None,
              "to_rate": 0, "vault": None, "errors": errors, "warnings": warnings}
    if args.vault and not args.vault.is_dir():
        errors.append(f"--vault : dossier introuvable {args.vault}")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(str(error))
        spec = None
    if spec is not None:
        # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
        errors += validate(spec, __file__)
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    base = args.spec.resolve().parent
    out_dir = args.out_dir or args.spec.parent
    stem = args.spec.name.removesuffix(".json")
    report["proposed"], report["criteria_added"] = complete(spec, base)
    if args.draft:
        proposed = draft(spec, base)
        out_dir.mkdir(parents=True, exist_ok=True)
        path = out_dir / f"{stem}.draft.json"
        path.write_text(json.dumps(proposed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        report.update(draft=str(path), to_rate=len(proposed["risks"]), treatments=len(spec["treatments"]),
                      risks=len(spec.get("risks", [])))
        if spec.get("threats") and not threat_rows(spec, base):
            warnings.append("threats : aucune menace lue (le .threats.json de stride.py doit être à côté du .md)")
        print(json.dumps(report, ensure_ascii=False))
        return 0
    result = check(spec, base, errors, warnings)
    report.update(treatments=len(spec["treatments"]), risks=len(spec.get("risks", [])), **{
        k: result[k] for k in ("aipd", "residual_high", "transfers_out")})
    if errors:
        print(json.dumps(report, ensure_ascii=False))
        return 1
    out_dir.mkdir(parents=True, exist_ok=True)
    for suffix, text in ((".registre.md", registre(spec)), (".aipd.md", aipd(spec, result))):
        path = out_dir / f"{stem}{suffix}"
        with open(path, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        report["outputs"].append(str(path))
    if args.vault:
        report["vault"] = write_vault(args.vault, args.folder, spec, result, errors)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
