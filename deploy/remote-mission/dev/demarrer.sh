#!/bin/sh
# Démarrage du service en dev local (mode local : les conversations sont traitées dans ce conteneur,
# sans Kubernetes) : mission de démonstration créée au premier lancement, skills et agents copiés
# pour OpenCode dans le HOME, puis service HTTP.
set -e
if [ ! -d /work/missions/demo/.git ]; then
  uv run --quiet /opt/myskills/skills/mission-workspace/scripts/mission.py init /work/missions/demo \
    --nature avant-vente --name "Démo" > /dev/null
  echo "mission de démonstration créée : /work/missions/demo"
fi
uv run --quiet /opt/myskills/scripts/install.py sync --source /opt/myskills --global --tools opencode \
  --models /etc/myskills/models.json > /dev/null
exec uv run --quiet /opt/myskills/deploy/remote-mission/service/scripts/remote_server.py serve \
  --config /etc/myskills/remote.json
