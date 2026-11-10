"""Revue du code : cycles, chaînes synchrones, appels entre services tirés de la configuration, écarts avec l'architecture décrite (arch_review.py)."""
from __future__ import annotations

import re
from pathlib import Path


def cycles(nodes: list[str], edges: set[tuple[str, str]]) -> list[list[str]]:
    """Composantes fortement connexes de plus d'un nœud (Tarjan), dans l'ordre des nœuds."""
    graph = {n: sorted({b for a, b in edges if a == n and b != n}, key=nodes.index) for n in nodes}
    index, low, stack, on, found, counter = {}, {}, [], set(), [], [0]

    def visit(node):
        index[node] = low[node] = counter[0]
        counter[0] += 1
        stack.append(node)
        on.add(node)
        for nxt in graph[node]:
            if nxt not in index:
                visit(nxt)
                low[node] = min(low[node], low[nxt])
            elif nxt in on:
                low[node] = min(low[node], index[nxt])
        if low[node] == index[node]:
            group = []
            while True:
                item = stack.pop()
                on.discard(item)
                group.append(item)
                if item == node:
                    break
            if len(group) > 1:
                found.append(sorted(group, key=nodes.index))

    for node in nodes:
        if node not in index:
            visit(node)
    return sorted(found, key=lambda g: nodes.index(g[0]))


def longest_sync(start: str, sync: dict[str, list[str]]) -> list[str]:
    """Plus long chemin synchrone sans boucle depuis start (graphes de quelques dizaines de composants)."""
    best = [start]

    def walk(path):
        nonlocal best
        if len(path) > len(best):
            best = list(path)
        for nxt in sync.get(path[-1], []):
            if nxt not in path:
                walk(path + [nxt])

    walk([start])
    return best


def glob_regex(pattern: str) -> re.Pattern:
    """Motif de fichiers (src/api/**, *.py) ; un chemin sans joker vaut pour le dossier entier."""
    pattern = pattern.strip("/").removeprefix("./")
    if not any(c in pattern for c in "*?["):
        return re.compile(re.escape(pattern) + r"(/.*)?")
    out, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**/", i):
            out, i = out + "(.*/)?", i + 3
        elif pattern.startswith("**", i):
            out, i = out + ".*", i + 2
        else:
            out += {"*": "[^/]*", "?": "[^/]"}.get(pattern[i], re.escape(pattern[i]))
            i += 1
    return re.compile(out)


CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".env", ".properties", ".toml", ".ini", ".conf", ".cfg", ".xml", ".tf",
                   ".hcl"}


CONFIG_NAMES = re.compile(r"^(dockerfile|(docker-)?compose[\w.-]*|\.env[\w.-]*)$", re.I)


SKIP_DIRS = {".git", "node_modules", "vendor", "target", "build", "dist", ".venv", "venv", "__pycache__",
             "graphify-out", ".idea", ".vscode", ".terraform"}


URL = re.compile(r"\b(?:jdbc:)?([a-z][a-z0-9+.-]*)://(?:[^\s/@\"'<>]*@)?([A-Za-z0-9_-][A-Za-z0-9_.-]*)(?::\d+)?"
                 r"(/[A-Za-z0-9_.-]*)?", re.I)


DB_SCHEMES = {"postgres", "postgresql", "mysql", "mariadb", "mongodb", "mongodb+srv", "sqlserver", "oracle",
              "cockroachdb"}


ASYNC_SCHEMES = {"amqp", "amqps", "kafka", "nats", "mqtt"}


MAX_FILES, MAX_BYTES = 3000, 512_000


def config_files(root: Path):
    count = 0
    for path in sorted(root.rglob("*")):
        if count >= MAX_FILES:
            return
        if any(part in SKIP_DIRS for part in path.relative_to(root).parts[:-1]) or not path.is_file():
            continue
        if path.suffix.lower() in CONFIG_SUFFIXES or CONFIG_NAMES.match(path.name):
            if path.stat().st_size <= MAX_BYTES:
                count += 1
                yield path


