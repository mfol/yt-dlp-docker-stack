"""
yt-dlp API (Flask)

Backend para baixar video/audio com yt-dlp.

Compatibilidade:
  - Rotas LEGADAS (mantidas, nao quebrar clientes antigos):
      POST /download            {url, format}      -> {status, job_id}
      GET  /progress            (SSE global)
      GET  /files               -> ["nome", ...]
      GET  /download-file/<name>
      POST /delete              {name}
    Essas rotas enviam o header `Deprecation` apontando para a v2.

  - Rotas NOVAS (v2 / gerenciamento). O proxy expoe tudo sob /api,
    entao o frontend chama /api/<rota> e o Flask recebe /<rota>:
      GET    /healthz
      GET    /platforms
      GET    /jobs                       -> lista de jobs
      GET    /jobs/<id>                  -> 1 job
      GET    /jobs/<id>/events           (SSE por job, emite `finished`/`error`)
      GET    /cookies                    -> status dos cookies por plataforma
      PUT    /cookies/<platform>         (texto cru OU multipart `file`)
      DELETE /cookies/<platform>
      POST   /cookies/<platform>/test    -> testa se o cookie ainda autentica
"""

import os
import sys
import time
import json
import uuid
import queue
import shutil
import logging
import threading
import subprocess
from datetime import datetime, timezone

from flask import (
    Flask, request, jsonify, Response,
    send_from_directory, abort, stream_with_context,
)

# --------------------------------------------------------------------------- #
# Config
# --------------------------------------------------------------------------- #

DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "/downloads")
# Diretorio GRAVAVEL para cookies (volume). Tornar facil renovar cookies.
COOKIES_DIR = os.getenv("COOKIES_DIR", "/cookies")
# Locais legados (montados read-only no compose antigo) usados como fallback.
LEGACY_COOKIE_PATHS = {
    "youtube": "/app/www.youtube.com_cookies.txt",
    "tiktok": "/app/www.tiktok.com_cookies.txt",
}
MAX_WORKERS = int(os.getenv("MAX_WORKERS", "2"))
CORS_ORIGINS = os.getenv("CORS_ORIGINS", "")  # "*" ou csv de origens; vazio = same-origin
COOKIE_WARN_DAYS = int(os.getenv("COOKIE_WARN_DAYS", "7"))

os.makedirs(DOWNLOAD_DIR, exist_ok=True)
os.makedirs(COOKIES_DIR, exist_ok=True)

# Plataformas suportadas. Adicionar nova plataforma = 1 entrada aqui.
PLATFORMS = {
    "youtube": {
        "label": "YouTube",
        "hosts": ["youtube.com", "youtu.be"],
        "test_url": "https://www.youtube.com/watch?v=BaW_jenozKc",
        "extractor_args": ["youtube:player_client=web,android,tv"],
    },
    "tiktok": {
        "label": "TikTok",
        "hosts": ["tiktok.com"],
        "test_url": "https://www.tiktok.com/@tiktok",
        "extractor_args": [],
    },
    "instagram": {
        "label": "Instagram",
        "hosts": ["instagram.com"],
        "test_url": "https://www.instagram.com/instagram/",
        "extractor_args": [],
    },
}

ALLOWED_FORMATS = {"mp3", "mp4"}

# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("ytdlp-api")

app = Flask(__name__)

# --------------------------------------------------------------------------- #
# Helpers: cookies
# --------------------------------------------------------------------------- #

def platform_for_url(url: str):
    u = (url or "").lower()
    for name, cfg in PLATFORMS.items():
        if any(host in u for host in cfg["hosts"]):
            return name
    return None


def cookie_path(platform: str):
    """Caminho efetivo do cookie: prioriza COOKIES_DIR (gravavel), cai no legado."""
    primary = os.path.join(COOKIES_DIR, f"{platform}.txt")
    if os.path.isfile(primary):
        return primary
    legacy = LEGACY_COOKIE_PATHS.get(platform)
    if legacy and os.path.isfile(legacy):
        return legacy
    return None


def writable_cookie_path(platform: str):
    return os.path.join(COOKIES_DIR, f"{platform}.txt")


