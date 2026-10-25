---
name: well-architected-review
description: "Contrôle une architecture cloud décrite en JSON contre l'AWS Well-Architected Framework, l'Azure Well-Architected Framework et le Google Cloud Well-Architected Framework (fiabilité, sécurité, opérations, performances, coûts, durabilité) et contre les conventions de schéma des fournisseurs. À utiliser dès la définition d'une architecture (piliers) puis sur le schéma (conventions)."
---

# well-architected-review

Les chemins `scripts/...` sont relatifs au dossier de ce skill. L'entrée est
la description JSON de `cloud_build.py` (skill `cloud-architecture`, qui
doit être installé à côté) : `--schema` l'affiche.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Description JSON de l'architecture, celle de cloud_build.py (skill cloud-architecture) ; à la définition, la description cloud d'une option (schemas/option-<id>.cloud.json d'architecture-options) ; Facultatif : accept, les écarts acceptés avec leur raison.
- **Sorties** : <sujet>.wa.md : synthèse par pilier, constats (règle, pilier, gravité, élément, correction, référence du cadre), points hors du schéma.
- **`wa_check.py`** : Contrôle la même description contre l'AWS Well-Architected Framework, l'Azure Well-Architected Framework et le Google Cloud Well-Architected Framework (fiabilité, sécurité, excellence opérationnelle, performances, coûts, durabilité) et contre les conventions de schéma des fournisseurs (imbrication région, VPC/VNet, zone, sous-réseau ; icônes officielles) : un constat par règle enfreinte, avec pilier, gravité, élément, correction et référence du cadre ; écrit <sujet>.wa.md. Rapport JSON, codes de sortie : 0 revue écrite, aucun constat non accepté au seuil --fail-on ; 1 description illisible, erreur, ou constat non accepté au seuil --fail-on ; le rapport et <sujet>.wa.md sont tout de même produits sauf erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **Dépend de** `cloud-architecture` (`cloud_build.py`, obligatoire) : lire la description comme le schéma : types de services, groupes, frontières et numéros de flux F1, F2....
- **Vault Obsidian** : écrit les notes de type `revue-well-architected`, `constat` ; lit les notes typées, selon l'ontologie `shared/vault-ontology.json` (frontmatter vérifié par `scripts/lib/vault_ontology.py`).
- **Passe la main** au skill `cloud-architecture` : corriger la description puis reconstruire le schéma.
- **Passe la main** au skill `threat-model` : préparer aussi le modèle de menaces STRIDE.
- **Passe la main** à l'utilisateur : un écart est voulu : sa raison va dans accept.

## 1. Lancer la revue

```bash
uv run scripts/wa_check.py SUJET.json [--scope piliers|conventions] [--fail-on moyenne]
```

Dans un workflow avec un vault Obsidian, ajoutez `--vault VAULT --folder
DOSSIER [--option ID]` : une note `revue-well-architected` et une note
`constat` par constat rejoignent la mémoire partagée.

Le contrôle des piliers sert dès la définition de l'architecture : lancez
`--scope piliers` sur la description d'une option (celle qu'écrit
`architecture-options`, sans groupes réseau) pour comparer les options et
compléter celle qui sera retenue avant tout schéma. Au dessin,
`--scope conventions` contrôle le schéma ; sans `--scope`, tout est contrôlé.

Le script contrôle la description contre l'AWS Well-Architected Framework,
l'Azure Well-Architected Framework et le Google Cloud Well-Architected
Framework, selon les services présents, puis contre les conventions de
schéma des fournisseurs. `--rules` liste les 20 règles :

| Pilier | Contrôles |
| --- | --- |
| Fiabilité | calcul ou base sur une seule zone de disponibilité, instance unique, base sans réplique ni sauvegarde, une NAT pour plusieurs zones |
| Sécurité | stockage en sous-réseau public ou atteint de l'extérieur, calcul exposé sans équilibreur, flux non chiffré à travers une frontière, entrée publique sans WAF, pas de coffre à secrets, pas d'audit |
| Excellence opérationnelle | pas de supervision (CloudWatch, Azure Monitor, Cloud Monitoring) |
| Performances | utilisateurs servis sans CDN |
| Coûts et durabilité | capacité fixe sans autoscaling |
| Conventions de schéma | ordre des groupes (Cloud > région > VPC > zone > sous-réseau chez AWS ; région > VNet > sous-réseau chez Azure ; projet > VPC > région > sous-réseau chez Google), groupe hors de son conteneur, instance posée dans le VPC hors sous-réseau, service régional dessiné dans un sous-réseau, fournisseurs mélangés, icône générique au lieu de l'icône officielle |

Chaque constat donne la règle, le pilier, la gravité (haute, moyenne,
basse), l'élément (identifiant ou flux F1, F2...), la correction et la
référence du cadre (question AWS `REL10`, recommandation Azure `RE:05`...).
`SUJET.wa.md` reprend la synthèse par pilier, les constats, puis ce qui ne
se vérifie pas sur un schéma (IAM, chiffrement au repos, tests de reprise,
étiquetage des coûts...).

Corrigez la description et relancez. Un écart voulu s'accepte dans la
description, avec sa raison ; il reste dans la revue mais ne compte plus :

```json
"accept": {"SEC-07": "CloudTrail géré par le compte de sécurité", "REL-02@bastion": "bastion jetable"}
```

Code de sortie 1 dès un constat non accepté de gravité `--fail-on` ou plus
(défaut `haute`, `aucune` pour ne jamais échouer) : c'est la porte de
revue d'un workflow. Ce contrôle ne remplace pas une revue avec l'outil
Well-Architected du fournisseur ; il garantit que le schéma ne montre pas
d'écart évident.
