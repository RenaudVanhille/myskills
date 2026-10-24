# Markdown guide: how content becomes slides

## Document structure

| Markdown | Result |
|---|---|
| Front matter (`---` block at the top) | `title`, `subtitle`, `author`, `date`, `purpose`, `lang`, `agenda_title` |
| The only `#` heading | deck title (cover slide) |
| First short paragraph under it (≤ 140 characters) | cover subtitle |
| No `#` heading | the first `##` with only a short paragraph becomes the cover; otherwise the file name |
| Other paragraphs before the first `##` | an "Overview" / "Introduction" slide |
| Each `##` | a slide, or a chapter divider when it has two or more `###` |
| Each `###` | a slide inside that chapter |
| `####` and deeper | bold paragraph on the current slide |
| `---` inside a section | forces a new slide |

An agenda is added when there are 3 or more `##` sections (`--agenda` / `--no-agenda` force it).
A closing slide is added unless the last section is already a Q&A (`--no-closing` removes it).

## Parts (chapters) for long documents

A long talk reads better in 3 to 6 parts, each opened by a numbered chapter slide, with the agenda
listing the parts instead of every section.

- **Your choice:** put `<!-- part: Part title -->` on its own line directly under the first `##` of
  each part (written just above that `##` also works). The parts then follow your markers exactly.
- **Automatic:** with 12 or more `##` sections and no markers (and no `###` chapters already), the
  sections are grouped by theme (context, solution, models, architecture, costs, governance,
  performance, hosting, roadmap, team, results) and each part gets a theme title, or the title of
  its first section when no theme stands out. The command prints the parts it chose.
- The agenda uses the template's own numbered agenda layout (e.g. `Summary_*`) when one has exactly
  as many slots as there are parts or sections; otherwise it is drawn.

## Front matter example

```markdown
---
title: Quarterly review
subtitle: Customer Operations, Q3 2026
author: Reno
date: October 2026
purpose: status_report     # proposal | status_report | training | strategy | technical | postmortem | research
lang: en                   # en | fr
icons: off                 # optional: no pictograms in this deck
schemas: off               # optional: never reuse the brand's ready-made diagrams
variants: off              # optional: cards always a grid unless a hint says rows
---
```

## Automatic visuals

The tool looks at the heading text (in English and French) and at the shape of the list.
Icons, the brand's ready-made diagrams, maps and accessibility are described in
`references/brand-library.md`.

| Visual | Triggered by | Write it like |
|---|---|---|
| process | ordered list of 3–7 short items, or a steps / process / workflow / étapes heading with labelled items | `1. **Capture**: all channels in one queue` |
| cycle | cycle, loop, lifecycle, iterative, continuous, flywheel, boucle, amélioration continue in the heading | `- **Measure**: track satisfaction` |
| timeline | 3–8 items starting with a date or period | `- **Q1 2027**: pilot` · `- T2 2027: déploiement` · `- Week 3: launch` |
| hierarchy | nested list under organisation, org chart, structure, team, architecture, components, organigramme | top item with indented children |
| hierarchy (decision tree) | a flat list of `condition → outcome` lines, or a repeating pattern such as Task / Model / Task / Model (an optional first line is the root) | `- Short question → small model` |
| cards | 2–6 items all written `**Label**: text` | `- **Keep hiring**: costs grow linearly` |
| stats | 2–4 items all starting with a number | `- **38%** of tickets wait more than 24h` |
| stats (key figure) | one item starting with a number, optionally with sub-items that explain it; uses the template's key-figure layout (e.g. `Key_Figure_*`) when the section also has a lead sentence or sub-items | `- **72%** of the bill comes from agents` |
| pyramid | "pyramid" in the heading, 3–6 items | top level first |
| funnel | funnel, entonnoir, tunnel, conversion in the heading, 3–6 items (a number as label is shown inside the funnel) | `- **10,000**: website visitors` |
| hub | one top item with 3–8 indented items under a hub, ecosystem, platform, au cœur, au centre, pillars heading | `- **Platform**: …` then indented `- **Sales**: …` |
| rings | 2–5 items all starting with a percentage | `- **72%**: of employees use the intranet` |
| gantt | 2–10 items starting with a date **range** on one scale: months, quarters, halves, weeks, sprints | `- **Jan–Mar 2026**: Discovery` · `- Weeks 1-3: Audit` · `- T2-T4: Construction` |
| matrix | a table whose cells are ratings: ● ◕ ◑ ◔ ○, `3/4`, `★★☆`; drawn as Harvey balls | `\| Data quality \| ◑ \| ● \|` |
| map | 3+ items starting with a European country, or groups of countries | `- **France**: 12 offices` |
| comparison | 2–3 `###` under a heading with vs, versus, comparison, before/after, options, avant/après; or 2–4 `###` with `<!-- slide: comparison -->` under the `##` (columns, e.g. teams or personas) | each `###` holds one short list, or each one code block (code side by side) |
| stairs | maturity, staircase, escalier, paliers, montée en puissance/compétences, step-up in the heading, 3–6 items; the first sub-item of each level is its outcome, shown under the step | `1. **Experiment**: test on our own work` + indented `- First real use cases` |
| flow | exactly 3 labelled items reading inputs → core → outputs (first label says inputs, context, existing, data, entrants…; last says outputs, deliverables, results, services, livrables…). The middle box is the core, in the dark brand colour. A second list right after it (use `*` bullets so Markdown keeps it separate) of 2–4 labelled items becomes panels under the flow | see "Case-study one-pager" below |
| cards as tags | 3–6 cards whose labels are short codes (P0–P3, T1, L2, S1) are drawn as ranked bands: tag on the left, description on the right | `- **P0**: critical path, security` |
| chart | table whose first column is time-like (months, quarters, years) and other columns numeric; or a trend / growth / volume / évolution heading | normal Markdown table |
| table | any other table | normal Markdown table |
| bullets | everything else, and lists under next steps / actions / prochaines étapes | normal list |

