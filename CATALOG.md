# Catalogue des agents et des skills

Fichier généré par `scripts/build.py` : ne pas le modifier à la main. Les
contrats qui font foi sont en JSON : `skills/<nom>/contract.json`,
`src/agents/<nom>.contract.json` et les schémas de `shared/schemas/`. La
version machine de ce catalogue est [`catalog.json`](catalog.json).

## Messages entre agents

- Message de passage : [`shared/schemas/handoff.schema.json`](shared/schemas/handoff.schema.json).
  Champs : `agent` (document-extractor | schema-designer | document-publisher | architecture-workflow | architecture-reviewer), `objective` (texte), `files` (liste), `audience` (technique | non technique), `destination` (markdown | obsidian | word | powerpoint | pdf | confluence | sharepoint | xwiki | html), `output` (texte) ; facultatifs : `constraints`.
- Rapport final : [`shared/schemas/agent-report.schema.json`](shared/schemas/agent-report.schema.json).
  Champs : `agent` (document-extractor | schema-designer | document-publisher | architecture-workflow | architecture-reviewer), `status` (ok | partiel | echec), `files` (liste), `tools` (texte), `level` (simple | moyen | complexe), `corrections` (liste), `todo` (liste), `next` (objet).

## Agents

### `architecture-reviewer`

