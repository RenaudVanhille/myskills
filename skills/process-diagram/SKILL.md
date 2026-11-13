---
name: process-diagram
description: "Dessine un processus métier en couloirs (notation BPMN, swimlanes) : qui fait quoi, dans quel ordre, avec les décisions, les attentes, les passages de main et les points de douleur, en draw.io et PNG, avec sa fiche Markdown. À utiliser pour décrire un processus existant ou cible, un parcours de traitement entre services, un logigramme avec acteurs, à partir d'un atelier, d'une procédure ou d'un cahier des charges, pour un public métier ou technique. Pas pour une séquence d'appels entre systèmes (mermaid-diagram) ni pour une cartographie du SI (urbanization-map)."
---

# process-diagram

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décrivez seulement le processus ; le script le contrôle, le met en page et
écrit le draw.io. N'écrivez pas le XML draw.io à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief (kind processus) : public et destination ; Description JSON du processus : title, lanes (acteurs), steps (début, tâches, décisions, attentes, fins), flows (enchaînements et conditions).
- **Sorties** : <sujet>.drawio : processus en couloirs (notation BPMN), XML clair, à côté de sa description <sujet>.json ; <sujet>.processus.md : fiche du processus (synthèse, acteurs, déroulé numéroté, points de douleur) ; Avec --export : <sujet>.drawio.png ou .svg.
- **`process_build.py`** : Contrôle un processus métier (étape inaccessible, impasse, boucle sans sortie, décision sans libellé, référence inconnue), le met en page en couloirs (un par acteur, de gauche à droite), écrit le .drawio aux couleurs de la charte et sa fiche Markdown, puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `drawio-diagram` (`check_drawio.py`, facultatif : sans lui, avertissement) : vérifier le .drawio produit.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : exporter l'image dans le même appel (--export).
- **Passe la main** au skill `diagram-export` : exporter en PDF ou relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main.
- **Passe la main** au skill `mermaid-diagram` : le processus va dans un Markdown ou Obsidian sans couloirs : organigramme Mermaid.

## 1. Décrire le processus

Fichier `<sujet>.json` (`process_build.py --schema` en donne la forme) :

```json
{
  "title": "Déclaration d'un sinistre",
  "audience": "non technique",
  "lanes": [
    {"id": "assure", "name": "Assuré", "kind": "externe"},
    {"id": "gestionnaire", "name": "Gestionnaire"}
  ],
  "steps": [
    {"id": "survenu", "name": "Sinistre survenu", "type": "start", "lane": "assure"},
    {"id": "declarer", "name": "Déclarer le sinistre", "type": "task", "lane": "assure", "system": "Portail"},
    {"id": "complet", "name": "Dossier complet ?", "type": "gateway", "lane": "gestionnaire"},
    {"id": "completer", "name": "Compléter les pièces", "type": "task", "lane": "assure"},
    {"id": "clos", "name": "Dossier accepté", "type": "end", "lane": "gestionnaire"}
  ],
  "flows": [
    {"from": "survenu", "to": "declarer"},
    {"from": "declarer", "to": "complet"},
    {"from": "complet", "to": "completer", "label": "non"},
    {"from": "completer", "to": "complet"},
    {"from": "complet", "to": "clos", "label": "oui"}
  ]
}
```

- `lanes` : un couloir par acteur, de haut en bas. `kind` : `acteur`
  (défaut), `systeme` (une application qui agit seule) ou `externe` (client,
  partenaire). Un outil utilisé par une personne n'est pas un couloir : c'est
  le `system` de la tâche.
- `steps` : `start`, `task`, `gateway` (décision, un seul chemin suivi),
  `parallel` (tous les chemins, puis leur réunion), `event` (attente, délai,
  message reçu), `end`.
- Noms : une tâche est un verbe à l'infinitif et son objet (« Contrôler le
  dossier »), une décision une question fermée, un début ou une fin un état
  (« Sinistre survenu », « Assuré indemnisé »).
- `flows` : un `label` sur chaque sortie d'une décision. Un retour en
  arrière (boucle) se décrit comme un flux ordinaire : le script le
  reconnaît et le trace en tirets.
- `pain` : le point de douleur constaté à l'étape (ressaisie, attente,
  erreur), dans les mots de la source ; l'étape passe en rouge. `note` : une
  précision pour la fiche seulement.
- Ne décrivez que ce que la source dit. Une étape supposée se signale à
  l'utilisateur, elle ne se dessine pas.

## 2. Construire

```bash
uv run scripts/process_build.py <sujet>.json --export png
```

Le script refuse un processus incohérent, sans rien écrire : référence
inconnue (le nom proche est proposé), étape inaccessible, impasse, boucle
sans sortie, décision sans libellé, plusieurs suites sans décision.
Corrigez la description d'après `errors` et relancez.

Il écrit `<sujet>.drawio`, `<sujet>.processus.md` (synthèse, acteurs,
déroulé numéroté, points de douleur) et, avec `--export`, l'image. Lisez le
rapport, pas les fichiers : `decisions`, `handoffs` (passages de main),
`pains`, `loops`. N'ouvrez l'image que si `review_image` est vrai.

## 3. Lisibilité

- Public non technique : 15 étapes au plus (avertissement au-delà).
  Regroupez des tâches d'un même acteur ou faites un schéma par
  sous-processus.
- Beaucoup de passages de main (`handoffs`) pour peu de tâches : c'est un
  constat à donner à l'utilisateur, pas un défaut du schéma.
- Processus existant et processus cible : deux descriptions, deux schémas,
  mêmes identifiants d'étapes pour les comparer.

## 4. Livrer

Pour Confluence ou un document : le `.drawio` et le `.drawio.png`. La fiche
`.processus.md` s'insère telle quelle dans un dossier ou une note. Charte
graphique : celle du dépôt (`shared/references/style.md`).
