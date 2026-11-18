---
name: tender-response
description: "Prépare la réponse à un appel d'offres à partir du dossier de consultation en Markdown : dépouillement (dates limites, critères de notation et poids, pièces à fournir, format de réponse, clauses à risque, citations vérifiées), matrice de conformité exigence par exigence (Markdown, CSV, Excel), registre des hypothèses, exclusions, prérequis et questions au client avant la date limite. Les scripts écrivent les brouillons, le modèle relit et juge. À utiliser en avant-vente, avant le chiffrage et le mémoire technique."
---

# tender-response

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Chaque
script écrit d'abord un brouillon (`--draft`, jamais par-dessus un fichier
existant) : vous ne faites que relire, juger et compléter. Ne relisez pas
les fichiers produits : lisez le rapport.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Dossier de consultation (règlement, cahier des charges, bordereau de prix) en Markdown dans sources/ (sortie de doc-to-markdown) ; Description du dépouillement (ao.json) : dates, critères et poids, pièces, format, clauses à risque, chacun avec sa citation ; écrite d'abord par tender_build.py --draft ; Pour la matrice de conformité : exigences.json (requirements-catalog), options.json (architecture-options) et conformite.json (réponse par exigence) ; Pour le registre : registre.json (hypothèses, exclusions, prérequis, questions) ; brouillon tiré d'exigences.json, chiffrage.json et du journal ; Pour la qualification : qualification.json (note et raison par critère de la grille, décision de l'utilisateur) ; facultatif, une grille propre à l'organisation.
- **Sorties** : ao.md : dépouillement (calendrier et échéances, critères pondérés, pièces à fournir à cocher, format de réponse, clauses à risque par niveau) ; conformite.md, conformite.csv et conformite.xlsx : matrice de conformité (réponse par exigence, justification, composants, source) ; questions-client.md : questions à poser avant la date limite ; registre.md et registre.csv : hypothèses, exclusions, prérequis et réponses du client, à reprendre dans l'offre ; qualification.md : grille notée, note sur 100, recommandation go / no-go et décision, tracée au journal.
- **`tender_build.py`** : Dépouille un dossier de consultation : vérifie chaque citation, contrôle les poids des critères (premier niveau sur 100, sous-critères égaux à leur critère), l'ordre des dates et le temps restant avant les dates limites (questions, remise), signale les clauses à risque haut sans note et les éléments des sources repris par aucune entrée ; écrit ao.md ; avec --draft, écrit d'abord la description depuis les sources (dates, tableaux de pondération, listes de pièces, format, clauses). Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`compliance_build.py`** : Construit la matrice de conformité : valide exigences.json et options.json contre le schéma de leur script, exige une réponse par exigence retenue et une justification pour chaque réponse partielle ou non conforme, reprend les composants de l'option pour une réponse conforme, signale une réponse qui contredit les écarts de l'option ; écrit Markdown, CSV et Excel (bibliothèque standard), relit le classeur ; avec --draft, écrit d'abord les réponses tirées des écarts de l'option. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`assumptions.py`** : Tient le registre des hypothèses, exclusions, prérequis et questions au client : nature tirée du préfixe, références vérifiées dans exigences.json et ao.json, réponse exigée d'une question répondue, questions à envoyer comptées avant la date limite du dépouillement ; écrit questions-client.md et le registre à reprendre dans l'offre (Markdown, CSV relu) ; avec --draft, écrit d'abord le registre depuis exigences.json, chiffrage.json et le journal. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`qualify.py`** : Qualifie un appel d'offres sur une grille pondérée (go / no-go) : valide la grille, exige une note de 0 à 5 justifiée par critère, calcule la note sur 100 et la recommandation (seuils de la grille, critère éliminatoire), exige la raison d'une décision contraire, trace la décision au journal du workflow (--log) ; avec --draft, écrit la grille à noter avec les indices du dépouillement. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : valider options.json contre son schéma.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : tracer la décision go / no-go au journal du workflow (--log).
- **Passe la main** au skill `doc-to-markdown` : le dossier de consultation n'est pas encore en Markdown.
- **Passe la main** au skill `requirements-catalog` : le dépouillement est fait : cataloguer les exigences du cahier des charges.
- **Passe la main** au skill `architecture-dossier` : assembler le mémoire technique selon les critères (dossier_build.py --template memoire --tender ao.json).
- **Passe la main** au skill `decision-log` : noter les choix (clause acceptée, hypothèse posée, question retirée) et soumettre le livrable à la revue.
- **Passe la main** à l'agent `ui-designer` : le dossier de consultation contient des maquettes d'écrans à reproduire en HTML ou un design system à proposer.

## 1. Dépouiller le dossier de consultation

Les documents du dossier (règlement de la consultation, cahier des charges,
bordereau de prix) sont en Markdown dans `sources/` (sinon `doc-to-markdown`
d'abord).

```bash
uv run scripts/tender_build.py ao.json --draft
```

Le brouillon donne les dates (nature : questions, remise, soutenance,
visite, démarrage), les critères des tableaux de pondération (sous-critères
rattachés au critère dont ils font la somme, thème deviné), les pièces à
fournir (`memoire: true` et `pages` pour le mémoire technique), le format
de réponse et les clauses à risque, chacun avec sa citation exacte. Votre
travail :

- corriger un libellé, une nature de date, le thème d'un critère
  (`solution`, `securite`, `methode`, `maintenance`, `equipe`,
  `environnement`, `prix`, `autre` : il range le mémoire technique) ;
- pour chaque clause, écrire `note` (pourquoi c'est un risque, que faire :
  question au client, provision, réserve) et ajuster `level` ;
- passer dans `ignored`, avec `reason`, ce qui ne sert pas à la réponse.

```bash
uv run scripts/tender_build.py ao.json
```

Le rapport donne les jours restants avant les dates limites (`deadlines`),
le budget de pages du mémoire (`memoire_pages`) et les éléments des sources
repris par aucune entrée (`uncovered`, à reprendre ou écarter). Une date
limite des questions proche se dit tout de suite à l'utilisateur.

## 2. Qualifier : go ou no-go

Juste après le dépouillement, avant d'engager l'équipe :

```bash
uv run scripts/qualify.py qualification.json --draft
uv run scripts/qualify.py qualification.json --log qualification
```

Le brouillon donne un critère par ligne de la grille
(`references/grille-qualification.json`, ou celle de l'organisation dans
`grid`) avec ce qu'en dit le dépouillement (jours avant la remise, clauses à
risque, pièces). Notez chaque critère de 0 à 5 avec sa raison en une
phrase ; la décision (`decision` : `go`, `go-conditions` avec
`conditions`, `no-go`) est celle de l'utilisateur, avec ses mots. Le
script calcule la note sur 100 et la recommandation (un critère
éliminatoire à 1 ou moins donne no-go) ; une décision contraire exige sa
raison. Avec `--log`, la décision est notée au journal de l'étape
(`logged`). Un no-go arrête le workflow : dites-le à l'utilisateur.

## 3. Matrice de conformité

Après le choix de l'option (`options.json` d'architecture-options, avec sa
décision) et le catalogue d'exigences (`exigences.json`), dans le même
dossier :

