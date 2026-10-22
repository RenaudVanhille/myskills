---
name: c4-architecture
description: "Modélise une architecture logicielle selon le modèle C4 (contexte, conteneurs, composants) avec LikeC4, valide le modèle et exporte une image par vue. À utiliser pour les schémas d'architecture."
---

# c4-architecture

Le modèle C4 décrit une architecture en niveaux, du plus large au plus
détaillé. Un seul modèle LikeC4 sert toutes les vues : on décrit les éléments
une fois, chaque vue en montre une partie.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Décision de diagram-brief ; Code, configuration ou description de l'architecture.
- **Sorties** : Dossier LikeC4 : specification.c4 et model.c4 ; Un PNG par vue (après export).
- **Scripts** : aucun ; la validation passe par le skill suivant.
- **Passe la main** au skill `diagram-export` : valider le modèle et exporter les vues.
- **Passe la main** au skill `excalidraw-diagram` : une vue est destinée à un public non technique.

## 1. Choisir le niveau

| Niveau | Montre | Pour |
| --- | --- | --- |
| 1. Contexte | le système, ses utilisateurs, les systèmes externes | tout public |
| 2. Conteneurs | applications, API, bases, files à l'intérieur du système | équipe, architectes |
| 3. Composants | modules à l'intérieur d'un conteneur | développeurs |

Le niveau 4 (code) ne se dessine pas : le code suffit. Un public non technique
ne voit que le niveau 1 ; s'il faut aller plus loin pour lui, passez par
`excalidraw-diagram`.

## 2. Écrire le modèle

Dans un dossier dédié (par exemple `docs/architecture/`) :

1. Copiez `references/specification.c4` : il définit les types d'éléments
   (`person`, `system`, `external`, `container`, `component`, `database`,
   `queue`) aux couleurs de la charte, et la relation `async`.
2. Écrivez `model.c4` :

```text
model {
  client = person 'Client' 'Achète en ligne'
  shop = system 'Boutique' {
    web = container 'Site web' {
      technology 'React'
    }
    api = container 'API paiement' {
      technology 'Java'
    }
    db = database 'Paiements' 'PostgreSQL'
    bus = queue 'Évènements'
  }
  bank = external 'Banque'

  client -> shop.web 'commande'
  shop.web -> shop.api 'appelle'
  shop.api -> shop.db 'enregistre'
  shop.api -[async]-> shop.bus 'publie'
  shop.api -> bank 'débite'
}

views {
  view index {
    title 'Boutique : contexte'
    include *
  }
  view shop of shop {
    title 'Boutique : conteneurs'
    include *
  }
}
```

- Identifiants courts sans accents ; libellés entre apostrophes droites.
- Chaque relation porte un verbe. `-[async]->` pour un message ou un évènement.
- `view <nom> of <élément>` montre l'intérieur d'un élément : une vue par
  niveau utile, pas plus.
- À partir du code : lisez les points d'entrée, la configuration (Docker
  Compose, manifestes Kubernetes, fichiers d'environnement) et les clients
  HTTP ou de messagerie pour trouver conteneurs et relations. Notez dans la
  réponse ce qui est déduit et ce qui reste à confirmer.

## 3. Valider et exporter

```bash
uv run ../diagram-export/scripts/export.py DOSSIER_DU_MODELE
```

Le script lance `likec4 validate` (références inconnues, erreurs de syntaxe)
puis exporte une image PNG par vue (`index.png`, `shop.png`) dans le dossier.
Avec `--check`, il valide et rend sans rien écrire. Il utilise `likec4` s'il
est installé, sinon `npx likec4` (Node.js requis).

Ouvrez chaque image et vérifiez que la vue se lit seule : titre, pas plus de
15 à 20 éléments, libellés de relations présents.

## 4. Livrer

- Dépôt : gardez les `.c4` dans le dépôt et liez les PNG depuis le Markdown.
  `npx likec4 start DOSSIER` ouvre un aperçu interactif.
- Bloc Mermaid à la place d'une image : `npx likec4 gen mermaid DOSSIER -o
  DOSSIER/mermaid` donne une base (une vue par fichier `.mmd`), sans les
  couleurs ; ajoutez les `classDef` de la charte avant de l'intégrer.
- Word, PowerPoint, Confluence : les PNG, ou un schéma draw.io si
  l'utilisateur veut l'éditer à la main ensuite.
