---
name: meeting-notes
description: "Compte rendu d'une réunion (atelier, kick-off, comité, entretien, soutenance) tiré de sa transcription ou de ses notes : participants, décisions, actions avec porteur et échéance, questions ouvertes et exigences entendues, chacune avec sa citation exacte vérifiée par script dans la transcription. Écrit le compte rendu Markdown, source directe du catalogue d'exigences et du vault, et le CSV des actions importable dans Jira ou Azure DevOps. À utiliser pour un compte rendu, un relevé de décisions, la synthèse d'un atelier ou d'une vidéo de réunion."
---

# meeting-notes

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous lisez
la transcription et décidez de ce qui compte ; le script vérifie les
citations, met en forme et écrit le CSV.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : La transcription ou les notes d'une réunion en Markdown (doc-to-markdown : vidéo transcrite en local, document, notes) ; Description JSON du compte rendu (notes_build.py --schema) : participants, décisions, actions, questions ouvertes, exigences entendues, avec leurs citations exactes.
- **Sorties** : <nom>.md : compte rendu daté (participants, ordre du jour, synthèse, décisions, actions, questions, exigences entendues, citations), utilisable comme source de requirements-catalog ; <nom>.actions.csv : une ligne par action (séparateur ;), importable dans Jira ou Azure DevOps.
- **`notes_build.py`** : Contrôle la description du compte rendu (identifiants uniques D-, A-, Q-, X-, échéance pas avant la réunion, porteur parmi les participants), retrouve chaque citation dans la transcription (casse, accents et espaces ignorés), écrit le compte rendu Markdown et le CSV des actions, puis relit le CSV. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Passe la main** au skill `requirements-catalog` : le compte rendu porte des exigences : il rejoint sources/ et req_build.py le reprend.
- **Passe la main** au skill `decision-log` : dans un workflow, chaque décision du compte rendu se trace au journal (journal.py log --kind decision).
- **Passe la main** au skill `markdown-to-obsidian` : le compte rendu va dans le vault Obsidian.
- **Passe la main** au skill `doc-to-markdown` : la réunion n'est encore qu'une vidéo, un enregistrement ou un document : la transcrire d'abord, en local.
- **Passe la main** à l'utilisateur : une décision ou un porteur n'est pas clair dans la transcription : la question à poser.

## 1. Préparer

La transcription doit être en Markdown : une vidéo ou un enregistrement
passe d'abord par `doc-to-markdown` (transcription locale), un document
aussi. Lisez la transcription une fois, en entier.

## 2. Décrire le compte rendu

Fichier `cr.json` (`uv run scripts/notes_build.py --schema` donne sa forme
sur une ligne) :

```json
{
  "title": "Atelier exigences du portail sinistres",
  "date": "2026-11-02", "kind": "atelier", "source": "sources/atelier.md",
  "participants": [{"name": "Claire Martin", "role": "MOA", "org": "Mutuelle"}],
  "decisions": [{"id": "D-1", "text": "Le portail sera responsive", "quote": "on part sur du responsive"}],
  "actions": [{"id": "A-1", "text": "Envoyer les volumes 2025", "owner": "Claire Martin", "due": "2026-11-09"}],
  "questions": [{"id": "Q-1", "text": "Faut-il gérer les mandataires ?", "to": "MOA"}],
  "requirements": [{"id": "X-1", "text": "Déclaration possible sur mobile", "quote": "les assurés doivent pouvoir déclarer depuis leur téléphone"}]
}
```

- **Une décision** est ce qui a été tranché en séance, pas une intention ;
  sa citation exacte (`quote`) prouve qu'elle a été dite.
- **Une action** a un porteur nommé (participant, sinon le signaler) et,
  si elle a été dite, une échéance.
- **Une question ouverte** est ce que personne n'a tranché ; `to` dit qui
  doit répondre.
- **Une exigence entendue** se recopie avec sa citation mot pour mot :
  `requirements-catalog` la reprendra depuis le compte rendu.
- Rien d'inventé : ce qui n'est pas dans la transcription n'y va pas.

## 3. Construire

```bash
uv run scripts/notes_build.py cr.json --out sources/cr-atelier.md
```

Corrigez les erreurs du rapport (citation introuvable : recopiez-la depuis
la transcription) et relancez jusqu'à zéro erreur. Les avertissements
(porteur hors participants, action sans échéance) se disent à
l'utilisateur.

## 4. Livrer

Le compte rendu (`.md`) et le CSV des actions. Dans un workflow, chaque
décision se trace au journal (`decision-log`) ; pour le vault, passez à
`markdown-to-obsidian`.
