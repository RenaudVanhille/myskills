# Brand templates

## Which template is used

First match wins:

1. `--template path/to/brand.potx` (a `.pptx` also works)
2. `MD2PPTX_TEMPLATE` environment variable
3. `.md2pptx/` folder with one `.potx`, in the current directory or any parent: a per-project brand
4. `assets/templates/brand/` inside the skill: the organisation brand shipped with the skill
5. `assets/templates/default.potx`: neutral 16:9 fallback

The command's last line says which template it used and why. `--check` shows the same.

To ship your organisation's brand with the skill, put exactly one `.potx` in
`assets/templates/brand/` before publishing the skill repository. Keep that repository private if
the template is confidential.

## What is taken from the template

- **Slide size, masters, layouts, logos, footers, page numbers.** Sample slides inside the
  template (for example a brand manual) are removed; only masters and layouts are used.
- **Colours**: every shape uses theme colours. Accent slots that repeat the same colour are
  skipped, so neighbouring shapes stay distinct.
- **Fonts**: theme fonts. Only code blocks use Courier New.
- **Footer**: the layout's footer placeholder is filled with the deck title (`--footer "text"`,
  `--no-footer`).

## Layout roles

| Role | Used for | Detected from |
|---|---|---|
| `title` | cover | name contains cover / title slide / couverture, with title + subtitle placeholders; layouts without a picture placeholder preferred |
| `section` | chapter divider (chapter number goes into an "XX." or "01" placeholder) | section / divider / chapter / chapitre / intercalaire |
| `content` | every content slide; the lead sentence goes in a small subtitle placeholder | title + one large body placeholder, or names like Title and Content, Text_1Column |
| `title_only` | diagrams, tables, charts | "title only" / "titre seul", else the content layout with its body removed |
| `quote` | blockquotes: quote, name, role | quote / citation / testimonial |
| `closing` | last slide; a short prompt like "Q&A" gets "Q&A" / "Q&R" | back cover / closing / end / thank / merci |
| `blank` | not used by default | blank / vide |

Two optional layout families are also used when the template has them (no role to configure):

| Layouts | Used for | Detected from |
|---|---|---|
| numbered agenda (`Summary_*`) | the agenda, when a layout has exactly as many number + title slots as there are items | name contains summary / sommaire / agenda / contents, with 3+ placeholders prompting "XX" or "01" |
| key figure (`Key_Figure_*`) | a section with one headline number plus a lead sentence or sub-items | name contains key figure / chiffre / big number / KPI, with one "XX" or "XX%" placeholder |

Check the result:

```bash
uv run SKILL_DIR/scripts/pptx_build.py --md2pptx --list-layouts -t brand.potx
```

## Overriding

On the command line:

```bash
--layout content="Text_1Column_2" --layout section="Chapter_2"
```

In a JSON file passed with `--layout-map roles.json`, or permanently in a sidecar file next to the
template named `<template name>.md2pptx.json`:

```json
{ "layouts": { "content": "Text_1Column_1", "section": "Chapter_1", "closing": "Back_Cover_1" } }
```

## Tested templates

| Template | Result |
|---|---|
| `default.potx` (bundled) | all roles detected |
| An organisation template with 52 layouts | Cover_3, Chapter_1, Text_1Column_1, Quote_2, Back_Cover_1 detected automatically; Summary_1/2/3 (4, 6, 8 items) and Key_Figure_1 used when they fit |

## Brand library

In myskills the brand library (`assets/brand-library/`) is not shipped: diagrams and the map of
Europe are drawn with the template's theme colours, and no pictograms are added. See
`references/brand-library.md` for what it brings when it is present.

## Rebuilding the default template

`assets/templates/default.potx` comes from the md2pptx skill, where `make_default_template.py`
regenerates it.
