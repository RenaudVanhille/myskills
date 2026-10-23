# /// script
# requires-python = ">=3.10"
# dependencies = ["pyyaml>=6"]
# ///
"""Écrit la description d'un schéma cloud (pour cloud_build.py) depuis le code d'infrastructure.

Lit des fichiers Terraform (.tf : AWS, Azure, Google), des fichiers
docker-compose et des manifestes Kubernetes, fichiers ou dossiers. Les
ressources connues deviennent des services aux types de cloud_build.py, les
réseaux des groupes (VPC, VNet, sous-réseaux, namespaces), les références
entre ressources des flux. Les ressources sans équivalent (rôles IAM, règles
de pare-feu...) sont comptées dans `ignored`. La description écrite est
validée contre le schéma d'entrée de cloud_build.py et construite à blanc
avant d'être rendue.

    uv run scripts/iac_import.py SOURCE [...] [--out SUJET.json] [--title T]
"""

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE / "lib"))
sys.path.insert(0, str(HERE))
from spec_schema import validate  # noqa: E402

# Ressource Terraform -> type de service de cloud_build.py.
TF_NODES = {
    "aws_lambda_function": "aws:lambda", "aws_sqs_queue": "aws:sqs", "aws_sns_topic": "aws:sns",
    "aws_s3_bucket": "aws:s3", "aws_db_instance": "aws:rds", "aws_rds_cluster": "aws:aurora",
    "aws_dynamodb_table": "aws:dynamodb", "aws_ecs_service": "aws:ecs", "aws_eks_cluster": "aws:eks",
    "aws_instance": "aws:ec2", "aws_lb": "aws:alb", "aws_alb": "aws:alb", "aws_elb": "aws:elb",
    "aws_cloudfront_distribution": "aws:cloudfront", "aws_api_gateway_rest_api": "aws:api-gateway",
    "aws_apigatewayv2_api": "aws:api-gateway", "aws_elasticache_cluster": "aws:elasticache",
    "aws_elasticache_replication_group": "aws:elasticache", "aws_kinesis_stream": "aws:kinesis",
    "aws_cognito_user_pool": "aws:cognito", "aws_secretsmanager_secret": "aws:secrets-manager",
    "aws_kms_key": "aws:kms", "aws_route53_zone": "aws:route53", "aws_wafv2_web_acl": "aws:waf",
    "aws_nat_gateway": "aws:nat-gateway", "aws_internet_gateway": "aws:internet-gateway",
    "aws_sfn_state_machine": "aws:step-functions", "aws_cloudwatch_event_rule": "aws:eventbridge",
    "aws_efs_file_system": "aws:efs", "aws_ecr_repository": "aws:ecr", "aws_msk_cluster": "aws:msk",
    "aws_opensearch_domain": "aws:opensearch", "aws_redshift_cluster": "aws:redshift",
    "aws_docdb_cluster": "aws:documentdb", "aws_batch_job_queue": "aws:batch",
    "azurerm_linux_function_app": "azure:functions", "azurerm_windows_function_app": "azure:functions",
    "azurerm_function_app": "azure:functions", "azurerm_linux_web_app": "azure:app-service",
    "azurerm_windows_web_app": "azure:app-service", "azurerm_app_service": "azure:app-service",
    "azurerm_kubernetes_cluster": "azure:aks", "azurerm_mssql_database": "azure:sql-database",
    "azurerm_cosmosdb_account": "azure:cosmos-db", "azurerm_storage_account": "azure:storage-account",
    "azurerm_servicebus_namespace": "azure:service-bus", "azurerm_eventhub_namespace": "azure:event-hubs",
    "azurerm_key_vault": "azure:key-vault", "azurerm_redis_cache": "azure:redis",
    "azurerm_postgresql_flexible_server": "azure:postgresql", "azurerm_mysql_flexible_server": "azure:mysql",
    "azurerm_api_management": "azure:api-management", "azurerm_application_gateway": "azure:application-gateway",
    "azurerm_cdn_frontdoor_profile": "azure:front-door", "azurerm_frontdoor": "azure:front-door",
    "azurerm_linux_virtual_machine": "azure:vm", "azurerm_windows_virtual_machine": "azure:vm",
    "azurerm_container_registry": "azure:acr", "azurerm_container_group": "azure:container-instances",
    "azurerm_static_web_app": "azure:static-web-apps", "azurerm_logic_app_workflow": "azure:logic-apps",
    "google_cloud_run_service": "gcp:cloud-run", "google_cloud_run_v2_service": "gcp:cloud-run",
    "google_cloudfunctions_function": "gcp:cloud-functions", "google_cloudfunctions2_function": "gcp:cloud-functions",
    "google_sql_database_instance": "gcp:cloud-sql", "google_storage_bucket": "gcp:cloud-storage",
    "google_pubsub_topic": "gcp:pubsub", "google_container_cluster": "gcp:gke",
    "google_compute_instance": "gcp:compute-engine", "google_bigquery_dataset": "gcp:bigquery",
    "google_redis_instance": "gcp:memorystore", "google_spanner_instance": "gcp:spanner",
    "google_firestore_database": "gcp:firestore", "google_artifact_registry_repository": "gcp:artifact-registry",
}
# Ressource Terraform -> type de groupe ; les sous-réseaux AWS sont publics ou privés selon leur adressage.
TF_GROUPS = {"aws_vpc": "aws:vpc", "aws_subnet": "aws:private-subnet", "azurerm_virtual_network": "azure:vnet",
             "azurerm_subnet": "azure:subnet", "azurerm_resource_group": "azure:resource-group",
             "google_compute_network": "gcp:vpc", "google_compute_subnetwork": "gcp:subnet"}
