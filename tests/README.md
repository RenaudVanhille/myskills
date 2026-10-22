# Jeu de tests

- `fixtures/` : documents réels et anonymisés (PDF, DOCX, PPTX, XLSX, images)
  et contextes de schémas (descriptions, ADR, extraits de code).
- `expected/` : pour chaque fixture, le résultat attendu, avec le même nom de
  base (`rapport.pdf` -> `rapport.md`, `contexte-paiement.md` -> `contexte-paiement.drawio`).

Chaque skill est testé dans les 4 outils sur ces fichiers avant d'être
considéré comme terminé. Ne mettez ici aucun document confidentiel.
