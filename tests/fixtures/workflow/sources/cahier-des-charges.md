# Cahier des charges : portail de déclaration de sinistres

## Contexte

La mutuelle veut permettre à ses assurés de déclarer un sinistre en ligne,
sans passer par leur agence.

## Besoins fonctionnels

L'assuré doit pouvoir déclarer un sinistre auto ou habitation en ligne, avec
des photos et des justificatifs. Il doit pouvoir suivre l'avancement de son
dossier.

Le gestionnaire devra recevoir chaque déclaration dans l'outil de gestion des
sinistres existant, sans ressaisie.

Un accusé de réception est envoyé par courriel à l'assuré.

## Contraintes

| Thème | Attente |
| --- | --- |
| Charge | Le portail doit supporter 2 000 déclarations par jour, avec un pic après les tempêtes. |
| Disponibilité | Le service devra être disponible 99,5 % du temps. |

Les données personnelles doivent rester hébergées dans l'Union européenne.
Il faut une authentification forte des assurés.