# Ressources de liaison : (attribut source, attribut cible) d'un flux entre deux services.
TF_LINKS = {"aws_lambda_event_source_mapping": ("event_source_arn", "function_name"),
            "aws_sns_topic_subscription": ("topic_arn", "endpoint"),
            "aws_cloudwatch_event_target": ("rule", "arn"),
            "aws_lambda_permission": ("source_arn", "function_name"),
            "google_pubsub_subscription": ("topic", "push_config")}
LABEL_ATTRS = ("name", "function_name", "identifier", "cluster_identifier", "bucket", "domain_name", "cluster_name")
TF_PROVIDERS = {"aws": "aws", "azurerm": "azure", "google": "gcp"}
RESOURCE = re.compile(r'^\s*resource\s+"([A-Za-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"\s*\{', re.M)
PROVIDER_BLOCK = re.compile(r'^\s*provider\s+"([A-Za-z0-9_]+)"\s*\{', re.M)
REFERENCE = re.compile(r"\b((?:aws|azurerm|google)_[a-z0-9_]+)\.([A-Za-z0-9_-]+)\b")

K8S_NODES = {"Deployment": "k8s:deploy", "StatefulSet": "k8s:sts", "DaemonSet": "k8s:ds", "ReplicaSet": "k8s:rs",
             "Pod": "k8s:pod", "Job": "k8s:job", "CronJob": "k8s:cronjob", "Service": "k8s:svc",
             "Ingress": "k8s:ing", "ConfigMap": "k8s:cm", "Secret": "k8s:secret",
             "HorizontalPodAutoscaler": "k8s:hpa", "PersistentVolumeClaim": "k8s:pvc", "PersistentVolume": "k8s:pv",
             "NetworkPolicy": "k8s:netpol", "ServiceAccount": "k8s:sa", "CustomResourceDefinition": "k8s:crd"}
WORKLOADS = {"Deployment", "StatefulSet", "DaemonSet", "ReplicaSet", "Job", "CronJob", "Pod"}
# Image docker-compose -> type générique.
COMPOSE_IMAGES = [(("postgres", "mysql", "mariadb", "mongo", "redis", "valkey", "memcached", "cassandra",
                    "elasticsearch", "opensearch", "minio", "mssql", "oracle", "neo4j", "influxdb"), "db"),
                  (("rabbitmq", "kafka", "nats", "activemq", "pulsar", "mosquitto", "redpanda"), "queue")]
COMPOSE_NAMES = re.compile(r"^(docker-)?compose(\.[\w-]+)?\.ya?ml$", re.I)


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "x"


class Model:
    """Services, groupes et flux lus dans toutes les sources, avant mise en forme."""

    def __init__(self):
        self.nodes: dict[str, dict] = {}    # id -> {type, label, count, parent}
        self.groups: dict[str, dict] = {}   # id -> {type, label, parent}
        self.flows: list[dict] = []
        self.ignored: Counter = Counter()
        self.regions: list[tuple[str, str]] = []  # (fournisseur, région)
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def flow(self, source: str, target: str, **extra) -> None:
        if source != target and not any(f["from"] == source and f["to"] == target for f in self.flows):
            self.flows.append({"from": source, "to": target, **extra})


