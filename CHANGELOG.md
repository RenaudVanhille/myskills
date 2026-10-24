# Journal des versions

## Non publié

### Chiffrage

- Skill `solution-estimate` (niveau complexe) : `estimate_build.py` chiffre
  l'option retenue d'`architecture-options` à partir d'une description
  courte (taux par profil, lots par composant estimés en jours ou à trois
  points, pilotage, provision, lignes d'infrastructure avec leur base de
  prix, run, budget). Il calcule la charge espérée et la fourchette P10-P90,
  l'infrastructure, le run, le fonctionnement mensuel et le coût total sur
  l'horizon, signale les exigences qu'aucun lot ne porte, les composants
  sans chiffrage, les lots trop incertains et les dépassements de budget,
  écrit `chiffrage.md` et `chiffrage.csv` et relit le CSV. Aucun tarif
  consulté en ligne.
- Hébergeurs alternatifs et souverains : catalogue
  `solution-estimate/references/providers.json` (AWS, Azure, Google Cloud,
  OVHcloud, Cloud Temple, Outscale, S3NS, Bleu, NumSpot, Scaleway, interne ;
  juridiction, qualifications SecNumCloud et HDS, qualifications en cours),
  complété par un catalogue du projet. `hosting` exige des qualifications :
  chaque ligne cloud ou service hors qualification est signalée, coût par
  hébergeur dans le chiffrage.
- Agent `solution-estimator` (niveau complexe) : découpe, estime et pose
  les hypothèses, fait calculer le script, note les hypothèses au journal
  d'un workflow ; `architecture-options` lui passe la main une fois la
  décision prise.

## 0.4.0 (2026-10-24)

Revue de cohérence des skills et des agents : dépendances déclarées,
skills découpés par responsabilité, workflows décrits en un seul endroit et
modèle choisi par niveau de travail.

### Contrôle

- Champ `requires` des contrats : un skill n'appelle un autre skill que par
  `skill_paths.py` et le déclare ; `regles` refuse tout chemin caché vers un
  autre skill et tout appel non déclaré, `contrats` vérifie les cibles.
  Rubrique « Dépend de » dans les SKILL.md et `CATALOG.md`.
- `input.same_as` : le schéma d'entrée des descriptions cloud n'existe plus
  qu'une fois, repris par `build.py` dans les skills qui le lisent.
- `architecture-options` : le catalogue des exigences est toujours validé ;
  sans `requirements-catalog`, un avertissement le dit (plus de saut
  silencieux).
- `diagram-brief` : `brief.py` valide la décision courte (public,
  destination, type, message, éléments) et applique la grille ; la décision
  complète (format, skill, vue cloud, livraison, raison) peut passer à un
  autre agent. La grille est dans `references/grille.md`.
- Workflows : la définition JSON est la seule source des étapes (consignes,
  `ask`, `memory`, `level` par étape) ; `architecture-workflow` devient un
  moteur générique (132 lignes au lieu de 186).

### Niveaux et modèles

- `level` (simple, moyen, complexe) obligatoire dans chaque contrat de
  skill et d'agent, et dans chaque étape des workflows livrés.
- `shared/models.json` : modèle par niveau et par outil (Claude Code :
  `haiku`, `sonnet`, `opus` ; ailleurs le modèle de la session). `build.py`
  en tire le `model` des agents générés et leur consigne sur les niveaux
  (marqueur `{{niveaux}}`).
- Les listes d'agents des schémas de messages sont régénérées par
  `build.py` : un nouvel agent n'a aucun schéma à modifier.

### Nouveaux skills et agent

- `well-architected-review` (`wa_check.py`) et `threat-model`
  (`stride.py`), sortis de `cloud-architecture`, qui garde le dessin.
- `architecture-deck` (`deck_build.py`), sorti de `architecture-options`.
- `agent-handoff` (`check_message.py`) : validation des messages de passage
  et des rapports finaux, notés au journal d'un workflow ; remplace
  `journal.py handoff|report`.
- `urbanization-map` : `pos_impact.py` situe des options dans le POS
  (repris de `architecture-options`, qui l'appelle) ; inventaire lu aussi
  depuis une note Markdown.
- Agent `architecture-reviewer` (niveau complexe) : modèle de menaces et
  revue Well-Architected, appelé par `schema-designer` et par l'étape
  `menaces` du workflow `cloud-existant`.

### Mémoire et mutualisation

- `vault_sync.py` suit le champ `memory` de la définition : une note par
  étape soumise, schémas PNG et Markdown intégrés, schéma de chaque option
  dans sa note ; le vault du workflow `cloud-existant` est complet.
- `shared/scripts/drawio_xml.py` : structure du fichier, pages, formes,
  flèches, mesure du texte et écriture communes à `drawio_build.py`,
  `cloud_build.py` et `pos_build.py` (fichiers produits identiques).
- Tests : cas `brief`, `pos-impact`, `passage-agents`,
  `vault-cloud-existant` ; cas d'agents C4, Mermaid, cloud, Word et
  `architecture-reviewer`.

### Migration

- `journal.py handoff|report` : utiliser
  `check_message.py handoff|report` du skill `agent-handoff`.
- `cloud-architecture/scripts/wa_check.py` et `stride.py` :
  `well-architected-review/scripts/wa_check.py` et
  `threat-model/scripts/stride.py`, mêmes options.
- `architecture-options/scripts/deck_build.py` :
  `architecture-deck/scripts/deck_build.py`.
- Installer les skills requis à côté (tous le sont avec le plugin).

## 0.3.0 (2026-10-24)

### Nouveautés

- `cloud-architecture` : `wa_check.py` contrôle la description d'une
  architecture contre l'AWS Well-Architected Framework, l'Azure
  Well-Architected Framework et le Google Cloud Well-Architected Framework
  (fiabilité, sécurité, excellence opérationnelle, performances, coûts,
  durabilité) et contre les conventions de schéma des fournisseurs
  (imbrication région, VPC/VNet, zone, sous-réseau ; icônes officielles).
  20 règles, constats avec pilier, gravité, correction et référence du
  cadre, rapport JSON et `<sujet>.wa.md`. Clé `accept` de la description
  pour accepter un écart avec sa raison ; `--fail-on` pour la porte de
  revue ; `--scope piliers` dès la définition de l'architecture (options
  cloud de `architecture-options`), `--scope conventions` au dessin.
