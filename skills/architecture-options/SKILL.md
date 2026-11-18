---
name: architecture-options
description: "Propose et compare 2 ou 3 options d'architecture à partir d'un catalogue d'exigences : écarts de couverture, notes par critère justifiées, score pondéré et rang calculés par script, recommandation, puis ADR de la décision et un schéma draw.io par option. À utiliser pour proposer des architectures, comparer des scénarios ou documenter un choix d'architecture."
---

# architecture-options

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
concevez les options et les notez ; le script vérifie les références,
calcule scores et rang, met en forme et prépare les schémas.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Facultatif : le POS existant du SI (JSON ou CSV de urbanization-map, ou note Markdown avec tableau), dans le dossier ou dans le vault Obsidian du workflow (vault:<chemin>) ; Description JSON des options : title, context, audience, requirements, pos, hosting (qualifications, refs), criteria, options (id, name, summary, provider, components, flows, gaps, placement, wa_accept, scores, score_notes, pros, cons, risks), recommendation, decision ; Après la revue : decision.json, le choix de l'utilisateur (option, by, why, date, refs).
- **Sorties** : <nom>.md : comparaison pour la revue (synthèse et rang, critères et notes, écarts aux exigences, détail des options, recommandation, décision) ; schemas/architectures.json : description draw.io, une page par option, à construire avec drawio_build.py ; adr-architecture.md : décision d'architecture, quand decision est renseignée ou --decision donné ; tracabilite.md, tracabilite.csv : matrice exigence, couverture par option, composants de l'option retenue (ou recommandée) ; schemas/option-<id>.cloud.json : description cloud_build.py d'une option qui a un provider (icônes officielles) ; schemas/option-<id>.wa.md : revue Well-Architected des piliers d'une option cloud (wa_check.py du skill well-architected-review) ; schemas/pos-option-<id>.json : POS cible de chaque option (statuts des applications touchées), écrit par pos_impact.py (urbanization-map), à construire avec pos_build.py.
- **`options_build.py`** : Vérifie les références aux exigences, calcule le score pondéré et le rang de chaque option, élimine celles qui laissent une exigence indispensable non couverte, signale une recommandation qui ne suit pas le classement, puis écrit la comparaison, la description des schémas et l'ADR ; écrit la matrice de traçabilité exigence, option, composant (tracabilite.md, tracabilite.csv) et, pour une option avec provider, la description cloud_build.py de son schéma aux icônes officielles et sa revue Well-Architected des piliers (wa_check.py de well-architected-review) (constats par pilier dans la comparaison, constats de l'option retenue dans l'ADR). Avec le POS du SI, vérifie le placement de chaque option (pos_impact.py d'urbanization-map), en compte les impacts (créations, évolutions, remplacements, redondances, flux entre zones) et écrit son POS cible. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `urbanization-map` (`pos_impact.py`, facultatif : sans lui, avertissement) : placement de chaque option dans le POS du SI, impacts et POS cibles ; erreur si la description a un pos.
- **Dépend de** `well-architected-review` (`wa_check.py`, facultatif : sans lui, avertissement) : revue Well-Architected des piliers de chaque option cloud.
- **Dépend de** `cloud-architecture` (`lib/providers.json`, obligatoire) : catalogue commun des hébergeurs.
- **Passe la main** au skill `drawio-diagram` : construire schemas/architectures.drawio avec drawio_build.py.
- **Passe la main** au skill `diagram-export` : exporter les pages en PNG et les relire.
- **Passe la main** à l'agent `schema-designer` : un schéma C4, cloud aux icônes officielles ou un modèle de menaces est demandé pour l'option retenue.
- **Passe la main** au skill `decision-log` : noter la recommandation, soumettre la comparaison, puis la décision de l'utilisateur.
- **Passe la main** au skill `urbanization-map` : construire le POS cible de chaque option avec pos_build.py.
- **Passe la main** au skill `architecture-deck` : la décision est prise et les schémas exportés : assembler la présentation du dossier.
- **Passe la main** à l'agent `solution-estimator` : la décision est prise : chiffrer l'option retenue (charge, infrastructure, run, coût total).
- **Passe la main** au skill `cloud-architecture` : construire le schéma aux icônes du fournisseur d'une option cloud (schemas/option-<id>.cloud.json).

## 1. Concevoir les options

