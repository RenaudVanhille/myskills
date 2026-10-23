---
name: decision-log
description: "Tient l'état d'un workflow à étapes avec portes de revue humaine et trace chaque choix, hypothèse, question, retour et validation dans un journal (workflow.json et journal.md). Une étape ne démarre qu'après validation des précédentes ; un fichier validé puis modifié est détecté. À utiliser pour piloter un workflow prédictible où l'utilisateur relit chaque étape et où toutes les décisions doivent être tracées."
---

# decision-log

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script
tient l'état et applique les règles ; vous n'écrivez jamais `workflow.json`
ni `journal.md` à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Dossier du workflow ; Commande : init, start, log, submit, review ou status, avec l'étape, le texte et les références (exigences, options, entrées).
- **Sorties** : workflow.json : étapes dans l'ordre, statut, empreintes SHA-256 des fichiers soumis, entrées du journal ; journal.md : version lisible (étapes, décisions et revues, questions), réécrite à chaque commande.
- **`journal.py`** : Fait respecter l'ordre des étapes et les portes de revue (démarrage seulement après validation des étapes précédentes, validation seulement d'une étape en revue dont les fichiers n'ont pas changé, retour qui remet à reprendre l'étape et les suivantes), note chaque choix, hypothèse, question, soumission, retour et validation, et détecte un fichier validé modifié depuis. Rapport JSON, codes de sortie : 0 commande appliquée ; 1 commande refusée (étape inconnue, ordre ou porte de revue non respectés, fichier introuvable) ; workflow.json inchangé.
- **Passe la main** à l'utilisateur : une étape est soumise : l'utilisateur la valide ou fait un retour.

## 1. Le cycle d'une étape

```text
a-faire --start--> en-cours --submit--> en-revue --review valide--> validee
                                            |
                                            +--review retour--> a-reprendre --start--> en-cours ...
```

| Commande | Quand | Le script refuse si |
| --- | --- | --- |
| `init DOSSIER [--stages a,b,c] [--title T]` | une fois, au début | `workflow.json` existe déjà |
| `start DOSSIER ETAPE` | avant de travailler sur l'étape | une étape précédente n'est pas validée |
| `log DOSSIER ETAPE --kind choix\|hypothese\|question --text T --why J --refs EF-001,A` | à chaque choix qui demande du jugement | l'étape n'est pas en cours (sauf question) |
| `submit DOSSIER ETAPE --files F ...` | livrables vérifiés par leurs scripts | l'étape n'est pas en cours, fichier introuvable |
| `review DOSSIER ETAPE --decision valide\|retour --text "..."` | quand l'utilisateur a répondu | validation : étape pas en revue, ou fichiers modifiés depuis la soumission |
| `status DOSSIER` | pour reprendre un workflow | - |

Le rapport donne toujours `current` (étape courante) et `next` (prochaine
action) : suivez `next`, ne le déduisez pas vous-même.

## 2. Règles

- **Revue humaine** : n'appelez `review` qu'avec la réponse explicite de
  l'utilisateur, et mettez ses mots dans `--text`. Une validation n'est
  jamais déduite d'un silence.
- **Retour** : `review --decision retour` remet l'étape à reprendre, ainsi
  que toutes les étapes suivantes déjà commencées (entrées « invalidation »).
  Il vaut aussi pour une étape déjà validée : c'est la seule façon de revenir
  en arrière.
- **Choix tracés** : notez avec `log` chaque décision prise sans
  l'utilisateur (outil choisi, exigence déduite, phrase écartée, note
  attribuée, hypothèse), en une phrase, avec sa justification (`--why`) et
  les identifiants concernés (`--refs`). Une question que seul l'utilisateur
  peut trancher se note `--kind question` et se pose à la revue.
- **Fichiers figés** : `submit` enregistre l'empreinte de chaque fichier. Si
  un fichier validé change, `status` l'avertit : faites revoir l'étape
  (`review --decision retour`) plutôt que de continuer.

`journal.md` est la version lisible, à joindre au dossier livré.
