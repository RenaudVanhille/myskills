# Règles des skills et des agents

Ce fichier s'applique à tout skill et à tout agent de ce dépôt, présent ou à
venir. Il est lu par Copilot, OpenCode, Kiro, Hermes et, via `CLAUDE.md`, par
Claude Code. Une règle marquée **(vérifiée)** est contrôlée par le cas
`regles` de `uv run tests/run.py` ; les autres sont relues à la main.

Les skills et les agents servent dans des workflows multi-agents : chaque
étape doit être prévisible, respecter son contrat à la lettre et coûter le
moins de tokens possible.

## 1. Portabilité

- Un skill est un dossier `skills/<nom>/` au format
  [Agent Skills](https://agentskills.io) : `SKILL.md` avec `name` égal au nom
  du dossier et une `description` de 1024 caractères au plus **(vérifiée)**.
  `SKILL.md` reste sous 500 lignes **(vérifiée)** ; le détail va dans
  `references/`, chargé à la demande.
- Il fonctionne dans GitHub Copilot, Claude Code, OpenCode, Kiro et Hermes,
  installé comme plugin (voir le README). Rien de propre à un seul outil dans
  un `SKILL.md`.
- Un agent s'écrit une seule fois dans `src/agents/<nom>.md` (format neutre) ;
  `scripts/build.py` génère les versions Claude Code et Copilot,
  `scripts/install.py` celles d'OpenCode, Kiro et Hermes. On ne modifie
  jamais un fichier généré.

## 2. Contrats et validation

Chaque étape d'un workflow valide ce qu'elle reçoit et ce qu'elle produit.

- **Contrat** : chaque skill a un `contract.json`, chaque agent un
  `src/agents/<nom>.contract.json` **(vérifiée)**. Ils font foi ; la section
  « Contrat » des `SKILL.md`, `CATALOG.md` et `catalog.json` en sont générés
  par `uv run scripts/build.py` **(vérifiée : fichiers à jour)**.
- **Scripts déclarés** : tout script de `scripts/` figure dans le contrat,
  avec usage, options et codes de sortie (0 succès, 1 erreur) **(vérifiée)**.
- **Entrée** : un script qui lit une description JSON déclare son JSON Schema
  dans le champ `input` du contrat et la valide avant tout travail avec
  `scripts/lib/spec_schema.py` (copie de `shared/scripts/spec_schema.py` faite
  par `build.py`). Toutes les erreurs d'un coup, chacune précise et
  actionnable : le chemin (`items/2/type`), la valeur reçue et les valeurs
  possibles ou proches (« lamda » : lambda ?). `--schema` affiche le schéma
  sur une ligne, pour que le modèle l'obtienne sans lire le contrat. Une
  entrée CSV est contrôlée de la même façon (colonnes, ligne fautive). Une
  entrée invalide donne le code 1 et un rapport avec `errors`, sans fichier
  produit à moitié.
- **Sortie** : le livrable est vérifié par un script avant d'être rendu
  (`check_drawio.py`, `validate.py`, export et relecture de l'image...).
  Un livrable non vérifié est signalé comme tel dans le rapport final.
- **Rapport** : un script écrit un rapport JSON court sur la sortie standard,
  dont le JSON Schema est dans le contrat **(vérifiée : schéma présent et
  valide)** ; `tests/run.py` valide chaque rapport contre ce schéma. Champs
  `errors` et `warnings` toujours présents.
- **Entre agents** : une demande suit `shared/schemas/handoff.schema.json`,
  un agent termine par le rapport final de
  `shared/schemas/agent-report.schema.json`, en JSON sur une ligne. Un passage
  de main vise un skill ou un agent qui existe **(vérifiée)**.

## 3. Sobriété en tokens

- Le script fait le travail mécanique : mise en page, styles, nettoyage,
  rendu, validation. Le modèle n'écrit qu'une description courte (JSON, CSV)
  et ne décide que ce qui demande du jugement. Jamais de XML draw.io,
  Excalidraw ou de mise en page écrits à la main par le modèle.
- Le modèle ne relit pas un fichier qu'il vient de produire : il lit le
  rapport du script. Il ne charge `references/` que si le `SKILL.md` le dit.
- Rapports et messages courts : des compteurs et des listes d'erreurs, pas
  de contenu recopié. Pas de résumé de ce qui vient d'être fait.
- Une seule question à l'utilisateur, et seulement si la réponse change le
  résultat ; sinon, choisir et dire pourquoi.
- Toute modification d'un skill ou d'un agent qui peut changer le coût se
  mesure avec `tests/cost.py` (avant, après).

## 4. Agents

- Les agents orchestrent et valident ; la logique métier vit dans les
  skills. Avant de créer un skill ou un agent, réutiliser ou étendre un
  existant (`CATALOG.md`).
- Outils au strict nécessaire, aucun accès web **(vérifiée)**. Les commandes
  shell autorisées sont listées dans le champ `commands` de l'agent source.
- Pas de modèle imposé : le harnais choisit. Chaque agent classe ses actions
  en niveaux `simple`, `moyen`, `complexe` avec une grille, et adapte son
  effort ; pas de sous-agent exécutant dédié.
- Import et export dans des agents séparés : `document-extractor` importe,
  `document-publisher` exporte **(vérifiée)**.

## 5. Local et sûr

- Tout rendu et toute conversion se font en local. Aucun contenu n'est envoyé
  à un service en ligne (SaaS, API de rendu) ; seuls des outils ou
  bibliothèques peuvent être téléchargés.
- Rendus de navigateur avec Playwright, jamais Puppeteer **(vérifiée)**, et
  pas de serveur MCP Playwright.
- Un agent ne publie rien en ligne : il produit des fichiers.

## 6. Scripts

- Python 3.10+, lancé par `uv run` (ou `python`), sous Windows, macOS et
  Linux : `pathlib`, `encoding="utf-8"` partout, pas de commande shell propre
  à un système.
- En-tête [PEP 723](https://peps.python.org/pep-0723/) (`# /// script`) avec
  `requires-python` et les dépendances **(vérifiée)**. Bibliothèque standard
  de préférence.
- Un outil externe manquant est signalé avec la commande pour l'installer ;
  le skill `check-prerequisites` en tient la liste.

## 7. Noms et livrables

- Noms simples et parlants, en minuscules avec tirets (`doc-to-markdown`,
  `schema-designer`) **(vérifiée)**. Textes destinés à l'utilisateur en
  français.
- Schémas pour Confluence : le `.drawio` (macro draw.io) et le
  `.drawio.png`. La charte graphique commune est `shared/references/style.md`.
- Un skill repris d'un tiers cite sa source et respecte sa licence ; le
  dépôt est sous licence MIT.

## 8. Avant de livrer un skill ou un agent

1. Contrat écrit ou mis à jour, puis `uv run scripts/build.py`.
2. Au moins un cas dans `tests/cases.json` (dont un cas d'entrée invalide
   pour un script qui lit une description), fixtures dans `tests/fixtures/`.
3. `uv run tests/run.py` sans échec, `regles` et `contrats` compris.
4. Pour un agent, un cas dans `tests/agent-cases.json` ; mesure du coût avec
   `tests/cost.py` si le comportement change.
5. README à jour (tableaux des skills et des agents).
