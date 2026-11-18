---
name: mockup-to-html
description: "Reproduit en HTML/CSS des maquettes d'écrans fournies en image (appel d'offres, cahier des charges, capture d'une application) : la page est décrite en JSON court (composants, textes, tokens du design system), le script écrit un HTML sémantique, accessible et responsive, découpe logos et photos dans la maquette, rend la page dans un navigateur local et la compare à la maquette (similarité, zones à reprendre) ; la même description donne la page en Bootstrap, React (MUI, Ant Design), Vue (Vuetify) ou Angular (Angular Material), le découpage en composants et les lots du chiffrage frontend. À utiliser pour transformer une maquette, un wireframe ou une capture d'écran en page HTML, en prototype ou en intégration de référence, ou pour découper et chiffrer un frontend."
---

# mockup-to-html

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Un script
mesure la maquette et en tire une ébauche ; vous la corrigez en regardant
la maquette ; le script écrit le HTML et le CSS, puis compare le rendu à la
maquette bloc par bloc. N'écrivez jamais de HTML ni de CSS à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Maquettes d'écrans en image (PNG, JPEG, WebP), par exemple tirées d'un appel d'offres par doc-to-markdown ; Description JSON de chaque page (page_build.py --schema) : arbre de composants, textes, tokens ; Facultatif : tokens du design system (design-system, ds_build.py --schema).
- **Sorties** : <maquette>.analysis.json : mise en page mesurée (bandes, colonnes, cadres, textes, mesures) ; avec --draft, <maquette>.json : ébauche de description de page ; <nom>.html : page sémantique (header, nav, main, section, footer), accessible, responsive ; <nom>.css : variables CSS des tokens puis styles des composants ; assets/ : zones découpées dans la maquette (logos, photos, illustrations) ; <nom>.render.png : rendu de la page ; <nom>.compare.png : maquette, rendu et écarts côte à côte ; dans le rapport, fidélité bloc par bloc et écarts rattachés aux nœuds ; Avec --target react-mui ou react-antd : <Nom>Page.tsx, theme.ts (tokens, thème de la bibliothèque) et App.tsx ; avec --target vue-vuetify : <Nom>Page.vue, vuetify.ts, tokens.ts, App.vue, main.ts ; avec --target angular-material : <nom>-page.component.ts, .html, .css, tokens.ts, styles.scss ; avec --target bootstrap : vendor/bootstrap-<version>.min.css ; <nom>.ux.md : revue UX et accessibilité (contrôles WCAG sur le rendu, constats par heuristique de Nielsen, triés par gravité) ; decoupage.json, .md, .csv : composants, motifs répétés, écrans et lots du chiffrage frontend ; decoupage.lots.json pour solution-estimate.
- **`ui_analyze.py`** : Mesure la mise en page d'une maquette d'écran, en local et sans modèle téléchargé : bandes (fond, filet), colonnes, cadres (aplats, cadres à bordure, images, rayon), textes avec position, taille de police estimée et couleur par OCR local (Tesseract ; sans lui, mise en page seule, signalé), tailles, espacements et rayons récurrents ; écrit l'analyse et, avec --draft, une ébauche de description de page pour page_build.py (bandes en sections, colonnes en grille ou rangée, cartes, titres, textes exacts, boutons, tokens les plus proches, largeur du conteneur), contrôlée contre son schéma ; un espacement ou une taille sans token proche est signalé avec la valeur à ajouter au design system. Rapport JSON (0 succès, 1 erreur).
- **`page_build.py`** : Écrit le HTML sémantique et le CSS d'une page décrite par un arbre de composants (27 : section, row, grid, header, card, form, table, tabs, stepper...), contrôle composants, propriétés, variantes, tokens, images locales et zones découpées, accessibilité (h1 unique, niveaux de titres, textes alternatifs, contraste par section) ; rend la page dans un navigateur local réseau coupé, la compare à la maquette bloc par bloc (fidélité : textes présents, position et taille des textes, bandes, cadres, image ; écarts rattachés au nœud de la description, en px CSS, avec le token proche) et en similarité d'image et contrôle le débordement sur mobile. Cibles : HTML, Bootstrap (version fixée, thème tiré des tokens, rendu et comparé de même), React avec MUI ou Ant Design (page TSX, thème et App ; JSX contrôlé), Vue 3 avec Vuetify (composant .vue, thème Vuetify) ou Angular avec Angular Material (composant autonome, styles.scss) ; gabarits contrôlés ; rendu non vérifié pour ces trois familles, la cible HTML sert de référence. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`ux_review.py`** : Revue UX et accessibilité des pages décrites, sans modèle pour les contrôles : rendu local (Playwright, réseau coupé) de la même description que page_build.py, contraste réel de chaque texte sur son fond (WCAG 1.4.3, AAA 1.4.6), nom accessible des boutons, liens et champs (4.1.2), image sans alt (1.1.1), taille des cibles (2.5.8 avec son exception d'espacement, 44 px en AAA), texte sous 12 px, tableau sans en-tête, langue, zone principale, débordement à 390 px, plus d'un bouton primary ; chaque écart rattaché au nœud de la description. Valide les constats de jugement du modèle (heuristiques de Nielsen h1 à h10 ou a11y, gravité 1 à 4, nœud existant) et écrit <page>.ux.md trié par gravité. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`ui_breakdown.py`** : Découpe les écrans décrits en composants (emplois, écrans, variantes, composant de la bibliothèque visée, complexité par règles), repère les motifs répétés (composants composés candidats), classe les écrans, et écrit les lots du chiffrage frontend à trois points au format de solution-estimate (composants, motifs, écrans, lots transverses), contrôlés contre son schéma ; réemploi entre écrans (même structure, écrans semblables, écrans faits de motifs) et motif compté pour un composant ; avec --ux, un lot par constat UX retenu (gravité au moins ux.min_severity, jours par gravité) ; abaques donnés avant le lancement (section frontend de ~/.myskills/abaques.json, de la mission ou de --abaques), sinon par défaut et signalés. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `design-system` (`ds_build.py`, obligatoire) : tokens : schéma, valeurs par défaut, couleurs dérivées, variables CSS et contraste.
- **Dépend de** `solution-estimate` (`estimate_build.py`, facultatif : sans lui, avertissement) : contrôler les lots frontend contre le schéma des lots du chiffrage.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Passe la main** au skill `design-system` : les tokens (couleurs, typographie, espacements) ne sont pas encore définis : ds_extract.py --draft depuis les maquettes.
- **Passe la main** au skill `solution-estimate` : chiffrer le frontend : estimate_build.py --draft --lots decoupage.lots.json.
- **Passe la main** à l'agent `document-extractor` : les maquettes sont dans un PDF, un PowerPoint ou un Word : en extraire les images.
- **Passe la main** à l'agent `document-publisher` : les pages doivent être livrées dans un document Word ou un site XWiki.
- **Passe la main** à l'utilisateur : une maquette est ambiguë (état d'un écran, contenu masqué, interaction) : la question à poser.

