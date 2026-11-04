# Cibler une bibliothèque

Détail de la section 5 du `SKILL.md`, à lire seulement quand une
bibliothèque est demandée.

Sur demande, la même description donne la page dans une bibliothèque
(`--target`) ; ne réécrivez rien :

- `bootstrap` : classes et thème Bootstrap tirés des tokens, rendu et
  comparé comme la page HTML (Bootstrap à version fixée, dans le cache :
  `doctor.py maquettes --prefetch` avant un travail hors ligne) ;
- `react-mui`, `react-antd` : `<Nom>Page.tsx`, `theme.ts` (tokens et
  thème de la bibliothèque) et `App.tsx` ;
- `vue-vuetify` : `<Nom>Page.vue`, `vuetify.ts` (thème Vuetify tiré des
  tokens), `tokens.ts`, `App.vue`, `main.ts` ;
- `angular-material` : composant autonome (`<nom>-page.component.ts`,
  `.html`, `.css`), `tokens.ts` et `styles.scss` (thème Angular Material,
  couleurs exactes des tokens).

Pour React, Vue et Angular, le code est contrôlé mais pas rendu :
construisez aussi la cible `html`, qui sert de référence visuelle, et
dites que le rendu reste à vérifier dans le projet. Une autre
bibliothèque (PrimeVue, PrimeNG, Tailwind) : prenez la plus proche et
dites l'écart.
