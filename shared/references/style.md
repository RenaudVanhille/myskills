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

## Par format

### draw.io

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

### Mermaid

```text
classDef person fill:#fef3c7,stroke:#b45309,color:#1f2937
classDef system fill:#dbeafe,stroke:#1d4ed8,color:#1f2937
classDef external fill:#f3f4f6,stroke:#6b7280,color:#1f2937,stroke-dasharray:4 3
classDef db fill:#dcfce7,stroke:#15803d,color:#1f2937
classDef queue fill:#f3e8ff,stroke:#7e22ce,color:#1f2937
classDef alert fill:#fee2e2,stroke:#b91c1c,color:#1f2937
```

Formes : `client([Client])` pour une personne, `api[API]`, `db[(Base)]`,
`bus[/Bus/]`. Async : `-.->`. Le titre va dans l'en-tête
`---\ntitle: ...\n---`.

### Excalidraw

Rôles : `person`, `system`, `external`, `db`, `queue`, `alert`, `zone` dans le
format simplifié de `excalidraw_build.py`, qui applique ces couleurs. Police
Excalifont (style dessiné) pour un public non technique, Nunito pour un
schéma plus sobre.

### POS

Trois niveaux imbriqués, du plus large au plus fin, puis les applications :

```text
Zone          : rounded=1;arcSize=2;dashed=1;fillColor=<fond>;strokeColor=<bordure>;fontColor=<bordure>;fontSize=16;fontStyle=1;
Quartier      : rounded=1;arcSize=4;fillColor=<fond quartier>;strokeColor=<bordure>;fontColor=#1f2937;fontSize=14;fontStyle=1;
Îlot          : rounded=1;arcSize=6;fillColor=#ffffff;strokeColor=#d1d5db;fontColor=#1f2937;fontSize=13;
Application   : rounded=1;fillColor=<statut>;strokeColor=<statut>;fontColor=#1f2937;fontSize=14;
```

Chaque type de zone a sa teinte, reprise par ses quartiers ; les îlots
restent blancs pour que les statuts des applications ressortent. Échanges
reprend la couleur des files et bus, référentiels celle des données. En
vocabulaire TOGAF, les capacités de niveau 1 prennent ces teintes dans
l'ordre.

| Zone | Fond | Bordure, titre | Fond des quartiers |
| --- | --- | --- | --- |
| Pilotage | `#eef2ff` | `#4f46e5` | `#e0e7ff` |
| Opérations | `#fefce8` | `#ca8a04` | `#fef9c3` |
| Support | `#fdf2f8` | `#db2777` | `#fce7f3` |
| Référentiels | `#f0fdf4` | `#15803d` | `#dcfce7` |
| Échanges | `#faf5ff` | `#7e22ce` | `#f3e8ff` |

Disposition : zone de pilotage en haut, opérations (cœur de métier) au
milieu, support en bas, échanges à gauche, référentiels à droite. Les blocs
sont des conteneurs draw.io (`container=1`) : déplacer un quartier déplace
son contenu. `pos_build.py` (skill `urbanization-map`) applique ces règles.

### Cloud

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

### LikeC4

Le fichier `references/specification.c4` du skill `c4-architecture` définit
les types aux couleurs de la charte : `person` (amber), `system` et
`container` (primary), `component` (sky), `external` (gray, tirets),
`database` (green, forme storage), `queue` (indigo, forme queue), et la
relation `async` (tirets, flèche ouverte). LikeC4 trace ses relations en
tirets fins par défaut : c'est la convention de l'outil, gardez-la.
