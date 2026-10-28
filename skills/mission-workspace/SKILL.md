---
name: mission-workspace
description: "Ouvre et suit un espace de travail par mission : un répertoire, un vault Obsidian unique, pour une avant-vente (documents reçus, solution, chiffrage, schémas, POS) ou une revue d'architecture (documentation et code, un dépôt par service). Crée mission.json et l'arborescence, démarre le workflow de la nature, fige les commits revus, fait le point dans le vault et contrôle la cohérence entre livrables (exigences, option retenue, chiffrage, revue). À utiliser au début d'une mission, pour savoir où en est une mission ou avant de la livrer."
---

# mission-workspace

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Les skills
restent installés une fois pour toutes ; seules les données vivent dans la
mission. Une fois `mission.json` posé, les scripts qui écrivent dans le
vault (revue, menaces, Well-Architected, chiffrage, AIPD, journal) le
trouvent seuls en remontant depuis leurs fichiers : ne leur passez plus
`--vault` ni `--folder`. Un `--vault` vers un autre vault y est refusé.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : simple (modèle léger).
- **Entrées** : Un dossier par mission : avant-vente (documents reçus, souvent des PDF) ou revue d'architecture (documentation et code, un dépôt par service) ; Facultatif : la description de la mission en JSON (nature, client, échéance, workflows, dépôts, référentiels, écarts acceptés), schéma shared/schemas/mission.schema.json.
- **Sorties** : mission.json à la racine de la mission, documents/, le vault Obsidian de la mission (et code/ pour une revue), le workflow de la nature démarré (workflow.json) ; Dans le vault : la note Mission (type mission) : workflows et étapes, dépôts et commits, référentiels, contrôles de cohérence ; Rapport : état de la mission et contrôles de cohérence entre livrables (MIS-01 à MIS-09).
- **`mission.py`** : Ouvre une mission dans un dossier (mission.json, documents/, vault, code/ pour une revue, workflow de sa nature lancé avec son vault ; refusé dans une mission existante), ajoute ses dépôts et fige leur commit, fait le point (workflows, étape courante, dépôts, référentiels) et contrôle sans modèle la cohérence entre livrables : exigence indispensable hors de l'option retenue, composant non chiffré, exigence non fonctionnelle indispensable sans scénario de revue, livrable validé modifié, revue ou chiffrage d'une autre option, dépôt absent ou hors du commit figé, référentiel introuvable. Réécrit la note Mission du vault, vérifiée contre l'ontologie. Rapport JSON, codes de sortie : 0 commande appliquée (check : aucun contrôle ouvert au niveau de --fail-on) ; 1 mission introuvable ou invalide (chemin, valeur hors liste, chemin hors de la mission), mission dans une mission, workflow non démarré, ou check avec un contrôle ouvert au niveau de --fail-on.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `decision-log` (`journal.py`, obligatoire) : démarrer le workflow de la mission (init) et lire son état (status).
- **Vault Obsidian** : écrit les notes de type `mission` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** à l'agent `architecture-workflow` : la mission est ouverte : dérouler son workflow (avant-vente pour une avant-vente, revue-dossier pour une revue).
- **Passe la main** à l'agent `architecture-reviewer` : revue d'architecture de la mission, dépôts de code compris.
- **Passe la main** à l'utilisateur : un contrôle ouvert demande une décision : corriger le livrable, ou accepter l'écart avec sa raison (accept).

## 1. Ouvrir la mission

```bash
uv run scripts/mission.py init DOSSIER --nature avant-vente --name "Portail sinistres" --client "Mutuelle X"
uv run scripts/mission.py init DOSSIER --nature revue --name "Plateforme commandes"
```

Nature déduite de la demande : des documents à transformer en solution,
chiffrage, schémas ou POS donnent `avant-vente` ; un existant à juger
(dossier reçu, code) donne `revue`. Ne demandez que ce qui manque pour
le nom. Pour des workflows, dépôts ou référentiels déjà connus, écrivez
la description courte et passez `--file` (`--schema` donne le schéma).

Le rapport donne `started` : le workflow démarré et sa première étape ;
la suite se mène avec l'agent `architecture-workflow`.

## 2. Revue : déclarer les dépôts

Un dépôt par service, cloné par l'utilisateur dans `code/<nom>` :

```bash
uv run scripts/mission.py repo DOSSIER --name commandes --component commandes --alias orders
uv run scripts/mission.py freeze DOSSIER
```

`--component` relie le dépôt à son composant de l'architecture ;
`--alias` donne les autres noms du service dans la configuration des
autres dépôts (hôte, service Kubernetes). `freeze` note le commit de
chaque dépôt : la revue porte sur un commit connu. La revue
d'architecture (`arch_review.py`, `"code": {}`) reprend alors les dépôts
de la mission sans autre chemin.

## 3. Faire le point, contrôler

```bash
uv run scripts/mission.py status DOSSIER
uv run scripts/mission.py check DOSSIER --fail-on haute
```

Les règles de complétude propres à la mission (postes attendus du
chiffrage, scénarios attendus de la revue) vont dans `references.regles`,
lues par `estimate_build.py` et `arch_review.py`. Les principes
d'architecture du client vont dans `references.principes`, contrôlés par
`arch_review.py`. Pour calibrer un chiffrage, `analogues` désigne des
missions passées (dossier ou `chiffrage.json`), lues seulement : ne
l'ajoutez que si l'utilisateur l'accepte pour cette mission
(confidentialité entre clients).

Lisez `next`, `counts` et les `findings` du rapport, pas la note du
vault. Un contrôle ouvert se corrige dans le livrable qu'il cite (la
correction dans `fix`), ou s'accepte dans `accept` de `mission.json`
(`"MIS-02@gestion": "raison"`) avec les mots de l'utilisateur, jamais
sans sa raison. Lancez `check` avant de livrer un dossier ou une offre.