def parse_cookie_expiry(path: str):
    """Le um arquivo Netscape e devolve (earliest_expiry_ts, total_cookies)."""
    earliest = None
    count = 0
    try:
        with open(path, "r", encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < 7:
                    continue
                count += 1
                try:
                    exp = int(parts[4])
                except ValueError:
                    continue
                if exp <= 0:  # cookie de sessao
                    continue
                if earliest is None or exp < earliest:
                    earliest = exp
    except OSError:
        return None, 0
    return earliest, count


def cookie_status(platform: str):
    path = cookie_path(platform)
    cfg = PLATFORMS[platform]
    base = {
        "platform": platform,
        "label": cfg["label"],
        "present": path is not None,
        "source": None,
        "updated_at": None,
        "size": 0,
        "cookies": 0,
        "earliest_expiry": None,
        "days_left": None,
        "health": "missing",
    }
    if not path:
        return base

    st = os.stat(path)
    earliest, count = parse_cookie_expiry(path)
    base.update(
        present=True,
        source="managed" if path.startswith(COOKIES_DIR) else "legacy",
        updated_at=datetime.fromtimestamp(st.st_mtime, timezone.utc).isoformat(),
        size=st.st_size,
        cookies=count,
    )
    if earliest:
        days = (earliest - time.time()) / 86400.0
        base["earliest_expiry"] = datetime.fromtimestamp(
            earliest, timezone.utc
        ).isoformat()
        base["days_left"] = round(days, 1)
        if days <= 0:
            base["health"] = "expired"
        elif days <= COOKIE_WARN_DAYS:
            base["health"] = "expiring"
        else:
            base["health"] = "ok"
    else:
        base["health"] = "ok" if count else "empty"
    return base


def looks_like_netscape(text: str) -> bool:
    head = text.lstrip()[:512].lower()
    if head.startswith("# netscape http cookie file") or "# http cookie file" in head:
        return True
    # heuristica: alguma linha com 7 campos separados por TAB
    for line in text.splitlines():
        if line and not line.startswith("#") and len(line.split("\t")) >= 7:
            return True
    return False


# --------------------------------------------------------------------------- #
# Helpers: filesystem seguro
# --------------------------------------------------------------------------- #

def safe_download_path(name: str):
    """Resolve `name` dentro de DOWNLOAD_DIR, bloqueando path traversal."""
    if not name or "/" in name or "\\" in name or name in (".", ".."):
        abort(400, description="nome invalido")
    base = os.path.abspath(DOWNLOAD_DIR)
    final = os.path.abspath(os.path.join(base, name))
    if os.path.dirname(final) != base:
        abort(400, description="nome invalido")
    return final


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #

jobs = {}                 # job_id -> dict
jobs_lock = threading.Lock()
task_q = queue.Queue()

# Estado GLOBAL legado (mantido para /progress antigo).
state = {"status": "idle", "last_line": ""}


def new_job(url: str, fmt: str):
    job_id = uuid.uuid4().hex
    job = {
        "id": job_id,
        "url": url,
        "format": fmt,
        "platform": platform_for_url(url),
        "status": "queued",      # queued | downloading | processing | done | error
        "percent": 0.0,
        "last_line": "",
        "filename": None,
        "error": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None,
    }
    with jobs_lock:
        jobs[job_id] = job
        # poda jobs antigos (mantem ultimos 50)
        if len(jobs) > 50:
            for k in sorted(jobs, key=lambda j: jobs[j]["created_at"])[:-50]:
                jobs.pop(k, None)
    return job


def build_cmd(url: str, fmt: str):
    args = ["yt-dlp", "--restrict-filenames", "--no-playlist", "--newline",
            "--print-to-file", "after_move:filepath", "/tmp/_lastfile"]
    platform = platform_for_url(url)
    if platform:
        ck = cookie_path(platform)
        if ck:
            args += ["--cookies", ck]
        for ea in PLATFORMS[platform]["extractor_args"]:
            args += ["--extractor-args", ea]

    out_tpl = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")
    if fmt == "mp3":
        args += ["-x", "--audio-format", "mp3", "-o", out_tpl, url]
    else:
        args += ["-f", "bv*+ba/b", "--merge-output-format", "mp4", "-o", out_tpl, url]
    return args


def run_job(job):
    job_id = job["id"]
    job["status"] = "downloading"
    state["status"] = "downloading"
    state["last_line"] = ""

    cmd = build_cmd(job["url"], job["format"])
    logger.info("job %s exec: %s", job_id, " ".join(cmd))
    try:
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True
        )
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            job["last_line"] = line
            state["last_line"] = line
            if "%" in line and "[download]" in line:
                import re
                m = re.search(r"(\d+(?:\.\d+)?)%", line)
                if m:
                    job["percent"] = float(m.group(1))
            elif "[ffmpeg]" in line or "[ExtractAudio]" in line or "[Merger]" in line:
                job["status"] = "processing"
                job["percent"] = max(job["percent"], 99.0)
            logger.info("yt-dlp[%s]: %s", job_id[:8], line)

        rc = proc.wait()
        if rc == 0:
            job["status"] = "done"
            job["percent"] = 100.0
            try:
                with open("/tmp/_lastfile") as fh:
                    fp = fh.read().strip().splitlines()[-1]
                    job["filename"] = os.path.basename(fp)
            except (OSError, IndexError):
                pass
        else:
            job["status"] = "error"
            job["error"] = job["last_line"] or f"yt-dlp saiu com codigo {rc}"
        logger.info("job %s finalizado rc=%s", job_id, rc)
    except Exception as exc:  # noqa: BLE001
        job["status"] = "error"
        job["error"] = str(exc)
        logger.exception("job %s falhou", job_id)
    finally:
        job["finished_at"] = datetime.now(timezone.utc).isoformat()
        state["status"] = "idle"
        state["last_line"] = ""


