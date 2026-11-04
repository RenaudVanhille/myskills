# Capitaliser les retours

À lire en fin de mission ou à la demande.

```bash
uv run scripts/lessons.py MISSION [MISSION...]
uv run scripts/lessons.py --apply retenues.json --to mission|utilisateur
```

Lisez le rapport : `recurring`, `proposed` (règles proposées, dans
`lecons.json`), `covered` (déjà couvertes). Montrez les règles proposées à
l'utilisateur ; ne mettez dans `retenues.json` que celles qu'il garde,
corrigées (libellé, motif) : jamais sans son accord.
