---
name: cloud-architecture
description: "Dessine des schémas d'architecture cloud en draw.io avec les icônes officielles AWS, Azure, GCP et Kubernetes : déploiement (régions, VPC, sous-réseaux), réseau et flux (matrice des flux), cluster Kubernetes, haute disponibilité et PRA (RPO, RTO), pipeline data ou CI/CD GitOps. Sa description sert aussi au modèle de menaces STRIDE (threat-model) et à la revue Well-Architected (well-architected-review). À utiliser pour un architecte solution, à partir d'une description ou de code d'infrastructure."
---

# cloud-architecture

Les chemins `scripts/...` sont relatifs au dossier de ce skill. Vous
décrivez les groupes, les services et les flux ; le script fait la mise en
page avec les icônes officielles livrées dans draw.io (rien n'est
téléchargé). N'écrivez pas le XML draw.io à la main.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Niveau** : moyen (modèle standard).
- **Entrées** : Décision de diagram-brief : public et destination ; Description JSON de l'architecture : title, provider (aws, azure, gcp, k8s ou hébergeur souverain : ovh, outscale, cloud-temple, scaleway, s3ns, bleu, numspot, sur-site), qualifications, view, items (groupes imbriqués et services typés), flows, objectives ; ou du code d'infrastructure (Terraform, CloudFormation, Bicep, docker-compose, manifestes Kubernetes) que iac_import.py traduit en description.
- **Sorties** : <sujet>.drawio en XML clair, avec les icônes officielles AWS, Azure, GCP ou Kubernetes (formes génériques de la charte pour les hébergeurs souverains), à côté de sa description <sujet>.json ; Vue network (ou --matrix) : <sujet>.flows.md, la matrice des flux ; Après export : <sujet>.drawio.png (une image par page), .svg ou .pdf.
- **`cloud_build.py`** : Construit le schéma draw.io (mise en page des groupes imbriqués, icônes officielles livrées dans draw.io, flux, titre, RPO/RTO, légende), puis le vérifie avec check_drawio.py du skill drawio-diagram s'il est installé. Rapport JSON (0 succès, 1 erreur ; description validée, `--schema` affiche son JSON Schema).
- **`iac_import.py`** : Écrit la description de cloud_build.py depuis le code d'infrastructure : ressources Terraform (AWS, Azure, Google), CloudFormation (AWS, YAML ou JSON) et Bicep (Azure), services docker-compose et manifestes Kubernetes deviennent services typés, réseaux et namespaces des groupes, références et dépendances des flux ; la description est validée contre le schéma d'entrée de cloud_build.py et construite à blanc avant d'être écrite. Rapport JSON (0 succès, 1 erreur).
- **Lancement** : `uv run "<dossier du skill>/scripts/<script>" ...`, chemin complet écrit dans chaque commande, avec des `/` (une variable ou une fonction shell d'un appel précédent y est vide) ; rapport JSON lu tel quel, sans tube.
- **Dépend de** `drawio-diagram` (`check_drawio.py`, facultatif : sans lui, avertissement) : vérifier le .drawio produit.
- **Dépend de** `diagram-export` (`export.py`, facultatif : sans lui, avertissement) : --export : rendre l'image dans le même appel que la construction.
- **Passe la main** au skill `diagram-export` : exporter et relire l'image.
- **Passe la main** au skill `drawio-diagram` : retoucher le .drawio à la main.
- **Passe la main** au skill `mermaid-diagram` : diagramme de séquence des appels entre services pour un parcours.
- **Passe la main** au skill `threat-model` : modèle de menaces STRIDE de l'architecture décrite (même description JSON).
- **Passe la main** au skill `well-architected-review` : revue Well-Architected des piliers ou des conventions de schéma (même description JSON).

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
- **Hébergeur souverain** (`provider` : `ovh`, `outscale`, `cloud-temple`,
  `scaleway`, `s3ns`, `bleu`, `numspot`, `sur-site`) : pas d'icônes
  officielles, formes de la charte et vocabulaire commun : services
  `instance`, `bare-metal`, `kubernetes`, `container`, `database`,
  `postgresql`, `object-storage`, `load-balancer`, `waf`, `secrets`,
  `monitoring`, `logs`, `backup`... ; groupes `project`, `region`, `zone`,
  `network`, `subnet`. Le nom de l'hébergeur s'affiche (`ovh:network` :
  vRack). Liste : `--types ovh`. `"qualifications": ["secnumcloud"]`
  déclare ce qu'exigent les exigences ; `wa_check.py` signale un hébergeur
  qui ne l'a pas.
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
CloudFormation, Bicep, docker-compose, manifestes Kubernetes), ne le lisez pas : le script écrit la
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

## 4. Menaces et revue Well-Architected

La même description sert deux revues, chacune dans son skill :
`threat-model` (`stride.py`, modèle de menaces STRIDE, mêmes numéros de
flux F1, F2... que la vue `threats`) et `well-architected-review`
(`wa_check.py`, piliers des cadres AWS, Azure et Google Cloud et
conventions de schéma des fournisseurs). Après un dessin, lancez au moins
`wa_check.py SUJET.json --scope conventions`.

## 5. Exporter et relire

```bash
uv run ../diagram-export/scripts/export.py SUJET.drawio --format png
```

Ou en un seul appel avec la construction : `cloud_build.py SUJET.json
--export png` ; l'image est dans `export` du rapport.

N'ouvrez l'image que si `review_image` est vrai (lisibilité douteuse selon
le contrôle) : flèche qui traverse une icône ou un libellé, libellés qui
se chevauchent, groupe trop large. Changez l'ordre des services, `layout`
ou `wrap`, ou découpez en pages, puis reconstruisez. Si quelqu'un a retouché
le `.drawio` à la main, c'est lui qui fait foi : modifiez-le avec
`drawio-diagram`.

Pour Confluence, livrez le `.drawio` (macro draw.io) et le `.drawio.png`
(à insérer dans la page), plus la matrice des flux ou le modèle de menaces
s'ils ont été produits. Gardez la description `.json` pour faire évoluer le
schéma.

draw.io Desktop est requis pour l'export (voir `check-prerequisites`).
