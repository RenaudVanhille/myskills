# /// script
# requires-python = ">=3.10"
# ///
"""Construit un schéma d'architecture cloud en draw.io à partir d'une description courte.

La description donne des groupes imbriqués (région, VPC, zone, sous-réseau,
cluster, namespace, étape de pipeline...) et des services par type
(`aws:lambda`, `azure:aks`, `gcp:cloud-run`, `k8s:pod`, ou générique :
`service`, `db`...). Le script place tout, avec les icônes officielles
livrées dans draw.io (aucun téléchargement), trace les flux, ajoute titre,
objectifs RPO/RTO et légende, puis vérifie le fichier comme check_drawio.py
du skill drawio-diagram s'il est installé à côté.

Vues : deployment (défaut), network (flux numérotés sur le schéma, détail
dans la matrice des flux <sujet>.flows.md),
kubernetes, dr (régions active et passive, RPO/RTO), pipeline (étapes de
gauche à droite), threats (frontières de confiance, flux numérotés comme dans
stride.py, en rouge quand ils traversent une frontière).

    uv run scripts/cloud_build.py SUJET.json [--out SUJET.drawio] [--view VUE] [--matrix] [--export png|svg]
    uv run scripts/cloud_build.py --types [aws|azure|gcp|k8s|ovh|...|generic]

Les hébergeurs sans jeu d'icônes dans draw.io (OVHcloud, Scaleway, Outscale,
Cloud Temple, S3NS, Bleu, NumSpot, hébergement interne) ont un vocabulaire
commun (`ovh:kubernetes`, `outscale:network`...), dessiné avec les formes de
la charte : catalogue commun shared/providers.json, copié dans lib/
(copie unique, que les autres skills lisent par skill_paths).
"""

import argparse
import difflib
import json
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from drawio_xml import (edge as new_edge, html, new_file, new_page, text_lines, text_width, vertex,  # noqa: E402
                        waypoints, write)
from skill_paths import absent, export_image, load_module  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402

HERE = Path(__file__).resolve().parent
ICONS = {k: v for k, v in json.loads((HERE / "icons.json").read_text(encoding="utf-8")).items()
         if not k.startswith("_")}
VIEWS = ("deployment", "network", "kubernetes", "dr", "pipeline", "threats")
# Catalogue commun des hébergeurs (shared/providers.json) : ceux qui ont un champ diagram se dessinent
# avec les formes génériques de la charte et le vocabulaire commun de services et de groupes.
CATALOG = json.loads((HERE / "lib" / "providers.json").read_text(encoding="utf-8"))
HOSTS = {k: v for k, v in CATALOG["providers"].items() if "diagram" in v}
HOST_SERVICES = {k: v for k, v in CATALOG["diagram"]["services"].items() if not k.startswith("_")}
HOST_GROUPS = {k: v for k, v in CATALOG["diagram"]["groups"].items() if not k.startswith("_")}
PROVIDERS = ("aws", "azure", "gcp", "k8s") + tuple(HOSTS)


def host_label(host: str, short: str, default: str) -> str:
    return HOSTS[host]["diagram"].get("labels", {}).get(short, default)

BASE = "whiteSpace=wrap;html=1;fontColor=#1f2937;fontSize=13;"
# Types génériques, aux styles de la charte : type -> (style, kind STRIDE, libellé par défaut).
GENERIC = {
    "user": ("shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=1;fillColor=#fef3c7;"
             "strokeColor=#b45309;fontColor=#1f2937;fontSize=13;", "external", "Utilisateur"),
    "internet": ("ellipse;shape=cloud;" + BASE + "fillColor=#f3f4f6;strokeColor=#6b7280;", "external", "Internet"),
    "external": ("rounded=1;dashed=1;" + BASE + "fillColor=#f3f4f6;strokeColor=#6b7280;", "external", "Système externe"),
    "service": ("rounded=1;" + BASE + "fillColor=#dbeafe;strokeColor=#1d4ed8;", "process", "Service"),
    "server": ("rounded=0;" + BASE + "fillColor=#dbeafe;strokeColor=#1d4ed8;", "process", "Serveur"),
    "db": ("shape=cylinder3;boundedLbl=1;size=10;" + BASE + "fillColor=#dcfce7;strokeColor=#15803d;", "store", "Base"),
    "queue": ("shape=parallelogram;perimeter=parallelogramPerimeter;" + BASE + "fillColor=#f3e8ff;strokeColor=#7e22ce;",
              "store", "File"),
    "repo": ("shape=document;boundedLbl=1;size=0.2;" + BASE + "fillColor=#f9fafb;strokeColor=#6b7280;", "store", "Dépôt Git"),
    "alert": ("rounded=0;" + BASE + "fillColor=#fee2e2;strokeColor=#b91c1c;", "process", "Point de vigilance"),
    "note": ("text;html=1;align=left;verticalAlign=top;whiteSpace=wrap;fontColor=#1f2937;fontSize=12;", None, ""),
}
ALIASES = {"users": "user", "person": "user", "system": "service", "tool": "service", "app": "service",
           "database": "db", "storage": "db", "bus": "queue", "topic": "queue", "git": "repo"}

