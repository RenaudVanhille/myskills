# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow>=10", "playwright>=1.48", "numpy>=1.24"]
# ///
"""Revue UX et accessibilité des pages décrites : contrôles mécaniques sur le rendu, constats du modèle mis en forme.

Le script, et non le modèle, contrôle chaque page dans un navigateur local
(Playwright, réseau coupé), à partir de la même description que
page_build.py ; chaque écart est rattaché au nœud de la description
(body/2/children/0) :

- contraste réel de chaque texte sur son fond (WCAG 1.4.3, 1.4.6 en AAA) ;
- nom accessible des boutons, liens et champs (4.1.2) ; image sans
  attribut alt (1.1.1) ;
- taille des cibles cliquables : 24 px (2.5.8), 44 px en AAA (2.5.5) ;
- texte de moins de 12 px ; tableau sans en-tête (1.3.1) ; langue de la
  page (3.1.1) ; zone principale (main) ; débordement horizontal à 390 px
  (1.4.10) ;
- plus d'un bouton primary par écran (règle du design system).

Le modèle écrit un JSON court (schéma par --schema) : les pages revues,
le niveau visé (AA, AAA) et ses constats de jugement, rangés par
heuristique de Nielsen (h1 à h10) ou en accessibilité (a11y), avec gravité
1 à 4, nœud, problème et correction. Premier passage avec "findings": []
pour les seuls contrôles ; le script valide le tout (pages lisibles, nœuds
existants) et écrit <page>.ux.md : synthèse, contrôles, constats, triés
par gravité.

    uv run scripts/ux_review.py REVUE.json [--out-dir DOSSIER] [--no-render] | --schema
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "lib"))
import page_build  # noqa: E402
import script_report  # noqa: E402
from spec_schema import print_schema, validate  # noqa: E402
from text_tools import beside  # noqa: E402

HEURISTICS = {
    "h1": "Visibilité de l'état du système",
    "h2": "Correspondance avec le monde réel",
    "h3": "Contrôle et liberté de l'utilisateur",
    "h4": "Cohérence et standards",
    "h5": "Prévention des erreurs",
    "h6": "Reconnaître plutôt que se souvenir",
    "h7": "Flexibilité et efficacité",
    "h8": "Esthétique et design minimaliste",
    "h9": "Aider à reconnaître, diagnostiquer et corriger les erreurs",
    "h10": "Aide et documentation",
    "a11y": "Accessibilité (WCAG 2.2)",
}
SEVERITY = {1: "mineur", 2: "gênant", 3: "majeur", 4: "bloquant"}
MAX_ISSUES = 20

# Contrôles évalués dans la page rendue (copie repérée par data-node).
AUDIT_SCRIPT = """(level) => {
  const out = [];
  const host = el => { const h = el.closest('[data-node]'); return h ? h.dataset.node : null; };
  const rgba = s => {  // rgb(), rgba() ou color(srgb r g b / a) (color-mix)
    const m = (s.match(/[\\d.]+/g) || []).map(Number);
    const unit = s.startsWith('color(') ? 255 : 1;
    return [m[0] * unit, m[1] * unit, m[2] * unit, m.length > 3 ? m[3] : 1];
  };
  const lum = c => { const f = v => { v /= 255; return v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
                     return 0.2126 * f(c[0]) + 0.7152 * f(c[1]) + 0.0722 * f(c[2]); };
  const ratio = (a, b) => { const x = lum(a), y = lum(b); return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05); };
  const hex = c => '#' + c.slice(0, 3).map(v => Math.round(v).toString(16).padStart(2, '0')).join('');
  const visible = el => { const r = el.getBoundingClientRect(); const s = getComputedStyle(el);
                          return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none'; };
  const background = el => {
    let color = [255, 255, 255, 1], layers = [];
    for (let e = el; e; e = e.parentElement) {
      const s = getComputedStyle(e);
      if (s.backgroundImage && s.backgroundImage !== 'none') return null;
      const c = rgba(s.backgroundColor);
      if (c[3] > 0) { layers.push(c); if (c[3] >= 1) break; }
    }
    layers.reverse().forEach(c => { color = [0, 1, 2].map(i => c[i] * c[3] + color[i] * (1 - c[3])).concat([1]); });
    return color;
  };
  const counted = {contrast: 0, name: 0, target: 0, text: 0};
  const seen = new Set();
  document.querySelectorAll('body *').forEach(el => {
    if (!visible(el) || el.closest('svg')) return;
    const own = [...el.childNodes].some(n => n.nodeType === 3 && n.data.trim());
    if (!own) return;
    counted.text++;
    const s = getComputedStyle(el), size = parseFloat(s.fontSize), bold = parseInt(s.fontWeight) >= 700;
    const bg = background(el);
    if (size < 12 && !seen.has('size' + host(el))) {
      seen.add('size' + host(el));
      out.push({kind: 'text-size', node: host(el), value: size, text: el.textContent.trim().slice(0, 40)});
    }
    if (!bg) return;
    counted.contrast++;
    const large = size >= 24 || (bold && size >= 18.66);
    const need = level === 'AAA' ? (large ? 4.5 : 7) : (large ? 3 : 4.5);
    const fg = rgba(s.color), r = ratio(fg, bg);
    if (r < need && !seen.has('contrast' + host(el))) {
      seen.add('contrast' + host(el));
      out.push({kind: 'contrast', node: host(el), value: Math.round(r * 100) / 100, need: need,
                colors: [hex(fg), hex(bg)], text: el.textContent.trim().slice(0, 40)});
    }
  });
  const minimum = level === 'AAA' ? 44 : 24;
  const targets = [];
  document.querySelectorAll('a[href], button, input, select, textarea, summary, [role=button], [role=tab]').forEach(el => {
    if (!visible(el) || (el.type === 'hidden')) return;
    counted.name++;
    let name = (el.getAttribute('aria-label') || el.getAttribute('title') || '').trim();
    if (!name && el.getAttribute('aria-labelledby'))
      name = el.getAttribute('aria-labelledby').split(/\\s+/).map(id => (document.getElementById(id) || {}).textContent || '').join(' ').trim();
    if (!name && el.labels && el.labels.length) name = [...el.labels].map(l => l.textContent).join(' ').trim();
    if (!name && ['submit', 'button', 'reset'].includes(el.type)) name = (el.value || '').trim();
    if (!name && !['INPUT', 'SELECT', 'TEXTAREA'].includes(el.tagName))
      name = (el.textContent || '').trim() || [...el.querySelectorAll('img[alt]')].map(i => i.alt).join(' ').trim();
    if (!name && !seen.has('name' + host(el))) {
      seen.add('name' + host(el));
      out.push({kind: 'name', node: host(el), tag: el.tagName.toLowerCase()});
    }
    const inline = el.tagName === 'A' && el.closest('p, li') && getComputedStyle(el).display === 'inline';
    const box = (el.type === 'checkbox' || el.type === 'radio') && el.labels && el.labels.length
      ? el.labels[0].getBoundingClientRect() : el.getBoundingClientRect();
    counted.target++;
    if (!inline) targets.push({el, box, text: (el.textContent || name || '').trim().slice(0, 40)});
  });
  // Exception de 2.5.8 : une petite cible passe si un cercle de 24 px centré sur elle ne touche aucune autre cible.
  const centre = b => [b.x + b.width / 2, b.y + b.height / 2];
  const gap = (p, b) => Math.hypot(Math.max(b.x - p[0], 0, p[0] - b.right), Math.max(b.y - p[1], 0, p[1] - b.bottom));
  const small = targets.filter(t => t.box.width < minimum || t.box.height < minimum);
  small.forEach(t => {
    const c = centre(t.box);
    const spaced = level !== 'AAA' && targets.every(o => o === t || gap(c, o.box) >= minimum / 2)
      && small.every(o => o === t || Math.hypot(c[0] - centre(o.box)[0], c[1] - centre(o.box)[1]) >= minimum);
    if (spaced || seen.has('target' + host(t.el))) return;
    seen.add('target' + host(t.el));
    out.push({kind: 'target', node: host(t.el), value: [Math.round(t.box.width), Math.round(t.box.height)], need: minimum,
              text: t.text});
  });
  document.querySelectorAll('img:not([alt])').forEach(el => out.push({kind: 'alt', node: host(el)}));
  document.querySelectorAll('table').forEach(el => { if (!el.querySelector('th')) out.push({kind: 'table', node: host(el)}); });
  if (!document.documentElement.lang) out.push({kind: 'lang', node: null});
  if (!document.querySelector('main, [role=main]')) out.push({kind: 'main', node: null});
  return {issues: out, counted: counted};
}"""

AUTO = {  # gravité, message, correction
    "contrast": (3, "contraste {value}:1 sous {need}:1 ({colors}) pour « {text} » (WCAG 1.4.3)",
                 "prendre un token de texte plus sombre ou un fond plus clair (ds_build.py propose la teinte)"),
    "name": (4, "{tag} sans nom accessible (WCAG 4.1.2)", "ajouter un texte, un label ou un label d'icône"),
    "target": (2, "cible de {value[0]}×{value[1]} px sous {need} px « {text} » (WCAG 2.5.8)",
               "agrandir le bouton (size md) ou son padding"),
    "text-size": (2, "texte de {value} px « {text} », illisible sous 12 px", "prendre le token de texte xs ou sm"),
    "alt": (3, "image sans attribut alt (WCAG 1.1.1)", "ajouter alt, \"\" si décorative"),
    "table": (2, "tableau sans en-tête (WCAG 1.3.1)", "renseigner columns"),
    "lang": (2, "langue de la page absente (WCAG 3.1.1)", "renseigner lang"),
    "main": (1, "pas de zone principale (main)", "placer le contenu dans une section ou une barre latérale"),
    "mobile": (2, "débordement horizontal à 390 px (WCAG 1.4.10)", "réduire les colonnes ou passer le tableau en défilement"),
    "primary": (1, "{value} boutons primary sur l'écran", "garder un seul bouton primary, passer les autres en secondary ou outline"),
}


def resolve(spec: dict, node: str):
    """Nœud de la description désigné par son chemin (body/2/children/0), ou None."""
    current = spec
    for part in node.split("/"):
        if isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        elif isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current


def primaries(value) -> int:
    """Boutons primary de la description (variante explicite ou bouton d'action principal)."""
    if isinstance(value, dict):
        own = 1 if value.get("variant") == "primary" and "text" in value else 0
        return own + sum(primaries(v) for v in value.values())
    if isinstance(value, list):
        return sum(primaries(v) for v in value)
    return 0


def auto_issue(raw: dict) -> dict:
    severity, message, fix = AUTO[raw["kind"]]
    fields = {"value": "", "need": "", "text": "", "tag": "", **raw}
    if "colors" in raw:
        fields["colors"] = " sur ".join(raw["colors"])
    return {"kind": raw["kind"], "node": raw.get("node"), "severity": severity,
            "message": message.format(**fields), "fix": fix}


def markdown(title: str, level: str, issues: list[dict], findings: list[dict], summary: str, rendered: bool) -> str:
    lines = [f"# Revue UX et accessibilité : {title}", "",
             f"Niveau visé : WCAG 2.2 {level}. Contrôles mécaniques "
             + ("sur le rendu local." if rendered else "sur la description seule (rendu non vérifié).")]
    if summary:
        lines += ["", summary]
    counts = {s: sum(1 for i in issues + findings if i["severity"] == s) for s in (4, 3, 2, 1)}
    lines += ["", "| Gravité | Nombre |", "| --- | --- |"]
    lines += [f"| {SEVERITY[s]} ({s}) | {n} |" for s, n in counts.items()]

    def cell(text) -> str:
        return str(text or "").replace("|", "\\|").replace("\n", " ")

    lines += ["", "## Contrôles automatiques", ""]
    if issues:
        lines += ["| Gravité | Nœud | Constat | Correction |", "| --- | --- | --- | --- |"]
        lines += [f"| {i['severity']} | `{i['node'] or 'page'}` | {cell(i['message'])} | {cell(i['fix'])} |"
                  for i in sorted(issues, key=lambda i: -i["severity"])]
    else:
        lines.append("Aucun écart.")
    lines += ["", "## Constats de la revue", ""]
    if findings:
        lines += ["| Gravité | Heuristique | Nœud | Problème | Correction |", "| --- | --- | --- | --- | --- |"]
        lines += [f"| {f['severity']} | {HEURISTICS[f['heuristic']]} | `{f.get('node') or 'page'}` | {cell(f['problem'])} "
                  f"| {cell(f['fix'])} |" for f in sorted(findings, key=lambda f: -f["severity"])]
    else:
        lines.append("Aucun constat fourni (--findings).")
    return "\n".join(lines) + "\n"


def review(path: Path, out_arg: Path | None, level: str, findings: list[dict], summary: str, no_render: bool) -> dict:
    result = {"input": str(path), "outputs": [], "rendered": False, "checked": {}, "issue_count": 0, "issues": [],
              "findings": 0, "severity": {str(s): 0 for s in (1, 2, 3, 4)}, "errors": [], "warnings": []}
    context: dict = {"errors": [], "warnings": [], "tokens": None, "outputs": []}
    ready = page_build.prepare(path, out_arg, context)
    result["errors"] += context["errors"]
    if ready is None:
        return result
    spec, page, out_dir, stem = ready["spec"], ready["page"], ready["out_dir"], ready["stem"]
    mine = [f for f in findings if f.get("page") in (None, stem, path.name)]
    for f in mine:
        if f.get("node") and resolve(spec, f["node"]) is None:
            result["errors"].append(f"findings : nœud « {f['node']} » absent de {path.name} (chemin body/2/children/0)")
    if result["errors"]:
        return result
    markup, _css = page.build()
    result["errors"] += page.errors
    if result["errors"]:
        return result
    raw: list[dict] = []
    count = primaries(spec.get("body"))
    if count > 1:
        raw.append({"kind": "primary", "node": None, "value": count})
    if no_render:
        result["warnings"].append("contrôles du rendu non faits (--no-render) : contraste réel, cibles, noms")
    else:
        check = out_dir / f".{stem}.ux.html"
        css_path = out_dir / f".{stem}.ux.css"
        check.write_text(markup.replace(f'href="{stem}.css"', f'href="{css_path.name}"', 1), encoding="utf-8")
        css_path.write_text(_css, encoding="utf-8")
        try:
            scale = spec.get("scale", 1)
            mockup = ready["mockup"]
            width = spec.get("width") or (round(mockup.width / scale) if mockup else 1280)
            shot = page_build.render(out_dir, check.name, width, 1, None, f"() => ({AUDIT_SCRIPT})({json.dumps(level)})")
            result["rendered"] = True
            raw += shot["audit"]["issues"]
            result["checked"] = shot["audit"]["counted"]
            if shot["mobile_overflow"]:
                raw.append({"kind": "mobile", "node": None})
        except ImportError:
            result["warnings"].append("contrôles du rendu non faits : Playwright manquant, lancez ce script avec `uv run`")
        except page_build.local_tools.PackageError as error:
            result["warnings"].append(f"contrôles du rendu non faits : {error}")
        finally:
            check.unlink(missing_ok=True)
            css_path.unlink(missing_ok=True)
    issues = [auto_issue(r) for r in raw]
    issues.sort(key=lambda i: -i["severity"])
    for item in issues + mine:
        result["severity"][str(item["severity"])] += 1
    result["issue_count"] = len(issues)
    result["issues"] = [{k: i[k] for k in ("kind", "node", "severity", "message")} for i in issues[:MAX_ISSUES]]
    result["findings"] = len(mine)
    md = beside(out_dir / f"{stem}.ux.md")
    md.write_text(markdown(spec["title"], level, issues, mine, summary, result["rendered"]), encoding="utf-8")
    result["outputs"].append(str(md))
    if result["severity"]["4"] or result["severity"]["3"]:
        result["warnings"].append(f"{result['severity']['4']} écart(s) bloquant(s) et {result['severity']['3']} majeur(s) : "
                                  "corriger les nœuds cités puis relancer page_build.py")
    return result


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("review", nargs="?", type=Path)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--no-render", action="store_true")
    parser.add_argument("--schema", action="store_true")
    args = parser.parse_args()
    if args.schema:
        print_schema(__file__)
        return 0
    if args.review is None:
        script_report.print_report([], ["revue manquante (REVUE.json, --schema pour sa forme)"])
        return 1
    try:
        data = json.loads(args.review.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        script_report.print_report([], [f"{args.review} illisible ({error})"])
        return 1
    errors = validate(data, __file__)
    if errors:
        script_report.print_report([], errors)
        return 1
    pages = [args.review.parent / name for name in data["pages"]]
    names = {p.stem for p in pages} | {p.name for p in pages}
    errors = [f"findings/{i}/page : « {f['page']} » absente de pages ({', '.join(data['pages'])})"
              for i, f in enumerate(data["findings"]) if f.get("page") and f["page"] not in names]
    if len(pages) > 1:
        errors += [f"findings/{i}/page : page à préciser, plusieurs pages revues"
                   for i, f in enumerate(data["findings"]) if f.get("node") and not f.get("page")]
    if errors:
        script_report.print_report([], errors)
        return 1
    results = [review(p, args.out_dir, data.get("level", "AA"), data["findings"], data.get("summary", ""), args.no_render)
               for p in pages]
    script_report.print_report(results)
    return 1 if any(r["errors"] for r in results) else 0


if __name__ == "__main__":
    sys.exit(main())
