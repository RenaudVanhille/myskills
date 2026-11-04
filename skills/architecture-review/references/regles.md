# Règles de la revue

À lire seulement pour expliquer un constat ; `arch_review.py --rules`
donne la même liste.

| Axe | Contrôles |
| --- | --- |
| Structure | cycle d'appels synchrones, base partagée par plusieurs composants, dépendance vers une couche supérieure, composant pivot (6 voisins ou plus), chaîne de plus de 4 appels synchrones, dépendance synchrone à un externe sur le parcours utilisateur, point unique de défaillance quand la disponibilité est exigée, composant sans flux |
| Code | dépendance du code absente de l'architecture, cycle entre composants dans le code, code non rattaché |
| Traçabilité | exigence indispensable sans composant, décision ni scénario (ou non couverte par l'option), exigence non fonctionnelle sans scénario, composant sans exigence ni décision |
| Scénarios | non satisfait ou à risque sans risque noté, non satisfait (gravité : son importance), sans mesure, à vérifier, scénario attendu absent (QUA-06 : pointe de charge, panne, sinistre, attaque, croissance, incident selon les exigences) |
| Décisions et risques | aucune décision, décision proposée, compromis sans décision, risque haut sans atténuation, risque ouvert (gravité : la sienne), risque sans responsable |
