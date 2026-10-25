# Revue d'architecture : Portail de sinistres, option A

Revue de l'option retenue avant le lancement des développements.

Option revue : A (`options.json`).

**Avis : défavorable** (2 constat(s) haut(s), 7 moyen(s), 7 bas ouverts ; 2 accepté(s)).

Contrôle par `arch_review.py` (35 règles) de la description écrite pour la revue : 7 composants, 5 flux, 4 scénarios de qualité. Les points hors de la description sont listés à la fin.

## Synthèse

| Axe | Haute | Moyenne | Basse | Acceptés |
| --- | --- | --- | --- | --- |
| Structure | 0 | 1 | 1 | 1 |
| Traçabilité des exigences | 0 | 2 | 1 | 0 |
| Scénarios de qualité | 1 | 1 | 1 | 0 |
| Décisions | 0 | 0 | 2 | 0 |
| Risques | 1 | 0 | 1 | 0 |
| Well-Architected (cloud) | 0 | 3 | 1 | 1 |

## Arbre d'utilité

### Performance

| ID | Scénario | Mesure | Importance / difficulté | Exigences | Évaluation |
| --- | --- | --- | --- | --- | --- |
| QS-01 | 10 000 assurés déclarent après une tempête (pic) : les déclarations sont enregistrées | 95 % en moins de 2 s | haute / moyenne | ENF-001 | satisfait : mise à l'échelle automatique, file vers la gestion |

### Disponibilité

| ID | Scénario | Mesure | Importance / difficulté | Exigences | Évaluation |
| --- | --- | --- | --- | --- | --- |
| QS-02 | l'annuaire des assurés ne répond plus : l'assuré est prévenu et peut revenir plus tard | - | - / - | ENF-002 | à risque : aucun mode dégradé prévu |

### Sécurité

| ID | Scénario | Mesure | Importance / difficulté | Exigences | Évaluation |
| --- | --- | --- | --- | --- | --- |
| QS-03 | un tiers tente de se connecter avec un mot de passe volé : la connexion est refusée sans le second facteur | 100 % des tentatives | - / - | ENF-004, SEC-01 | non satisfait : MFA non activée par l'annuaire |

### Conformité

| ID | Scénario | Mesure | Importance / difficulté | Exigences | Évaluation |
| --- | --- | --- | --- | --- | --- |
| QS-04 | audit de la localisation des données : toutes les données sont en Union européenne | aucune donnée hors UE | - / - | ENF-003 | à vérifier |

## Constats

