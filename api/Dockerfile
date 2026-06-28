# Base via cache Docker interno (Nexus)
FROM docker-cache.packtudo.com/library/python:3.12-slim

# APT via repos Nexus (HTTPS). Remove sources padrao (deb822) pra nao vazar pro deb.debian.org.
RUN rm -f /etc/apt/sources.list.d/debian.sources && \
    printf 'deb https://pack-nexus.packtudo.com/repository/debian-bookworm/ bookworm main\n\
deb https://pack-nexus.packtudo.com/repository/debian-bookworm-updates/ bookworm-updates main\n\
deb https://pack-nexus.packtudo.com/repository/debian-bookworm-security/ bookworm-security main\n' \
        > /etc/apt/sources.list && \
    apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl nodejs ca-certificates && \
    apt-get clean && rm -rf /var/lib/apt/lists/*

# PIP via pypi-proxy Nexus (HTTPS, sem --trusted-host)
ENV PIP_INDEX_URL=https://pack-nexus.packtudo.com/repository/pypi-proxy/simple
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
