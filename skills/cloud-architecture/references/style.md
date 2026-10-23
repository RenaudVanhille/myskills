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

## Cloud

Les services cloud gardent l'icône officielle de leur fournisseur (AWS,
Azure, GCP, Kubernetes), livrée dans draw.io, avec ses couleurs : un
architecte la reconnaît au premier coup d'œil. Les groupes du fournisseur
(région, VPC, sous-réseau public ou privé, security group, cluster,
namespace) gardent aussi leurs couleurs. Ces styles portent `shape=mxgraph.*`,
`image=` ou `vendor=1` et `check_drawio.py` ne les compte pas hors charte.
Le reste suit la charte : texte `#1f2937`, libellé sous l'icône en 12 px
sur fond blanc, services génériques (`service`, `db`, `queue`,
`external`) aux couleurs des rôles.

```text
Flux synchrone   : strokeColor=#374151;endArrow=block;endFill=1;
Flux asynchrone  : strokeColor=#374151;dashed=1;endArrow=open;
Réplication      : strokeColor=#7e22ce;dashed=1;dashPattern=1 3;strokeWidth=2;
Traverse une frontière (vue threats) : strokeColor=#b91c1c;strokeWidth=2;
Frontière de confiance : dashed=1;dashPattern=8 4;strokeWidth=2;strokeColor=#b91c1c;fillColor=none;
Étape de pipeline : fillColor=#f9fafb;strokeColor=#d1d5db;
Objectifs RPO/RTO : fillColor=#fef3c7;strokeColor=#b45309;
```

Une région passive (PRA) est atténuée (`opacity=60`) et son nom suivi de
« (passif) ». `cloud_build.py` (skill `cloud-architecture`) applique ces
règles.