| ID | Règle | Axe | Gravité | Élément | Constat | Correction | Référence | Statut |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| C01 | QUA-01 | Scénarios de qualité | haute | QS-03 | Scénario non satisfait sans risque noté : la connexion est refusée sans le second facteur | Noter le risque (risks, scenarios) avec sa mesure d'atténuation, ou changer l'architecture. | ATAM (SEI) : risques | à traiter |
| C02 | RSK-01 | Risques | haute | R-01 | Risque haut sans mesure d'atténuation : la connexion bloque si l'annuaire tombe | Donner la mesure d'atténuation (mitigation) ou changer l'architecture. | arc42 §11 ; ATAM (SEI) | à traiter |
| C03 | OPS-01 | Well-Architected (cloud) | moyenne | aws | Excellence opérationnelle : Pas de supervision : aucun service de supervision | Ajouter le service de supervision du fournisseur (métriques, journaux, alertes). | AWS Well-Architected OPS04 : observabilité (CloudWatch) | accepté : supervision par l'outil central |
| C04 | QUA-03 | Scénarios de qualité | moyenne | QS-02 | Scénario sans mesure : l'assuré est prévenu et peut revenir plus tard | Donner une mesure vérifiable de la réponse (« 95 % en moins de 2 s »). | ATAM (SEI) : scénario de qualité (stimulus, environnement, réponse, mesure) | à traiter |
| C05 | REL-02 | Well-Architected (cloud) | moyenne | api | Fiabilité : Instance unique : API déclarations | Au moins deux instances (count), un groupe d'autoscaling ou une instance par zone. | AWS Well-Architected REL10 et REL07 : redondance, adaptation à la demande | à traiter |
| C06 | SEC-03 | Well-Architected (cloud) | moyenne | F3 | Sécurité : Flux non chiffré à travers une frontière : F3 API déclarations → Annuaire des assurés (Extérieur) | Chiffrer le flux ("encrypted": true, ou protocole HTTPS, TLS...). | AWS Well-Architected SEC09 : protéger les données en transit | à traiter |
| C07 | SEC-05 | Well-Architected (cloud) | moyenne | F1 | Sécurité : Point d'entrée public sans WAF : F1 Assuré → Portail web | Ajouter le pare-feu applicatif du fournisseur devant le point d'entrée. | AWS Well-Architected SEC05 : AWS WAF devant les points d'entrée | à traiter |
| C08 | STR-06 | Structure | moyenne | api>annuaire | Dépendance synchrone à un système externe sur le parcours utilisateur : le parcours de l'utilisateur attend annuaire | Délai, disjoncteur et mode dégradé, ou file asynchrone ; niveau de service du tiers dans les exigences. | Release It! (M. Nygard) : points d'intégration ; ISO/IEC 25010 : disponibilité | à traiter |
| C09 | STR-08 | Structure | moyenne | portail | Point unique de défaillance : une seule instance sur le parcours de l'utilisateur, disponibilité exigée | Redonder le composant (count 2 ou plus), ou accepter l'écart avec sa raison (service managé...). | ISO/IEC 25010 : disponibilité, tolérance aux pannes | accepté : CDN managé, redondant par construction |
| C10 | TRA-02 | Traçabilité des exigences | moyenne | ENF-005 | Exigence non fonctionnelle sans scénario de qualité : Coût de fonctionnement (importante) | Écrire le scénario (stimulus, réponse, mesure) et l'évaluer. | ATAM (SEI) : arbre d'utilité ; ISO/IEC 25010 | à traiter |
| C11 | TRA-02 | Traçabilité des exigences | moyenne | SEC-02 | Exigence non fonctionnelle sans scénario de qualité : Conserver les journaux (importante) | Écrire le scénario (stimulus, réponse, mesure) et l'évaluer. | ATAM (SEI) : arbre d'utilité ; ISO/IEC 25010 | à traiter |
| C12 | DEC-02 | Décisions | basse | ADR-002 | Décision encore proposée : File de messages managée | Faire accepter la décision ou la remplacer. | arc42 §9 ; ADR (M. Nygard) | à traiter |
| C13 | DEC-03 | Décisions | basse | compromis 2 | Compromis sans décision qui l'assume : MFA : sécurité contre facilité d'accès | Rattacher le compromis à sa décision (decision). | ATAM (SEI) : compromis ; arc42 §9 | à traiter |
| C14 | QUA-04 | Scénarios de qualité | basse | QS-04 | Scénario à vérifier : toutes les données sont en Union européenne | Évaluer le scénario : satisfait, à risque ou non satisfait, avec la raison. | ATAM (SEI) : analyse | à traiter |
| C15 | RSK-02 | Risques | basse | R-01 | Risque sans responsable : la connexion bloque si l'annuaire tombe | Nommer le responsable (owner). | arc42 §11 | à traiter |
| C16 | SEC-07 | Well-Architected (cloud) | basse | aws | Sécurité : Pas de journal d'audit ni de détection : aucun journal d'audit ni détection | Ajouter le journal d'audit ou la détection des menaces du fournisseur. | AWS Well-Architected SEC04 : journalisation et détection (CloudTrail, GuardDuty) | à traiter |
| C17 | STR-07 | Structure | basse | outils | Composant sans flux : aucun flux n'entre ni ne sort | Relier le composant ou le retirer de l'architecture. | arc42 §5 : vue en briques | à traiter |
| C18 | TRA-03 | Traçabilité des exigences | basse | outils | Composant sans exigence ni décision : Utilitaires | Dire quelle exigence ou décision justifie le composant (refs), ou le retirer. | ISO/IEC/IEEE 42010 : justification de l'architecture | à traiter |

## Risques

| ID | Risque | Gravité | Scénarios | Atténuation | Responsable |
| --- | --- | --- | --- | --- | --- |
| R-01 | la connexion bloque si l'annuaire tombe | haute | QS-02 | à définir | à désigner |

## Points de sensibilité et compromis

- Sensibilité : taille de la file de déclarations (file, QS-01)
- Compromis Performance contre Utilisabilité : file asynchrone : charge absorbée, transmission différée (décision ADR-001)
- Compromis Sécurité contre Utilisabilité : MFA : sécurité contre facilité d'accès (sans décision)

## Décisions

| ID | Décision | Statut | Exigences | Composants |
| --- | --- | --- | --- | --- |
| ADR-001 | Option A retenue (`adr-architecture.md`) | acceptée | ENF-001 | - |
| ADR-002 | File de messages managée | proposée | - | file |

## Traçabilité des exigences

| Exigence | Titre | Priorité | Composants | Décisions | Scénarios |
| --- | --- | --- | --- | --- | --- |
| EF-001 | Déclarer un sinistre en ligne | indispensable | portail, api | - | - |
| EF-002 | Suivre son dossier | importante | api | - | - |
| EF-003 | Transmettre au gestionnaire | indispensable | file, gestion | - | - |
| ENF-001 | Tenir la charge | indispensable | api | ADR-001 | QS-01 |
| ENF-002 | Disponibilité | importante | file | - | QS-02 |
| ENF-003 | Données en Union européenne | indispensable | api | - | QS-04 |
| ENF-004 | Authentification forte | indispensable | annuaire | - | QS-03 |
| ENF-005 | Coût de fonctionnement | importante | api | - | - |
| SEC-01 | Chiffrer les échanges | indispensable | portail | - | QS-03 |
| SEC-02 | Conserver les journaux | importante | api | - | - |

## À vérifier hors de la description

- **Sécurité applicative** : authentification et droits par rôle, validation des entrées, dépendances vulnérables (OWASP ASVS).
- **Données** : propriétaire de chaque donnée, rétention et purge, données personnelles (RGPD).
- **Exploitation** : journaux corrélés, métriques et alertes, procédures de reprise testées.
- **Performance** : tests de charge sur les scénarios de performance retenus.
- **Évolution** : versionnement des API et des événements, compatibilité ascendante.
- **Organisation** : équipes et frontières des composants (loi de Conway), compétences à acquérir.