def worker(idx: int):
    logger.info("worker %d iniciado", idx)
    while True:
        job_id = task_q.get()
        job = jobs.get(job_id)
        if job:
            run_job(job)
        task_q.task_done()


for i in range(MAX_WORKERS):
    threading.Thread(target=worker, args=(i,), daemon=True).start()


# --------------------------------------------------------------------------- #
# CORS + headers
# --------------------------------------------------------------------------- #

@app.after_request
def add_headers(resp):
    if CORS_ORIGINS:
        origin = request.headers.get("Origin", "")
        if CORS_ORIGINS == "*":
            resp.headers["Access-Control-Allow-Origin"] = "*"
        elif origin in {o.strip() for o in CORS_ORIGINS.split(",")}:
            resp.headers["Access-Control-Allow-Origin"] = origin
            resp.headers["Vary"] = "Origin"
        resp.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,DELETE,OPTIONS"
        resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return resp


# --------------------------------------------------------------------------- #
# Rotas LEGADAS (mantidas) — marcadas como deprecated
# --------------------------------------------------------------------------- #

def _deprecate(resp, successor):
    resp.headers["Deprecation"] = "true"
    resp.headers["Link"] = f'<{successor}>; rel="successor-version"'
    return resp


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = (data.get("url") or "").strip()
    fmt = data.get("format", "mp4")
    if not url:
        return jsonify(error="URL ausente"), 400
    if fmt not in ALLOWED_FORMATS:
        return jsonify(error="formato invalido"), 400

    job = new_job(url, fmt)
    task_q.put(job["id"])
    logger.info("job %s enfileirado url=%s fmt=%s", job["id"], url, fmt)
    resp = jsonify(status="queued", job_id=job["id"])
    return _deprecate(resp, "/api/jobs")


@app.route("/progress")
def progress():
    @stream_with_context
    def stream():
        while True:
            if state["status"] == "idle":
                yield "data: idle\n\n"
            else:
                yield f"data: {state['last_line']}\n\n"
            time.sleep(1)
    resp = Response(stream(), mimetype="text/event-stream")
    return _deprecate(resp, "/api/jobs/<id>/events")


@app.route("/files")
def files():
    items = sorted(os.listdir(DOWNLOAD_DIR))
    return _deprecate(jsonify(items), "/api/files")


@app.route("/download-file/<path:name>")
def download_file(name):
    path = safe_download_path(name)
    if not os.path.isfile(path):
        abort(404)
    return send_from_directory(DOWNLOAD_DIR, name, as_attachment=True)


@app.route("/delete", methods=["POST"])
def delete():
    data = request.get_json(silent=True) or {}
    name = data.get("name")
    if not name:
        return jsonify(error="nome ausente"), 400
    path = safe_download_path(name)
    if os.path.isfile(path):
        os.remove(path)
        logger.info("arquivo deletado: %s", name)
        return _deprecate(jsonify(status="deleted"), "/api/files/<name>")
    return jsonify(error="arquivo nao encontrado"), 404


# --------------------------------------------------------------------------- #
# Rotas NOVAS (v2)
# --------------------------------------------------------------------------- #

@app.route("/healthz")
def healthz():
    return jsonify(
        status="ok",
        version=ytdlp_version(),
        workers=MAX_WORKERS,
        queue=task_q.qsize(),
    )


def ytdlp_version():
    try:
        return subprocess.check_output(["yt-dlp", "--version"], text=True).strip()
    except Exception:  # noqa: BLE001
        return "unknown"


@app.route("/platforms")
def platforms():
    return jsonify([
        {"id": pid, "label": cfg["label"], "hosts": cfg["hosts"]}
        for pid, cfg in PLATFORMS.items()
    ])


@app.route("/jobs")
def list_jobs():
    with jobs_lock:
        data = sorted(jobs.values(), key=lambda j: j["created_at"], reverse=True)
    return jsonify(data)


