# Dossier d'architecture : billettique du réseau de transport

Prestataire : société exemple (document de test, fictif). Version 1.2, octobre 2026.

## 1. Contexte et objectifs

Le réseau de transport d'Aubrelac remplace sa billettique. Les voyageurs achètent leurs titres sur une application mobile et un site web, les valident par QR code dans les bus et les trams. Les contrôleurs vérifient les titres avec un terminal portable.

Objectifs annoncés :

- 150 000 voyageurs actifs, 40 000 achats par jour, 5 000 achats par minute au pic de la rentrée ;
- disponibilité de la vente de 99,9 % ;
- paiement par carte conforme PCI DSS, sans stockage des numéros de carte ;
- validation hors ligne dans les véhicules pendant 24 heures.

## 2. Composants

| Composant | Rôle | Technologie |
|---|---|---|
| Application mobile | Achat et présentation des titres | Flutter |
| Site web | Achat des titres | Angular |
| API vente | Panier, commande, émission des titres | Java, une instance |
| API compte | Comptes voyageurs | Java |
| Base billettique | Comptes, commandes, titres | PostgreSQL, une instance |
| Service de paiement | Prestataire de paiement externe | API REST |
| Valideurs embarqués | Lecture des QR codes dans les véhicules | Logiciel embarqué |
| Terminal de contrôle | Contrôle des titres | Android |
| Outil décisionnel | Statistiques de fréquentation | lit la base billettique |

## 3. Flux

1. L'application mobile et le site appellent l'API vente.
2. L'API vente appelle l'API compte, qui appelle le service de paiement, de façon synchrone, avant de confirmer la commande.
3. L'API vente et l'API compte lisent et écrivent la base billettique.
4. Les valideurs embarqués téléchargent la liste des titres chaque nuit depuis l'API vente.
5. L'outil décisionnel lit directement la base billettique.

## 4. Choix d'architecture

- Une seule base pour simplifier les jointures entre comptes et commandes.
- L'API vente est déployée sur une machine virtuelle unique, redémarrée par l'exploitation en cas de panne.
- Aucun cache : la base est jugée assez rapide.

## 5. Sécurité

Les échanges sont chiffrés en TLS. Les voyageurs se connectent par identifiant et mot de passe. Les journaux applicatifs sont conservés 30 jours.

## 6. Points ouverts

- Dimensionnement du pic de la rentrée non mesuré.
- Plan de reprise d'activité à définir.
