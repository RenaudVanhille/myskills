---
name: domain-design
description: "Définit les domaines d'une solution selon le DDD stratégique : sous-domaines cœur, support et génériques, contextes bornés (entités possédées, exigences, équipe, langage), carte des contextes (client-fournisseur, couche anticorruption, événements...). Le script contrôle le découpage, calcule cohésion et couplage, recommande le style par une grille (monolithe modulaire, mixte ou microservices, et seulement si le projet s'y prête), dessine la carte en draw.io et prépare les composants de chaque style pour architecture-options. À utiliser pour découper un domaine, définir des bounded contexts, décider monolithe ou microservices."
---

# domain-design

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
découpez le domaine et répondez à la grille ; le script contrôle, calcule
le style, dessine et écrit.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : complexe (modèle puissant).
- **Entrées** : Les exigences (exigences.json de requirements-catalog) et, sur un existant, le modèle de données actuel (modele.json de data-model) ; Description JSON du découpage (domain_build.py --schema) : sous-domaines, contextes bornés (entités, exigences, équipe, langage, besoins propres), carte des contextes, facteurs de la grille de style.
- **Sorties** : <nom>.md : style recommandé et grille, sous-domaines, contextes et leur langage, carte des contextes, couplage, points d'attention ; <nom>.styles.json : composants et flux du monolithe modulaire, du mixte et des microservices, au format d'options.json ; <nom>.carte.drawio : carte des contextes (une colonne par sous-domaine), et son image avec --export.
- **`domain_build.py`** : Vérifie sous-domaines, contextes, exigences et entités citées, un seul contexte propriétaire par entité ; calcule cohésion et couplage entre contextes, signale dépendance absente de la carte, cycle, noyau partagé, exigence fonctionnelle sans contexte ; calcule le style recommandé (monolithe modulaire, mixte, microservices) et les contextes à extraire avec la grille ; écrit le document, les squelettes de composants vérifiés contre le schéma d'options.json et la carte des contextes contrôlée par drawio_build.py. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Dépend de** `requirements-catalog` (`req_build.py`, facultatif : sans lui, avertissement) : valider exigences.json contre son schéma.
- **Dépend de** `data-model` (`model_build.py`, facultatif : sans lui, avertissement) : valider la description du modèle de données (entités, relations).
- **Dépend de** `architecture-options` (`options_build.py`, facultatif : sans lui, avertissement) : vérifier les squelettes de composants de chaque style contre le schéma d'options.json.
- **Dépend de** `drawio-diagram` (`drawio_build.py`, facultatif : sans lui, avertissement) : dessiner et contrôler la carte des contextes.
- **Dépend de** `markdown-to-obsidian` (`lib/vault_ontology.py`, obligatoire) : ontologie du vault Obsidian (source unique) : construire et vérifier les notes écrites.
- **Dépend de** `mission-workspace` (`lib/workspace.py`, obligatoire) : espace de travail de la mission (mission.json, vault et dossiers par défaut).
- **Vault Obsidian** : écrit les notes de type `decoupage-domaines`, `contexte-borne`, selon l'ontologie du vault (`vault_ontology.py` du skill markdown-to-obsidian).
- **Passe la main** au skill `data-model` : découpage validé : modèle de données de chaque contexte (champ context des entités, schéma par contexte, clé étrangère entre contextes signalée).
- **Passe la main** au skill `architecture-options` : options à comparer : partir des squelettes de <nom>.styles.json (style recommandé et une alternative).
- **Passe la main** au skill `api-contract` : contrats des relations de la carte (API de l'amont, événements publiés).
- **Passe la main** au skill `architecture-review` : contrôler une architecture contre le découpage (domains, règles DOM-).
- **Passe la main** au skill `diagram-export` : image de la carte demandée après coup.
- **Passe la main** à l'utilisateur : facteur de la grille inconnu (équipes, maturité DevOps, cohérence exigée) : la question à poser, une seule fois.

## 1. Découper

Partez des exigences fonctionnelles (`exigences.json`, leur `domain`), du
glossaire et des processus métier, pas des tables : un découpage tiré des
données donne des services « par entité », couplés par chaque processus.
Sur un projet neuf, le découpage vient d'abord et le modèle de données de
chaque contexte ensuite (`data-model`, champ `context`) ; le couplage se
calcule alors sur les entités possédées et utilisées. Sur un existant, le
modèle actuel (`model` : `modele.json` de `data-model`) mesure le couplage
réel par ses relations.

- **Sous-domaines** : `coeur` (ce qui différencie le métier, développé),
  `support` (nécessaire et spécifique), `generique` (à acheter ou réutiliser).
- **Contextes bornés** : un langage cohérent, une équipe, des entités
  possédées. Un terme qui change de sens (le « Sinistre » de la déclaration
  n'est pas celui de l'indemnisation) sépare deux contextes ; chaque entité
  n'a qu'un contexte propriétaire, les autres la citent dans `uses`.
- **Besoins propres** (`needs`) : seulement ce qui distingue vraiment le
  contexte des autres (charge dix fois plus forte, livraisons chaque jour,
  isolement réglementaire), avec sa raison. Ils désignent les services à
  extraire.
- **Carte** : une relation par paire de contextes, l'amont fournit, l'aval
  dépend ; motifs `client-fournisseur`, `conformiste`, `acl`, `open-host`,
  `langage-publie`, `partenariat`, `noyau-partage`, `chemins-separes` ;
  `integration` `sync` (l'aval appelle) ou `async` (événements de l'amont).

## 2. Répondre à la grille

`factors` : `devops` (faible, moyenne, forte), `stabilite` des frontières
(incertaine, connue), `coherence` exigée entre contextes (forte,
eventuelle), `delai` (court, normal), chacun avec sa raison tirée des
documents. Équipes, nombre de contextes, besoins propres et couplage se
calculent. Un facteur inconnu se demande une fois à l'utilisateur ; sans
réponse, laissez-le absent : le rapport baisse la confiance.

```json
{
  "title": "Domaines du portail sinistres",
  "requirements": "exigences.json",
  "model": "modele.json",
  "subdomains": [{"id": "sinistres", "name": "Sinistres", "kind": "coeur", "why": "déclaration en ligne différenciante"}],
  "contexts": [
    {"id": "declaration", "name": "Déclaration", "subdomain": "sinistres", "team": "Équipe portail",
     "entities": ["Declaration", "Piece"], "uses": ["Contrat"], "refs": ["EF-001"],
     "terms": {"Sinistre": "événement déclaré par l'assuré, pas encore instruit"},
     "needs": {"echelle": "pics après une tempête (ENF-001)"}}
  ],
  "relations": [{"upstream": "contrats", "downstream": "declaration", "patterns": ["open-host", "acl"],
                 "integration": "sync", "label": "vérifie la garantie"}],
  "factors": {"devops": {"value": "moyenne", "why": "CI en place, pas d'orchestrateur"}}
}
```

## 3. Construire

```bash
uv run scripts/domain_build.py domaines.json [--export png] [--vault VAULT --folder DOSSIER]
```

Corrigez jusqu'à zéro erreur. Le rapport donne `style.recommended` (la
grille ne propose les microservices que si le projet s'y prête : plusieurs
équipes, besoins propres, DevOps en place, domaine stable, contextes peu
couplés), `extract` (services à sortir d'un monolithe modulaire) et
`confidence`. Dites les avertissements à l'utilisateur ; une dépendance hors
carte se déclare dans `relations` ou se supprime.

## 4. Livrer et enchaîner

`domaines.md` (grille, contextes, langage, carte, couplage),
`domaines.carte.drawio` et `domaines.styles.json`. Pour comparer, passez à
`architecture-options` : une option reprend les `components` et `flows` du
style recommandé, une autre l'alternative la plus proche ; ils portent
`contexts`, que `architecture-review` contrôle avec `domains`. Le style
retenu par l'utilisateur va dans `decision` (`style`, `why`), puis on
relance le script.
