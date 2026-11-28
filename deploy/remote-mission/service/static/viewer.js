// Visionneuse des fichiers d'une mission : arbre de la branche, rendu façon Obsidian (wikilinks, callouts,
// propriétés, Mermaid), schémas, tableaux, téléchargements. Bibliothèques servies par le service (aucun CDN).
"use strict";

const state = { files: [], byPath: new Map(), byName: new Map(), backlinks: {}, current: null };
const $ = (id) => document.getElementById(id);
const TEXT = /\.(md|txt|csv|tsv|json|ya?ml|xml|drawio|mmd|puml|py|js|ts|sql|sh|ps1|toml|ini|log|html?|css)$/i;
const IMAGE = /\.(png|jpe?g|gif|svg|webp)$/i;
const OFFICE = /\.(docx?|pptx?|xlsx?|odt|ods|odp|zip)$/i;

function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
const raw = (path) => "brut/" + path.split("/").map(encodeURIComponent).join("/");
const dirOf = (path) => (path.includes("/") ? path.slice(0, path.lastIndexOf("/") + 1) : "");
const baseName = (path) => path.slice(path.lastIndexOf("/") + 1);

function resolve(from, target) {
  const parts = (dirOf(from) + target).split("/");
  const out = [];
  for (const part of parts) {
    if (part === "..") out.pop();
    else if (part !== "." && part !== "") out.push(part);
  }
  return out.join("/");
}

