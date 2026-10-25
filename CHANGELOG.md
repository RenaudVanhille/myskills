# Journal des versions

## À venir

### Par où commencer

- Agent `orientation` (niveau simple) : lit la demande et les noms des
  fichiers fournis, choisit l'agent ou le workflow, écrit `passage.json`
  validé par `check_message.py` ; aucun travail métier, une question au
  plus.
- `agent-handoff` : `route.py` liste les agents et les workflows (et les
  skills sur demande) classés pour une demande, depuis
  `scripts/lib/routes.json`, catalogue réduit généré par `build.py`.

### Dossier d'architecture

- Skill `architecture-dossier` (niveau simple) : `dossier_build.py`
  assemble le DAT d'un dossier de workflow selon un gabarit de sections
  (`dat` par défaut, `avis` pour un dossier reçu, ou celui de
  l'organisation) ; seule la synthèse est écrite par le modèle ; sections
  obligatoires manquantes signalées (`--strict`), liens et images vérifiés.
- Workflow `architecture` : étape facultative `dossier`. Nouveau workflow
  `revue-dossier` : documents, exigences, revue d'architecture, avis.

### Tests

- Mesure de coût des 21 cas d'agent, modèle de chaque niveau contre Sonnet
  (`costs.csv`, libellés `v0.5-agent` et `v0.5-sonnet`).
- Niveau complexe gardé en Opus : sur revue-menaces, chiffrage et
  revue-architecture (`qualite-opus`, `qualite-sonnet`), Sonnet coûte
  2,3 fois moins mais oublie des postes (réseau, test d'intrusion,
  hors production) et juge satisfait un scénario de pic qu'Opus classe à
  risque.
- `importer-obsidian` : le cas fournit un vault (`.obsidian/app.json`) et
  demande la racine du vault ; `publier-pptx` : le prompt dit que la
  doublure de markdown-to-pptx est voulue (l'agent la refusait, à raison,
  devant un comité).

## 0.5.0 (2026-10-25)

Ontologie du vault, revue d'architecture et chiffrage, puis revue v0.4.0 :
hébergeurs souverains communs aux skills cloud, étapes facultatives du
workflow, mémoire partagée complète et diagrammes C4 et Mermaid écrits par
script.

### Hébergeurs souverains

- `shared/providers.json` (déplacé de `solution-estimate`) : catalogue
  commun des hébergeurs (AWS, Azure, Google Cloud, OVHcloud, Cloud Temple,
  Outscale, S3NS, Bleu, NumSpot, Scaleway, sur site), juridiction,
  qualifications (SecNumCloud, HDS) et vocabulaire de schéma ; copié par
  `build.py` dans `cloud-architecture`, `well-architected-review`,
  `architecture-options` et `solution-estimate`.
- `cloud-architecture` : `provider` accepte ces hébergeurs (services
  génériques aux formes de la charte, groupes projet, région, zone, réseau,
  sous-réseau), `qualifications` exigées ; `--types ovh` liste le
  vocabulaire.
- `well-architected-review` : services des hébergeurs lus par leur rôle ;
  règle SEC-08 (hébergeur sans la qualification exigée).
- `architecture-options` : `hosting` (qualifications et exigences qui les
  portent) ; une option chez un hébergeur non qualifié reçoit un écart
  bloquant sur ces exigences ; la description cloud de l'option garde les
  qualifications.

### Workflow et mémoire partagée

- `decision-log` : étape `facultative` d'une définition, sous-commande
  `journal.py skip --text` (statut `sautee`, décision `saut` au journal).
  Le workflow `architecture` gagne les étapes facultatives `revue`
  (architecture-reviewer) et `chiffrage` (solution-estimator).
- `--vault --folder` sur `wa_check.py`, `stride.py` et
  `estimate_build.py` : notes `revue-well-architected`, `modele-menaces`,
  `chiffrage` et `lot` (nouveaux types de l'ontologie), constats reliés à
  l'option et aux exigences. `vault_ontology.Notes` mutualise l'écriture
  (relations vers des notes existantes, notes périmées retirées), reprise
  par `arch_review.py`.

### Diagrammes écrits par script

- `c4-architecture` : `c4_build.py` écrit `model.c4` et `specification.c4`
  depuis une description JSON courte ou une option
  (`--from-options options.json --option A`) et vérifie références,
  imbrication C4 et taille des vues ; `likec4 validate` s'il est installé.
- `mermaid-diagram` : `mermaid_build.py` écrit flowchart et séquence
  (identifiants sûrs, libellés protégés, charte, blocs alt/opt/loop),
  aussi depuis une option.

### Modèles

- `shared/models.json` : modèles Copilot à jour (Claude 5.5, GPT-6 Luna et GPT-6.1 Sol), avec repli (liste) ;
  `install.py --models FICHIER` remplace les modèles par niveau à
  l'installation (OpenCode, Kiro, Hermes, Copilot).

### Tests

- Contrôle des fournisseurs des contrats contre le catalogue commun ; un
  `SKILL.md` ne cite un autre skill par `../` que s'il lui passe la main.
- Cas `cloud-souverain`, `options-souverain`, `workflow-facultative`,
  `vault-revues`, `installation-modeles`, `c4-modele`, `c4-erreurs`,
  `mermaid-script`.

### Ontologie du vault Obsidian

- `shared/vault-ontology.json` (schéma `shared/schemas/vault-ontology.schema.json`) :
  14 types de notes (workflow, etape, revue, exigence, terme,
  option-architecture, decision, adr, document, application,
  revue-architecture, constat, risque, menace), propriétés et valeurs
  permises, relations typées écrites en wikilinks dans le frontmatter
  (`workflow`, `concerne`, `termes`, `ecarts`, `option`, `exigences`,
  `evalue`, `porte-sur`, `issu-de`, `attenue-par`...), tags normalisés
  (`type/<type>` et facettes `<propriété>/<valeur>`). Un type s'ajoute sans
  code.
- `shared/scripts/vault_ontology.py`, copié par `build.py` dans les skills
  dont le contrat déclare `vault` (`writes`, `reads`) : construit, écrit et
  vérifie le frontmatter.
- `decision-log` : `vault_sync.py` écrit des notes typées (relations et
  tags normalisés) et n'écrit rien si une note sort de l'ontologie ; listes
  du frontmatter en blocs, comme Obsidian ; statut de l'ADR `acceptee`.
- `markdown-to-obsidian` : `obsidianize.py` écrit `type: document` ; la
  classification Laya va dans `nature` (au lieu de `type`) et `domaine`.
  Nouveau `vault_check.py` : vérifie un vault ou un dossier contre
  l'ontologie et exporte le graphe typé (node-link NetworkX, lisible par
  graphify ou networkx) ; `--ontology [TYPE]` donne l'ontologie résumée.
- Règles : champ `vault` des contrats, types existants et ontologie
  cohérente (`contrats`), import de `vault_ontology` par tout skill qui
  écrit dans le vault (`regles`).

### Revue d'architecture

- Skill `architecture-review` (`arch_review.py`) : revue d'une architecture
  logicielle ou solution à la manière d'ATAM. Le modèle écrit et évalue les
  scénarios de qualité (arbre d'utilité), les risques, sensibilités,
  compromis et décisions ; le script contrôle la structure (cycles
  synchrones, base partagée, couches, pivot, chaîne synchrone longue,
  dépendance externe synchrone, point unique de défaillance), la
  traçabilité des exigences, les scénarios, décisions et risques, reprend
  une option d'`architecture-options` (`source`) sans recopie, ajoute les
  piliers Well-Architected d'une description cloud et calcule l'avis.
- Code comparé à l'architecture avec graphify, skill externe appelé par son
  contrat (`shared/external/graphify.contract.json`) : `--code-only` par
  défaut (analyse locale) ; `semantic` fait lire aussi les documents par le
  modèle du harness ou par Ollama.
- AGENTS.md, section 5 : la règle vise les services tiers non maîtrisés ;
  les modèles du harness (offre entreprise) ne sont pas concernés. Le contrat des skills
  externes accepte un outil en ligne de commande (`locate.command`) et le
  schéma de sa sortie (`output_schema`).
- `--vault` : la revue, ses constats et ses risques deviennent des notes
  typées du vault (`revue-architecture`, `constat`, `risque` de
  l'ontologie), reliées aux notes d'exigence, d'option et d'ADR.
- Agent `architecture-reviewer` : revue d'architecture en plus des menaces
  et du Well-Architected ; `check-prerequisites` : groupe `revue`.

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
