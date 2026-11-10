"""Règles, libellés et mises en forme communs à la revue d'architecture (arch_review.py)."""
from __future__ import annotations

import re
import unicodedata


SEVERITIES = ("haute", "moyenne", "basse")


AXES = {"structure": "Structure", "code": "Code et architecture", "tracabilite": "Traçabilité des exigences",
        "qualite": "Scénarios de qualité", "decisions": "Décisions", "risques": "Risques",
        "well-architected": "Well-Architected (cloud)", "principes": "Principes du client",
        "domaines": "Domaines et découpage"}


ATTRIBUTES = {"performance": "Performance", "disponibilite": "Disponibilité", "securite": "Sécurité",
              "conformite": "Conformité", "exploitabilite": "Exploitabilité", "maintenabilite": "Maintenabilité",
              "evolutivite": "Évolutivité", "interoperabilite": "Interopérabilité", "utilisabilite": "Utilisabilité",
              "portabilite": "Portabilité", "cout": "Coût", "autre": "Autre"}


DECIDED = {"proposee": "proposée", "acceptee": "acceptée", "remplacee": "remplacée"}


STATUS = {"satisfait": "satisfait", "risque": "à risque", "non-satisfait": "non satisfait", "a-verifier": "à vérifier"}


ATAM = "ATAM (SEI)"


