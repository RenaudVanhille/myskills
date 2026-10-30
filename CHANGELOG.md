# Journal des versions

## [0.10.0](https://github.com/RenaudVanhille/myskills/compare/v0.9.0...v0.10.0) (2026-10-30)


### Ajouts

* **doc-to-markdown:** vidéo en local, modèles et flux réseau limités aux sources identifiées ([#44](https://github.com/RenaudVanhille/myskills/issues/44)) ([b8647e1](https://github.com/RenaudVanhille/myskills/commit/b8647e1d16ffade21b9b6f8024faaba88f7dc0e8))
* maquettes vers HTML/CSS, Bootstrap, React, Vue ou Angular, design system et chiffrage frontend ([#47](https://github.com/RenaudVanhille/myskills/issues/47)) ([0a045b8](https://github.com/RenaudVanhille/myskills/commit/0a045b8395b3956b09b8a97e4a55b320b773ac08))
* modèles Docling et Laya préparés avant le run, prérequis et architecture dans le README ([#46](https://github.com/RenaudVanhille/myskills/issues/46)) ([ab8f10f](https://github.com/RenaudVanhille/myskills/commit/ab8f10fc95320aa40b58e56f2e4ff7fc11909542))

## [0.9.0](https://github.com/RenaudVanhille/myskills/compare/v0.8.0...v0.9.0) (2026-10-28)


### Ajouts

* brouillons d'exigences et de scénarios, lisibilité des schémas, CloudFormation et Bicep ([#41](https://github.com/RenaudVanhille/myskills/issues/41)) ([0bdeb95](https://github.com/RenaudVanhille/myskills/commit/0bdeb9594470b12832ad62f07fc4d09475c443b0))
* **mission-workspace:** un répertoire par mission, vault unique et revue multi-dépôts ([#38](https://github.com/RenaudVanhille/myskills/issues/38)) ([c0aa232](https://github.com/RenaudVanhille/myskills/commit/c0aa2323004bc6b9a0e157cee6b47435a7389f96))
* règles de complétude, leçons des revues et missions de référence notées ([#40](https://github.com/RenaudVanhille/myskills/issues/40)) ([63871a8](https://github.com/RenaudVanhille/myskills/commit/63871a8a454c88a0309492801c7de7e93ca10e56))
* **tender-response:** appel d'offres, matrice de conformité, hypothèses et mémoire technique ([#42](https://github.com/RenaudVanhille/myskills/issues/42)) ([1db20e4](https://github.com/RenaudVanhille/myskills/commit/1db20e49b1f60d315d2c36cbd76412968a20c4c6))
* **tender-response:** qualification go / no-go, principes du client et calibration par analogie ([#43](https://github.com/RenaudVanhille/myskills/issues/43)) ([f4ae9d9](https://github.com/RenaudVanhille/myskills/commit/f4ae9d98b01c61c0a7c1e9ff4ba8cb15a6b2d77b))

## [0.8.0](https://github.com/RenaudVanhille/myskills/compare/v0.7.0...v0.8.0) (2026-10-27)


### Ajouts

* **requirements-catalog:** tri des phrases non reprises par un modèle léger, Laya recadré ([#37](https://github.com/RenaudVanhille/myskills/issues/37)) ([88aa9ef](https://github.com/RenaudVanhille/myskills/commit/88aa9efa451b47e5a914f128618e1a51cc7f92f3))


### Corrections

* **architecture-review:** risques et scénarios non satisfaits comptés dans la synthèse et l'avis ([#36](https://github.com/RenaudVanhille/myskills/issues/36)) ([094af70](https://github.com/RenaudVanhille/myskills/commit/094af70b8fb900cdca79cb0071a1ecb059e977cb))


### Coût et performances

* brouillons et règles pour les menaces, l'AIPD et le chiffrage ([#34](https://github.com/RenaudVanhille/myskills/issues/34)) ([e343575](https://github.com/RenaudVanhille/myskills/commit/e343575902a4de9d3e3f7603a4f05d492c9bef59))

## 0.7.0 (2026-10-26)

### Fiabilité

- CI : job `rendus` (Linux) qui installe draw.io Desktop et Playwright et
  joue les cas lents (`run.py --slow`), dont l'export draw.io et les cas
  Laya ; la matrice Linux, macOS, Windows reste.
- `tests/laya_eval.py` et `fixtures/laya/phrases.json` (112 phrases
  étiquetées, pièges compris) : précision, rappel et F1 de Laya face à la
  regex, meilleur seuil, justesse sur la nature et la catégorie ; résultat
  dans le résumé du job `rendus`. Première mesure : F1 0,505 pour Laya
  contre 0,496 pour la regex, rappel plus bas (0,38 contre 0,42), nature
  juste à 59 %, catégorie à 45 %.
- `req_build.py --laya` : Laya ne fait plus qu'ajouter des phrases à celles
  de la regex ; une phrase normative qu'il écarte reste signalée
  (`dismissed` la compte). Consignes de `req_laya.py` réécrites sur le
  modèle des exemples de Laya, versionnées dans la clé du cache
  (`LAYA_PROMPT`) : un ancien cache ne sert plus. Après coup : F1 de la
  règle « regex ou Laya » 0,555 contre 0,496 pour la regex seule (rappel
  0,50 contre 0,42), catégorie juste à 57 % ; la nature (56 %) reste peu
  fiable, ses désaccords ne sont qu'à vérifier.
- Mesure du coût (`cost.py --repeat 3`, modèle de chaque agent) : étape
  schémas du workflow `architecture` 0,61 $ et 69 tours avant, 0,15 $ et
  13 tours après (`journal.py check`) ; chiffrage 0,61 $ avant, 0,73 $
  après, l'agent décrivant désormais les consommations cloud avec
  `cloud-cost` ; `workflow-cloud-existant` 0,21 $ avant, 0,24 $ après ;
  `revue-menaces` stable (0,69 $ puis 0,71 $). draw.io simulé pour ces
  mesures dans le conteneur (export de PNG fixe).

### Coût

- `journal.py check DOSSIER ETAPE` : lance en un appel tous les contrôles
  d'une étape (champ `run` des étapes : script, arguments, `foreach`, `if`,
  `vault`), rapport `checks` par commande ; les cinq workflows le
  déclarent, `architecture-workflow` l'appelle avant `submit`. Le cas
  `regles` vérifie chaque entrée `run`.
- `stride.py` écrit aussi `<sujet>.threats.json` ; `threat_review.py`
  (threat-model) lit un court fichier de décisions par menace (traitée,
  acceptée, écartée, avec mesure ou raison), le vérifie et réécrit le
  modèle : le modèle ne réécrit plus le Markdown des menaces.
- `estimate_build.py` signale les postes souvent oubliés (tests de
  sécurité, environnements hors production, réseau, recette, mise en
  production, formation). Le chiffrage reste au niveau complexe : Sonnet
  oubliait ces postes, que le script rattrape désormais sans changer de
  modèle.
- Budget de taille : `SKILL.md` et agent source sous 16 000 caractères
  (cas `regles`).

### Ajouts

- `drawio_read.py` (drawio-diagram) : tire d'un `.drawio` existant (clair
  ou compressé) la description courte de `drawio_build.py`, rôles déduits
  du style, positions ou grille (`--grid`) ; plus de XML édité à la main.
- Skill `cloud-cost` : coût de fonctionnement cloud des options
  (`cost_build.py couts.json`), grille de prix indicative locale (AWS,
  Azure, Google Cloud, OVHcloud, Scaleway), plages horaires, remises,
  postes oubliés, budget ; `--infra OPTION` donne les lignes
  d'infrastructure du chiffrage. Étape chiffrage des workflows
  `architecture` et `migration-cloud`.
- `route.py --laya` (agent-handoff) : Laya choisit parmi les six premiers
  candidats ; son choix passe en tête à partir de 0,6 de confiance.
- `install.py sync` : installe et met à jour skills et agents pour Claude
  Code, Copilot, OpenCode, Kiro et Hermes, en global (défaut) ou par projet,
  depuis l'archive GitHub (jeton `gh auth token`, `GH_TOKEN`...), sans clone
  ni identifiants git, ou depuis une copie locale (`--source` : dossier,
  clone, ZIP téléchargé depuis GitHub) ; sans gh ni variable, le jeton est
  demandé dans le terminal ; ne réécrit rien si la version n'a pas changé, retire
  ce qui n'existe plus, garde l'état (`~/.myskills/state.json`,
  `.myskills.json`) et une copie du script dans `~/.myskills/`.
  `install.py status` : ce qui est installé, fichiers manquants, version
  disponible. Rapport JSON (`shared/schemas/install-report.schema.json`),
  `--models` validé contre `install-models.schema.json` (`--schema`). Cas
  `synchro`, `synchro-globale`, `synchro-erreurs`.
- `req_build.py --laya` (requirements-catalog) : le modèle local Laya
  (`req_laya.py`, dans son propre environnement) dit si chaque phrase non
  reprise des sources est une exigence, même sans verbe normatif, et
  contrôle la nature et la catégorie des exigences retenues
  (avertissements au-dessus de 0,7 de confiance). Réponses en cache
  (`--laya-cache`), repli sur la regex sans Laya. Rapport : `method`,
  `dismissed`, `disagreements`. Facultatif : sans `--laya`, rien ne change.

## 0.6.0 (2026-10-25)

### Parallélisation

- Workflows en graphe : champ `after` des étapes (défaut : l'étape
  précédente) ; `journal.py` donne les étapes prêtes (`ready`), refuse une
  étape dont une dépendance n'est pas franchie, et un retour ne remet à
  reprendre que les étapes qui en dépendent. Verrou `workflow.lock` : des
  sous-agents peuvent appeler `journal.py` en même temps. `architecture` :
  revue et chiffrage en parallèle après les schémas ; `cloud-existant` :
  schémas et menaces ; `conformite` : exigences et description ;
  `migration-cloud` : cible (puis chiffrage) et feuille de route. Le cas
  `regles` vérifie `after`.
- `architecture-workflow` lance les étapes prêtes chacune dans un
  sous-agent du niveau de l'étape ; `architecture-reviewer` fait de même
  pour menaces, Well-Architected, ATAM et AIPD demandés ensemble ;
  `document-extractor` pour plusieurs documents à transcrire.
- `convert.py --jobs` (jusqu'à 4 documents en même temps, Docling un à la
  fois) ; `run.py --jobs` (par défaut le nombre de cœurs : 69 s à 34 s sur
  4 cœurs).

### Coût

- `cost.py` : `--repeat N` (médiane), `--jobs N`, `max_cost_usd` par cas,
  `--summary` (dernières médianes et écart, sans rien lancer), cas de
  workflow de bout en bout (`rounds`, `--workflow`) avec une ligne par
  étape.
- Cas d'agents du lot D : `migration-evaluation`,
  `migration-feuille-de-route`, `dossier-architecture`,
  `bout-en-bout-cloud-existant`, `bout-en-bout-architecture`.
- `--export png|svg` sur `drawio_build.py`, `cloud_build.py`,
  `excalidraw_build.py` et `c4_build.py` : construire, vérifier et exporter
  en un appel (`skill_paths.run_script` et `export_image`) ; les workflows
  s'en servent.

### Ajouts

- `architecture-dossier` : `actions.py`, plan d'actions unique tiré des
  revues (constats Well-Architected et de revue, risques, menaces à mesure
  retenue, risques de l'AIPD), une action par règle ou mesure, priorités
  P1 à P3, affectation `--assign`, CSV pour Jira ou Azure DevOps ; repris
  par les gabarits et l'étape `plan` de `conformite`.
- Skill `api-contract` (niveau moyen) : `api_build.py` écrit OpenAPI 3.1 et
  AsyncAPI 3.0 depuis une description courte, contrôle doublons, types,
  exigences et composants de l'option, signale les exigences sans
  interface et relit chaque YAML ; étape `schemas` du workflow
  `architecture`, sur demande.

### Corrections

- `diagram-export` : un `.drawio` de plusieurs pages exportait deux fois la
  dernière page (`--page-index` de draw.io compte à partir de 0).
- `decision-log` : une étape en revue dont un livrable change se soumet à
  nouveau, au lieu d'être bloquée jusqu'à un retour.

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

### Conformité

- Skill `data-protection` (niveau complexe) : `dpia_build.py` écrit le
  registre des traitements et l'AIPD depuis une description courte ;
  AIPD requise à partir de deux critères du CEPD, base légale et exception
  de l'article 9 contrôlées, transfert hors EEE sans garantie refusé,
  hébergeur soumis à des lois extraterritoriales signalé, mesures reliées
  aux exigences et aux menaces STRIDE, risque résiduel élevé signalé
  (consultation de la CNIL) ; notes `traitement` (nouveau type de
  l'ontologie) et `risque` dans le vault.
- Workflow `conformite` : exigences, description cloud, menaces et
  qualification de l'hébergeur, registre et AIPD, plan d'actions et
  dossier de conformité (`dossier_build.py --template conformite`).
- Agent `architecture-reviewer` : AIPD avec `data-protection`.

### Migration

- Skill `migration-assessment` (niveau complexe) : `assess_build.py`
  contrôle l'évaluation 6R d'un portefeuille (dépendances inconnues ou en
  cycle, application retirée encore utilisée, socle hors support
  réhébergé, données sensibles chez un hébergeur extraterritorial) et
  calcule les vagues de migration selon les dépendances.
- Skill `transition-roadmap` (niveau moyen) : `roadmap_build.py` reprend
  les vagues, calcule dates, marges et chemin critique, contrôle
  l'échéance et écrit un diagramme de Gantt Mermaid.
- Workflow `migration-cloud` : exigences, évaluation 6R, architecture
  cible, chiffrage (facultatif), feuille de route, dossier de migration
  (facultatif, `dossier_build.py --template migration`).

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
