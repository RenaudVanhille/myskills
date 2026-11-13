---
name: design-system
description: "Aide à définir un design system ou reprend celui du client (tokens W3C, variables CSS, thème MUI ou Ant Design), qui prime alors sur les maquettes : palette tirée des maquettes par script, rôles des couleurs proposés, tokens (couleurs, typographie, espacements, rayons, ombres) contrôlés (contrastes WCAG avec teinte corrigée proposée, couleurs en double, échelle irrégulière), inventaire des composants employés dans les pages, variables CSS, tokens au format W3C Design Tokens, documentation Markdown et page de référence (styleguide) rendue en local. À utiliser pour créer ou documenter un design system, une charte d'interface, des design tokens ou vérifier l'accessibilité d'une palette."
---

# design-system

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script
mesure, complète et contrôle ; vous décidez des rôles, des noms et des
principes.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Maquettes d'écrans en image (PNG, JPEG, WebP), pour en tirer la palette ; Tokens du design system en JSON (ds_build.py --schema), souvent le brouillon de ds_extract.py relu ; Facultatif : le design system existant du client (tokens W3C, variables CSS, thème MUI ou Ant Design), qui prime sur les maquettes ; Facultatif : descriptions des pages de mockup-to-html, pour l'inventaire des composants ; Facultatif : charte graphique ou contraintes du client (couleurs imposées, niveau d'accessibilité AA ou AAA).
- **Sorties** : <nom>.css : variables CSS (--color-*, --text-*, --space-*, --radius-*, --shadow-*) ; <nom>.tokens.json : tokens au format W3C Design Tokens (Style Dictionary, Tokens Studio) ; <nom>.md : documentation (principes, couleurs, contrastes WCAG, typographie, espacements, composants et emplois) ; <nom>.styleguide.json : page de référence décrite pour mockup-to-html ; avec --render, <nom>.styleguide.html et son rendu.
- **`ds_extract.py`** : Tire la palette des maquettes en local (réduction sans lissage, comptage, fusion des couleurs proches, part de surface), propose les rôles background, text, primary, secondary, surface et border, et écrit avec --draft un brouillon de tokens valide, dont les échelles (tailles de texte, espacements, rayons) sont mesurées par ui_analyze.py de mockup-to-html s'il est installé. Avec --against, compare les maquettes à un design system fourni et liste les couleurs qui s'en écartent. Rapport JSON (0 succès, 1 erreur).
- **`ds_import.py`** : Reprend un design system existant (tokens W3C, Style Dictionary ou Tokens Studio avec alias, variables CSS, thème MUI ou Ant Design en JSON ou .ts/.js, tokens de myskills) : valeurs normalisées, tokens rangés par nature, rôles des couleurs tirés des noms, couleurs sans rôle gardées ; écrit des tokens valides marqués source.locked (le design system fourni prime sur les maquettes). Rapport JSON (0 succès, 1 erreur).
- **`ds_build.py`** : Complète les couleurs (surface, bordure, texte secondaire, texte sur chaque couleur de fond), contrôle les contrastes WCAG 2.1 et propose une teinte qui passe, signale couleurs presque identiques, échelle de tailles irrégulière et espacement hors grille, fait l'inventaire des composants et des couleurs en dur des pages ; écrit variables CSS, tokens W3C, documentation et page de référence, rendue avec --render. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `mockup-to-html` (`page_build.py`, facultatif : sans lui, avertissement) : construire et rendre la page de référence (--render).
- **Dépend de** `mockup-to-html` (`ui_analyze.py`, facultatif : sans lui, avertissement) : mesurer tailles de texte, espacements et rayons des maquettes pour le brouillon (--draft).
- **Passe la main** au skill `mockup-to-html` : reproduire les maquettes en HTML avec ces tokens.
- **Passe la main** à l'agent `document-publisher` : la documentation du design system doit être livrée en Word, HTML ou XWiki.
- **Passe la main** à l'utilisateur : une couleur de la charte du client échoue au contraste : garder la marque ou prendre la teinte proposée.
- **Passe la main** à l'utilisateur : une maquette s'écarte du design system fourni : prendre le token le plus proche ou demander au client.

## 1. Design system fourni par le client

S'il existe (tokens W3C, Style Dictionary, variables CSS, thème MUI ou
Ant Design), il **prime sur les maquettes** : reprenez-le au lieu de tirer
la palette.

