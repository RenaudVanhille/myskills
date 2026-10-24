# The slide plan (JSON)

`--plan-only` prints every decision without rendering; `--plan plan.json` saves it while rendering.
Edit it and render it with `--from-plan`:

```bash
uv run SKILL_DIR/scripts/pptx_build.py --md2pptx notes.md --plan-only --plan plan.json
uv run SKILL_DIR/scripts/pptx_build.py --md2pptx plan.json --from-plan -o notes.pptx
```

## Top level

```json
{
  "title": "Automating Tier-1 Customer Support",
  "purpose": {"type": "proposal", "label": "Proposal", "confidence": 1.0, "source": "heuristics"},
  "lang": "en",
  "source": "examples/sample.md",
  "slides": [ ... ],
  "parts": [{"title": "Costs & return", "sections": ["Budget", "Savings"], "auto": true}],
  "warnings": ["slide 7: title has 72 characters (over 60, it is shrunk to fit): '...'"]
}
```

`"variants": "off"` appears when automatic card variants were switched off (front matter or
`--no-variants`). `parts` and `warnings` only appear when there are any; they are informational (the part dividers are
already in `slides`).

## Slides

Every slide has `kind` and `title`; optional `lead` (intro sentence) and `notes` (speaker notes).
Diagram, list and table slides may also carry `banner` (dark key-message band above the visual)
and `takeaway` (bar under it).
Text fields accept inline Markdown (`**bold**`, `*italic*`, `` `code` ``, links).

| kind | fields |
|---|---|
| `title` | `subtitle`, `byline` |
| `agenda` | `items`: list of strings |
| `section` | `subtitle`, `number`; part dividers also carry `part: true` and `covers` (the section titles in the part) |
| `closing` | `subtitle`, `short_title` (used when the layout expects a short text such as "Q&A") |
| `bullets` | `items`: `[{"text", "children": [...]}]`, `ordered`, `plain`, `style` (`"rows"` = highlighted rows) |
| `text` | `paragraphs`: list of strings |
| `stairs` | `items` as for process; the first entry of `details` is shown under the step |
| `flow` | `items` (3: inputs, core, outputs) as for process; optional `panels`: `[{"label", "text", "details"}]` |
| `process`, `cycle`, `timeline`, `cards`, `pyramid` | `items`: `[{"label", "text", "details": [...]}]`; `cards` also `variant` (`"grid"` or `"rows"`: set from a hint, from code labels, or alternated between consecutive card slides) |
| `stats` | `items`: `[{"value": "38%", "text": "of tickets ...", "details": [...]}]`; one item = key figure |
| `hierarchy` | `items`: nested `[{"text", "children": [...]}]`; a single top item is the root |
| `funnel` | `items`: like `process`; a numeric `label` is shown inside the funnel |
| `hub` | `root`: `{"label", "text", "details"}` (null = the slide title), `items`: like `process` (3–8) |
| `rings` | `items`: `[{"value": "72%", "text", "percent": 0.72}]` |
| `gantt` | `scale`: column labels; `items`: `[{"label", "range", "start", "end"}]` (0-based column indexes, inclusive) |
| `matrix` | `header`, `rows` like `table`; rating cells (●◕◑◔○, `3/4`, `★★☆`, 0–4) become Harvey balls |
| `map` | `groups`: `[{"label", "countries": ["FR", "DE"], "items": [text]}]` (ISO 3166 codes) |
| `comparison` | `columns`: `[{"title", "text", "items": [{"text", "children"}]}]` (2–3) |
| `table` | `header`: list, `rows`: list of lists |
| `chart` | `chart`: `{"categories", "series": [{"name", "values"}], "chart_type": "line" \| "column" \| "bar" \| "pie", "percent"}` |
| `code` | `code`, `lang` |
| `quote` | `quote`, `attribution` ("Name, role") |
| `image` | `src` (relative to the Markdown file, or a URL), `alt`; optional `caption`, `items` (text beside the picture), `plain`, `ordered`, `position` (`left`/`right`, side of the picture) |

Any slide may also carry `icons` (`"on"`/`"off"`) and `schema` (`"off"`). At the top level,
`"icons": "off"` or `"schemas": "off"` apply to the whole deck.

Changing `kind` in the plan also works when the fields match; for example, `cycle` ↔ `process` ↔
`timeline` share the same `items` shape.
