# Brouillon du chiffrage (`--draft`)

```bash
uv run scripts/estimate_build.py chiffrage.json --draft [--option ID] [--infra couts.infra.json] [--lots decoupage.lots.json --lots decoupage-back.lots.json]
```

Il écrit `chiffrage.json` (jamais par-dessus un fichier existant) :

- un lot par composant à construire ou à intégrer, et les lots transverses
  (cadrage, recette, tests de sécurité, mise en production, formation) ;
- pilotage, provision et run aux valeurs usuelles (listées dans `_draft`) ;
- le budget tiré des exigences de coût ;
- les lignes d'infrastructure de `cost_build.py --infra` (skill `cloud-cost`) ;
- avec `--lots` (répétable, alias `--frontend`), les lots des experts à la
  place du lot global de chaque composant qu'ils couvrent : frontend
  (`ui_breakdown.py`, skill `mockup-to-html` : composants, motifs, écrans)
  et backend (`api_breakdown.py`, skill `api-contract`), charges d'abaque
  et réemploi à relire.

Quand ces lots d'experts chiffrent toute la réalisation et l'intégration,
les lots transverses reçoivent une charge par ratio de ces jours (`ratio` et
`profile` des règles de `references/postes-attendus.json`, raison dans
`note`) : à relire, pas à estimer. Un poste déjà couvert par un lot
d'expert (plan de recette) n'est pas ajouté.

Complétez ensuite : `effort` de chaque lot (vide), `rates`, hypothèses et
exclusions. Ajoutez, découpez ou retirez un lot, et revoyez les valeurs
usuelles, seulement quand vous avez une raison.

## Exemple de description complétée

```json
{
  "title": "Chiffrage du portail de sinistres",
  "rates": {"chef-de-projet": 850, "architecte": 950, "developpeur": 650},
  "work": [
    {"id": "L1", "name": "API des déclarations", "phase": "realisation", "component": "api",
     "refs": ["EF-001", "EF-002"], "effort": {"developpeur": [25, 35, 55], "architecte": 3}}
  ],
  "overheads": [{"id": "P1", "name": "Pilotage", "percent": 12, "profile": "chef-de-projet"}],
  "contingency": 10,
  "infra": [
    {"id": "I1", "name": "Conteneurs managés, 2 zones", "component": "api", "environment": "production",
     "kind": "cloud", "quantity": 4, "unit_cost": 70, "period": "mois",
     "basis": "hypothèse : 4 tâches 1 vCPU 2 Go, grille publique 2026"}
  ],
  "run": [{"id": "R1", "name": "Maintenance corrective et évolutive", "percent_of_build": 15}],
  "budget": {"monthly": 8000, "refs": ["ENF-005"]},
  "assumptions": ["L'outil de gestion expose une API de création de dossier."]
}
```
