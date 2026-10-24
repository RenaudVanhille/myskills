---
name: diagram-export
description: "Exporte un schéma (draw.io, Mermaid, Excalidraw, LikeC4) en PNG, SVG ou PDF pour Word, PowerPoint, Confluence ou un Markdown, ou vérifie seulement qu'il se rend. À utiliser pour intégrer un schéma dans un document ou valider sa syntaxe, pas pour convertir un document Markdown entier."
---

# diagram-export

Un seul script pour tous les formats. Le chemin `scripts/export.py` est
relatif au dossier de ce skill.

```bash
uv run scripts/export.py SCHEMA [...] [--format png|svg|pdf] [--scale 2] \
    [--out DOSSIER] [--transparent] [--check]
```

| Source | Outil | Sortie |
| --- | --- | --- |
| `.drawio` | draw.io Desktop | `nom.drawio.png`, `.svg` ou `.pdf` ; PNG et SVG gardent le XML et se rouvrent dans draw.io |
| `.mmd` | Mermaid dans un navigateur local (Playwright) | `nom.png`, `.svg` ou `.pdf` |
| `.md` | idem, pour chaque bloc ```mermaid | `nom-1.png`, `nom-2.png`... |
| `.excalidraw` | Excalidraw dans un navigateur local | `nom.excalidraw.png` ou `.svg`, qui embarquent la scène |
| dossier LikeC4 ou `.c4` | LikeC4 | un PNG par vue, nommé d'après la vue |

Les exports vont à côté de la source, ou dans `--out`.

Le rendu est entièrement local : aucun schéma n'est envoyé à un service en
ligne. Le réseau ne sert qu'au premier usage, pour télécharger les outils
(bibliothèques Mermaid et Excalidraw à version fixée et empreinte vérifiée,
LikeC4 via `npx`, Playwright) ; ensuite, tout fonctionne hors ligne. Pour
une machine sans réseau : `doctor.py --prefetch` (skill
`check-prerequisites`) avant, puis `MYSKILLS_OFFLINE=1`.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Fichiers .drawio, .mmd, .mermaid, .md (blocs mermaid), .excalidraw, .c4 ou dossier LikeC4.
- **Sorties** : Images à côté de la source ou dans --out : <nom>.drawio.png, <nom>-1.png, <nom>.excalidraw.svg, un PNG par vue LikeC4 ; Rien avec --check.
- **`export.py`** : Exporte les schémas en PNG, SVG ou PDF, ou vérifie leur rendu. Mermaid et Excalidraw sont rendus dans un navigateur local avec des bibliothèques à version fixée, vérifiées par leur empreinte ; avec MYSKILLS_OFFLINE=1, rien n'est téléchargé. Rapport JSON, codes de sortie : 0 toutes les sources sont rendues ; 1 au moins une source échoue.
- **Passe la main** au skill `check-prerequisites` : un outil de rendu manque (groupe schemas).

## Choisir le format de sortie

| Destination | Format |
| --- | --- |
| Word, PowerPoint | `png`, `--scale 2` (net à l'impression comme à l'écran) |
| Confluence | `png` ; pour draw.io, livrez aussi le `.drawio` à importer dans la macro draw.io |
| Markdown, site web | `svg` |
| Impression, pièce jointe | `pdf` (draw.io et Mermaid) |
| Fond coloré (diapositive sombre) | ajoutez `--transparent` |

Un `.drawio` de plusieurs pages donne une image par page :
`<nom>.drawio.png` pour la première, `<nom>-2.drawio.png`... pour les
suivantes ; en PDF, un seul fichier avec toutes les pages.

## Vérifier sans exporter

`--check` rend le schéma dans un dossier temporaire et ne garde rien : c'est
la validation de syntaxe pour Mermaid et LikeC4, et un test de rendu pour
draw.io et Excalidraw. Inutile avant un export : un export qui échoue donne
la même erreur. Exportez plusieurs schémas en une seule commande.

## Rapport

Le script affiche un rapport JSON par source : fichiers produits
(`outputs`) et erreur éventuelle (`error`, avec le message de l'outil).
Code de sortie 1 si une source échoue. Si un outil manque, le message dit
lequel : appliquez `check-prerequisites` (groupe `schemas`).

Après l'export, ouvrez l'image pour la relire avant de la livrer.
