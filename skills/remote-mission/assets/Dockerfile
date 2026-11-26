# Image du service des missions à distance (skill remote-mission).
# Construite en local ou par la CI GitLab ; les outils sont téléchargés à la construction,
# jamais pendant un tour. Contexte de construction : la racine du dépôt myskills.
FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates curl nodejs npm \
    && rm -rf /var/lib/apt/lists/* \
    && npm install -g @anthropic-ai/claude-code \
    && curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

RUN useradd --create-home --uid 10001 myskills
COPY --chown=myskills . /opt/myskills
USER myskills
WORKDIR /home/myskills
# Skills et agents de myskills pour Claude Code (~/.claude), sans réseau au lancement.
RUN uv run /opt/myskills/scripts/install.py sync --source /opt/myskills --tools claude

EXPOSE 8765
ENTRYPOINT ["uv", "run", "/opt/myskills/skills/remote-mission/scripts/remote_server.py", "serve", \
            "--config", "/etc/myskills/remote.json"]
