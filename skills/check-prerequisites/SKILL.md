---
name: check-prerequisites
description: "Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (uv, draw.io Desktop, navigateur, LibreOffice en option) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable."
---

# check-prerequisites

Lance le script fourni avec ce skill, avec le groupe utile :

```bash
uv run scripts/doctor.py extraction   # uv (MarkItDown et Docling sont fournis par uv)
uv run scripts/doctor.py schemas      # uv, draw.io Desktop, navigateur ; Node.js en option
uv run scripts/doctor.py publication  # uv (Pandoc est fourni) ; LibreOffice en option
uv run scripts/doctor.py              # tout
```

Le chemin `scripts/doctor.py` est relatif au dossier de ce skill. Le script
n'a aucune dépendance et fonctionne sous Windows, macOS et Linux (aussi avec
`python3` ou `py`).

Le rapport JSON liste dans `missing` les outils obligatoires manquants (code
de sortie 1) et, dans `errors` et `warnings`, la commande d'installation de
chacun. Montre-la à l'utilisateur et n'installe rien sans son accord ; un
outil facultatif absent ne bloque rien.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Un groupe : extraction, schemas, publication ou tout (défaut).
- **Sorties** : Aucun fichier.
- **`doctor.py`** : Vérifie les outils locaux et donne la commande d'installation des manquants. Rapport JSON, codes de sortie : 0 tous les outils obligatoires sont présents ; 1 au moins un outil obligatoire manque, ou groupe inconnu.
- **Passe la main** à l'utilisateur : un outil manque : il l'installe lui-même, rien n'est installé sans son accord.

