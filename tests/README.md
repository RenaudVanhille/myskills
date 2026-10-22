# Jeu de tests

- `fixtures/` : documents réels et anonymisés (PDF, DOCX, PPTX, XLSX, images)
  et contextes de schémas (descriptions, ADR, extraits de code).
- `expected/` : pour chaque fixture, le résultat attendu, avec le même nom de
  base (`rapport.pdf` -> `rapport.md`, `contexte-paiement.md` -> `contexte-paiement.drawio`).

Chaque skill est testé dans les 5 outils sur ces fichiers avant d'être
considéré comme terminé. Ne mettez ici aucun document confidentiel.

## Exemples synthétiques

`uv run tests/make_fixtures.py` régénère `fixtures/samples/` : un DOCX, un
PPTX, un PDF texte, un PDF scanné et une image de schéma, utilisés pour tester
`doc-to-markdown` sans document réel.

## Lancer les tests

### 1. Scripts (rapide, sans modèle)

```bash
uv run tests/run.py            # cas de tests/cases.json
uv run tests/run.py --slow     # ajoute les cas lents (Laya, Pandoc)
uv run tests/run.py --only docx,obsidian --keep
```

Le cas `contrats` vérifie que chaque script, chaque skill et chaque agent a
son contrat, et que `CATALOG.md` est à jour. Chaque cas lance ensuite les
scripts d'un skill sur les fixtures et vérifie le code de sortie, les champs
du rapport annoncés dans le contrat, le rapport JSON, les fichiers produits et, s'il existe, la
ressemblance avec le résultat attendu de `expected/` (90 % minimum). Code de
sortie 1 si un cas échoue.

### 2. Agents (dans chaque outil)

`agent-cases.json` décrit des demandes à faire aux agents (`prompt`), les
fichiers à leur donner (`inputs`), le fichier qu'ils doivent produire
(`output`) et une grille d'affirmations (`rubric`). Copiez les `inputs` dans
un dossier de travail, lancez l'agent avec le prompt, puis notez le résultat :

```bash
uv run --with laya tests/judge.py outputs DOSSIER_DE_TRAVAIL
```

### 3. Déclenchement des skills

`triggers.json` associe des demandes au skill attendu. Le juge choisit un
skill d'après les seules descriptions des `SKILL.md` : une erreur signale une
description à préciser.

```bash
uv run --with laya tests/judge.py triggers
```

### Le juge

`judge.py` utilise un modèle de décision, qui répond par des probabilités à
des questions fermées au lieu de rédiger du texte :

- **Laya** (défaut) : local, rien ne sort du poste. PyTorch et ~1,3 Go de
  modèle sont téléchargés au premier lancement.
- **Microsoft Decision 1** via OpenRouter : `--backend decision1`, avec la
  variable `OPENROUTER_API_KEY`. Vérifiez l'identifiant du modèle dans le
  catalogue OpenRouter et passez-le à `--model` s'il diffère de
  `microsoft/decision-1`. Les textes jugés partent chez OpenRouter : à
  réserver aux documents de test.

Aucun skill livré ne dépend du juge.
