# Image des missions à distance (skill remote-mission) : service frontal et pods de session.
# Elle contient tout ce que les skills de myskills utilisent, pour qu'une session travaille
# hors ligne : rien n'est téléchargé pendant un message (modèles, paquets npm, navigateur,
# environnements Python préparés ici). Contexte de construction : la racine du dépôt myskills.
#
#   docker build -f skills/remote-mission/assets/Dockerfile -t registry.exemple.local/myskills/remote-mission:X.Y.Z .
#
# Arguments : versions épinglées (à relire à chaque mise à jour) et skill externe markdown-to-pptx
# (dépôt git du plugin powerpoint-skill, facultatif : sans lui, l'export PowerPoint est signalé absent).
FROM node:22-bookworm-slim

ARG DRAWIO_VERSION=26.0.9
ARG CLAUDE_CODE_VERSION=latest
ARG LIKEC4_VERSION=latest
ARG MD2PPTX_REPO=""
ARG MD2PPTX_REF=main

# Caches hors du HOME (le HOME d'une session est sur son volume) : partagés, en lecture seule à l'usage.
ENV UV_PYTHON_INSTALL_DIR=/opt/uv/python \
    UV_CACHE_DIR=/opt/uv/cache \
    UV_TOOL_DIR=/opt/uv/tools \
    UV_TOOL_BIN_DIR=/usr/local/bin \
    UV_LINK_MODE=copy \
    XDG_CACHE_HOME=/opt/myskills-cache \
    PLAYWRIGHT_BROWSERS_PATH=/opt/pw-browsers \
    MYSKILLS_NO_SANDBOX=1 \
    LANG=C.UTF-8

# Outils système : git, OCR (Tesseract fr/en), LibreOffice sans interface (PDF, relecture des
# .docx), écran virtuel pour draw.io (xvfb), polices des rendus, bibliothèques d'Electron.
RUN apt-get update && apt-get install -y --no-install-recommends \
        git ca-certificates curl xvfb xauth \
        tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng \
        libreoffice-writer-nogui libreoffice-impress-nogui libreoffice-calc-nogui \
        fonts-dejavu fonts-liberation fonts-noto-core fonts-noto-color-emoji \
        libgtk-3-0 libnotify4 libnss3 libxss1 libxtst6 libatspi2.0-0 libsecret-1-0 libgbm1 libasound2 \
    && curl -fsSL -o /tmp/drawio.deb \
        "https://github.com/jgraph/drawio-desktop/releases/download/v${DRAWIO_VERSION}/drawio-amd64-${DRAWIO_VERSION}.deb" \
    && apt-get install -y --no-install-recommends /tmp/drawio.deb \
    && rm -rf /tmp/drawio.deb /var/lib/apt/lists/*

# uv, Python, Claude Code, LikeC4, graphify (skill externe de revue), dépendances de Chromium.
RUN curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh \
    && uv python install 3.12 \
    && npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}" "likec4@${LIKEC4_VERSION}" \
    && uv tool install graphifyy \
    && uvx playwright install-deps chromium \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 10001 myskills \
    && mkdir -p /opt/uv/cache /opt/myskills-cache /opt/pw-browsers /opt/md2pptx \
    && chown -R myskills /opt/uv /opt/myskills-cache /opt/pw-browsers /opt/md2pptx
COPY --chown=myskills . /opt/myskills
USER myskills
WORKDIR /home/myskills

# Skill externe markdown-to-pptx (facultatif) : trouvé par MD2PPTX_SKILL.
RUN if [ -n "$MD2PPTX_REPO" ]; then git clone --depth 1 --branch "$MD2PPTX_REF" "$MD2PPTX_REPO" /opt/md2pptx; fi
ENV MD2PPTX_SKILL=/opt/md2pptx

# Préchargement : paquets JavaScript des rendus et modèles locaux (Docling, Whisper) depuis leurs
# sources épinglées, empreintes vérifiées ; navigateur de Playwright ; environnements uv de chaque
# script (dépendances PEP 723) ; skills et agents pour Claude Code. Puis état des outils (informatif).
RUN uv run /opt/myskills/skills/check-prerequisites/scripts/doctor.py tout --prefetch \
    && uvx playwright install chromium \
    && for script in /opt/myskills/skills/*/scripts/*.py; do \
           uv sync --quiet --script "$script"; \
       done \
    && uv run /opt/myskills/scripts/install.py sync --source /opt/myskills --tools claude \
    && (uv run /opt/myskills/skills/check-prerequisites/scripts/doctor.py tout || true)

# À l'usage : rien ne se télécharge (uv, rendus, modèles).
ENV UV_OFFLINE=1 \
    MYSKILLS_OFFLINE=1 \
    HF_HUB_OFFLINE=1

EXPOSE 8765
ENTRYPOINT ["uv", "run", "/opt/myskills/skills/remote-mission/scripts/remote_server.py", "serve", \
            "--config", "/etc/myskills/remote.json"]
