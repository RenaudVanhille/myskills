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

**Hors ligne** : sur une machine qui n'aura pas de réseau, lancez d'abord,
connecté, `uv run scripts/doctor.py schemas --prefetch` : Mermaid et
Excalidraw sont téléchargés dans le cache de myskills à une version fixée,
et leur empreinte est vérifiée (un paquet différent est refusé). Ensuite,
`MYSKILLS_OFFLINE=1` interdit tout téléchargement : un rendu qui en aurait
besoin s'arrête avec la marche à suivre. Le cache est un dossier copiable
(`%LOCALAPPDATA%\myskills`, sinon `~/.cache/myskills`).

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Un groupe : extraction, schemas, publication ou tout (défaut) ; Facultatif : --prefetch, pour préparer une machine qui travaillera hors ligne.
- **Sorties** : Aucun fichier, sauf avec --prefetch : les bibliothèques de rendu dans le cache de myskills.
- **`doctor.py`** : Vérifie les outils locaux et donne la commande d'installation des manquants ; avec --prefetch, remplit le cache des bibliothèques de rendu (version fixée, empreinte vérifiée) pour travailler hors ligne. Rapport JSON, codes de sortie : 0 tous les outils obligatoires sont présents (et le préchargement a réussi) ; 1 au moins un outil obligatoire manque, groupe inconnu, ou préchargement impossible (réseau, empreinte différente).
- **Passe la main** à l'utilisateur : un outil manque : il l'installe lui-même, rien n'est installé sans son accord.