GROUP = ("whiteSpace=wrap;html=1;container=1;collapsible=0;recursiveResize=0;verticalAlign=top;align=left;"
         "spacingLeft=10;fontSize=13;fontStyle=1;")
AWS_GROUP = ("outlineConnect=0;gradientColor=none;html=1;whiteSpace=wrap;fontSize=13;fontStyle=1;container=1;"
             "pointerEvents=0;collapsible=0;recursiveResize=0;shape=mxgraph.aws4.group;verticalAlign=top;"
             "align=left;spacingLeft=30;")
# Groupes : type -> style. vendor=1 marque les couleurs imposées par le fournisseur (check_drawio les tolère).
GROUPS = {
    "aws:cloud": AWS_GROUP + "grIcon=mxgraph.aws4.group_aws_cloud_alt;strokeColor=#232F3E;fillColor=none;fontColor=#232F3E;",
    "aws:account": AWS_GROUP + "grIcon=mxgraph.aws4.group_account;strokeColor=#CD2264;fillColor=none;fontColor=#CD2264;",
    "aws:region": AWS_GROUP + "grIcon=mxgraph.aws4.group_region;strokeColor=#00A4A6;fillColor=none;fontColor=#147EBA;dashed=1;",
    "aws:vpc": AWS_GROUP + "grIcon=mxgraph.aws4.group_vpc2;strokeColor=#8C4FFF;fillColor=none;fontColor=#8C4FFF;",
    "aws:az": GROUP + "vendor=1;fillColor=none;strokeColor=#147EBA;dashed=1;fontColor=#147EBA;",
    "aws:public-subnet": AWS_GROUP + "grIcon=mxgraph.aws4.group_security_group;grStroke=0;strokeColor=#7AA116;"
                                     "fillColor=#F2F6E8;fontColor=#248814;",
    "aws:private-subnet": AWS_GROUP + "grIcon=mxgraph.aws4.group_security_group;grStroke=0;strokeColor=#00A4A6;"
                                      "fillColor=#E6F6F7;fontColor=#147EBA;",
    "aws:security-group": GROUP + "vendor=1;fillColor=none;strokeColor=#DD3522;fontColor=#DD3522;",
    "aws:asg": AWS_GROUP + "grIcon=mxgraph.aws4.group_auto_scaling_group;strokeColor=#D86613;fillColor=none;"
                           "fontColor=#D86613;dashed=1;",
    "aws:datacenter": AWS_GROUP + "grIcon=mxgraph.aws4.group_corporate_data_center;strokeColor=#7D8998;fillColor=none;"
                                  "fontColor=#5A6C86;",
    "azure:subscription": GROUP + "vendor=1;fillColor=none;strokeColor=#0078D4;fontColor=#0078D4;",
    "azure:resource-group": GROUP + "vendor=1;fillColor=none;strokeColor=#0078D4;dashed=1;fontColor=#0078D4;",
    "azure:region": GROUP + "vendor=1;fillColor=none;strokeColor=#50E6FF;dashed=1;fontColor=#0078D4;",
    "azure:vnet": GROUP + "vendor=1;fillColor=#F2F8FD;strokeColor=#0078D4;fontColor=#0078D4;",
    "azure:subnet": GROUP + "vendor=1;fillColor=#FFFFFF;strokeColor=#5EA0EF;dashed=1;fontColor=#0078D4;",
    "azure:zone": GROUP + "vendor=1;fillColor=none;strokeColor=#5EA0EF;dashed=1;fontColor=#0078D4;",
    "gcp:project": GROUP + "vendor=1;fillColor=#F6F6F6;strokeColor=#9AA0A6;fontColor=#5F6368;",
    "gcp:region": GROUP + "vendor=1;fillColor=none;strokeColor=#4285F4;dashed=1;fontColor=#4285F4;",
    "gcp:zone": GROUP + "vendor=1;fillColor=none;strokeColor=#9AA0A6;dashed=1;fontColor=#5F6368;",
    "gcp:vpc": GROUP + "vendor=1;fillColor=#E8F0FE;strokeColor=#4285F4;fontColor=#1A73E8;",
    "gcp:subnet": GROUP + "vendor=1;fillColor=#FFFFFF;strokeColor=#34A853;dashed=1;fontColor=#188038;",
    "k8s:cluster": GROUP + "vendor=1;fillColor=#F5F8FE;strokeColor=#326CE5;fontColor=#326CE5;rounded=1;arcSize=4;",
    "k8s:namespace": GROUP + "vendor=1;fillColor=none;strokeColor=#326CE5;dashed=1;fontColor=#326CE5;",
    "k8s:node": GROUP + "vendor=1;fillColor=#FFFFFF;strokeColor=#9CB8F2;fontColor=#326CE5;",
    "zone": GROUP + "rounded=1;arcSize=4;dashed=1;fillColor=none;strokeColor=#9ca3af;fontColor=#6b7280;",
    "onprem": GROUP + "rounded=0;fillColor=#f9fafb;strokeColor=#6b7280;fontColor=#374151;",
    "internet": GROUP + "rounded=1;arcSize=4;dashed=1;fillColor=#f9fafb;strokeColor=#9ca3af;fontColor=#6b7280;",
    "stage": GROUP + "rounded=1;arcSize=4;fillColor=#f9fafb;strokeColor=#d1d5db;fontColor=#374151;align=center;spacingLeft=0;",
    "env": GROUP + "rounded=1;arcSize=4;fillColor=none;strokeColor=#1d4ed8;fontColor=#1d4ed8;",
    "boundary": GROUP + "rounded=1;arcSize=4;dashed=1;dashPattern=8 4;strokeWidth=2;fillColor=none;"
                        "strokeColor=#b91c1c;fontColor=#b91c1c;",
}
# Groupes des hébergeurs sans icônes : rôle commun (projet, région, zone, réseau, sous-réseau) -> style de la charte.
HOST_GROUP_STYLES = {
    "project": GROUP + "rounded=0;fillColor=#f9fafb;strokeColor=#6b7280;fontColor=#374151;",
    "region": GROUP + "rounded=1;arcSize=4;dashed=1;fillColor=none;strokeColor=#9ca3af;fontColor=#6b7280;",
    "zone": GROUP + "rounded=1;arcSize=4;dashed=1;fillColor=none;strokeColor=#9ca3af;fontColor=#6b7280;",
    "network": GROUP + "rounded=1;arcSize=4;fillColor=none;strokeColor=#1d4ed8;fontColor=#1d4ed8;",
    "subnet": GROUP + "rounded=1;arcSize=4;dashed=1;fillColor=none;strokeColor=#1d4ed8;fontColor=#1d4ed8;",
}
GROUP_LABELS: dict[str, str] = {}
for _host in HOSTS:
    for _short, _group in HOST_GROUPS.items():
        GROUPS[f"{_host}:{_short}"] = HOST_GROUP_STYLES[_group["as"]]
        GROUP_LABELS[f"{_host}:{_short}"] = host_label(_host, _short, _group["label"])
