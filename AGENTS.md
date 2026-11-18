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
  `SKILL.md` reste sous 500 lignes et 16 000 caractères, un agent source
  sous 16 000 caractères **(vérifiée)** ; le détail va dans
  `references/`, chargé à la demande.
- Il fonctionne dans GitHub Copilot, Claude Code, OpenCode, Kiro et Hermes,
  installé comme plugin (voir le README). Rien de propre à un seul outil dans
  un `SKILL.md`.
- Un skill tiers installé à part ne se copie pas : il s'appelle par son seul
  contrat d'interface, `shared/external/<nom>.contract.json`
  (`shared/schemas/external-skill.schema.json`), et un passage de main de
  type `externe` le cite **(vérifiée)**. Le script appelant le trouve, valide
  sa sortie contre le contrat et donne la consigne d'installation s'il
  manque.
- Un skill n'appelle un script d'un autre skill de myskills que par
  `scripts/lib/skill_paths.py` (`find_script`, `load_module`, `schema_of`),
  et le déclare dans le champ `requires` de son contrat (skill, script,
  raison, facultatif ou non) **(vérifiée : pas de chemin vers un autre
  skill, chaque appel déclaré, cible existante)**. Sans le skill requis, le
  script le signale dans son rapport. Un schéma d'entrée partagé ne se
  recopie pas : `input.same_as` le reprend du script source.
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
  par `build.py`) **(vérifiée : `input` et `--schema` déclarés)**. Toutes les
  erreurs d'un coup, chacune précise et actionnable : le chemin
  (`items/2/type`), la valeur reçue et les valeurs possibles ou proches («
  lamda » : lambda ?). `--schema` affiche le schéma sur une ligne, pour que le
  modèle l'obtienne sans lire le contrat. Une entrée CSV est contrôlée de la
  même façon (colonnes, ligne fautive). Une entrée invalide donne le code 1 et
  un rapport avec `errors`, sans fichier produit à moitié.
- **Sortie** : le livrable est vérifié par un script avant d'être rendu
  (`check_drawio.py`, `validate.py`, export et relecture de l'image...).
  Un livrable non vérifié est signalé comme tel dans le rapport final.
- **Rapport** : un script écrit un rapport JSON court sur la sortie standard,
  dont le JSON Schema est dans le contrat **(vérifiée : schéma présent et
  valide)** ; `tests/run.py` valide chaque rapport contre ce schéma. Le
  rapport est un objet avec `errors` et `warnings` toujours présents
  **(vérifiée)** ; un script qui traite plusieurs fichiers
  met un objet par fichier dans `results` (`shared/scripts/script_report.py`).
- **Entre agents** : une demande suit `shared/schemas/handoff.schema.json`,
  un agent termine par le rapport final de
  `shared/schemas/agent-report.schema.json`, en JSON sur une ligne, validés
  par `check_message.py` (skill `agent-handoff`) avant l'envoi. Un passage
  de main vise un skill ou un agent qui existe **(vérifiée)**. La liste des
  agents de ces schémas est tenue par `build.py` : un nouvel agent n'y
  touche pas.
- **Vault Obsidian** : toute note écrite dans le vault suit l'ontologie
  `vault-ontology.json` (types, propriétés, relations typées en wikilinks,
  tags normalisés `type/<type>` et facettes). Elle et son module
  `vault_ontology.py` n'existent qu'une fois, dans
  `skills/markdown-to-obsidian/scripts/lib/` : un autre skill les charge par
  `require_module("markdown-to-obsidian", "lib/vault_ontology.py")` déclaré
  dans `requires`, jamais par une copie **(vérifiée)**. De même pour les
  autres sources uniques de `SINGLE_SOURCES` (`scripts/contracts_lib.py`) :
  `workspace.py` et ses schémas (`mission-workspace`), `model_store.py` et
  `model-sources.json` (`check-prerequisites`), `providers.json`
  (`cloud-architecture`, par `require_file`). Le skill déclare
  `vault` dans son contrat (`writes` : types écrits, `reads`) ; les types
  existent et le script vérifie ses notes avec `vault_ontology` avant
  d'écrire **(vérifiée)**. Dans une mission (un répertoire,
  `mission.json`, skill `mission-workspace`), un script qui écrit dans le
  vault prend celui de la mission par défaut et refuse tout autre, par
  `scripts/lib/workspace.py` (`vault_target`) **(vérifiée)**. Un nouveau
  type ou une nouvelle relation s'ajoute dans l'ontologie, sans code. Toute écriture
  dans le vault passe par `Notes.write` (ou `vault_sync`), sous le verrou du
  vault (`vault_lock`) et en écriture atomique (`save`) : des skills lancés en
  parallèle n'y perdent rien. `vault_check.py`
  (`markdown-to-obsidian`) vérifie un vault et exporte son graphe typé.
