---
name: diagram-brief
description: "Grille de choix du format de schéma (Mermaid, draw.io, Excalidraw, C4) selon le public, la destination (Markdown, Obsidian, Word, PowerPoint, Confluence) et le type de schéma. À utiliser avant de produire un schéma."
---

# diagram-brief

Avant de dessiner, fixez trois choses : le **public**, la **destination** et
le **type de schéma**. Puis choisissez le format avec la grille.

## 1. Les trois questions

| Question | Réponses possibles |
| --- | --- |
| Pour qui ? | technique (développeurs, architectes, ops) ou non technique (métier, direction, client) |
| Où sera-t-il lu ? | Markdown d'un dépôt, Obsidian, Word, PowerPoint, Confluence |
| Que montre-t-il ? | architecture (contexte, conteneurs, composants), flux ou processus, séquence d'appels, états, modèle de données, déploiement, vue d'ensemble pour expliquer |

Déduisez ce que vous pouvez du contexte (un ADR vise un public technique, une
présentation au comité un public non technique). Ne posez qu'une question, et
seulement si la réponse change le format.

## 2. La grille

| Situation | Format | Skill |
| --- | --- | --- |
| Architecture logicielle à maintenir, plusieurs vues ou niveaux | LikeC4 (C4) | `c4-architecture` |
| Une seule vue C4 dans un Markdown | Mermaid généré depuis LikeC4, ou Mermaid `flowchart` aux couleurs C4 | `c4-architecture` |
| Séquence d'appels, états, classes, modèle de données, Gantt | Mermaid | `mermaid-diagram` |
| Flux ou processus simple dans un dépôt ou Obsidian | Mermaid | `mermaid-diagram` |
| Public non technique, atelier, vue d'ensemble « pour expliquer » | Excalidraw | `excalidraw-diagram` |
| Public technique, Word, PowerPoint ou Confluence, mise en page précise, schéma réseau ou déploiement | draw.io | `drawio-diagram` |

Le public passe avant la destination. Un
schéma pour un public non technique est un Excalidraw, même s'il finit dans
PowerPoint ou Confluence (on l'exporte en PNG). draw.io sert quand le public
est technique ou que l'utilisateur veut retoucher le schéma lui-même dans
Office ou Confluence.

En cas de doute entre deux formats, préférez celui qui reste modifiable là où
le schéma vivra : Mermaid dans un dépôt, draw.io dans Office et Confluence.

## 3. Ce qu'on livre selon la destination

| Destination | Livraison |
| --- | --- |
| Markdown d'un dépôt (GitHub, GitLab) | bloc ```mermaid dans le fichier ; sinon export SVG à côté et lien relatif |
| Obsidian | bloc ```mermaid, ou export `.excalidraw.svg` intégré avec `![[nom.excalidraw.svg]]` |
| Word, PowerPoint | PNG à l'échelle 2 (`diagram-export`), plus la source à côté |
| Confluence, schéma draw.io | le `.drawio` (à importer dans la macro draw.io pour le modifier) et le `.drawio.png` (à insérer dans la page) |
| Confluence, autre format | le PNG à insérer dans la page, plus la source jointe à la page |

## 4. Avant de commencer à dessiner

Notez en une phrase : le message principal du schéma, les 3 à 7 éléments
indispensables, et ce qu'on laisse de côté. Pour un public non technique,
remplacez chaque terme technique par ce qu'il fait (« le service qui encaisse »
plutôt que « payment-api »).

La charte commune est dans `references/style.md` : couleurs par rôle, formes,
taille du texte, règles de composition.
