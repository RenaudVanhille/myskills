---
name: check-prerequisites
description: "Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (MarkItDown, Docling, draw.io Desktop, Node.js, navigateur) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable."
---

# check-prerequisites

Lance le script fourni avec ce skill, avec le groupe utile :

```bash
python scripts/doctor.py extraction   # MarkItDown, Docling
python scripts/doctor.py schemas      # draw.io Desktop, Node.js, uv, navigateur
python scripts/doctor.py publication  # uv (Pandoc est fourni)
python scripts/doctor.py              # tout
```

Le chemin `scripts/doctor.py` est relatif au dossier de ce skill. Le script
n'a aucune dépendance et fonctionne sous Windows, macOS et Linux (`python3`
ou `py` selon le système, ou `uv run scripts/doctor.py`).

Code de sortie 0 si tout est présent, 1 sinon. Si un outil manque, montre à
l'utilisateur la commande d'installation affichée et ne l'installe pas sans
son accord.

## Contrat

Généré depuis [`contract.json`](contract.json), qui fait foi : les rapports
JSON des scripts y sont décrits en JSON Schema.

- **Entrées** : Un groupe : extraction, schemas, publication ou tout (défaut).
- **Sorties** : Aucun fichier.
- **`doctor.py`** : Vérifie les outils locaux et affiche la commande d'installation des manquants.
  - Rapport (texte) : Une ligne par outil : [ok], [manquant] ou [facultatif], suivie de la commande d'installation.
  - Codes de sortie : 0 tous les outils obligatoires sont présents ; 1 au moins un outil manque.
- **Passe la main** à l'utilisateur : un outil manque : il l'installe lui-même, rien n'est installé sans son accord.