Process steps written as whole sentences are drawn as numbered rows instead of chevrons.
A short flat list (2–6 items) is drawn as highlighted rows, numbered when the list is ordered;
add `<!-- slide: bullets -->` to keep plain bullets. When two card slides follow each other, the
second is drawn as horizontal bands so the deck doesn't repeat the same picture (a grid, then
bands, then a grid again; a slide with more than 5 cards stays a grid). Choose the look yourself
with `<!-- slide: cards rows -->` or `<!-- slide: cards grid -->`; a hint always wins. To switch
the automatic choice off for a whole deck, add `variants: off` to the front matter (or pass
`--no-variants`): every card slide is then a grid, code-labelled cards included, unless hinted.

## Key message banner and takeaway

A short blockquote (under 200 characters, no `— author` line) in the same section as a list,
table or diagram is not a separate quote slide any more: before the visual it becomes a dark
banner above it, after the visual a takeaway bar under it. A quote on its own, a long quote or an
attributed quote is still a quote slide; `<!-- slide: quote -->` forces one.

```markdown
## Using AI: protect client trust

> AI assists. The employee stays responsible for use, control and distribution.

- **Client obligations**: respect confidentiality and data location clauses
- **Our markers**: security and sovereignty by design
- **Employee policy**: no client data in public AI tools

> Four questions before sharing: allowed tool? compatible data? requirements met? human check?
```

## Case-study one-pager (flow)

```markdown
## MaaS | BMAD at the heart of AI delivery

From the existing NAM/BFC code to reusable, tested MaaS components.

> Structure, document, generate and test MaaS delivery with human validation.

- **Existing assets (inputs)**: project context
  - Code, API and legacy
  - Specs, user stories and mock-ups
- **Scope · Architecture · Build**: BMAD core
  - Vision · PRD · UX · Epics & Stories
- **Deliverables**: what the project produced
  - White-label web components
  - Back-end, BFF and unit tests

* **Context & governance**: BMAD pilot on NAM and BFC, dedicated branch.
* **Project stakes**: move the customer account to product mode.
* **Securing through tests**: unit-test coverage above 60%.
```

Use `<!-- slide: flow -->` when the labels don't say inputs and outputs; with any other count of
items than 3, all boxes get the same weight.

## Images

Write a normal Markdown image on its own line, under the heading of the slide it belongs to:

```markdown
## Target architecture

- Hosted on Azure
- Data encrypted at rest

![Logical view of the platform](images/architecture.png)
```

| Under the heading | Result |
|---|---|
| the image alone | picture slide, scaled to fit the content area, alt text as caption |
| the image + a short plain list (≤ 7 lines) or short paragraphs (≤ 600 characters) | text on the left, picture on the right |
| the image + a list that becomes a diagram, a table, or a second image | one slide each |

- The path is relative to the Markdown file (`images/x.png`, `../assets/x.jpg`); absolute paths
  and `http(s)://` URLs also work. Spaces must be written `%20` or the path wrapped in `<...>`.
- Formats: PNG, JPG, GIF, BMP, TIFF directly; WebP and others are converted; SVG needs
  `pip install cairosvg`.
- Caption: the title in `![alt](path "Caption")` if given, otherwise the alt text. `![](path)`
  gives no caption.
- `<!-- slide: image; position=left -->` puts the picture on the left and the text on the right.
- A missing or unreadable file never stops the run: the slide gets a grey placeholder and the
  command prints `warning: image not found ...`.
- An image in the middle of a sentence is moved out of the text onto the slide.

## Hints (override any decision)

Put the hint on its own line directly under the heading:

```markdown
## Request lifecycle
<!-- slide: process -->
- Client sends query to the gateway
- Query parser normalises terms
```

| Hint | Effect |
|---|---|
| `<!-- slide: KIND -->` | force a kind: process, cycle, timeline, hierarchy, cards, stats, pyramid, comparison, funnel, hub, rings, gantt, matrix, map, chart, table, bullets, text, image |
| `<!-- slide: KIND; title=New title -->` | also change the slide title |
| `<!-- slide: KIND; icons=on -->` / `icons=off` | force or remove pictograms on this slide |
| `<!-- slide: cards rows -->` / `cards grid` | cards as horizontal bands / as a grid (same as `cards; variant=rows`); beats the automatic choice and `variants: off` |
| `<!-- slide: KIND; schema=off -->` | draw the diagram instead of using the brand's ready-made one |
| `<!-- notes: text -->` | speaker notes for that slide (kept above the generated talking points) |
| `<!-- part: Title -->` | start a new part (chapter) at this section, see above |

## Text that doesn't fit

- A short first paragraph before a list or table becomes the slide's lead sentence (in the
  template's subtitle line when it has one).
- Longer or later paragraphs go into the speaker notes.
- Long lists and tables continue on extra slides titled "(cont.)" / "(suite)".
- Inline **bold**, *italic*, `code` and [links](https://example.com) are kept.

## Speaker notes and text checks

- Every slide gets speaker notes: the key message (the lead sentence), the talking points (each
  item in full) and a transition to the next slide, in the deck's language, after any notes you
  wrote. `--no-auto-notes` keeps only yours.
- Card, step and list texts start with a capital letter ("décomposition du problème" becomes
  "Décomposition du problème"); words such as `iPhone` or code are left alone.
- Titles lose a trailing period or colon. A title longer than 60 characters is shrunk to fit and
  reported as `warning: slide N: title has … characters`; shorten it in the Markdown.
