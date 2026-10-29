---
name: mockup-to-html
description: "Reproduit en HTML/CSS des maquettes d'écrans fournies en image (appel d'offres, cahier des charges, capture d'une application) : la page est décrite en JSON court (composants, textes, tokens du design system), le script écrit un HTML sémantique, accessible et responsive, découpe logos et photos dans la maquette, rend la page dans un navigateur local et la compare à la maquette (similarité, zones à reprendre). À utiliser pour transformer une maquette, un wireframe ou une capture d'écran en page HTML, en prototype ou en intégration de référence."
---

# mockup-to-html

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
regardez la maquette et décrivez la page ; le script écrit le HTML et le
CSS, puis vérifie le rendu. N'écrivez jamais de HTML ni de CSS à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Maquettes d'écrans en image (PNG, JPEG, WebP), par exemple tirées d'un appel d'offres par doc-to-markdown ; Description JSON de chaque page (page_build.py --schema) : arbre de composants, textes, tokens ; Facultatif : tokens du design system (design-system, ds_build.py --schema).
- **Sorties** : <nom>.html : page sémantique (header, nav, main, section, footer), accessible, responsive ; <nom>.css : variables CSS des tokens puis styles des composants ; assets/ : zones découpées dans la maquette (logos, photos, illustrations) ; <nom>.render.png : rendu de la page ; <nom>.compare.png : maquette, rendu et écarts côte à côte.
- **`page_build.py`** : Écrit le HTML sémantique et le CSS d'une page décrite par un arbre de composants (27 : section, row, grid, header, card, form, table, tabs, stepper...), contrôle composants, propriétés, variantes, tokens, images locales et zones découpées, accessibilité (h1 unique, niveaux de titres, textes alternatifs, contraste par section) ; rend la page dans un navigateur local réseau coupé, la compare à la maquette (similarité, zones les plus éloignées, hauteur) et contrôle le débordement sur mobile. Rapport JSON, codes de sortie : 0 page écrite (avertissements possibles : similarité faible, accessibilité, rendu non vérifié faute de navigateur) ; 1 description ou tokens invalides, composant, propriété, variante ou token inconnu, ressource externe, zone hors maquette, design-system absent ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `design-system` (`ds_build.py`, obligatoire) : tokens : schéma, valeurs par défaut, couleurs dérivées, variables CSS et contraste.
- **Passe la main** au skill `design-system` : les tokens (couleurs, typographie, espacements) ne sont pas encore définis : ds_extract.py --draft depuis les maquettes.
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

## 4. Livrer

Le dossier (`.html`, `.css`, `assets/`) s'ouvre tel quel dans un
navigateur. Plusieurs écrans : une description chacun, les mêmes tokens,
puis `ds_build.py design-system.json --pages *.json` (skill
`design-system`) pour l'inventaire des composants.
