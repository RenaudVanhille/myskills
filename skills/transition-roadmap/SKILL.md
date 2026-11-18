---
name: transition-roadmap
description: "Construit la feuille de route de transition d'une architecture actuelle vers la cible : chantiers et jalons avec durées et prédécesseurs, vagues de migration reprises de migration-assessment, dates, marges et chemin critique calculés par script, échéance contrôlée, diagramme de Gantt Mermaid et CSV. À utiliser pour un plan de transition, une trajectoire, un planning de migration ou un schéma directeur à phaser."
---

# transition-roadmap

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
découpez la transition en chantiers et estimez leur durée ; le script
calcule les dates, les marges et le chemin critique.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Description JSON des chantiers et jalons de la transition (roadmap_build.py --schema) ; Facultatif : les vagues de migration (<nom>.waves.json de migration-assessment).
- **Sorties** : <nom>.md : synthèse (dates, durée, chemin critique), tableau des chantiers avec marges, diagramme de Gantt Mermaid ; <nom>.csv : une ligne par chantier (dates, durée, lot, responsable, critique).
- **`roadmap_build.py`** : Reprend les vagues de migration comme chantiers, contrôle les prédécesseurs (connus, sans cycle), calcule les dates au plus tôt, les marges, le chemin critique et la fin du programme, signale l'échéance dépassée et les chantiers trop longs, écrit le tableau et le diagramme de Gantt Mermaid. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Passe la main** au skill `migration-assessment` : les vagues de migration ne sont pas encore calculées.
- **Passe la main** au skill `diagram-export` : le diagramme de Gantt doit être rendu en image (export.py <nom>.md).
- **Passe la main** à l'agent `document-publisher` : la feuille de route doit être livrée en Word, PowerPoint ou HTML.
- **Passe la main** à l'utilisateur : arbitrer une échéance dépassée : raccourcir le chemin critique, ajouter des moyens ou décaler.

## 1. Décrire

Fichier `feuille-de-route.json` (`uv run scripts/roadmap_build.py --schema`
donne sa forme sur une ligne) : `title`, `start` (début du programme),
`deadline` si une échéance est imposée, et :

- `waves` : les vagues de `migration-assessment` (`file` :
  `migration.waves.json`), chacune devient un chantier `V1`, `V2`... après
  la précédente ; `weeks` donne les semaines par effort (défaut S 2, M 4,
  L 8, XL 16) et `after` les chantiers à finir avant la première vague ;
- `items` : les autres chantiers (socle, sécurité, conduite du changement,
  décommissionnement) et les jalons (`weeks: 0`), avec `after` (chantiers
  ou vagues), `lot`, `owner`, et `start` seulement pour une date imposée.

Un chantier de plus de 26 semaines se découpe. Une durée sans source
(atelier, chiffrage) est une hypothèse : dites-la à l'utilisateur.

## 2. Calculer

```bash
uv run scripts/roadmap_build.py feuille-de-route.json
```

Corrigez jusqu'à zéro erreur (prédécesseur inconnu ou en cycle). Le
rapport donne les dates, la durée, le chemin critique et `late_weeks` ;
une échéance dépassée se présente à l'utilisateur avec le chemin critique
à raccourcir. Ne relisez pas `feuille-de-route.md` : le diagramme de Gantt
Mermaid y est écrit par le script ; pour une image, `diagram-export`
(`export.py feuille-de-route.md`) le rend en PNG.
