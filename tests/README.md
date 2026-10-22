# Jeu de tests

- `fixtures/` : documents réels et anonymisés (PDF, DOCX, PPTX, XLSX, images)
  et contextes de schémas (descriptions, ADR, extraits de code).
- `expected/` : pour chaque fixture, le résultat attendu, avec le même nom de
  base (`rapport.pdf` -> `rapport.md`, `contexte-paiement.md` -> `contexte-paiement.drawio`).

Chaque skill est testé dans les 4 outils sur ces fichiers avant d'être
considéré comme terminé. Ne mettez ici aucun document confidentiel.

## Exemples synthétiques

`uv run tests/make_fixtures.py` régénère `fixtures/samples/` : un DOCX, un
PPTX, un PDF texte, un PDF scanné et une image de schéma, utilisés pour tester
`doc-to-markdown` sans document réel.
