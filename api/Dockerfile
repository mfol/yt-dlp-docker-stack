FROM python:3.12-slim

RUN apt update && \
    apt install -y --no-install-recommends ffmpeg curl nodejs ca-certificates && \
    pip install --no-cache-dir --upgrade flask yt-dlp && \
    apt clean && rm -rf /var/lib/apt/lists/*

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