- Workflow `architecture` : l'étape `architectures` contrôle chaque option
  cloud contre les piliers Well-Architected ; l'étape `schemas` contrôle les
  conventions du schéma de l'option retenue.
- Workflow `cloud-existant` : l'étape `menaces` livre aussi la revue
  Well-Architected ; `schema-designer` la lance pour un schéma cloud.
- Message d'erreur des descriptions JSON : forme attendue d'une clé libre
  (`accept`) au lieu d'une liste vide.
- `architecture-options` : position de chaque option dans le POS du SI
  (`pos`, `placement`) : noms vérifiés dans le POS, impacts (créations,
  évolutions, remplacements, redondances, flux entre zones), critère
  « urbanisation », section dans `options.md` et l'ADR, POS cible par option
  (`schemas/pos-option-<id>.json` pour `pos_build.py`).
- POS d'entrée lu aussi depuis une note Markdown (tableau zone, quartier,
  ilot, application, statut) et depuis le vault du workflow
  (`"pos": "vault:<chemin>"`), quand il a été versé à l'étude.
- `architecture-workflow` : demande le POS du SI avec le vault, construit
  le POS cible de chaque option à l'étape `schemas` ; note d'option du vault
  avec sa position.
- `architecture-options` : revue Well-Architected des piliers dès la
  définition des options (`wa_check.py`) : constats par pilier dans
  `options.md`, détail dans `schemas/option-<id>.wa.md`, constats de
  l'option retenue dans l'ADR ; écart accepté avec sa raison
  (`wa_accept`), gravité haute non traitée signalée ; `count` des
  composants et `protocol` des flux ; type cloud inconnu refusé dès cette
  étape. `architecture-workflow` y répond avant la revue.
- `options_build.py` : rapport conforme au contrat aussi après une erreur
  de référence (`trace` à null).
- Export PowerPoint par le skill externe `markdown-to-pptx` (md2pptx, de
  Reno), installé à part : myskills n'en copie pas le code et ne connaît que
  son contrat d'interface, `shared/external/markdown-to-pptx.contract.json`
  (dossiers d'installation, commande, conventions du Markdown, schéma du
  plan rendu). Nouveau type de passage de main `externe`, vérifié par le cas
  `contrats`.
- `markdown-publish` : `pptx_publish.py` trouve le skill installé, vérifie
  le Markdown, le lance, valide le plan rendu contre le contrat et relit le
  `.pptx` ; skill absent : consigne d'installation dans le rapport.
- `architecture-options` : `deck_build.py` assemble `presentation.md` depuis
  les étapes validées du workflow (exigences et glossaire, notes par
  critère, scores, écarts, comparaison, schémas PNG, décision, couverture,
  questions ouvertes), chaque donnée une seule fois ; `options_build.py`
  partage ses contrôles et scores (`analyse`).
- Workflow `architecture` : présentation facultative à l'étape `schemas` ;
  `document-publisher` livre le PowerPoint ; `check-prerequisites` cherche le
  skill externe.

## 0.2.0 (2026-10-23)

Revue complète après la 0.1 : fiabilité, contrôle des workflows multi-agents,
tests sur trois systèmes et nouvelles fonctionnalités.

### Corrections

- `convert.py` : deux documents de même nom (`rapport.pdf`, `rapport.png`)
  ne s'écrasent plus ; un dossier passé en entrée est parcouru.
- Rapports JSON de forme unique (`results`, `errors`, `warnings`) pour les
  scripts qui traitent plusieurs fichiers ; `errors` et `warnings` toujours
  présents.
- `check_drawio.py` lit la charte depuis `shared/references/style.md`.
- Kiro : chemin des skills correct pour une installation globale.
- `export.py` signale une image vide ou presque blanche.

### Contrôle multi-agents

- `journal.py handoff|report` valide les messages de passage et les
  rapports finals des agents (schéma, fichiers cités) et les trace.
- Revue différentielle : à une nouvelle soumission, `changes` liste les
  exigences, options et fichiers changés.
- Revue dans Obsidian : note de revue par étape, `review --from-vault`.
- `vault_sync.py` valide chaque fichier lu contre le schéma du skill qui
  l'écrit et n'écrit que les notes changées.

### Nouveautés

- Matrice de traçabilité exigences → composants (`tracabilite.md`, `.csv`)
  et description cloud des options qui ont un fournisseur.
- `iac_import.py` : description de schéma cloud depuis Terraform (AWS,
  Azure, Google), docker-compose et Kubernetes.
- Workflows décrits en JSON (`journal.py init --definition`) : `architecture`
  et `cloud-existant` livrés.
- Glossaire du projet relié aux exigences, une note Obsidian par terme.
- Mode hors ligne : `doctor.py --prefetch`, Mermaid et Excalidraw à version
  fixée et empreinte SHA-512 vérifiée, `MYSKILLS_OFFLINE=1`.

### Tests

- CI GitHub Actions sous Ubuntu, macOS et Windows.
- `tests/cost.py --max-increase` signale une hausse de coût ; nouveaux cas
  d'agent (retour, reprise, cloud-existant).

## 0.1.0 (2026-10-22)

Première version.
