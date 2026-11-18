---
name: check-prerequisites
description: "Vérifie que les outils locaux nécessaires aux skills de myskills sont installés (uv, draw.io Desktop, navigateur, LibreOffice en option) et indique comment installer ceux qui manquent. À utiliser avant une première conversion ou un premier schéma, ou quand une commande est introuvable."
---

# check-prerequisites

Lance le script fourni avec ce skill, avec le groupe utile :

```bash
uv run scripts/doctor.py extraction   # uv (MarkItDown et Docling sont fournis par uv) ; modèles Docling, Tesseract en option
uv run scripts/doctor.py video        # uv ; modèle de transcription Whisper
uv run scripts/doctor.py schemas      # uv, draw.io Desktop, navigateur ; Node.js en option
uv run scripts/doctor.py maquettes    # uv, navigateur (pages HTML rendues et comparées aux maquettes), Tesseract
uv run scripts/doctor.py publication  # uv (Pandoc est fourni) ; LibreOffice en option
uv run scripts/doctor.py revue        # uv ; graphify en option (revue d'architecture)
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

**Modèles locaux** : un run n'en télécharge aucun. `doctor.py extraction
--prefetch` (Docling : mise en page et tableaux) et `doctor.py video
--prefetch` (Whisper) les téléchargent une fois, seulement depuis leur source
épinglée (`model-sources.json`), empreintes vérifiées ;
`--models-from DOSSIER` les copie depuis une copie du cache. Un script à qui
il manque un modèle s'arrête ou se replie en donnant cette commande.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Un groupe : extraction, video, schemas, maquettes, publication, revue ou tout (défaut) ; Facultatif : --prefetch, pour préparer une machine qui travaillera hors ligne ; Facultatif : --models-from DOSSIER, pour copier les modèles locaux depuis un dossier.
- **Sorties** : Aucun fichier, sauf avec --prefetch : les bibliothèques de rendu et les modèles locaux (groupes extraction et video) dans le cache de myskills.
- **`doctor.py`** : Vérifie les outils locaux et donne la commande d'installation des manquants ; avec --prefetch, remplit le cache des bibliothèques de rendu (version fixée, empreinte vérifiée) pour travailler hors ligne. Avec les groupes extraction (Docling) et video (Whisper), télécharge aussi les modèles locaux depuis leur source épinglée (model-sources.json) : un run n'en télécharge aucun. Rapport JSON (0 succès, 1 erreur).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Passe la main** à l'utilisateur : un outil manque : il l'installe lui-même, rien n'est installé sans son accord.

