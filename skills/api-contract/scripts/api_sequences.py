# /// script
# requires-python = ">=3.10"
# ///
"""Écrit un diagramme de séquence Mermaid par exigence portée par les interfaces, depuis api.json.

Le script, et non le modèle, lit la description des interfaces d'api_build.py
(validée contre son schéma) et, pour chaque exigence citée dans `refs` :

- un participant client, puis les composants qui portent les opérations et
  les événements (libellés tirés de l'option d'architecture citée par
  `source`, s'il y en a une) ;
- un appel et sa réponse par opération (méthode, chemin, ressource rendue,
  statut), un message asynchrone par événement (envoi ou réception) ;
- chaque description est écrite par mermaid_build.py (skill
  mermaid-diagram), qui contrôle références et identifiants.

Écrit <nom>.seq-<exigence>.mmd et <nom>.sequences.md (tous les diagrammes,
titrés par exigence).

    uv run scripts/api_sequences.py api.json [--out-dir DOSSIER] [--only EF-001,EF-002] | --schema
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
from skill_paths import absent, find_script, schema_of  # noqa: E402
from spec_schema import check, print_schema, validate  # noqa: E402

STATUS = {"POST": 201, "DELETE": 204}


def safe(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_") or "x"


def read_json(path: Path, errors: list[str], what: str):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        errors.append(f"{what} : {path} illisible ({error})")
        return None


def sequences(spec: dict, base: Path, errors: list[str]) -> list[dict]:
    labels, titles = {}, {}
    if spec.get("source"):
        options = read_json(base / spec["source"]["options"], errors, "source")
        chosen = next((o for o in (options or {}).get("options", []) if o.get("id") == spec["source"]["option"]), {})
        labels = {c["id"]: c.get("label", c["id"]) for c in chosen.get("components", [])}
    if spec.get("requirements"):
        catalog = read_json(base / spec["requirements"], errors, "requirements")
        titles = {r["id"]: r.get("title", "") for r in (catalog or {}).get("requirements", [])}
    ops, events = spec.get("operations", []), spec.get("events", [])
    service = next((o["component"] for o in ops if o.get("component")), "api")
    refs = sorted({r for item in ops + events for r in item.get("refs", [])})
    out = []
    for rid in refs:
        participants = [{"id": "client", "label": "Client", "actor": True}]
        seen = {"client"}

        def add(cid: str) -> str:
            pid = safe(cid)
            if pid not in seen:
                participants.append({"id": pid, "label": labels.get(cid, cid)})
                seen.add(pid)
            return pid
        messages = []
        for op in (o for o in ops if rid in o.get("refs", [])):
            target = add(op.get("component") or service)
            messages.append({"from": "client", "to": target, "label": f"{op['method']} {op['path']}", "kind": "call"})
            answer = f"{op.get('status', STATUS.get(op['method'], 200))}" + (f" {op['response']}" if op.get("response") else "")
            messages.append({"from": target, "to": "client", "label": answer, "kind": "reply"})
        for ev in (e for e in events if rid in e.get("refs", [])):
            channel = add(ev.get("component") or ev["channel"])
            producer = add(service)
            ends = (producer, channel) if ev.get("action", "send") == "send" else (channel, producer)
            messages.append({"from": ends[0], "to": ends[1], "label": f"{ev['name']} ({ev['channel']})", "kind": "async"})
        title = f"{rid} : {titles[rid]}" if titles.get(rid) else rid
        out.append({"rid": rid, "spec": {"title": title, "type": "sequence", "participants": participants,
                                         "messages": messages}})
    return out


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("api", type=Path, nargs="?", help="description des interfaces (api.json d'api_build.py)")
    parser.add_argument("--out-dir", type=Path, help="dossier des fichiers produits (défaut : celui d'api.json)")
    parser.add_argument("--only", help="exigences à dessiner, séparées par des virgules")
    parser.add_argument("--schema", action="store_true", help="affiche le schéma de la description sur une ligne")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    report = {"input": str(args.api), "outputs": [], "diagrams": 0, "requirements": [], "errors": [], "warnings": []}
    errors, warnings = report["errors"], report["warnings"]

    def done(code: int) -> int:
        print(json.dumps(report, ensure_ascii=False))
        return code

    if not args.api:
        errors.append("description api.json attendue")
        return done(1)
    spec = read_json(args.api, errors, "api.json")
    if spec is None:
        return done(1)
    errors += validate(spec, __file__)
    builder, target = find_script("mermaid-diagram", "mermaid_build.py"), schema_of("mermaid-diagram", "mermaid_build.py")
    if builder is None or target is None:
        errors.append(absent("mermaid-diagram", "mermaid_build.py"))
    if errors:
        return done(1)
    found = sequences(spec, args.api.parent, errors)
    if args.only:
        wanted = {r.strip() for r in args.only.split(",") if r.strip()}
        unknown = sorted(wanted - {f["rid"] for f in found})
        errors += [f"--only : exigence « {u} » portée par aucune interface" for u in unknown]
        found = [f for f in found if f["rid"] in wanted]
    if not found and not errors:
        errors.append("aucune opération ni aucun événement ne cite d'exigence (refs) : rien à dessiner")
    for f in found:
        errors += [f"séquence {f['rid']} : {e}" for e in check(f["spec"], target)]
    if errors:
        return done(1)
    out_dir = args.out_dir or args.api.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    stem = args.api.name.removesuffix(".json").removesuffix(".api")
    sections, outputs = [f"# Séquences : {spec['title']}", ""], []
    with tempfile.TemporaryDirectory() as tmp:
        for f in found:
            desc = Path(tmp) / f"{safe(f['rid'])}.json"
            desc.write_text(json.dumps(f["spec"], ensure_ascii=False), encoding="utf-8")
            out = out_dir / f"{stem}.seq-{f['rid']}.mmd"
            done_run = subprocess.run([sys.executable, str(builder), str(desc), "--out", str(out)],
                                      capture_output=True, text=True, encoding="utf-8")
            try:
                sub = json.loads(done_run.stdout)
            except ValueError:
                sub = {"errors": [(done_run.stderr or "sans sortie").strip().splitlines()[-1][:200]]}
            errors += [f"mermaid_build.py ({f['rid']}) : {e}" for e in sub.get("errors", [])]
            if sub.get("errors") or not out.is_file():
                continue
            outputs.append(out)
            body = out.read_text(encoding="utf-8")
            sections += [f"## {f['spec']['title']}", "", "```mermaid", body.rstrip(), "```", ""]
    if errors:
        for path in outputs:
            path.unlink(missing_ok=True)
        return done(1)
    index = out_dir / f"{stem}.sequences.md"
    index.write_text("\n".join(sections), encoding="utf-8")
    warnings.append("rendu non vérifié ici : diagram-export --check sur les .mmd si une image est demandée")
    report.update(outputs=[str(p) for p in [*outputs, index]], diagrams=len(outputs),
                  requirements=[f["rid"] for f in found])
    return done(0)


if __name__ == "__main__":
    sys.exit(main())
