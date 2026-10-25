# Analyse d'impact relative à la protection des données : Portail de déclaration des sinistres

**AIPD requise** : 2 critère(s) du CEPD (données sensibles ou à caractère hautement personnel; traitement à grande échelle).

Traitements : 2 ; risques analysés : 4 ; risques résiduels élevés : 1 ; transferts hors EEE : 1.

Hébergement : aws, juridiction hors-ue.

## Risques pour les personnes

| Risque | Traitement | Événement redouté | Gravité | Vraisemblance | Niveau | Mesures | Résiduel |
| --- | --- | --- | --- | --- | --- | --- | --- |
| R-01 | T-01 | Accès illégitime aux données | 4 (maximale) | 3 (importante) | élevé | chiffrement en transit (M001)<br>authentification forte (ENF-003) *(prévue)* | 4 × 3 : élevé |
| R-02 | T-01 | Modification non désirée | 3 (importante) | 2 (limitée) | significatif | journal des modifications | 3 × 1 : significatif |
| R-03 | T-01 | Disparition des données | 2 (limitée) | 2 (limitée) | limité | sauvegardes chiffrées (M002) | 2 × 1 : limité |
| R-04 | T-02 | Accès illégitime aux données | 3 (importante) | 2 (limitée) | significatif | aucune | à évaluer |

## Carte des risques

Gravité en ligne, vraisemblance en colonne ; initial → résiduel.

| Gravité \ Vraisemblance | 1 | 2 | 3 | 4 |
| --- | --- | --- | --- | --- |
| 4 (maximale) |  |  | R-01, R-01' |  |
| 3 (importante) | R-02' | R-02, R-04 |  |  |
| 2 (limitée) | R-03' | R-03 |  |  |
| 1 (négligeable) |  |  |  |  |

## Sources et impacts

- **R-01** : sources attaquant externe, autorité étrangère ; impacts : divulgation de données de santé.
- **R-02** : sources non précisées ; impacts : indemnisation erronée.
- **R-03** : sources non précisées ; impacts : dossier perdu, déclaration à refaire.
- **R-04** : sources non précisées ; impacts : non précisés.

## À valider

- Avis du délégué à la protection des données et, le cas échéant, des personnes concernées.
- Plan d'action des mesures prévues, avec responsable et échéance.
- Revue de l'analyse à chaque évolution du traitement.
