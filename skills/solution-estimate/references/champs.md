# Champs du chiffrage

Détail de chaque champ de `chiffrage.json` (`estimate_build.py --schema` en donne la forme).

- **Lots** : un lot par composant de l'option à construire ou à modifier,
  plus les lots transverses (cadrage, tests, déploiement, reprise de
  données, conduite du changement) ; `phase` parmi cadrage, conception,
  realisation, integration, tests, deploiement, migration,
  conduite-changement, pilotage. `component` reprend l'identifiant du
  composant dans `options.json` ; `refs` ajoute les exigences que le lot
  porte en plus de celles du composant.
- **Taux** : `rates` est facultatif. Sans lui, seules les charges sont
  produites (jours et heures, sans montant) : la valorisation reste au
  chef de projet. `hours_per_day` (défaut 7) convertit les jours en heures.
- **Complexité** : `complexity` par lot (faible, moyenne, elevee,
  tres-elevee) quand elle tient à autre chose que la taille (technologie
  nouvelle, dépendance externe, sujet réglementé) ; sans elle, le script
  la déduit de la charge espérée et le signale.
- **Charge** : jours par profil, un nombre si la charge est sûre, sinon
  `[mini, probable, maxi]`. Le script calcule l'espérance (mini + 4
  probable + maxi) / 6 et la fourchette P10-P90 : ne les écrivez pas. Un
  lot dont l'écart mini-maxi dépasse le probable est signalé : découpez-le
  ou levez l'hypothèse.
- **Pilotage** : `overheads` en pourcentage de la charge des lots, au taux
  d'un profil. **Provision** : `contingency`, en % du coût de réalisation.
- **Infrastructure** : une ligne par poste (`kind` cloud, licence,
  materiel, service, autre ; `period` mois, an ou unique), avec `basis`
  obligatoire : grille tarifaire et sa date, devis, ou hypothèse de
  dimensionnement. Aucun tarif ne se cherche en ligne : un prix inconnu est
  une hypothèse à faire valider, notée comme telle.
- **Hébergeur** : `hosting` (hébergeur par défaut, qualifications exigées
  et leurs `refs`), contrôlé ligne par ligne ; détail dans
  `references/hebergeur-et-ia.md`, à lire seulement pour un hébergeur imposé.
- **Run** : par an, `days_per_year` avec `profile`, ou `percent_of_build`
  (part du coût de réalisation hors provision).
- **Budget** : plafonds `build`, `monthly` (infrastructure et run par
  mois), `tco`, avec les exigences qui les fixent (`refs`). Un dépassement
  est signalé.
- **Hypothèses de production** : la charge saisie est celle d'une équipe
  sans IA ; le script la recalcule toujours sans IA, avec IA et en dev IA
  natif. Un lot où l'IA aide peu ou beaucoup prend son facteur
  (`"ai": {"avec-ia": 0.95}`, raison dans `note`) ; les valeurs par défaut
  ne changent que sur une base (`scenarios`, voir
  `references/hebergeur-et-ia.md`).
- **Réemploi** : un lot qui réutilise un autre lot ou un existant le déclare,
  `"reuse": {"from": "L3", "percent": 40, "basis": "même gabarit que L3"}`
  (`from` absent : existant du client). La charge saisie est celle sans
  réemploi ; le script la réduit et donne le taux de réemploi.
  Pas de marge dans un lot : pilotage et provision s'ajoutent une fois.
- **Hypothèses et exclusions** : chacune en une phrase ; elles vont dans
  le chiffrage et, dans un workflow, au journal.
