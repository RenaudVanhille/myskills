---
name: c4-architecture
description: "Modélise une architecture logicielle selon le modèle C4 (contexte, conteneurs, composants) avec LikeC4, valide le modèle et exporte une image par vue. À utiliser pour les schémas d'architecture."
---

# c4-architecture

Le modèle C4 décrit une architecture en niveaux, du plus large au plus
détaillé. Un seul modèle LikeC4 sert toutes les vues : on décrit les éléments
une fois, chaque vue en montre une partie.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Code, configuration ou description de l'architecture ; pour un existant, le graphe du code de graphify (graph.json) ; Description JSON du modèle (c4_build.py --schema), ou options.json d'architecture-options et l'option retenue.
- **Sorties** : Dossier LikeC4 : specification.c4 et model.c4 ; Un PNG par vue (après export).
- **`c4_build.py`** : Écrit le modèle LikeC4 (model.c4, specification.c4 de la charte) à partir d'une description JSON courte ou d'une option d'architecture-options, puis le vérifie : identifiants uniques, relations vers des éléments connus (avec la valeur proche), imbrication C4, vues de 20 éléments au plus, likec4 validate s'il est installé ; avec --draft graph.json, le brouillon de la description d'un existant tiré du graphe du code (graphify). Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : --from-options : valider options.json contre son schéma et reprendre une option.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : valider le modèle et exporter les vues.
- **Passe la main** au skill `excalidraw-diagram` : une vue est destinée à un public non technique.
- **Passe la main** au skill externe `graphify` (installé à part, contrat `shared/external/graphify.contract.json`) : C4 d'un existant sans graphe du code : graphify extract <dossier> --code-only (analyse locale) produit graphify-out/graph.json, que --draft lit.

## 1. Choisir le niveau

| Niveau | Montre | Pour |
| --- | --- | --- |
| 1. Contexte | le système, ses utilisateurs, les systèmes externes | tout public |
| 2. Conteneurs | applications, API, bases, files à l'intérieur du système | équipe, architectes |
| 3. Composants | modules à l'intérieur d'un conteneur | développeurs |

Le niveau 4 (code) ne se dessine pas : le code suffit. Un public non technique
ne voit que le niveau 1 ; s'il faut aller plus loin pour lui, passez par
`excalidraw-diagram`.

## 2. Décrire le modèle

Vous décrivez les éléments en JSON ; `scripts/c4_build.py` écrit
`model.c4`, copie `specification.c4` (types aux couleurs de la charte,
relation `async`) et vérifie le modèle. N'écrivez pas le `.c4` à la main.
`uv run scripts/c4_build.py --schema` donne la forme de `MODELE.json` :

```json
{
  "title": "Boutique en ligne",
  "elements": [
    {"id": "client", "kind": "person", "label": "Client", "description": "Achète en ligne"},
    {"id": "shop", "kind": "system", "label": "Boutique", "elements": [
      {"id": "web", "kind": "container", "label": "Site web", "tech": "React"},
      {"id": "api", "kind": "container", "label": "API paiement", "tech": "Java"},
      {"id": "db", "kind": "database", "label": "Paiements", "tech": "PostgreSQL"},
      {"id": "bus", "kind": "queue", "label": "Évènements"}
    ]},
    {"id": "bank", "kind": "external", "label": "Banque"}
  ],
  "relations": [
    {"from": "client", "to": "web", "label": "commande"},
    {"from": "api", "to": "bus", "label": "publie", "async": true},
    {"from": "api", "to": "bank", "label": "débite", "tech": "HTTPS"}
  ],
  "views": [
    {"id": "index", "title": "Boutique : contexte"},
    {"id": "shop", "title": "Boutique : conteneurs", "of": "shop"}
  ]
}
```

```bash
uv run scripts/c4_build.py MODELE.json [--out-dir DOSSIER]
uv run scripts/c4_build.py --from-options options.json --option A [--out-dir DOSSIER]
```

- `kind` : `person`, `system`, `external`, `container`, `component`,
  `database`, `queue` ; `elements` imbrique (composant dans un conteneur,
  conteneur dans un système). Les relations citent les identifiants seuls,
  le script écrit les chemins pointés.
- Chaque relation porte un verbe (`label`) ; `async` pour un message ou un
  évènement.
- Sans `views` : une vue de contexte et une vue de conteneurs par système.
  Une vue par niveau utile, pas plus.
- `--from-options` reprend une option d'`architecture-options` : personnes
  et externes autour d'un système `solution`, composants en conteneurs,
  flux en relations.
- À partir du code, partez du graphe de graphify (analyse locale) :
  `uv run scripts/c4_build.py c4.json --draft graphify-out/graph.json`
  écrit le brouillon (un conteneur par dossier de premier niveau, ses
  fichiers et sa technologie, les dépendances extraites entre dossiers).
  Complétez-le en lisant les points d'entrée, la configuration (Docker
  Compose, manifestes Kubernetes, fichiers d'environnement) et les clients
  HTTP ou de messagerie pour trouver conteneurs et relations. Notez dans la
  réponse ce qui est déduit et ce qui reste à confirmer.

Le rapport donne les erreurs avec leur chemin (élément inconnu avec la
valeur proche, imbrication interdite) ; corrigez la description et
relancez. Si `likec4` est installé, le script lance `likec4 validate`.

## 3. Valider et exporter

```bash
uv run ../diagram-export/scripts/export.py DOSSIER_DU_MODELE
```

Ou en un seul appel avec la construction : `c4_build.py MODELE.json
--export png` ; les images sont dans `export` du rapport.

`export.py` lance `likec4 validate` (références inconnues, erreurs de syntaxe)
puis exporte une image PNG par vue (`index.png`, `shop.png`) dans le dossier.
Avec `--check`, il valide et rend sans rien écrire. Il utilise `likec4` s'il
est installé, sinon `npx likec4` (Node.js requis).

Ouvrez chaque image et vérifiez que la vue se lit seule : titre, pas plus de
15 à 20 éléments, libellés de relations présents.

## 4. Livrer

- Dépôt : gardez les `.c4` dans le dépôt et liez les PNG depuis le Markdown.
  `npx likec4 start DOSSIER` ouvre un aperçu interactif.
- Bloc Mermaid à la place d'une image : `npx likec4 gen mermaid DOSSIER -o
  DOSSIER/mermaid` donne une base (une vue par fichier `.mmd`), sans les
  couleurs ; ajoutez les `classDef` de la charte avant de l'intégrer.
- Word, PowerPoint, Confluence : les PNG, ou un schéma draw.io si
  l'utilisateur veut l'éditer à la main ensuite.