# --- Terraform ---------------------------------------------------------------
def block_body(text: str, start: int) -> str:
    """Corps d'un bloc HCL dont l'accolade ouvrante précède start ; ignore les chaînes et commentaires."""
    depth, i, quote = 1, start, False
    while i < len(text) and depth:
        char = text[i]
        if quote:
            if char == "\\":
                i += 1
            elif char == '"':
                quote = False
        elif char == '"':
            quote = True
        elif char == "#" or text.startswith("//", i):
            i = text.find("\n", i)
            if i < 0:
                break
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
        i += 1
    return text[start:i - 1] if not depth else text[start:]


def literal(body: str, attr: str) -> str | None:
    match = re.search(rf'^\s*{attr}\s*=\s*"([^"$]*)"\s*$', body, re.M)
    return match.group(1) if match else None


def read_terraform(path: Path, model: Model, resources: dict) -> None:
    text = path.read_text(encoding="utf-8")
    for match in PROVIDER_BLOCK.finditer(text):
        provider = TF_PROVIDERS.get(match.group(1))
        region = literal(block_body(text, match.end()), "region")
        if provider and region:
            model.regions.append((provider, region))
    for match in RESOURCE.finditer(text):
        kind, name = match.groups()
        key = f"{kind}.{name}"
        if key in resources:
            model.errors.append(f"{path.name} : ressource « {key} » déclarée deux fois")
            continue
        resources[key] = {"kind": kind, "name": name, "body": block_body(text, match.end()), "file": path.name}


def label_of(res: dict) -> str:
    for attr in LABEL_ATTRS:
        value = literal(res["body"], attr)
        if value:
            return value
    return res["name"]


def tf_refs(body: str, resources: dict) -> list[str]:
    found = []
    for kind, name in REFERENCE.findall(body):
        key = f"{kind}.{name}"
        if key in resources and key not in found:
            found.append(key)
    return found


def attr_refs(body: str, attr: str, resources: dict) -> list[str]:
    """Références dans la valeur d'un attribut (sur une ligne, ou un bloc du même nom)."""
    match = re.search(rf"^\s*{attr}\s*(=\s*(.*)$|\{{)", body, re.M)
    if not match:
        return []
    value = match.group(2) if match.group(2) is not None else block_body(body, match.end())
    return tf_refs(value, resources)


def build_terraform(resources: dict, model: Model) -> None:
    ids = {key: slug(res["name"]) for key, res in resources.items()}
    taken: Counter = Counter(ids.values())
    for key, res in resources.items():
        if taken[ids[key]] > 1:  # même nom pour deux types : on préfixe par le type court
            ids[key] = slug(res["kind"].split("_", 1)[1] + "-" + res["name"])
    groups = {key for key, res in resources.items() if res["kind"] in TF_GROUPS}
    nodes = {key for key, res in resources.items() if res["kind"] in TF_NODES}
    for key in sorted(groups, key=lambda k: resources[k]["kind"] not in ("aws_vpc", "azurerm_resource_group")):
        res = resources[key]
        kind = TF_GROUPS[res["kind"]]
        if res["kind"] == "aws_subnet" and re.search(r"map_public_ip_on_launch\s*=\s*true", res["body"]):
            kind = "aws:public-subnet"
        label = literal(res["body"], "name") or res["name"]
        cidr = literal(res["body"], "cidr_block")
        parents = [r for r in tf_refs(res["body"], resources) if r in groups]
        model.groups[ids[key]] = {"type": kind, "label": f"{label} {cidr}" if cidr else label,
                                  "parent": ids[parents[0]] if parents else None}
    subnet_attrs = ("subnet_id", "subnet_ids", "subnets", "subnetwork", "vpc_config", "network_configuration",
                    "network_interface", "virtual_network_subnet_id", "default_node_pool", "network")
    for key in nodes:
        res = resources[key]
        place = []
        for attr in subnet_attrs:
            place += [r for r in attr_refs(res["body"], attr, resources) if r in groups]
        if not place:
            place = [r for r in tf_refs(res["body"], resources) if r in groups]
        if not place:  # par une ressource intermédiaire : groupe de sous-réseaux, interface réseau...
            for ref in tf_refs(res["body"], resources):
                if ref not in nodes:
                    place += [r for r in tf_refs(resources[ref]["body"], resources) if r in groups]
        # Le groupe le plus profond : un sous-réseau plutôt que son réseau.
        place.sort(key=lambda r: 0 if "subnet" in resources[r]["kind"] else 1)
        count = re.search(r"^\s*(?:count|desired_count|instance_count|node_count)\s*=\s*(\d+)\s*$", res["body"], re.M)
        model.nodes[ids[key]] = {"type": TF_NODES[res["kind"]], "label": label_of(res),
                                 "count": int(count.group(1)) if count and int(count.group(1)) > 1 else None,
                                 "parent": ids[place[0]] if place else None}
    for key in nodes:
        for ref in tf_refs(resources[key]["body"], resources):
            if ref in nodes:
                model.flow(ids[key], ids[ref])
    for key, res in resources.items():
        if res["kind"] in TF_LINKS:
            source_attr, target_attr = TF_LINKS[res["kind"]]
            sources = [r for r in attr_refs(res["body"], source_attr, resources) if r in nodes]
            targets = [r for r in attr_refs(res["body"], target_attr, resources) if r in nodes]
            if sources and targets:
                model.flow(ids[sources[0]], ids[targets[0]], style="async")
                continue
        if key not in nodes and key not in groups:
            model.ignored[res["kind"]] += 1


