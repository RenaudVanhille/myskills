# Brand library: icons, ready-made diagrams, maps and accessibility

`assets/brand-library/` holds pieces extracted from the brand's own PowerPoint libraries
(`ICON_LIBRARY.pptx` and `2024_BIBLIOTHEQUE_SCHEMA_VFR.potx`). They are brand assets: keep the
skill repository private.

| File | Content |
|---|---|
| `icons.json` | index of the 655 pictograms: id, category, English and French keywords, `auto` (false for social-network logos and bare arcs, which are never picked on their own) |
| `icons.xml.gz` | the pictograms as native vector shapes |
| `schemas.json` + `schemas.xml.gz` | 7 ready-made diagrams and the Europe map, with the text slots each item fills |

Rebuild after the libraries change: `python SKILL_DIR/scripts/tools/build_schemas.py path/to/schema-library.potx`.
The icon keywords live in `icons.json`; add synonyms there (`en` / `fr` lists) when an obvious
word does not find its icon.

## Icons

Icons are added on their own when **every** item of the slide finds a convincing pictogram, each a
different one. Otherwise the slide has none, so a slide never mixes items with and without icons.

| Slide | Where the icon goes |
|---|---|
| cards (grid) | in the coloured header, left of the label |
| cards (bands) | in the coloured arrow, left of the label |
| highlighted rows (unnumbered short list) | at the start of each row |
| process (chevrons) | above each chevron, or at the top of each description box |
| process (numbered rows) | after the step number |
| key figures (2–4) | above each number |
| hub (drawn) | left of each satellite label |

How the match works: the item's label (for a sentence, its first four words) is compared with the
icon keywords in English and French, ignoring accents, plurals and word endings
(`sécurité` = `security`, `déploiements` = `deploy`). A keyword that names what the icon *is*
weighs more than an association.

- Write labels with a concrete noun: **Security**, **Budget**, **Training**, **Cloud**,
  **Customer support**, **Recrutement**, **Formation**. Abstract labels (**Phase 2**, **Pillar A**)
  find nothing, and the slide stays without icons.
- Force icons on a slide with a weaker match: `<!-- slide: cards; icons=on -->`.
- Turn them off for a slide: `<!-- slide: cards; icons=off -->`; for the deck: `icons: off` in
  the front matter; for a run: `--no-icons`.
- Icons take the item's accent colour, or white/dark on a coloured header (whichever is readable).
  They are flagged as decorative, so screen readers skip them.

## Ready-made brand diagrams

When the template is the brand template (its theme colours match the library's) and a slide has
exactly the number of items one of these diagrams holds, the brand's own drawing is copied and its
text slots are filled. Text keeps the library's fonts and sizes; it may shrink to 75 % but never
below 10 pt. If it would not fit, the tool draws its own version instead.

| Kind | Items | Library slide | Looks like |
|---|---|---|---|
| funnel | 5 | 12 | coloured funnel with numbers, label + text on the right |
| pyramid | 6 | 11 | stacked steps 01–06, label + text on the right |
| process | 4 | 23 | four numbered rings with the text inside |
| process | 6 | 27 | six rings 01–06, text below |
| hub | 4 | 17 | centre circle with four corner boxes |
| hub | 8 | 18 | centre circle, four boxes on each side |
| timeline | 6 | 45 | year badges alternating above and below a line |

- A lead sentence is kept only when it fits on the template's subtitle line (120 characters).
- Turn it off for a slide with `<!-- slide: process; schema=off -->`; for the deck with
  `schemas: off` in the front matter; for a run with `--no-brand-schemas`.
- The copy is a group of native shapes named `Diagram <name>`: ungroup it in PowerPoint to edit.

## Maps

A list of European countries becomes a map of Europe with those countries in an accent colour,
and the list beside it.

```markdown
## Nos implantations

- **France** : siège et 12 agences
- **Allemagne** : 5 bureaux
- **Espagne** : centre de services
```

- Triggered by three or more items that start with a country name (English or French), or two
  under a heading such as countries, locations, offices, présence, implantations, markets.
- Groups get one colour each: a top-level item that is not a country, with countries indented
  under it (up to four groups). The group names become the legend.
- 51 countries and territories: the EU, the UK, Norway, Switzerland, Iceland, the Balkans,
  Ukraine, Moldova, Belarus and Turkey. Russia and Cyprus are not on the map; other countries
  leave the slide as a list.
- Force it with `<!-- slide: map -->`.

## Accessibility

- **Alt text.** Each diagram is grouped and the group gets a description written from its content
  ("Process diagram: Plan: …; Code: …"), in the deck's language. Charts, tables and pictures get
  one too (pictures use the Markdown alt text, so write it: `![Team workshop](img.png)`).
  Icons are flagged as decorative.
- **Contrast.** Text on a coloured shape is white or dark, whichever meets WCAG 2.1 (4.5:1, or 3:1
  for large bold text) against the template's actual colours. On the brand template, orange
  shapes therefore get dark text, because white on orange is only 2.9:1. Accent colours used as
  text (key figures, timeline labels) are darkened just enough to be readable.
- **Check.** `--a11y` lists every description after rendering and counts pictures, charts or
  tables left without one. PowerPoint's own *Check Accessibility* should then report no missing
  alt text.