## 1. Préparer

- Maquettes dans un PDF, un PowerPoint ou un Word : l'agent
  `document-extractor` en extrait d'abord les images.
- Tokens : un design system fourni par le client se reprend avec
  `ds_import.py` (skill `design-system`) et prime sur les maquettes ;
  sinon, faites-le d'abord avec le skill `design-system` (`ds_extract.py maquettes/*.png --draft
  design-system.json`, puis `ds_build.py`). Plusieurs maquettes d'un même
  dossier partagent un seul fichier de tokens.

## 2. Décrire la page

Commencez par mesurer la maquette, sans rien estimer à l'œil :

```bash
uv run scripts/ui_analyze.py maquettes/accueil.png --tokens design-system.json --draft --out-dir pages
```

Le script mesure bandes, colonnes, cadres, rayons et, par OCR local
(Tesseract), les textes exacts et leur taille ; il écrit
`pages/accueil.json`, une ébauche de description, et signale les mesures
sans token proche (valeur à ajouter au design system). Regardez **une
fois** la maquette pour corriger l'ébauche : rôle des blocs (carte,
formulaire, tableau, onglets...), composants que le script ne devine pas,
textes mal lus, niveaux de titres. Ne déplacez rien à l'œil : les
positions et tailles viennent des mesures. Sans Tesseract, l'ébauche n'a
pas les textes : recopiez-les.

Un fichier par écran, `accueil.json` (`uv run scripts/page_build.py
--schema` donne sa forme) : `title`, `mockup` (l'image, relative au
fichier), `tokens` (`design-system.json`), `scale` si la maquette est
exportée en 2x, et `body`, la liste des blocs de haut en bas.

Composants : `section`, `row`, `grid`, `stack`, `box`, `sidebar`
(application avec barre latérale), `header`, `breadcrumb`, `tabs`,
`stepper`, `pagination`, `footer`, `heading`, `text`, `link`, `list`,
`badge`, `alert`, `image`, `icon`, `avatar`, `card`, `stat`, `graph` (barres,
courbe, anneau), `table`, `button`, `buttons`, `search`, `form` (dont
`switch`), `modal`, `divider`, `spacer`. Détail dans
`references/composants.md`, à lire seulement pour un composant inconnu.

- Largeurs et hauteurs en pixels seulement où aucun token ne convient :
  `width` d'un `button` ou d'une `box`, `height` d'une `card` (hauteur
  minimale), d'une `image` ou d'une `box`.
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
sont donnés). Puis lisez `fidelity` : la maquette et le rendu sont
analysés de la même façon et comparés bloc par bloc (`texts` : textes de
la maquette présents ; `positions` : place et taille des textes ;
`bands` : bandes de la page ; `frames` : cartes, boutons, images ;
`image` : similarité d'image). `issues` donne les écarts, les plus graves
d'abord, chacun rattaché au nœud de la description (`body/2/children/0`),
en px CSS, avec le token proche :

- `score` d'au moins 0,85 : livrez ;
- en dessous : corrigez les nœuds cités dans `issues` (padding, taille,
  hauteur, texte manquant ou inventé) et relancez, trois reprises au plus,
  puis livrez en disant ce qui reste. Un écart que le vocabulaire ne sait
  pas corriger se signale, il ne se force pas.

Regardez `accueil.compare.png` (maquette, rendu, écarts en rouge) seulement
si `issues` n'explique pas un score bas. `similarity` et `zones` restent
dans le rapport pour mémoire ; seuls, ils ne voient ni le texte ni les
petits écarts.

Ne relisez ni `accueil.html` ni le CSS : le rapport suffit. Traitez les
avertissements d'accessibilité (titre, `alt`, contraste) et
`mobile_overflow`. Sans navigateur, la page est écrite mais non vérifiée :
dites-le et proposez `check-prerequisites` (groupe `maquettes`).

## 4. Revoir l'UX et l'accessibilité

```bash
uv run scripts/ux_review.py revue.json
```

`revue.json` (`--schema`) : `pages`, `level` (AA, AAA) et `findings`.
Premier passage avec `"findings": []` : le script rend chaque page et
contrôle contraste réel, noms accessibles, taille des cibles, textes sous
12 px, tableaux, langue, boutons primary ; `issues` cite le nœud.
Corrigez les gravités 3 et 4 dans la description. Puis, sur **une**
lecture de la maquette et des `issues`, écrivez vos constats de jugement
(heuristique h1 à h10 de Nielsen ou a11y, gravité 1 à 4, nœud, problème,
correction : parcours, libellés, retour d'état, prévention des erreurs) et
relancez : `<page>.ux.md` est la revue à livrer.

## 5. Cibler une bibliothèque

Sur demande, la même description donne la page dans une bibliothèque
(`--target` : `bootstrap`, `react-mui`, `react-antd`, `vue-vuetify`,
`angular-material`) ; ne réécrivez rien. Fichiers produits, rendu et
écarts : `references/cibles.md`, à lire seulement pour cette demande.

## 6. Découper et chiffrer le frontend

`ui_breakdown.py --target <bibliothèque> --component <composant> --out
decoupage pages/*.json` donne écrans, composants, réemploi et charge à
trois points (`decoupage.md`, `decoupage.lots.json` pour
`estimate_build.py --draft --lots`). Options (`--abaques`, `--ux
revue.json`) et règles de réemploi : `references/decoupage.md`, à lire
seulement pour un découpage.

## 7. Livrer

Le dossier (`.html`, `.css`, `assets/`) s'ouvre tel quel dans un
navigateur. Plusieurs écrans : une description chacun, les mêmes tokens,
puis `ds_build.py design-system.json --pages *.json` (skill
`design-system`) pour l'inventaire des composants.
