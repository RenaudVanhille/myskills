# Hébergeur et hypothèses de production

Détail de la section 2 du skill, à lire seulement pour un hébergeur imposé (souverain, SecNumCloud, HDS) ou pour changer les hypothèses de production.

- **Hébergeur** : `hosting` donne l'hébergeur par défaut et les
  qualifications exigées par les exigences, par exemple
  `{"provider": "cloud-temple", "qualifications": ["secnumcloud"], "refs": ["CONF-01"]}` ;
  une ligne peut en nommer un autre (`provider`). Sans `hosting`, c'est le
  `provider` de l'option. Les hébergeurs connus (aws, azure, gcp, ovh,
  cloud-temple, outscale, s3ns, bleu, numspot, scaleway, sur-site), leur
  juridiction et leurs qualifications (secnumcloud, hds) sont dans
  `shared/providers.json` (copié dans `scripts/lib/`) ; ne le chargez pas, le script le lit. Un
  hébergeur ou une qualification propre au projet s'ajoute dans un
  catalogue du dossier, de même forme, cité par `providers`. Le script
  signale chaque ligne cloud ou service dont l'hébergeur n'a pas une
  qualification exigée, rappelle de vérifier l'offre chez un hébergeur
  qualifié (la qualification porte sur une offre) et avertit si l'option
  est décrite chez un autre fournisseur.
- **Hypothèses de production** : la charge saisie est celle d'une équipe
  sans IA ; le script la recalcule toujours pour trois hypothèses, sans
  IA, avec IA (développement assisté) et dev IA natif (agents qui écrivent
  code et tests, l'équipe spécifie et valide). Pour chacune : facteur de
  charge par phase, incertitude sur le gain (commune à tous les lots, elle
  élargit la fourchette), adoption (outillage, garde-fous, formation, en %
  de la charge), licences et jetons par jour travaillé, facteur du run.
  Les valeurs par défaut et leurs sources sont dans
  `references/hypotheses-ia.json` (ne le chargez pas, le script le lit).
  Ne les changez que sur une base : mesure de l'équipe, lot pilote, offre
  d'un éditeur, par exemple
  `"scenarios": {"avec-ia": {"factors": {"realisation": 0.65}, "basis": "mesure de l'équipe, 2026"}}`.
  Un lot où l'IA aide peu ou beaucoup (code ancien, progiciel peu
  documenté, sujet réglementé) prend son propre facteur,
  `"ai": {"avec-ia": 0.95, "ia-natif": 0.9}`, avec la raison dans `note`.