GROUP_ALIASES = {"subnet-public": "public-subnet", "subnet-private": "private-subnet", "sg": "security-group",
                 "ns": "namespace", "rg": "resource-group", "datacenter": "onprem", "trust": "boundary",
                 "environment": "env", "step": "stage"}
# Groupes qui sont des frontières de confiance par défaut (modèle de menaces).
BOUNDARIES = {"aws:account", "aws:vpc", "aws:public-subnet", "aws:private-subnet", "aws:security-group",
              "aws:datacenter", "azure:subscription", "azure:vnet", "azure:subnet", "gcp:project", "gcp:vpc",
              "gcp:subnet", "k8s:cluster", "k8s:namespace", "onprem", "internet", "boundary"} | \
             {f"{h}:{g}" for h in HOSTS for g, v in HOST_GROUPS.items() if v["as"] in ("project", "network", "subnet")}
# Disposition par défaut des enfants d'un groupe.
COLUMN = {"aws:az", "azure:zone", "gcp:zone", "aws:region", "azure:region", "gcp:region"} | \
         {f"{h}:{g}" for h in HOSTS for g, v in HOST_GROUPS.items() if v["as"] in ("region", "zone")}

EDGE = ("edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;fontSize=11;labelBackgroundColor=#ffffff;"
        "fontColor=#1f2937;")
FLOWS = {
    "sync": (EDGE + "strokeColor=#374151;endArrow=block;endFill=1;", "Appel synchrone"),
    "async": (EDGE + "strokeColor=#374151;dashed=1;endArrow=open;", "Asynchrone"),
    "replication": (EDGE + "strokeColor=#7e22ce;dashed=1;dashPattern=1 3;strokeWidth=2;startArrow=none;"
                    "endArrow=block;endFill=1;", "Réplication, sauvegarde"),
    "crossing": (EDGE + "strokeColor=#b91c1c;strokeWidth=2;endArrow=block;endFill=1;", "Traverse une frontière"),
}
TITLE = "text;html=1;fontSize=20;fontStyle=1;align=left;verticalAlign=middle;fontColor=#1f2937;"
NOTE = "rounded=0;whiteSpace=wrap;html=1;align=left;spacingLeft=8;fillColor=#fef3c7;strokeColor=#b45309;fontColor=#1f2937;fontSize=13;"
PAD, HEADER, GAP, ICON_PAD = 24, 38, 40, 16


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-") or "n"


