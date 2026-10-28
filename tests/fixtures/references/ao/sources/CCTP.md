# Cahier des clauses techniques particulières

Métropole d'Aubrelac (collectivité fictive, document de test). Marché AUB-2026-041.

## 1. Contexte

La Métropole d'Aubrelac compte 420 000 habitants. Les rendez-vous des services aux habitants sont aujourd'hui pris par téléphone ou au guichet. Les agents utilisent un annuaire Active Directory et un logiciel d'état civil existant, qui expose une API REST.

## 2. Exigences fonctionnelles

- L'habitant doit pouvoir prendre, modifier et annuler un rendez-vous en ligne, sans créer de compte.
- L'habitant doit recevoir une confirmation et un rappel par courriel ou SMS la veille du rendez-vous.
- Les agents doivent pouvoir gérer les plannings de chaque service et bloquer des créneaux.
- La plateforme doit transmettre les rendez-vous d'état civil au logiciel d'état civil existant par son API.
- Les agents doivent s'authentifier avec leur compte de l'annuaire de la Métropole.
- La plateforme doit produire des statistiques mensuelles de fréquentation par service.

## 3. Exigences non fonctionnelles

- La plateforme doit supporter 2 000 utilisateurs simultanés lors de l'ouverture des inscriptions aux piscines, avec un temps de réponse inférieur à 2 secondes pour 95 % des requêtes.
- La disponibilité doit être d'au moins 99,5 % par mois, hors maintenance programmée.
- Les données doivent être hébergées en France, chez un hébergeur qualifié SecNumCloud.
- La plateforme doit respecter le RGAA 4.1 au niveau AA.
- Les données personnelles des habitants doivent être supprimées 12 mois après le rendez-vous.
- Le titulaire doit réaliser un test d'intrusion avant la mise en production, puis chaque année.
- Le coût d'hébergement ne doit pas dépasser 3 000 euros par mois.

## 4. Niveaux de service et pénalités

- Une anomalie bloquante doit être corrigée en moins de 4 heures ouvrées.
- En cas de dépassement, une pénalité de 500 euros par heure de retard est appliquée, plafonnée à 10 % du montant annuel du marché.

## 5. Réversibilité

À la fin du marché, le titulaire doit restituer l'ensemble des données dans un format ouvert et documenté, et assister le nouveau titulaire pendant trois mois.

## 6. Propriété intellectuelle

Les développements spécifiques deviennent la propriété de la Métropole, qui peut les réutiliser librement.
