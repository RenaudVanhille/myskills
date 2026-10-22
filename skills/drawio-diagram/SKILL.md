---
name: drawio-diagram
description: "Crée (à partir d'une description courte) ou modifie un schéma draw.io (.drawio), le vérifie et l'exporte en PNG, SVG ou PDF modifiables. À utiliser pour les schémas destinés à Word, PowerPoint ou Confluence, ou qui demandent une mise en page précise."
---

# drawio-diagram

Les chemins `scripts/...` sont relatifs au dossier de ce skill. N'écrivez pas
le XML draw.io à la main pour un nouveau schéma : décrivez-le dans un format
court, le script construit le fichier aux styles de la charte.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Décision de diagram-brief et description JSON du schéma : title, audience, elements (ou pages) ; Ou un .drawio existant à modifier.
- **Sorties** : <sujet>.drawio en XML clair, à côté de sa description <sujet>.json ; Après export : <sujet>.drawio.png, .svg ou .pdf.
- **`drawio_build.py`** : Construit le .drawio aux styles de la charte à partir de la description JSON, puis le vérifie comme check_drawio.py. Rapport JSON, codes de sortie : 0 schéma produit sans erreur ; 1 description illisible ou erreur.
- **`check_drawio.py`** : Vérifie un fichier draw.io avant export. Rapport JSON, codes de sortie : 0 aucune erreur ; 1 au moins un fichier a une erreur.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.

## 1. Décrire le schéma

Fichier `<sujet>.json`, le même format que pour `excalidraw-diagram` (une
description sert aux deux) :

```json
{
  "title": "Paiement : conteneurs",
  "audience": "technique",
  "elements": [
    {"id": "client", "role": "person", "label": "Client", "row": 0, "col": 0},
    {"id": "shop", "role": "zone", "label": "Boutique", "x": 270, "y": -40, "w": 540, "h": 340},
    {"id": "api", "role": "system", "label": "API paiement [Java]", "row": 0, "col": 1},
    {"id": "db", "role": "db", "label": "Paiements", "row": 1, "col": 1},
    {"id": "bank", "role": "external", "label": "Banque", "row": 0, "col": 3},
    {"from": "client", "to": "api", "label": "paie"},
    {"from": "api", "to": "db", "label": "enregistre"},
    {"from": "api", "to": "bank", "label": "débite", "style": "async"}
  ]
}
```

- **Formes** : `role` parmi `person`, `system`, `external`, `db`, `queue`,
  `alert`, `zone` (cadre en tirets, toujours derrière) et `note` (texte
  libre) ; le rôle donne le style de la charte. `shape` (`rectangle`,
  `ellipse`, `diamond`) force une forme.
- **Placement** : `row` et `col` (grille de 300 × 180 px, décimales
  permises), ou `x` et `y` en pixels ; taille 180 × 80 par défaut, ou `w`
  et `h`. Flux de gauche à droite.
- **Flèches** : `from`, `to`, `label` (un verbe), `style: "async"` pour des
  tirets. draw.io les trace et les garde attachées aux formes.
- **Libellés** : `\n` pour aller à la ligne.
- **Plusieurs vues** : `"pages": [{"name": "Contexte", "title": "...",
  "elements": [...]}, ...]`, une page draw.io par vue.
- Titre et légende sont ajoutés par le script (`legend` : `auto`, `true` ou
  `false`).

## 2. Construire et vérifier

```bash
uv run scripts/drawio_build.py SUJET.json
```

Produit `SUJET.drawio` et un rapport : erreurs (identifiant en double, flèche
vers une forme inconnue) et avertissements (formes qui se chevauchent, forme
qui déborde d'une zone, plus de 7 éléments pour un public non technique, pas
de titre). Corrigez la description jusqu'à zéro erreur et zéro avertissement.

## 3. Modifier un .drawio existant

Lisez-le, gardez les identifiants et ne touchez qu'aux cellules concernées
(`<mxCell>` : `value` pour le libellé, `style`, `<mxGeometry x y width
height>`). Les styles de la charte sont dans `references/style.md` (section
draw.io). S'il est compressé (texte en base64 dans `<diagram>`),
`check_drawio.py` sait le lire ; réécrivez-le en XML clair. Puis vérifiez :

```bash
uv run scripts/check_drawio.py SCHEMA.drawio
```

Erreurs : XML illisible, identifiant en double, parent ou extrémité de flèche
introuvable. Avertissements : chevauchement, forme sans libellé, flèche non
attachée, couleur hors charte, pas de titre.

Si quelqu'un a retouché à la main un `.drawio` construit par le script, c'est
le `.drawio` qui fait foi : modifiez-le directement plutôt que de
reconstruire.

## 4. Exporter et relire

```bash
uv run ../diagram-export/scripts/export.py SUJET.drawio --format png
```

Le PNG `SUJET.drawio.png` garde le XML : il se rouvre dans draw.io. Ouvrez
l'image et vérifiez la lisibilité (libellés coupés, flèches qui se croisent
ou passent sous une forme). Ajustez `row`, `col`, `w` ou `h`, reconstruisez
et réexportez.

Pour Confluence, livrez les deux fichiers : le `.drawio`, à importer dans la
macro draw.io de la page pour le modifier, et le `.drawio.png`, à insérer
dans la page. Gardez le `.json` à côté pour faire évoluer le schéma.

draw.io Desktop est requis pour l'export (voir `check-prerequisites`).
