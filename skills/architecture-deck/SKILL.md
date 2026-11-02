---
name: architecture-deck
description: "Assemble la présentation d'un dossier d'architecture (besoin, exigences, options notées, schémas, décision, couverture) depuis les étapes déjà validées d'un workflow, sans rien rédiger, au format du skill externe markdown-to-pptx. À utiliser pour présenter un choix d'architecture en PowerPoint à un comité."
---

# architecture-deck

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Le script lit
les livrables validés d'`architecture-options` (installé à côté) et ne
demande rien au modèle : une diapositive par information, le détail dans les
notes de l'orateur.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Dossier d'un workflow d'architecture aux étapes validées : options.json, exigences.json (et son glossaire), decision.json, PNG des schémas déjà exportés.
- **Sorties** : presentation.md : présentation du dossier (besoin, options, décision) au format du skill externe markdown-to-pptx, schémas exportés compris ; chaque donnée n'y figure qu'une fois.
- **`deck_build.py`** : Assemble la présentation du dossier à partir des étapes validées, sans rien demander au modèle : options.json (validé contre le schéma d'options_build.py), le catalogue d'exigences et son glossaire, decision.json, les PNG des schémas déjà exportés. Mêmes scores et contrôles qu'options_build.py ; une diapositive par information (chiffres clés, exigences indispensables, glossaire, notes par critère en graphique, scores, écarts, comparaison, un schéma par option, décision, couverture par l'option retenue, questions ouvertes), le détail dans les notes de l'orateur. Rapport JSON (0 succès, 1 erreur).
- **Dépend de** `architecture-options` (`options_build.py`, obligatoire) : mêmes scores, contrôles et schéma d'options.json que la comparaison validée.
- **Passe la main** au skill `markdown-publish` : produire le .pptx de presentation.md avec pptx_publish.py (skill externe markdown-to-pptx).

## 1. Assembler

Une fois la décision prise et les schémas exportés en PNG :

```bash
uv run scripts/deck_build.py DOSSIER
uv run ../markdown-publish/scripts/pptx_publish.py DOSSIER/presentation.md [--template MARQUE.potx]
```

`deck_build.py` écrit `presentation.md` à partir des fichiers validés
(rien à rédiger) ; un schéma non exporté est signalé et sa diapositive
omise. `pptx_publish.py` appelle le skill externe `markdown-to-pptx`,
installé à part, et vérifie le `.pptx`. N'éditez `presentation.md` que pour
une demande de l'utilisateur ; corrigez sinon la source (`options.json`,
exigences) et relancez.
