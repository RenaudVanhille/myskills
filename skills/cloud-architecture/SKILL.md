---
name: cloud-architecture
description: "Dessine des schémas d'architecture cloud en draw.io avec les icônes officielles AWS, Azure, GCP et Kubernetes : déploiement (régions, VPC, sous-réseaux), réseau et flux (matrice des flux), cluster Kubernetes, haute disponibilité et PRA (RPO, RTO), pipeline data ou CI/CD GitOps. Prépare aussi le modèle de menaces STRIDE et contrôle le respect des cadres Well-Architected d'AWS, Azure et Google Cloud et des conventions de schéma des fournisseurs. À utiliser pour un architecte solution, à partir d'une description ou de code d'infrastructure."
---

# cloud-architecture

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décrivez les groupes, les services et les flux ; le script fait la mise en
page avec les icônes officielles livrées dans draw.io (rien n'est
téléchargé). N'écrivez pas le XML draw.io à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Décision de diagram-brief : public et destination ; Description JSON de l'architecture : title, provider, view, items (groupes imbriqués et services typés), flows, objectives ; ou du code d'infrastructure (Terraform, docker-compose, manifestes Kubernetes) que iac_import.py traduit en description.
- **Sorties** : <sujet>.drawio en XML clair, avec les icônes officielles AWS, Azure, GCP ou Kubernetes, à côté de sa description <sujet>.json ; Vue network (ou --matrix) : <sujet>.flows.md, la matrice des flux ; Avec stride.py : <sujet>.threats.md, le modèle de menaces STRIDE à compléter ; Avec wa_check.py : <sujet>.wa.md, la revue Well-Architected du schéma (constats par pilier, conventions du fournisseur, points hors du schéma) ; Après export : <sujet>.drawio.png (une image par page), .svg ou .pdf.
- **`cloud_build.py`** : Construit le schéma draw.io (mise en page des groupes imbriqués, icônes officielles livrées dans draw.io, flux, titre, RPO/RTO, légende), puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON, codes de sortie : 0 schéma produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`stride.py`** : Prépare le modèle de menaces STRIDE à partir de la même description : frontières de confiance, flux qui les traversent, une menace type par catégorie applicable, avec mesure type et statut à compléter. Rapport JSON, codes de sortie : 0 modèle produit sans erreur ; 1 description illisible ou erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`wa_check.py`** : Contrôle la même description contre l'AWS Well-Architected Framework, l'Azure Well-Architected Framework et le Google Cloud Well-Architected Framework (fiabilité, sécurité, excellence opérationnelle, performances, coûts, durabilité) et contre les conventions de schéma des fournisseurs (imbrication région, VPC/VNet, zone, sous-réseau ; icônes officielles) : un constat par règle enfreinte, avec pilier, gravité, élément, correction et référence du cadre ; écrit <sujet>.wa.md. Rapport JSON, codes de sortie : 0 revue écrite, aucun constat non accepté au seuil --fail-on ; 1 description illisible, erreur, ou constat non accepté au seuil --fail-on ; le rapport et <sujet>.wa.md sont tout de même produits sauf erreur.
  Description JSON validée avant tout traitement : clé inconnue, type ou valeur hors liste donnent une erreur avec son chemin ; `--schema` affiche le JSON Schema.
- **`iac_import.py`** : Écrit la description de cloud_build.py depuis le code d'infrastructure : ressources Terraform (AWS, Azure, Google), services docker-compose et manifestes Kubernetes deviennent services typés, réseaux et namespaces des groupes, références et dépendances des flux ; la description est validée contre le schéma d'entrée de cloud_build.py et construite à blanc avant d'être écrite. Rapport JSON, codes de sortie : 0 description écrite, conforme et construite sans erreur ; 1 source introuvable ou format non reconnu, aucune ressource reconnue, ressource en double, ou description produite rejetée par cloud_build.py ; rien n'est écrit.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main.
- **Passe la main** au skill `mermaid-diagram` : diagramme de séquence des appels entre services pour un parcours.

## 1. Choisir la vue

| Vue (`view`) | Pour montrer | Groupes typiques |
| --- | --- | --- |
| `deployment` (défaut) | où tournent les services | région, VPC/VNet, zone, sous-réseau |
| `network` | flux réseau et sécurité : numéros F1, F2... sur le schéma, protocole et port dans la matrice `<sujet>.flows.md` | VPC, sous-réseaux, security groups |
| `kubernetes` | le chemin d'une requête jusqu'aux pods | cluster, namespace, node |
| `dr` | haute disponibilité et reprise : régions active et passive, réplications, RPO et RTO | région avec `state` |
| `pipeline` | data (ingestion, transformation, stockage) ou CI/CD GitOps, de gauche à droite | `stage`, `env` |
| `threats` | frontières de confiance en rouge, flux numérotés comme dans le modèle STRIDE | frontières |

Une seule description peut servir plusieurs vues : `--view` remplace celle
du fichier. Pour une séquence d'appels entre services, utilisez
`mermaid-diagram` (modèle « Séquence cloud »).

## 2. Décrire l'architecture

Fichier `<sujet>.json` :

```json
{
  "title": "Boutique : déploiement AWS",
  "provider": "aws",
  "items": [
    {"id": "clients", "type": "users", "label": "Clients"},
    {"type": "region", "label": "eu-west-3", "items": [
      {"type": "vpc", "label": "VPC prod", "items": [
        {"type": "public-subnet", "label": "Public", "items": [{"id": "alb", "type": "alb"}]},
        {"type": "private-subnet", "label": "Privé", "layout": "column", "items": [
          {"id": "api", "type": "ecs", "label": "API commandes", "count": 3},
          {"id": "db", "type": "aurora"}]}]}]}
  ],
  "flows": [
    {"from": "clients", "to": "alb", "protocol": "HTTPS", "port": 443},
    {"from": "alb", "to": "api"},
    {"from": "api", "to": "db", "port": 5432, "encrypted": true}
  ]
}
```