class Builder:
    def __init__(self, spec: dict, view: str, page: str, errors: list, warnings: list):
        self.spec, self.view, self.page = spec, view, page
        self.provider = spec.get("provider")
        self.errors, self.warnings = errors, warnings
        self.nodes: dict[str, dict] = {}      # id -> {kind, label, type, path (frontières ancêtres), count}
        self.groups: dict[str, dict] = {}     # id -> {type, label, boundary}
        self.styles_used: set[str] = set()
        self.ids: set[str] = set()
        self.absolute: dict[str, tuple] = {}  # id -> (x, y, w, h, groupe) absolus, après placement
        self.icon_sizes: dict[str, float] = {}
        self.parent_of: dict[str, str] = {}

    # --- résolution des types ------------------------------------------------
    def resolve_node(self, raw: str, where: str) -> tuple[str, dict]:
        name = str(raw or "service").strip().lower()
        candidates = [name]
        if ":" not in name and self.provider:
            candidates.insert(0, f"{self.provider}:{name}")
        for candidate in candidates:
            host, _, short = candidate.partition(":")
            if host in HOSTS and short in HOST_SERVICES:
                service = HOST_SERVICES[short]
                style, kind, _ = GENERIC[service["as"]]
                return candidate, {"style": style, "kind": kind, "icon": False,
                                   "label": host_label(host, short, service["label"])}
            if candidate in ICONS:
                icon = ICONS[candidate]
                return candidate, {"style": icon["style"], "kind": icon["kind"], "label": icon["label"],
                                   "w": icon["w"], "h": icon["h"], "icon": True}
            generic = ALIASES.get(candidate, candidate)
            if generic in GENERIC:
                style, kind, label = GENERIC[generic]
                return generic, {"style": style, "kind": kind, "label": label, "icon": False}
        known = list(ICONS) + list(GENERIC) + [f"{h}:{s}" for h in HOSTS for s in HOST_SERVICES]
        close = difflib.get_close_matches(name, known, n=3, cutoff=0.6)
        if not close and ":" not in name:
            close = [k for k in known if k.endswith(":" + name)][:3]
        hint = f" (proche : {', '.join(close)})" if close else " (liste : --types)"
        self.errors.append(f"{self.page} : {where}, type inconnu « {raw} »{hint}")
        style, kind, label = GENERIC["service"]
        return "service", {"style": style, "kind": kind, "label": label, "icon": False}

    def resolve_group(self, raw: str, where: str) -> str:
        name = str(raw or "zone").strip().lower()
        prefix, _, short = name.rpartition(":")
        short = GROUP_ALIASES.get(short, short)
        name = f"{prefix}:{short}" if prefix else short
        for candidate in ([f"{self.provider}:{name}"] if ":" not in name and self.provider else []) + [name]:
            if candidate in GROUPS:
                return candidate
        if ":" not in name:
            for provider in PROVIDERS:
                if f"{provider}:{name}" in GROUPS:
                    return f"{provider}:{name}"
        close = difflib.get_close_matches(name, list(GROUPS), n=3, cutoff=0.6)
        self.errors.append(f"{self.page} : {where}, type de groupe inconnu « {raw} »"
                           + (f" (proche : {', '.join(close)})" if close else f" ({', '.join(sorted(GROUPS))})"))
        return "zone"

    def new_id(self, item: dict, fallback: str) -> str:
        cid = str(item.get("id") or slug(str(item.get("label") or fallback)))
        if cid in self.ids:
            if item.get("id"):
                self.errors.append(f"{self.page} : identifiant en double « {cid} »")
            base, n = cid, 2
            while f"{base}-{n}" in self.ids:
                n += 1
            cid = f"{base}-{n}"
        self.ids.add(cid)
        return cid

    # --- mesure et placement -------------------------------------------------
    def measure(self, item: dict, path: tuple) -> dict:
        """Calcule la taille de chaque élément (récursif) ; renvoie un arbre de boîtes."""
        if "items" in item:
            gtype = self.resolve_group(item.get("type"), f"groupe « {item.get('label', '?')} »")
            gid = self.new_id(item, gtype.split(":")[-1])
            label = str(item.get("label", "")) or GROUP_LABELS.get(gtype, "")
            state = item.get("state")
            if state in ("active", "passive"):
                label += " (actif)" if state == "active" else " (passif)"
            boundary = bool(item.get("boundary", gtype in BOUNDARIES))
            self.groups[gid] = {"type": gtype, "label": label or gtype, "boundary": boundary}
            sub_path = path + ((gid,) if boundary else ())
            children = [self.measure(child, sub_path) for child in item["items"]]
            layout = item.get("layout") or ("column" if gtype in COLUMN else "row")
            wrap = int(item.get("wrap") or 0)
            if layout == "column":
                wrap = 1
            elif not wrap:
                wrap = len(children) or 1
            rows = [children[i:i + wrap] for i in range(0, len(children), wrap)] or [[]]
            col_w = [max((r[c]["w"] for r in rows if c < len(r)), default=0) for c in range(wrap)]
            row_h = [max((c["h"] for c in r), default=0) for r in rows]
            y = HEADER
            for r, row in enumerate(rows):
                x = PAD
                for c, child in enumerate(row):
                    # Centré dans sa colonne et sa ligne : les flèches restent droites.
                    child["x"] = x + (col_w[c] - child["w"]) / 2 if wrap > 1 or layout == "column" else x
                    child["y"] = y + (row_h[r] - child["h"]) / 2
                    x += (col_w[c] if wrap > 1 or layout == "column" else child["w"]) + GAP
                y += row_h[r] + GAP
            inner_w = max((sum(col_w[:len(r)]) + GAP * (len(r) - 1) if wrap > 1 or layout == "column"
                           else sum(c["w"] for c in r) + GAP * (len(r) - 1)) for r in rows)
            w = max(inner_w + 2 * PAD, text_width(label, 13) + 60, 160)
            h = max(y - GAP + PAD, HEADER + 40)
            style = GROUPS["boundary"] if self.view == "threats" and boundary else GROUPS[gtype]
            if state == "passive":
                style += "opacity=60;textOpacity=80;"
            if item.get("chain"):
                for a, b in zip(children, children[1:]):
                    self.spec.setdefault("_chain", []).append({"from": a["id"], "to": b["id"]})
            return {"id": gid, "group": True, "label": label, "style": style, "w": w, "h": h, "children": children,
                    "row": len(rows) == 1 and layout != "column"}

        where = f"élément « {item.get('label') or item.get('id') or item.get('type')} »"
        ntype, info = self.resolve_node(item.get("type"), where)
        label = str(item.get("label") or info["label"])
        if item.get("count"):
            label += f" ×{item['count']}"
        nid = self.new_id(item, label)
        self.nodes[nid] = {"kind": item.get("kind", info["kind"]), "label": label.replace("\n", " "),
                           "type": ntype, "path": path, "count": item.get("count")}
        style = info["style"] + ("fontSize=12;fontColor=#1f2937;labelBackgroundColor=#ffffff;" if info["icon"] else "")
        if info["icon"]:
            iw, ih = float(item.get("w", info["w"])), float(item.get("h", info["h"]))
            sw = max(iw, text_width(label, 12) + ICON_PAD, 90)
            sh = ih + text_lines(label) * 15 + 8
            self.icon_sizes[nid] = ih
            return {"id": nid, "label": label, "style": style, "w": sw, "h": sh, "icon": (iw, ih)}
        if ntype == "user":
            self.icon_sizes[nid] = 50.0
            sw = max(60.0, text_width(label, 13) + ICON_PAD)
            return {"id": nid, "label": label, "style": style + "labelBackgroundColor=#ffffff;", "w": sw,
                    "h": 50 + text_lines(label) * 16 + 8,
                    "icon": (30.0, 50.0)}
        w = float(item.get("w", max(140, text_width(label, 13) + 30)))
        h = float(item.get("h", max(60, text_lines(label) * 18 + 24)))
        if ntype == "internet":
            w, h = w + 20, h + 20
        return {"id": nid, "label": label, "style": style, "w": w, "h": h}

    def place(self, box: dict, parent: str = "1", ax: float = 0, ay: float = 0) -> None:
        """Positions absolues (x, y, w, h, groupe) de chaque boîte ; ax, ay : origine du parent."""
        x, y = ax + box.get("x", 0), ay + box.get("y", 0)
        self.absolute[box["id"]] = (x, y, box["w"], box["h"], "children" in box)
        self.parent_of[box["id"]] = parent
        for child in box.get("children", []):
            self.place(child, box["id"], x, y)

    def emit(self, root: ET.Element, box: dict, parent: str, edges: dict) -> None:
        """Écrit la cellule, puis ses sous-groupes, les flux internes au groupe, enfin ses services :
        les flux passent au-dessus du fond des groupes et sous les libellés des services."""
        x, y = box.get("x", 0), box.get("y", 0)
        if box.get("icon"):
            iw, ih = box["icon"]
            vertex(root, box["id"], html(box["label"]), box["style"], x + (box["w"] - iw) / 2, y, iw, ih, parent)
        else:
            vertex(root, box["id"], html(box["label"]), box["style"], x, y, box["w"], box["h"], parent)
        children = box.get("children", [])
        for child in [c for c in children if "children" in c]:
            self.emit(root, child, box["id"], edges)
        for edge in edges.get(box["id"], []):
            root.append(edge)
        for child in [c for c in children if "children" not in c]:
            self.emit(root, child, box["id"], edges)

    def detour(self, source: str, target: str) -> list[tuple[float, float]]:
        """Points de passage d'un flux horizontal qui traverserait un autre service : il passe dessous."""
        sx, sy, sw, sh, sg = self.absolute[source]
        tx, ty, tw, th, tg = self.absolute[target]
        if sg or tg:
            return []
        scy, tcy = sy + self.icon_h(source) / 2, ty + self.icon_h(target) / 2
        if abs(scy - tcy) > 20:
            return []
        left, right = (sx + sw, tx) if sx < tx else (tx + tw, sx)
        blocking = [(x, y, w, h) for nid, (x, y, w, h, g) in self.absolute.items()
                    if not g and nid not in (source, target) and x < right and x + w > left and y <= scy <= y + h]
        if not blocking:
            return []
        lane = max(y + h for _, y, _, h in blocking) + 12
        start, end = (sx + sw + 10, tx - 10) if sx < tx else (sx - 10, tx + tw + 10)
        return [(start, lane), (end, lane)]

    def icon_h(self, nid: str) -> float:
        return self.icon_sizes.get(nid, self.absolute[nid][3])

    def crossing(self, a: str, b: str) -> list[str]:
        pa, pb = set(self.nodes[a]["path"]), set(self.nodes[b]["path"])
        crossed = [self.groups[g]["label"] for g in self.nodes[a]["path"] + self.nodes[b]["path"] if g in pa ^ pb]
        # Une entité externe est hors de toute frontière par définition.
        kinds = {self.nodes[a]["kind"], self.nodes[b]["kind"]}
        if not crossed and "external" in kinds and kinds != {"external"}:
            crossed = ["Extérieur"]
        return crossed


