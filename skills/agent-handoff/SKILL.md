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

## Marquer les fichiers générés

Tout fichier généré porte une marque cachée « généré par IA » (règlement
(UE) 2024/1689, AI Act, article 50), propre à son format. Les scripts des
skills marquent leurs livrables. Un fichier que vous écrivez vous-même, sans
script (note, page, code), se marque avant le rapport final ; jamais un
fichier fourni par l'utilisateur :

```bash
uv run scripts/mark_generated.py sortie/synthese.md sortie/page.html
```

`check_message.py report` signale en avertissement chaque fichier livré
sans marque. Un export ou une mise en forme d'un fichier de l'utilisateur
(Word d'un Markdown, PNG d'un schéma) n'est pas marqué : il reprend la
marque de sa source.

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

Avec `--laya`, le modèle local Laya choisit parmi les six premiers
candidats ; son choix passe en tête à partir de 0,6 de confiance (champ
`laya` du rapport). Il est facultatif : sans Laya, le classement par mots
reste. Réservez-le aux demandes sans mot commun avec les candidats. Le
modèle se prépare avant, une fois : `doctor.py extraction --prefetch`
(skill `check-prerequisites`) ; rien ne se télécharge pendant le run.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier de travail, ou dossier d'un workflow (workflow.json) ; Un message de passage (shared/schemas/handoff.schema.json) ou un rapport final d'agent (shared/schemas/agent-report.schema.json), en JSON ; Pour le routage : la demande de l'utilisateur et les fichiers fournis (route.py).
- **Sorties** : Aucun fichier ; dans un dossier de workflow, une entrée « passage » ou « rapport » au journal (workflow.json, journal.md) ; Avec mark_generated.py : les fichiers générés cités, marqués « généré par IA » sur place.
- **`check_message.py`** : Valide un message de passage ou un rapport final d'agent contre son schéma, vérifie que chaque fichier cité existe (et, dans un rapport final, signale un fichier livré sans marque « généré par IA ») et, dans un dossier de workflow, le note au journal (skill decision-log). Rapport JSON, codes de sortie : 0 message conforme, fichiers présents (et tracé au journal s'il y a un workflow) ; 1 message illisible, non conforme à son schéma ou fichier cité introuvable.
- **`mark_generated.py`** : Marque « généré par IA » (AI Act, art. 50) les fichiers que l'agent écrit lui-même sans script, jamais un fichier fourni par l'utilisateur : marque cachée propre au format (frontmatter, meta HTML, commentaire, chunk PNG, propriétés Office), relue après écriture ; --check vérifie sans écrire. Rapport JSON, codes de sortie : 0 fichiers marqués (ou déjà marqués) ; 1 fichier introuvable, marque impossible ou, avec --check, fichier sans marque.
- **`route.py`** : Donne la liste compacte des agents et workflows (et, sur demande, des skills) depuis le catalogue de routage généré par build.py, classée par les mots partagés avec la demande et les extensions des fichiers fournis ; le score est un indice, le choix revient à l'agent orientation ; dans une mission (mission.json), donne sa nature, ses workflows et son vault, et met ses workflows devant. Rapport JSON, codes de sortie : 0 liste rendue (avertissement si aucun mot commun ou égalité en tête) ; 1 ni --query ni --list, ou catalogue de routage illisible.
- **`route_laya.py`** : Pose au modèle local Laya (CPU, sans service en ligne) la question fermée de route.py --laya : quel candidat traite la demande, d'après les descriptions ; lancé par route.py dans son propre environnement. Rapport JSON, codes de sortie : 0 choix rendu ; 1 description invalide ou Laya indisponible.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `decision-log` (`journal.py`, facultatif : sans lui, avertissement) : noter le message au journal d'un workflow.
- **Passe la main** à l'utilisateur : l'outil ne permet pas d'appeler l'agent visé : lui donner le message et l'agent à lancer.

