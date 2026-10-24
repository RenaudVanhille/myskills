---
name: markdown-to-pptx
description: "Transforme un document Markdown (notes, proposition, rapport, dossier d'architecture, compte rendu) en présentation PowerPoint .pptx modifiable, sur le gabarit .potx de la marque. Choisit seul le visuel de chaque section (processus, cycle, frise, organigramme, cartes, chiffres clés, comparaison, entonnoir, Gantt, matrice de maturité, carte d'Europe), des tableaux et graphiques natifs, écrit les notes de l'orateur et les textes alternatifs. À utiliser pour livrer une présentation à partir de Markdown."
---

# markdown-to-pptx

Les chemins `scripts/...`, `references/...` et `assets/...` sont relatifs au
dossier de ce skill. Le moteur `scripts/md2pptx/` est repris du skill
`markdown-to-pptx` (md2pptx 0.5.1) de Reno, projet `powerpoint-skill`, sans
sa bibliothèque de marque (pictogrammes et schémas de marque, privés) : les
diagrammes sont dessinés en formes natives.

## Contrat

Résumé de [`contract.json`](contract.json), qui fait foi (champs des rapports en JSON Schema).

- **Entrées** : Un document Markdown (titre #, sections ##, listes, tableaux, images relatives au .md), éventuellement annoté de consignes <!-- slide: cycle --> ; Un gabarit .potx de la marque (facultatif) : --template, MD2PPTX_TEMPLATE ou un dossier .md2pptx/ du projet ; sinon le gabarit neutre fourni.
- **Sorties** : <nom>.pptx modifiable : diagrammes en formes PowerPoint natives (processus, cycle, frise, cartes, chiffres clés, comparaison, entonnoir, Gantt...), tableaux et graphiques natifs, notes de l'orateur, textes alternatifs ; Avec --plan : le plan des diapositives en JSON (type de chaque diapositive, objet du document, langue).
- **`pptx_build.py`** : Construit la présentation avec le moteur md2pptx (visuel choisi pour chaque section, gabarit appliqué), puis rouvre le .pptx pour vérifier le nombre de diapositives, les diapositives vides et les textes alternatifs. Rapport JSON, codes de sortie : 0 présentation écrite et vérifiée ; 1 Markdown ou gabarit introuvable, document illisible, rendu impossible ou fichier produit incohérent ; aucun .pptx laissé.
- **Passe la main** au skill `diagram-export` : exporter en PNG un schéma draw.io, Mermaid ou Excalidraw avant de le citer comme image dans le Markdown.
- **Passe la main** à l'utilisateur : relire la présentation et la diffuser.

## 1. Construire

```bash
uv run scripts/pptx_build.py DOC.md --out DOC.pptx [--template MARQUE.potx] [--plan plan.json]
```

Le gabarit est choisi dans cet ordre : `--template`, la variable
`MD2PPTX_TEMPLATE`, un dossier `.md2pptx/` contenant un seul `.potx` (à côté
du Markdown ou dans un dossier parent), sinon le gabarit neutre
`assets/templates/default.potx`. Couleurs, polices et dispositions viennent
du gabarit ; ne les fixez jamais dans le Markdown.

Le rapport donne le gabarit retenu (`template_source`), l'objet et la langue
détectés, le nombre de diapositives par type (`kinds`) et les objets sans
texte alternatif (`missing_alt`). Ne rouvrez pas le `.pptx` : le script l'a
déjà vérifié.

Les commandes d'origine de md2pptx que citent les références (diagnostic,
dispositions du gabarit, plan modifié à la main) passent par
`uv run scripts/pptx_build.py --md2pptx --check | --list-layouts -t MARQUE.potx | PLAN.json --from-plan -o DOC.pptx` ;
leur sortie est du texte, sans rapport JSON.

## 2. Écrire ou ajuster le Markdown

Le moteur déduit le visuel de la forme du texte : liste ordonnée courte →
processus, éléments datés (`T2 2027 :`) → frise, `**Libellé** : texte` →
cartes, `**38 %** de ...` → chiffres clés, tableau à colonne temporelle et
nombres → graphique natif. Pour imposer un visuel, une consigne seule sur la
ligne sous le titre de la section :

```markdown
## Notre démarche
<!-- slide: cycle -->
```

Types : `process`, `cycle`, `timeline`, `hierarchy`, `cards`, `stats`,
`pyramid`, `comparison`, `funnel`, `hub`, `rings`, `gantt`, `matrix`, `map`,
`stairs`, `flow`, `chart`, `table`, `bullets`, `text`. Notes de l'orateur :
`<!-- notes: ce qu'il faut dire -->`. Une ligne `---` dans une section ouvre
une nouvelle diapositive.

Ne lisez les références que si le besoin se présente :

| Besoin | Lire |
| --- | --- |
| Règles à donner à l'agent qui écrit le Markdown | `references/authoring-guide.md` (à transmettre tel quel) |
| Correspondance Markdown → diapositives, toutes les consignes | `references/markdown-guide.md` |
| Gabarit de marque, rôles des dispositions | `references/templates.md` |
| Plan JSON des diapositives | `references/plan-format.md` |
| Erreurs | `references/troubleshooting.md` |

## 3. Schémas et images

Une image s'écrit `![Ce que montre l'image](images/x.png)` (chemin relatif au
Markdown) ; son texte devient le texte alternatif. Un schéma draw.io,
Mermaid ou Excalidraw s'exporte d'abord en PNG avec `diagram-export`.

## 4. Après la construction

Donnez le chemin du `.pptx`, l'objet détecté, les types de diapositives et
les avertissements. Un objet sans texte alternatif se corrige dans le
Markdown (texte de l'image), puis on reconstruit.