# --- docker-compose ----------------------------------------------------------
def read_compose(path: Path, data: dict, model: Model) -> None:
    services = data.get("services")
    if not isinstance(services, dict):
        model.errors.append(f"{path.name} : pas de section services")
        return
    project = str(data.get("name") or path.parent.name or "compose")
    group = slug("compose-" + project)
    model.groups[group] = {"type": "env", "label": project, "parent": None}
    exposed = []
    for name, service in services.items():
        service = service or {}
        image = str(service.get("image") or name).lower().rsplit("/", 1)[-1]
        kind = next((t for words, t in COMPOSE_IMAGES if any(w in image for w in words)), "service")
        replicas = (service.get("deploy") or {}).get("replicas")
        model.nodes[slug(name)] = {"type": kind, "label": name,
                                   "count": replicas if isinstance(replicas, int) and replicas > 1 else None,
                                   "parent": group}
        ports = [str(p).split(":")[0] for p in service.get("ports") or [] if ":" in str(p)]
        if ports:
            exposed.append((slug(name), ports[0]))
    for name, service in services.items():
        depends = (service or {}).get("depends_on") or []
        for target in (depends if isinstance(depends, list) else list(depends)) + list((service or {}).get("links") or []):
            target = str(target).split(":")[0]
            if target in services:
                model.flow(slug(name), slug(target))
            else:
                model.warnings.append(f"{path.name} : {name} dépend de « {target} », service inconnu")
    if exposed:
        model.nodes["utilisateurs"] = {"type": "user", "label": "Utilisateurs", "count": None, "parent": None}
        for target, port in exposed:
            port = port.split("/")[0].rsplit(":", 1)[-1]
            model.flow("utilisateurs", target, **({"port": int(port)} if port.isdigit() else {}))


# --- Kubernetes --------------------------------------------------------------
def pod_spec(doc: dict) -> dict:
    spec = doc.get("spec") or {}
    if doc["kind"] == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec") or {})
    if doc["kind"] == "Pod":
        return spec
    return ((spec.get("template") or {}).get("spec") or {})


def pod_labels(doc: dict) -> dict:
    if doc["kind"] == "Pod":
        return (doc.get("metadata") or {}).get("labels") or {}
    spec = doc.get("spec") or {}
    if doc["kind"] == "CronJob":
        spec = ((spec.get("jobTemplate") or {}).get("spec") or {})
    return (((spec.get("template") or {}).get("metadata") or {}).get("labels") or {})


