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
- **Entrées** : Un dossier par mission : avant-vente (documents reçus, souvent des PDF) ou revue d'architecture (documentation et code, un dépôt par service) ; Facultatif : la description de la mission en JSON (nature, client, échéance, workflows, dépôts, référentiels, écarts acceptés), schéma shared/schemas/mission.schema.json ; Facultatif : le référentiel du client partagé entre ses missions (referentiel.path de mission.json) : dossier de notes typées application, terme, adr.
- **Sorties** : mission.json à la racine de la mission, documents/, le vault Obsidian de la mission (et code/ pour une revue), le workflow de la nature démarré (workflow.json) ; Dans le vault : la note Mission (type mission) : workflows et étapes, dépôts et commits, référentiels, contrôles de cohérence ; Rapport : état de la mission et contrôles de cohérence entre livrables (MIS-01 à MIS-09) ; Avec referentiel.py : dans le vault de la mission, Référentiel/ (notes du référentiel du client) ; dans le référentiel, les notes versées par push --apply.
- **`mission.py`** : Ouvre une mission dans un dossier (mission.json, documents/, vault, code/ pour une revue, workflow de sa nature lancé avec son vault ; refusé dans une mission existante), ajoute ses dépôts et fige leur commit, fait le point (workflows, étape courante, dépôts, référentiels) et contrôle sans modèle la cohérence entre livrables : exigence indispensable hors de l'option retenue, composant non chiffré, exigence non fonctionnelle indispensable sans scénario de revue, livrable validé modifié, revue ou chiffrage d'une autre option, dépôt absent ou hors du commit figé, référentiel introuvable. Réécrit la note Mission du vault, vérifiée contre l'ontologie. upgrade remet une mission ouverte avec une version antérieure au niveau des scripts actuels, à blanc sauf --apply. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`referentiel.py`** : Partage le référentiel du client entre ses missions (applications du SI, glossaire, ADR) : pull copie ses notes typées dans le vault de la mission (Référentiel/, liens réécrits, notes retirées du référentiel retirées) ; push verse les notes de la mission de ces types dans le référentiel (titre, propriétés, texte d'introduction, liens vers des notes non partagées réduits à leur libellé), sans jamais écraser une note présente (même id, titre ou alias) : alias complétés, différence de texte signalée en conflit ; à blanc sans --apply. Notes vérifiées contre l'ontologie, sous le verrou du vault. Rapport JSON (0 succès, 1 erreur).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `decision-log` (`journal.py`, obligatoire) : démarrer le workflow de la mission (init), lire son état (status) et le mettre à niveau (upgrade).
- **Dépend de** `markdown-to-obsidian` (`lib/vault_ontology.py`, obligatoire) : ontologie du vault Obsidian (source unique) : construire et vérifier les notes écrites.
- **Vault Obsidian** : écrit les notes de type `mission`, `application`, `terme`, `adr` ; lit les notes typées, selon l'ontologie du vault (`vault_ontology.py` du skill markdown-to-obsidian).
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

Une mission ouverte avec une version antérieure de myskills se remet à
niveau d'une commande, à blanc d'abord :

```bash
uv run scripts/mission.py upgrade DOSSIER
uv run scripts/mission.py upgrade DOSSIER --apply
```

Montrez à l'utilisateur le rapport à blanc (`upgrade.workflows` : étapes
ajoutées, retirées, gardées, liens, `journal.md`) avant `--apply`.
L'avancement, les fichiers validés et le journal sont gardés ;
`--keep-definition` garde les étapes et consignes d'origine. Rejouable.

## 4. Référentiel du client entre missions

Un client a souvent plusieurs missions : ses applications, son glossaire et
ses ADR se capitalisent dans **son** référentiel, un dossier de notes typées
hors de la mission (`"referentiel": {"path": "..."}` dans `mission.json`,
absolu ou relatif). Jamais un référentiel commun à plusieurs clients.

```bash
uv run scripts/mission.py init DOSSIER ... --referentiel REF  # ouverture : pull fait d'office
uv run scripts/referentiel.py pull DOSSIER          # plus tard : rafraîchit <vault>/Référentiel/
uv run scripts/referentiel.py push DOSSIER          # à la fin : ce qui serait versé (à blanc)
uv run scripts/referentiel.py push DOSSIER --apply  # après accord de l'utilisateur
```

`push` ne verse que les types `application`, `terme` et `adr` (`--types`),
réduits au titre, aux propriétés et au texte d'introduction ; une note déjà
présente n'est jamais écrasée (alias complétés, différence signalée dans
`conflicts`). Montrez `added` et `conflicts` à l'utilisateur avant
`--apply` : c'est lui qui décide de ce qui sort de la mission. Un référentiel
introuvable donne MIS-08 au `check`. `status` et `check` font ce `push` à
blanc et le résument dans `referentiel` (`to_share`, `conflicts`) ; workflow
terminé et contrôles traités, `next` demande de proposer le versement.
