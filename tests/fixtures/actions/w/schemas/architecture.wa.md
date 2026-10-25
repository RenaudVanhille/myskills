# Revue Well-Architected : Boutique en ligne : déploiement AWS

Contrôle automatique du schéma par `wa_check.py` (21 règles ; cadres : AWS Well-Architected). Ce n'est pas une revue complète : les points hors du schéma sont listés à la fin.

## Synthèse

| Pilier | Haute | Moyenne | Basse | Acceptés |
| --- | --- | --- | --- | --- |
| Fiabilité | 0 | 3 | 0 | 0 |
| Sécurité | 0 | 4 | 1 | 0 |
| Excellence opérationnelle | 0 | 1 | 0 | 0 |
| Efficacité des performances | 0 | 0 | 0 | 0 |
| Optimisation des coûts | 0 | 0 | 1 | 0 |
| Durabilité | 0 | 0 | 1 | 0 |
| Conventions de schéma | 0 | 0 | 0 | 0 |

## Constats

| ID | Règle | Pilier | Gravité | Élément | Constat | Correction | Référence | Statut |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| W01 | OPS-01 | Excellence opérationnelle | moyenne | aws | Pas de supervision : aucun service de supervision | Ajouter le service de supervision du fournisseur (métriques, journaux, alertes). | AWS Well-Architected OPS04 : observabilité (CloudWatch) | à traiter |
| W02 | REL-01 | Fiabilité | moyenne | eu-west-3-paris | Une seule zone de disponibilité : eu-west-3 (Paris) : 0 zone pour API commandes (ECS Fargate) ×3, Aurora PostgreSQL, Redis | Répartir calcul et bases sur au moins deux zones (groupes az ou zone). | AWS Well-Architected REL10 : isoler les pannes, déployer sur plusieurs zones | à traiter |
| W03 | REL-03 | Fiabilité | moyenne | db | Base sans réplique ni sauvegarde : Aurora PostgreSQL | Déclarer la réplique (flux replication, count) ou le service de sauvegarde. | AWS Well-Architected REL09 : sauvegarder les données ; REL10 | à traiter |
| W04 | REL-03 | Fiabilité | moyenne | cache | Base sans réplique ni sauvegarde : Redis | Déclarer la réplique (flux replication, count) ou le service de sauvegarde. | AWS Well-Architected REL09 : sauvegarder les données ; REL10 | à traiter |
| W05 | SEC-03 | Sécurité | moyenne | F4 | Flux non chiffré à travers une frontière : F4 ALB → API commandes (ECS Fargate) ×3 (Sous-réseau public, Sous-réseau privé applicatif) | Chiffrer le flux ("encrypted": true, ou protocole HTTPS, TLS...). | AWS Well-Architected SEC09 : protéger les données en transit | à traiter |
| W06 | SEC-03 | Sécurité | moyenne | F5 | Flux non chiffré à travers une frontière : F5 API commandes (ECS Fargate) ×3 → Aurora PostgreSQL (Sous-réseau privé applicatif, Sous-réseau privé données) | Chiffrer le flux ("encrypted": true, ou protocole HTTPS, TLS...). | AWS Well-Architected SEC09 : protéger les données en transit | à traiter |
| W07 | SEC-03 | Sécurité | moyenne | F6 | Flux non chiffré à travers une frontière : F6 API commandes (ECS Fargate) ×3 → Redis (Sous-réseau privé applicatif, Sous-réseau privé données) | Chiffrer le flux ("encrypted": true, ou protocole HTTPS, TLS...). | AWS Well-Architected SEC09 : protéger les données en transit | à traiter |
| W08 | SEC-03 | Sécurité | moyenne | F10 | Flux non chiffré à travers une frontière : F10 API commandes (ECS Fargate) ×3 → NAT Gateway (Sous-réseau privé applicatif, Sous-réseau public) | Chiffrer le flux ("encrypted": true, ou protocole HTTPS, TLS...). | AWS Well-Architected SEC09 : protéger les données en transit | à traiter |
| W09 | COST-01 | Optimisation des coûts | basse | app | Capacité fixe sans autoscaling : API commandes (ECS Fargate) ×3 | Ajuster la capacité à la demande : groupe d'autoscaling, VMSS, HPA ou service serverless. | AWS Well-Architected COST09 et SUS02 : aligner l'offre sur la demande | à traiter |
| W10 | SEC-07 | Sécurité | basse | aws | Pas de journal d'audit ni de détection : aucun journal d'audit ni détection | Ajouter le journal d'audit ou la détection des menaces du fournisseur. | AWS Well-Architected SEC04 : journalisation et détection (CloudTrail, GuardDuty) | à traiter |

## À vérifier hors du schéma

- **Excellence opérationnelle** : infrastructure en code, déploiements automatisés et réversibles, procédures d'exploitation.
- **Sécurité** : moindre privilège IAM, chiffrement au repos et gestion des clés, correctifs, réponse aux incidents.
- **Fiabilité** : quotas, tests de reprise (PRA), RPO et RTO mesurés, dépendances externes.
- **Efficacité des performances** : choix des tailles d'instance, tests de charge, cache applicatif.
- **Optimisation des coûts** : étiquetage et suivi des coûts, réservations ou engagements, cycle de vie des données.
- **Durabilité** : choix de la région, taux d'utilisation, rétention des données.
