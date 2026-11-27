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
- **Entrées** : Documents en Markdown (sortie de doc-to-markdown) dans un dossier sources ; Description JSON des exigences : title, sources, requirements (id repris des documents ou EF-001 / SECU-01, PERF-01... par catégorie, nature, title, text, priority, category ou domain, metric, sources avec citation, questions, status), ignored, glossary (terme, définition, synonymes).
- **Sorties** : <nom>.md : catalogue pour la revue (exigences fonctionnelles, non fonctionnelles, questions, exigences déduites, retirées, phrases écartées, glossaire avec les exigences qui emploient chaque terme) ; chaque source est un lien Markdown vers le document, à la section de la ligne citée ; <nom>.csv : même catalogue pour un tableur (séparateur ;, UTF-8 avec BOM) ; ecarts-exigences.md : écart entre le catalogue validé et sa copie de travail d'une évolution (req_diff.py).
- **`req_build.py`** : Vérifie chaque citation dans son document et en donne la ligne, repère les phrases des sources reprises par aucune exigence (phrases normatives par la regex ; avec --candidates et son tri par un modèle léger, les phrases qu'il tient pour des exigences), signale une exigence renumérotée alors que sa source porte un identifiant, doublons, exigences non mesurables et dimensions de volumétrie absentes (utilisateurs, pic, débit, données, croissance, conservation), puis écrit le catalogue en Markdown et en CSV ; avec --draft, écrit d'abord le brouillon de la description (une exigence par phrase normative des sources, citation exacte, identifiant du document, nature, catégorie, priorité et mesure déduites) que le modèle trie. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`req_diff.py`** : Compare le catalogue validé et sa copie de travail d'une évolution : exigences ajoutées, retirées (absentes ou sorties du périmètre retenu) et modifiées champ par champ (texte, priorité, mesure, catégorie, nature, domaine, titre), exigence ajoutée sans source signalée ; avec --domains, contextes bornés qui portent chaque exigence changée et exigence ajoutée sans contexte ; avec --start, copie la référence dans la copie de travail ; les deux catalogues sont validés contre le schéma de req_build.py. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube ; fichiers de travail dans `.myskills-tmp/` du dossier de travail, jamais dans le dossier temporaire du système.
- **Dépend de** `domain-design` (`domain_build.py`, facultatif : sans lui, avertissement) : req_diff.py --domains : valider domaines.json contre son schéma.
- **Passe la main** au skill `doc-to-markdown` : les documents ne sont pas encore en Markdown.
- **Passe la main** au skill `architecture-options` : le catalogue est validé : proposer des architectures.
- **Passe la main** au skill `decision-log` : noter les choix (exigence déduite, phrase écartée, priorité) et soumettre le catalogue à la revue.

## 1. Lire les sources

Les documents sont en Markdown dans un dossier `sources/` (sinon,
`doc-to-markdown` d'abord). Commencez par le brouillon, puis lisez chaque
document une fois, en entier, pour le trier :

```bash
uv run scripts/req_build.py exigences.json --draft
```

Une exigence par phrase normative, citation exacte, identifiant du document
s'il en porte un, nature, catégorie, priorité (doit : indispensable, pourra :
souhaitable) et mesure déduites des mots. Retirez ce qui n'est pas une
exigence de la solution (ou passez-le dans `ignored` avec sa raison),
fusionnez, corrigez titres et catégories, ajoutez les exigences sans verbe
normatif et le glossaire.

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
    {"id": "PERF-01", "title": "Tenir la charge", "text": "2 000 déclarations par jour.",
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
  fonctionnelle et, pour une non fonctionnelle, le préfixe de sa catégorie
  suivi de deux chiffres : `PERF` performance, `DISP` disponibilité, `SECU`
  sécurité, `CONF` conformité, `EXPL` exploitabilité, `MAIN`
  maintenabilité, `EVOL` évolutivité, `INTE` interopérabilité, `UTIL`
  utilisabilité, `PORT` portabilité, `COUT` coût, `ENF` autre (`SECU-01`).
  Un préfixe qui ne suit pas la catégorie est signalé ; les `ENF-nnn` d'un
  catalogue plus ancien se renomment par `mission.py upgrade --apply` (ou
  `journal.py upgrade`), correspondance gardée dans `renamed`. Le script signale une
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
- **Volumétrie** : le script attend six dimensions (utilisateurs, pic ou
  simultanés, débit, volume de données, croissance, conservation), lues dans
  les exigences retenues ou leurs questions. Une dimension absente des
  sources se demande tout de suite : une question dans l'exigence la plus
  proche, posée à la première revue, pas au chiffrage. Sans objet pour le
  projet : `"volumetry": {"retention": "aucune donnée conservée"}`.
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
écartée, exigence non mesurable, doublon, volumétrie absente
(`volumetry_missing`, section « Volumétrie » d'`exigences.md`). Corrigez jusqu'à zéro erreur et
zéro phrase non reprise. Produit `exigences.md` pour la revue et
`exigences.csv` pour un tableur.

**Tri des phrases non reprises** (recommandé : la regex ne voit pas les
exigences écrites au présent, « le système envoie un accusé... ») :

1. `uv run scripts/req_build.py exigences.json --candidates` écrit
   `exigences.candidats.json` : la consigne et les phrases à trier.
2. Confiez ce seul fichier à un sous-agent de niveau simple (modèle léger) :
   il suit la consigne et écrit `exigences.tri.json`. Sans outil de
   sous-agent, faites-le vous-même avec la même consigne.
3. Relancez `req_build.py exigences.json` : le tri est lu d'office et
   décide seul pour les phrases triées ; ne restent signalées que celles
   qu'il tient pour des exigences (`method` : `tri`). Une phrase ajoutée
   ensuite aux sources repasse par l'étape 1, qui n'écrit que les phrases
   pas encore triées.

Mesuré sur 112 phrases étiquetées (`tests/triage_eval.py`) : F1 0,99 à 1
pour le tri par un modèle léger, 0,50 pour la regex seule.

## 4. Évolution d'un catalogue validé

Pour une demande de changement, ne touchez pas au catalogue validé :
`uv run scripts/req_diff.py ../exigences.json exigences.json --start` en
fait la copie de travail, que vous modifiez (exigences ajoutées avec leur
citation de la demande, textes ou priorités changés, `status` pour en
retirer). Puis `uv run scripts/req_build.py exigences.json` et `uv run
scripts/req_diff.py ../exigences.json exigences.json --out
ecarts-exigences.md` (avec `--domains ../domaines.json`, les contextes
touchés).
