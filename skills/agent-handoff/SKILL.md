---
name: agent-handoff
description: "Valide un message de passage entre agents ou le rapport final d'un agent (JSON Schema, fichiers cités présents) et le note au journal d'un workflow. À utiliser par tout agent avant de passer la main à un autre ou de rendre son rapport final."
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

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier de travail, ou dossier d'un workflow (workflow.json) ; Un message de passage (shared/schemas/handoff.schema.json) ou un rapport final d'agent (shared/schemas/agent-report.schema.json), en JSON.
- **Sorties** : Aucun fichier ; dans un dossier de workflow, une entrée « passage » ou « rapport » au journal (workflow.json, journal.md).
- **`check_message.py`** : Valide un message de passage ou un rapport final d'agent contre son schéma, vérifie que chaque fichier cité existe et, dans un dossier de workflow, le note au journal (skill decision-log). Rapport JSON, codes de sortie : 0 message conforme, fichiers présents (et tracé au journal s'il y a un workflow) ; 1 message illisible, non conforme à son schéma ou fichier cité introuvable.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : noter le message au journal d'un workflow.
- **Passe la main** à l'utilisateur : l'outil ne permet pas d'appeler l'agent visé : lui donner le message et l'agent à lancer.

