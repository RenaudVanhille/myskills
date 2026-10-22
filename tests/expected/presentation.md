# Architecture du service de paiement

Le service de paiement reçoit les commandes, appelle la banque et notifie le client. Ce document décrit ses composants.

## Flux d'un paiement

![schema-flux.png](attachments/presentation-1.png)

Schéma : l'API transmet la commande au Worker, qui appelle la Banque.