@app.route("/jobs/<job_id>")
def get_job(job_id):
    job = jobs.get(job_id)
    if not job:
        abort(404)
    return jsonify(job)


@app.route("/jobs/<job_id>/events")
def job_events(job_id):
    job = jobs.get(job_id)
    if not job:
        abort(404)

    @stream_with_context
    def stream():
        last = None
        while True:
            snap = {
                "status": job["status"],
                "percent": job["percent"],
                "last_line": job["last_line"],
                "filename": job["filename"],
                "error": job["error"],
            }
            if snap != last:
                yield f"data: {json.dumps(snap)}\n\n"
                last = dict(snap)
            if job["status"] == "done":
                yield "event: finished\ndata: {}\n\n"
                return
            if job["status"] == "error":
                yield f"event: error\ndata: {json.dumps({'error': job['error']})}\n\n"
                return
            time.sleep(0.8)
    return Response(stream(), mimetype="text/event-stream")


@app.route("/cookies")
def cookies_list():
    return jsonify([cookie_status(p) for p in PLATFORMS])


@app.route("/cookies/<platform>", methods=["GET"])
def cookies_get(platform):
    if platform not in PLATFORMS:
        abort(404)
    return jsonify(cookie_status(platform))


@app.route("/cookies/<platform>", methods=["PUT", "POST"])
def cookies_put(platform):
    if platform not in PLATFORMS:
        abort(404, description="plataforma desconhecida")

    # aceita multipart (file) OU corpo cru (text/plain) OU {content:"..."} json
    content = None
    if "file" in request.files:
        content = request.files["file"].read().decode("utf-8", errors="ignore")
    elif request.is_json:
        content = (request.get_json(silent=True) or {}).get("content")
    else:
        content = request.get_data(as_text=True)

    if not content or not content.strip():
        return jsonify(error="conteudo vazio"), 400
    if not looks_like_netscape(content):
        return jsonify(
            error="nao parece um cookie Netscape. Exporte com a extensao "
                  "'Get cookies.txt' (formato Netscape)."
        ), 422

    dest = writable_cookie_path(platform)
    tmp = dest + ".tmp"
    with open(tmp, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(content if content.startswith("#") else "# Netscape HTTP Cookie File\n" + content)
    os.replace(tmp, dest)
    logger.info("cookies atualizados: %s (%d bytes)", platform, len(content))
    return jsonify(cookie_status(platform))


@app.route("/cookies/<platform>", methods=["DELETE"])
def cookies_delete(platform):
    if platform not in PLATFORMS:
        abort(404)
    path = writable_cookie_path(platform)
    if os.path.isfile(path):
        os.remove(path)
        logger.info("cookies removidos: %s", platform)
    return jsonify(cookie_status(platform))


@app.route("/cookies/<platform>/test", methods=["POST"])
def cookies_test(platform):
    if platform not in PLATFORMS:
        abort(404)
    ck = cookie_path(platform)
    cfg = PLATFORMS[platform]
    cmd = ["yt-dlp", "--simulate", "--no-warnings", "--no-playlist",
           "--playlist-items", "1", "-q"]
    if ck:
        cmd += ["--cookies", ck]
    for ea in cfg["extractor_args"]:
        cmd += ["--extractor-args", ea]
    cmd.append(cfg["test_url"])

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        ok = proc.returncode == 0
        msg = (proc.stderr or proc.stdout).strip().splitlines()
        return jsonify(
            ok=ok,
            has_cookie=ck is not None,
            message=(msg[-1] if msg else ("ok" if ok else "falhou")),
        )
    except subprocess.TimeoutExpired:
        return jsonify(ok=False, has_cookie=ck is not None, message="timeout"), 504


@app.route("/files/<path:name>", methods=["DELETE"])
def delete_file_v2(name):
    path = safe_download_path(name)
    if os.path.isfile(path):
        os.remove(path)
        return jsonify(status="deleted")
    abort(404)


# --------------------------------------------------------------------------- #
# Static frontend (opcional: serve index.html se montado em /app/frontend)
# --------------------------------------------------------------------------- #

FRONTEND_DIR = os.getenv("FRONTEND_DIR", "/app/frontend")


@app.route("/")
def index():
    if os.path.isfile(os.path.join(FRONTEND_DIR, "index.html")):
        return send_from_directory(FRONTEND_DIR, "index.html")
    return jsonify(service="ytdlp-api", health="/healthz")


if __name__ == "__main__":
    logger.info("yt-dlp %s | workers=%d | cookies=%s", ytdlp_version(), MAX_WORKERS, COOKIES_DIR)
    app.run(host="0.0.0.0", port=5000, threaded=True)