def align(boxes: list, flows: list, y0: float, row: bool) -> None:
    """Aligne verticalement un service posé dans une rangée sur les services auxquels il est relié
    ailleurs (ex. Clients et CloudFront à hauteur de l'ALB) : les flèches restent droites."""
    where = {}  # id -> (boîte, parent, est dans une rangée simple)

    def walk(items, parent, in_row):
        for item in items:
            where[item["id"]] = (item, parent, in_row)
            walk(item.get("children", []), item, item.get("row", False))
    walk(boxes, None, row)

    def top(box):
        y, parent = box.get("y", 0), where[box["id"]][1]
        return y + (top(parent) if parent else 0)

    links = {}
    for flow in flows:
        a, b = str(flow.get("from")), str(flow.get("to"))
        if a in where and b in where:
            links.setdefault(a, []).append(b)
            links.setdefault(b, []).append(a)
    movable = {nid for nid, (box, _, in_row) in where.items() if in_row and not box.get("children") and nid in links}
    placed = set(where) - movable
    changed = True
    # De proche en proche, depuis les services fixes (dans un groupe) : Clients -> CloudFront -> WAF -> ALB.
    while changed:
        changed = False
        for nid in sorted(movable - placed):
            box, parent, _ = where[nid]
            others = [where[o][0] for o in links[nid] if o in placed]
            if not others:
                continue
            centre = sum(top(o) + (o["icon"][1] if o.get("icon") else o["h"]) / 2 for o in others) / len(others)
            own = (box["icon"][1] if box.get("icon") else box["h"]) / 2
            base = top(parent) if parent else 0
            low = HEADER if parent else y0
            high = parent["h"] - PAD - box["h"] if parent else float("inf")
            box["y"] = max(low, min(high, centre - own - base))
            placed.add(nid)
            changed = True


