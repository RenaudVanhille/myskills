# Découper et chiffrer le frontend

Détail de la section 6 du `SKILL.md`, à lire seulement pour un découpage
ou un chiffrage du frontend.

```bash
uv run scripts/ui_breakdown.py --target react-mui --component portail --out decoupage pages/*.json
```

Le rapport donne écrans, composants, motifs, réemploi et la charge à
trois points ; `decoupage.md` est le découpage à livrer. `--target` réduit
les composants fournis par la bibliothèque, `--component` rattache les lots
au composant web de l'option. Un écran de même structure qu'un autre, ou
semblable, ou fait de motifs, réutilise son lot (`reuse`). Les jours
viennent d'abaques donnés avant le lancement (section `frontend` des
abaques, `--abaques`), sinon par défaut : `calibrated` faux, à dire.
Après la revue UX (§ 4), `--ux revue.json` ajoute un lot par constat
retenu de gravité 2 ou plus (ce que la maquette ne montre pas : erreurs,
confirmations, aide), aux jours de l'abaque `ux` ; `ux_lots` les compte.
`estimate_build.py chiffrage.json --draft --lots decoupage.lots.json`
(skill `solution-estimate`) reprend ces lots.
