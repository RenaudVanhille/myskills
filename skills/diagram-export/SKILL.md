---
name: diagram-export
description: "Exporte un schéma (draw.io, Mermaid, Excalidraw, LikeC4) en PNG, SVG ou PDF pour Word, PowerPoint, Confluence ou un Markdown, ou vérifie seulement qu'il se rend. À utiliser pour intégrer un schéma dans un document ou valider sa syntaxe."
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
| `.mmd` | Mermaid CLI | `nom.png`, `.svg` ou `.pdf` |
| `.md` | Mermaid CLI, pour chaque bloc ```mermaid | `nom-1.png`, `nom-2.png`... |
| `.excalidraw` | Excalidraw dans un navigateur local | `nom.excalidraw.png` ou `.svg`, qui embarquent la scène |
| dossier LikeC4 ou `.c4` | LikeC4 | un PNG par vue, nommé d'après la vue |

Les exports vont à côté de la source, ou dans `--out`.

## Choisir le format de sortie

| Destination | Format |
| --- | --- |
| Word, PowerPoint | `png`, `--scale 2` (net à l'impression comme à l'écran) |
| Confluence | `png` ; pour draw.io, le `.drawio.png` reste modifiable |
| Markdown, site web | `svg` |
| Impression, pièce jointe | `pdf` (draw.io et Mermaid) |
| Fond coloré (diapositive sombre) | ajoutez `--transparent` |

## Vérifier sans exporter

`--check` rend le schéma dans un dossier temporaire et ne garde rien : c'est
la validation de syntaxe pour Mermaid et LikeC4, et un test de rendu pour
draw.io et Excalidraw.

## Rapport

Le script affiche un rapport JSON par source : fichiers produits
(`outputs`) et erreur éventuelle (`error`, avec le message de l'outil).
Code de sortie 1 si une source échoue. Si un outil manque, le message dit
lequel : appliquez `check-prerequisites` (groupe `schemas`).

Après l'export, ouvrez l'image pour la relire avant de la livrer.
