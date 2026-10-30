---
name: mockup-to-html
description: "Reproduit en HTML/CSS des maquettes d'écrans fournies en image (appel d'offres, cahier des charges, capture d'une application) : la page est décrite en JSON court (composants, textes, tokens du design system), le script écrit un HTML sémantique, accessible et responsive, découpe logos et photos dans la maquette, rend la page dans un navigateur local et la compare à la maquette (similarité, zones à reprendre) ; la même description donne la page en Bootstrap, React MUI ou Ant Design, le découpage en composants et les lots du chiffrage frontend. À utiliser pour transformer une maquette, un wireframe ou une capture d'écran en page HTML, en prototype ou en intégration de référence, ou pour découper et chiffrer un frontend."
---

# mockup-to-html

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
regardez la maquette et décrivez la page ; le script écrit le HTML et le
CSS, puis vérifie le rendu. N'écrivez jamais de HTML ni de CSS à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Maquettes d'écrans en image (PNG, JPEG, WebP), par exemple tirées d'un appel d'offres par doc-to-markdown ; Description JSON de chaque page (page_build.py --schema) : arbre de composants, textes, tokens ; Facultatif : tokens du design system (design-system, ds_build.py --schema).
- **Sorties** : <nom>.html : page sémantique (header, nav, main, section, footer), accessible, responsive ; <nom>.css : variables CSS des tokens puis styles des composants ; assets/ : zones découpées dans la maquette (logos, photos, illustrations) ; <nom>.render.png : rendu de la page ; <nom>.compare.png : maquette, rendu et écarts côte à côte ; Avec --target react-mui ou react-antd : <Nom>Page.tsx, theme.ts (tokens, thème de la bibliothèque) et App.tsx ; avec --target bootstrap : vendor/bootstrap-<version>.min.css ; decoupage.json, .md, .csv : composants, motifs répétés, écrans et lots du chiffrage frontend ; decoupage.lots.json pour solution-estimate.
- **`page_build.py`** : Écrit le HTML sémantique et le CSS d'une page décrite par un arbre de composants (27 : section, row, grid, header, card, form, table, tabs, stepper...), contrôle composants, propriétés, variantes, tokens, images locales et zones découpées, accessibilité (h1 unique, niveaux de titres, textes alternatifs, contraste par section) ; rend la page dans un navigateur local réseau coupé, la compare à la maquette (similarité, zones les plus éloignées, hauteur) et contrôle le débordement sur mobile. Cibles : HTML, Bootstrap (version fixée, thème tiré des tokens, rendu et comparé de même), React avec MUI ou Ant Design (page TSX, thème et App ; JSX contrôlé, rendu non vérifié, la cible HTML sert de référence). Rapport JSON, codes de sortie : 0 page écrite (avertissements possibles : similarité faible, accessibilité, rendu non vérifié faute de navigateur) ; 1 description ou tokens invalides, composant, propriété, variante ou token inconnu, ressource externe, zone hors maquette, design-system absent, Bootstrap absent du cache hors ligne, JSX mal formé ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`ui_breakdown.py`** : Découpe les écrans décrits en composants (emplois, écrans, variantes, composant de la bibliothèque visée, complexité par règles), repère les motifs répétés (composants composés candidats), classe les écrans, et écrit les lots du chiffrage frontend à trois points au format de solution-estimate (composants, motifs, écrans, lots transverses), contrôlés contre son schéma ; abaques réglables. Rapport JSON, codes de sortie : 0 découpage et lots écrits ; 1 page ou règles invalides, lots hors du schéma de solution-estimate ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `design-system` (`ds_build.py`, obligatoire) : tokens : schéma, valeurs par défaut, couleurs dérivées, variables CSS et contraste.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : contrôler les lots frontend contre le schéma des lots du chiffrage.
- **Passe la main** au skill `design-system` : les tokens (couleurs, typographie, espacements) ne sont pas encore définis : ds_extract.py --draft depuis les maquettes.
- **Passe la main** au skill `solution-estimate` : chiffrer le frontend : estimate_build.py --draft --frontend decoupage.lots.json.
- **Passe la main** à l'agent `document-extractor` : les maquettes sont dans un PDF, un PowerPoint ou un Word : en extraire les images.
- **Passe la main** à l'agent `document-publisher` : les pages doivent être livrées dans un document Word ou un site XWiki.
- **Passe la main** à l'utilisateur : une maquette est ambiguë (état d'un écran, contenu masqué, interaction) : la question à poser.

## 1. Préparer

- Maquettes dans un PDF, un PowerPoint ou un Word : l'agent
  `document-extractor` en extrait d'abord les images.
- Tokens : si le design system n'existe pas, faites-le d'abord avec le
  skill `design-system` (`ds_extract.py maquettes/*.png --draft
  design-system.json`, puis `ds_build.py`). Plusieurs maquettes d'un même
  dossier partagent un seul fichier de tokens.

