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
- **Entrées** : Dossier du workflow ; Commande : init, start, log, submit, review ou status, avec l'étape, le texte et les références (exigences, options, entrées) ; Facultatif : un vault Obsidian, mémoire partagée entre agents, sessions et utilisateur.
- **Sorties** : workflow.json : étapes dans l'ordre (d'une définition JSON : workflows/architecture.json, cloud-existant.json, revue-dossier.json, conformite.json, migration-cloud.json ou fournie), statut, empreintes SHA-256 des fichiers soumis, entrées du journal ; journal.md : version lisible (étapes, décisions et revues, questions), réécrite à chaque commande ; Avec un vault Obsidian : VAULT/<dossier>/ avec une note d'index, Exigences/EF-001.md..., Glossaire/<terme>.md..., Options/Option A.md..., Décisions/D-001.md..., ADR architecture.md, Étapes/<étape>.md avec ses livrables intégrés (copies dans Fichiers/).
- **`journal.py`** : Fait respecter l'ordre des étapes et les portes de revue (démarrage seulement après validation des étapes dont l'étape dépend, la précédente ou celles de son champ after, validation seulement d'une étape en revue dont les fichiers n'ont pas changé, retour qui remet à reprendre l'étape et celles qui en dépendent), donne les étapes prêtes à mener en parallèle (ready), sérialise les commandes d'un même dossier (verrou), note chaque choix, hypothèse, question, soumission, retour et validation, et détecte un fichier validé modifié depuis. Avec un vault, réécrit après chaque commande la mémoire partagée dans Obsidian (vault_sync.py). Rapport JSON, codes de sortie : 0 commande appliquée ; 1 commande ou message refusé (étape inconnue, ordre ou porte de revue non respectés, livrable validé modifié, fichier introuvable, définition ou workflow.json non conforme à son schéma) ; workflow.json inchangé.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`vault_sync.py`** : Écrit la mémoire partagée du workflow dans un vault Obsidian : une note par exigence, option et entrée du journal, une note par étape soumise avec ses livrables (images et Markdown copiés dans Fichiers/ et intégrés), une note d'index et l'ADR, reliées par des wikilinks et typées selon l'ontologie du vault (type, propriétés, relations typées, tags normalisés, vérifiés avant l'écriture), depuis workflow.json et les livrables que la définition nomme dans memory ; supprime les notes générées qui ne correspondent plus à rien et vérifie que chaque lien pointe vers une note. Lancé par journal.py après chaque commande quand le vault est connu. Rapport JSON, codes de sortie : 0 notes écrites, tous les liens résolus ; 1 workflow.json ou vault introuvable, fichier lu non conforme au schéma du skill qui l'écrit (workflow.json, exigences.json, options.json, decision.json), note hors ontologie du vault (rien n'est écrit), ou lien cassé.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider le catalogue d'exigences avant d'en écrire les notes.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json et decision.json avant d'en écrire les notes.
- **Vault Obsidian** : écrit les notes de type `workflow`, `etape`, `revue`, `exigence`, `terme`, `option-architecture`, `decision`, `adr`, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
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
| `start DOSSIER ETAPE` | avant de travailler sur l'étape | une étape dont elle dépend n'est pas validée, ou un de ses livrables a changé depuis |
| `log DOSSIER ETAPE --kind choix\|hypothese\|question --text T --why J --refs EF-001,A` | à chaque choix qui demande du jugement | l'étape n'est pas en cours (sauf question) |
| `submit DOSSIER ETAPE [--files F ...]` | livrables vérifiés par leurs scripts | l'étape n'est ni en cours ni en revue (une étape en revue se soumet à nouveau si ses livrables changent), fichier introuvable, livrable attendu par la définition absent |
| `review DOSSIER ETAPE --decision valide\|retour --text "..."` | quand l'utilisateur a répondu | validation : étape pas en revue, ou fichiers modifiés depuis la soumission |
| `review DOSSIER ETAPE --from-vault` | l'utilisateur a rempli sa note de revue dans Obsidian | pas de vault, note sans propriété `revue` |
| `handoff DOSSIER --file M.json` | avant d'envoyer un message de passage | message non conforme, fichier introuvable |
| `report DOSSIER --file R.json` | avant de rendre le rapport final d'un agent | rapport non conforme, fichier introuvable |
| `status DOSSIER` | pour reprendre un workflow | - |

Le rapport donne toujours `current` (étape courante) et `next` (prochaine
action) : suivez `next`, ne le déduisez pas vous-même. À une nouvelle
soumission, `changes` liste les exigences, options et fichiers ajoutés,
retirés ou modifiés depuis la version relue : présentez-les à l'utilisateur
pour qu'il ne relise que ce qui a changé.

Avec une définition, le rapport de `init`, `start` et `status` donne aussi
`stage` : l'étape à produire (skills, agent, entrées, livrables attendus,
contrôles à lancer, consignes). Suivez-le ; `submit` sans `--files` soumet
les livrables de la définition. `ready` liste les étapes qui peuvent
démarrer maintenant : quand il y en a plusieurs, elles se mènent en
parallèle (section 2).

`handoff` et `report` (`--json '<une ligne>'` au lieu de `--file`)
fonctionnent aussi hors workflow : ils valident alors sans tracer.