Partez du catalogue validé (`exigences.md`). Proposez 2 options, 3 si une
troisième est vraiment différente : des styles ou des partis pris distincts
(par exemple développement spécifique dans le cloud, progiciel, extension
de l'existant), pas des variantes d'un même schéma.

## 2. Décrire les options

Commencez par le brouillon, sans lire le catalogue des hébergeurs ni le code :

```bash
uv run scripts/options_build.py options.json --draft
```

Il écrit `options.json` avec les critères pondérés, `hosting` (qualifications
exigées par les exigences, SecNumCloud ou HDS) et deux options à décrire ; le
rapport donne les hébergeurs qualifiés (`providers`) et les exigences
indispensables à couvrir. `cloud_build.py --types <provider>` (skill
`cloud-architecture`) liste les types de composants d'un hébergeur. Complétez
le fichier :

```json
{
  "title": "Options d'architecture du portail",
  "context": "Ouvrir la déclaration en ligne, reliée à l'outil de gestion existant.",
  "requirements": "exigences.json",
  "options": [
    {"id": "A", "name": "Application web cloud", "summary": "Portail et API en conteneurs managés.",
     "components": [{"id": "assure", "label": "Assuré", "role": "person"},
                    {"id": "api", "label": "API", "tech": "conteneurs"},
                    {"id": "gestion", "label": "Outil de gestion", "role": "external"}],
     "flows": [{"from": "assure", "to": "api", "label": "HTTPS"}, {"from": "api", "to": "gestion", "style": "async"}],
     "gaps": {"ENF-005": {"level": "partiel", "note": "coût variable pendant les pics"}},
     "scores": {"performance": 5, "cout": 3},
     "score_notes": {"performance": "mise à l'échelle automatique", "cout": "6 000 euros par mois estimés"},
     "pros": ["..."], "cons": ["..."], "risks": ["..."]}
  ],
  "recommendation": {"option": "A", "why": "...", "refs": ["ENF-001"]}
}
```

- **Technologies** : `tech` nomme le framework ou le produit d'un
  composant ; ajoutez `version` (`"tech": "Spring Boot", "version": "3.3"`)
  quand l'utilisateur ou les documents la fixent, jamais devinée. Elle suit
  la technologie dans `options.md` et dans les exports (`spec-pack`).
- **Critères** : sans `criteria`, une catégorie d'exigence non
  fonctionnelle par critère, pondérée par sa plus haute priorité
  (indispensable 3, importante 2, souhaitable 1). Donnez `criteria`
  (`id`, `name`, `weight` 1 à 5, `refs`) seulement si l'utilisateur veut
  d'autres critères ; notez ce choix dans le journal.
- **Notes** : de 1 à 5 pour chaque critère et chaque option, chacune
  justifiée en quelques mots dans `score_notes`. Le score et le rang sont
  calculés par le script : ne les écrivez pas.
- **Écarts** : `gaps` liste seulement les exigences couvertes en partie
  (`partiel`) ou pas du tout (`non`) ; les autres sont couvertes. Une option
  qui ne couvre pas une exigence indispensable est éliminée.
- **Composants et flux** : ceux qui comptent pour comparer (10 au plus),
  `role` parmi person, system (défaut), external, db, queue. Ils donnent le
  schéma de l'option. `refs` d'un composant liste les exigences qu'il
  porte : la matrice de traçabilité les reprend, et le script avertit d'une
  exigence couverte qu'aucun composant de l'option retenue ne porte.
- **Option cloud** : avec `provider` (aws, azure, gcp, k8s, ou un hébergeur
  souverain : ovh, outscale, cloud-temple, scaleway, s3ns, bleu, numspot,
  sur-site) et un `type`
  `cloud_build.py` par composant (`ecs`, `aurora`, `sqs`... ; sinon déduit
  du rôle), le script écrit aussi `schemas/option-<id>.cloud.json`, schéma
  aux icônes officielles. Le script la contrôle aussi contre les piliers
  du cadre Well-Architected du fournisseur (`wa_check.py` du skill
  `cloud-architecture`) : constats par pilier dans `options.md`, détail
  dans `schemas/option-<id>.wa.md`, constats de l'option retenue dans
  l'ADR. Donnez `count` (2, « 2-10 ») aux composants redondés et
  `protocol` (HTTPS, TLS...) aux flux. Chaque constat ouvert (pas de
  supervision, pas de WAF, instance unique...) s'ajoute à l'option comme
  composant, ou s'accepte avec sa raison dans `wa_accept` (clé du champ
  `open` du rapport, `"SEC-05@F1": "WAF du groupe en amont"`) ; il pèse
  sur la note du critère concerné. Une gravité haute non traitée est
  signalée.
