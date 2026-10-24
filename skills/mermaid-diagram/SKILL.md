---
name: mermaid-diagram
description: "Écrit des schémas Mermaid (flux, séquence, états, classes, modèle de données) dans un Markdown ou un fichier .mmd et vérifie qu'ils se rendent. À utiliser pour la documentation dans un dépôt (README, docs/) ou Obsidian."
---

# mermaid-diagram

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Contenu à représenter.
- **Sorties** : Bloc ```mermaid dans un Markdown, ou fichier .mmd.
- **Scripts** : aucun ; la validation passe par le skill suivant.
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

## 2. Écrire

- Un titre dans l'en-tête :
  ```text
  ---
  title: Traitement d'un paiement
  ---
  flowchart LR
  ```
- Identifiants courts sans accents (`api`, `db`), libellés lisibles entre
  crochets : `api[API paiement]`. Libellés avec des caractères spéciaux
  (`(`, `:`, `/`) entre guillemets : `api["API (v2)"]`.
- Formes de la charte : `client([Client])`, `api[API]`, `db[(Base)]`,
  `bus[/Bus/]`. Flèche synchrone `-->`, asynchrone `-.->`, libellé
  `-->|appelle|`.
- Couleurs : ajoutez les `classDef` de `references/style.md` utiles, puis
  `class api,web system`. Pas de couleur en dur ailleurs.
- `subgraph` pour une zone (équipe, réseau, système).
- 15 à 20 nœuds maximum ; au-delà, faites deux schémas.

### Séquence cloud

Pour les appels entre services sur un parcours (requête API, traitement
asynchrone, authentification) :

```text
---
title: Passage d'une commande
---
sequenceDiagram
  autonumber
  actor client as Client
  box Exposition
    participant gw as API Gateway
  end
  box Services
    participant api as API commandes
    participant db as Base commandes
    participant bus as File SQS
  end
  client->>gw: POST /commandes (HTTPS, jeton OIDC)
  gw->>api: transmet (mTLS)
  api->>db: INSERT commande
  alt stock insuffisant
    api-->>client: 409 Conflit
  else stock disponible
    api-)bus: CommandeCréée
    api-->>client: 201 Créé
  end
  Note over api,db: délai max 300 ms
```

- `autonumber` numérote les messages ; `box` regroupe les participants par
  zone (exposition, services, données, tiers).
- `->>` appel synchrone, `-->>` réponse, `-)` message asynchrone.
- `alt` / `else` pour les cas d'erreur, `opt` pour une étape facultative,
  `loop` pour une relance ; `Note over` pour un délai, un timeout ou un
  protocole.
- Mêmes noms de services que le schéma de déploiement (`cloud-architecture`).

## 3. Vérifier le rendu

```bash
uv run ../diagram-export/scripts/export.py FICHIER.md --check
```

Le script rend chaque bloc ```mermaid (ou le fichier `.mmd`) sans rien
écrire et indique le bloc fautif avec le message de Mermaid. Corrigez et
relancez jusqu'à zéro erreur. Le rendu utilise la bibliothèque Mermaid dans
un navigateur local piloté par Playwright (Edge ou Chrome s'ils sont
installés) ; la bibliothèque est téléchargée une fois depuis npm puis gardée
en cache.

Erreurs fréquentes : parenthèse ou deux-points non protégés dans un
libellé, mot réservé `end` utilisé comme identifiant, flèche `->` au lieu de
`-->` dans un `flowchart`.

## 4. Livrer

- Dépôt et Obsidian : laissez le bloc dans le Markdown, ils le rendent.
- Word, PowerPoint, Confluence : exportez avec `diagram-export`
  (`--format png`), un fichier par bloc (`<nom>-1.png`, `<nom>-2.png`...).