// Nom de note ou de fichier (Obsidian) -> chemin dans la branche.
function findByName(name) {
  const clean = decodeURIComponent(name).trim().replace(/^\.?\//, "");
  if (state.byPath.has(clean)) return clean;
  const key = clean.toLowerCase();
  return state.byName.get(key) || state.byName.get(key + ".md") || null;
}

async function loadTree() {
  const response = await fetch("api/arbre", { cache: "no-store" });
  if (!response.ok) {
    $("liste").innerHTML = `<p class="discret">${esc(await response.text())}</p>`;
    return;
  }
  const data = await response.json();
  $("mission").textContent = data.mission;
  $("branche").textContent = data.branch;
  document.title = `${data.mission} : fichiers`;
  state.files = data.files.filter((f) => !/(^|\/)\.(git|obsidian|historique|myskills-tmp)\//.test(f.path));
  state.backlinks = data.backlinks || {};
  for (const f of state.files) {
    state.byPath.set(f.path, f);
    const name = baseName(f.path).toLowerCase();
    if (!state.byName.has(name)) state.byName.set(name, f.path);
  }
  renderTree("");
  if (!data.libs || !data.libs.includes("marked.js")) {
    $("chemin").textContent = "Bibliothèques de rendu absentes (fetch_vendor.py) : Markdown affiché en texte.";
  }
  const wanted = decodeURIComponent(location.hash.slice(1));
  if (wanted && state.byPath.has(wanted)) openFile(wanted);
  else {
    const start = ["journal.md", "README.md", "index.md"].map(findByName).find(Boolean);
    if (start) openFile(start);
  }
}

function renderTree(filter) {
  const root = {};
  const needle = filter.toLowerCase();
  for (const f of state.files) {
    if (needle && !f.path.toLowerCase().includes(needle)) continue;
    let node = root;
    const parts = f.path.split("/");
    parts.slice(0, -1).forEach((p) => { node = node[p + "/"] = node[p + "/"] || {}; });
    node[parts[parts.length - 1]] = f.path;
  }
  const build = (node, depth) => {
    const keys = Object.keys(node).sort((a, b) => (b.endsWith("/") - a.endsWith("/")) || a.localeCompare(b, "fr"));
    return "<ul>" + keys.map((key) => {
      if (key.endsWith("/")) {
        const open = needle || depth < 1 ? " open" : "";
        return `<li><details${open}><summary>${esc(key.slice(0, -1))}</summary>${build(node[key], depth + 1)}</details></li>`;
      }
      const active = node[key] === state.current ? ' class="actif"' : "";
      return `<li><a href="#${encodeURIComponent(node[key])}"${active} title="${esc(node[key])}">${esc(key)}</a></li>`;
    }).join("") + "</ul>";
  };
  $("liste").innerHTML = Object.keys(root).length ? build(root, 0) : '<p class="discret">Aucun fichier poussé sur cette branche.</p>';
}

async function fetchText(path) {
  const response = await fetch(raw(path), { cache: "no-store" });
  if (!response.ok) throw new Error(await response.text());
  return response.text();
}

// --- Markdown façon Obsidian ---------------------------------------------------------------------------
function frontmatter(text) {
  const match = /^---\r?\n([\s\S]*?)\r?\n---\r?\n?/.exec(text);
  if (!match) return { body: text, props: "" };
  const rows = match[1].split(/\r?\n/).filter((l) => /^[\w-]+:/.test(l)).map((l) => {
    const i = l.indexOf(":");
    return `<tr><td>${esc(l.slice(0, i))}</td><td>${esc(l.slice(i + 1).trim().replace(/^["']|["']$/g, ""))}</td></tr>`;
  });
  return { body: text.slice(match[0].length), props: rows.length ? `<table class="proprietes">${rows.join("")}</table>` : "" };
}

function obsidian(text, from) {
  // Inclusions ![[image.png]] et liens [[note|libellé]] -> Markdown ordinaire, résolus dans la branche.
  text = text.replace(/!\[\[([^\]|]+)(?:\|[^\]]*)?\]\]/g, (_, name) => {
    const path = findByName(name);
    return path && IMAGE.test(path) ? `![${name}](<${raw(path)}>)` : `[[${name}]]`;
  });
  text = text.replace(/\[\[([^\]|#]+)(#[^\]|]*)?(?:\|([^\]]+))?\]\]/g, (_, name, _anchor, label) => {
    const path = findByName(name);
    const shown = label || name;
    return path ? `[${shown}](#${encodeURIComponent(path)})` : `<span class="wikilien absent">${esc(shown)}</span>`;
  });
  return text;
}

function callouts(container) {
  for (const quote of container.querySelectorAll("blockquote")) {
    const first = quote.firstElementChild;
    const match = first && /^\s*\[!(\w+)\][-+]?\s*(.*)/.exec(first.innerHTML);
    if (!match) continue;
    const kind = match[1].toLowerCase();
    const title = match[2].split("<br>")[0] || kind.charAt(0).toUpperCase() + kind.slice(1);
    first.innerHTML = first.innerHTML.replace(/^\s*\[!\w+\][-+]?\s*[^<\n]*(<br>)?/, "");
    const box = document.createElement("div");
    box.className = `callout ${kind}`;
    box.innerHTML = `<div class="callout-titre">${title}</div>`;
    while (quote.firstChild) box.appendChild(quote.firstChild);
    quote.replaceWith(box);
  }
}

function fixLinks(container, from) {
  for (const img of container.querySelectorAll("img[src]")) {
    const src = img.getAttribute("src");
    if (!/^(brut\/|data:|https?:)/.test(src)) {
      const path = resolve(from, decodeURIComponent(src));
      if (state.byPath.has(path)) img.src = raw(path);
    }
  }
  for (const a of container.querySelectorAll("a[href]")) {
    const href = a.getAttribute("href");
    if (/^https?:/.test(href)) { a.target = "_blank"; a.rel = "noopener noreferrer"; continue; }
    if (href.startsWith("#") || href.startsWith("brut/")) continue;
    const path = resolve(from, decodeURIComponent(href.split("#")[0]));
    if (state.byPath.has(path)) a.setAttribute("href", "#" + encodeURIComponent(path));
  }
}

async function renderMarkdown(path, text) {
  const { body, props } = frontmatter(text);
  if (!window.marked || !window.DOMPurify) return `${props}<pre>${esc(body)}</pre>`;
  const html = window.DOMPurify.sanitize(window.marked.parse(obsidian(body, path), { gfm: true }));
  const box = document.createElement("div");
  box.innerHTML = props + html;
  callouts(box);
  fixLinks(box, path);
  for (const code of box.querySelectorAll("pre > code.language-mermaid")) {
    const div = document.createElement("div");
    div.className = "mermaid";
    div.textContent = code.textContent;
    code.parentElement.replaceWith(div);
  }
  return box;
}

function csvTable(text, separator) {
  const rows = [];
  let row = [], cell = "", quoted = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (quoted) {
      if (c === '"' && text[i + 1] === '"') { cell += '"'; i++; } else if (c === '"') quoted = false; else cell += c;
    } else if (c === '"') quoted = true;
    else if (c === separator) { row.push(cell); cell = ""; }
    else if (c === "\n") { row.push(cell.replace(/\r$/, "")); rows.push(row); row = []; cell = ""; }
    else cell += c;
  }
  if (cell || row.length) { row.push(cell); rows.push(row); }
  if (!rows.length) return "<p class=\"discret\">Fichier vide.</p>";
  const [head, ...rest] = rows;
  return `<table><thead><tr>${head.map((h) => `<th>${esc(h)}</th>`).join("")}</tr></thead><tbody>` +
    rest.map((r) => `<tr>${r.map((c) => `<td>${esc(c)}</td>`).join("")}</tr>`).join("") + "</tbody></table>";
}

async function openFile(path) {
  state.current = path;
  document.body.classList.remove("menu-ouvert");
  renderTree($("filtre").value);
  $("chemin").textContent = path;
  const download = $("telecharger");
  download.hidden = false;
  download.href = raw(path);
  download.setAttribute("download", baseName(path));
  const content = $("contenu");
  content.innerHTML = '<p class="discret">Chargement…</p>';
  try {
    if (/\.md$/i.test(path)) {
      const rendered = await renderMarkdown(path, await fetchText(path));
      content.innerHTML = "";
      if (typeof rendered === "string") content.innerHTML = rendered; else content.appendChild(rendered);
      if (window.mermaid && content.querySelector(".mermaid")) {
        try { await window.mermaid.run({ nodes: content.querySelectorAll(".mermaid") }); } catch (e) { /* schéma laissé en texte */ }
      }
    } else if (IMAGE.test(path)) {
      content.innerHTML = `<img src="${raw(path)}" alt="${esc(baseName(path))}">`;
    } else if (/\.drawio$/i.test(path)) {
      const png = [path + ".png", path.replace(/\.drawio$/i, ".png"), path.replace(/\.drawio$/i, ".drawio.svg")].find((p) => state.byPath.has(p));
      content.innerHTML = (png ? `<img src="${raw(png)}" alt="${esc(baseName(path))}">` : '<p class="discret">Pas d\'export PNG à côté de ce schéma.</p>') +
        `<p class="discret">Schéma draw.io : téléchargez-le pour l'ouvrir dans draw.io ou Confluence.</p>`;
    } else if (/\.pdf$/i.test(path)) {
      content.innerHTML = `<p><a href="${raw(path)}" target="_blank" rel="noopener">Ouvrir le PDF dans un nouvel onglet</a></p>`;
    } else if (OFFICE.test(path)) {
      content.innerHTML = `<p>Document Office : <a href="${raw(path)}" download="${esc(baseName(path))}">télécharger ${esc(baseName(path))}</a>.</p>`;
    } else if (/\.(csv|tsv)$/i.test(path)) {
      content.innerHTML = csvTable(await fetchText(path), /\.tsv$/i.test(path) ? "\t" : (/;/.test((await fetchText(path)).split("\n")[0]) ? ";" : ","));
    } else if (/\.json$/i.test(path)) {
      const text = await fetchText(path);
      let pretty = text;
      try { pretty = JSON.stringify(JSON.parse(text), null, 2); } catch (e) { /* JSON invalide : tel quel */ }
      content.innerHTML = `<pre><code>${esc(pretty)}</code></pre>`;
    } else if (TEXT.test(path) || (state.byPath.get(path).size || 0) < 200000) {
      content.innerHTML = `<pre><code>${esc(await fetchText(path))}</code></pre>`;
    } else {
      content.innerHTML = `<p><a href="${raw(path)}" download>Télécharger ${esc(baseName(path))}</a></p>`;
    }
  } catch (error) {
    content.innerHTML = `<p class="discret">${esc(error.message || error)}</p>`;
  }
  const incoming = state.backlinks[path] || [];
  const aside = $("entrants");
  aside.hidden = !incoming.length;
  aside.querySelector("ul").innerHTML = incoming.map((p) => `<li><a href="#${encodeURIComponent(p)}">${esc(p)}</a></li>`).join("");
  $("contenu").parentElement.scrollTop = 0;
}

window.addEventListener("hashchange", () => {
  const path = decodeURIComponent(location.hash.slice(1));
  if (state.byPath.has(path) && path !== state.current) openFile(path);
});
document.addEventListener("DOMContentLoaded", () => {
  if (window.mermaid) window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict",
    theme: matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "default" });
  $("filtre").addEventListener("input", (e) => renderTree(e.target.value));
  $("menu").addEventListener("click", () => document.body.classList.toggle("menu-ouvert"));
  loadTree();
});
