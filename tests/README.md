# Jeu de tests

- `fixtures/` : documents synthétiques (PDF texte et scanné, DOCX, PPTX,
  image), descriptions de schémas, exigences et options d'un projet fictif
  (portail de sinistres).
- `expected/` : pour chaque fixture, le résultat attendu, avec le même nom de
  base (`rapport.pdf` -> `rapport.md`, `contexte-paiement.md` -> `contexte-paiement.drawio`).

Les scripts sont testés par `run.py` sous Linux, macOS et Windows (CI
GitHub Actions) ; les agents se testent dans chaque outil avec
`agent-cases.json`. Ne mettez ici aucun document confidentiel.

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

Le cas `contrats` valide chaque `contract.json` contre son schéma, vérifie
que chaque script est déclaré, que les passages de main visent des skills et
des agents qui existent, que les exemples de message de passage et de
rapport final sont conformes, et que les fichiers générés sont à jour.
Le cas `regles` vérifie les règles mécaniques d'[`AGENTS.md`](../AGENTS.md) :
`SKILL.md` (nom, description, taille), en-tête PEP 723 des scripts, schéma
de chaque rapport JSON, agents sans outil web ni commande réseau, import et
export séparés, pas de Puppeteer.
Chaque cas lance ensuite les scripts d'un skill sur les fixtures et vérifie
la conformité de la description JSON en entrée au schéma `input` du contrat
(avec `jsonschema`, en plus du validateur intégré aux scripts), le code de
sortie, la conformité du rapport au JSON Schema du contrat, des
valeurs du rapport, les fichiers produits et, s'il existe, la
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

### 3. Coût des agents (Claude Code)

`cost.py` joue les cas de `agent-cases.json` dans Claude Code (`claude -p`,
plugin chargé depuis le dépôt, modèle fixe) et ajoute à `costs.csv` une ligne
par cas : coût, tokens, nombre de tours, sous-agents lancés, fichier produit
ou non. Lancez-le avant et après une modification des agents ou des skills
pour en chiffrer l'effet :

```bash
uv run tests/cost.py --label avant --only extraire-docx,schema-drawio
uv run tests/cost.py --label apres --only extraire-docx,schema-drawio --keep
```

Avec `--keep`, les dossiers de travail restent, pour `judge.py outputs`.
Chaque cas coûte quelques centimes avec `sonnet`.

### 4. Déclenchement des skills

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