- **Lisibilité dans Obsidian** : une note générée se lit sans ouvrir ses
  liens. Titre `#` parlant (repris en alias par `vault_ontology`), liens
  libellés par le titre de la note visée et non par un identifiant, callout
  pour ce qui demande une action ou une attention (`callout`), nombres et
  accords en français (`number`, `count`, `label` et les libellés de
  l'ontologie), livrable complet copié dans le vault et lié (`Notes.attach`),
  pas cité en code. La section « Revues et analyses » des notes visées par
  une relation `hub` est tenue par `vault_ontology`, comme les tableaux
  `Tableaux.base` tirés des `views` de l'ontologie et la carte
  `Carte.canvas` tirée de son champ `canvas`. La section « Mes notes » d'une
  note générée appartient à l'utilisateur : gardée à chaque réécriture
  (`Notes`), ses callouts `[!question]` et `[!retour]` relus par
  `vault_annotations`. `vault_check.py`
  signale les écarts (`lisibilité :`).
- **Workflows** : un workflow est une définition JSON
  (`skills/decision-log/workflows/`), seule source des étapes, des skills,
  des livrables, des contrôles, des consignes et de la mémoire du vault.
  L'agent `architecture-workflow` est un moteur générique qui la suit : un
  nouveau workflow ne demande qu'une définition. Chaque étape livrée a un
  `level`, et ses skills figurent dans ceux de l'agent **(vérifiée)**. Une
  étape qui ne dépend pas de la précédente le dit dans `after`, qui ne cite
  que des étapes placées avant elle **(vérifiée)** : les étapes prêtes en
  même temps se mènent en parallèle. Chaque workflow a au moins un cas
  d'agent dans `tests/agent-cases.json` **(vérifiée)** ; les mots d'une
  demande qui le désignent sans figurer dans ses libellés (legacy,
  comité...) vont dans `keywords`, et toute demande mal routée s'ajoute au
  cas `routage-reference`.

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
  mesure avec `tests/cost.py` (avant, après), en médiane de plusieurs
  exécutions (`--repeat 3`) : une seule exécution varie trop pour conclure.
- Le coût suit surtout le nombre de tours : un script qui enchaîne
  construction, contrôle et export (`--export`) vaut mieux qu'une consigne
  plus courte. Un travail indépendant d'un autre (étapes, analyses,
  documents) va à un sous-agent lancé en parallèle, avec un contexte court.

## 4. Agents

- Les agents orchestrent et valident ; la logique métier vit dans les
  skills. Avant de créer un skill ou un agent, réutiliser ou étendre un
  existant (`CATALOG.md`).
- Outils au strict nécessaire, aucun accès web **(vérifiée)**. Les commandes
  shell autorisées sont listées dans le champ `commands` de l'agent source.
- **Niveaux et modèles** : chaque skill, agent et étape de workflow déclare
  son niveau (`level` : `simple`, `moyen`, `complexe`) **(vérifiée)**.
  `shared/models.json` fait correspondre un modèle à chaque niveau, par
  outil (léger, standard, puissant ; `null` : modèle de la session) ;
  `build.py` en tire le `model` des agents générés et leur section sur les
  niveaux (marqueur `{{niveaux}}` dans chaque agent source, **vérifiée**).
  Le travail mécanique va au niveau simple, le jugement au niveau complexe.
  Chaque agent classe aussi ses actions avec une grille et adapte son
  effort ; un sous-agent seulement pour un lot ou une étape d'un autre
  niveau, avec le modèle de ce niveau.
- Fichiers de travail (descriptions provisoires, rendus et sorties de
  vérification) dans `.myskills-tmp/` du dossier de travail, jamais dans le
  dossier temporaire du système : hors du dossier, chaque écriture demande
  une approbation. `journal.py submit` le vide ; un script garde `tempfile`
  pour ce qu'il crée et supprime lui-même. La consigne des agents et des
  `SKILL.md` est générée par `build.py`.
- Import et export dans des agents séparés : `document-extractor` importe,
  `document-publisher` exporte **(vérifiée)**. Un moteur de workflow peut
  lancer une conversion mécanique (script) ; tout travail de vision ou de
  relecture d'un import passe à `document-extractor`.

## 5. Local et sûr

- Tout rendu et toute conversion se font en local. Aucun contenu n'est envoyé
  à un service tiers non maîtrisé (SaaS, API de rendu ou de conversion) ;
  seuls des outils ou bibliothèques peuvent être téléchargés.
- Les modèles du harness (Claude, Copilot, Kiro... sous offre entreprise,
  avec sa politique de sécurité et de non-rétention) ne sont pas concernés :
  un script peut leur confier un travail de modèle, de préférence au niveau
  simple. Un modèle local (Ollama) reste possible ; tout autre fournisseur
  de modèle est un service tiers.