def flow_label(flow: dict) -> str:
    parts = [str(flow[k]) for k in ("protocol", "port") if flow.get(k)]
    head = " ".join(parts)
    text = str(flow.get("label", ""))
    return f"{text} ({head})" if text and head else text or head


def build_page(spec: dict, view: str, name: str, errors: list, warnings: list) -> tuple[ET.Element, Builder, list]:
    b = Builder(spec, view, name, errors, warnings)
    diagram, root = new_page(f"p-{slug(name)}", name)

    top = {"type": "zone", "items": spec.get("items", []), "layout": spec.get("layout", "row"),
           "wrap": spec.get("wrap"), "chain": spec.get("chain")}
    boxes = []
    for item in top["items"]:
        boxes.append(b.measure(item, ()))
    if top.get("chain"):
        for a, c in zip(boxes, boxes[1:]):
            spec.setdefault("_chain", []).append({"from": a["id"], "to": c["id"]})
    # Disposition du premier niveau : comme un groupe, sans cadre.
    y0 = 60.0
    objectives = spec.get("objectives") or {}
    notes = [f"{k.upper()} {v}" for k, v in objectives.items()]
    if spec.get("provider") in HOSTS:
        notes.insert(0, f"Hébergeur : {HOSTS[spec['provider']]['name']}")
    if notes:
        y0 += 50
    x = 0.0
    if top["layout"] == "column":
        y = y0
        width = max((bx["w"] for bx in boxes), default=0)
        for bx in boxes:
            bx["x"], bx["y"] = (width - bx["w"]) / 2, y
            y += bx["h"] + 2 * GAP
    else:
        height = max((bx["h"] for bx in boxes), default=0)
        for bx in boxes:
            bx["x"], bx["y"] = x, y0 + (height - bx["h"]) / 2
            x += bx["w"] + 2.5 * GAP
    align(boxes, spec.get("flows", []), y0, top["layout"] != "column")
    right = max((bx["x"] + bx["w"] for bx in boxes), default=400)

    title = spec.get("title")
    if title:
        vertex(root, "title", html(str(title)), TITLE, 0, 0, max(400, len(str(title)) * 12), 30)
    else:
        warnings.append(f"{name} : pas de titre")
    if notes:
        text = " · ".join(notes)
        vertex(root, "objectives", html(text), NOTE, 0, 45, max(220, text_width(text, 13) + 30), 34)
    for bx in boxes:
        b.place(bx)

    flows, edges = [], {}
    for index, flow in enumerate(list(spec.get("flows", [])) + spec.pop("_chain", []), 1):
        source, target = str(flow.get("from")), str(flow.get("to"))
        if source not in b.ids or target not in b.ids:
            missing = source if source not in b.ids else target
            errors.append(f"{name} : flux {source} -> {target}, identifiant inconnu « {missing} »")
            continue
        number = len(flows) + 1
        crosses = b.crossing(source, target) if source in b.nodes and target in b.nodes else []
        kind = flow.get("style", "sync")
        if kind not in FLOWS or kind == "crossing":
            errors.append(f"{name} : flux {source} -> {target}, style inconnu « {kind} » (sync, async, replication)")
            kind = "sync"
        if view == "threats" and crosses:
            kind = "crossing"
        b.styles_used.add(kind)
        label = flow_label(flow)
        if view == "network":
            # Sur le schéma, le numéro seul : le détail (protocole, port) est dans la matrice des flux.
            label = f"F{number}"
        elif view == "threats":
            label = f"F{number}"
        style = FLOWS[kind][0]
        if flow.get("both"):
            style += "startArrow=block;startFill=1;"
        points = b.detour(source, target) if source in b.absolute and target in b.absolute else []
        if points:
            # Sortie et entrée sur les côtés, sinon draw.io sort par le bas, à travers le libellé.
            rightward = points[0][0] < points[1][0]
            style += f"exitX={1 if rightward else 0};exitY=0.5;entryX={0 if rightward else 1};entryY=0.5;"
        # Deux services du même groupe : le flux appartient au groupe (sous les libellés des services).
        parent = b.parent_of.get(source, "1")
        if parent != b.parent_of.get(target) or source in b.groups or target in b.groups:
            parent = "1"
        px0, py0 = b.absolute[parent][:2] if parent != "1" else (0, 0)
        node, geometry = new_edge(None, f"f{number}-{source}-{target}", html(label), style, source, target, parent)
        if points:
            waypoints(geometry, [(px - px0, py - py0) for px, py in points])
        edges.setdefault(parent, []).append(node)
        flows.append({"n": number, "from": source, "to": target, "label": str(flow.get("label", "")),
                      "protocol": flow.get("protocol", ""), "port": flow.get("port", ""),
                      "encrypted": flow.get("encrypted"), "crosses": crosses, "style": kind})

    for bx in boxes:
        b.emit(root, bx, "1", edges)
    for edge in edges.get("1", []):
        root.append(edge)

    # Légende des flux, à droite, si plus d'un style ou une vue qui en dépend.
    legend = spec.get("legend", "auto")
    if legend and (legend is True or len(b.styles_used) > 1 or b.styles_used - {"sync"}):
        lx = right + 80
        vertex(root, "legend-title", "Légende", "text;html=1;fontStyle=1;align=left;fontColor=#1f2937;fontSize=13;",
                 lx, y0, 120, 20)
        for row, kind in enumerate(k for k in FLOWS if k in b.styles_used):
            # Un trait du style du flux, libellé à droite (draw.io : forme « line »).
            line = re.sub(r"(edgeStyle|endArrow|endFill|startArrow|labelBackgroundColor)=[^;]*;", "", FLOWS[kind][0])
            vertex(root, f"legend-{kind}", FLOWS[kind][1], "shape=line;" + line + "labelPosition=right;"
                     "verticalLabelPosition=middle;align=left;spacingLeft=8;fontSize=12;", lx, y0 + 30 + row * 28, 40, 20)

    leaves = len(b.nodes)
    if str(spec.get("audience", "")).startswith("non") and leaves > 12:
        warnings.append(f"{name} : {leaves} services pour un public non technique (12 maximum) ; "
                        "regroupez ou faites une vue par sujet")
    elif leaves > 40:
        warnings.append(f"{name} : {leaves} services sur une page ; découpez en plusieurs vues (pages)")
    if view == "dr" and not objectives:
        warnings.append(f"{name} : vue PRA sans objectives (rpo, rto)")
    if view == "dr" and not any(f["style"] == "replication" for f in flows):
        warnings.append(f"{name} : vue PRA sans flux de réplication (style replication)")
    return diagram, b, flows


