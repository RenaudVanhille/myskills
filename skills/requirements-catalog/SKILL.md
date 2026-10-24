---
name: requirements-catalog
description: "Extrait des documents d'un projet (cahier des charges, comptes rendus, spécifications convertis en Markdown) le catalogue des exigences fonctionnelles et non fonctionnelles, avec identifiants stables, priorité, mesure et citation de la source vérifiée par script, puis l'exporte en Markdown et CSV. À utiliser pour recenser, tracer ou exporter les exigences d'un projet."
---

# requirements-catalog

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous lisez
les documents et rédigez une description JSON courte ; le script vérifie
chaque citation, cherche les exigences oubliées et met en forme.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Documents en Markdown (sortie de doc-to-markdown) dans un dossier sources ; Description JSON des exigences : title, sources, requirements (id repris des documents ou EF-/ENF-, nature, title, text, priority, category ou domain, metric, sources avec citation, questions, status), ignored, glossary (terme, définition, synonymes).
- **Sorties** : <nom>.md : catalogue pour la revue (exigences fonctionnelles, non fonctionnelles, questions, exigences déduites, retirées, phrases écartées, glossaire avec les exigences qui emploient chaque terme) ; <nom>.csv : même catalogue pour un tableur (séparateur ;, UTF-8 avec BOM).
- **`req_build.py`** : Vérifie chaque citation dans son document et en donne la ligne, repère les phrases normatives des sources reprises par aucune exigence, signale une exigence renumérotée alors que sa source porte un identifiant, doublons et exigences non mesurables, puis écrit le catalogue en Markdown et en CSV. Rapport JSON, codes de sortie : 0 catalogue produit sans erreur (avertissements possibles) ; 1 description invalide, citation introuvable ou autre erreur ; aucun fichier produit.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Passe la main** au skill `doc-to-markdown` : les documents ne sont pas encore en Markdown.
- **Passe la main** au skill `architecture-options` : le catalogue est validé : proposer des architectures.
- **Passe la main** au skill `decision-log` : noter les choix (exigence déduite, phrase écartée, priorité) et soumettre le catalogue à la revue.

## 1. Lire les sources

Les documents sont en Markdown dans un dossier `sources/` (sinon,
`doc-to-markdown` d'abord). Lisez chaque document une fois, en entier.

## 2. Décrire les exigences

Fichier `exigences.json`, à côté du dossier `sources/` :

```json
{
  "title": "Exigences du portail de sinistres",
  "sources": "sources",
  "requirements": [
    {"id": "EF-001", "title": "Déclarer un sinistre", "text": "L'assuré déclare un sinistre en ligne.",
     "domain": "Sinistres", "priority": "indispensable",
     "sources": [{"doc": "cahier-des-charges.md", "quote": "L'assuré doit pouvoir déclarer un sinistre"}]},
    {"id": "ENF-001", "title": "Tenir la charge", "text": "2 000 déclarations par jour.",
     "category": "performance", "metric": "2 000 par jour, pic x10", "priority": "indispensable",
     "sources": [{"doc": "cahier-des-charges.md", "quote": "supporter 2 000 déclarations par jour"}],
     "questions": ["Quel est le pic après une tempête ?"]}
  ],
  "ignored": [{"doc": "compte-rendu.md", "quote": "L'ancienne application devra être arrêtée", "reason": "autre projet"}]
}
```

- **Identifiants** : si les documents numérotent déjà leurs exigences
  (`SEC-01`, `REQ-012`...), gardez leur identifiant tel quel et ajoutez
  `"nature": "fonctionnelle"` ou `"non-fonctionnelle"`. Sinon, `EF-nnn`
  fonctionnelle, `ENF-nnn` non fonctionnelle. Le script signale une
  exigence renumérotée alors que sa source porte un identifiant, et un
  identifiant repris introuvable dans les sources. Un identifiant ne change
  jamais et n'est jamais réutilisé : pour enlever une exigence,
  `"status": "retiree"` et `reason`.
- **Une exigence = un besoin vérifiable**. Fusionnez les doublons (plusieurs
  `sources`), découpez les phrases qui en portent plusieurs.
- **Priorité** : `indispensable`, `importante`, `souhaitable`,
  `hors-perimetre`, d'après les mots du document (doit, devrait, pourra) ;
  notez votre choix dans le journal s'il n'est pas explicite.
- **Non fonctionnelle** : `category` parmi performance, disponibilite,
  securite, conformite, exploitabilite, maintenabilite, evolutivite,
  interoperabilite, utilisabilite, portabilite, cout, autre ; `metric`
  mesurable, sinon une question.
- **Source** : `quote` est une citation exacte et courte (une phrase ou un
  morceau) ; le script la retrouve et calcule la ligne, mise en forme et
  accents ignorés. `page` facultatif. Une exigence implicite n'a pas de
  citation : `derived` dit d'où elle vient, elle sera listée « à
  confirmer ».
- **Phrase écartée** : une phrase normative qui n'est pas une exigence du
  projet va dans `ignored`, avec sa raison.
- **Ambiguïté** : ne tranchez pas seul, ajoutez une question.
- **Glossaire** (facultatif) : les termes métier et sigles que les exigences
  emploient, `"glossary": [{"term": "Sinistre", "definition": "...",
  "aliases": ["sinistres auto"], "sources": [...]}]`. Le script relie chaque
  terme aux exigences qui l'emploient (sans casse ni accents), refuse un
  terme ou synonyme défini deux fois et signale un terme employé nulle
  part. Dans un workflow avec vault, chaque terme devient une note
  `Glossaire/<terme>` (synonymes en `aliases` Obsidian), liée à ses
  exigences.

## 3. Construire et vérifier

```bash
uv run scripts/req_build.py exigences.json
```

Erreurs : citation introuvable (avec la ligne la plus proche), document
absent, identifiant en double ou mal formé. Avertissements : phrase
normative des sources (doit, devra, il faut, shall, must...) ni reprise ni
écartée, exigence non mesurable, doublon. Corrigez jusqu'à zéro erreur et
zéro phrase non reprise. Produit `exigences.md` pour la revue et
`exigences.csv` pour un tableur.