- **Non négociable** : aucun document, même en partie (texte, image, son),
  ne part ailleurs que vers les modèles du harness. Un modèle local ne se
  télécharge que depuis une source de `shared/model-sources.json` (hôte
  autorisé, révision épinglée, empreintes SHA-256 vérifiées, entrée ajoutée
  par `scripts/pin_model.py` et relue en PR), par
  `model_store.py` (skill `check-prerequisites`). Un script qui lit un document avec une
  bibliothèque de modèle ou de conversion (faster-whisper, MarkItDown, Docling) appelle d'abord `model_store.guard_network()` : seuls les hôtes
  identifiés (`model-sources.json`, `MYSKILLS_ALLOWED_HOSTS`), le proxy et
  la machine restent joignables, tout autre flux est refusé et signalé dans
  le rapport **(vérifiée)**. Jamais de
  bibliothèque qui tire ses modèles d'ailleurs (ModelScope, RapidOCR,
  EasyOCR...) ni d'extra MarkItDown qui envoie le contenu à un service
  (`all`, `audio-transcription`, `az-doc-intel`) **(vérifiée)**.
- Aucun téléchargement de modèle pendant un run : chaque modèle local
  s'installe avant, une fois, par `doctor.py GROUPE --prefetch` (ou
  `--models-from`, skill `check-prerequisites`). Un script le lit dans le
  cache vérifié (`model_store.require`, Docling en version
  épinglée avec `--artifacts-path`, `HF_HUB_OFFLINE`) ; s'il manque, il
  s'arrête ou se replie en donnant cette commande **(vérifiée)**.
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

1. Contrat écrit ou mis à jour : `level` (le modèle écrit-il ou décide-t-il
   quelque chose ? non : simple ; une description ou une correction :
   moyen ; concevoir, noter, analyser : complexe), `requires` pour chaque
   script d'un autre skill appelé ; pour un agent, le marqueur
   `{{niveaux}}`, pour un workflow, une définition JSON avec un `level` par
   étape. Puis `uv run scripts/build.py`.
2. Au moins un cas dans `tests/cases.json` par script **(vérifiée)** (dont un cas d'entrée invalide
   pour un script qui lit une description), fixtures dans `tests/fixtures/`.
3. `uv run tests/run.py` sans échec, `regles` et `contrats` compris.
4. Pour un agent, un cas dans `tests/agent-cases.json`, avec des contrôles
   sans modèle (`checks`) **(vérifiée)** ; mesure du coût avec
   `tests/cost.py` si le comportement change.
5. README à jour (tableaux des skills et des agents).

## 9. Commits, PR et versions

Les versions et `CHANGELOG.md` sont produits par
[release-please](https://github.com/googleapis/release-please) à partir des
titres des commits de `main` ; personne ne les écrit à la main, ce qui
supprime les conflits sur le journal.

- Titre de PR au format [Conventional Commits](https://www.conventionalcommits.org/fr/) :
  `type(portée): description`, description en français, à l'impératif ou
  nominale, sans point final, 100 caractères au plus. Portée facultative :
  le skill ou l'agent touché (`feat(cloud-cost): grille GCP`). Contrôlé en
  CI par `uv run scripts/check_commit.py "TITRE"` (workflow `titre-pr`) ; à lancer
  avant d'ouvrir ou de renommer une PR.
- Types : `feat` (ajout visible, version mineure), `fix` (correction,
  correctif), `perf` (coût en tokens ou en temps, correctif), `docs`,
  `refactor`, `test`, `ci`, `build`, `chore`, `style` (hors journal, sauf
  `docs` et `refactor`), `revert`. Rupture d'un contrat, d'un schéma ou d'une
  option : `!` après le type ou pied `BREAKING CHANGE: ...` (version
  majeure). Pour forcer une version, pied `Release-As: X.Y.Z` dans le
  message du squash.
- Une PR = un sujet = une ligne du journal : son titre est ce qu'on lira
  dans `CHANGELOG.md`. Le détail (mesures, cas de test) va dans la
  description de la PR, pas dans le journal.
- Fusion en **squash** uniquement : le titre de la PR devient le commit de
  `main` que release-please lit. Les commits de la branche suivent la même
  forme, de préférence.
- Ne jamais modifier à la main `CHANGELOG.md`, la version de `plugin.json`,
  de `.claude-plugin/*.json` ni `.release-please-manifest.json` **(vérifiée :
  versions égales, pas de section « Non publié »)**. release-please tient à
  jour une PR `chore(main): release X.Y.Z` ; la fusionner publie le tag
  `vX.Y.Z` et la release GitHub.
