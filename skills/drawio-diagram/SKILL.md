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

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief et description JSON du schéma : title, audience, elements (ou pages) ; Ou un .drawio existant à modifier.
- **Sorties** : <sujet>.drawio en XML clair, à côté de sa description <sujet>.json ; Après export : <sujet>.drawio.png, .svg ou .pdf ; Depuis un .drawio existant : sa description courte <sujet>.json (drawio_read.py), à éditer puis reconstruire.
- **`drawio_build.py`** : Construit le .drawio aux styles de la charte à partir de la description JSON, puis le vérifie comme check_drawio.py. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`check_drawio.py`** : Vérifie un fichier draw.io avant export : structure, charte, chevauchements, et lisibilité estimée sans rendu (libellé trop long pour sa forme, flèches qui se croisent, flèche sous une forme) ; dit s'il faut relire l'image exportée (review_image). Rapport JSON (0 succès, 1 erreur).
- **`drawio_read.py`** : Tire d'un .drawio existant (XML clair ou compressé) la description JSON courte de drawio_build.py : rôle de chaque forme déduit de son style, identifiants, libellés sans HTML et positions (ou grille approchée), flèches avec libellé et style ; vérifie la description contre le schéma de drawio_build.py avant de l'écrire. Le modèle édite cette description au lieu du XML. Rapport JSON (0 succès, 1 erreur).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
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

Ne lisez pas le XML : tirez-en la description courte, éditez-la, puis
reconstruisez.

```bash
uv run scripts/drawio_read.py SCHEMA.drawio --out SCHEMA.json
uv run scripts/drawio_build.py SCHEMA.json --out SCHEMA.drawio --export png
```

`drawio_read.py` lit chaque page (XML clair ou compressé), garde les
identifiants, les libellés et les positions (`--grid` : une grille `row`,
`col` approchée, pour que `drawio_build.py` refasse la mise en page), déduit
le rôle de chaque forme de son style et reprend les flèches. Il refuse
d'écraser une description existante sans `--force`. Avertissements : flèche
sans forme à une extrémité (ignorée), forme sans libellé, icônes de
fournisseur : un schéma cloud se reprend avec `cloud-architecture`, qui
garde les icônes, car `drawio_build.py` applique les styles de la charte.

Pour seulement vérifier un `.drawio` reçu :

```bash
uv run scripts/check_drawio.py SCHEMA.drawio
```

Erreurs : XML illisible, identifiant en double, parent ou extrémité de flèche
introuvable. Avertissements : chevauchement, forme sans libellé, flèche non
attachée, couleur hors charte, pas de titre.

## 4. Exporter et relire

```bash
uv run ../diagram-export/scripts/export.py SUJET.drawio --format png
```

Ou en un seul appel avec la construction : `drawio_build.py SUJET.json
--export png` ; l'image est dans `export` du rapport.

Le PNG `SUJET.drawio.png` garde le XML : il se rouvre dans draw.io. Le
script estime la lisibilité (libellé trop long, flèches qui se croisent ou
passent sous une forme) : n'ouvrez l'image que si `review_image` est vrai,
pour juger les avertissements « lisibilité ». Ajustez `row`, `col`, `w` ou
`h`, reconstruisez et réexportez.

Pour Confluence, livrez les deux fichiers : le `.drawio`, à importer dans la
macro draw.io de la page pour le modifier, et le `.drawio.png`, à insérer
dans la page. Gardez le `.json` à côté pour faire évoluer le schéma.

draw.io Desktop est requis pour l'export (voir `check-prerequisites`).
