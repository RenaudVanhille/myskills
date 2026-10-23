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

- **Entrées** : Catalogue d'exigences validé (exigences.json de requirements-catalog) ; Description JSON des options : title, context, audience, requirements, criteria, options (id, name, summary, components, flows, gaps, scores, score_notes, pros, cons, risks), recommendation, decision ; Après la revue : decision.json, le choix de l'utilisateur (option, by, why, date, refs).
- **Sorties** : <nom>.md : comparaison pour la revue (synthèse et rang, critères et notes, écarts aux exigences, détail des options, recommandation, décision) ; schemas/architectures.json : description draw.io, une page par option, à construire avec drawio_build.py ; adr-architecture.md : décision d'architecture, quand decision est renseignée ou --decision donné.
- **`options_build.py`** : Vérifie les références aux exigences, calcule le score pondéré et le rang de chaque option, élimine celles qui laissent une exigence indispensable non couverte, signale une recommandation qui ne suit pas le classement, puis écrit la comparaison, la description des schémas et l'ADR. Rapport JSON, codes de sortie : 0 comparaison produite sans erreur (avertissements possibles) ; 1 description invalide, exigence ou composant inconnu, note manquante ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `drawio-diagram` : construire schemas/architectures.drawio avec drawio_build.py.
- **Passe la main** au skill `diagram-export` : exporter les pages en PNG et les relire.
- **Passe la main** à l'agent `schema-designer` : un schéma C4, cloud aux icônes officielles ou un modèle de menaces est demandé pour l'option retenue.
- **Passe la main** au skill `decision-log` : noter la recommandation, soumettre la comparaison, puis la décision de l'utilisateur.

## 1. Concevoir les options

Partez du catalogue validé (`exigences.md`). Proposez 2 options, 3 si une
troisième est vraiment différente : des styles ou des partis pris distincts
(par exemple développement spécifique dans le cloud, progiciel, extension
de l'existant), pas des variantes d'un même schéma.

## 2. Décrire les options

Fichier `options.json`, à côté de `exigences.json` :

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
  schéma de l'option.
- **Recommandation** : l'option et pourquoi, avec les exigences
  déterminantes. Si elle ne suit pas le classement, le script l'avertit :
  la justification doit l'expliquer.
- **Décision** : après la revue, écrivez `decision.json` (`option`, `by`,
  `why` avec les mots de l'utilisateur, `date`, `refs`), même si le choix
  diffère de la recommandation, et lancez le script avec `--decision
  decision.json` : il n'écrit que l'ADR, la comparaison validée ne change
  pas. Hors workflow, le même objet peut aller dans `decision` de
  `options.json`.

## 3. Construire

```bash
uv run scripts/options_build.py options.json
```

Produit `options.md` (comparaison pour la revue) et
`schemas/architectures.json` (une page draw.io par option) ;
`--decision decision.json` produit `adr-architecture.md`. Corrigez jusqu'à zéro erreur.

## 4. Schémas

```bash
uv run ../drawio-diagram/scripts/drawio_build.py schemas/architectures.json
uv run ../diagram-export/scripts/export.py schemas/architectures.drawio --format png
```

Une image par option (`architectures.drawio.png`, `architectures-2.drawio.png`...),
à relire une fois chacune. Pour l'option retenue, un schéma C4, cloud aux
icônes officielles ou un modèle de menaces se demande à l'agent
`schema-designer`, avec `options.md` et les mêmes noms de composants.