# règle -> (axe, gravité, titre, correction, référence)
RULES = {
    "STR-01": ("structure", "moyenne", "Cycle de dépendances synchrones",
               "Casser le cycle : inverser une dépendance, passer un flux en asynchrone ou extraire le code commun.",
               "Principe des dépendances acycliques (R. C. Martin) ; ISO/IEC 25010 : modularité"),
    "STR-02": ("structure", "moyenne", "Base de données partagée",
               "Une base par composant propriétaire ; les autres passent par son API ou ses événements.",
               "Database per service (microservices.io) ; ISO/IEC 25010 : modularité, modifiabilité"),
    "STR-03": ("structure", "moyenne", "Dépendance vers une couche supérieure",
               "Inverser la dépendance (interface dans la couche basse, événement) ou revoir la couche du composant.",
               "Architecture en couches (POSA) ; arc42 §8"),
    "STR-04": ("structure", "basse", "Composant pivot",
               "Découper le composant ou introduire une médiation (événements, passerelle).",
               f"ISO/IEC 25010 : modularité ; {ATAM} : point de sensibilité"),
    "STR-05": ("structure", "moyenne", "Chaîne d'appels synchrones longue",
               "Raccourcir la chaîne (asynchrone, cache, agrégation) ; délai et disjoncteur à chaque saut.",
               "Release It! (M. Nygard) : chaînes d'intégration, disjoncteur"),
    "STR-06": ("structure", "moyenne", "Dépendance synchrone à un système externe sur le parcours utilisateur",
               "Délai, disjoncteur et mode dégradé, ou file asynchrone ; niveau de service du tiers dans les exigences.",
               "Release It! (M. Nygard) : points d'intégration ; ISO/IEC 25010 : disponibilité"),
    "STR-07": ("structure", "basse", "Composant sans flux",
               "Relier le composant ou le retirer de l'architecture.", "arc42 §5 : vue en briques"),
    "STR-08": ("structure", "moyenne", "Point unique de défaillance",
               "Redonder le composant (count 2 ou plus), ou accepter l'écart avec sa raison (service managé...).",
               "ISO/IEC 25010 : disponibilité, tolérance aux pannes"),
    "CODE-01": ("code", "moyenne", "Dépendance du code absente de l'architecture",
                "Déclarer le flux s'il est voulu, sinon supprimer la dépendance du code.",
                "Modèle de réflexion (Murphy, Notkin) : divergence entre code et architecture"),
    "CODE-02": ("code", "moyenne", "Cycle de dépendances entre composants dans le code",
                "Casser le cycle : inverser une dépendance (interface, événement) ou déplacer le code commun.",
                "Principe des dépendances acycliques (R. C. Martin)"),
    "CODE-03": ("code", "basse", "Code non rattaché à un composant",
                "Rattacher les fichiers à un composant (code) ou les exclure (.graphifyignore).",
                "arc42 §5 : correspondance entre briques et code"),
    "CODE-04": ("code", "moyenne", "Appel entre services absent de l'architecture",
                "Déclarer le flux s'il est voulu (style async pour un canal), sinon retirer l'appel de la configuration.",
                "Modèle de réflexion (Murphy, Notkin) : divergence ; microservices.io : communication entre services"),
    "CODE-05": ("code", "basse", "Flux déclaré sans trace dans le code ni la configuration",
                "Vérifier le flux (appel par une adresse calculée, passerelle) ou le retirer de l'architecture.",
                "Modèle de réflexion (Murphy, Notkin) : absence"),
    "CODE-06": ("code", "moyenne", "Base de données partagée par plusieurs services",
                "Une base par service propriétaire ; les autres passent par son API ou ses événements.",
                "Database per service (microservices.io)"),
    "CODE-07": ("code", "basse", "Dépôt rattaché à aucun composant",
                "Relier le dépôt à son composant (component du dépôt ou motifs code <dépôt>/...).",
                "arc42 §5 : correspondance entre briques et code"),
    "TRA-01": ("tracabilite", "haute", "Exigence indispensable sans support",
               "Rattacher l'exigence à un composant (refs), une décision ou un scénario, ou la traiter comme écart.",
               "ISO/IEC/IEEE 42010 : chaque préoccupation est traitée"),
    "TRA-02": ("tracabilite", "moyenne", "Exigence non fonctionnelle sans scénario de qualité",
               "Écrire le scénario (stimulus, réponse, mesure) et l'évaluer.",
               f"{ATAM} : arbre d'utilité ; ISO/IEC 25010"),
    "TRA-03": ("tracabilite", "basse", "Composant sans exigence ni décision",
               "Dire quelle exigence ou décision justifie le composant (refs), ou le retirer.",
               "ISO/IEC/IEEE 42010 : justification de l'architecture"),
    "QUA-01": ("qualite", "haute", "Scénario non satisfait sans risque noté",
               "Noter le risque (risks, scenarios) avec sa mesure d'atténuation, ou changer l'architecture.",
               f"{ATAM} : risques"),
    "QUA-02": ("qualite", "moyenne", "Scénario à risque sans risque noté",
               "Noter le risque (risks, scenarios) avec sa mesure d'atténuation.", f"{ATAM} : risques"),
    "QUA-03": ("qualite", "moyenne", "Scénario sans mesure",
               "Donner une mesure vérifiable de la réponse (« 95 % en moins de 2 s »).",
               f"{ATAM} : scénario de qualité (stimulus, environnement, réponse, mesure)"),
    "QUA-04": ("qualite", "basse", "Scénario à vérifier",
               "Évaluer le scénario : satisfait, à risque ou non satisfait, avec la raison.", f"{ATAM} : analyse"),
    # Gravité variable : l'importance du scénario (haute si non donnée).
    "QUA-05": ("qualite", "importance", "Scénario non satisfait",
               "Changer l'architecture pour satisfaire le scénario, ou faire accepter l'écart (accept) avec sa raison.",
               f"{ATAM} : risques"),
    "QUA-06": ("qualite", "moyenne", "Scénario attendu absent",
               "Écrire ce scénario (stimulus, environnement, réponse, mesure) et l'évaluer, ou accepter l'écart "
               "(accept) avec sa raison.",
               f"{ATAM} : scénarios de croissance et d'exploration ; règles de complétude (references/)"),
    "DEC-01": ("decisions", "moyenne", "Aucune décision d'architecture documentée",
               "Documenter les décisions structurantes (ADR).", "arc42 §9 ; ADR (M. Nygard)"),
    "DEC-02": ("decisions", "basse", "Décision encore proposée",
               "Faire accepter la décision ou la remplacer.", "arc42 §9 ; ADR (M. Nygard)"),
    "DEC-03": ("decisions", "basse", "Compromis sans décision qui l'assume",
               "Rattacher le compromis à sa décision (decision).", f"{ATAM} : compromis ; arc42 §9"),
    "RSK-01": ("risques", "haute", "Risque haut sans mesure d'atténuation",
               "Donner la mesure d'atténuation (mitigation) ou changer l'architecture.", f"arc42 §11 ; {ATAM}"),
    "RSK-02": ("risques", "basse", "Risque sans responsable", "Nommer le responsable (owner).", "arc42 §11"),
    "DOM-01": ("domaines", "moyenne", "Base de données partagée entre contextes bornés",
               "Un schéma ou une base par contexte ; les autres contextes passent par l'API ou les événements du "
               "propriétaire.", "DDD (E. Evans) : contexte borné ; Database per service (microservices.io)"),
    "DOM-02": ("domaines", "moyenne", "Flux entre contextes absent de la carte des contextes",
               "Déclarer la relation dans la carte (amont, aval, motif) ou retirer le flux.",
               "DDD (E. Evans) : carte des contextes"),
    "DOM-03": ("domaines", "moyenne", "Appel synchrone de l'amont vers l'aval",
               "L'amont publie un événement que l'aval consomme, ou la relation de la carte est inversée.",
               "DDD (E. Evans) : relation client-fournisseur ; principe des dépendances stables (R. C. Martin)"),
    "DOM-04": ("domaines", "moyenne", "Cycle de dépendances synchrones entre contextes",
               "Un des contextes devient amont : l'autre sens passe en événements, ou les contextes fusionnent.",
               "DDD (V. Vernon) : carte des contextes ; principe des dépendances acycliques"),
    "DOM-05": ("domaines", "basse", "Composant applicatif sans contexte borné",
               "Dire quel contexte le composant porte (contexts), ou le retirer.", "DDD (E. Evans) : contexte borné"),
    "DOM-06": ("domaines", "moyenne", "Contexte borné porté par aucun composant",
               "Rattacher le contexte à un composant (module du monolithe ou service), ou le retirer du découpage.",
               "DDD (E. Evans) : contexte borné"),
    "DOM-07": ("domaines", "basse", "Contexte éclaté en nombreux services",
               "Regrouper les services du contexte : un contexte, un service, sauf besoin propre justifié.",
               "Building Microservices (S. Newman) : taille d'un service"),
    "DOM-08": ("domaines", "moyenne", "Composant qui appelle de manière synchrone de nombreux contextes",
               "Réduire le couplage temporel : événements, données répliquées, ou revoir les frontières.",
               "Building Microservices (S. Newman) : couplage temporel"),
    "DOM-09": ("domaines", "moyenne", "Découpage en services que la grille de style ne justifie pas",
               "Garder le contexte dans le monolithe modulaire, ou noter le style retenu et sa raison (decision de "
               "domain-design).", "Monolith First (M. Fowler) ; grille de domain-design"),
    # Gravité variable : celle du principe (references.principes de la mission).
    "PRI-01": ("principes", "gravité du principe", "Principe d'architecture du client non respecté",
               "Respecter le principe, ou faire accepter l'écart (accept) avec la raison du client.",
               "principes d'architecture du client (references.principes de mission.json)"),
    # Gravité variable : celle du risque.
    "RSK-03": ("risques", "gravité du risque", "Risque ouvert",
               "Traiter le risque (changer l'architecture) ou le faire accepter (accept) avec sa raison.",
               f"arc42 §11 ; {ATAM}"),
}


# Ce que la description ne montre pas : à vérifier avec l'équipe.
OFF_DESCRIPTION = {
    "Sécurité applicative": "authentification et droits par rôle, validation des entrées, dépendances vulnérables "
                            "(OWASP ASVS)",
    "Données": "propriétaire de chaque donnée, rétention et purge, données personnelles (RGPD)",
    "Exploitation": "journaux corrélés, métriques et alertes, procédures de reprise testées",
    "Performance": "tests de charge sur les scénarios de performance retenus",
    "Évolution": "versionnement des API et des événements, compatibilité ascendante",
    "Organisation": "équipes et frontières des composants (loi de Conway), compétences à acquérir",
}


def plain(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if not unicodedata.combining(c)).lower()


def count_of(comp: dict) -> int:
    """Nombre d'instances d'un composant : count (2, « 2-10 » : le minimum), 1 par défaut."""
    found = re.match(r"\s*(\d+)", str(comp.get("count", 1)))
    return int(found.group(1)) if found else 1
