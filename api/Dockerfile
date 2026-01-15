FROM python:3.12-slim

RUN apt update && \
    apt install -y ffmpeg curl && \
    pip install flask yt-dlp && \
    apt clean

WORKDIR /app
COPY app.py .

ENV DOWNLOAD_DIR=/downloads

EXPOSE 5000
CMD ["python", "app.py"]
