from flask import Flask, request, jsonify, Response, send_from_directory, abort
import subprocess
import os
import threading
import queue
import time
import logging
import sys

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)

# logging para aparecer no docker logs
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout
)
logger = logging.getLogger(__name__)

tasks = queue.Queue()
state = {
    "status": "idle",
    "last_line": ""
}

def worker():
    logger.info("worker iniciado")
    while True:
        url, fmt = tasks.get()
        logger.info(f"nova tarefa recebida url={url} format={fmt}")

        state["status"] = "downloading"
        state["last_line"] = ""

        output_template = os.path.join(
            DOWNLOAD_DIR,
            "%(title)s.%(ext)s"
        )

        cookies_path = os.path.expanduser(
            "/app/www.tiktok.com_cookies.txt"
        )

        cookies_path_yt = os.path.expanduser(
            "/app/www.youtube.com_cookies.txt"
        )

        common_args = [
            "yt-dlp",
            "--restrict-filenames",
            "--no-playlist",
            "--newline",
        ]

        # adiciona cookies apenas se for TikTok
        if "tiktok" in url:
            common_args.extend(["--cookies", cookies_path])
            logger.info(f"cookies habilitados para TikTok: {cookies_path}")

        # adiciona cookies apenas se for Youtube
        if "youtube.com" in url or "youtu.be" in url:
            common_args.extend(["--cookies", cookies_path_yt])
            logger.info(f"cookies habilitados para Youtube: {cookies_path_yt}")
            common_args.extend(["--extractor-args", "youtube:player_client=web,android,tv"])
            logger.info("extractor args habilitados para Youtube")

        if fmt == "mp3":
            cmd = common_args +  [
                "-x",
                "--audio-format", "mp3",
                "-o", output_template,
                url
            ]
        else:
            cmd = common_args + [
                "-f", "bv*+ba/b",
                "--merge-output-format", "mp4",
                "-o", output_template,
                url
            ]

        logger.info(f"executando comando: {' '.join(cmd)}")

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True
            )

            for line in proc.stdout:
                line = line.strip()
                state["last_line"] = line
                logger.info(f"yt-dlp: {line}")

            return_code = proc.wait()
            logger.info(f"processo yt-dlp finalizado com código {return_code}")

        except Exception as e:
            logger.exception(f"erro no worker ao processar url={url} format={fmt}: {e}")

        state["status"] = "idle"
        state["last_line"] = ""
        tasks.task_done()
        logger.info("tarefa finalizada, estado voltou para idle")

threading.Thread(target=worker, daemon=True).start()

@app.route("/download", methods=["POST"])
def download():
    logger.info("requisição recebida em /download")
    data = request.json
    url = data.get("url")
    fmt = data.get("format", "mp4")

    if not url:
        logger.warning("download recusado: URL ausente")
        return {"error": "URL ausente"}, 400

    tasks.put((url, fmt))
    logger.info(f"tarefa enfileirada url={url} format={fmt} queue_size={tasks.qsize()}")
    return {"status": "queued"}

@app.route("/progress")
def progress():
    logger.info("cliente conectado em /progress")

    def stream():
        while True:
            if state["status"] == "idle":
                yield "data: idle\n\n"
            else:
                yield f"data: {state['last_line']}\n\n"
            time.sleep(1)

    return Response(stream(), mimetype="text/event-stream")

@app.route("/files")
def files():
    files = sorted(os.listdir(DOWNLOAD_DIR))
    logger.info(f"listando arquivos: total={len(files)}")
    return jsonify(files)

@app.route("/download-file/<path:name>")
def download_file(name):
    path = os.path.join(DOWNLOAD_DIR, name)
    logger.info(f"download de arquivo solicitado: {name}")

    if not os.path.isfile(path):
        logger.warning(f"arquivo não encontrado para download: {name}")
        abort(404)

    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=True)

@app.route("/delete", methods=["POST"])
def delete():
    name = request.json.get("name")
    path = os.path.join(DOWNLOAD_DIR, name)

    logger.info(f"solicitação de delete para arquivo: {name}")

    if os.path.isfile(path):
        os.remove(path)
        logger.info(f"arquivo deletado: {name}")
        return {"status": "deleted"}

    logger.warning(f"arquivo não encontrado para delete: {name}")
    return {"error": "arquivo não encontrado"}, 404

logger.info("iniciando aplicação Flask na porta 5000")
app.run(host="0.0.0.0", port=5000)
