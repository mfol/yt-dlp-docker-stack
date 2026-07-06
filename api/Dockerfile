# Imagem base — default publico. Build interno (Gitea) passa --build-arg BASE_IMAGE=<cache Nexus>.
ARG BASE_IMAGE=python:3.12-slim
FROM ${BASE_IMAGE}

# Registries — defaults PUBLICOS (funciona pra qualquer um). O build interno
# sobrescreve via --build-arg: APT_MIRROR e PIP_INDEX_URL apontando pro Nexus.
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG APT_MIRROR=

# APT: se APT_MIRROR for setado (build interno), troca as sources pra ele;
# vazio (default publico) = usa o mirror padrao da imagem base.
RUN if [ -n "$APT_MIRROR" ]; then \
      rm -f /etc/apt/sources.list.d/debian.sources && \
      printf 'deb %s/debian-bookworm/ bookworm main\ndeb %s/debian-bookworm-updates/ bookworm-updates main\ndeb %s/debian-bookworm-security/ bookworm-security main\n' \
        "$APT_MIRROR" "$APT_MIRROR" "$APT_MIRROR" > /etc/apt/sources.list ; \
    fi && \
    apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl nodejs ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# PIP (default pypi.org; build interno passa o pypi-proxy do Nexus)
ENV PIP_INDEX_URL=${PIP_INDEX_URL}
RUN pip install --no-cache-dir --upgrade flask yt-dlp

WORKDIR /app
# build context = raiz do repo (docker build -f api/Dockerfile .)
COPY api/app.py .
COPY frontend/ ./frontend/

ENV DOWNLOAD_DIR=/downloads \
    COOKIES_DIR=/cookies \
    FRONTEND_DIR=/app/frontend \
    MAX_WORKERS=2

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:5000/healthz || exit 1

CMD ["python", "app.py"]