## 2. Workflows décrits en JSON

`--definition` prend un workflow livré dans `workflows/` ou un fichier JSON
de même forme (`--schema` : `$defs.definition`) :

| Workflow | Étapes |
| --- | --- |
| `architecture` | documents, exigences, architectures, schemas, puis revue et chiffrage en parallèle, et dossier (facultatives) : des documents du projet au dossier d'architecture technique |
| `cloud-existant` | description, puis schemas et menaces en parallèle : du code d'infrastructure au schéma cloud et au modèle STRIDE |
| `revue-dossier` | documents, exigences, revue, avis (facultative) : instruire un dossier reçu pour un comité, sans concevoir d'options |
| `conformite` | exigences et description en parallèle, menaces, rgpd, plan : menaces STRIDE, qualification de l'hébergeur, registre et AIPD RGPD, puis plan d'actions et dossier de conformité |
| `migration-cloud` | exigences, evaluation, puis cible suivie du chiffrage, en parallèle de la feuille-de-route, et dossier (chiffrage et dossier facultatifs) : évaluation 6R et vagues, architecture cible, trajectoire avec chemin critique |

```json
{"name": "revue-code", "title": "Revue d'un dépôt", "stages": [
  {"id": "analyse", "skills": ["doc-to-markdown"], "deliverables": ["analyse.md"],
   "optional": ["annexes/*.md"], "checks": ["doc-to-markdown : validate.py analyse.md"],
   "instructions": "Une phrase de consigne."}]}
```

Chaque motif de `deliverables` doit correspondre à au moins un fichier à la
soumission ; ceux d'`optional` sont soumis s'ils existent.

Par défaut, une étape dépend de la précédente. `after` donne la liste des
étapes dont elle dépend vraiment, toutes placées avant elle (`[]` : aucune) :
dans `architecture`, revue et chiffrage dépendent des schémas et non l'une
de l'autre, et le dossier attend les deux. Quand `ready` donne plusieurs
étapes, démarrez-les toutes (`start` pour chacune) et confiez chacune à un
sous-agent du niveau de l'étape ; chacune a sa propre revue, présentées
ensemble. Les commandes d'un même dossier attendent leur tour (verrou
`workflow.lock`) : des sous-agents peuvent appeler `journal.py` en même
temps sans rien perdre. La définition est
copiée dans `workflow.json` : la modifier ensuite ne change pas un workflow
commencé.

## 3. Règles

- **Revue humaine** : n'appelez `review` qu'avec la réponse explicite de
  l'utilisateur, et mettez ses mots dans `--text`. Une validation n'est
  jamais déduite d'un silence.
- **Retour** : `review --decision retour` remet l'étape à reprendre, ainsi
  que toutes les étapes qui en dépendent déjà commencées (entrées
  « invalidation ») ; une étape menée en parallèle n'est pas touchée.
  Il vaut aussi pour une étape déjà validée : c'est la seule façon de revenir
  en arrière.
- **Choix tracés** : notez avec `log` chaque décision prise sans
  l'utilisateur (outil choisi, exigence déduite, phrase écartée, note
  attribuée, hypothèse), en une phrase, avec sa justification (`--why`) et
  les identifiants concernés (`--refs`). Une question que seul l'utilisateur
  peut trancher se note `--kind question` et se pose à la revue.
- **Fichiers figés** : `submit` enregistre l'empreinte de chaque fichier. Si
  un fichier validé change, `status` l'avertit : faites revoir l'étape
  (`review --decision retour`) plutôt que de continuer.

`journal.md` est la version lisible, à joindre au dossier livré.

## 4. Mémoire partagée dans Obsidian

Avec `init --vault VAULT` (et `--folder`, défaut `Workflows/<titre>`),
chaque commande réécrit dans le vault une note par exigence
(`Exigences/EF-001`), par terme du glossaire (`Glossaire/Sinistre`), par option (`Options/Option A`), par entrée du
journal (`Décisions/D-001`), l'ADR et une note d'index, reliées par des
wikilinks. Le frontmatter suit l'ontologie du vault
(`scripts/lib/vault-ontology.json`) : `type`, propriétés (`priorite`,
`etape`, `par`...), relations typées en wikilinks (`workflow`, `concerne`,
`termes`, `ecarts`, `option`...) et tags normalisés (`type/exigence`,
`priorite/indispensable`) ; une note hors ontologie bloque l'écriture.
C'est la mémoire commune des agents, des sessions et de
l'utilisateur : pour reprendre un workflow ou retrouver une décision, lisez
la note d'index puis les notes liées, pas tout le dossier.

Une étape soumise a sa note de revue (`Revues/Revue <étape>`) : l'utilisateur
y met la propriété `revue` à `validée` ou `retour` et écrit son retour sous
« Votre retour » ; `review --from-vault` la lit et trace la décision comme
prise dans Obsidian. Les autres notes sont générées (`genere: decision-log`) :
ne les modifiez pas, un retour passe par `review`. Les autres notes du vault ne sont jamais
touchées. Pour choisir le dossier, lisez d'abord le profil du vault
(`vault_profile.py` du skill `markdown-to-obsidian`). Hors journal,
`vault_sync.py DOSSIER --vault VAULT` refait la synchronisation.
