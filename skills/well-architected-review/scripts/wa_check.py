# /// script
# requires-python = ">=3.10"
# ///
"""Contrôle une architecture décrite pour cloud_build.py contre les cadres Well-Architected des fournisseurs.

Même description JSON que cloud_build.py. Le script applique des règles
mécaniques tirées de l'AWS Well-Architected Framework, de l'Azure
Well-Architected Framework et du Google Cloud Well-Architected Framework
(fiabilité, sécurité, excellence opérationnelle, performances, coûts,
durabilité), puis les conventions de schéma des fournisseurs (imbrication
des groupes région, VPC/VNet, zone, sous-réseau ; icônes officielles). Les
hébergeurs souverains du catalogue commun (shared/providers.json : OVHcloud,
Outscale, Cloud Temple...) passent les mêmes règles, par les rôles de leurs
services, avec les repères AWS faute de cadre propre ; la règle SEC-08
compare leurs qualifications à celles qu'exige la description
(`qualifications` : secnumcloud, hds). Chaque
constat donne la règle, le pilier, la gravité, l'élément, la correction et
la référence du cadre. Un constat accepté (clé `accept` de la description,
avec sa raison) reste dans le rapport mais ne compte plus. Le script écrit
<sujet>.wa.md : synthèse par pilier, constats, puis ce qui ne se vérifie pas
sur un schéma.

`--scope piliers` ne garde que les piliers : à la définition de
l'architecture (description d'une option, sans groupes réseau), avant tout
schéma ; `--scope conventions` ne garde que les conventions de schéma.

    uv run scripts/wa_check.py SUJET.json [--out SUJET.wa.md] [--scope tout|piliers|conventions]
                               [--fail-on haute|moyenne|basse|aucune]
    uv run scripts/wa_check.py --rules
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, load_module  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

HERE = Path(__file__).resolve().parent
# Types de services, groupes et numéros de flux : ceux du schéma (skill cloud-architecture).
CLOUD = load_module("cloud-architecture", "cloud_build.py")
MISSING = None if CLOUD else absent("cloud-architecture", "cloud_build.py")

CLOUDS = ("aws", "azure", "gcp")
SEVERITIES = ("haute", "moyenne", "basse")
PILLARS = {"reliability": "Fiabilité", "security": "Sécurité", "operations": "Excellence opérationnelle",
           "performance": "Efficacité des performances", "cost": "Optimisation des coûts",
           "sustainability": "Durabilité", "conventions": "Conventions de schéma"}
FRAMEWORKS = {"aws": "AWS Well-Architected", "azure": "Azure Well-Architected",
              "gcp": "Google Cloud Well-Architected", "k8s": "Kubernetes"}

# Rôles des services (types résolus par cloud_build.py).
VM = {"aws:ec2", "aws:ecs", "aws:eks", "aws:server", "azure:vm", "azure:aks", "azure:app-service",
      "gcp:compute-engine", "gcp:gke", "server", "k8s:deploy", "k8s:sts"}
SERVERLESS = {"aws:lambda", "aws:fargate", "aws:app-runner", "azure:functions", "azure:logic-apps",
              "azure:static-web-apps", "azure:container-instances", "gcp:cloud-run", "gcp:cloud-functions",
              "gcp:app-engine"}
# Bases à rendre redondantes soi-même (DynamoDB, Cosmos DB, Spanner... le sont par construction).
DATABASES = {"aws:rds", "aws:aurora", "aws:documentdb", "aws:neptune", "aws:redshift", "aws:elasticache",
             "azure:sql-database", "azure:mysql", "azure:postgresql", "azure:redis", "gcp:cloud-sql",
             "gcp:alloydb", "gcp:memorystore", "db"}
ENTRY = {"aws:alb", "aws:elb", "aws:nlb", "aws:api-gateway", "aws:cloudfront", "azure:application-gateway",
         "azure:front-door", "azure:load-balancer", "azure:api-management", "gcp:load-balancing",
         "gcp:api-gateway", "gcp:apigee", "gcp:cdn", "k8s:ing"}
ROLES = {
    "waf": {"aws": {"aws:waf"}, "azure": {"azure:front-door", "azure:application-gateway"}, "gcp": {"gcp:armor"}},
    "cdn": {"aws": {"aws:cloudfront"}, "azure": {"azure:front-door"}, "gcp": {"gcp:cdn"}},
    "secrets": {"aws": {"aws:secrets-manager", "aws:systems-manager"}, "azure": {"azure:key-vault"},
                "gcp": {"gcp:secret-manager"}},
    "monitoring": {"aws": {"aws:cloudwatch"}, "azure": {"azure:monitor", "azure:app-insights", "azure:log-analytics"},
                   "gcp": {"gcp:monitoring", "gcp:logging"}},
    "audit": {"aws": {"aws:cloudtrail", "aws:guardduty"}, "azure": {"azure:defender", "azure:log-analytics"},
              "gcp": {"gcp:logging", "gcp:security-command-center"}},
    "backup": {"aws": {"aws:backup", "aws:drs"}, "azure": {"azure:recovery-vault"}, "gcp": {"gcp:backup-dr"}},
}
SCALING_GROUPS = {"aws:asg"}
SCALING_NODES = {"azure:vmss", "k8s:hpa"}
REGIONS = {"aws:region", "azure:region", "gcp:region"}
ZONES = {"aws:az", "azure:zone", "gcp:zone"}
NETWORKS = {"aws:vpc", "azure:vnet", "gcp:vpc"}
SUBNETS = {"aws:public-subnet", "aws:private-subnet", "azure:subnet", "gcp:subnet"}
# Services régionaux ou globaux, hors réseau privé : ils se dessinent dans la région, pas dans un sous-réseau
# (accès privé : un endpoint privé dans le sous-réseau).
OUTSIDE_SUBNET = {f"aws:{t}" for t in ("s3", "dynamodb", "sqs", "sns", "cloudfront", "route53", "iam", "cloudwatch",
                                       "cloudtrail", "kms", "secrets-manager", "cognito", "api-gateway", "eventbridge",
                                       "step-functions", "kinesis", "firehose", "glue", "athena", "backup", "ecr",
                                       "waf", "shield", "global-accelerator", "guardduty", "bedrock")} | \
                 {f"azure:{t}" for t in ("storage-account", "cosmos-db", "key-vault", "front-door", "traffic-manager",
                                         "entra-id", "dns", "monitor", "log-analytics", "app-insights", "acr",
                                         "event-grid", "service-bus", "event-hubs", "openai", "defender")} | \
                 {f"gcp:{t}" for t in ("bigquery", "cloud-storage", "pubsub", "firestore", "spanner", "iam", "logging",
                                       "monitoring", "cdn", "armor", "dns", "cloud-run", "cloud-functions",
                                       "secret-manager", "kms", "artifact-registry", "vertex-ai")}
# Imbrication des groupes : rang (un groupe ne contient pas un groupe de rang inférieur) et ancêtre obligatoire.
RANK = {"aws:cloud": 0, "aws:account": 1, "aws:region": 2, "aws:vpc": 3, "aws:az": 4, "aws:public-subnet": 5,
        "aws:private-subnet": 5, "azure:subscription": 0, "azure:resource-group": 1, "azure:region": 1,
        "azure:vnet": 2, "azure:subnet": 3, "gcp:project": 0, "gcp:vpc": 1, "gcp:region": 1, "gcp:subnet": 3,
        "k8s:cluster": 0, "k8s:namespace": 1, "k8s:node": 1}
REQUIRED = {"aws:public-subnet": {"aws:vpc"}, "aws:private-subnet": {"aws:vpc"}, "aws:security-group": {"aws:vpc"},
            "aws:az": {"aws:region", "aws:vpc"}, "aws:vpc": {"aws:region"}, "azure:subnet": {"azure:vnet"},
            "azure:zone": {"azure:region", "azure:vnet"}, "gcp:subnet": {"gcp:vpc"},
            "gcp:zone": {"gcp:region", "gcp:subnet"}, "k8s:namespace": {"k8s:cluster"}, "k8s:node": {"k8s:cluster"}}

CONVENTION_REF = {"aws": "AWS Architecture Icons : AWS Cloud > Région > VPC > Zone de disponibilité > Sous-réseau",
                  "azure": "Azure Architecture Icons et Architecture Center : abonnement > groupe de ressources ; "
                           "région > VNet > sous-réseau",
                  "gcp": "Google Cloud Icons et diagrammes d'architecture : projet > VPC > région > sous-réseau, zone",
                  "k8s": "Kubernetes Icons : cluster > namespace, node"}
# règle -> (pilier, gravité, titre, correction, références par fournisseur)
RULES = {
    "REL-01": ("reliability", "moyenne", "Une seule zone de disponibilité",
               "Répartir calcul et bases sur au moins deux zones (groupes az ou zone).",
               {"aws": "REL10 : isoler les pannes, déployer sur plusieurs zones", "azure": "RE:05 : redondance",
                "gcp": "Fiabilité : déploiement multizone"}),
    "REL-02": ("reliability", "moyenne", "Instance unique",
               "Au moins deux instances (count), un groupe d'autoscaling ou une instance par zone.",
               {"aws": "REL10 et REL07 : redondance, adaptation à la demande", "azure": "RE:05 : redondance",
                "gcp": "Fiabilité : redondance des ressources"}),
    "REL-03": ("reliability", "moyenne", "Base sans réplique ni sauvegarde",
               "Déclarer la réplique (flux replication, count) ou le service de sauvegarde.",
               {"aws": "REL09 : sauvegarder les données ; REL10", "azure": "RE:05 et RE:09 : redondance, reprise",
                "gcp": "Fiabilité : sauvegarde et reprise des données"}),
    "REL-04": ("reliability", "basse", "Passerelle NAT unique pour plusieurs zones",
               "Une passerelle NAT par zone de disponibilité.",
               {"aws": "REL10 : une NAT Gateway par zone", "azure": "RE:05 : redondance",
                "gcp": "Fiabilité : redondance"}),
    "SEC-01": ("security", "haute", "Stockage dans un sous-réseau public",
               "Placer bases et stockages dans un sous-réseau privé.",
               {"aws": "SEC05 : couches réseau", "azure": "SE:04 : segmentation", "gcp": "Sécurité : réseau"}),
    "SEC-02": ("security", "haute", "Stockage atteint depuis l'extérieur",
               "Passer par un service applicatif ou une passerelle authentifiée.",
               {"aws": "SEC05 : couches réseau", "azure": "SE:04 et SE:06 : segmentation, contrôles réseau",
                "gcp": "Sécurité : réseau"}),
    "SEC-03": ("security", "moyenne", "Flux non chiffré à travers une frontière",
               "Chiffrer le flux (\"encrypted\": true, ou protocole HTTPS, TLS...).",
               {"aws": "SEC09 : protéger les données en transit", "azure": "SE:07 : chiffrement",
                "gcp": "Sécurité : chiffrement en transit"}),
    "SEC-04": ("security", "haute", "Calcul exposé directement",
               "Passer par un équilibreur de charge ou une passerelle d'API.",
               {"aws": "SEC05 et SEC06 : réseau, protection du calcul", "azure": "SE:06 : contrôles réseau",
                "gcp": "Sécurité : réseau"}),
    "SEC-05": ("security", "moyenne", "Point d'entrée public sans WAF",
               "Ajouter le pare-feu applicatif du fournisseur devant le point d'entrée.",
               {"aws": "SEC05 : AWS WAF devant les points d'entrée",
                "azure": "SE:06 : WAF sur Front Door ou Application Gateway", "gcp": "Sécurité : Cloud Armor"}),
    "SEC-06": ("security", "basse", "Pas de coffre à secrets",
               "Ajouter le coffre à secrets du fournisseur (identifiants des bases, clés d'API).",
               {"aws": "SEC02 : stocker et utiliser les secrets de façon sûre", "azure": "SE:09 : secrets d'application",
                "gcp": "Sécurité : Secret Manager"}),
    "SEC-07": ("security", "basse", "Pas de journal d'audit ni de détection",
               "Ajouter le journal d'audit ou la détection des menaces du fournisseur.",
               {"aws": "SEC04 : journalisation et détection (CloudTrail, GuardDuty)",
                "azure": "SE:10 : supervision et détection (Defender, Log Analytics)",
                "gcp": "Sécurité : Cloud Audit Logs, Security Command Center"}),
    "OPS-01": ("operations", "moyenne", "Pas de supervision",
               "Ajouter le service de supervision du fournisseur (métriques, journaux, alertes).",
               {"aws": "OPS04 : observabilité (CloudWatch)", "azure": "OE:07 : système de supervision (Azure Monitor)",
                "gcp": "Excellence opérationnelle : Cloud Monitoring, Cloud Logging"}),
    "PERF-01": ("performance", "basse", "Utilisateurs servis sans CDN",
                "Ajouter le CDN du fournisseur devant le contenu public.",
                {"aws": "PERF04 : réseau et diffusion (CloudFront)", "azure": "Efficacité des performances : Front Door",
                 "gcp": "Performances : Cloud CDN"}),
    "COST-01": ("cost", "basse", "Capacité fixe sans autoscaling",
                "Ajuster la capacité à la demande : groupe d'autoscaling, VMSS, HPA ou service serverless.",
                {"aws": "COST09 et SUS02 : aligner l'offre sur la demande", "azure": "CO:12 et PE:05 : mise à l'échelle",
                 "gcp": "Coûts et durabilité : autoscaling"}),
    "CONV-01": ("conventions", "moyenne", "Imbrication des groupes inversée",
                "Respecter l'ordre des groupes du fournisseur.", CONVENTION_REF),
    "CONV-02": ("conventions", "moyenne", "Groupe hors de son conteneur",
                "Placer le groupe dans son conteneur (sous-réseau dans un VPC, zone dans une région...).",
                CONVENTION_REF),
    "CONV-03": ("conventions", "basse", "Ressource posée dans le VPC hors sous-réseau",
                "Placer instances et bases dans un sous-réseau.", CONVENTION_REF),
    "CONV-04": ("conventions", "basse", "Service régional ou global dans un sous-réseau",
                "Le dessiner dans la région hors VPC ; accès privé : endpoint privé dans le sous-réseau.",
                CONVENTION_REF),
    "CONV-05": ("conventions", "moyenne", "Service d'un autre fournisseur dans le groupe",
                "Faire un groupe par fournisseur.", CONVENTION_REF),
    "CONV-06": ("conventions", "basse", "Icône générique chez un fournisseur",
                "Utiliser le type officiel du fournisseur (--types de cloud_build.py).", CONVENTION_REF),
    "SEC-08": ("security", "haute", "Hébergeur sans la qualification exigée",
               "Choisir un hébergeur et une offre qualifiés (shared/providers.json), ou accepter l'écart avec sa raison.",
               {}),
}

# Hébergeurs souverains (catalogue commun shared/providers.json, copié dans lib/) : rôles de leurs services et
# de leurs groupes, pour appliquer les mêmes règles ; repères AWS faute de cadre Well-Architected propre.
CATALOG = json.loads((HERE / "lib" / "providers.json").read_text(encoding="utf-8"))
HOSTS = {k: v for k, v in CATALOG["providers"].items() if "diagram" in v}
_SERVICES = {k: v for k, v in CATALOG["diagram"]["services"].items() if not k.startswith("_")}
_GROUPS = {k: v for k, v in CATALOG["diagram"]["groups"].items() if not k.startswith("_")}


def host_types(role: str, host: str | None = None) -> set[str]:
    return {f"{h}:{s}" for h in ([host] if host else HOSTS) for s, v in _SERVICES.items() if role in v["roles"]}


def host_groups(kind: str) -> set[str]:
    return {f"{h}:{g}" for h in HOSTS for g, v in _GROUPS.items() if v["as"] == kind}


VM |= host_types("vm")
SERVERLESS |= host_types("serverless")
DATABASES |= host_types("database")
ENTRY |= host_types("entry")
OUTSIDE_SUBNET |= host_types("managed")
for _role, _by_cloud in ROLES.items():
    _by_cloud.update({h: host_types(_role, h) for h in HOSTS})
REGIONS |= host_groups("region")
ZONES |= host_groups("zone")
NETWORKS |= host_groups("network")
SUBNETS |= host_groups("subnet")
_HOST_RANK = {"project": 0, "region": 1, "network": 2, "zone": 3, "subnet": 4}
for _host in HOSTS:
    for _g, _v in _GROUPS.items():
        RANK[f"{_host}:{_g}"] = _HOST_RANK[_v["as"]]
        if _v["as"] == "subnet":
            REQUIRED[f"{_host}:{_g}"] = host_groups("network")
        elif _v["as"] == "zone":
            REQUIRED[f"{_host}:{_g}"] = host_groups("region") | host_groups("network")
    FRAMEWORKS[_host] = f"{HOSTS[_host]['name']} (repères AWS Well-Architected, pas de cadre propre) :"
    CONVENTION_REF[_host] = ("pas de jeu d'icônes officiel : formes de la charte ; "
                             "projet > région > réseau privé > zone, sous-réseau")
CLOUDS = CLOUDS + tuple(HOSTS)
for _rule, (_pillar, _, _, _, _refs) in RULES.items():
    if _rule == "SEC-08":
        _refs.update({c: "qualification exigée par les exigences (SecNumCloud : référentiel de l'ANSSI ; "
                         "HDS : hébergement de données de santé)" for c in (*CLOUDS, "k8s")})
    elif _pillar != "conventions" and "aws" in _refs:
        _refs.update({h: _refs["aws"] for h in HOSTS})
# Ce qui ne se voit pas sur un schéma : à demander en revue.
OFF_DIAGRAM = {
    "operations": "infrastructure en code, déploiements automatisés et réversibles, procédures d'exploitation",
    "security": "moindre privilège IAM, chiffrement au repos et gestion des clés, correctifs, réponse aux incidents",
    "reliability": "quotas, tests de reprise (PRA), RPO et RTO mesurés, dépendances externes",
    "performance": "choix des tailles d'instance, tests de charge, cache applicatif",
    "cost": "étiquetage et suivi des coûts, réservations ou engagements, cycle de vie des données",
    "sustainability": "choix de la région, taux d'utilisation, rétention des données",
}
TLS = ("HTTPS", "TLS", "MTLS", "SSH", "IPSEC", "SFTP", "AMQPS", "GRPCS")


def provider(kind: str) -> str | None:
    prefix = kind.split(":", 1)[0] if ":" in kind else None
    return prefix if prefix in FRAMEWORKS else None


def replicated(node: dict) -> bool:
    count = node.get("count")
    if isinstance(count, int):
        return count > 1
    return bool(count) and str(count).strip() not in ("1", "0")


def check(spec: dict) -> tuple[list[dict], list[str], set[str]]:
    _, pages, errors, _ = CLOUD.build(spec, None)
    findings, seen = [], set()
    clouds = {spec.get("provider")} | {p.get("provider") for p in spec.get("pages", [])}
    types_all: set[str] = set()
    groups_all: set[str] = set()
    for _, b, _ in pages:
        types_all |= {n["type"] for n in b.nodes.values()}
        groups_all |= {g["type"] for g in b.groups.values()}
    clouds |= {provider(t) for t in types_all | groups_all}
    clouds = {c for c in clouds if c}

    def add(rule, element, message, where=None):
        key = (rule, element)
        if key in seen:
            return
        seen.add(key)
        pillar, severity, title, fix, refs = RULES[rule]
        # Conventions : le guide d'icônes du fournisseur ; piliers : le cadre Well-Architected et la question.
        plain = pillar == "conventions" or rule == "SEC-08"
        named = (lambda c: refs[c]) if plain else (lambda c: f"{FRAMEWORKS[c]} {refs[c]}")
        if where in refs:
            ref = named(where)
        else:
            # Sans fournisseur connu : les repères des trois grands cadres.
            ref = " ; ".join(named(c) for c in CLOUDS if c in refs and (
                c in clouds or (not clouds & set(CLOUDS) and c in ("aws", "azure", "gcp"))))
        findings.append({"rule": rule, "pillar": pillar, "severity": severity, "element": element,
                         "message": f"{title} : {message}", "fix": fix, "ref": ref, "accepted": None})

    multi = len(pages) > 1
    for name, b, flows in pages:
        def ancestors(cid):
            chain, cur = [], b.parent_of.get(cid, "1")
            while cur != "1":
                chain.append(cur)
                cur = b.parent_of.get(cur, "1")
            return chain

        def gtypes(cid):
            return [b.groups[g]["type"] for g in ancestors(cid)]

        def where(cid):
            node = b.nodes.get(cid)
            own = provider(node["type"]) if node else provider(b.groups[cid]["type"])
            if own:
                return own
            near = next((provider(t) for t in gtypes(cid) if provider(t)), None)
            return near or (spec.get("provider") if spec.get("provider") in FRAMEWORKS else None)

        def generic_zone(gid):
            # « zone » chez Azure ou GCP qui contient des régions ou un réseau : simple regroupement, pas une AZ.
            return any(b.groups[g]["type"] in REGIONS | NETWORKS for g in b.groups if gid in ancestors(g))

        def at(element):
            return f"{name}/{element}" if multi else element

        label = {**{k: v["label"] for k, v in b.nodes.items()}, **{k: v["label"] for k, v in b.groups.items()}}
        types = {n["type"] for n in b.nodes.values()}
        view = b.view
        # Vue pipeline (CI/CD, data) : chaîne d'outils, pas un déploiement ; seuls les flux sont contrôlés.
        layout = view != "pipeline"
        # Doublons même type et même libellé (une instance par zone) : comptent comme redondance.
        twins: dict[tuple, int] = {}
        for node in b.nodes.values():
            base = node["label"].split(" ×")[0]
            twins[(node["type"], base)] = twins.get((node["type"], base), 0) + 1
        repl = {f["from"] for f in flows if f["style"] == "replication"} | \
               {f["to"] for f in flows if f["style"] == "replication"}

        for gid, group in b.groups.items() if layout else ():
            gt, chain = group["type"], gtypes(gid)
            if gt in ZONES and generic_zone(gid):
                continue
            for parent in chain:
                if gt in RANK and parent in RANK and provider(gt) == provider(parent) and RANK[parent] > RANK[gt]:
                    add("CONV-01", at(gid), f"{group['label']} ({gt}) est dans {parent}", provider(gt))
                    break
            if gt in REQUIRED and not REQUIRED[gt] & set(chain):
                add("CONV-02", at(gid), f"{group['label']} ({gt}) hors de {' ou '.join(sorted(REQUIRED[gt]))}",
                    provider(gt))
            regional = any(t in REGIONS for t in chain) or \
                any(b.groups[g]["type"] in REGIONS for g in b.groups if gid in ancestors(g))
            if gt in REGIONS or (gt in NETWORKS and not regional):
                inside = [n for n in b.nodes if gid in ancestors(n)]
                heavy = [n for n in inside if b.nodes[n]["type"] in VM | DATABASES]
                zones = [g for g in b.groups if gid in ancestors(g) and b.groups[g]["type"] in ZONES
                         and not generic_zone(g)]
                if heavy and len(zones) < 2 and view in ("deployment", "network", "dr"):
                    add("REL-01", at(gid),
                        f"{group['label']} : {len(zones)} zone pour {', '.join(label[n] for n in heavy[:3])}",
                        provider(gt))
                nats = [n for n in inside if b.nodes[n]["type"] == "aws:nat-gateway"]
                capacity = sum(int(b.nodes[n]["count"]) if isinstance(b.nodes[n]["count"], int) else 1 for n in nats)
                if nats and len(zones) > capacity:
                    add("REL-04", at(gid), f"{capacity} NAT pour {len(zones)} zones", "aws")

        for nid, node in b.nodes.items() if layout else ():
            nt, chain = node["type"], gtypes(nid)
            if node["kind"] is None:
                continue
            base = node["label"].split(" ×")[0]
            scaled = bool(set(chain) & SCALING_GROUPS) or bool(types & SCALING_NODES)
            spread = replicated(node) or twins[(nt, base)] > 1
            if nt in VM and not spread and not scaled:
                add("REL-02", at(nid), node["label"], where(nid))
            if nt in VM and spread and not scaled and not nt.startswith("k8s:"):
                add("COST-01", at(nid), node["label"], where(nid))
            if nt in DATABASES and not spread and nid not in repl and \
                    not any(types_all & roles for roles in ROLES["backup"].values()):
                add("REL-03", at(nid), node["label"], where(nid))
            if node["kind"] == "store" and "aws:public-subnet" in chain:
                add("SEC-01", at(nid), node["label"], "aws")
            direct = b.parent_of.get(nid)
            if direct in b.groups and b.groups[direct]["type"] in NETWORKS and nt in VM | DATABASES:
                add("CONV-03", at(nid), f"{node['label']} dans {b.groups[direct]['label']}", where(nid))
            if nt in OUTSIDE_SUBNET and set(chain) & SUBNETS:
                add("CONV-04", at(nid), node["label"], where(nid))
            own = provider(nt)
            near = next((provider(t) for t in chain if provider(t) in CLOUDS), None)
            if own in CLOUDS and near and near != own:
                add("CONV-05", at(nid), f"{node['label']} ({own}) dans un groupe {near}", own)
            if nt in ("server", "db", "queue") and any(provider(t) in CLOUDS for t in chain):
                add("CONV-06", at(nid), f"{node['label']} ({nt})", where(nid))

        for f in flows:
            src, dst = b.nodes.get(f["from"]), b.nodes.get(f["to"])
            if not src or not dst:
                continue
            tag = at(f"F{f['n']}")
            text = f"F{f['n']} {label[f['from']]} → {label[f['to']]}"
            if layout and src["kind"] == "external" and dst["kind"] == "store":
                add("SEC-02", tag, text, where(f["to"]))
            if layout and src["kind"] == "external" and dst["type"] in VM:
                add("SEC-04", tag, text, where(f["to"]))
            proto = f"{f['protocol']} {f['port']}".upper()
            # Appel d'un service managé (S3, SQS, Key Vault...) : API HTTPS du fournisseur, chiffrée par défaut.
            managed = src["type"] in OUTSIDE_SUBNET or dst["type"] in OUTSIDE_SUBNET
            encrypted = f["encrypted"] if f["encrypted"] is not None else (
                True if managed or any(t in proto for t in TLS) else None)
            if f["crosses"] and encrypted is not True and f["style"] != "replication":
                add("SEC-03", tag, f"{text} ({', '.join(f['crosses'])})", where(f["to"]))
            if layout and src["kind"] == "external" and dst["type"] in ENTRY:
                cloud = where(f["to"])
                if cloud in CLOUDS and not types_all & ROLES["waf"][cloud]:
                    add("SEC-05", tag, text, cloud)
                if src["type"] == "user" and cloud in CLOUDS and not types_all & ROLES["cdn"][cloud]:
                    add("PERF-01", tag, text, cloud)

    # Présence des services transverses, sur l'ensemble de la description, pour chaque fournisseur.
    workload = {v for _, b, _ in pages if b.view in ("deployment", "network", "dr", "threats")
                for v in (provider(n["type"]) for n in b.nodes.values()) if v in CLOUDS}
    for cloud in sorted(workload):
        mine = {t for t in types_all if t.startswith(cloud + ":")}
        if not mine & ROLES["monitoring"][cloud]:
            add("OPS-01", cloud, "aucun service de supervision", cloud)
        if not mine & ROLES["audit"][cloud]:
            add("SEC-07", cloud, "aucun journal d'audit ni détection", cloud)
        if mine & (VM | SERVERLESS) and (mine | types_all) & DATABASES and not mine & ROLES["secrets"][cloud]:
            add("SEC-06", cloud, "calcul et base sans coffre à secrets", cloud)
    # Qualifications exigées de chaque hébergeur décrit (catalogue commun des hébergeurs).
    required = list(dict.fromkeys(spec.get("qualifications") or []))
    for cloud in sorted(c for c in clouds if c in CATALOG["providers"]) if required else ():
        info = CATALOG["providers"][cloud]
        missing = [q for q in required if q not in info["qualifications"]]
        if missing:
            pending = [q for q in missing if q in info.get("pending", [])]
            add("SEC-08", cloud, f"{info['name']} sans {', '.join(missing)}"
                + (f" (qualification en cours : {', '.join(pending)})" if pending else ""), cloud)
    return findings, errors, clouds


def hosting_notes(spec: dict, clouds: set[str]) -> list[str]:
    """Avertissements sur les qualifications exigées : offre à vérifier, hébergeur hors catalogue."""
    required = spec.get("qualifications") or []
    if not required:
        return []
    known = CATALOG["providers"]
    notes = [f"{known[c]['name']} : {known[c]['note']}" for c in sorted(clouds)
             if c in known and known[c].get("note") and set(required) <= set(known[c]["qualifications"])]
    unknown = sorted(c for c in clouds if c not in known and c != "k8s")
    if unknown:
        notes.append(f"qualifications non vérifiées pour {', '.join(unknown)} (absent du catalogue des hébergeurs)")
    return notes


def accept(findings: list[dict], accepted: dict, warnings: list[str]) -> None:
    used = set()
    for finding in findings:
        for key in (f"{finding['rule']}@{finding['element']}", finding["rule"]):
            if key in accepted:
                finding["accepted"] = accepted[key]
                used.add(key)
                break
    warnings += [f"acceptation « {k} » sans constat correspondant" for k in accepted if k not in used]


def cell(text) -> str:
    return str(text).replace("|", "/").replace("\n", " ")


def markdown(title: str, findings: list[dict], clouds: set[str], rules: int) -> str:
    frameworks = ", ".join(FRAMEWORKS[c].removesuffix(" :") for c in ("aws", "azure", "gcp", "k8s", *HOSTS)
                           if c in clouds) or "aucun fournisseur"
    lines = [f"# Revue Well-Architected : {title}", "",
             f"Contrôle automatique du schéma par `wa_check.py` ({rules} règles ; cadres : {frameworks}). "
             "Ce n'est pas une revue complète : les points hors du schéma sont listés à la fin.", "",
             "## Synthèse", "", "| Pilier | Haute | Moyenne | Basse | Acceptés |", "| --- | --- | --- | --- | --- |"]
    for key, name in PILLARS.items():
        mine = [f for f in findings if f["pillar"] == key]
        if key == "sustainability":
            mine = [f for f in findings if f["rule"] == "COST-01"]
        open_ = [f for f in mine if not f["accepted"]]
        lines.append(f"| {name} | " + " | ".join(str(sum(f["severity"] == s for f in open_)) for s in SEVERITIES)
                     + f" | {len(mine) - len(open_)} |")
    lines += ["", "## Constats", ""]
    if not findings:
        lines.append("Aucun constat.")
    else:
        lines += ["| ID | Règle | Pilier | Gravité | Élément | Constat | Correction | Référence | Statut |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        order = sorted(findings, key=lambda f: (SEVERITIES.index(f["severity"]), f["rule"]))
        for index, f in enumerate(order, 1):
            status = f"accepté : {f['accepted']}" if f["accepted"] else "à traiter"
            lines.append(f"| W{index:02d} | {f['rule']} | {PILLARS[f['pillar']]} | {f['severity']} | "
                         f"{cell(f['element'])} | {cell(f['message'])} | {cell(f['fix'])} | {cell(f['ref'])} | "
                         f"{cell(status)} |")
    lines += ["", "## À vérifier hors du schéma", ""]
    lines += [f"- **{PILLARS[k]}** : {v}." for k, v in OFF_DIAGRAM.items()]
    return "\n".join(lines) + "\n"


def list_rules() -> str:
    return "\n".join(f"{rule} {PILLARS[p]} ({s}) : {title}" for rule, (p, s, title, _, _) in RULES.items())


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, help="fichier Markdown (défaut : <sujet>.wa.md)")
    parser.add_argument("--fail-on", choices=SEVERITIES + ("aucune",), default="haute",
                        help="code de sortie 1 dès un constat non accepté de cette gravité ou plus (défaut : haute)")
    parser.add_argument("--scope", choices=("tout", "piliers", "conventions"), default="tout",
                        help="règles appliquées : piliers à la définition de l'architecture, conventions au dessin "
                             "(défaut : tout)")
    parser.add_argument("--rules", action="store_true", help="liste les règles, puis s'arrête")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if args.rules:
        print(list_rules())
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
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
    warnings: list[str] = []
    findings, errors, clouds = check(spec)
    if args.scope != "tout":
        findings = [f for f in findings if (f["pillar"] == "conventions") == (args.scope == "conventions")]
    rules = {r for r, v in RULES.items() if args.scope == "tout" or (v[0] == "conventions") == (args.scope == "conventions")}
    warnings += hosting_notes(spec, clouds)
    accept(findings, spec.get("accept") or {}, warnings)
    findings.sort(key=lambda f: (SEVERITIES.index(f["severity"]), f["rule"]))
    open_ = [f for f in findings if not f["accepted"]]
    counts = {s: sum(f["severity"] == s for f in open_) for s in SEVERITIES}
    counts["acceptés"] = len(findings) - len(open_)
    # option-a.cloud.json (architecture-options) -> option-a.wa.md
    out = args.out or args.spec.with_name(args.spec.name.removesuffix(".json").removesuffix(".cloud") + ".wa.md")
    result = {"input": str(args.spec), "output": None, "providers": sorted(clouds), "scope": args.scope, "rules": len(rules),
              "counts": counts, "findings": findings, "errors": errors, "warnings": warnings}
    if not errors:
        out.write_text(markdown(str(spec.get("title", "architecture")), findings, clouds, len(rules)),
                       encoding="utf-8")
        result["output"] = str(out)
    print(json.dumps(result, ensure_ascii=False))
    limit = SEVERITIES.index(args.fail_on) if args.fail_on in SEVERITIES else -1
    failing = any(SEVERITIES.index(f["severity"]) <= limit for f in open_)
    return 1 if errors or failing else 0


if __name__ == "__main__":
    sys.exit(main())
