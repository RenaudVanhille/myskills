# Catalogue des agents et des skills

Fichier généré par `scripts/build.py` : ne pas le modifier à la main. Les
contrats qui font foi sont en JSON : `skills/<nom>/contract.json`,
`src/agents/<nom>.contract.json` et les schémas de `shared/schemas/`. La
version machine de ce catalogue est [`catalog.json`](catalog.json).

## Messages entre agents

- Message de passage : [`shared/schemas/handoff.schema.json`](shared/schemas/handoff.schema.json).
  Champs : `agent` (document-extractor | schema-designer | document-publisher | architecture-workflow | architecture-reviewer | solution-estimator | orientation), `objective` (texte), `files` (liste), `audience` (technique | non technique), `destination` (markdown | obsidian | word | powerpoint | pdf | confluence | sharepoint | xwiki | html), `output` (texte) ; facultatifs : `constraints`.
- Rapport final : [`shared/schemas/agent-report.schema.json`](shared/schemas/agent-report.schema.json).
  Champs : `agent` (document-extractor | schema-designer | document-publisher | architecture-workflow | architecture-reviewer | solution-estimator | orientation), `status` (ok | partiel | echec), `files` (liste), `tools` (texte), `level` (simple | moyen | complexe), `corrections` (liste), `todo` (liste), `next` (objet).

## Agents

### `architecture-reviewer`

