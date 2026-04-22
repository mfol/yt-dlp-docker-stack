FROM python:3.12-slim

RUN apt update && \
    apt install -y --no-install-recommends ffmpeg curl nodejs ca-certificates && \
    pip install --no-cache-dir --upgrade flask yt-dlp && \
    apt clean && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY app.py .

ENV DOWNLOAD_DIR=/downloads

EXPOSE 5000
CMD ["python", "app.py"]
