---
name: mermaid-diagram
description: "Écrit des schémas Mermaid (flux, séquence, états, classes, modèle de données) dans un Markdown ou un fichier .mmd et vérifie qu'ils se rendent. À utiliser pour la documentation dans un dépôt (README, docs/) ou Obsidian."
---

# mermaid-diagram

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Contenu à représenter ; Description JSON d'un flowchart ou d'une séquence (mermaid_build.py --schema), ou options.json d'architecture-options et l'option retenue.
- **Sorties** : Bloc ```mermaid dans un Markdown, ou fichier .mmd.
- **`mermaid_build.py`** : Écrit un diagramme Mermaid (flowchart ou séquence) à partir d'une description JSON courte ou d'une option d'architecture-options : identifiants sûrs, libellés protégés, formes et classDef de la charte, sous-graphes, flèches synchrones ou asynchrones, blocs alt/opt/loop ; vérifie les références (avec la valeur proche) et le nombre de nœuds. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : --from-options : valider options.json contre son schéma et reprendre une option.
- **Passe la main** au skill `diagram-export` : vérifier le rendu (--check) ou exporter en PNG ou SVG.

## 1. Choisir le type

| Pour montrer | Type Mermaid |
| --- | --- |
| Flux, processus, dépendances entre composants | `flowchart LR` (ou `TD` si vertical) |
| Échanges entre acteurs dans le temps | `sequenceDiagram` |
| Cycle de vie d'un objet | `stateDiagram-v2` |
| Modèle objet | `classDiagram` |
| Modèle de données | `erDiagram` |
| Planning | `gantt` |

## 2. Flux et séquence : décrire en JSON

Pour un `flowchart` ou un `sequenceDiagram`, décrivez le contenu en JSON ;
`scripts/mermaid_build.py` écrit la syntaxe (identifiants sûrs, libellés
protégés, formes et `classDef` de la charte, `autonumber`) et vérifie les
références. `uv run scripts/mermaid_build.py --schema` donne la forme.

```json
{"title": "Traitement d'un paiement", "type": "flowchart", "direction": "LR",
 "nodes": [{"id": "client", "label": "Client", "kind": "person"},
           {"id": "api", "label": "API (v2)", "kind": "system"},
           {"id": "db", "label": "Paiements", "kind": "db"}],
 "groups": [{"label": "Boutique", "nodes": ["api", "db"]}],
 "edges": [{"from": "client", "to": "api", "label": "paie"},
           {"from": "api", "to": "db", "label": "enregistre", "async": false}]}
```

```json
{"title": "Passage d'une commande", "type": "sequence",
 "participants": [{"id": "client", "label": "Client", "actor": true},
                  {"id": "api", "label": "API commandes", "box": "Services"}],
 "messages": [{"from": "client", "to": "api", "label": "POST /commandes (HTTPS)"},
              {"block": "alt", "branches": [
                {"when": "stock insuffisant", "messages": [{"from": "api", "to": "client", "label": "409", "kind": "reply"}]},
                {"when": "stock disponible", "messages": [{"from": "api", "to": "client", "label": "201", "kind": "reply"}]}]},
              {"note": "délai max 300 ms", "over": ["api"]}]}
```

```bash
uv run scripts/mermaid_build.py SCHEMA.json [--out SCHEMA.md|.mmd]
uv run scripts/mermaid_build.py --from-options options.json --option A [--out F]
```

- Nœuds : `kind` `person`, `system`, `external`, `db`, `queue`, `alert` ;
  `groups` donne les `subgraph` (équipe, réseau, système). 15 à 20 nœuds
  au plus ; au-delà, faites deux schémas.
- Liens : un verbe par lien (`label`) ; `async` pour un évènement.
- Séquence : `kind` `call` (défaut), `reply`, `async` ; `box` regroupe les
  participants par zone (exposition, services, données, tiers) ; blocs
  `alt`, `opt`, `loop` ; `note` sur un ou plusieurs participants. Mêmes
  noms de services que le schéma de déploiement (`cloud-architecture`).
- `--from-options` donne le flowchart d'une option d'`architecture-options`.

## 3. Autres types : écrire à la main

États, classes, modèle de données et planning s'écrivent directement :

- Un titre dans l'en-tête (`---`, `title: ...`, `---`).
- Identifiants courts sans accents (`api`, `db`), libellés avec des
  caractères spéciaux (`(`, `:`, `/`) entre guillemets : `api["API (v2)"]`.
- Couleurs : les `classDef` de `references/style.md` utiles, puis
  `class api,web system`. Pas de couleur en dur ailleurs.

## 4. Vérifier le rendu

```bash
uv run ../diagram-export/scripts/export.py FICHIER.md --check
```

Le script rend chaque bloc ```mermaid (ou le fichier `.mmd`) sans rien
écrire et indique le bloc fautif avec le message de Mermaid. Corrigez et
relancez jusqu'à zéro erreur. Le rendu utilise la bibliothèque Mermaid dans
un navigateur local piloté par Playwright (Edge ou Chrome s'ils sont
installés) ; la bibliothèque est téléchargée une fois depuis npm puis gardée
en cache.

Erreurs fréquentes à la main : parenthèse ou deux-points non protégés dans
un libellé, mot réservé `end` utilisé comme identifiant, flèche `->` au lieu
de `-->` dans un `flowchart`.

## 5. Livrer

- Dépôt et Obsidian : laissez le bloc dans le Markdown, ils le rendent.
- Word, PowerPoint, Confluence : exportez avec `diagram-export`
  (`--format png`), un fichier par bloc (`<nom>-1.png`, `<nom>-2.png`...).