Revoit une architecture logicielle ou solution (revue ATAM : scénarios de qualité, risques, compromis, décisions, traçabilité des exigences, code comparé à l'architecture avec graphify en local) et la sécurité et la qualité d'une architecture cloud décrite en JSON : modèle de menaces STRIDE et revue Well-Architected d'AWS, Azure et Google Cloud (piliers et conventions de schéma). Trie les constats, propose les corrections, rend un avis et fait accepter les écarts par l'utilisateur. Adapte l'effort de chaque action pour limiter les coûts.

**Skills** : `check-prerequisites`, `architecture-review`, `threat-model`, `well-architected-review`, `cloud-architecture`, `diagram-export`, `decision-log`, `agent-handoff`

Généré depuis `src/agents/architecture-reviewer.contract.json`, qui fait foi.

- **Niveau** : complexe (modèle puissant, `shared/models.json`).
- **Reçoit** : Pour une revue d'architecture logicielle ou solution : l'option d'architecture-options (options.json et son id) ou les composants et flux, le catalogue d'exigences, les décisions (ADR) et, s'il existe, le dossier du code ; La description JSON d'une architecture cloud (celle de cloud_build.py) : schéma existant, option d'architecture-options (schemas/option-<id>.cloud.json) ou description tirée du code (iac_import.py) ; Ce que l'utilisateur veut : revue d'architecture, modèle de menaces STRIDE, revue Well-Architected des piliers, conventions du schéma, ou tout ; Les contraintes connues (sécurité, conformité, écarts déjà acceptés et leur raison).
- **Produit** : <sujet>.revue.md : revue d'architecture, avis calculé, arbre d'utilité évalué, constats, risques, compromis, décisions, traçabilité et conformité du code ; <sujet>.threats.md : modèle de menaces STRIDE relu, menaces gardées et précisées, mesures et statuts proposés ; <sujet>.wa.md : revue Well-Architected, constats ouverts ou acceptés avec leur raison ; Si demandé, le schéma des menaces (cloud_build.py --view threats) et son PNG.
- **Ne fait jamais** : Accepter un écart (accept) sans la raison donnée par l'utilisateur ; Évaluer un scénario de qualité sans dire pourquoi, ou confier les documents à graphify avec un modèle autre que celui du harness ou un modèle local ; Modifier le schéma ou la description d'un autre agent sans le dire ; Envoyer une description ou un schéma à un service en ligne.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `schema-designer` | le schéma doit être corrigé ou complété après la revue (composant manquant, flux à chiffrer) | la description JSON corrigée ; les constats qui la justifient ; la destination du schéma |
| `architecture-workflow` | la revue est faite pour une étape de workflow : rendre la main pour la soumission | les fichiers .revue.md, .threats.md et .wa.md ; les constats de gravité haute restants ; le dossier du workflow |
| `document-publisher` | la revue doit être livrée en Word, HTML ou XWiki | les fichiers .revue.md, .threats.md et .wa.md ; l'outil cible |

### `architecture-workflow`

Déroule un workflow prédictible des documents d'un projet jusqu'à l'architecture : conversion des documents, catalogue des exigences fonctionnelles et non fonctionnelles avec sources, 2 ou 3 options d'architecture comparées, schémas associés. Suit aussi d'autres workflows décrits en JSON, comme du code d'infrastructure jusqu'au schéma cloud et au modèle de menaces. S'arrête après chaque étape pour la revue de l'utilisateur et trace chaque choix et décision dans un journal.

**Skills** : `check-prerequisites`, `decision-log`, `agent-handoff`, `doc-to-markdown`, `markdown-to-obsidian`, `requirements-catalog`, `architecture-options`, `urbanization-map`, `well-architected-review`, `drawio-diagram`, `cloud-architecture`, `diagram-export`, `architecture-deck`, `threat-model`

Généré depuis `src/agents/architecture-workflow.contract.json`, qui fait foi.

- **Niveau** : moyen (modèle standard, `shared/models.json`).
- **Reçoit** : Un dossier de projet contenant documents/ : cahiers des charges, comptes rendus, spécifications (PDF, Office, Markdown, images) ; Avec le workflow architecture, le POS du SI existant (plan d'occupation des sols, JSON ou CSV de urbanization-map), pour situer la solution dans l'architecture globale ; Le vault Obsidian qui sert de mémoire partagée ; À chaque porte de revue, la réponse de l'utilisateur : validation ou retour.
- **Produit** : sources/*.md : les documents en Markdown ; exigences.json, exigences.md, exigences.csv : catalogue des exigences fonctionnelles et non fonctionnelles, sources vérifiées ; options.json, options.md : 2 ou 3 options comparées et recommandation ; decision.json et adr-architecture.md : le choix de l'utilisateur ; schemas/architectures.drawio et un PNG par option ; avec un POS, le POS cible de chaque option (schemas/pos-option-<id>.drawio) ; workflow.json et journal.md : état des étapes, choix, questions, retours et validations ; Dans le vault Obsidian, mémoire partagée : une note par exigence, option et décision, l'ADR et une note d'index, reliées par des wikilinks.
- **Ne fait jamais** : Démarrer une étape avant la validation explicite de la précédente par l'utilisateur ; Valider une étape à la place de l'utilisateur ; Modifier les documents d'origine de documents/ ; Écrire workflow.json, journal.md, les catalogues Markdown ou le XML draw.io à la main.
- **Passe la main** :

| Agent | Quand | À transmettre |
| --- | --- | --- |
| `document-extractor` | des documents demandent une transcription par vision page à page (scans, schémas en image) en lot | les documents ; la cible markdown et le dossier sources/ |
| `schema-designer` | l'utilisateur veut pour l'option retenue un schéma C4, cloud aux icônes officielles ou réseau | options.md et options.json ; l'option retenue et ses noms de composants ; le dossier schemas/ ; la note de l'option dans le vault |
| `document-publisher` | le dossier d'architecture doit être livré en Word, HTML, XWiki ou présenté en PowerPoint | exigences.md, options.md, adr-architecture.md et les PNG, ou presentation.md (deck_build.py, skill architecture-deck) pour PowerPoint ; l'outil cible ; le gabarit .potx de la marque, s'il est connu |
| `architecture-reviewer` | une revue d'architecture (ATAM, traçabilité, code comparé à l'architecture), un modèle de menaces STRIDE ou une revue Well-Architected est demandé, pour l'option retenue ou à l'étape menaces d'un workflow | options.json et l'option retenue, exigences.json et adr-architecture.md pour une revue d'architecture ; la description JSON cloud (schemas/option-<id>.cloud.json ou schemas/architecture.json) ; le dossier schemas/ ; la note de l'option dans le vault |

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

## Skills

### `agent-handoff`

Valide un message de passage entre agents ou le rapport final d'un agent (JSON Schema, fichiers cités présents) et le note au journal d'un workflow. À utiliser par tout agent avant de passer la main à un autre ou de rendre son rapport final.

Résumé de [`contract.json`](skills/agent-handoff/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier de travail, ou dossier d'un workflow (workflow.json) ; Un message de passage (shared/schemas/handoff.schema.json) ou un rapport final d'agent (shared/schemas/agent-report.schema.json), en JSON.
- **Sorties** : Aucun fichier ; dans un dossier de workflow, une entrée « passage » ou « rapport » au journal (workflow.json, journal.md).
- **`check_message.py`** : Valide un message de passage ou un rapport final d'agent contre son schéma, vérifie que chaque fichier cité existe et, dans un dossier de workflow, le note au journal (skill decision-log). Rapport JSON, codes de sortie : 0 message conforme, fichiers présents (et tracé au journal s'il y a un workflow) ; 1 message illisible, non conforme à son schéma ou fichier cité introuvable.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : noter le message au journal d'un workflow.
- **Passe la main** à l'utilisateur : l'outil ne permet pas d'appeler l'agent visé : lui donner le message et l'agent à lancer.

### `architecture-deck`

Assemble la présentation d'un dossier d'architecture (besoin, exigences, options notées, schémas, décision, couverture) depuis les étapes déjà validées d'un workflow, sans rien rédiger, au format du skill externe markdown-to-pptx. À utiliser pour présenter un choix d'architecture en PowerPoint à un comité.

Résumé de [`contract.json`](skills/architecture-deck/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier d'un workflow d'architecture aux étapes validées : options.json, exigences.json (et son glossaire), decision.json, PNG des schémas déjà exportés.
- **Sorties** : presentation.md : présentation du dossier (besoin, options, décision) au format du skill externe markdown-to-pptx, schémas exportés compris ; chaque donnée n'y figure qu'une fois.
- **`deck_build.py`** : Assemble la présentation du dossier à partir des étapes validées, sans rien demander au modèle : options.json (validé contre le schéma d'options_build.py), le catalogue d'exigences et son glossaire, decision.json, les PNG des schémas déjà exportés. Mêmes scores et contrôles qu'options_build.py ; une diapositive par information (chiffres clés, exigences indispensables, glossaire, notes par critère en graphique, scores, écarts, comparaison, un schéma par option, décision, couverture par l'option retenue, questions ouvertes), le détail dans les notes de l'orateur. Rapport JSON, codes de sortie : 0 presentation.md écrit ; 1 options.json, decision.json ou catalogue illisible ou invalide (erreurs avec leur chemin) ; aucun fichier écrit.
- **Dépend de** `architecture-options` (`options_build.py`, obligatoire) : mêmes scores, contrôles et schéma d'options.json que la comparaison validée.
- **Passe la main** au skill `markdown-publish` : produire le .pptx de presentation.md avec pptx_publish.py (skill externe markdown-to-pptx).

### `architecture-options`

Propose et compare 2 ou 3 options d'architecture à partir d'un catalogue d'exigences : écarts de couverture, notes par critère justifiées, score pondéré et rang calculés par script, recommandation, puis ADR de la décision et un schéma draw.io par option. À utiliser pour proposer des architectures, comparer des scénarios ou documenter un choix d'architecture.

Résumé de [`contract.json`](skills/architecture-options/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Facultatif : le POS existant du SI (JSON ou CSV de urbanization-map, ou note Markdown avec tableau), dans le dossier ou dans le vault Obsidian du workflow (vault:<chemin>) ; Description JSON des options : title, context, audience, requirements, pos, criteria, options (id, name, summary, components, flows, gaps, placement, wa_accept, scores, score_notes, pros, cons, risks), recommendation, decision ; Après la revue : decision.json, le choix de l'utilisateur (option, by, why, date, refs).
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

### `architecture-review`

Revue d'une architecture logicielle ou solution à la manière d'ATAM : scénarios de qualité évalués, risques, points de sensibilité, compromis et décisions, contrôle mécanique de la structure (cycles, base partagée, couches, chaîne synchrone, dépendance externe, point unique de défaillance) et de la traçabilité des exigences, avis calculé. Peut comparer le code à l'architecture avec graphify (analyse locale) et intégrer les piliers Well-Architected d'une option cloud. À utiliser pour revoir, auditer ou valider une architecture, une option retenue ou un dossier d'architecture.

Résumé de [`contract.json`](skills/architecture-review/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON de la revue (revue.json) : composants, flux, couches, scénarios de qualité, risques, points de sensibilité, compromis, décisions ; ou les composants et flux d'une option d'architecture-options (source) ; Facultatif : le catalogue d'exigences (exigences.json de requirements-catalog), pour la traçabilité ; Facultatif : la description cloud de la même architecture (schemas/option-<id>.cloud.json), pour les piliers Well-Architected ; Facultatif : le code source, ou le graph.json déjà produit par graphify, pour comparer le code à l'architecture ; Facultatif : accept, les écarts acceptés avec leur raison.
- **Sorties** : <sujet>.revue.md : avis, synthèse par axe, arbre d'utilité (scénarios de qualité et leur évaluation), constats, risques, points de sensibilité et compromis, décisions, traçabilité des exigences, conformité du code, points à vérifier hors de la description.
- **`arch_review.py`** : Contrôle une architecture logicielle ou solution décrite en JSON, à la manière d'une revue ATAM : structure (cycles de dépendances synchrones, base partagée, couches, composant pivot, chaîne synchrone longue, dépendance synchrone à un système externe, point unique de défaillance), traçabilité des exigences (exigence indispensable sans composant ni décision, exigence non fonctionnelle sans scénario de qualité), scénarios de qualité (non satisfaits ou à risque sans risque noté, sans mesure), décisions et risques ; avec une description cloud, les piliers Well-Architected (wa_check.py de well-architected-review) ; avec le code, dépendances du code absentes de l'architecture et cycles entre composants, à partir du graphe de graphify (skill externe : code analysé en local ; documents, si demandés, lus par le modèle du harness ou un modèle local). Calcule l'avis et écrit <sujet>.revue.md. Rapport JSON, codes de sortie : 0 revue écrite, aucun constat non accepté au seuil --fail-on ; 1 description illisible, référence inconnue, graphify manquant ou en échec, ou constat non accepté au seuil --fail-on ; sauf erreur, le rapport et <sujet>.revue.md sont tout de même produits.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et en reprendre les composants et les flux de l'option revue.
- **Dépend de** `well-architected-review` (`wa_check.py`, facultatif : sans lui, avertissement) : piliers Well-Architected de la description cloud (cloud).
- **Passe la main** au skill externe `graphify` (installé à part, contrat `shared/external/graphify.contract.json`) : comparer le code à l'architecture : le script lance graphify extract sur code.root (--code-only par défaut, ou documents lus par le modèle du harness ou Ollama avec semantic) et lit le graphe.
- **Passe la main** au skill `architecture-options` : un constat demande de changer l'option (composant, flux, écart) : corriger options.json puis relancer.
- **Passe la main** au skill `well-architected-review` : revue Well-Architected complète d'une architecture cloud, conventions du schéma comprises.
- **Passe la main** au skill `threat-model` : analyse des menaces STRIDE de l'architecture revue.
- **Passe la main** au skill `decision-log` : dans un workflow : noter les écarts acceptés et soumettre la revue.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept ; un risque attend un responsable.

### `c4-architecture`

Modélise une architecture logicielle selon le modèle C4 (contexte, conteneurs, composants) avec LikeC4, valide le modèle et exporte une image par vue. À utiliser pour les schémas d'architecture.

Résumé de [`contract.json`](skills/c4-architecture/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Code, configuration ou description de l'architecture.
- **Sorties** : Dossier LikeC4 : specification.c4 et model.c4 ; Un PNG par vue (après export).
- **Scripts** : aucun ; la validation passe par le skill suivant.
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
- **Entrées** : Décision de diagram-brief : public et destination ; Description JSON de l'architecture : title, provider, view, items (groupes imbriqués et services typés), flows, objectives ; ou du code d'infrastructure (Terraform, docker-compose, manifestes Kubernetes) que iac_import.py traduit en description.
- **Sorties** : <sujet>.drawio en XML clair, avec les icônes officielles AWS, Azure, GCP ou Kubernetes, à côté de sa description <sujet>.json ; Vue network (ou --matrix) : <sujet>.flows.md, la matrice des flux ; Après export : <sujet>.drawio.png (une image par page), .svg ou .pdf.
- **`cloud_build.py`** : Construit le schéma draw.io (mise en page des groupes imbriqués, icônes officielles livrées dans draw.io, flux, titre, RPO/RTO, légende), puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON, codes de sortie : 0 schéma produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`iac_import.py`** : Écrit la description de cloud_build.py depuis le code d'infrastructure : ressources Terraform (AWS, Azure, Google), services docker-compose et manifestes Kubernetes deviennent services typés, réseaux et namespaces des groupes, références et dépendances des flux ; la description est validée contre le schéma d'entrée de cloud_build.py et construite à blanc avant d'être écrite. Rapport JSON, codes de sortie : 0 description écrite, conforme et construite sans erreur ; 1 source introuvable ou format non reconnu, aucune ressource reconnue, ressource en double, ou description produite rejetée par cloud_build.py ; rien n'est écrit.
- **Dépend de** `drawio-diagram` (`check_drawio.py`, facultatif : sans lui, avertissement) : vérifier le .drawio produit.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main.
- **Passe la main** au skill `mermaid-diagram` : diagramme de séquence des appels entre services pour un parcours.
- **Passe la main** au skill `threat-model` : modèle de menaces STRIDE de l'architecture décrite (même description JSON).
- **Passe la main** au skill `well-architected-review` : revue Well-Architected des piliers ou des conventions de schéma (même description JSON).

### `decision-log`

Tient l'état d'un workflow à étapes avec portes de revue humaine et trace chaque choix, hypothèse, question, retour et validation dans un journal (workflow.json et journal.md). Une étape ne démarre qu'après validation des précédentes ; un fichier validé puis modifié est détecté. À utiliser pour piloter un workflow prédictible où l'utilisateur relit chaque étape et où toutes les décisions doivent être tracées.

Résumé de [`contract.json`](skills/decision-log/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier du workflow ; Commande : init, start, log, submit, review ou status, avec l'étape, le texte et les références (exigences, options, entrées) ; Facultatif : un vault Obsidian, mémoire partagée entre agents, sessions et utilisateur.
- **Sorties** : workflow.json : étapes dans l'ordre (d'une définition JSON : workflows/architecture.json, workflows/cloud-existant.json ou fournie), statut, empreintes SHA-256 des fichiers soumis, entrées du journal ; journal.md : version lisible (étapes, décisions et revues, questions), réécrite à chaque commande ; Avec un vault Obsidian : VAULT/<dossier>/ avec une note d'index, Exigences/EF-001.md..., Glossaire/<terme>.md..., Options/Option A.md..., Décisions/D-001.md..., ADR architecture.md, Étapes/<étape>.md avec ses livrables intégrés (copies dans Fichiers/).
- **`journal.py`** : Fait respecter l'ordre des étapes et les portes de revue (démarrage seulement après validation des étapes précédentes, validation seulement d'une étape en revue dont les fichiers n'ont pas changé, retour qui remet à reprendre l'étape et les suivantes), note chaque choix, hypothèse, question, soumission, retour et validation, et détecte un fichier validé modifié depuis. Avec un vault, réécrit après chaque commande la mémoire partagée dans Obsidian (vault_sync.py). Rapport JSON, codes de sortie : 0 commande appliquée ; 1 commande ou message refusé (étape inconnue, ordre ou porte de revue non respectés, livrable validé modifié, fichier introuvable, définition ou workflow.json non conforme à son schéma) ; workflow.json inchangé.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`vault_sync.py`** : Écrit la mémoire partagée du workflow dans un vault Obsidian : une note par exigence, option et entrée du journal, une note par étape soumise avec ses livrables (images et Markdown copiés dans Fichiers/ et intégrés), une note d'index et l'ADR, reliées par des wikilinks et typées selon l'ontologie du vault (type, propriétés, relations typées, tags normalisés, vérifiés avant l'écriture), depuis workflow.json et les livrables que la définition nomme dans memory ; supprime les notes générées qui ne correspondent plus à rien et vérifie que chaque lien pointe vers une note. Lancé par journal.py après chaque commande quand le vault est connu. Rapport JSON, codes de sortie : 0 notes écrites, tous les liens résolus ; 1 workflow.json ou vault introuvable, fichier lu non conforme au schéma du skill qui l'écrit (workflow.json, exigences.json, options.json, decision.json), note hors ontologie du vault (rien n'est écrit), ou lien cassé.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider le catalogue d'exigences avant d'en écrire les notes.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et decision.json avant d'en écrire les notes.
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
- **Sorties** : <sujet>.drawio en XML clair, à côté de sa description <sujet>.json ; Après export : <sujet>.drawio.png, .svg ou .pdf.
- **`drawio_build.py`** : Construit le .drawio aux styles de la charte à partir de la description JSON, puis le vérifie comme check_drawio.py. Rapport JSON, codes de sortie : 0 schéma produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`check_drawio.py`** : Vérifie un fichier draw.io avant export. Rapport JSON, codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.

### `excalidraw-diagram`

Crée un schéma Excalidraw au style dessiné à la main à partir d'une description simple, le rend en PNG ou SVG et le relit. À utiliser pour les publics non techniques, les ateliers (façon tableau blanc) et les vues d'ensemble.

Résumé de [`contract.json`](skills/excalidraw-diagram/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Description JSON du schéma : title, audience, elements.
- **Sorties** : <sujet>.excalidraw, à côté de sa description <sujet>.json ; Après export : <sujet>.excalidraw.png ou .svg.
- **`excalidraw_build.py`** : Construit la scène Excalidraw à partir de la description JSON. Rapport JSON, codes de sortie : 0 scène produite sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
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
- **Entrées** : Décision de diagram-brief ; Contenu à représenter.
- **Sorties** : Bloc ```mermaid dans un Markdown, ou fichier .mmd.
- **Scripts** : aucun ; la validation passe par le skill suivant.
- **Passe la main** au skill `diagram-export` : vérifier le rendu (--check) ou exporter en PNG ou SVG.

### `requirements-catalog`

Extrait des documents d'un projet (cahier des charges, comptes rendus, spécifications convertis en Markdown) le catalogue des exigences fonctionnelles et non fonctionnelles, avec identifiants stables, priorité, mesure et citation de la source vérifiée par script, puis l'exporte en Markdown et CSV. À utiliser pour recenser, tracer ou exporter les exigences d'un projet.

Résumé de [`contract.json`](skills/requirements-catalog/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Documents en Markdown (sortie de doc-to-markdown) dans un dossier sources ; Description JSON des exigences : title, sources, requirements (id repris des documents ou EF-/ENF-, nature, title, text, priority, category ou domain, metric, sources avec citation, questions, status), ignored, glossary (terme, définition, synonymes).
- **Sorties** : <nom>.md : catalogue pour la revue (exigences fonctionnelles, non fonctionnelles, questions, exigences déduites, retirées, phrases écartées, glossaire avec les exigences qui emploient chaque terme) ; <nom>.csv : même catalogue pour un tableur (séparateur ;, UTF-8 avec BOM).
- **`req_build.py`** : Vérifie chaque citation dans son document et en donne la ligne, repère les phrases normatives des sources reprises par aucune exigence, signale une exigence renumérotée alors que sa source porte un identifiant, doublons et exigences non mesurables, puis écrit le catalogue en Markdown et en CSV. Rapport JSON, codes de sortie : 0 catalogue produit sans erreur (avertissements possibles) ; 1 description invalide, citation introuvable ou autre erreur ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `doc-to-markdown` : les documents ne sont pas encore en Markdown.
- **Passe la main** au skill `architecture-options` : le catalogue est validé : proposer des architectures.
- **Passe la main** au skill `decision-log` : noter les choix (exigence déduite, phrase écartée, priorité) et soumettre le catalogue à la revue.

### `threat-model`

Prépare le modèle de menaces STRIDE d'une architecture décrite en JSON (celle des schémas cloud) : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable avec sa mesure et son statut à compléter. À utiliser pour une analyse de sécurité d'une architecture cloud, d'une option d'architecture ou d'une infrastructure existante.

Résumé de [`contract.json`](skills/threat-model/contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Description JSON de l'architecture, celle de cloud_build.py (skill cloud-architecture) : groupes, services typés, flux avec protocole ; Ou la description cloud d'une option d'architecture-options (schemas/option-<id>.cloud.json).
- **Sorties** : <sujet>.threats.md : frontières de confiance, flux qui les traversent, une menace type par catégorie STRIDE applicable, mesure type et statut à compléter.
- **`stride.py`** : Prépare le modèle de menaces STRIDE à partir de la même description : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable, avec mesure type et statut à compléter. Rapport JSON, codes de sortie : 0 modèle produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `cloud-architecture` (`cloud_build.py`, obligatoire) : lire la description comme le schéma : types de services, groupes, frontières et numéros de flux F1, F2....
- **Passe la main** au skill `cloud-architecture` : schéma des menaces (cloud_build.py --view threats), mêmes numéros de flux.
- **Passe la main** au skill `well-architected-review` : contrôler aussi les piliers Well-Architected du fournisseur.
- **Passe la main** à l'utilisateur : compléter avec lui les mesures retenues et les statuts des menaces.

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
- **Passe la main** au skill `cloud-architecture` : corriger la description puis reconstruire le schéma.
- **Passe la main** au skill `threat-model` : préparer aussi le modèle de menaces STRIDE.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept.
