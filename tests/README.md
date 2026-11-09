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
uv run tests/run.py --slow     # ajoute les cas lents (navigateur, Pandoc, réseau)
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

Une étape peut aussi être `{"copy": [source, destination]}` (fichier de
travail), porter `"env"` (variables de l'étape, `{out}` permis : cache isolé,
`MYSKILLS_OFFLINE`) ou `"exit": "any"` quand le code dépend de la machine.
`"report_in"` admet une valeur parmi une liste (deux candidats également
justes en tête de `route.py`, par exemple).

Le cas `routage-reference` est le jeu de demandes de référence du routage :
une demande courante par ligne et le candidat attendu en tête. Toute
demande mal routée s'y ajoute avant de corriger les synonymes de `route.py`
ou les `keywords` du workflow.

### 2. Agents (dans chaque outil)

`agent-cases.json` décrit des demandes à faire aux agents (`prompt`), les
fichiers à leur donner (`inputs`), le fichier qu'ils doivent produire
(`output`) et une grille d'affirmations (`rubric`). Copiez les `inputs` dans
un dossier de travail, lancez l'agent avec le prompt, puis notez le résultat :

```bash
uv run --with laya tests/judge.py outputs DOSSIER_DE_TRAVAIL
uv run tests/judge.py --backend checks outputs DOSSIER_DE_TRAVAIL
```

Un cas peut aussi porter des contrôles sans modèle (`checks` : fichier
présent, texte ou motif contenu, valeur ou nombre d'éléments d'un JSON,
valeur d'un champ de chaque élément d'une liste : `each` + `in`) ;
`--backend checks` ne fait que ceux-là. La note du cas (`score`, de 0 à 1)
est la part des contrôles et des affirmations vérifiés.

Un cas de `cases.json` qui lit un modèle local le déclare dans `models` :
sans ce modèle dans le cache vérifié, `run.py` ne le lance pas et l'annonce
comme prérequis manquant, avec la commande `doctor.py --prefetch` (en CI,
variable `CI`, il tourne quand même et échoue si le modèle manque). De même
pour un outil externe déclaré dans `tools` (`drawio`).

Chaque workflow a au moins un cas d'agent : `id` `workflow-<nom>` ou
`bout-en-bout-<nom>`, ou champ `workflow` (contrôlé par le cas `contrats`).

Les cas `reference-*` (et `migration-evaluation`) sont des missions de
référence, sur des documents fictifs mais complets : un appel d'offres
public (`fixtures/references/ao/` : RC, CCTP, BPU, exigences et options),
un dossier d'architecture reçu d'un prestataire
(`fixtures/references/dossier-recu/`) et une migration. On les rejoue à
chaque PR qui touche le chiffrage, la revue ou les workflows.

### 3. Coût des agents (Claude Code)

`cost.py` joue les cas de `agent-cases.json` dans Claude Code (`claude -p`,
plugin chargé depuis le dépôt, modèle fixe) et ajoute à `costs.csv` une ligne
par cas : coût, tokens, nombre de tours, sous-agents lancés, fichier produit
ou non, et la note de l'exécution (`score` : contrôles du cas par défaut,
grille avec `--judge laya`) : la qualité se suit avec le coût. Lancez-le avant et après une modification des agents ou des skills
pour en chiffrer l'effet :

```bash
uv run tests/cost.py --label avant --only extraire-docx,schema-drawio
uv run tests/cost.py --label apres --only extraire-docx,schema-drawio --keep
```

Avec `--keep`, les dossiers de travail restent, pour `judge.py outputs`.
Chaque cas coûte quelques centimes avec `sonnet`.

### 4. Justesse de Laya sur les exigences

`fixtures/laya/phrases.json` étiquette 112 phrases de cahier des charges et de
compte rendu (exigence ou non, nature, catégorie), avec des pièges voulus :
exigences sans verbe normatif, verbes normatifs hors exigence. `laya_eval.py`
pose à Laya les questions de `req_build.py --laya` et compare au repli par
regex : précision, rappel et F1, meilleur seuil, fausses alertes sur la nature
et la catégorie. Laya se garde si la règle de `req_build.py` (regex ou
Laya) a un meilleur F1 que la regex seule.

```bash
uv run tests/laya_eval.py --markdown laya-eval.md
```

Le job `rendus` de la CI le lance à chaque PR (résumé du job et artefact
`laya-eval`), avec les cas lents de `run.py` et l'export par draw.io Desktop.

### 5. Déclenchement des skills

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
