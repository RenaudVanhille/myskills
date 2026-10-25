---
name: agent-handoff
description: "Valide un message de passage entre agents ou le rapport final d'un agent (JSON Schema, fichiers cités présents) et le note au journal d'un workflow ; donne la liste compacte des agents et workflows classés pour une demande. À utiliser par tout agent avant de passer la main à un autre ou de rendre son rapport final, et pour choisir par où commencer."
---

# agent-handoff

Tout agent de myskills termine par un **rapport final** et passe la main
par un **message de passage**, en JSON sur une ligne. Avant de les envoyer,
validez-les (chemin `scripts/` relatif au dossier de ce skill) :

```bash
uv run scripts/check_message.py handoff DOSSIER --json '{"agent": "schema-designer", ...}'
uv run scripts/check_message.py report DOSSIER --json '{"agent": "document-extractor", ...}'
```

`DOSSIER` est le dossier de travail : les fichiers cités dans `files` y sont
cherchés. Corrigez jusqu'à zéro erreur (`errors` donne le chemin du champ
fautif, la valeur reçue et les valeurs possibles). Dans le dossier d'un
workflow (`workflow.json`), le message est noté au journal à l'étape
courante (`entry`), sans autre commande.

Les champs des deux messages sont dans la section « Contrat » de chaque
agent ; les schémas qui font foi sont `shared/schemas/handoff.schema.json`
et `shared/schemas/agent-report.schema.json`. Un nouvel agent n'a rien à
changer ici : `scripts/build.py` met à jour la liste des agents permis.

## Choisir l'agent ou le workflow

Quand on ne sait pas qui doit traiter une demande (agent `orientation`) :

```bash
uv run scripts/route.py --query "la demande telle quelle" --files cahier.pdf
```

Le rapport liste les agents et les workflows, une phrase chacun, classés
par les mots qu'ils partagent avec la demande. Le score n'est qu'un indice :
choisissez en lisant les descriptions, sans ouvrir `catalog.json`. Un
workflow (`kind: workflow`) se lance par son agent (`architecture-workflow`)
en donnant son nom dans `constraints` du message de passage
(`"workflow : <nom>"`). `--kind skills` liste aussi les skills.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier de travail, ou dossier d'un workflow (workflow.json) ; Un message de passage (shared/schemas/handoff.schema.json) ou un rapport final d'agent (shared/schemas/agent-report.schema.json), en JSON ; Pour le routage : la demande de l'utilisateur et les fichiers fournis (route.py).
- **Sorties** : Aucun fichier ; dans un dossier de workflow, une entrée « passage » ou « rapport » au journal (workflow.json, journal.md).
- **`check_message.py`** : Valide un message de passage ou un rapport final d'agent contre son schéma, vérifie que chaque fichier cité existe et, dans un dossier de workflow, le note au journal (skill decision-log). Rapport JSON, codes de sortie : 0 message conforme, fichiers présents (et tracé au journal s'il y a un workflow) ; 1 message illisible, non conforme à son schéma ou fichier cité introuvable.
- **`route.py`** : Donne la liste compacte des agents et workflows (et, sur demande, des skills) depuis le catalogue de routage généré par build.py, classée par les mots partagés avec la demande et les extensions des fichiers fournis ; le score est un indice, le choix revient à l'agent orientation. Rapport JSON, codes de sortie : 0 liste rendue (avertissement si aucun mot commun ou égalité en tête) ; 1 ni --query ni --list, ou catalogue de routage illisible.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : noter le message au journal d'un workflow.
- **Passe la main** à l'utilisateur : l'outil ne permet pas d'appeler l'agent visé : lui donner le message et l'agent à lancer.

