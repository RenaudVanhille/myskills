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
(F1, F2...) sont ceux du schéma `cloud_build.py --view threats`. Il écrit
aussi <sujet>.threats.json, les mêmes menaces en données (nature, type,
flux, chiffrement, frontière : de quoi écrire des règles) : le modèle n'y
répond que par un court fichier de décisions, que threat_review.py reporte
dans le tableau (pas de réécriture du Markdown). Ce que la description prouve
déjà est proposé comme traité (`suggested`) : altération et interception
d'un flux chiffré (encrypted, HTTPS, TLS...).

    uv run scripts/stride.py SUJET.json [--out SUJET.threats.md] [--all-flows]
                             [--vault VAULT --folder DOSSIER_DU_VAULT [--option ID]]

Avec `--vault`, une note modele-menaces (compteurs, flux à risque ; relation
evalue vers la note de l'option `--option`) va dans le vault Obsidian du
workflow, vérifiée contre son ontologie. Les menaces restent dans le
.threats.md jusqu'à leur analyse.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, load_module, require_module  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

vault_ontology = require_module("markdown-to-obsidian", "lib/vault_ontology.py")
workspace = require_module("mission-workspace", "lib/workspace.py")

# Types de services, groupes et numéros de flux : ceux du schéma (skill cloud-architecture).
CLOUD = load_module("cloud-architecture", "cloud_build.py")
MISSING = None if CLOUD else absent("cloud-architecture", "cloud_build.py")

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


def encryption(f: dict) -> tuple[bool | None, str]:
    """Chiffrement déclaré du flux (encrypted, sinon protocole) et protocole affiché."""
    proto = " ".join(str(f[k]) for k in ("protocol", "port") if f[k])
    tls = any(t in proto.upper() for t in ("HTTPS", "TLS", "MTLS", "SSH", "IPSEC"))
    return (f["encrypted"] if f["encrypted"] is not None else (True if tls else None)), proto


def suggestion(category: str, row: dict) -> dict | None:
    """Mesure que la description prouve déjà : proposée comme traitée, le modèle peut la revoir."""
    if row["kind"] == "flow" and category in "TI" and row.get("encrypted"):
        how = row.get("protocol") or "chiffrement déclaré"
        return {"status": "traitee", "measure": f"Flux chiffré en transit ({how}), d'après la description."}
    return None


def model(spec: dict, all_flows: bool) -> tuple[str, dict, list[dict]]:
    _, pages, errors, warnings = CLOUD.build(spec, "threats")
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
            encrypted, proto = encryption(f)
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
                rows.append((0 if node["path"] == () else 1, f"{node['label']}", node["kind"], category,
                             {"kind": node["kind"], "type": node["type"]}))
        for f in flows:
            counts["flows"] += 1
            if f["crosses"] or all_flows:
                encrypted, proto = encryption(f)
                info = {"kind": "flow", "flow": f"F{f['n']}", "crossing": bool(f["crosses"]),
                        "encrypted": encrypted, "protocol": proto or None}
                for category in APPLIES["flow"]:
                    rows.append((-1 if f["crosses"] else 2, f"F{f['n']} {label[f['from']]} → {label[f['to']]}",
                                 "flow", category, info))
    counts["by_stride"] = {c: sum(r[3] == c for r in rows) for c in CATEGORIES}
    rows.sort(key=lambda r: r[0])
    lines += ["## Menaces", "", "| ID | Élément | STRIDE | Menace | Mesure type | Mesure retenue | Statut |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    threats = []
    counts["suggested"] = 0
    for index, (_, name, nature, category, info) in enumerate(rows, 1):
        text, measure = threat(category, "process" if nature == "network" else nature, name)
        item = {"id": f"M{index:03d}", "element": name, "stride": category, "threat": text, "measure": measure,
                **{k: v for k, v in info.items() if v is not None}}
        proposed = suggestion(category, info)
        if proposed:
            item["suggested"] = proposed
            counts["suggested"] += 1
        threats.append(item)
        lines.append(f"| M{index:03d} | {cell(name)} | {category} : {CATEGORIES[category]} | {cell(text)} | "
                     f"{cell(measure)} | {cell(proposed['measure']) if proposed else ''} | "
                     f"{'traitée (proposé)' if proposed else 'à analyser'} |")
    counts["threats"] = len(rows)
    return "\n".join(lines) + "\n", {**counts, "errors": errors, "warnings": warnings}, threats


def write_vault(vault: Path, folder: str, spec: dict, report: dict, out: Path, option: str | None,
                errors: list[str]) -> dict | None:
    """Note modele-menaces du vault : compteurs et lien vers le .threats.md, évalue l'option."""
    notes = vault_ontology.Notes(vault, "threat-model")
    base = vault_ontology.safe_folder(folder)
    title = vault_ontology.safe_name(spec.get("title", "architecture"), "menaces")
    option_rel = f"{base}/Options/Option {option}" if option else None
    v = vault_ontology
    detail = notes.attach(f"{base}/Rapports/{title}/{out.name}", out) if out.is_file() else f"`{out.name}`"
    crossing = (f"{v.count(report['crossing'], 'flux traversant', 'flux traversant')} une frontière de confiance "
                f"({v.count(report['boundaries'], 'frontière')})")
    body = [f"# Modèle de menaces : {spec.get('title', 'architecture')}", ""]
    body += v.callout("warning" if report["threats"] else "success",
                      f"{v.count(report['threats'], 'menace')} à analyser sur {v.count(report['elements'], 'élément')}",
                      [crossing + "."])
    body += ["| STRIDE | Menaces |", "| --- | --- |"]
    body += [f"| {c} : {CATEGORIES[c]} | {v.number(n)} |" for c, n in report["by_stride"].items() if n]
    body += ["", f"Détail, mesures retenues et statuts : {detail}."]
    notes.add(f"{base}/Modèles de menaces/{title}", "modele-menaces",
              {"menaces": report["threats"], "flux-a-risque": report["crossing"]},
              {"evalue": [(option_rel, f"Option {option}")] if option_rel else []}, body, ["securite"])
    result = notes.write(errors)
    return {**result, "folder": base} if result else None


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, help="fichier Markdown (défaut : <sujet>.threats.md)")
    parser.add_argument("--all-flows", action="store_true",
                        help="analyser aussi les flux internes (par défaut : ceux qui traversent une frontière)")
    parser.add_argument("--vault", type=Path, help="vault Obsidian où écrire la note du modèle de menaces")
    parser.add_argument("--folder", help="dossier des notes dans le vault, celui du workflow (Workflows/<titre>)")
    parser.add_argument("--option", help="identifiant de l'option évaluée (note Options/Option <id> du vault)")
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
    if scoped:
        print(json.dumps({"input": str(args.spec), "errors": scoped, "warnings": []}, ensure_ascii=False))
        return 1
    if bool(args.vault) != bool(args.folder):
        parser.error("--vault et --folder vont ensemble")
    if args.vault and not args.vault.is_dir():
        print(json.dumps({"input": str(args.spec), "errors": [f"--vault : dossier introuvable {args.vault}"],
                          "warnings": []}, ensure_ascii=False))
        return 1
    if MISSING:
        print(json.dumps({"input": str(args.spec), "errors": [MISSING], "warnings": []}, ensure_ascii=False))
        return 1
    try:
        spec = json.loads(args.spec.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        print(json.dumps({"input": str(args.spec), "errors": [str(error)], "warnings": []}, ensure_ascii=False))
        return 1
    # Description validée contre le schéma d'entrée du contract.json avant tout traitement.
    invalid = validate(spec, __file__)
    if invalid:
        print(json.dumps({"input": str(args.spec), "errors": invalid, "warnings": []}, ensure_ascii=False))
        return 1
    text, report, threats = model(spec, args.all_flows)
    out = args.out or args.spec.with_name(args.spec.name.removesuffix(".json") + ".threats.md")
    data = out.with_name(out.name.removesuffix(".md") + ".json")
    result = {"input": str(args.spec), "output": None, "model": None,
              **{k: v for k, v in report.items() if k != "by_stride"}, "vault": None}
    if not report["errors"]:
        out.write_text(text, encoding="utf-8")
        head = text.split("## Menaces", 1)[0]
        data.write_text(json.dumps({"title": spec.get("title", "architecture"), "head": head, "threats": threats},
                                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        result["output"], result["model"] = str(out), str(data)
        if args.vault:
            result["vault"] = write_vault(args.vault, args.folder, spec, report, out, args.option, report["errors"])
    print(json.dumps(result, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