def matrix(title: str, pages: list[tuple[str, Builder, list]]) -> str:
    lines = [f"# Matrice des flux : {title}", ""]
    for name, b, flows in pages:
        if len(pages) > 1:
            lines += [f"## {name}", ""]
        lines += ["| N° | Source | Destination | Protocole | Port | Description | Frontière traversée |",
                  "| --- | --- | --- | --- | --- | --- | --- |"]
        label = {**{k: v["label"] for k, v in b.nodes.items()}, **{k: v["label"] for k, v in b.groups.items()}}
        for f in flows:
            cells = [f"F{f['n']}", label.get(f["from"], f["from"]), label.get(f["to"], f["to"]),
                     str(f["protocol"]), str(f["port"]), f["label"], ", ".join(f["crosses"]) or "non"]
            lines.append("| " + " | ".join(c.replace("|", "/") for c in cells) + " |")
        lines.append("")
    return "\n".join(lines)


def load_check():
    """check_drawio.py du skill drawio-diagram, s'il est installé à côté."""
    module = load_module("drawio-diagram", "check_drawio.py")
    return module.check if module else None


def build(spec: dict, view_override: str | None = None):
    errors, warnings = [], []
    mxfile = new_file()
    pages = []
    for number, page in enumerate(spec.get("pages") or [spec], 1):
        merged = {k: v for k, v in spec.items() if k not in ("pages", "items", "flows", "title", "objectives")}
        merged.update(page)
        view = view_override or merged.get("view", "deployment")
        if view not in VIEWS:
            errors.append(f"vue inconnue « {view} » ({', '.join(VIEWS)})")
            view = "deployment"
        name = str(page.get("name") or page.get("title") or f"Page-{number}")
        diagram, builder, flows = build_page(merged, view, name, errors, warnings)
        mxfile.append(diagram)
        pages.append((name, builder, flows))
    return mxfile, pages, errors, warnings