def build_kubernetes(docs: list[dict], model: Model) -> None:
    cluster = "cluster"
    model.groups[cluster] = {"type": "k8s:cluster", "label": "Cluster Kubernetes", "parent": None}
    index = {}
    for doc in docs:
        meta = doc.get("metadata") or {}
        kind, name = doc["kind"], str(meta.get("name") or "?")
        if kind == "Namespace":
            model.groups.setdefault(slug("ns-" + name), {"type": "k8s:namespace", "label": name, "parent": cluster})
            continue
        if kind not in K8S_NODES:
            model.ignored[kind] += 1
            continue
        namespace = str(meta.get("namespace") or "default")
        group = slug("ns-" + namespace)
        model.groups.setdefault(group, {"type": "k8s:namespace", "label": namespace, "parent": cluster})
        nid = slug(f"{K8S_NODES[kind].split(':')[1]}-{name}")
        replicas = (doc.get("spec") or {}).get("replicas")
        model.nodes[nid] = {"type": K8S_NODES[kind], "label": f"{kind} {name}",
                            "count": replicas if isinstance(replicas, int) and replicas > 1 else None, "parent": group}
        index[(kind, namespace, name)] = (nid, doc)

    def find(kind: str, namespace: str, name) -> str | None:
        return index.get((kind, namespace, str(name)), (None,))[0]

    for (kind, namespace, name), (nid, doc) in index.items():
        spec = doc.get("spec") or {}
        if kind == "Ingress":
            for rule in spec.get("rules") or []:
                for path in ((rule.get("http") or {}).get("paths") or []):
                    backend = (path.get("backend") or {}).get("service") or {}
                    target = find("Service", namespace, backend.get("name") or path.get("backend", {}).get("serviceName"))
                    port = (backend.get("port") or {}).get("number")
                    if target:
                        model.flow(nid, target, **({"port": port} if isinstance(port, int) else {}))
        elif kind == "Service":
            selector = spec.get("selector") or {}
            port = next((p.get("targetPort") or p.get("port") for p in spec.get("ports") or []), None)
            for (other, other_ns, _), (oid, odoc) in index.items():
                labels = pod_labels(odoc) if other in WORKLOADS else {}
                if other in WORKLOADS and other_ns == namespace and selector and \
                        all(labels.get(k) == v for k, v in selector.items()):
                    model.flow(nid, oid, **({"port": port} if isinstance(port, int) else {}))
        elif kind == "HorizontalPodAutoscaler":
            ref = spec.get("scaleTargetRef") or {}
            target = find(str(ref.get("kind")), namespace, ref.get("name"))
            if target:
                model.flow(nid, target, label="ajuste", style="async")
        elif kind in WORKLOADS:
            pod = pod_spec(doc)
            for volume in pod.get("volumes") or []:
                claim = (volume.get("persistentVolumeClaim") or {}).get("claimName")
                for ref_kind, ref_name in (("PersistentVolumeClaim", claim),
                                           ("ConfigMap", (volume.get("configMap") or {}).get("name")),
                                           ("Secret", (volume.get("secret") or {}).get("secretName"))):
                    target = find(ref_kind, namespace, ref_name) if ref_name else None
                    if target:
                        model.flow(nid, target, label="monte" if ref_kind == "PersistentVolumeClaim" else "lit")
            for container in pod.get("containers") or []:
                for source in container.get("envFrom") or []:
                    for ref_kind, key in (("ConfigMap", "configMapRef"), ("Secret", "secretRef")):
                        target = find(ref_kind, namespace, (source.get(key) or {}).get("name"))
                        if target:
                            model.flow(nid, target, label="lit")
            for template in spec.get("volumeClaimTemplates") or []:
                claim = slug(f"pvc-{(template.get('metadata') or {}).get('name', 'data')}-{name}")
                model.nodes[claim] = {"type": "k8s:pvc", "label": f"PVC {(template.get('metadata') or {}).get('name', 'data')}",
                                      "count": None, "parent": model.nodes[nid]["parent"]}
                model.flow(nid, claim, label="monte")


# --- lecture des sources -----------------------------------------------------
def expand(paths: list[Path]) -> list[Path]:
    files = []
    for path in paths:
        if path.is_dir():
            files += sorted(p for p in path.rglob("*") if p.is_file() and p.suffix.lower() in (".tf", ".yaml", ".yml")
                            and not any(part.startswith(".") for part in p.relative_to(path).parts))
        else:
            files.append(path)
    return files


def read_sources(paths: list[Path], model: Model) -> dict:
    resources, k8s, read = {}, [], Counter()
    for path in expand(paths):
        if not path.exists():
            model.errors.append(f"{path} : fichier introuvable")
            continue
        if path.suffix.lower() == ".tf":
            read["terraform"] += 1
            read_terraform(path, model, resources)
            continue
        if path.suffix.lower() not in (".yaml", ".yml"):
            model.errors.append(f"{path.name} : format non reconnu (.tf, docker-compose ou manifeste Kubernetes .yaml)")
            continue
        try:
            docs = [d for d in yaml.safe_load_all(path.read_text(encoding="utf-8")) if d]
        except yaml.YAMLError as error:
            mark = getattr(error, "problem_mark", None)
            where = f", ligne {mark.line + 1}" if mark else ""
            model.warnings.append(f"{path.name} : YAML illisible{where} (gabarit Helm ?), fichier ignoré")
            continue
        if COMPOSE_NAMES.match(path.name) or (len(docs) == 1 and isinstance(docs[0], dict) and "services" in docs[0]
                                             and "kind" not in docs[0]):
            read["compose"] += 1
            read_compose(path, docs[0], model)
            continue
        manifests = [d for d in docs if isinstance(d, dict) and d.get("kind") and d.get("apiVersion")]
        for doc in docs:
            if isinstance(doc, dict) and doc.get("kind") == "List":
                manifests += [d for d in doc.get("items") or [] if isinstance(d, dict) and d.get("kind")]
        if not manifests:
            model.warnings.append(f"{path.name} : ni docker-compose ni manifeste Kubernetes, fichier ignoré")
            continue
        read["kubernetes"] += 1
        k8s += [d for d in manifests if d.get("kind") != "List"]
    build_terraform(resources, model)
    if k8s:
        build_kubernetes(k8s, model)
    return dict(read)