```bash
uv run scripts/compliance_build.py conformite.json --draft
uv run scripts/compliance_build.py conformite.json
```

Le brouillon donne une réponse par exigence retenue, tirée des écarts de
l'option (`hint` : la note de l'écart). N'écrivez que `justification` des
réponses `partiel` et `non-conforme`, en une ou deux phrases pour
l'acheteur : ce qui est couvert, ce qui ne l'est pas, ce qui est proposé.
Une réponse conforme sans justification reprend les composants qui couvrent
l'exigence. Le script produit `conformite.md`, `.csv` et `.xlsx` (relu) ;
une réponse qui contredit l'option est un avertissement à trancher.

## 4. Registre des hypothèses et questions

```bash
uv run scripts/assumptions.py registre.json --draft
uv run scripts/assumptions.py registre.json
```

Le brouillon reprend les questions ouvertes d'`exigences.json`, les
hypothèses et exclusions de `chiffrage.json` et les hypothèses et
questions du journal. Reformulez chaque question pour le client, ajoutez
les prérequis (accès, données, interlocuteurs) et les questions sur les
clauses à risque (`refs` : `R-02`, `ENF-001`...). Une question reçoit
`status` (`a-envoyer`, `envoyee`, `repondue` avec `answer`,
`sans-reponse`). Après la date limite, une question sans réponse devient
une hypothèse de l'offre.

Le script écrit `questions-client.md` (à envoyer avant la date limite) et
`registre.md` (à reprendre dans l'offre et dans le mémoire).

## 5. Mémoire technique

Le mémoire s'assemble avec `architecture-dossier`, dans l'ordre des
critères : vous écrivez les sections de `memoire/` (compréhension,
solution, sécurité, méthodologie, maintenance...) en reprenant les
livrables, puis, avec le script de ce skill-là :
`dossier_build.py . --template memoire --tender ao.json --out
memoire-technique.md --strict`.

Un critère sans section remplie et un dépassement du budget de pages sont
des erreurs avec `--strict`. La soutenance se prépare avec
`architecture-deck`.