def asyncapi_channels(doc: dict) -> tuple[set[str], set[str]]:
    """Canaux envoyés et reçus d'un document AsyncAPI 2 (subscribe : l'application envoie) ou 3 (action)."""
    sends, receives = set(), set()
    channels = doc.get("channels") or {}
    if str(doc.get("asyncapi", "")).startswith("2"):
        for name, channel in channels.items():
            if isinstance(channel, dict):
                (sends if "subscribe" in channel else set()).add(name)
                (receives if "publish" in channel else set()).add(name)
        return sends, receives
    for operation in (doc.get("operations") or {}).values():
        if not isinstance(operation, dict):
            continue
        ref = ((operation.get("channel") or {}).get("$ref") or "").rsplit("/", 1)[-1]
        channel = channels.get(ref) or {}
        name = channel.get("address") or ref
        if name:
            (sends if operation.get("action") == "send" else receives).add(name)
    return sends, receives


def service_calls(repos: list[dict], comps: list[dict], warnings: list[str]) -> tuple[list[dict], dict, dict]:
    """Appels entre services lus dans la configuration et les contrats de chaque dépôt : URL vers un autre
    service ou un composant (hôte = dépôt, alias ou identifiant de composant), canaux AsyncAPI ; bases de
    données citées. Rend les appels, les bases (clé -> dépôts) et le composant de chaque dépôt."""
    ids = {c["id"].lower(): c["id"] for c in comps}
    owner = {}
    for repo in repos:
        owner[repo["name"]] = repo.get("component") or ids.get(repo["name"].lower())
    names: dict[str, str] = dict(ids)
    for repo in repos:
        if owner[repo["name"]]:
            for alias in [repo["name"], *repo.get("aliases", [])]:
                names[alias.lower()] = owner[repo["name"]]
    try:
        import yaml
    except ImportError:
        yaml = None
        warnings.append("code : pyyaml absent, canaux AsyncAPI non lus (uv run installe pyyaml)")
    calls: dict[tuple, dict] = {}
    databases: dict[str, set[str]] = {}
    sends: dict[str, set[str]] = {}
    receives: dict[str, set[str]] = {}
    for repo in repos:
        root = Path(repo["root"])
        if not root.is_dir():
            continue
        source = owner[repo["name"]]
        for path in config_files(root):
            text = path.read_text(encoding="utf-8", errors="replace")
            where = f"{repo['name']}/{path.relative_to(root).as_posix()}"
            for match in URL.finditer(text):
                scheme, host, base_path = match.group(1).lower(), match.group(2).lower(), match.group(3) or ""
                if scheme in DB_SCHEMES:
                    databases.setdefault(f"{host}{base_path}", set()).add(repo["name"])
                target = names.get(host) or names.get(host.split(".")[0])
                if source and target and target != source:
                    style = "async" if scheme in ASYNC_SCHEMES else "sync"
                    calls.setdefault((source, target), {"from": source, "to": target, "style": style,
                                                        "via": f"{scheme}://{host}", "file": where})
            if yaml is not None and path.suffix.lower() in (".yaml", ".yml", ".json") and "asyncapi" in text[:2000]:
                try:
                    doc = yaml.safe_load(text)
                except yaml.YAMLError:
                    continue
                if isinstance(doc, dict) and doc.get("asyncapi"):
                    out, inn = asyncapi_channels(doc)
                    for name in out:
                        sends.setdefault(name, set()).add(repo["name"])
                    for name in inn:
                        receives.setdefault(name, set()).add(repo["name"])
    for channel, producers in sorted(sends.items()):
        for producer in sorted(producers):
            for consumer in sorted(receives.get(channel, set())):
                a, b = owner.get(producer), owner.get(consumer)
                if a and b and a != b:
                    calls.setdefault((a, b), {"from": a, "to": b, "style": "async", "via": f"canal {channel}",
                                              "file": f"{producer} > {consumer}"})
    return list(calls.values()), databases, owner
