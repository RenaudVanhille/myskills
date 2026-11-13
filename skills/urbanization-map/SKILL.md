---
name: urbanization-map
description: "Dessine le plan d'occupation des sols (POS) d'un système d'information, ou carte d'urbanisation : zones, quartiers, îlots et applications rangées dedans, colorées par statut, en draw.io et PNG. Fait aussi la carte des capacités TOGAF (Business Capability Map) avec les applications posées dessus. À utiliser pour une cartographie fonctionnelle du SI, technique ou pour la direction, à partir d'une liste ou d'un inventaire CSV."
---

# urbanization-map

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décrivez seulement le découpage du SI ; le script fait toute la mise en
page, aux styles de la charte. N'écrivez pas le XML draw.io à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief : public et destination ; Description JSON du plan : title, audience, detail, vocabulary, zones (quartiers, ilots, apps) ; ou inventaire CSV, ou note Markdown avec son tableau (zone, quartier, ilot, application, statut) ; Pour pos_impact.py : le POS existant et des options d'architecture avec leur placement (options.json d'architecture-options).
- **Sorties** : <sujet>.drawio en XML clair, à côté de sa description <sujet>.json ou de l'inventaire .csv ; Après export : <sujet>.drawio.png (une image par page), .svg ou .pdf ; Avec pos_impact.py : schemas/pos-option-<id>.json, le POS cible de chaque option, à construire avec pos_build.py.
- **`pos_build.py`** : Construit le plan d'occupation des sols en draw.io (mise en page, styles de la charte, titre, légende, pages de zoom), puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`pos_impact.py`** : Situe des options d'architecture dans le POS existant : vérifie le placement de chaque option (noms connus du POS, zone et quartier d'une nouvelle application), compte créations, évolutions, remplacements, réutilisations, redondances et flux entre zones, puis écrit le POS cible de chaque option pour pos_build.py. Lit le POS en JSON, CSV ou note Markdown, ou dans le vault du workflow (vault:<chemin>). Sert aussi de module à options_build.py. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `drawio-diagram` (`check_drawio.py`, facultatif : sans lui, avertissement) : vérifier le .drawio produit.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main, ou dessiner les flux entre applications (cartographie applicative).

## 1. Le découpage

Un POS range le SI en blocs imbriqués, du plus large au plus fin :

| Niveau | Ce que c'est | Exemple |
| --- | --- | --- |
| Zone | grande famille d'activités | Pilotage, Opérations, Support, Référentiels, Échanges |
| Quartier | domaine fonctionnel | Distribution, Contrats, Sinistres |
| Îlot | sous-domaine, bloc de fonctions cohérent | Devis, Souscription |
| Application | ce qui occupe l'îlot | Simulateur web |

Le script place les zones selon leur type (`kind`) : `pilotage` en haut,
`operations` au milieu, `support` en bas, `echanges` à gauche,
`referentiel` à droite. Sans `kind`, il le déduit du nom (Pilotage,
Support, Référentiels, Échanges ; sinon opérations).

## 2. Décrire le plan

Fichier `<sujet>.json` :

```json
{
  "title": "Plan d'occupation des sols du SI",
  "audience": "technique",
  "zones": [
    {"name": "Pilotage", "quartiers": [
      {"name": "Décisionnel", "apps": ["Entrepôt de données"]}]},
    {"name": "Opérations", "quartiers": [
      {"name": "Distribution", "ilots": [
        {"name": "Devis", "apps": ["Simulateur web", {"name": "Outil agence", "status": "a-remplacer"}]}]}]},
    {"name": "Référentiels", "quartiers": [{"name": "Tiers", "apps": ["Référentiel clients"]}]}
  ]
}
```

- Une application est un nom, ou `{"name", "status"}`. Statuts :
  `en-place` (défaut), `a-faire-evoluer`, `a-remplacer`, `nouvelle`,
  `externe` ; chacun a sa couleur dans la charte.
- Un quartier a des `ilots`, des `apps` posées directement, ou les deux.
- `detail` : niveau le plus fin affiché (`zone`, `quartier`, `ilot`,
  `application`). Défaut : `application` pour un public technique,
  `quartier` pour un public non technique.
- `zoom: true` ajoute une page par zone, au niveau des applications : la
  vue d'ensemble reste lisible et le détail est à côté.
- Titre et légende sont ajoutés par le script (`legend` : `auto`, `true`
  ou `false`).
- `vocabulary: "togaf"` (ou `--vocabulary togaf`) pour une démarche TOGAF :
  la légende parle de capacités de niveau 1, 2 et 3 et de composants
  applicatifs, et les zones s'empilent dans l'ordre donné, sans la
  disposition pilotage / opérations / support. Avec `detail` à `ilot`, on
  obtient la *Business Capability Map* ; avec `application`, les
  applications posées sur les capacités (*Application/Function Matrix* en
  carte). Les statuts correspondent à l'analyse d'écart entre l'existant et
  la cible.

Si l'inventaire existe déjà dans un tableur, ne le recopiez pas : exportez-le
en CSV (séparateur `;` ou `,`) avec les colonnes `zone`, `quartier`,
`ilot`, `application`, `statut` (et `type` pour forcer le type de zone), une
ligne par application. Statuts en clair acceptés : « à faire évoluer »,
« à remplacer », « à créer », « SaaS »...

## 3. Construire

```bash
uv run scripts/pos_build.py SUJET.json [--detail quartier] [--zoom]
uv run scripts/pos_build.py inventaire.csv --title "POS du SI" --audience "non technique" --zoom
```

L'inventaire peut aussi être une note Markdown dont le tableau a les
colonnes de l'inventaire CSV (zone, quartier, ilot, application, statut).

Produit `SUJET.drawio` et un rapport : nombre de zones, quartiers, îlots et
applications, erreurs (statut ou type inconnu) et avertissements
(application rangée dans plusieurs îlots, trop d'applications pour le
public, et ceux de `check_drawio.py` du skill `drawio-diagram`). Corrigez la
description jusqu'à zéro erreur et zéro avertissement.

Pour un public non technique : `detail` à `quartier` (ou `zone`), des noms
de domaines en mots simples, et `--zoom` si l'on veut quand même le détail.

Les blocs sont des conteneurs draw.io : déplacer un quartier dans draw.io
déplace ses îlots et ses applications. Si quelqu'un a retouché le `.drawio` à
la main, c'est lui qui fait foi : modifiez-le avec `drawio-diagram` plutôt
que de reconstruire.

## 4. Exporter et relire

```bash
uv run ../diagram-export/scripts/export.py SUJET.drawio --format png
```

Une image par page (`SUJET.drawio.png`, puis `SUJET-2.drawio.png`... pour
les pages de zoom), qui garde le XML et se rouvre dans draw.io. Ouvrez la vue
d'ensemble pour la relire : libellés coupés, blocs trop vides ou trop
chargés. Ajustez le découpage ou `detail`, reconstruisez et réexportez.

Pour Confluence, livrez le `.drawio` (macro draw.io) et le `.drawio.png`
(à insérer dans la page). Gardez la description `.json` ou le `.csv` à
côté pour faire évoluer le plan.

Les flux entre applications ne font pas partie du POS : pour les montrer,
faites une cartographie applicative avec `drawio-diagram`, en reprenant
les mêmes noms.

draw.io Desktop est requis pour l'export (voir `check-prerequisites`).

## 5. Situer des options d'architecture dans le POS

```bash
uv run scripts/pos_impact.py options.json [--out-dir schemas/]
```

Pour chaque option, `placement` dit quelles applications elle crée (avec
zone, quartier et îlot), fait évoluer, remplace ou réutilise. Le script
vérifie les noms contre le POS (`pos`, relatif au `.json` ou `vault:<chemin>`),
compte les impacts, signale les redondances (nouvelle application dans un
îlot occupé sans `coexists`) et écrit le POS cible `pos-option-<id>.json` de
chaque option, à construire avec `pos_build.py`. `architecture-options`
l'appelle elle-même : ne le lancez à part que hors de ce skill.
