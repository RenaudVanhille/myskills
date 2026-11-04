# Workflows livrés et forme d'une définition

À lire seulement pour choisir un workflow livré ou en écrire un.

`--definition` prend un workflow livré dans `workflows/` ou un fichier JSON
de même forme (`--schema` : `$defs.definition`) :

| Workflow | Étapes |
| --- | --- |
| `architecture` | documents, exigences, architectures, schemas, puis revue et chiffrage en parallèle, et dossier (facultatives) : des documents du projet au dossier d'architecture technique |
| `cloud-existant` | description, puis schemas et menaces en parallèle : du code d'infrastructure au schéma cloud et au modèle STRIDE |
| `revue-dossier` | documents, exigences, revue, avis (facultative) : instruire un dossier reçu pour un comité, sans concevoir d'options |
| `conformite` | exigences et description en parallèle, menaces, rgpd, plan : menaces STRIDE, qualification de l'hébergeur, registre et AIPD RGPD, puis plan d'actions et dossier de conformité |
| `migration-cloud` | exigences, evaluation, puis cible suivie du chiffrage, en parallèle de la feuille-de-route, et dossier (chiffrage et dossier facultatifs) : évaluation 6R et vagues, architecture cible, trajectoire avec chemin critique |
| `maquettes` | design-system, pages, ux, decoupage : des maquettes d'écrans aux pages HTML comparées, à la revue UX et aux lots du chiffrage frontend (constats UX retenus compris) |
| `avant-vente` | documents, depouillement, qualification, exigences, architectures, schemas, conformite, maquettes, chiffrage, revue, registre, memoire, soutenance : réponse à un appel d'offres, des documents reçus à l'offre |
| `cadrage` | documents, comptes-rendus, exigences, modele-donnees, architectures, dimensionnement, interfaces, recette : cadrage d'un projet : ateliers, exigences, données, dimensionnement, interfaces et recette |

```json
{"name": "revue-code", "title": "Revue d'un dépôt", "stages": [
  {"id": "analyse", "skills": ["doc-to-markdown"], "deliverables": ["analyse.md"],
   "optional": ["annexes/*.md"], "checks": ["doc-to-markdown : validate.py analyse.md"],
   "instructions": "Une phrase de consigne."}]}
```
