---
name: excalidraw-diagram
description: "Crée un schéma Excalidraw au style dessiné à la main à partir d'une description simple, le rend en PNG ou SVG et le relit. À utiliser pour les publics non techniques, les ateliers (façon tableau blanc) et les vues d'ensemble."
---

# excalidraw-diagram

Les chemins `scripts/...` sont relatifs au dossier de ce skill. N'écrivez pas
le JSON Excalidraw à la main : décrivez le schéma dans un format court, le
script construit la scène.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief ; Description JSON du schéma : title, audience, elements.
- **Sorties** : <sujet>.excalidraw, à côté de sa description <sujet>.json ; Après export : <sujet>.excalidraw.png ou .svg.
- **`excalidraw_build.py`** : Construit la scène Excalidraw à partir de la description JSON. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : rendre et relire l'image.

## 1. Décrire le schéma

Fichier `<sujet>.json` :

```json
{
  "title": "Comment un paiement est traité",
  "audience": "non technique",
  "elements": [
    {"id": "client", "role": "person", "label": "Client", "row": 0, "col": 0},
    {"id": "boutique", "role": "zone", "label": "Notre boutique", "x": 260, "y": -40, "w": 640, "h": 360},
    {"id": "site", "role": "system", "label": "Site web", "row": 0, "col": 1},
    {"id": "paiement", "role": "system", "label": "Service\nde paiement", "row": 0, "col": 2},
    {"id": "historique", "role": "db", "label": "Historique", "row": 1, "col": 2},
    {"id": "banque", "role": "external", "label": "Banque", "row": 0, "col": 3.3},
    {"from": "client", "to": "site", "label": "commande"},
    {"from": "paiement", "to": "historique", "label": "enregistre", "style": "async"}
  ]
}
```

- **Formes** : `role` parmi `person`, `system`, `external`, `db`, `queue`,
  `alert`, `zone` (cadre en tirets derrière les formes) et `note` (texte
  libre). Le rôle donne la couleur de la charte. `shape` (`rectangle`,
  `ellipse`, `diamond`) force une forme.
- **Placement** : `row` et `col` (grille de 300 × 180 px, valeurs décimales
  permises), ou `x` et `y` en pixels. Taille par défaut 180 × 80, ou `w` et
  `h`.
- **Flèches** : `from`, `to`, `label` (un verbe), `style: "async"` pour des
  tirets. Elles sont attachées aux formes : elles suivent si on les déplace
  dans Excalidraw.
- **Libellés** : `\n` pour aller à la ligne.
- `font` : `excalifont` (dessiné, par défaut) ou `nunito` (sobre, sans
  effet main levée). `legend` : `auto` (par défaut), `true` ou `false`.

## 2. Construire

```bash
uv run scripts/excalidraw_build.py SUJET.json
```

Produit `SUJET.excalidraw` et un rapport : erreurs (identifiant en double,
flèche vers une forme inconnue) et avertissements (formes qui se
chevauchent, forme qui déborde d'une zone, plus de 7 éléments pour un public
non technique, pas de titre). Corrigez la description jusqu'à zéro erreur et
zéro avertissement.

## 3. Rendre et relire

```bash
uv run ../diagram-export/scripts/export.py SUJET.excalidraw --format png
```

Ou en un seul appel avec la construction : `excalidraw_build.py SUJET.json
--export png` ; l'image est dans `export` du rapport.

Produit `SUJET.excalidraw.png` (ou `.svg`), qui embarque la scène : on peut le
rouvrir dans excalidraw.com. Ouvrez l'image et vérifiez : textes qui
débordent, flèches qui traversent une forme, schéma trop large. Ajustez `row`,
`col` ou `w` et recommencez les étapes 2 et 3.

Le rendu utilise la bibliothèque Excalidraw dans un navigateur local (Edge ou
Chrome s'ils sont installés, sinon Chromium de Playwright). La bibliothèque est
téléchargée une fois depuis npm puis gardée en cache.

## 4. Livrer

- Obsidian avec le plugin Excalidraw : livrez le `.excalidraw`. Sans le
  plugin : le `.excalidraw.svg` et `![[SUJET.excalidraw.svg]]`.
- Word, PowerPoint, Confluence : le `.excalidraw.png`.
- Gardez le `.json` de description à côté : c'est lui qu'on modifie pour
  faire évoluer le schéma. Si quelqu'un a retouché le `.excalidraw` dans
  Excalidraw, c'est ce fichier qui fait foi : modifiez-le directement.
