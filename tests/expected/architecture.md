<!-- genere-par-ia: true · generateur: myskills/doc-to-markdown · Contenu généré par IA, règlement (UE) 2024/1689 (AI Act), article 50 -->
# Architecture du service de paiement

> *Document généré par IA (myskills/doc-to-markdown) : à relire et valider avant tout usage. Mention de transparence, règlement (UE) 2024/1689 (AI Act), article 50.*

Le service de paiement reçoit les commandes, appelle la banque et notifie le client. Ce document décrit ses composants.

## Composants

| Composant | Rôle | Technologie |
| --- | --- | --- |
| API | Reçoit les commandes | Java 21 |
| Worker | Appelle la banque | Python 3.13 |
| Base | Stocke les paiements | PostgreSQL |

## Flux

![architecture-1.png](attachments/architecture-1.png)

Figure 1 : flux d'un paiement.