- **Qualification d'hébergement** : si une exigence impose SecNumCloud ou
  HDS, écrivez `"hosting": {"qualifications": ["secnumcloud"], "refs":
  ["ENF-003"]}`. Le script compare l'hébergeur de chaque option au catalogue
  commun des hébergeurs : sans la qualification, l'écart « non » est ajouté
  sur ces exigences (option éliminée si l'une est indispensable) et la
  revue Well-Architected porte le constat SEC-08.
- **Recommandation** : l'option et pourquoi, avec les exigences
  déterminantes. Si elle ne suit pas le classement, le script l'avertit :
  la justification doit l'expliquer.
- **Décision** : après la revue, écrivez `decision.json` (`option`, `by`,
  `why` avec les mots de l'utilisateur, `date`, `refs`), même si le choix
  diffère de la recommandation, et lancez le script avec `--decision
  decision.json` : il n'écrit que l'ADR, la comparaison validée ne change
  pas. Hors workflow, le même objet peut aller dans `decision` de
  `options.json`.

- **Position dans le SI** : avec le POS existant du SI (`"pos":
  "pos-si.csv"` : description JSON ou inventaire CSV de `urbanization-map`,
  ou note Markdown avec le tableau zone, quartier, ilot, application,
  statut ; `"vault:Études/POS du SI.md"` pour un POS versé au vault du
  workflow), chaque option dit où elle se place dans l'architecture
  globale :

  ```json
  "placement": [
    {"app": "Portail sinistres", "change": "nouvelle", "zone": "Opérations",
     "quartier": "Sinistres", "ilot": "Déclaration", "component": "api",
     "coexists": "canal web en plus du téléphone"},
    {"app": "Outil de gestion des sinistres", "change": "a-faire-evoluer", "component": "gestion"}
  ]
  ```

  `change` : `nouvelle` (zone et quartier du POS, îlot conseillé),
  `a-faire-evoluer`, `a-remplacer`, `en-place` (réutilisée), `externe`. Une
  application existante garde son nom exact du POS. Le script signale une
  redondance (nouvelle application dans un îlot déjà occupé, sans
  `coexists` qui l'explique), compte les flux entre zones (via
  `component`) et ajoute le critère `urbanisation` à noter.

## 3. Construire

```bash
uv run scripts/options_build.py options.json
```

Produit `options.md` (comparaison pour la revue),
`schemas/architectures.json` (une page draw.io par option), la matrice de
traçabilité `tracabilite.md` et `.csv` (exigence, couverture par option,
composants de l'option retenue ou recommandée) et, pour une option cloud,
`schemas/option-<id>.cloud.json` ; avec un POS, la section « Position dans
le SI » et le POS cible de chaque option, `schemas/pos-option-<id>.json` ;
`--decision decision.json` produit `adr-architecture.md`. Corrigez jusqu'à zéro erreur.

## 4. Schémas

```bash
uv run ../drawio-diagram/scripts/drawio_build.py schemas/architectures.json
uv run ../diagram-export/scripts/export.py schemas/architectures.drawio --format png
```

Une image par option (`architectures.drawio.png`, `architectures-2.drawio.png`...),
à relire une fois chacune. Une option cloud a aussi son schéma aux icônes
officielles :

```bash
uv run ../cloud-architecture/scripts/cloud_build.py schemas/option-a.cloud.json
```

Avec un POS, le POS cible de chaque option (applications touchées colorées
par statut) :

```bash
uv run ../urbanization-map/scripts/pos_build.py schemas/pos-option-a.json
```

Pour l'option retenue, un schéma C4, réseau ou un modèle de menaces STRIDE
se demande à l'agent `schema-designer`, avec `options.md` et les mêmes noms
de composants.

## 5. Présentation (facultatif)

Une fois la décision prise et les schémas exportés en PNG, le skill
`architecture-deck` assemble la présentation du dossier depuis les seuls
fichiers validés.