def list_types(which: str | None) -> str:
    lines = []
    for provider in PROVIDERS + ("generic",):
        if which and which != provider:
            continue
        if provider == "generic":
            nodes = sorted(GENERIC) + [f"{a}={b}" for a, b in sorted(ALIASES.items())]
            groups = sorted(g for g in GROUPS if ":" not in g)
        elif provider in HOSTS:
            nodes = [f"{s} ({host_label(provider, s, v['label'])})" for s, v in HOST_SERVICES.items()]
            groups = [f"{g} ({host_label(provider, g, v['label'])})" for g, v in HOST_GROUPS.items()]
        else:
            nodes = sorted(k.split(":", 1)[1] for k in ICONS if k.startswith(provider + ":"))
            groups = sorted(g.split(":", 1)[1] for g in GROUPS if g.startswith(provider + ":"))
        lines.append(f"{provider} services : {', '.join(nodes)}")
        lines.append(f"{provider} groupes : {', '.join(groups)}")
    return "\n".join(lines)


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("spec", type=Path, nargs="?")
    parser.add_argument("--out", type=Path, help="fichier .drawio (défaut : même nom)")
    parser.add_argument("--view", choices=VIEWS, help="vue, prioritaire sur celle de la description")
    parser.add_argument("--export", choices=["png", "svg"],
                        help="exporte aussi l'image (skill diagram-export) : construire et rendre en un appel")
    parser.add_argument("--matrix", action="store_true", help="écrit aussi <sujet>.flows.md, la matrice des flux (toujours en vue network)")
    parser.add_argument("--types", nargs="?", const="", metavar="FOURNISSEUR",
                        help="liste les types connus (aws, azure, gcp, k8s, hébergeurs souverains, generic) et s'arrête")
    parser.add_argument("--schema", action="store_true",
                        help="affiche le schéma JSON de la description sur une ligne, puis s'arrête")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if args.types is not None:
        print(list_types(args.types or None))
        return 0
    if not args.spec:
        parser.error("description JSON attendue")
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
    mxfile, pages, errors, warnings = build(spec, args.view)
    name = args.spec.name.removesuffix(".json")
    out = args.out or args.spec.with_name(name + ".drawio")
    report = {"input": str(args.spec), "output": None, "matrix": None, "views": [], "pages": len(pages),
              "groups": sum(len(b.groups) for _, b, _ in pages), "services": sum(len(b.nodes) for _, b, _ in pages),
              "flows": sum(len(f) for _, _, f in pages), "errors": errors, "warnings": warnings}
    report["views"] = sorted({b.view for _, b, _ in pages})
    if not errors:
        write(mxfile, out)
        report["output"] = str(out)
        if args.matrix or "network" in report["views"]:
            target = out.with_name(out.name.removesuffix(".drawio") + ".flows.md")
            target.write_text(matrix(str(spec.get("title", name)), pages), encoding="utf-8")
            report["matrix"] = str(target)
        check = load_check()
        if check:
            checked = check(out)
            report["review_image"] = checked["review_image"]
            report["errors"] += checked["errors"]
            report["warnings"] += checked["warnings"]
        else:
            report["warnings"].append("fichier non vérifié : " + absent("drawio-diagram", "check_drawio.py"))
    if args.export and not report["errors"]:
        report["export"], failed = export_image(out, args.export)
        report["errors"] += failed
    print(json.dumps(report, ensure_ascii=False))
    return 1 if report["errors"] else 0


if __name__ == "__main__":
    sys.exit(main())
