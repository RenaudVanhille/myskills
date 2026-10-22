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

Dans une cartographie applicative ou un plan d'occupation des sols (POS),
les applications sont colorées par statut. « En place » garde la couleur de
notre système, « à remplacer » celle du point de vigilance ; deux couleurs
s'ajoutent, réservées à ces statuts :

| Statut d'application | Fond | Bordure |
| --- | --- | --- |
| En place | `#dbeafe` | `#1d4ed8` |
| À faire évoluer | `#ffedd5` | `#c2410c` |
| À remplacer ou retirer | `#fee2e2` | `#b91c1c` |
| À créer (tirets) | `#ccfbf1` | `#0f766e` |
| Externe, SaaS (tirets) | `#f3f4f6` | `#6b7280` |

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

## draw.io

```text
Personne      : shape=umlActor;verticalLabelPosition=bottom;fillColor=#fef3c7;strokeColor=#b45309;fontColor=#1f2937;
Système       : rounded=1;whiteSpace=wrap;html=1;fillColor=#dbeafe;strokeColor=#1d4ed8;fontColor=#1f2937;fontSize=14;
Externe       : rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor=#f3f4f6;strokeColor=#6b7280;fontColor=#1f2937;fontSize=14;
Base          : shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=12;fillColor=#dcfce7;strokeColor=#15803d;fontColor=#1f2937;fontSize=14;
File          : shape=parallelogram;perimeter=parallelogramPerimeter;whiteSpace=wrap;html=1;fillColor=#f3e8ff;strokeColor=#7e22ce;fontColor=#1f2937;
Vigilance     : rounded=0;whiteSpace=wrap;html=1;fillColor=#fee2e2;strokeColor=#b91c1c;fontColor=#1f2937;
Zone          : rounded=1;whiteSpace=wrap;html=1;dashed=1;fillColor=none;strokeColor=#9ca3af;verticalAlign=top;align=left;spacingLeft=8;fontColor=#6b7280;
Flèche        : edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#374151;fontSize=12;endArrow=block;endFill=1;
Flèche async  : edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#374151;fontSize=12;dashed=1;endArrow=open;
Titre         : text;html=1;fontSize=20;fontStyle=1;align=left;
```