- **Service** : `type` sans préfixe pris chez `provider` (`lambda`), ou
  préfixé (`azure:aks`, `gcp:bigquery`, `k8s:pod`), ou générique (`user`,
  `internet`, `service`, `server`, `db`, `queue`, `repo`, `external`,
  `note`). `label` remplace le nom par défaut, `count` ajoute « ×3 ».
  Liste complète : `uv run scripts/cloud_build.py --types aws` (ou
  `azure`, `gcp`, `k8s`, `generic`). Un type inconnu donne une erreur avec
  les types proches.
- **Groupe** : tout élément qui a des `items`. Types : `cloud`, `account`,
  `region`, `vpc`, `az`, `public-subnet`, `private-subnet`,
  `security-group`, `asg` (AWS) ; `subscription`, `resource-group`,
  `region`, `vnet`, `subnet`, `zone` (Azure) ; `project`, `region`,
  `zone`, `vpc`, `subnet` (GCP) ; `cluster`, `namespace`, `node` (`k8s:`) ;
  génériques `zone`, `onprem`, `internet`, `stage`, `env`, `boundary`.
- **Disposition** : les enfants d'un groupe sont en ligne (`"layout":
  "column"` pour les empiler, `"wrap": 3` pour une grille). Régions et
  zones de disponibilité s'empilent par défaut. Rangez les services dans
  l'ordre des flux : le script aligne un service sur ceux qu'il appelle et
  fait passer sous les autres une flèche qui en traverserait un.
- **Flux** : `from`, `to` (identifiants de services ou de groupes),
  `label` (un verbe), `protocol`, `port`, `style` (`sync` par défaut,
  `async`, `replication`), `both: true` pour une double flèche,
  `encrypted` pour le modèle de menaces. `"chain": true` sur un groupe (ou
  à la racine) relie ses éléments dans l'ordre.
- **PRA** : `"state": "active"` ou `"passive"` sur les régions, flux
  `replication`, et `"objectives": {"rpo": "15 min", "rto": "1 h"}`.
- **Plusieurs vues** : `"pages": [{"name", "view", "items", "flows"}, ...]`.

Si l'architecture existe en code (Terraform AWS, Azure ou Google,
docker-compose, manifestes Kubernetes), ne le lisez pas : le script écrit la
description, que vous complétez ensuite (titre, acteurs externes, protocoles,
flux que le code ne montre pas) :

```bash
uv run scripts/iac_import.py infra/ k8s/ --out boutique.json --title "Boutique"
```

Le rapport compte services, groupes et flux ; `ignored` et `warnings`
nomment ce qui n'a pas d'équivalent (rôles IAM, règles...). Le sens d'un flux
tiré d'une référence est « utilise » ; vérifiez-le. Un gabarit Helm se rend
d'abord (`helm template`). Pour Bicep ou CloudFormation, écrivez la
description à la main à partir des ressources et de leurs liens.

## 3. Construire

```bash
uv run scripts/cloud_build.py SUJET.json [--view network] [--matrix]
```

Rapport : nombre de groupes, services et flux, erreurs (type inconnu, flux
vers un identifiant inconnu) et avertissements (trop de services pour le
public, vue PRA sans RPO/RTO ni réplication, et ceux de `check_drawio.py`).
Corrigez la description jusqu'à zéro erreur et zéro avertissement.

Public non technique : 12 services au plus, des libellés en mots simples
(« paiement » plutôt que « ECS »), une vue par sujet.

## 4. Modèle de menaces STRIDE

```bash
uv run scripts/stride.py SUJET.json
uv run scripts/cloud_build.py SUJET.json --view threats --out SUJET-menaces.drawio
```

Les comptes, VPC, sous-réseaux, security groups, clusters, namespaces,
`onprem`, `internet` et `boundary` sont des frontières de confiance
(`"boundary": false` ou `true` pour forcer) ; une entité externe (`user`,
`external`...) est hors frontière. `stride.py` écrit `SUJET.threats.md` :
frontières, flux qui les traversent (en tête, avec chiffrement déclaré ou
non), puis une menace type par catégorie STRIDE applicable à chaque
élément, avec une mesure type et les colonnes « Mesure retenue » et
« Statut » à compléter. Relisez le tableau : gardez les menaces
pertinentes, précisez-les pour le contexte, complétez les mesures. Les
numéros F1, F2... sont les mêmes que sur le schéma `threats`.

## 5. Revue Well-Architected

```bash
uv run scripts/wa_check.py SUJET.json [--scope piliers|conventions] [--fail-on moyenne]
```

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

## 6. Exporter et relire

```bash
uv run ../diagram-export/scripts/export.py SUJET.drawio --format png
```

Ouvrez l'image : flèche qui traverse une icône ou un libellé, libellés qui
se chevauchent, groupe trop large. Changez l'ordre des services, `layout`
ou `wrap`, ou découpez en pages, puis reconstruisez. Si quelqu'un a retouché
le `.drawio` à la main, c'est lui qui fait foi : modifiez-le avec
`drawio-diagram`.

Pour Confluence, livrez le `.drawio` (macro draw.io) et le `.drawio.png`
(à insérer dans la page), plus la matrice des flux ou le modèle de menaces
s'ils ont été produits. Gardez la description `.json` pour faire évoluer le
schéma.

draw.io Desktop est requis pour l'export (voir `check-prerequisites`).
