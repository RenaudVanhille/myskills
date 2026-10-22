# Charte graphique des schémas

Partagée par tous les skills de schémas. Source : `shared/references/style.md`,
copiée dans `references/style.md` de chaque skill par `scripts/build.py`, avec
les seules règles du format de ce skill.
Le but : qu'un même élément ait la même couleur et la même forme, quel que
soit le format.

## Rôles et couleurs

| Rôle | Forme | Fond | Bordure |
| --- | --- | --- | --- |
| Personne, acteur | personnage ou ellipse | `#fef3c7` | `#b45309` |
| Notre système, conteneur, service | rectangle arrondi | `#dbeafe` | `#1d4ed8` |
| Système externe | rectangle arrondi, bordure en tirets | `#f3f4f6` | `#6b7280` |
| Base de données, stockage | cylindre | `#dcfce7` | `#15803d` |
| File, bus, évènement | parallélogramme ou rectangle | `#f3e8ff` | `#7e22ce` |
| Point de vigilance, erreur | rectangle | `#fee2e2` | `#b91c1c` |
| Zone, frontière (équipe, réseau, SI) | rectangle sans fond, tirets | aucun | `#9ca3af` |

- Texte : `#1f2937`. Flèches : `#374151`.
- Appel synchrone : trait plein. Asynchrone (message, évènement) : tirets.
- Une couleur ne sert qu'à un rôle. Pas d'autre couleur sans raison.

## Texte

- Police : celle du format (Helvetica dans draw.io, Excalifont dans Excalidraw).
- Taille : 14 px pour les éléments, 12 px pour les libellés de flèche, 20 px pour
  le titre.
- Libellé d'élément : un nom, plus éventuellement la technologie entre
  crochets (`API paiement [Java]`) pour un public technique.
- Libellé de flèche : un verbe (`appelle`, `publie`, `lit`), jamais vide sauf
  évidence.

## Règles de composition

- Toujours un titre. Une légende dès que plus d'une couleur ou d'un style de
  trait est utilisé.
- Sens de lecture : de gauche à droite ou de haut en bas, l'utilisateur en
  premier.
- Public non technique : 7 éléments maximum, pas de sigle ni de technologie,
  des verbes simples.
- Public technique : 15 à 20 éléments maximum par vue ; au-delà, faire
  plusieurs vues.
- Aucun chevauchement d'éléments ni de libellés, flèches sans croisement
  quand c'est possible.
- Nom de fichier : `<sujet>-<vue>` en minuscules et tirets
  (`paiement-conteneurs.drawio`), l'export garde le même nom.