Revoit une architecture logicielle ou solution (revue ATAM : scénarios de qualité, risques, compromis, décisions, traçabilité des exigences, code comparé à l'architecture avec graphify en local) et la sécurité et la qualité d'une architecture cloud décrite en JSON : modèle de menaces STRIDE et revue Well-Architected d'AWS, Azure et Google Cloud (piliers et conventions de schéma), et la protection des données d'une solution : registre des traitements et analyse d'impact RGPD (AIPD). Trie les constats, propose les corrections, rend un avis et fait accepter les écarts par l'utilisateur. Adapte l'effort de chaque action pour limiter les coûts.

**Skills** : `check-prerequisites`, `mission-workspace`, `architecture-review`, `threat-model`, `well-architected-review`, `data-protection`, `cloud-architecture`, `diagram-export`, `decision-log`, `agent-handoff`

Généré depuis `src/agents/architecture-reviewer.contract.json`, qui fait foi.

- **Niveau** : complexe (modèle puissant, `shared/models.json`).
- **Reçoit** : Pour une revue d'architecture logicielle ou solution : l'option d'architecture-options (options.json et son id) ou les composants et flux, le catalogue d'exigences, les décisions (ADR) et, s'il existe, le dossier du code ; La description JSON d'une architecture cloud (celle de cloud_build.py) : schéma existant, option d'architecture-options (schemas/option-<id>.cloud.json) ou description tirée du code (iac_import.py) ; Ce que l'utilisateur veut : revue d'architecture, modèle de menaces STRIDE, revue Well-Architected des piliers, conventions du schéma, registre et AIPD RGPD, ou tout ; Pour le RGPD : les traitements (finalités, personnes, données, destinataires, durées) connus ou à déduire des exigences et des flux ; Les contraintes connues (sécurité, conformité, écarts déjà acceptés et leur raison) ; Pour plusieurs dépôts (microservices) : les dépôts de la mission (mission.json, un par service, commit figé) ou code.repos.
- **Produit** : <sujet>.revue.md : revue d'architecture, avis calculé, arbre d'utilité évalué, constats, risques, compromis, décisions, traçabilité et conformité du code ; <sujet>.threats.md : modèle de menaces STRIDE relu, menaces gardées et précisées, mesures et statuts proposés ; <sujet>.wa.md : revue Well-Architected, constats ouverts ou acceptés avec leur raison ; aipd.registre.md et aipd.aipd.md : registre des traitements et analyse d'impact, risques cotés et reliés aux exigences et aux menaces ; Si demandé, le schéma des menaces (cloud_build.py --view threats) et son PNG.
- **Ne fait jamais** : Accepter un écart (accept) sans la raison donnée par l'utilisateur ; Évaluer un scénario de qualité sans dire pourquoi, ou confier les documents à graphify avec un modèle autre que celui du harness ou un modèle local ; Modifier le schéma ou la description d'un autre agent sans le dire ; Coter un risque RGPD ou cocher un critère du CEPD sans le justifier ; Envoyer une description ou un schéma à un service en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | le schéma doit être corrigé ou complété après la revue (composant manquant, flux à chiffrer) | la description JSON corrigée ; les constats qui la justifient ; la destination du schéma |
| `architecture-workflow` | la revue est faite pour une étape de workflow : rendre la main pour la soumission | les fichiers .revue.md, .threats.md et .wa.md ; les constats de gravité haute restants ; le dossier du workflow |
| `document-publisher` | la revue doit être livrée en Word, HTML ou XWiki | les fichiers .revue.md, .threats.md et .wa.md ; l'outil cible |

### `architecture-workflow`

Déroule un workflow prédictible des documents d'un projet jusqu'à l'architecture : conversion des documents, catalogue des exigences fonctionnelles et non fonctionnelles avec sources, 2 ou 3 options d'architecture comparées, schémas associés, puis au choix revue d'architecture, chiffrage et dossier d'architecture technique. Suit aussi d'autres workflows décrits en JSON, comme du code d'infrastructure jusqu'au schéma cloud et au modèle de menaces, ou l'instruction d'un dossier reçu jusqu'à l'avis d'architecture. S'arrête après chaque étape pour la revue de l'utilisateur et trace chaque choix et décision dans un journal.

**Skills** : `check-prerequisites`, `mission-workspace`, `decision-log`, `agent-handoff`, `doc-to-markdown`, `markdown-to-obsidian`, `requirements-catalog`, `architecture-options`, `urbanization-map`, `well-architected-review`, `drawio-diagram`, `cloud-architecture`, `diagram-export`, `architecture-deck`, `threat-model`, `architecture-review`, `solution-estimate`, `cloud-cost`, `architecture-dossier`, `data-protection`, `migration-assessment`, `transition-roadmap`, `api-contract`

Généré depuis `src/agents/architecture-workflow.contract.json`, qui fait foi.

- **Niveau** : moyen (modèle standard, `shared/models.json`).
- **Reçoit** : Un dossier de projet contenant documents/ : cahiers des charges, comptes rendus, spécifications (PDF, Office, Markdown, images) ; Avec le workflow architecture, le POS du SI existant (plan d'occupation des sols, JSON ou CSV de urbanization-map), pour situer la solution dans l'architecture globale ; Le vault Obsidian qui sert de mémoire partagée ; À chaque porte de revue, la réponse de l'utilisateur : validation ou retour ; Ou le dossier d'une mission (mission.json, skill mission-workspace) : son vault, ses documents et ses dépôts, sans les redemander.
- **Produit** : sources/*.md : les documents en Markdown ; exigences.json, exigences.md, exigences.csv : catalogue des exigences fonctionnelles et non fonctionnelles, sources vérifiées ; options.json, options.md : 2 ou 3 options comparées et recommandation ; decision.json et adr-architecture.md : le choix de l'utilisateur ; schemas/architectures.drawio et un PNG par option ; avec un POS, le POS cible de chaque option (schemas/pos-option-<id>.drawio) ; Au choix de l'utilisateur (étapes facultatives) : revue.json et revue.md, revue d'architecture de l'option retenue ; chiffrage.json, chiffrage.md et chiffrage.csv, son chiffrage ; workflow.json et journal.md : état des étapes, choix, questions, retours et validations ; Dans le vault Obsidian, mémoire partagée : une note par exigence, option et décision, l'ADR et une note d'index, reliées par des wikilinks.
- **Ne fait jamais** : Démarrer une étape avant la validation explicite, par l'utilisateur, de celles dont elle dépend (ou son renoncement à une étape facultative) ; Valider une étape à la place de l'utilisateur ; Modifier les documents d'origine de documents/ ; Écrire workflow.json, journal.md, les catalogues Markdown ou le XML draw.io à la main.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `document-extractor` | des documents demandent une transcription par vision page à page (scans, schémas en image) en lot | les documents ; la cible markdown et le dossier sources/ |
| `schema-designer` | l'utilisateur veut pour l'option retenue un schéma C4, cloud aux icônes officielles ou réseau | options.md et options.json ; l'option retenue et ses noms de composants ; le dossier schemas/ ; la note de l'option dans le vault |
| `document-publisher` | le dossier d'architecture doit être livré en Word, HTML, XWiki ou présenté en PowerPoint | exigences.md, options.md, adr-architecture.md et les PNG, ou presentation.md (deck_build.py, skill architecture-deck) pour PowerPoint ; l'outil cible ; le gabarit .potx de la marque, s'il est connu |
| `architecture-reviewer` | une revue d'architecture (ATAM, traçabilité, code comparé à l'architecture), un modèle de menaces STRIDE ou une revue Well-Architected est demandé, pour l'option retenue ou à l'étape menaces d'un workflow | options.json et l'option retenue, exigences.json et adr-architecture.md pour une revue d'architecture ; la description JSON cloud (schemas/option-<id>.cloud.json ou schemas/architecture.json) ; le dossier schemas/ ; la note de l'option dans le vault |
| `solution-estimator` | l'utilisateur veut le chiffrage de l'option retenue (étape chiffrage) | exigences.json, options.json et decision.json ; les taux, l'horizon et le budget donnés par l'utilisateur, ou les hypothèses notées au journal ; la note de l'option dans le vault |

### `document-extractor`

Extrait le contenu de documents PDF, DOCX, PPTX, XLSX ou d'images vers Markdown ou Obsidian. Choisit l'outil (MarkItDown, Docling, vision), adapte l'effort de chaque action pour limiter les coûts et valide le résultat avant de le livrer.

**Skills** : `check-prerequisites`, `doc-to-markdown`, `markdown-to-obsidian`, `agent-handoff`

Généré depuis `src/agents/document-extractor.contract.json`, qui fait foi.

- **Niveau** : moyen (modèle standard, `shared/models.json`).
- **Reçoit** : Fichiers PDF, DOCX, PPTX, XLSX, images, ou un dossier ; La cible : Markdown ou vault Obsidian ; Un dossier de sortie (défaut : à côté du document).
- **Produit** : Un Markdown par document et ses images dans attachments/ ; Ou des notes rangées dans le vault Obsidian.
- **Ne fait jamais** : Produire du Word, du HTML ou une page de wiki ; Envoyer un document à un service en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | un schéma en image doit devenir modifiable | l'image extraite et le Markdown qui la contient ; le public et la destination |
| `document-publisher` | le Markdown obtenu doit partir en Word, HTML ou XWiki | les Markdown produits ; l'outil cible ; le modèle Word s'il y en a un |

### `document-publisher`

Transforme une documentation Markdown ou Obsidian en fichiers à publier : Word prêt à l'emploi, présentation PowerPoint, page HTML autonome ou page XWiki, schémas compris, pour SharePoint, Confluence ou XWiki. Ne publie rien en ligne. Adapte l'effort de chaque action pour limiter les coûts et relit le rendu avant de livrer.

**Skills** : `check-prerequisites`, `markdown-publish`, `diagram-export`, `agent-handoff`

Généré depuis `src/agents/document-publisher.contract.json`, qui fait foi.

- **Niveau** : simple (modèle léger, `shared/models.json`).
- **Reçoit** : Des fichiers Markdown ou des notes Obsidian (et le vault) ; L'outil cible : Word, PowerPoint, SharePoint, Confluence ou XWiki ; Un modèle Word ou un gabarit PowerPoint (.potx), s'il existe.
- **Produit** : Des fichiers .docx, .pptx, .html, .xwiki et ses images ; En option un PDF.
- **Ne fait jamais** : Publier en ligne : l'utilisateur importe lui-même les fichiers.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | un schéma ne s'exporte pas ou doit être corrigé | le fichier source du schéma ; le message d'erreur ; la destination |
| `document-extractor` | la source n'est pas encore en Markdown (PDF, Office) | le document ; la cible Markdown et le dossier de travail |

### `orientation`

Point d'entrée quand on ne sait pas par où commencer : lit la demande et les fichiers fournis, ouvre la mission au démarrage d'une avant-vente ou d'une revue d'architecture (un répertoire, un vault, le workflow de sa nature), choisit l'agent ou le workflow de myskills qui la traite (conversion de documents, schémas, architecture, revue, chiffrage, publication) et lui passe la main par un message validé. Ne fait aucun travail métier et pose au plus une question.

**Skills** : `agent-handoff`, `mission-workspace`

Généré depuis `src/agents/orientation.contract.json`, qui fait foi.

- **Niveau** : simple (modèle léger, `shared/models.json`).
- **Reçoit** : La demande de l'utilisateur, telle quelle, quand il ne sait pas quel agent ou quel workflow lancer ; Les fichiers qu'il fournit, s'il y en a (documents, schémas, code d'infrastructure, options, exigences) ; Le dossier de travail : une mission déjà ouverte (mission.json), ou le dossier où ouvrir celle d'une nouvelle avant-vente ou revue d'architecture.
- **Produit** : Au démarrage d'une avant-vente ou d'une revue d'architecture : la mission ouverte (mission.json, documents/ avec les documents fournis, vault, code/ et dépôts pour une revue, workflow de sa nature démarré), par mission.py init ; passage.json : le message de passage vers l'agent choisi (workflow nommé dans constraints), validé par check_message.py ; Une phrase qui dit quel agent ou quel workflow est choisi et pourquoi.
- **Ne fait jamais** : Faire le travail métier de l'agent choisi (convertir, dessiner, concevoir, revoir, chiffrer, publier) ; Poser plus d'une question à l'utilisateur ; Lire catalog.json ou les SKILL.md : route.py donne la liste des candidats ; Ouvrir une mission dans une mission existante, ou hors d'une avant-vente ou d'une revue d'architecture (simple conversion, schéma ou publication).
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `architecture-workflow` | la demande enchaîne plusieurs étapes d'un workflow livré (des documents à l'architecture, une infrastructure existante à ses menaces, un dossier à revoir...) | le dossier de la mission dans constraints (mission : <root>), ouverte au démarrage s'il le faut ; le nom du workflow dans constraints (workflow : <nom>) ; les fichiers fournis ; l'objectif dans les mots de l'utilisateur |
| `document-extractor` | il faut seulement convertir ou importer des documents (PDF, Office, images) en Markdown ou dans Obsidian | les documents ; la destination (dossier ou vault) |
| `schema-designer` | il faut seulement un schéma (flux, séquence, C4, cloud, POS, draw.io, Excalidraw) | le contenu ou les fichiers à représenter ; le public et la destination |
| `architecture-reviewer` | il faut revoir une architecture existante, ses menaces ou sa conformité Well-Architected | l'architecture (options, description cloud, code) ; ce qui est demandé : revue, menaces, Well-Architected |
| `solution-estimator` | il faut chiffrer une solution déjà décrite (exigences et option retenue) | exigences.json et options.json ; taux, horizon et budget s'ils sont donnés |
| `document-publisher` | il faut seulement publier une documentation Markdown en Word, PowerPoint, HTML ou XWiki | les fichiers Markdown ; l'outil cible |

### `schema-designer`

Conçoit des schémas d'ingénierie logicielle. Choisit le format (Mermaid, draw.io, Excalidraw, C4 avec LikeC4) selon le contexte, le public et la destination, adapte l'effort de chaque action pour limiter les coûts et valide le résultat avant de le livrer.

**Skills** : `check-prerequisites`, `diagram-brief`, `mermaid-diagram`, `drawio-diagram`, `excalidraw-diagram`, `c4-architecture`, `urbanization-map`, `cloud-architecture`, `well-architected-review`, `diagram-export`, `agent-handoff`

Généré depuis `src/agents/schema-designer.contract.json`, qui fait foi.

- **Niveau** : moyen (modèle standard, `shared/models.json`).
- **Reçoit** : Un contexte : description, code, ADR, Markdown ou image d'un schéma existant ; Si possible le public, la destination et le dossier de sortie.
- **Produit** : La source du schéma : bloc Mermaid, .drawio, .excalidraw et sa description .json (ou l'inventaire .csv d'un POS), ou modèle LikeC4 ; pour un schéma cloud, la matrice des flux et la revue des conventions de schéma (.wa.md) ; Ses exports PNG, SVG ou PDF ; pour Confluence avec draw.io, le .drawio et le .drawio.png.
- **Ne fait jamais** : Modifier un fichier qu'il n'a pas créé, sauf le schéma à corriger ; Envoyer un schéma à un service en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `document-extractor` | le contexte est un document à convertir d'abord (PDF, Office) | le document ; la cible Markdown et le dossier de travail |
| `document-publisher` | le schéma doit être intégré dans un Word, une page HTML ou XWiki | le Markdown qui référence le schéma ; la source et l'export ; l'outil cible |
| `architecture-reviewer` | un modèle de menaces STRIDE ou une revue Well-Architected des piliers est demandé pour le schéma cloud | la description JSON du schéma cloud ; le .drawio et son export ; les contraintes de sécurité connues |

### `solution-estimator`

Chiffre une solution à partir du catalogue d'exigences et de l'option d'architecture retenue : découpe en lots par composant, estime chaque lot à trois points, pose les hypothèses d'infrastructure et de run, puis fait calculer par script la charge, la fourchette, le coût d'infrastructure, le run, le coût total sur plusieurs années et le respect du budget. Adapte l'effort de chaque action pour limiter les coûts.

**Skills** : `check-prerequisites`, `solution-estimate`, `cloud-cost`, `requirements-catalog`, `architecture-options`, `decision-log`, `agent-handoff`

Généré depuis `src/agents/solution-estimator.contract.json`, qui fait foi.

- **Niveau** : complexe (modèle puissant, `shared/models.json`).
- **Reçoit** : Le catalogue d'exigences validé (exigences.json de requirements-catalog) ; Les options d'architecture (options.json d'architecture-options), avec la décision ou la recommandation ; l'option à chiffrer si ce n'est pas celle-là ; Ce que l'utilisateur veut chiffrer et les données connues : taux journaliers des profils, horizon, budget, devis ou grilles tarifaires, contraintes de planning.
- **Produit** : chiffrage.json : description du chiffrage (lots, charges, infrastructure, run, hypothèses), validée par estimate_build.py ; chiffrage.md : chiffrage pour la revue (synthèse, fourchette, budget, trois hypothèses sans IA, avec IA et dev IA natif, détail, coût total, couverture, hypothèses) ; chiffrage.csv : lignes détaillées pour un tableur, relu par le script ; chiffrage.hypotheses.csv : lignes de chaque hypothèse de production, relu par le script ; chiffrage.charges.md et chiffrage.charges.csv : plan de charge sans montant (tâche, complexité, jours, heures, par hypothèse) ; seuls produits sans taux journaliers.
- **Ne fait jamais** : Écrire un total, une espérance ou une fourchette à la main : le script les calcule ; Chercher un tarif en ligne ou envoyer le chiffrage à un service en ligne : un prix inconnu est une hypothèse avec sa base ; Modifier exigences.json ou options.json : un écart se signale à l'agent ou au skill qui les tient.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `architecture-workflow` | le chiffrage est fait pour un workflow : rendre la main pour la soumission | chiffrage.md et chiffrage.csv ; les hypothèses à valider et les avertissements restants ; le dossier du workflow |
| `document-publisher` | le chiffrage doit être livré en Word, HTML ou XWiki | chiffrage.md ; l'outil cible |

## Skills

### `agent-handoff`

Valide un message de passage entre agents ou le rapport final d'un agent (JSON Schema, fichiers cités présents) et le note au journal d'un workflow ; donne la liste compacte des agents et workflows classés pour une demande. À utiliser par tout agent avant de passer la main à un autre ou de rendre son rapport final, et pour choisir par où commencer.

Résumé de [`contract.json`](skills/agent-handoff/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier de travail, ou dossier d'un workflow (workflow.json) ; Un message de passage (shared/schemas/handoff.schema.json) ou un rapport final d'agent (shared/schemas/agent-report.schema.json), en JSON ; Pour le routage : la demande de l'utilisateur et les fichiers fournis (route.py).
- **Sorties** : Aucun fichier ; dans un dossier de workflow, une entrée « passage » ou « rapport » au journal (workflow.json, journal.md).
- **`check_message.py`** : Valide un message de passage ou un rapport final d'agent contre son schéma, vérifie que chaque fichier cité existe et, dans un dossier de workflow, le note au journal (skill decision-log). Rapport JSON, codes de sortie : 0 message conforme, fichiers présents (et tracé au journal s'il y a un workflow) ; 1 message illisible, non conforme à son schéma ou fichier cité introuvable.
- **`route.py`** : Donne la liste compacte des agents et workflows (et, sur demande, des skills) depuis le catalogue de routage généré par build.py, classée par les mots partagés avec la demande et les extensions des fichiers fournis ; le score est un indice, le choix revient à l'agent orientation ; dans une mission (mission.json), donne sa nature, ses workflows et son vault, et met ses workflows devant. Rapport JSON, codes de sortie : 0 liste rendue (avertissement si aucun mot commun ou égalité en tête) ; 1 ni --query ni --list, ou catalogue de routage illisible.
- **`route_laya.py`** : Pose au modèle local Laya (CPU, sans service en ligne) la question fermée de route.py --laya : quel candidat traite la demande, d'après les descriptions ; lancé par route.py dans son propre environnement. Rapport JSON, codes de sortie : 0 choix rendu ; 1 description invalide ou Laya indisponible.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : noter le message au journal d'un workflow.
- **Passe la main** à l'utilisateur : l'outil ne permet pas d'appeler l'agent visé : lui donner le message et l'agent à lancer.

### `api-contract`

Écrit les contrats d'interface d'une solution, OpenAPI 3.1 pour les opérations REST et AsyncAPI 3.0 pour les événements, à partir d'une description JSON courte : ressources, opérations, événements, composant porteur et exigences. Le script écrit le YAML, contrôle doublons, types, ressources, exigences et composants de l'option d'architecture, et relit chaque contrat. À utiliser pour concevoir ou documenter une API, un contrat d'interface, des échanges par événements ou les interfaces de l'option retenue.

Résumé de [`contract.json`](skills/api-contract/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Description JSON courte des interfaces (api_build.py --schema) : ressources, opérations REST, événements ; Facultatif : exigences.json (requirements-catalog) et options.json avec l'option retenue (architecture-options).
- **Sorties** : <nom>.openapi.yaml : contrat OpenAPI 3.1 des opérations REST ; <nom>.asyncapi.yaml : contrat AsyncAPI 3.0 des événements ; <nom>.api.md : tableaux des opérations, événements et ressources, couverture des exigences.
- **`api_build.py`** : Écrit les contrats OpenAPI 3.1 et AsyncAPI 3.0 d'une description courte et les contrôle : noms uniques, une opération par méthode et chemin, types et ressources connus, champs obligatoires déclarés, pas de corps pour GET et DELETE, exigences citées présentes, composant porteur présent dans l'option, exigence fonctionnelle indispensable sans interface et écriture sans sécurité signalées ; relit chaque YAML écrit et résout chaque $ref. Rapport JSON, codes de sortie : 0 contrats écrits et relus (avertissements possibles : exigence sans interface, écriture sans sécurité, ressource inutilisée) ; 1 description invalide, type ou ressource inconnus, doublon, exigence ou composant absents, relecture en échec ; aucun fichier produit sauf en cas d'échec de relecture.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et reprendre les composants de l'option.
- **Passe la main** au skill `architecture-review` : les interfaces doivent être revues avec l'architecture (traçabilité, dépendances synchrones).
- **Passe la main** à l'agent `document-publisher` : les contrats doivent être livrés dans un dossier Word, HTML ou XWiki.
- **Passe la main** à l'utilisateur : une exigence fonctionnelle indispensable n'a pas d'interface : l'ajouter ou dire qu'elle est hors API.

### `architecture-deck`

Assemble la présentation d'un dossier d'architecture (besoin, exigences, options notées, schémas, décision, couverture) depuis les étapes déjà validées d'un workflow, sans rien rédiger, au format du skill externe markdown-to-pptx. À utiliser pour présenter un choix d'architecture en PowerPoint à un comité.

Résumé de [`contract.json`](skills/architecture-deck/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier d'un workflow d'architecture aux étapes validées : options.json, exigences.json (et son glossaire), decision.json, PNG des schémas déjà exportés.
- **Sorties** : presentation.md : présentation du dossier (besoin, options, décision) au format du skill externe markdown-to-pptx, schémas exportés compris ; chaque donnée n'y figure qu'une fois.
- **`deck_build.py`** : Assemble la présentation du dossier à partir des étapes validées, sans rien demander au modèle : options.json (validé contre le schéma d'options_build.py), le catalogue d'exigences et son glossaire, decision.json, les PNG des schémas déjà exportés. Mêmes scores et contrôles qu'options_build.py ; une diapositive par information (chiffres clés, exigences indispensables, glossaire, notes par critère en graphique, scores, écarts, comparaison, un schéma par option, décision, couverture par l'option retenue, questions ouvertes), le détail dans les notes de l'orateur. Rapport JSON, codes de sortie : 0 presentation.md écrit ; 1 options.json, decision.json ou catalogue illisible ou invalide (erreurs avec leur chemin) ; aucun fichier écrit.
- **Dépend de** `architecture-options` (`options_build.py`, obligatoire) : mêmes scores, contrôles et schéma d'options.json que la comparaison validée.
- **Passe la main** au skill `markdown-publish` : produire le .pptx de presentation.md avec pptx_publish.py (skill externe markdown-to-pptx).

### `architecture-dossier`

Assemble le dossier d'architecture technique (DAT) d'un projet à partir des livrables validés d'un workflow : synthèse, exigences, options, décision (ADR), schémas, revue d'architecture, menaces, Well-Architected, chiffrage et journal, selon un gabarit de sections. Signale les pièces manquantes et vérifie les liens. À utiliser pour préparer un comité d'architecture ou livrer le dossier d'un projet.

Résumé de [`contract.json`](skills/architecture-dossier/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier d'un workflow d'architecture (livrables validés : exigences.md, options.md, ADR, schémas PNG, revue, menaces, Well-Architected, chiffrage, journal) ; synthese.md : la synthèse pour le comité, seule pièce écrite pour le dossier ; Facultatif : un gabarit de sections (JSON) propre à l'organisation ; Pour actions.py : les revues déjà produites du dossier (*.wa.md, *.threats.md, *.aipd.md, revue.md) ; facultatif, l'affectation (responsable, échéance) en JSON.
- **Sorties** : dossier-architecture.md : DAT en un seul Markdown (sommaire, sections numérotées, pièces reprises, schémas intégrés, annexes), liens vérifiés ; plan-actions.md et plan-actions.csv : plan d'actions unique, dédoublonné et priorisé, tiré des revues (CSV importable dans Jira ou Azure DevOps).
- **`dossier_build.py`** : Assemble le DAT d'un dossier de workflow selon un gabarit de sections : pièces Markdown reprises (frontmatter et titre retirés, titres décalés, liens recalés), images intégrées, fichiers listés en annexe ; signale chaque section obligatoire sans pièce avec la commande qui la produit ; relit le dossier produit et vérifie chaque lien et chaque image. Rapport JSON, codes de sortie : 0 dossier produit (sections manquantes et liens cassés en avertissements) ; 1 dossier introuvable, gabarit invalide, ou section obligatoire manquante avec --strict ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`actions.py`** : Rassemble les points ouverts des revues d'un dossier (constats Well-Architected et de revue d'architecture, risques de la revue, menaces à mesure retenue, risques de l'AIPD à mesure prévue ou résiduel élevé) en un plan d'actions unique : une action par règle ou par mesure (éléments regroupés), priorité P1 à P3 tirée de la gravité, responsable et échéance par défaut ou par clé ; relit le CSV produit. Rapport JSON, codes de sortie : 0 plan écrit (menaces encore à analyser et clés inconnues en avertissements) ; 1 dossier introuvable ou affectation invalide ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** à l'agent `document-publisher` : le dossier doit être livré en Word, PDF, HTML ou XWiki.
- **Passe la main** au skill `decision-log` : le dossier est un livrable d'étape : le soumettre à la revue (journal.py submit).
- **Passe la main** à l'utilisateur : une section obligatoire manque : produire la pièce, ou l'écarter du gabarit avec sa raison.

### `architecture-options`

Propose et compare 2 ou 3 options d'architecture à partir d'un catalogue d'exigences : écarts de couverture, notes par critère justifiées, score pondéré et rang calculés par script, recommandation, puis ADR de la décision et un schéma draw.io par option. À utiliser pour proposer des architectures, comparer des scénarios ou documenter un choix d'architecture.

Résumé de [`contract.json`](skills/architecture-options/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Facultatif : le POS existant du SI (JSON ou CSV de urbanization-map, ou note Markdown avec tableau), dans le dossier ou dans le vault Obsidian du workflow (vault:<chemin>) ; Description JSON des options : title, context, audience, requirements, pos, hosting (qualifications, refs), criteria, options (id, name, summary, provider, components, flows, gaps, placement, wa_accept, scores, score_notes, pros, cons, risks), recommendation, decision ; Après la revue : decision.json, le choix de l'utilisateur (option, by, why, date, refs).
- **Sorties** : <nom>.md : comparaison pour la revue (synthèse et rang, critères et notes, écarts aux exigences, détail des options, recommandation, décision) ; schemas/architectures.json : description draw.io, une page par option, à construire avec drawio_build.py ; adr-architecture.md : décision d'architecture, quand decision est renseignée ou --decision donné ; tracabilite.md, tracabilite.csv : matrice exigence, couverture par option, composants de l'option retenue (ou recommandée) ; schemas/option-<id>.cloud.json : description cloud_build.py d'une option qui a un provider (icônes officielles) ; schemas/option-<id>.wa.md : revue Well-Architected des piliers d'une option cloud (wa_check.py du skill well-architected-review) ; schemas/pos-option-<id>.json : POS cible de chaque option (statuts des applications touchées), écrit par pos_impact.py (urbanization-map), à construire avec pos_build.py.
- **`options_build.py`** : Vérifie les références aux exigences, calcule le score pondéré et le rang de chaque option, élimine celles qui laissent une exigence indispensable non couverte, signale une recommandation qui ne suit pas le classement, puis écrit la comparaison, la description des schémas et l'ADR ; écrit la matrice de traçabilité exigence, option, composant (tracabilite.md, tracabilite.csv) et, pour une option avec provider, la description cloud_build.py de son schéma aux icônes officielles et sa revue Well-Architected des piliers (wa_check.py de well-architected-review) (constats par pilier dans la comparaison, constats de l'option retenue dans l'ADR). Avec le POS du SI, vérifie le placement de chaque option (pos_impact.py d'urbanization-map), en compte les impacts (créations, évolutions, remplacements, redondances, flux entre zones) et écrit son POS cible. Rapport JSON, codes de sortie : 0 comparaison produite sans erreur (avertissements possibles) ; 1 description invalide, exigence ou composant inconnu, note manquante ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `urbanization-map` (`pos_impact.py`, facultatif : sans lui, avertissement) : placement de chaque option dans le POS du SI, impacts et POS cibles ; erreur si la description a un pos.
- **Dépend de** `well-architected-review` (`wa_check.py`, facultatif : sans lui, avertissement) : revue Well-Architected des piliers de chaque option cloud.
- **Passe la main** au skill `drawio-diagram` : construire schemas/architectures.drawio avec drawio_build.py.
- **Passe la main** au skill `diagram-export` : exporter les pages en PNG et les relire.
- **Passe la main** à l'agent `schema-designer` : un schéma C4, cloud aux icônes officielles ou un modèle de menaces est demandé pour l'option retenue.
- **Passe la main** au skill `decision-log` : noter la recommandation, soumettre la comparaison, puis la décision de l'utilisateur.
- **Passe la main** au skill `urbanization-map` : construire le POS cible de chaque option avec pos_build.py.
- **Passe la main** au skill `architecture-deck` : la décision est prise et les schémas exportés : assembler la présentation du dossier.
- **Passe la main** à l'agent `solution-estimator` : la décision est prise : chiffrer l'option retenue (charge, infrastructure, run, coût total).
- **Passe la main** au skill `cloud-architecture` : construire le schéma aux icônes du fournisseur d'une option cloud (schemas/option-<id>.cloud.json).

### `architecture-review`

Revue d'une architecture logicielle ou solution à la manière d'ATAM : scénarios de qualité évalués, risques, points de sensibilité, compromis et décisions, contrôle mécanique de la structure (cycles, base partagée, couches, chaîne synchrone, dépendance externe, point unique de défaillance) et de la traçabilité des exigences, avis calculé. Peut comparer le code à l'architecture avec graphify (analyse locale) et intégrer les piliers Well-Architected d'une option cloud. À utiliser pour revoir, auditer ou valider une architecture, une option retenue ou un dossier d'architecture.

Résumé de [`contract.json`](skills/architecture-review/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON de la revue (revue.json) : composants, flux, couches, scénarios de qualité, risques, points de sensibilité, compromis, décisions ; ou les composants et flux d'une option d'architecture-options (source) ; Facultatif : le catalogue d'exigences (exigences.json de requirements-catalog), pour la traçabilité ; Facultatif : la description cloud de la même architecture (schemas/option-<id>.cloud.json), pour les piliers Well-Architected ; Facultatif : le code source, ou le graph.json déjà produit par graphify, pour comparer le code à l'architecture ; Facultatif : accept, les écarts acceptés avec leur raison ; Règles de complétude (scénarios attendus) : references/scenarios-attendus.json, complétées par celles de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json) et de la mission (references.regles de mission.json), schéma shared/schemas/rules.schema.json.
- **Sorties** : <sujet>.revue.md : avis, synthèse par axe, arbre d'utilité (scénarios de qualité et leur évaluation), constats, risques, points de sensibilité et compromis, décisions, traçabilité des exigences, conformité du code, points à vérifier hors de la description ; Avec --vault : dans le vault, Revues d'architecture/<titre>.md (revue-architecture, avis, evalue), Constats/<titre>/*.md et Risques/<titre>/*.md (porte-sur, issu-de).
- **`arch_review.py`** : Contrôle une architecture logicielle ou solution décrite en JSON, à la manière d'une revue ATAM : structure (cycles de dépendances synchrones, base partagée, couches, composant pivot, chaîne synchrone longue, dépendance synchrone à un système externe, point unique de défaillance), traçabilité des exigences (exigence indispensable sans composant ni décision, exigence non fonctionnelle sans scénario de qualité), scénarios de qualité (non satisfaits ou à risque sans risque noté, sans mesure, scénario attendu absent selon les règles de complétude : pointe de charge, panne, sinistre, attaque, croissance, incident), décisions et risques ; avec une description cloud, les piliers Well-Architected (wa_check.py de well-architected-review) ; avec le code, dépendances du code absentes de l'architecture et cycles entre composants, à partir du graphe de graphify (skill externe : code analysé en local ; documents, si demandés, lus par le modèle du harness ou un modèle local). Calcule l'avis et écrit <sujet>.revue.md ; avec --vault, verse la revue, ses constats et ses risques dans le vault Obsidian, notes vérifiées contre l'ontologie avant l'écriture ; avec plusieurs dépôts (code.repos, ou ceux de la mission), un graphe par dépôt et les appels entre services lus dans la configuration et les contrats (URL d'un autre service, base de données, canaux AsyncAPI) : appel absent de l'architecture, flux déclaré sans trace, base partagée, dépôt sans composant. Avec --draft, écrit d'abord le brouillon de la description (source, squelettes de scénarios) que le modèle complète et évalue. Rapport JSON, codes de sortie : 0 revue écrite, aucun constat non accepté au seuil --fail-on ; 1 description illisible, référence inconnue, graphify manquant ou en échec, note du vault hors ontologie, ou constat non accepté au seuil --fail-on ; sauf erreur, le rapport et <sujet>.revue.md sont tout de même produits.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et en reprendre les composants et les flux de l'option revue.
- **Dépend de** `well-architected-review` (`wa_check.py`, facultatif : sans lui, avertissement) : piliers Well-Architected de la description cloud (cloud).
- **Vault Obsidian** : écrit les notes de type `revue-architecture`, `constat`, `risque` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill externe `graphify` (installé à part, contrat `shared/external/graphify.contract.json`) : comparer le code à l'architecture : le script lance graphify extract sur code.root, ou sur chaque dépôt de code.repos ou de la mission, en parallèle (--code-only par défaut, ou documents lus par le modèle du harness ou Ollama avec semantic) et lit les graphes.
- **Passe la main** au skill `architecture-options` : un constat demande de changer l'option (composant, flux, écart) : corriger options.json puis relancer.
- **Passe la main** au skill `well-architected-review` : revue Well-Architected complète d'une architecture cloud, conventions du schéma comprises.
- **Passe la main** au skill `threat-model` : analyse des menaces STRIDE de l'architecture revue.
- **Passe la main** au skill `decision-log` : dans un workflow : noter les écarts acceptés et soumettre la revue.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept ; un risque attend un responsable.

### `c4-architecture`

Modélise une architecture logicielle selon le modèle C4 (contexte, conteneurs, composants) avec LikeC4, valide le modèle et exporte une image par vue. À utiliser pour les schémas d'architecture.

Résumé de [`contract.json`](skills/c4-architecture/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Code, configuration ou description de l'architecture ; Description JSON du modèle (c4_build.py --schema), ou options.json d'architecture-options et l'option retenue.
- **Sorties** : Dossier LikeC4 : specification.c4 et model.c4 ; Un PNG par vue (après export).
- **`c4_build.py`** : Écrit le modèle LikeC4 (model.c4, specification.c4 de la charte) à partir d'une description JSON courte ou d'une option d'architecture-options, puis le vérifie : identifiants uniques, relations vers des éléments connus (avec la valeur proche), imbrication C4, vues de 20 éléments au plus, likec4 validate s'il est installé. Rapport JSON, codes de sortie : 0 modèle écrit et vérifié (avertissements possibles) ; 1 description invalide, référence inconnue, imbrication interdite ou erreur de likec4 validate ; aucun fichier sauf dans ce dernier cas.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : --from-options : valider options.json contre son schéma et reprendre une option.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : valider le modèle et exporter les vues.
- **Passe la main** au skill `excalidraw-diagram` : une vue est destinée à un public non technique.

### `check-prerequisites`

Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (uv, draw.io Desktop, navigateur, LibreOffice en option) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable.

Résumé de [`contract.json`](skills/check-prerequisites/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Un groupe : extraction, schemas, publication, revue ou tout (défaut) ; Facultatif : --prefetch, pour préparer une machine qui travaillera hors ligne.
- **Sorties** : Aucun fichier, sauf avec --prefetch : les bibliothèques de rendu dans le cache de myskills.
- **`doctor.py`** : Vérifie les outils locaux et donne la commande d'installation des manquants ; avec --prefetch, remplit le cache des bibliothèques de rendu (version fixée, empreinte vérifiée) pour travailler hors ligne. Rapport JSON, codes de sortie : 0 tous les outils obligatoires sont présents (et le préchargement a réussi) ; 1 au moins un outil obligatoire manque, groupe inconnu, ou préchargement impossible (réseau, empreinte différente).
- **Passe la main** à l'utilisateur : un outil manque : il l'installe lui-même, rien n'est installé sans son accord.

### `cloud-architecture`

Dessine des schémas d'architecture cloud en draw.io avec les icônes officielles AWS, Azure, GCP et Kubernetes : déploiement (régions, VPC, sous-réseaux), réseau et flux (matrice des flux), cluster Kubernetes, haute disponibilité et PRA (RPO, RTO), pipeline data ou CI/CD GitOps. Sa description sert aussi au modèle de menaces STRIDE (threat-model) et à la revue Well-Architected (well-architected-review). À utiliser pour un architecte solution, à partir d'une description ou de code d'infrastructure.

Résumé de [`contract.json`](skills/cloud-architecture/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief : public et destination ; Description JSON de l'architecture : title, provider (aws, azure, gcp, k8s ou hébergeur souverain : ovh, outscale, cloud-temple, scaleway, s3ns, bleu, numspot, sur-site), qualifications, view, items (groupes imbriqués et services typés), flows, objectives ; ou du code d'infrastructure (Terraform, CloudFormation, Bicep, docker-compose, manifestes Kubernetes) que iac_import.py traduit en description.
- **Sorties** : <sujet>.drawio en XML clair, avec les icônes officielles AWS, Azure, GCP ou Kubernetes (formes génériques de la charte pour les hébergeurs souverains), à côté de sa description <sujet>.json ; Vue network (ou --matrix) : <sujet>.flows.md, la matrice des flux ; Après export : <sujet>.drawio.png (une image par page), .svg ou .pdf.
- **`cloud_build.py`** : Construit le schéma draw.io (mise en page des groupes imbriqués, icônes officielles livrées dans draw.io, flux, titre, RPO/RTO, légende), puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON, codes de sortie : 0 schéma produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`iac_import.py`** : Écrit la description de cloud_build.py depuis le code d'infrastructure : ressources Terraform (AWS, Azure, Google), CloudFormation (AWS, YAML ou JSON) et Bicep (Azure), services docker-compose et manifestes Kubernetes deviennent services typés, réseaux et namespaces des groupes, références et dépendances des flux ; la description est validée contre le schéma d'entrée de cloud_build.py et construite à blanc avant d'être écrite. Rapport JSON, codes de sortie : 0 description écrite, conforme et construite sans erreur ; 1 source introuvable ou format non reconnu, aucune ressource reconnue, ressource en double, ou description produite rejetée par cloud_build.py ; rien n'est écrit.
- **Dépend de** `drawio-diagram` (`check_drawio.py`, facultatif : sans lui, avertissement) : vérifier le .drawio produit.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main.
- **Passe la main** au skill `mermaid-diagram` : diagramme de séquence des appels entre services pour un parcours.
- **Passe la main** au skill `threat-model` : modèle de menaces STRIDE de l'architecture décrite (même description JSON).
- **Passe la main** au skill `well-architected-review` : revue Well-Architected des piliers ou des conventions de schéma (même description JSON).

### `cloud-cost`

Estime et compare le coût de fonctionnement mensuel d'options d'architecture cloud (AWS, Azure, Google Cloud, OVHcloud, Scaleway, ou prix propres) : consommations par option (calcul, conteneurs, base de données, stockage, réseau, journaux), plages horaires, remise d'engagement, production et hors production, calculées par script sur une grille de prix locale. Signale les prix à vérifier, le hors production allumé en continu et les postes oubliés. À utiliser pour un coût de run, une estimation FinOps, comparer des options sur leur coût d'hébergement ou préparer les lignes d'infrastructure d'un chiffrage.

Résumé de [`contract.json`](skills/cloud-cost/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Les options d'architecture cloud à comparer (options.json d'architecture-options, ou leurs schémas cloud) et le dimensionnement connu : volumes, utilisateurs, données ; Description JSON des consommations par option (cost_build.py --schema) : service de la grille, quantité, environnement, plage horaire, prix propre et sa base, remise d'engagement ; Facultatif : une grille de prix propre (devis, grille vérifiée), de même forme que references/prix.json.
- **Sorties** : <nom>.md : comparaison des options (par mois, par an, sur l'horizon, production et hors production), coût par catégorie, détail des lignes avec la base de chaque prix ; <nom>.csv : une ligne par consommation (séparateur ;) ; Avec --infra : <nom>.infra.json, les lignes d'infrastructure du chiffrage de l'option (solution-estimate).
- **`cost_build.py`** : Vérifie hébergeurs et services de la grille, calcule chaque consommation (prix horaire et plage, ou prix mensuel), la remise d'engagement, le coût mensuel par catégorie et par environnement, annuel et sur l'horizon, classe les options ; signale les prix indicatifs à vérifier, le hors production allumé en continu avec l'économie d'un arrêt, les postes souvent oubliés (trafic sortant, sauvegardes, journaux) et le budget dépassé ; écrit la comparaison et le CSV, relit le CSV pour vérifier les totaux ; avec --infra, écrit les lignes d'infrastructure du chiffrage. Rapport JSON, codes de sortie : 0 comparaison écrite et CSV vérifié (avertissements possibles : prix indicatifs, postes oubliés, budget) ; 1 description invalide, hébergeur ou service inconnu, prix absent sans unit_cost, base manquante, grille illisible ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : vérifier les lignes d'infrastructure de --infra contre le schéma du chiffrage.
- **Passe la main** au skill `architecture-options` : le coût de fonctionnement change la note du critère cout d'une option.
- **Passe la main** au skill `solution-estimate` : chiffrer l'option retenue : ses lignes d'infrastructure viennent de --infra.
- **Passe la main** à l'utilisateur : valider le dimensionnement et faire vérifier les prix indicatifs avant tout engagement.

### `data-protection`

Prépare la conformité RGPD d'une solution : fiches du registre des traitements (article 30) et analyse d'impact relative à la protection des données (AIPD, article 35), avec nécessité de l'AIPD selon les critères du CEPD, transferts hors UE, hébergeur extraterritorial, risques pour les personnes notés en gravité et vraisemblance, mesures liées aux exigences et aux menaces STRIDE. Les contrôles et la carte des risques sont faits par script. À utiliser pour une analyse RGPD, une AIPD (DPIA), un registre des traitements ou un dossier d'homologation.

Résumé de [`contract.json`](skills/data-protection/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON des traitements de données personnelles et des risques pour les personnes (dpia_build.py --schema) ; Facultatif : exigences.json (requirements-catalog) et le .threats.md (threat-model), cités par les mesures ; l'hébergeur (shared/providers.json).
- **Sorties** : <nom>.registre.md : fiches du registre des traitements (art. 30) ; <nom>.aipd.md : analyse d'impact (critères, risques, carte gravité × vraisemblance, mesures, résiduels, points à valider).
- **`dpia_build.py`** : Contrôle la description des traitements et des risques (nécessité de l'AIPD selon les critères du CEPD, base légale, données sensibles, durée de conservation, transferts hors EEE sans garantie, hébergeur extraterritorial, événements redoutés couverts, résiduel jamais supérieur à l'initial, résiduel élevé qui appelle la consultation de la CNIL, références vers les exigences et les menaces), calcule les niveaux et la carte des risques, écrit le registre et l'AIPD ; propose ce qui se déduit sans jugement : critères du CEPD tirés des données, et pour chaque risque sources, impacts et mesures (exigences de sécurité, conformité, disponibilité ; menaces STRIDE des flux du traitement et des stockages) quand la description ne les donne pas. Rapport JSON, codes de sortie : 0 registre et AIPD écrits (avertissements possibles : critères, résiduels élevés, événements non couverts) ; avec --draft, propositions écrites ; 1 description invalide, traitement ou référence inconnus, transfert hors EEE sans garantie, conservation manquante, résiduel supérieur à l'initial ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Vault Obsidian** : écrit les notes de type `traitement`, `risque` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `threat-model` : les menaces STRIDE de l'architecture ne sont pas encore analysées : elles nourrissent les risques et les mesures.
- **Passe la main** au skill `decision-log` : noter au journal un risque accepté et sa raison, soumettre l'AIPD à la revue.
- **Passe la main** à l'agent `document-publisher` : le registre ou l'AIPD doivent être livrés en Word ou PDF.
- **Passe la main** à l'utilisateur : faire valider l'analyse par le délégué à la protection des données et décider d'un risque résiduel élevé.

### `decision-log`

Tient l'état d'un workflow à étapes avec portes de revue humaine et trace chaque choix, hypothèse, question, retour et validation dans un journal (workflow.json et journal.md). Une étape ne démarre qu'après validation de celles dont elle dépend, et des étapes indépendantes se mènent en parallèle ; un fichier validé puis modifié est détecté. À utiliser pour piloter un workflow prédictible où l'utilisateur relit chaque étape et où toutes les décisions doivent être tracées.

Résumé de [`contract.json`](skills/decision-log/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier du workflow ; Commande : init, start, log, check, submit, review ou status, avec l'étape, le texte et les références (exigences, options, entrées) ; Facultatif : un vault Obsidian, mémoire partagée entre agents, sessions et utilisateur ; Pour capitaliser : une ou plusieurs missions (ou dossiers de workflow), dont les retours du journal sont lus ; puis les règles retenues par l'utilisateur (schéma shared/schemas/rules.schema.json).
- **Sorties** : workflow.json : étapes dans l'ordre (d'une définition JSON : workflows/architecture.json, cloud-existant.json, revue-dossier.json, conformite.json, migration-cloud.json ou fournie), statut, empreintes SHA-256 des fichiers soumis, entrées du journal ; journal.md : version lisible (étapes, décisions et revues, questions), réécrite à chaque commande ; Avec un vault Obsidian : VAULT/<dossier>/ avec une note d'index, Exigences/EF-001.md..., Glossaire/<terme>.md..., Options/Option A.md..., Décisions/D-001.md..., ADR architecture.md, Étapes/<étape>.md avec ses livrables intégrés (copies dans Fichiers/) ; lecons.md et lecons.json : leçons par mission et par étape, retours récurrents entre missions, règles de complétude proposées (postes attendus du chiffrage, scénarios attendus de la revue) ; avec --apply, les règles retenues ajoutées au fichier de règles de la mission ou de l'utilisateur.
- **`journal.py`** : Fait respecter l'ordre des étapes et les portes de revue (démarrage seulement après validation des étapes dont l'étape dépend, la précédente ou celles de son champ after, validation seulement d'une étape en revue dont les fichiers n'ont pas changé, retour qui remet à reprendre l'étape et celles qui en dépendent), donne les étapes prêtes à mener en parallèle (ready), sérialise les commandes d'un même dossier (verrou), note chaque choix, hypothèse, question, soumission, retour et validation, et détecte un fichier validé modifié depuis. Avec un vault, réécrit après chaque commande la mémoire partagée dans Obsidian (vault_sync.py). Rapport JSON, codes de sortie : 0 commande appliquée ; 1 commande ou message refusé (étape inconnue, ordre ou porte de revue non respectés, livrable validé modifié, fichier introuvable, définition ou workflow.json non conforme à son schéma) ; workflow.json inchangé.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`vault_sync.py`** : Écrit la mémoire partagée du workflow dans un vault Obsidian : une note par exigence, option et entrée du journal, une note par étape soumise avec ses livrables (images et Markdown copiés dans Fichiers/ et intégrés), une note d'index et l'ADR, reliées par des wikilinks et typées selon l'ontologie du vault (type, propriétés, relations typées, tags normalisés, vérifiés avant l'écriture), depuis workflow.json et les livrables que la définition nomme dans memory ; supprime les notes générées qui ne correspondent plus à rien et vérifie que chaque lien pointe vers une note. Lancé par journal.py après chaque commande quand le vault est connu. Rapport JSON, codes de sortie : 0 notes écrites, tous les liens résolus ; 1 workflow.json ou vault introuvable, fichier lu non conforme au schéma du skill qui l'écrit (workflow.json, exigences.json, options.json, decision.json), note hors ontologie du vault (rien n'est écrit), ou lien cassé.
- **`lessons.py`** : Capitalise les retours de revue sans modèle : lit les retours du journal de chaque workflow des missions données, les regroupe par mission et par étape en rapprochant ceux qui disent la même chose (mots significatifs communs), repère ceux qui reviennent dans plusieurs missions et, pour une étape de chiffrage ou de revue, propose la règle de complétude qui les attraperait (poste attendu de solution-estimate, scénario attendu d'architecture-review) sauf si une règle en place les couvre déjà ; écrit lecons.md et lecons.json, relus. Avec --apply, ajoute les règles retenues par l'utilisateur au fichier de règles de la mission (references.regles de mission.json) ou de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json), validé avant l'écriture. Rapport JSON, codes de sortie : 0 leçons écrites, ou règles retenues ajoutées ; 1 dossier sans mission ni workflow, journal illisible, règles en place invalides, ou règles retenues invalides (chemin, valeur, expression) : rien n'est écrit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider le catalogue d'exigences avant d'en écrire les notes.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et decision.json avant d'en écrire les notes.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : lire les postes attendus en place pour ne pas reproposer une règle qui couvre déjà un retour.
- **Dépend de** `architecture-review` (`arch_review.py`, facultatif : sans lui, avertissement) : lire les scénarios attendus en place pour ne pas reproposer une règle qui couvre déjà un retour.
- **Vault Obsidian** : écrit les notes de type `workflow`, `etape`, `revue`, `exigence`, `terme`, `option-architecture`, `decision`, `adr`, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** à l'utilisateur : une étape est soumise : l'utilisateur la valide ou fait un retour.
- **Passe la main** au skill `markdown-to-obsidian` : choisir le dossier et les tags du vault (vault_profile.py) avant journal.py init --vault.

### `diagram-brief`

Choix du format de schéma (Mermaid, draw.io, Excalidraw, C4, POS, cloud) selon le public, la destination (Markdown, Obsidian, Word, PowerPoint, Confluence) et le type de schéma : décision courte en JSON validée par script, qui rend le format, le skill et la livraison. À utiliser avant de produire un schéma.

Résumé de [`contract.json`](skills/diagram-brief/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Contexte du schéma : description, code, ADR, Markdown ou image ; La décision courte en JSON : public, destination, type, message principal, 3 à 7 éléments.
- **Sorties** : La décision complète (format, skill, vue cloud, livraison, raison) dans le rapport, et en JSON avec --out pour le skill de dessin ou un autre agent.
- **`brief.py`** : Valide la décision courte et applique la grille de choix (public avant destination, format modifiable là où le schéma vivra) : format, skill, vue cloud, livraison selon la destination et raison du choix. Rapport JSON, codes de sortie : 0 décision rendue (avertissement si le nombre d'éléments sort de 3 à 7) ; 1 décision courte invalide ou illisible ; aucun fichier écrit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `mermaid-diagram` : séquence, états, classes, données, ou flux simple dans un dépôt ou Obsidian.
- **Passe la main** au skill `drawio-diagram` : public technique, Word, PowerPoint ou Confluence, mise en page précise.
- **Passe la main** au skill `excalidraw-diagram` : public non technique, atelier, vue d'ensemble.
- **Passe la main** au skill `c4-architecture` : architecture logicielle à plusieurs vues ou niveaux.
- **Passe la main** au skill `urbanization-map` : cartographie fonctionnelle du SI, plan d'occupation des sols (urbanisation).
- **Passe la main** au skill `cloud-architecture` : architecture cloud (AWS, Azure, GCP, Kubernetes), réseau, PRA ou pipeline.
- **Passe la main** au skill `threat-model` : modèle de menaces STRIDE d'un schéma cloud (type menaces).

### `diagram-export`

Exporte un schéma (draw.io, Mermaid, Excalidraw, LikeC4) en PNG, SVG ou PDF pour Word, PowerPoint, Confluence ou un Markdown, ou vérifie seulement qu'il se rend. À utiliser pour intégrer un schéma dans un document ou valider sa syntaxe, pas pour convertir un document Markdown entier.

Résumé de [`contract.json`](skills/diagram-export/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Fichiers .drawio, .mmd, .mermaid, .md (blocs mermaid), .excalidraw, .c4 ou dossier LikeC4.
- **Sorties** : Images à côté de la source ou dans --out : <nom>.drawio.png, <nom>-1.png, <nom>.excalidraw.svg, un PNG par vue LikeC4 ; Rien avec --check.
- **`export.py`** : Exporte les schémas en PNG, SVG ou PDF, ou vérifie leur rendu. Mermaid et Excalidraw sont rendus dans un navigateur local avec des bibliothèques à version fixée, vérifiées par leur empreinte ; avec MYSKILLS_OFFLINE=1, rien n'est téléchargé. Rapport JSON, codes de sortie : 0 toutes les sources sont rendues ; 1 au moins une source échoue.
- **Passe la main** au skill `check-prerequisites` : un outil de rendu manque (groupe schemas).

### `doc-to-markdown`

Convertit un document PDF (y compris scanné, par OCR), DOCX, PPTX, XLSX ou une image en Markdown propre, en local, avec les images extraites dans attachments/. À utiliser pour extraire le texte, les tableaux ou les images d'un document vers du Markdown.

Résumé de [`contract.json`](skills/doc-to-markdown/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Fichiers PDF, DOCX, PPTX, XLSX, XLS, DOC, PPT ; Images PNG, JPG, GIF, BMP, TIFF, WEBP ; Dossiers.
- **Sorties** : DOSSIER/<nom>.md ; DOSSIER/attachments/<nom>-N.<ext>, liées en relatif depuis le Markdown ; DOSSIER/.myskills-tmp/<nom>-pages/page-N.png : pages à transcrire par vision, à supprimer ensuite.
- **`convert.py`** : Convertit les documents en Markdown, en local. Rapport JSON, codes de sortie : 0 tous les fichiers sont convertis ; 1 au moins un fichier a échoué (error dans son résultat, repris dans errors).
- **`validate.py`** : Vérifie un Markdown converti, ou une note Obsidian avec --obsidian. Rapport JSON, codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **`classify.py`** : Classe des documents (type, domaine, moteur conseillé) avec le modèle local Laya, ou par règles. Rapport JSON, codes de sortie : 0 tous les fichiers sont classés ; 1 au moins un fichier a échoué.
- **Passe la main** au skill `markdown-to-obsidian` : la cible est un vault Obsidian.
- **Passe la main** à l'agent `schema-designer` : un schéma en image doit devenir modifiable.

### `drawio-diagram`

Crée (à partir d'une description courte) ou modifie un schéma draw.io (.drawio), le vérifie et l'exporte en PNG, SVG ou PDF modifiables. À utiliser pour les schémas destinés à Word, PowerPoint ou Confluence, ou qui demandent une mise en page précise.

Résumé de [`contract.json`](skills/drawio-diagram/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief et description JSON du schéma : title, audience, elements (ou pages) ; Ou un .drawio existant à modifier.
- **Sorties** : <sujet>.drawio en XML clair, à côté de sa description <sujet>.json ; Après export : <sujet>.drawio.png, .svg ou .pdf ; Depuis un .drawio existant : sa description courte <sujet>.json (drawio_read.py), à éditer puis reconstruire.
- **`drawio_build.py`** : Construit le .drawio aux styles de la charte à partir de la description JSON, puis le vérifie comme check_drawio.py. Rapport JSON, codes de sortie : 0 schéma produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`check_drawio.py`** : Vérifie un fichier draw.io avant export : structure, charte, chevauchements, et lisibilité estimée sans rendu (libellé trop long pour sa forme, flèches qui se croisent, flèche sous une forme) ; dit s'il faut relire l'image exportée (review_image). Rapport JSON, codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **`drawio_read.py`** : Tire d'un .drawio existant (XML clair ou compressé) la description JSON courte de drawio_build.py : rôle de chaque forme déduit de son style, identifiants, libellés sans HTML et positions (ou grille approchée), flèches avec libellé et style ; vérifie la description contre le schéma de drawio_build.py avant de l'écrire. Le modèle édite cette description au lieu du XML. Rapport JSON, codes de sortie : 0 description écrite ; 1 fichier illisible, schéma vide, description existante sans --force ou non conforme.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.

### `excalidraw-diagram`

Crée un schéma Excalidraw au style dessiné à la main à partir d'une description simple, le rend en PNG ou SVG et le relit. À utiliser pour les publics non techniques, les ateliers (façon tableau blanc) et les vues d'ensemble.

Résumé de [`contract.json`](skills/excalidraw-diagram/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Description JSON du schéma : title, audience, elements.
- **Sorties** : <sujet>.excalidraw, à côté de sa description <sujet>.json ; Après export : <sujet>.excalidraw.png ou .svg.
- **`excalidraw_build.py`** : Construit la scène Excalidraw à partir de la description JSON. Rapport JSON, codes de sortie : 0 scène produite sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : rendre et relire l'image.

### `markdown-publish`

Transforme un Markdown (ou une note Obsidian) en fichier Word, PDF, HTML ou XWiki, schémas compris, pour SharePoint, Confluence, XWiki ou un envoi par mail, ou en présentation PowerPoint avec le skill markdown-to-pptx installé à part. Ne publie rien en ligne. À utiliser pour livrer une documentation hors du dépôt.

Résumé de [`contract.json`](skills/markdown-publish/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Markdown ou notes Obsidian, avec leurs images et schémas sources ; Modèle Word ou gabarit PowerPoint .potx (facultatif) ; Vault Obsidian (facultatif).
- **Sorties** : <nom>.docx, <nom>.html, <nom>.xwiki et ses images dans <nom>-xwiki/ ; <nom>.pptx, par le skill externe markdown-to-pptx s'il est installé ; En option : PDF, planches PNG des pages à relire dans .myskills-tmp/<nom>-apercu/.
- **`publish.py`** : Produit Word, HTML ou XWiki à partir d'un Markdown, schémas compris, sans rien publier. Rapport JSON, codes de sortie : 0 tous les documents sont produits ; 1 au moins un document a échoué.
- **`pptx_publish.py`** : Produit une présentation PowerPoint modifiable avec le skill markdown-to-pptx, installé à part et appelé par son seul contrat d'interface : vérifie le Markdown (images en PNG, JPEG ou SVG, textes alternatifs, consignes de visuel connues), lance le skill dans le dossier du Markdown, valide le plan rendu contre le contrat puis rouvre le .pptx (diapositives, images, textes alternatifs). Rapport JSON, codes de sortie : 0 présentation écrite et vérifiée ; 1 Markdown, image ou gabarit invalide, skill markdown-to-pptx introuvable (avec la consigne d'installation), rendu en échec ou présentation incohérente ; aucun .pptx laissé.
- **`make_reference.py`** (maintenance du dépôt) : Régénère references/modele.docx aux couleurs de la charte. Pas de rapport, codes de sortie : 0 modèle écrit.
- **Dépend de** `diagram-export` (`export.py`, obligatoire) : exporter en image les schémas cités par le Markdown (sources .drawio, .excalidraw, .mmd, .c4).
- **Passe la main** au skill `diagram-export` : exporter les schémas (automatique).
- **Passe la main** au skill externe `markdown-to-pptx` (installé à part, contrat `shared/external/markdown-to-pptx.contract.json`) : produire le .pptx (pptx_publish.py le lance).
- **Passe la main** à l'utilisateur : importer les fichiers dans SharePoint, Confluence ou XWiki, ou présenter le .pptx.

### `markdown-to-obsidian`

Met un fichier Markdown au format Obsidian : frontmatter, embeds d'images, wikilinks, callouts, pièces jointes copiées dans le vault. À utiliser quand la cible est un vault Obsidian.

Résumé de [`contract.json`](skills/markdown-to-obsidian/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Notes Markdown (sortie de doc-to-markdown ou existantes) ; Dossier du vault Obsidian (facultatif).
- **Sorties** : Note au format Obsidian, sur place ou dans VAULT/<dossier>/ ; Images dans le dossier de pièces jointes du vault ; Avec --move : rien ne reste dans le dossier de travail ; Avec vault_check.py --graph : graphe typé des notes (JSON node-link NetworkX).
- **`obsidianize.py`** : Met des notes au format Obsidian et les range dans le vault. Rapport JSON, codes de sortie : 0 toutes les notes sont traitées ; 1 une note est introuvable ou une image manque (missing).
- **`vault_profile.py`** : Lit le vault (lecture seule) : tags, dossiers, dossier des pièces jointes. Rapport JSON, codes de sortie : 0 profil produit ; 1 vault introuvable.
- **`vault_check.py`** : Vérifie les notes typées du vault contre l'ontologie (shared/vault-ontology.json) et exporte leur graphe typé (lecture seule). Rapport JSON, codes de sortie : 0 notes conformes (ou ontologie affichée) ; 1 vault introuvable, type inconnu, ou note hors ontologie (avec --strict : aussi un avertissement).
- **Dépend de** `doc-to-markdown` (`classify.py`, facultatif : sans lui, avertissement) : classer les documents avant la conversion (--classify).
- **Dépend de** `doc-to-markdown` (`validate.py`, facultatif : sans lui, avertissement) : valider les notes produites.
- **Vault Obsidian** : écrit les notes de type `document` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `doc-to-markdown` : valider la note avec validate.py --obsidian.
- **Passe la main** au skill `markdown-publish` : exporter la note en Word, HTML ou XWiki.

### `mermaid-diagram`

Écrit des schémas Mermaid (flux, séquence, états, classes, modèle de données) dans un Markdown ou un fichier .mmd et vérifie qu'ils se rendent. À utiliser pour la documentation dans un dépôt (README, docs/) ou Obsidian.

Résumé de [`contract.json`](skills/mermaid-diagram/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Contenu à représenter ; Description JSON d'un flowchart ou d'une séquence (mermaid_build.py --schema), ou options.json d'architecture-options et l'option retenue.
- **Sorties** : Bloc ```mermaid dans un Markdown, ou fichier .mmd.
- **`mermaid_build.py`** : Écrit un diagramme Mermaid (flowchart ou séquence) à partir d'une description JSON courte ou d'une option d'architecture-options : identifiants sûrs, libellés protégés, formes et classDef de la charte, sous-graphes, flèches synchrones ou asynchrones, blocs alt/opt/loop ; vérifie les références (avec la valeur proche) et le nombre de nœuds. Rapport JSON, codes de sortie : 0 diagramme écrit (rendu à vérifier avec diagram-export --check) ; 1 description invalide ou référence inconnue ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : --from-options : valider options.json contre son schéma et reprendre une option.
- **Passe la main** au skill `diagram-export` : vérifier le rendu (--check) ou exporter en PNG ou SVG.

### `migration-assessment`

Évalue un portefeuille d'applications pour une migration vers le cloud (ou un autre hébergement) selon les 6R : réhéberger, replateformer, refondre, racheter, retirer ou conserver, avec la raison, l'effort et le risque de chaque choix. Le script contrôle les dépendances, les retraits, l'obsolescence et l'hébergeur cible, puis calcule les vagues de migration. À utiliser pour une étude de migration, un plan de sortie d'un datacenter, une rationalisation du portefeuille applicatif ou un inventaire à trier en 6R.

Résumé de [`contract.json`](skills/migration-assessment/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON du portefeuille d'applications et de la stratégie 6R de chacune (assess_build.py --schema), tirée d'un inventaire (CSV, POS d'urbanization-map, documents) ; Facultatif : exigences.json (requirements-catalog), cité par les applications ; l'hébergeur cible (shared/providers.json).
- **Sorties** : <nom>.md : synthèse par stratégie, tableau des applications, vagues de migration, points d'attention ; <nom>.csv : une ligne par application (stratégie, effort, risque, vague) ; <nom>.waves.json : vagues de migration, reprises par transition-roadmap.
- **`assess_build.py`** : Contrôle l'évaluation 6R (dépendances connues et sans cycle, application retirée encore utilisée, refactor d'effort S, rehost d'une technologie hors support, repurchase sans cible, application critique à risque élevé sans parade, données sensibles chez un hébergeur extraterritorial, références vers les exigences) et calcule les vagues de migration selon les dépendances. Rapport JSON, codes de sortie : 0 évaluation et vagues écrites (avertissements possibles : cohérences à vérifier) ; 1 description invalide, dépendance inconnue ou en cycle, application retirée encore utilisée, hébergeur ou exigence inconnus ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `transition-roadmap` : planifier les vagues dans la feuille de route de transition (waves dans sa description).
- **Passe la main** au skill `cloud-architecture` : décrire et dessiner l'architecture cible des applications migrées.
- **Passe la main** au skill `data-protection` : des données sensibles partent chez un hébergeur soumis à des lois extraterritoriales.
- **Passe la main** au skill `solution-estimate` : chiffrer la migration à partir des efforts et des vagues.
- **Passe la main** à l'utilisateur : faire valider chaque retrait d'application et les stratégies des applications critiques.

### `mission-workspace`

Ouvre et suit un espace de travail par mission : un répertoire, un vault Obsidian unique, pour une avant-vente (documents reçus, solution, chiffrage, schémas, POS) ou une revue d'architecture (documentation et code, un dépôt par service). Crée mission.json et l'arborescence, démarre le workflow de la nature, fige les commits revus, fait le point dans le vault et contrôle la cohérence entre livrables (exigences, option retenue, chiffrage, revue). À utiliser au début d'une mission, pour savoir où en est une mission ou avant de la livrer.

Résumé de [`contract.json`](skills/mission-workspace/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Un dossier par mission : avant-vente (documents reçus, souvent des PDF) ou revue d'architecture (documentation et code, un dépôt par service) ; Facultatif : la description de la mission en JSON (nature, client, échéance, workflows, dépôts, référentiels, écarts acceptés), schéma shared/schemas/mission.schema.json.
- **Sorties** : mission.json à la racine de la mission, documents/, le vault Obsidian de la mission (et code/ pour une revue), le workflow de la nature démarré (workflow.json) ; Dans le vault : la note Mission (type mission) : workflows et étapes, dépôts et commits, référentiels, contrôles de cohérence ; Rapport : état de la mission et contrôles de cohérence entre livrables (MIS-01 à MIS-09).
- **`mission.py`** : Ouvre une mission dans un dossier (mission.json, documents/, vault, code/ pour une revue, workflow de sa nature lancé avec son vault ; refusé dans une mission existante), ajoute ses dépôts et fige leur commit, fait le point (workflows, étape courante, dépôts, référentiels) et contrôle sans modèle la cohérence entre livrables : exigence indispensable hors de l'option retenue, composant non chiffré, exigence non fonctionnelle indispensable sans scénario de revue, livrable validé modifié, revue ou chiffrage d'une autre option, dépôt absent ou hors du commit figé, référentiel introuvable. Réécrit la note Mission du vault, vérifiée contre l'ontologie. Rapport JSON, codes de sortie : 0 commande appliquée (check : aucun contrôle ouvert au niveau de --fail-on) ; 1 mission introuvable ou invalide (chemin, valeur hors liste, chemin hors de la mission), mission dans une mission, workflow non démarré, ou check avec un contrôle ouvert au niveau de --fail-on.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `decision-log` (`journal.py`, obligatoire) : démarrer le workflow de la mission (init) et lire son état (status).
- **Vault Obsidian** : écrit les notes de type `mission` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** à l'agent `architecture-workflow` : la mission est ouverte : dérouler son workflow (architecture pour une avant-vente, revue-dossier pour une revue).
- **Passe la main** à l'agent `architecture-reviewer` : revue d'architecture de la mission, dépôts de code compris.
- **Passe la main** à l'utilisateur : un contrôle ouvert demande une décision : corriger le livrable, ou accepter l'écart avec sa raison (accept).

### `requirements-catalog`

Extrait des documents d'un projet (cahier des charges, comptes rendus, spécifications convertis en Markdown) le catalogue des exigences fonctionnelles et non fonctionnelles, avec identifiants stables, priorité, mesure et citation de la source vérifiée par script, puis l'exporte en Markdown et CSV. À utiliser pour recenser, tracer ou exporter les exigences d'un projet.

Résumé de [`contract.json`](skills/requirements-catalog/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Documents en Markdown (sortie de doc-to-markdown) dans un dossier sources ; Description JSON des exigences : title, sources, requirements (id repris des documents ou EF-/ENF-, nature, title, text, priority, category ou domain, metric, sources avec citation, questions, status), ignored, glossary (terme, définition, synonymes).
- **Sorties** : <nom>.md : catalogue pour la revue (exigences fonctionnelles, non fonctionnelles, questions, exigences déduites, retirées, phrases écartées, glossaire avec les exigences qui emploient chaque terme) ; <nom>.csv : même catalogue pour un tableur (séparateur ;, UTF-8 avec BOM).
- **`req_build.py`** : Vérifie chaque citation dans son document et en donne la ligne, repère les phrases des sources reprises par aucune exigence (phrases normatives par la regex ; avec --candidates et son tri par un modèle léger, les phrases qu'il tient pour des exigences ; avec --laya, celles du modèle local Laya et ses désaccords sur la catégorie), signale une exigence renumérotée alors que sa source porte un identifiant, doublons et exigences non mesurables, puis écrit le catalogue en Markdown et en CSV ; avec --draft, écrit d'abord le brouillon de la description (une exigence par phrase normative des sources, citation exacte, identifiant du document, nature, catégorie, priorité et mesure déduites) que le modèle trie. Rapport JSON, codes de sortie : 0 catalogue produit sans erreur (avertissements possibles) ; 1 description invalide, citation introuvable ou autre erreur ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`req_laya.py`** : Pose au modèle local Laya les questions fermées de req_build.py --laya (la phrase est-elle une exigence, quelle catégorie) ; lancé par req_build.py dans son propre environnement. Rapport JSON, codes de sortie : 0 toutes les questions posées (une phrase sans réponse est un avertissement) ; 1 description invalide ou Laya indisponible.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `doc-to-markdown` : les documents ne sont pas encore en Markdown.
- **Passe la main** au skill `architecture-options` : le catalogue est validé : proposer des architectures.
- **Passe la main** au skill `decision-log` : noter les choix (exigence déduite, phrase écartée, priorité) et soumettre le catalogue à la revue.

### `solution-estimate`

Chiffre une solution à partir du catalogue d'exigences et de l'option d'architecture retenue : charge de réalisation par lot, phase et profil (estimation à trois points, fourchette calculée), pilotage et provision, coût d'infrastructure, maintenance et exploitation, coût total sur plusieurs années, budget tenu ou dépassé, le tout en trois hypothèses de production comparées (sans IA, avec IA, dev IA natif), et un plan de charge par tâche (complexité, jours, heures), seul produit sans taux journaliers. Les calculs et les contrôles de couverture sont faits par script. À utiliser pour chiffrer un projet, estimer une charge, un budget, un coût d'infrastructure, un coût total de possession ou le gain d'un développement assisté par l'IA.

Résumé de [`contract.json`](skills/solution-estimate/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Options d'architecture (options.json d'architecture-options), avec la décision ou la recommandation ; Description JSON du chiffrage : title, context, requirements, architecture, option, currency, horizon, hosting (provider, qualifications, refs), providers, rates (facultatif), hours_per_day, work (id, name, phase, component, refs, effort, complexity, ai), overheads, contingency, infra (id, name, component, environment, kind, provider, quantity, unit_cost, period, basis), run, scenarios (avec-ia, ia-natif : factors, gain_uncertainty, setup_percent, tooling_per_day, run_factor, contingency, basis), budget, assumptions, exclusions ; Catalogue des hébergeurs (shared/providers.json, commun aux skills cloud : AWS, Azure, Google Cloud, OVHcloud, Cloud Temple, Outscale, S3NS, Bleu, NumSpot, Scaleway, interne ; juridiction, qualifications SecNumCloud, HDS), complété par un catalogue propre au projet ; Hypothèses de production par défaut (references/hypotheses-ia.json : facteurs par phase, incertitude, adoption, outillage IA, run, avec leurs sources), lues par le script ; Règles de complétude (postes attendus) : references/postes-attendus.json, complétées par celles de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json) et de la mission (references.regles de mission.json), schéma shared/schemas/rules.schema.json.
- **Sorties** : <nom>.md : chiffrage pour la revue (synthèse, budget, hypothèses sans IA, avec IA et IA natif, lots, phases, profils, infrastructure, run, coût total par année, couverture, hypothèses, exclusions) ; <nom>.csv : lignes détaillées (lots, pilotage, infrastructure, run), séparateur point-virgule, relu par le script ; <nom>.hypotheses.csv : lignes de chaque hypothèse de production (sans IA, avec IA, IA natif : lots avec leur facteur, adoption, pilotage, outillage IA, run), relu par le script ; <nom>.charges.md et <nom>.charges.csv : plan de charge sans montant (chaque tâche avec sa complexité, ses jours et ses heures, sans IA, avec IA et IA natif ; par phase et par profil), relu par le script ; seuls produits sans rates.
- **`estimate_build.py`** : Vérifie les profils, les composants de l'option chiffrée (options.json, architecture-options) et les exigences (exigences.json, requirements-catalog), contrôle l'hébergeur de chaque ligne d'infrastructure contre le catalogue des hébergeurs et les qualifications exigées (SecNumCloud, HDS...), calcule la charge espérée de chaque lot (estimation à trois points), la fourchette P10-P90 de la réalisation, le pilotage, la provision, l'infrastructure par an et ponctuelle, le run et le coût total sur l'horizon, puis les mêmes montants pour trois hypothèses de production (sans IA, avec IA, dev IA natif : facteur de charge par phase ou par lot, incertitude élargie, adoption, licences et jetons, run) ; signale les exigences qu'aucun lot ne porte, les composants sans chiffrage, les postes attendus absents (règles de complétude selon les exigences et les composants : tests de sécurité et de charge, hors production, réseau, recette, mise en production, formation, sauvegarde, supervision, intégration, reprise de données), les estimations très incertaines et les dépassements de budget ; écrit le chiffrage, son CSV et celui des hypothèses, ainsi que le plan de charge sans montant (tâche, complexité, jours, heures) ; sans taux journaliers, ce plan de charge seul, puis relit les CSV pour vérifier les totaux ; avec --draft, écrit le brouillon de la description (lots par composant et transverses, valeurs usuelles, budget, infrastructure de cloud-cost) pour que le modèle n'écrive que les charges. Rapport JSON, codes de sortie : 0 chiffrage produit et CSV vérifié (avertissements possibles) ; 1 description invalide, profil, composant ou exigence inconnu, estimation hors ordre, CSV qui ne redonne pas les totaux ; aucun fichier produit sauf dans ce dernier cas.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json contre son schéma.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Vault Obsidian** : écrit les notes de type `chiffrage`, `lot` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `decision-log` : noter les hypothèses de chiffrage, soumettre le chiffrage à la revue.
- **Passe la main** à l'agent `document-publisher` : le chiffrage doit être livré en Word, HTML ou XWiki.
- **Passe la main** au skill `architecture-options` : le coût chiffré contredit la note du critère coût d'une option : revoir sa note.

### `threat-model`

Prépare le modèle de menaces STRIDE d'une architecture décrite en JSON (celle des schémas cloud) : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable avec sa mesure et son statut à compléter. À utiliser pour une analyse de sécurité d'une architecture cloud, d'une option d'architecture ou d'une infrastructure existante.

Résumé de [`contract.json`](skills/threat-model/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON de l'architecture, celle de cloud_build.py (skill cloud-architecture) : groupes, services typés, flux avec protocole ; Ou la description cloud d'une option d'architecture-options (schemas/option-<id>.cloud.json).
- **Sorties** : <sujet>.threats.md : frontières de confiance, flux qui les traversent, une menace type par catégorie STRIDE applicable, mesure type ; après threat_review.py, menaces précisées, mesures retenues, statuts et menaces écartées avec leur raison ; <sujet>.threats.json : les mêmes menaces en données, auxquelles le modèle répond par un fichier de décisions.
- **`stride.py`** : Prépare le modèle de menaces STRIDE à partir de la même description : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable, avec mesure type et statut à compléter ; propose comme traité ce que la description prouve déjà (flux chiffré), et donne à chaque menace sa nature, son type, son flux et son chiffrement pour les règles de threat_review.py. Rapport JSON, codes de sortie : 0 modèle produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`threat_review.py`** : Reporte dans le modèle STRIDE les décisions du modèle sur les menaces, données dans un court fichier JSON : règles groupées (catégorie, nature, type, élément, flux traversant ou chiffré) et décisions par menace (statut, mesure retenue, menace précisée, raison), plus les propositions de stride.py ; vérifie chaque décision et règle, réécrit <sujet>.threats.md depuis <sujet>.threats.json, compte les menaces par statut, par règle et celles encore à analyser. Rapport JSON, codes de sortie : 0 décisions reportées dans le modèle ; 1 décisions invalides (menace inconnue, mesure ou raison manquante, identifiant décalé) ou modèle illisible.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `cloud-architecture` (`cloud_build.py`, obligatoire) : lire la description comme le schéma : types de services, groupes, frontières et numéros de flux F1, F2....
- **Vault Obsidian** : écrit les notes de type `modele-menaces` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `cloud-architecture` : schéma des menaces (cloud_build.py --view threats), mêmes numéros de flux.
- **Passe la main** au skill `well-architected-review` : contrôler aussi les piliers Well-Architected du fournisseur.
- **Passe la main** à l'utilisateur : compléter avec lui les mesures retenues et les statuts des menaces.

### `transition-roadmap`

Construit la feuille de route de transition d'une architecture actuelle vers la cible : chantiers et jalons avec durées et prédécesseurs, vagues de migration reprises de migration-assessment, dates, marges et chemin critique calculés par script, échéance contrôlée, diagramme de Gantt Mermaid et CSV. À utiliser pour un plan de transition, une trajectoire, un planning de migration ou un schéma directeur à phaser.

Résumé de [`contract.json`](skills/transition-roadmap/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Description JSON des chantiers et jalons de la transition (roadmap_build.py --schema) ; Facultatif : les vagues de migration (<nom>.waves.json de migration-assessment).
- **Sorties** : <nom>.md : synthèse (dates, durée, chemin critique), tableau des chantiers avec marges, diagramme de Gantt Mermaid ; <nom>.csv : une ligne par chantier (dates, durée, lot, responsable, critique).
- **`roadmap_build.py`** : Reprend les vagues de migration comme chantiers, contrôle les prédécesseurs (connus, sans cycle), calcule les dates au plus tôt, les marges, le chemin critique et la fin du programme, signale l'échéance dépassée et les chantiers trop longs, écrit le tableau et le diagramme de Gantt Mermaid. Rapport JSON, codes de sortie : 0 feuille de route écrite (avertissements possibles : échéance dépassée, chantier à découper) ; 1 description invalide, prédécesseur inconnu ou en cycle, fichier des vagues illisible, aucun chantier ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `migration-assessment` : les vagues de migration ne sont pas encore calculées.
- **Passe la main** au skill `diagram-export` : le diagramme de Gantt doit être rendu en image (export.py <nom>.md).
- **Passe la main** à l'agent `document-publisher` : la feuille de route doit être livrée en Word, PowerPoint ou HTML.
- **Passe la main** à l'utilisateur : arbitrer une échéance dépassée : raccourcir le chemin critique, ajouter des moyens ou décaler.

### `urbanization-map`

Dessine le plan d'occupation des sols (POS) d'un système d'information, ou carte d'urbanisation : zones, quartiers, îlots et applications rangées dedans, colorées par statut, en draw.io et PNG. Fait aussi la carte des capacités TOGAF (Business Capability Map) avec les applications posées dessus. À utiliser pour une cartographie fonctionnelle du SI, technique ou pour la direction, à partir d'une liste ou d'un inventaire CSV.

Résumé de [`contract.json`](skills/urbanization-map/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief : public et destination ; Description JSON du plan : title, audience, detail, vocabulary, zones (quartiers, ilots, apps) ; ou inventaire CSV, ou note Markdown avec son tableau (zone, quartier, ilot, application, statut) ; Pour pos_impact.py : le POS existant et des options d'architecture avec leur placement (options.json d'architecture-options).
- **Sorties** : <sujet>.drawio en XML clair, à côté de sa description <sujet>.json ou de l'inventaire .csv ; Après export : <sujet>.drawio.png (une image par page), .svg ou .pdf ; Avec pos_impact.py : schemas/pos-option-<id>.json, le POS cible de chaque option, à construire avec pos_build.py.
- **`pos_build.py`** : Construit le plan d'occupation des sols en draw.io (mise en page, styles de la charte, titre, légende, pages de zoom), puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON, codes de sortie : 0 plan produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`pos_impact.py`** : Situe des options d'architecture dans le POS existant : vérifie le placement de chaque option (noms connus du POS, zone et quartier d'une nouvelle application), compte créations, évolutions, remplacements, réutilisations, redondances et flux entre zones, puis écrit le POS cible de chaque option pour pos_build.py. Lit le POS en JSON, CSV ou note Markdown, ou dans le vault du workflow (vault:<chemin>). Sert aussi de module à options_build.py. Rapport JSON, codes de sortie : 0 impacts calculés et POS cibles écrits (avertissements possibles : redondance, option sans placement) ; 1 description invalide, POS illisible ou vide, application ou quartier inconnu du POS ; aucun fichier écrit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `drawio-diagram` (`check_drawio.py`, facultatif : sans lui, avertissement) : vérifier le .drawio produit.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main, ou dessiner les flux entre applications (cartographie applicative).

### `well-architected-review`

Contrôle une architecture cloud décrite en JSON contre l'AWS Well-Architected Framework, l'Azure Well-Architected Framework et le Google Cloud Well-Architected Framework (fiabilité, sécurité, opérations, performances, coûts, durabilité) et contre les conventions de schéma des fournisseurs. À utiliser dès la définition d'une architecture (piliers) puis sur le schéma (conventions).

Résumé de [`contract.json`](skills/well-architected-review/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Description JSON de l'architecture, celle de cloud_build.py (skill cloud-architecture) ; à la définition, la description cloud d'une option (schemas/option-<id>.cloud.json d'architecture-options) ; Facultatif : accept, les écarts acceptés avec leur raison.
- **Sorties** : <sujet>.wa.md : synthèse par pilier, constats (règle, pilier, gravité, élément, correction, référence du cadre), points hors du schéma.
- **`wa_check.py`** : Contrôle la même description contre l'AWS Well-Architected Framework, l'Azure Well-Architected Framework et le Google Cloud Well-Architected Framework (fiabilité, sécurité, excellence opérationnelle, performances, coûts, durabilité) et contre les conventions de schéma des fournisseurs (imbrication région, VPC/VNet, zone, sous-réseau ; icônes officielles) : un constat par règle enfreinte, avec pilier, gravité, élément, correction et référence du cadre ; écrit <sujet>.wa.md. Rapport JSON, codes de sortie : 0 revue écrite, aucun constat non accepté au seuil --fail-on ; 1 description illisible, erreur, ou constat non accepté au seuil --fail-on ; le rapport et <sujet>.wa.md sont tout de même produits sauf erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `cloud-architecture` (`cloud_build.py`, obligatoire) : lire la description comme le schéma : types de services, groupes, frontières et numéros de flux F1, F2....
- **Vault Obsidian** : écrit les notes de type `revue-well-architected`, `constat` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `cloud-architecture` : corriger la description puis reconstruire le schéma.
- **Passe la main** au skill `threat-model` : préparer aussi le modèle de menaces STRIDE.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept.