## 2. Décrire la page

Un fichier par écran, `accueil.json` (`uv run scripts/page_build.py
--schema` donne sa forme) : `title`, `mockup` (l'image, relative au
fichier), `tokens` (`design-system.json`), `scale` si la maquette est
exportée en 2x, et `body`, la liste des blocs de haut en bas.

Composants : `header` (`text` du logo ou `crop` de son image, `items` de
navigation, `actions`), `section` (bande pleine largeur, `background`,
`children`), `row` (`columns` en proportions `[2, 1]`), `grid` (`columns`
en nombre), `stack`, `heading` (`level`, `size`), `text` (`muted`, `size`),
`button` et `buttons` (`variant` : primary, secondary, outline, ghost,
danger), `link`, `image` (`crop` : zone `[x, y, largeur, hauteur]` de la
maquette, ou `src` local ; `alt` toujours), `card` (`title`, `text`,
`crop`, `actions`), `form` (`fields` : `label`, `type`, `options`,
`required` ; `columns` 1 ou 2), `table` (`headers`, `rows`), `list`,
`badge`, `alert`, `tabs`, `stepper`, `breadcrumb` (`items`, `current`),
`stat`, `search`, `box`, `divider`, `spacer`, `footer` (`groups`, `text`).

- Couleurs, tailles et espacements par **nom de token** (`"background":
  "primary"`, `"gap": "lg"`) ; une couleur en `#rrggbb` est signalée hors
  design system. Sur un fond coloré, le texte prend `on-<fond>` seul.
- Logos, photos, illustrations, icônes : `crop` dans la maquette, jamais
  d'URL (aucune ressource externe, rendu local).
- Recopiez les textes de la maquette ; un texte illisible se signale, il
  ne s'invente pas. Lorem ipsum seulement s'il y est.
- Un seul `heading` de niveau 1 ; les niveaux se suivent.

## 3. Construire et comparer

```bash
uv run scripts/page_build.py accueil.json
```

Corrigez jusqu'à zéro erreur (le chemin, la valeur et les valeurs permises
sont donnés). Puis lisez `similarity` (0 : pas mieux qu'une page unie,
1 : identique) et `zones` (cadres de la maquette les plus éloignés, en
pixels) :

- au-dessus de 0,6 sans avertissement de mise en page : livrez ;
- en dessous, ou `height_ratio` hors de 0,85 à 1,15 : regardez **une
  fois** `accueil.compare.png` (maquette, rendu, écarts en rouge),
  corrigez la description sur les zones signalées et relancez ; deux
  reprises au plus, puis livrez en disant ce qui reste.

Ne relisez ni `accueil.html` ni le CSS : le rapport suffit. Traitez les
avertissements d'accessibilité (titre, `alt`, contraste) et
`mobile_overflow`. Sans navigateur, la page est écrite mais non vérifiée :
dites-le et proposez `check-prerequisites` (groupe `maquettes`).

## 4. Cibler une bibliothèque

Sur demande, la même description donne la page dans une bibliothèque
(`--target`) ; ne réécrivez rien :

- `bootstrap` : classes et thème Bootstrap tirés des tokens, rendu et
  comparé comme la page HTML (Bootstrap à version fixée, dans le cache :
  `doctor.py maquettes --prefetch` avant un travail hors ligne) ;
- `react-mui`, `react-antd` : `<Nom>Page.tsx`, `theme.ts` (tokens et
  thème de la bibliothèque) et `App.tsx`. Le JSX est contrôlé mais pas
  rendu : construisez aussi la cible `html`, qui sert de référence
  visuelle, et dites que le rendu React reste à vérifier dans le projet.

## 5. Découper et chiffrer le frontend

```bash
uv run scripts/ui_breakdown.py --target react-mui --component portail --out decoupage pages/*.json
```

Le rapport donne écrans, composants, motifs répétés et la charge à trois
points ; `decoupage.md` est le découpage à livrer. `--target` réduit la
charge des composants fournis par la bibliothèque, `--component` rattache
les lots au composant web de l'option d'architecture. Les jours viennent
d'abaques par complexité : des hypothèses, à dire comme telles ; des
abaques propres au client se donnent dans `--rules` (`--schema`). Pour le
chiffrage, `estimate_build.py chiffrage.json --draft --frontend
decoupage.lots.json` (skill `solution-estimate`) reprend ces lots à la
place du lot global du portail.

## 6. Livrer

Le dossier (`.html`, `.css`, `assets/`) s'ouvre tel quel dans un
navigateur. Plusieurs écrans : une description chacun, les mêmes tokens,
puis `ds_build.py design-system.json --pages *.json` (skill
`design-system`) pour l'inventaire des composants.
