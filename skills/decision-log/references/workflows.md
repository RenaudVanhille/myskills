# Workflows livrés et forme d'une définition

À lire seulement pour choisir un workflow livré ou en écrire un.

`--definition` prend un workflow livré dans `workflows/` ou un fichier JSON
de même forme (`--schema` : `$defs.definition`) :

| Workflow | Étapes |
| --- | --- |
| `architecture` | documents, exigences, domaines (facultative), architectures, schemas, puis revue et chiffrage en parallèle, et dossier (facultatives) : des documents du projet au dossier d'architecture technique |
| `cloud-existant` | description, puis schemas et menaces en parallèle : du code d'infrastructure au schéma cloud et au modèle STRIDE |
| `revue-dossier` | documents, exigences, revue, avis (facultative) : instruire un dossier reçu pour un comité, sans concevoir d'options |
| `conformite` | exigences et description en parallèle, menaces, rgpd, plan : menaces STRIDE, qualification de l'hébergeur, registre et AIPD RGPD, puis plan d'actions et dossier de conformité |
| `migration-cloud` | exigences, evaluation, puis cible suivie du chiffrage et de l'exploitation, en parallèle de la feuille-de-route, et dossier (chiffrage, exploitation et dossier facultatifs) : évaluation 6R et vagues, architecture cible, trajectoire avec chemin critique |
| `maquettes` | design-system, pages, ux, decoupage : des maquettes d'écrans aux pages HTML comparées, à la revue UX et aux lots du chiffrage frontend (constats UX retenus compris) |
| `avant-vente` | documents, depouillement, qualification, exigences, domaines (facultative), architectures, schemas, conformite, maquettes, backend, chiffrage, revue, exploitation (facultative), registre, memoire, soutenance : réponse à un appel d'offres, des documents reçus à l'offre |
| `cadrage` | documents, comptes-rendus, processus (facultative), exigences, domaines (facultative), modele-donnees, architectures, dimensionnement, interfaces, recette : cadrage d'un projet : ateliers, processus, exigences, données, dimensionnement, interfaces et recette |
| `documentation` | documents, puis notes (facultative) et synthese en parallèle, schemas, document : de documents en vrac à une documentation pour un public donné |
| `restitution` | messages, puis schemas et presentation en parallèle, document : restitution de l'option retenue au comité ou aux décideurs, dans le sous-dossier restitution/ d'un dossier validé |
| `retro-documentation` | code, puis constat, infrastructure et donnees (facultatives) en parallèle, processus (facultative), domaines, revue, trajectoire et dossier (facultatives) : d'une application existante (graphe graphify) à son architecture constatée et à sa trajectoire de modernisation |
| `evolution` | documents, exigences, puis contrats, donnees et options en parallèle, decision, chiffrage (toutes facultatives), dossier : demande de changement sur une solution validée, dans le sous-dossier evolution/ |

```json
{"name": "revue-code", "title": "Revue d'un dépôt", "stages": [
  {"id": "analyse", "skills": ["doc-to-markdown"], "deliverables": ["analyse.md"],
   "optional": ["annexes/*.md"], "checks": ["doc-to-markdown : validate.py analyse.md"],
   "instructions": "Une phrase de consigne."}]}
```
