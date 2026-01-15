from flask import Flask, request, jsonify, Response, send_from_directory, abort
import subprocess
import os
import threading
import queue
import time

DOWNLOAD_DIR = "/downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

app = Flask(__name__)

tasks = queue.Queue()
state = {
    "status": "idle",
    "last_line": ""
}

def worker():
    while True:
        url, fmt = tasks.get()
        state["status"] = "downloading"
        state["last_line"] = ""

        output_template = os.path.join(
            DOWNLOAD_DIR,
            "%(title)s.%(ext)s"
        )

        cookies_path = os.path.expanduser(
            "/app/www.tiktok.com_cookies.txt"
        )

        common_args = [
            "yt-dlp",
            "--restrict-filenames",
        ]

        # adiciona cookies apenas se for TikTok
        if "tiktok" in url:
            common_args.extend(["--cookies", cookies_path])

        if fmt == "mp3":
            cmd = common_args +  [
                "-x",
                "--audio-format", "mp3",
                "-o", output_template,
                url
            ]
        else:
            cmd = common_args + [
                "-f", "best",
                "-o", output_template,
                url
            ]

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True
        )

        for line in proc.stdout:
            state["last_line"] = line.strip()

        state["status"] = "idle"
        state["last_line"] = ""
        tasks.task_done()

threading.Thread(target=worker, daemon=True).start()

@app.route("/download", methods=["POST"])
def download():
    data = request.json
    url = data.get("url")
    fmt = data.get("format", "mp4")

    if not url:
        return {"error": "URL ausente"}, 400

    tasks.put((url, fmt))
    return {"status": "queued"}

@app.route("/progress")
def progress():
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
    return jsonify(files)

@app.route("/download-file/<path:name>")
def download_file(name):
    path = os.path.join(DOWNLOAD_DIR, name)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=True)

@app.route("/delete", methods=["POST"])
def delete():
    name = request.json.get("name")
    path = os.path.join(DOWNLOAD_DIR, name)

    if os.path.isfile(path):
        os.remove(path)
        return {"status": "deleted"}

    return {"error": "arquivo não encontrado"}, 404

app.run(host="0.0.0.0", port=5000)
