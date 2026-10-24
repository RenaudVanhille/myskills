# Troubleshooting

Start with `uv run SKILL_DIR/scripts/pptx_build.py --md2pptx --check`.

| Symptom | Fix |
|---|---|
| `python: command not found` | use `python3` (macOS/Linux) or `py` (Windows). Python 3.9+ is required. |
| First run fails while installing dependencies | the machine has no access to PyPI. Install offline or from your mirror: `python -m pip install -r SKILL_DIR/scripts/requirements.txt`, then set `MD2PPTX_NO_BOOTSTRAP=1`. |
| Want the dependencies in a specific place | set `MD2PPTX_VENV=/path/to/venv` before the first run. |
| Wrong template used | the last output line says which one and why; see the order in `templates.md`, or pass `--template`. |
| Slides on the wrong layout, or missing titles | `--list-layouts -t brand.potx`, then `--layout role="Layout name"` or a sidecar `brand.md2pptx.json`. |
| "Layout 'X' for role 'Y' not found" | the name must match exactly as `--list-layouts` prints it. |
| A section got the wrong diagram | add `<!-- slide: KIND -->` under its heading (`--kinds` lists them). |
| A list became bullets instead of a diagram | write items as `**Label**: text`, or number them for a process. |
| Text looks small in a diagram | shorten labels (≤ 3 words work best) and move details into the text after the colon. |
| Labels come out in the wrong language | add `lang: fr` / `lang: en` to the front matter, or pass `--lang`. |
| Output file is large | brand templates embed their background images; that is the template's size, not the content. |
| `--preview` does nothing | LibreOffice (`soffice`) isn't installed. The .pptx itself is fine. Previews substitute fonts LibreOffice doesn't have, so spacing can differ slightly from PowerPoint. |
| PowerPoint shows "repair" | re-run with the latest skill version and report the Markdown that caused it. |
