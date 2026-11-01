# Vocabulaire des descriptions de page

Détail des composants de `page_build.py` ; la forme exacte est donnée par
`uv run scripts/page_build.py --schema`. Chargez ce fichier seulement si un
composant de l'ébauche ou de la maquette vous est inconnu.

## Mise en page

- `section` : bande pleine largeur ; `background`, `padding`, `width`
  (full, contained), `children`.
- `row` : colonnes en proportions (`columns: [2, 1]`), `gap`, `valign`.
- `grid` : `columns` en nombre, `gap` ; cartes ou statistiques en série.
- `stack` : empilement vertical ou horizontal (`direction`, `gap`).
- `box` : bloc libre (`width` en px, `height`, `background`, `padding`).
- `divider`, `spacer`.
- `sidebar` : application avec barre latérale ; `text` (marque) ou `crop`
  (logo), `items` (`text`, `href`, `icon`, `active`), `width` en px,
  `children` = contenu principal. Une seule par page, au premier niveau.

## En-tête, navigation, pied

- `header` : `text` du logo ou `crop` de son image, `items` de navigation,
  `actions` (boutons).
- `breadcrumb` (`items`, `current`), `tabs`, `stepper`, `pagination`
  (`pages`, `current`).
- `footer` : `groups` de liens, `text`.

## Contenu

- `heading` (`level`, `size`), `text` (`muted`, `size`), `link`, `list`,
  `badge`, `alert` (`variant` : info, success, warning, danger).
- `image` : `crop` `[x, y, largeur, hauteur]` de la maquette ou `src`
  local, `alt` toujours (`""` si décorative), `width` et `height` en px
  pour une image plus petite que sa colonne (logo, avatar découpé).
- `icon` : `name` d'une icône du jeu intégré (home, search, user, users,
  bell, settings, menu, close, plus, check, edit, trash, filter, download,
  upload, calendar, mail, phone, file, folder, chart, dashboard, list,
  logout, lock, info, warning, help, star, heart, cart, eye, chevron-*,
  arrow-right, more, refresh...) ou `crop` ; `label` si elle porte un
  sens, sinon décorative ; `size`.
- `avatar` : `text` (initiales calculées) ou `crop`, `size` sm, md, lg.
- `card` : `title`, `text`, `crop`, `actions`, `children`.
- `stat` : chiffre clé (`value`, `text`).
- `graph` : `variant` bar, line ou donut, `items` (`text`, `value`),
  `title`, `height` ; SVG en ligne aux couleurs des tokens, résumé lisible
  par les lecteurs d'écran.
- `table` : `headers`, `rows`.

## Actions et saisie

- `button`, `buttons` : `variant` primary, secondary, outline, ghost,
  danger ; un seul primary par écran.
- `search`.
- `form` : `fields` (`label`, `type` text, email, password, number, date,
  select, textarea, checkbox, radio, switch ; `options`, `required`),
  `columns` 1 ou 2, `actions`.
- `modal` : boîte de dialogue montrée ouverte ; `title`, `text`,
  `children`, `actions`.
