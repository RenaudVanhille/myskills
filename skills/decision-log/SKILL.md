---
name: decision-log
description: "Tient l'état d'un workflow à étapes avec portes de revue humaine et trace chaque choix, hypothèse, question, retour et validation dans un journal (workflow.json et journal.md). Une étape ne démarre qu'après validation de celles dont elle dépend, et des étapes indépendantes se mènent en parallèle ; un fichier validé puis modifié est détecté. À utiliser pour piloter un workflow prédictible où l'utilisateur relit chaque étape et où toutes les décisions doivent être tracées."
---

# decision-log

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script
tient l'état et applique les règles ; vous n'écrivez jamais `workflow.json`
ni `journal.md` à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier du workflow ; Commande (init, start, log, check, submit, review, status, upgrade, handoff, report), avec l'étape, le texte et les références (exigences, options, entrées) ; Facultatif : un vault Obsidian, mémoire partagée entre agents, sessions et utilisateur ; Pour capitaliser : une ou plusieurs missions (ou dossiers de workflow), dont les retours du journal sont lus ; puis les règles retenues par l'utilisateur (schéma shared/schemas/rules.schema.json).
- **Sorties** : workflow.json : étapes dans l'ordre (d'une définition JSON : un workflow livré de workflows/ ou fournie), statut, empreintes SHA-256 des fichiers soumis, entrées du journal ; journal.md : version lisible (étapes, schéma Mermaid d'avancement avec chaque étape obligatoire ou facultative et son statut, décisions et revues, questions), réécrite à chaque commande ; fichiers soumis, entrées, exigences et options y sont des liens Markdown vers le fichier ou la note du vault ; Livrables Markdown soumis (options.md, chiffrage.md, tracabilite.md...) : chaque identifiant d'exigence y devient un lien Markdown vers sa note du vault, sans changer le texte ni l'empreinte du fichier ; markdown-publish retire ces liens à l'export ; Avec un vault Obsidian : VAULT/<dossier>/ avec une note d'index, Exigences/, Documents/, Glossaire/, Options/, Décisions/, l'ADR et Étapes/<étape>.md avec ses livrables (vault dans le dossier du projet : liens vers les originaux, une seule version de chaque fichier ; sinon copies dans Fichiers/) ; lecons.md et lecons.json : leçons par mission et par étape, retours récurrents entre missions, règles de complétude proposées (postes attendus du chiffrage, scénarios attendus de la revue) ; avec --apply, les règles retenues ajoutées au fichier de règles de la mission ou de l'utilisateur.
- **`journal.py`** : Fait respecter l'ordre des étapes et les portes de revue (démarrage seulement après validation des étapes dont l'étape dépend, la précédente ou celles de son champ after, validation seulement d'une étape en revue dont les fichiers n'ont pas changé, retour qui remet à reprendre l'étape, puis, à sa nouvelle validation, les seules étapes qui en dépendent dont une entrée a changé), donne les étapes prêtes à mener en parallèle (ready), sérialise les commandes d'un même dossier (verrou), note chaque choix, hypothèse, question, soumission, retour et validation, et détecte un fichier validé modifié depuis ; chaque version validée est gardée dans .historique/ETAPE/DATE/ (dans une mission avec son dépôt git, un commit local valide(ETAPE) à la place ; une étape reprise se refait sur place, sans copie à côté). Avec un vault, réécrit après chaque commande la mémoire partagée dans Obsidian (vault_sync.py). upgrade remet un workflow ouvert avec une version antérieure au niveau des scripts actuels (définition livrée reprise sans perdre l'avancement, vault de la mission retrouvé, journal.md, liens des livrables, mémoire), à blanc sauf --apply. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`vault_sync.py`** : Écrit la mémoire partagée du workflow dans un vault Obsidian : une note par exigence, option, entrée du journal et document source (relation extrait-de), une note par étape soumise avec ses livrables, une note d'index et l'ADR, typées selon l'ontologie du vault et vérifiées avant l'écriture, depuis workflow.json et les livrables nommés dans memory ; supprime les notes générées orphelines et vérifie chaque lien. Lancé par journal.py après chaque commande quand le vault est connu. Rapport JSON (0 succès, 1 erreur). Rapport JSON (0 succès, 1 erreur).
- **`lessons.py`** : Capitalise les retours de revue sans modèle : lit les retours du journal de chaque workflow des missions données, les regroupe par mission et par étape en rapprochant ceux qui disent la même chose (mots significatifs communs), repère ceux qui reviennent dans plusieurs missions et, pour une étape de chiffrage ou de revue, propose la règle de complétude qui les attraperait (poste attendu de solution-estimate, scénario attendu d'architecture-review) sauf si une règle en place les couvre déjà ; écrit lecons.md et lecons.json, relus. Avec --apply, ajoute les règles retenues par l'utilisateur au fichier de règles de la mission (references.regles de mission.json) ou de l'utilisateur (MYSKILLS_REGLES, sinon ~/.myskills/regles.json), validé avant l'écriture. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider le catalogue d'exigences avant d'en écrire les notes.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et decision.json avant d'en écrire les notes.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : lire les postes attendus en place pour ne pas reproposer une règle qui couvre déjà un retour.
- **Dépend de** `architecture-review` (`arch_review.py`, facultatif : sans lui, avertissement) : lire les scénarios attendus en place pour ne pas reproposer une règle qui couvre déjà un retour.
- **Dépend de** `markdown-to-obsidian` (`lib/vault_ontology.py`, obligatoire) : ontologie du vault Obsidian (source unique) : construire et vérifier les notes écrites.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Vault Obsidian** : écrit les notes de type `workflow`, `etape`, `revue`, `exigence`, `terme`, `document`, `option-architecture`, `decision`, `adr`, selon l'ontologie du vault (`vault_ontology.py` du skill markdown-to-obsidian).
- **Passe la main** à l'utilisateur : une étape est soumise : l'utilisateur la valide ou fait un retour.
- **Passe la main** au skill `markdown-to-obsidian` : choisir le dossier et les tags du vault (vault_profile.py) avant journal.py init --vault.

## 1. Le cycle d'une étape

```text
a-faire --start--> en-cours --submit--> en-revue --review valide--> validee
                                            |
                                            +--review retour--> a-reprendre --start--> en-cours ...
```

| Commande | Quand | Le script refuse si |
| --- | --- | --- |
| `init DOSSIER [--definition NOM\|DEF.json \| --stages a,b,c] [--title T] [--vault VAULT --folder F]` | une fois, au début | `workflow.json` existe déjà, définition introuvable ou non conforme, vault introuvable |
| `start DOSSIER ETAPE [--submit]` | avant de travailler sur l'étape ; avec `--submit`, pour une étape que ses scripts produisent entièrement : contrôles et soumission dans le même appel | une étape dont elle dépend n'est pas validée, ou un de ses livrables a changé depuis |
| `log DOSSIER ETAPE --kind choix\|hypothese\|question\|reponse --text T --why J --refs EF-001,A` | à chaque choix qui demande du jugement ; `reponse --refs D-xxx` : la réponse de l'utilisateur, qui close la question | l'étape n'est pas en cours (sauf question et réponse) ; une réponse ne cite aucune question ouverte |
| `check DOSSIER ETAPE [--submit]` | descriptions de l'étape écrites, si sa définition a un champ `run` : tous ses contrôles en un appel ; avec `--submit`, soumission dans le même appel à zéro erreur | l'étape n'est pas démarrée, pas de `run` ; une erreur par contrôle en échec |
| `submit DOSSIER ETAPE [--files F ...]` | livrables vérifiés par leurs scripts | l'étape n'est ni en cours ni en revue (une étape en revue se soumet à nouveau si ses livrables changent), fichier introuvable, livrable attendu par la définition absent |
| `review DOSSIER ETAPE --decision valide\|retour --text "..."` | quand l'utilisateur a répondu | validation : étape pas en revue, ou fichiers modifiés depuis la soumission |
| `review DOSSIER ETAPE --from-vault` | l'utilisateur a rempli sa note de revue dans Obsidian | pas de vault, note sans propriété `revue` |
| `handoff DOSSIER --file M.json` | avant d'envoyer un message de passage | message non conforme, fichier introuvable |
| `report DOSSIER --file R.json` | avant de rendre le rapport final d'un agent | rapport non conforme, fichier introuvable |
| `status DOSSIER` | pour reprendre un workflow | - |
| `upgrade DOSSIER [--apply] [--keep-definition]` | workflow d'une version antérieure : à blanc, puis `--apply` si l'utilisateur accepte | définition introuvable ou invalide |

Le rapport donne toujours `current` (étape courante) et `next` (prochaine
action) : suivez `next`, ne le déduisez pas vous-même. À une nouvelle
soumission, `changes` liste les exigences, options et fichiers ajoutés,
retirés ou modifiés depuis la version relue : présentez-les à l'utilisateur
pour qu'il ne relise que ce qui a changé.

Avec une définition, le rapport de `init`, `start` et `status` donne aussi
`stage` : l'étape à produire (skills, agent, entrées, livrables attendus,
contrôles à lancer, consignes). Suivez-le ; si l'étape a un champ `run`,
écrivez toutes ses descriptions puis lancez `check` une fois, au lieu de
chaque contrôle à part (un tour au lieu d'un par script), avec `--submit`
pour soumettre dans le même appel ; `submit` sans `--files` soumet
les livrables de la définition. `ready` liste les étapes qui peuvent
démarrer maintenant : quand il y en a plusieurs, elles se mènent en
parallèle (section 2).

`handoff` et `report` (`--json '<une ligne>'` au lieu de `--file`)
fonctionnent aussi hors workflow : ils valident alors sans tracer.

## 2. Workflows décrits en JSON

`--definition` prend un workflow livré dans `workflows/` ou un fichier JSON
de même forme (`--schema` : `$defs.definition`). Étapes de chacun et
exemple de définition : `references/workflows.md`, à lire seulement pour
en choisir ou en écrire un. Étapes en parallèle, retour sur une étape
validée et mission : `references/moteur.md`, à lire quand le cas se
présente.

Chaque motif de `deliverables` doit correspondre à au moins un fichier à la
soumission ; ceux d'`optional` sont soumis s'ils existent.

Par défaut, une étape dépend de la précédente. `after` donne la liste des
étapes dont elle dépend vraiment, toutes placées avant elle (`[]` : aucune) :
dans `architecture`, revue et chiffrage dépendent des schémas et non l'une
de l'autre, et le dossier attend les deux. Quand `ready` donne plusieurs
étapes, elles se mènent en parallèle (`references/moteur.md`) ; les
commandes d'un même dossier attendent leur tour (verrou `workflow.lock`).
La définition est
copiée dans `workflow.json` : la modifier ensuite ne change pas un workflow
commencé.

## 3. Règles

- **Revue humaine** : n'appelez `review` qu'avec la réponse explicite de
  l'utilisateur, et mettez ses mots dans `--text`. Une validation n'est
  jamais déduite d'un silence.
- **Retour** : `review --decision retour` remet l'étape à reprendre, elle
  seule. À sa nouvelle validation, chaque étape commencée qui en dépend
  compare ses entrées (fichiers des étapes amont qu'elle lit, champ `inputs`
  de la définition) à celles de son démarrage : seules celles dont une
  entrée a changé sont remises à reprendre (entrées « invalidation »,
  `impacts.redo`) ; les autres restent validées et leurs livrables ne sont
  pas réécrits (`impacts.kept`). Un retour sur le modèle de données ne
  touche donc pas aux schémas cloud. Il vaut aussi pour une étape déjà
  validée : c'est la seule façon de revenir en arrière.
- **Choix tracés** : notez avec `log` chaque décision prise sans
  l'utilisateur (outil choisi, exigence déduite, phrase écartée, note
  attribuée, hypothèse), en une phrase, avec sa justification (`--why`) et
  les identifiants concernés (`--refs`). Une question que seul l'utilisateur
  peut trancher se note `--kind question` et se pose à la revue ; sa
  réponse se note `--kind reponse --refs D-xxx` (ses mots), ce qui la close.
  `status` ne compte que les questions ouvertes, et valider une étape qui en
  a encore donne un avertissement.
- **Fichiers figés** : `submit` enregistre l'empreinte de chaque fichier. Si
  un fichier validé change, `status` l'avertit : faites revoir l'étape
  (`review --decision retour`) plutôt que de continuer.

`journal.md` est la version lisible, à joindre au dossier livré. Son schéma
« Avancement » (Mermaid, repris dans la note d'index du vault) montre chaque étape,
obligatoire ou facultative (tirets), colorée selon son statut : ne pas le recopier.

**Capitaliser les retours** (fin de mission, ou à la demande) :
`lessons.py`, jamais sans l'accord de l'utilisateur sur les règles gardées ;
déroulé dans `references/lecons.md`.

## 4. Mémoire partagée dans Obsidian

Avec `init --vault VAULT` (et `--folder`, défaut `Workflows/<titre>`),
chaque commande réécrit dans le vault les notes du workflow (exigences,
documents, glossaire, options, décisions, ADR, index), typées selon
l'ontologie du vault. C'est la mémoire commune des agents, des sessions et
de l'utilisateur : pour reprendre un workflow ou retrouver une décision,
interrogez-la avec `vault_query.py` (skill `markdown-to-obsidian` : `--type
decision`, `--related "Option A"`, `--where statut=ouvert`), qui rend un JSON
court, plutôt que de lire les notes.

L'utilisateur peut valider dans Obsidian (`review --from-vault`) et écrire
sous « Mes notes » : ses callouts `[!question]` et `[!retour]` arrivent dans
le champ `annotations` du rapport, à prendre en compte. Notes écrites, revue
dans le vault, choix du dossier : `references/vault.md`, à lire seulement
dans ces cas. Hors journal, `vault_sync.py DOSSIER --vault VAULT` refait la
synchronisation.