```bash
uv run scripts/ds_import.py client/tokens.json --out design-system.json --name "Nom du client"
uv run scripts/ds_extract.py maquettes/*.png --against design-system.json
```

Le premier rapport donne les rôles trouvés (`mapped`) et les tokens non
repris ; un rôle absent prend une valeur par défaut, à confirmer. Le
second liste les couleurs des maquettes qui s'écartent du design system
(`deviations`) : dans les pages, prenez le token le plus proche et
signalez l'écart. Ne modifiez pas les tokens repris (`source.locked`) :
un contraste insuffisant se signale au client, il ne se corrige pas.
Passez ensuite à la section 3.

## 2. Tirer la palette des maquettes

Sans design system fourni :

```bash
uv run scripts/ds_extract.py maquettes/*.png --draft design-system.json --name "Nom du produit"
```

Le rapport donne la palette (couleur, part de surface, rôle proposé). Le
brouillon porte `background`, `text`, `primary`, `secondary`, `surface`,
`border` ; si mockup-to-html est installé, les tailles de texte (OCR local,
Tesseract facultatif), les espacements et les rayons sont mesurés sur les
maquettes (`measures` du rapport, `--scale 2` pour un export en 2x), sinon
ce sont les valeurs par défaut. L'OCR estime les tailles à 1 ou 2 px près :
arrondissez `md` à la taille courante de la charte si elle est connue. Relisez les rôles sur **une**
maquette : la couleur des boutons d'action est `primary`, une seconde
couleur d'accent `secondary` ; une couleur de statut visible (erreur,
succès) va dans `danger`, `success`... Sans maquette, partez de la charte
du client ou de `ds_build.py --schema`.

## 3. Compléter les tokens

Dans `design-system.json` : `name`, `description`, `principles` (3 à 5,
tirés du contexte : public, accessibilité visée, ton), `fonts` (piles de
polices installées sur les postes, aucune police téléchargée),
`font_sizes`, `spacing` (grille de 4 px), `radii`, `shadows` et, si la
cible est AAA, `contrast.min` à 7. `components` documente les composants
retenus (`description`, `usage`, `variants`, `do`, `dont`). Ne recopiez
pas les valeurs par défaut que vous ne changez pas : le script les ajoute.
Pour un design system fourni, n'ajoutez que `principles` et `components`.

## 4. Construire et contrôler

```bash
uv run scripts/ds_build.py design-system.json [--pages pages/*.json] [--render]
```

- Erreurs : corrigez jusqu'à zéro (chemin et valeurs permises donnés).
- `contrast` : chaque paire insuffisante porte une teinte `suggestion` qui
  passe. Couleur libre : prenez-la. Couleur de la charte du client :
  gardez-la pour les fonds et les aplats, prenez la teinte proposée pour
  le texte, et dites-le à l'utilisateur.
- Couleurs presque identiques : fusionnez. Échelle irrégulière ou
  espacement hors grille : corrigez ou justifiez.
- `--pages` : composants employés et couleurs écrites en dur, à remplacer
  par un token ou à ajouter comme token.
- `--render` : la page de référence est construite par `mockup-to-html`
  (`<nom>.styleguide.html`, et son rendu). Ne relisez pas les fichiers
  produits : le rapport suffit.

## 5. Livrer

`design-system.css` (à lier dans les pages), `design-system.tokens.json`
(import Style Dictionary ou Tokens Studio), `design-system.md` (à publier
par `document-publisher` si besoin) et le styleguide. Toute nouvelle page
se décrit avec ces tokens (skill `mockup-to-html`).
