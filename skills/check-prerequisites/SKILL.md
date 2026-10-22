---
name: check-prerequisites
description: "Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (MarkItDown, Docling, draw.io Desktop, Mermaid CLI, LikeC4, Playwright, Pandoc) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable."
---

# check-prerequisites

Lance le script fourni avec ce skill, avec le groupe utile :

```bash
bash scripts/doctor.sh extraction   # MarkItDown, Docling
bash scripts/doctor.sh schemas      # draw.io Desktop, Node.js, Mermaid CLI, LikeC4, Playwright
bash scripts/doctor.sh publication  # Pandoc
bash scripts/doctor.sh              # tout
```

Le chemin `scripts/doctor.sh` est relatif au dossier de ce skill.

Code de sortie 0 si tout est présent, 1 sinon. Si un outil manque, montre à
l'utilisateur la commande d'installation affichée et ne l'installe pas sans
son accord.
