---
name: diagram-brief
description: "Choix du format de schéma (Mermaid, draw.io, Excalidraw, C4, POS, cloud) selon le public, la destination (Markdown, Obsidian, Word, PowerPoint, Confluence) et le type de schéma : décision courte en JSON validée par script, qui rend le format, le skill et la livraison. À utiliser avant de produire un schéma."
---

# diagram-brief

Avant de dessiner, fixez le **public**, la **destination**, le **type de
schéma**, le message principal et les 3 à 7 éléments indispensables, en JSON.
`brief.py` valide cette décision courte et choisit le format et le skill.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Contexte du schéma : description, code, ADR, Markdown ou image ; La décision courte en JSON : public, destination, type, message principal, 3 à 7 éléments.
- **Sorties** : La décision complète (format, skill, vue cloud, livraison, raison) dans le rapport, et en JSON avec --out pour le skill de dessin ou un autre agent.
- **`brief.py`** : Valide la décision courte et applique la grille de choix (public avant destination, format modifiable là où le schéma vivra) : format, skill, vue cloud, livraison selon la destination et raison du choix. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Passe la main** au skill `mermaid-diagram` : séquence, états, classes, données, ou flux simple dans un dépôt ou Obsidian.
- **Passe la main** au skill `drawio-diagram` : public technique, Word, PowerPoint ou Confluence, mise en page précise.
- **Passe la main** au skill `excalidraw-diagram` : public non technique, atelier, vue d'ensemble.
- **Passe la main** au skill `c4-architecture` : architecture logicielle à plusieurs vues ou niveaux.
- **Passe la main** au skill `urbanization-map` : cartographie fonctionnelle du SI, plan d'occupation des sols (urbanisation).
- **Passe la main** au skill `process-diagram` : processus métier : qui fait quoi, décisions, passages de main (kind processus).
- **Passe la main** au skill `cloud-architecture` : architecture cloud (AWS, Azure, GCP, Kubernetes), réseau, PRA ou pipeline.
- **Passe la main** au skill `threat-model` : modèle de menaces STRIDE d'un schéma cloud (type menaces).

## 1. Écrire la décision courte

Déduisez ce que vous pouvez du contexte (un ADR vise un public technique, une
présentation au comité un public non technique). Ne posez qu'une question, et
seulement si la réponse change le format.

```json
{"subject": "Paiement en ligne", "audience": "technique", "destination": "confluence",
 "kind": "sequence", "message": "Le paiement est confirmé avant la commande.",
 "elements": ["client", "boutique", "service de paiement", "banque"],
 "left_out": ["remboursements"]}
```

`kind` : `architecture` (plusieurs vues C4), `vue-c4`, `urbanisation` ou
`capacites` (POS du SI), `cloud`, `cloud-reseau`, `kubernetes`, `pra`,
`pipeline`, `menaces`, `sequence`, `etats`, `classes`, `donnees`, `gantt`,
`flux`, `processus` (processus métier en couloirs par acteur, skill
`process-diagram`), `deploiement`, `reseau`, `vue-ensemble`. `editable` :
l'utilisateur veut retoucher le schéma lui-même. Le schéma complet :
`uv run scripts/brief.py --schema`.

## 2. Lancer le choix

```bash
uv run scripts/brief.py brief.json --out schemas/decision.json
# ou : uv run scripts/brief.py --json '{"audience": ...}'
```

Le rapport donne `decision` : `format`, `skill`, `view` (vue de
`cloud_build.py`), `delivery` (ce qu'on livre selon la destination) et
`reason`, à citer dans le rapport final. Le public passe avant la destination
: un schéma pour un public non technique est un Excalidraw, même dans
PowerPoint ou Confluence. La grille complète est dans `references/grille.md`
; ne la lisez que pour justifier un choix hors grille.

## 3. Avant de dessiner

Pour un public non technique, remplacez chaque terme technique par ce qu'il
fait (« le service qui encaisse » plutôt que « payment-api »). La charte
commune est dans `references/style.md` : couleurs par rôle, formes, taille
du texte, règles de composition.
