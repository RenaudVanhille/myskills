# /// script
# requires-python = ">=3.10"
# ///
"""Prépare le modèle de menaces STRIDE d'une architecture décrite pour cloud_build.py.

Même description JSON que cloud_build.py : les groupes de type compte, VPC,
sous-réseau, security group, cluster, namespace, on-premise, internet ou
boundary sont des frontières de confiance (`"boundary": true` ou `false`
pour forcer). Le script applique STRIDE par élément (entité externe : S, R ;
traitement : S, T, R, I, D, E ; stockage : T, R, I, D ; flux : T, I, D),
met en tête les flux qui traversent une frontière, et écrit
<sujet>.threats.md : frontières, flux à risque, puis une ligne par menace
avec une mesure type et une colonne Statut à compléter. Les numéros de flux
(F1, F2...) sont ceux du schéma `cloud_build.py --view threats`.

    uv run scripts/stride.py SUJET.json [--out SUJET.threats.md] [--all-flows]
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from cloud_build import build  # noqa: E402
sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from spec_schema import print_schema, validate  # noqa: E402

CATEGORIES = {"S": "Usurpation d'identité", "T": "Altération", "R": "Répudiation",
              "I": "Divulgation d'information", "D": "Déni de service", "E": "Élévation de privilèges"}
APPLIES = {"external": "SR", "process": "STRIDE", "store": "TRID", "network": "STID", "flow": "TID"}
# (catégorie, nature) -> (menace type, mesure type). "*" : toute nature.
THREATS = {
    ("S", "external"): ("Un tiers se fait passer pour {x}.", "Authentification forte (OIDC, MFA, mTLS pour un système)."),
    ("S", "*"): ("Un appelant non autorisé usurpe l'identité d'un client de {x}.",
                 "Authentifier chaque appel (jeton signé, mTLS, identité de charge de travail)."),
    ("T", "store"): ("Les données de {x} sont modifiées ou supprimées sans autorisation.",
                     "Droits minimaux en écriture, versionnement ou verrouillage, sauvegardes immuables."),
    ("T", "flow"): ("Le contenu du flux {x} est modifié en transit.", "TLS 1.2+ de bout en bout, signature des messages sensibles."),
    ("T", "*"): ("Le code, la configuration ou les entrées de {x} sont altérés.",
                 "Validation des entrées, images signées, configuration en lecture seule."),
    ("R", "external"): ("{x} nie avoir effectué une action.", "Journal d'audit horodaté des actions de {x}."),
    ("R", "*"): ("Une action sur {x} ne peut pas être attribuée à son auteur.",
                 "Journaux centralisés, horodatés et inaltérables (rétention définie)."),
    ("I", "store"): ("Les données de {x} sont lues par un tiers non autorisé.",
                     "Chiffrement au repos (clé gérée), accès privé uniquement, droits minimaux en lecture."),
    ("I", "flow"): ("Le flux {x} est intercepté.", "Chiffrement en transit (TLS), réseau privé ou endpoint privé."),
    ("I", "*"): ("{x} expose des données ou des secrets (erreurs, journaux, métadonnées).",
                 "Secrets dans un coffre, messages d'erreur génériques, journaux sans données sensibles."),
    ("D", "flow"): ("Le flux {x} est saturé ou coupé.", "Limitation de débit, files tampons, nouvelles tentatives avec délai."),
    ("D", "*"): ("{x} est rendu indisponible (saturation, quota).",
                 "Autoscaling, quotas et limitation de débit, protection anti-DDoS ou WAF en entrée."),
    ("E", "*"): ("Un attaquant obtient sur {x} plus de droits que prévu.",
                 "Moindre privilège (rôles IAM dédiés), isolation, pas d'exécution en root."),
}


def threat(category: str, nature: str, name: str) -> tuple[str, str]:
    text, measure = THREATS.get((category, nature)) or THREATS[(category, "*")]
    return text.format(x=name), measure.replace("{x}", name)


def cell(text: str) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def model(spec: dict, all_flows: bool) -> tuple[str, dict]:
    _, pages, errors, warnings = build(spec, "threats")
    lines = [f"# Modèle de menaces STRIDE : {spec.get('title', 'architecture')}", "",
             "Prérempli par `stride.py` à partir de la description de l'architecture : une menace type par "
             "catégorie STRIDE applicable. Gardez les menaces pertinentes, précisez-les, puis complétez la "
             "mesure retenue et le statut (à traiter, traitée, acceptée).", ""]
    rows, counts = [], {"boundaries": 0, "elements": 0, "flows": 0, "crossing": 0, "threats": 0}
    for name, b, flows in pages:
        label = {**{k: v["label"] for k, v in b.nodes.items()}, **{k: v["label"] for k, v in b.groups.items()}}
        if len(pages) > 1:
            lines += [f"## {name}", ""]
        bounds = [g["label"] for g in b.groups.values() if g["boundary"]]
        counts["boundaries"] += len(bounds)
        lines += ["## Frontières de confiance", ""] + [f"- {g}" for g in bounds] + \
                 (["- aucune : marquez les groupes avec \"boundary\": true"] if not bounds else []) + [""]
        crossing = [f for f in flows if f["crosses"]]
        clear = []
        counts["crossing"] += len(crossing)
        lines += ["## Flux qui traversent une frontière", "",
                  "| Flux | De | Vers | Frontière | Protocole | Chiffré |", "| --- | --- | --- | --- | --- | --- |"]
        for f in crossing:
            proto = " ".join(str(f[k]) for k in ("protocol", "port") if f[k])
            tls = any(t in proto.upper() for t in ("HTTPS", "TLS", "MTLS", "SSH", "IPSEC"))
            encrypted = f["encrypted"] if f["encrypted"] is not None else (True if tls else None)
            enc = {True: "oui", False: "non"}.get(encrypted, "?")
            lines.append(f"| F{f['n']} | {cell(label[f['from']])} | {cell(label[f['to']])} | "
                         f"{cell(', '.join(f['crosses']))} | {cell(proto)} | {enc} |")
            if encrypted is not True:
                clear.append(f"F{f['n']}")
        if clear:
            warnings.append(f"{name} : {', '.join(clear)} traversent une frontière sans chiffrement déclaré "
                            "(\"encrypted\": true, ou protocole HTTPS, TLS...)")
        if not crossing:
            lines.append("| aucun | | | | | |")
        lines.append("")
        for nid, node in b.nodes.items():
            if node["kind"] is None:
                continue
            counts["elements"] += 1
            if node["kind"] == "store" and any(f["to"] == nid and f["crosses"] and
                                               b.nodes.get(f["from"], {}).get("kind") == "external" for f in flows):
                warnings.append(f"{name} : {node['label']} (stockage) est atteint directement depuis l'extérieur")
            for category in APPLIES.get(node["kind"], "STRIDE"):
                rows.append((0 if node["path"] == () else 1, f"{node['label']}", node["kind"], category))
        for f in flows:
            counts["flows"] += 1
            if f["crosses"] or all_flows:
                for category in APPLIES["flow"]:
                    rows.append((-1 if f["crosses"] else 2, f"F{f['n']} {label[f['from']]} → {label[f['to']]}",
                                 "flow", category))
    rows.sort(key=lambda r: r[0])
    lines += ["## Menaces", "", "| ID | Élément | STRIDE | Menace | Mesure type | Mesure retenue | Statut |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for index, (_, name, nature, category) in enumerate(rows, 1):
        text, measure = threat(category, "process" if nature == "network" else nature, name)
        lines.append(f"| M{index:03d} | {cell(name)} | {category} : {CATEGORIES[category]} | {cell(text)} | "
                     f"{cell(measure)} |  | à analyser |")
    counts["threats"] = len(rows)
    return "\n".join(lines) + "\n", {**counts, "errors": errors, "warnings": warnings}


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, help="fichier Markdown (défaut : <sujet>.threats.md)")
    parser.add_argument("--all-flows", action="store_true",
                        help="analyser aussi les flux internes (par défaut : ceux qui traversent une frontière)")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)]}, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    invalid = validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid}, ensure_ascii=False))
        return 1
    text, report = model(spec, args.all_flows)
    out = args.out or args.spec.with_name(args.spec.name.removesuffix(".json") + ".threats.md")
    result = {"input": str(args.spec), "output": None, **report}
    if not report["errors"]:
        out.write_text(text, encoding="utf-8")
        result["output"] = str(out)
    print(json.dumps(result, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
