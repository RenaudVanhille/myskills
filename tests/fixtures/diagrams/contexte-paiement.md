# Contexte : service de paiement

Le client passe commande sur le site web. L'API de paiement (Java 21) reçoit la
commande et la dépose dans une file de messages. Un worker (Python 3.13) lit la
file, appelle la banque (système externe) et enregistre le résultat dans la
base PostgreSQL. Le client reçoit ensuite une notification par e-mail.

Public visé : l'équipe de développement.
