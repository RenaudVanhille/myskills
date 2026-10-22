---
name: drawio-diagram
description: "Crée ou modifie un schéma draw.io (.drawio), le vérifie et l'exporte en PNG, SVG ou PDF modifiables. À utiliser pour les schémas destinés à Word, PowerPoint ou Confluence, ou qui demandent une mise en page précise."
---

# drawio-diagram

Les chemins `scripts/...` sont relatifs au dossier de ce skill.

## 1. Écrire le fichier

Un `.drawio` est un XML non compressé :

```xml
<mxfile>
  <diagram id="p1" name="Contexte">
    <mxGraphModel grid="1" gridSize="10" page="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
        <mxCell id="title" value="Paiement : vue d'ensemble" style="text;html=1;fontSize=20;fontStyle=1;align=left;" vertex="1" parent="1">
          <mxGeometry x="0" y="0" width="400" height="30" as="geometry"/>
        </mxCell>
        <mxCell id="api" value="API paiement" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#dbeafe;strokeColor=#1d4ed8;fontColor=#1f2937;fontSize=14;" vertex="1" parent="1">
          <mxGeometry x="0" y="80" width="160" height="70" as="geometry"/>
        </mxCell>
        <mxCell id="db" value="Paiements" style="shape=cylinder3;whiteSpace=wrap;html=1;boundedLbl=1;size=12;fillColor=#dcfce7;strokeColor=#15803d;fontColor=#1f2937;fontSize=14;" vertex="1" parent="1">
          <mxGeometry x="260" y="80" width="120" height="80" as="geometry"/>
        </mxCell>
        <mxCell id="api-db" value="enregistre" style="edgeStyle=orthogonalEdgeStyle;rounded=1;html=1;strokeColor=#374151;fontSize=12;endArrow=block;endFill=1;" edge="1" parent="1" source="api" target="db">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

- Les cellules `0` et `1` sont obligatoires ; tout le reste a `parent="1"`,
  ou l'identifiant d'une zone pour être dedans (coordonnées alors relatives à
  la zone).
- Identifiants lisibles (`api`, `api-db`), uniques.
- Styles : copiez ceux de `references/style.md` (section draw.io) selon le
  rôle de chaque élément.
- Placement : grille de 10, 60 à 80 px d'écart entre les formes, flux de
  gauche à droite. Laissez draw.io tracer les flèches (`source`/`target`, pas
  de points intermédiaires sauf besoin).
- Une page (`<diagram>`) par vue si le schéma a plusieurs niveaux.
- Ajoutez une légende (formes de 30 × 20 et texte) dès que plus d'un rôle
  ou d'un style de flèche apparaît.

Pour modifier un schéma existant, lisez-le, gardez les identifiants et ne
touchez qu'aux cellules concernées. S'il est compressé (texte en base64 dans
`<diagram>`), le script de vérification sait le lire ; réécrivez-le en XML
clair.

## 2. Vérifier

```bash
uv run scripts/check_drawio.py SCHEMA.drawio
```

Erreurs (à corriger) : XML illisible, identifiant en double, parent ou
extrémité de flèche introuvable. Avertissements (à regarder) : formes qui se
chevauchent, forme sans libellé, flèche non attachée, couleur hors charte,
pas de titre.

## 3. Exporter et relire

```bash
uv run ../diagram-export/scripts/export.py SCHEMA.drawio --format png
```

Le PNG `SCHEMA.drawio.png` garde le XML : il se rouvre dans draw.io. Ouvrez
l'image et vérifiez la lisibilité (libellés coupés, flèches qui se croisent
ou passent sous une forme). Corrigez les coordonnées et réexportez.

draw.io Desktop est requis pour l'export (voir `check-prerequisites`).