def describe(model: Model, title: str) -> dict:
    """Arbre de groupes et services de cloud_build.py ; les groupes vides sont omis."""
    children: dict[str | None, list] = {}
    for gid, group in model.groups.items():
        children.setdefault(group["parent"] if group["parent"] in model.groups else None, []).append(("g", gid))
    for nid, node in model.nodes.items():
        children.setdefault(node["parent"] if node["parent"] in model.groups else None, []).append(("n", nid))
    empty = []

    def items_of(parent: str | None) -> list[dict]:
        out = []
        for what, cid in children.get(parent, []):
            if what == "n":
                node = model.nodes[cid]
                item = {"id": cid, "type": node["type"], "label": node["label"]}
                if node["count"]:
                    item["count"] = node["count"]
                out.append(item)
                continue
            inner = items_of(cid)
            if inner:
                group = model.groups[cid]
                out.append({"id": cid, "type": group["type"], "label": group["label"], "items": inner})
            else:
                empty.append(model.groups[cid]["label"])
        return out

    items = items_of(None)
    providers = Counter(n["type"].split(":")[0] for n in model.nodes.values() if ":" in n["type"])
    spec = {"title": title}
    if providers:
        spec["provider"] = providers.most_common(1)[0][0]
    if spec.get("provider") == "k8s":
        spec["view"] = "kubernetes"
    regions = [r for p, r in model.regions if p == spec.get("provider")]
    if regions and spec.get("provider") in ("aws", "azure", "gcp"):
        items = [{"type": f"{spec['provider']}:region", "label": regions[0], "items": items}]
    spec["items"] = items
    spec["flows"] = model.flows
    if empty:
        model.warnings.append(f"groupes vides omis : {', '.join(empty[:6])}" + (" ..." if len(empty) > 6 else ""))
    return spec


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sources", type=Path, nargs="+", help="fichiers .tf, docker-compose, manifestes, ou dossiers")
    parser.add_argument("--out", type=Path, help="description écrite (défaut : <première source>.cloud.json)")
    parser.add_argument("--title", help="titre du schéma (défaut : nom de la première source)")
    args = parser.parse_args()
    first = args.sources[0]
    out = args.out or first.with_name(first.name.split(".")[0] + ".cloud.json")
    model = Model()
    read = read_sources(args.sources, model)
    report = {"input": [str(p) for p in args.sources], "output": None, "sources": read, "provider": None,
              "groups": 0, "services": len(model.nodes), "flows": len(model.flows), "ignored": sum(model.ignored.values()),
              "errors": model.errors, "warnings": model.warnings}
    if not model.nodes and not model.errors:
        model.errors.append("aucune ressource reconnue dans les sources")
    if model.ignored:
        listed = ", ".join(f"{k} ({v})" for k, v in model.ignored.most_common(8))
        model.warnings.append(f"sans équivalent dans le schéma : {listed}" + (" ..." if len(model.ignored) > 8 else ""))
    if not model.errors:
        spec = describe(model, args.title or first.name.split(".")[0])
        report["provider"] = spec.get("provider")
        # Vérification : schéma d'entrée de cloud_build.py, puis construction à blanc (types, identifiants, flux).
        invalid = validate(spec, HERE / "cloud_build.py")
        if invalid:
            model.errors += [f"description produite non conforme : {e}" for e in invalid]
        else:
            from cloud_build import build
            _, pages, errors, _ = build(spec)
            model.errors += errors
            report["groups"] = sum(len(b.groups) for _, b, _ in pages)
        if not model.errors:
            out.write_text(json.dumps(spec, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report["output"] = str(out)
    print(json.dumps(report, ensure_ascii=False))
    return 1 if model.errors else 0


if __name__ == "__main__":
    sys.exit(main())
