# yt-dlp Stack (Docker)

**English** · [Português (BR)](README.pt-br.md)

A Flask API + mobile-first frontend (Tailwind) to download video/audio with
[**yt-dlp**](https://github.com/yt-dlp/yt-dlp), running in Docker.

> Powered by [yt-dlp](https://github.com/yt-dlp/yt-dlp) and [FFmpeg](https://ffmpeg.org).
> This project is only a thin UI/API wrapper — all the heavy lifting is done by them.

## Highlights

- **Mobile-first frontend** (Tailwind via CDN), flat light minimalist theme, 3 tabs: **Download**, **Cookies** and **Manual**.
- **Self-contained container** — the frontend is baked into the image and served by Flask
  itself at `/`. Every API route answers on both the bare path **and** under `/api` (works with or without a proxy).
- **Built-in Manual tab** — quick start, flow, URLs, cookies, FAQ and the API right in the UI.
- **Cookie manager in the UI** — refresh cookies without a redeploy. Shows health
  (active / expiring / expired) and days left per platform; paste text or upload a
  `.txt`; a **Test** button checks whether the cookie still authenticates.
- **Job IDs + per-job progress** (SSE), multiple parallel downloads (`MAX_WORKERS`).
- **Recent downloads with multi-select** — bulk download/delete and **select all**.
- **Sharing** — Web Share API with the actual file (opens WhatsApp, Instagram, etc. on
  mobile); fallback with WhatsApp / Telegram / copy link.
- **Thumbnails** — random frame from the middle of the video; embedded cover art or a waveform for audio.
- **Security**: path traversal blocked on download/delete/thumb, format and cookie validation.
- **Legacy APIs kept** (old clients keep working), flagged with a `Deprecation` header.

## Run

```bash
docker compose up -d --build
```

Frontend at `/`, API under `/api` (and also on the bare path). Files at `/downloads/<name>`. Health: `/healthz`.

## Build: public vs internal

The `Dockerfile` uses **public defaults** (`python:3.12-slim`, `pypi.org`, the default
Debian mirror) — anyone can build it. An internal build (behind a proxy/registry such as
Nexus) overrides them via `--build-arg`:

| ARG | Public default | Internal example |
|-----|----------------|------------------|
| `BASE_IMAGE` | `python:3.12-slim` | `docker-cache.example.com/library/python:3.12-slim` |
| `PIP_INDEX_URL` | `https://pypi.org/simple` | `https://nexus.example.com/repository/pypi-proxy/simple` |
| `APT_MIRROR` | *(empty = default mirror)* | `https://nexus.example.com/repository` |

```bash
# internal build
BASE_IMAGE=... APT_MIRROR=... PIP_INDEX_URL=... docker compose build
```

In the Gitea CI (`.gitea/workflows/deploy.yml`) those values come from **repo variables**
(`BASE_IMAGE`, `APT_MIRROR`, `PIP_INDEX_URL`) — set them under Settings → Actions →
Variables. If they are absent, the build falls back to the public defaults. The GitHub CI
(`.github/workflows/build.yml`) only validates the public build; it does not publish an image.

## Cookies (the easy part now)

1. Open the **Cookies** tab in the UI.
2. Export with the **"Get cookies.txt LOCALLY"** extension (Netscape format) while logged in to the platform.
3. Paste the content (or attach the `.txt`) into the platform card → **Save cookie**.
4. (Optional) **Test** to confirm.

Cookies live in the writable volume `./cookies/<platform>.txt` (never committed).
Older deploys with `www.youtube.com_cookies.txt` / `www.tiktok.com_cookies.txt`
still work as a read-only fallback.

Platforms: YouTube, TikTok, Instagram (adding more = one entry in `PLATFORMS` in `api/app.py`).

## API

### New (recommended) — `/api` prefix
| Method | Route | Description |
|--------|-------|-------------|
| GET | `/healthz` | status, yt-dlp version, queue |
| GET | `/platforms` | supported platforms |
| POST | `/download` | `{url, format}` → `{status, job_id}` |
| GET | `/jobs` | list jobs |
| GET | `/jobs/<id>` | one job |
| GET | `/jobs/<id>/events` | per-job SSE (emits `finished` / `error`) |
| GET | `/files` | list files |
| GET / HEAD | `/downloads/<name>` | serve the file (download + metadata) |
| DELETE | `/files/<name>` | delete file |
| GET | `/thumb/<name>` | thumbnail (video frame / audio cover or waveform) |
| GET | `/cookies` | status of all cookies |
| PUT | `/cookies/<platform>` | save cookie (raw text, `{content}` json, or multipart `file`) |
| DELETE | `/cookies/<platform>` | remove cookie |
| POST | `/cookies/<platform>/test` | test authentication |

### Legacy (DEPRECATED, still working)
`POST /download` · `GET /progress` (global SSE) · `GET /files` · `GET /download-file/<name>` · `POST /delete {name}`
— they respond with a `Deprecation: true` header + a `Link` to the successor.

## Environment variables

| Var | Default | Description |
|-----|---------|-------------|
| `DOWNLOAD_DIR` | `/downloads` | output files |
| `COOKIES_DIR` | `/cookies` | managed cookies (writable) |
| `THUMBS_DIR` | `/tmp/ytdlp-thumbs` | thumbnail cache (ephemeral) |
| `MAX_WORKERS` | `2` | concurrent downloads |
| `COOKIE_WARN_DAYS` | `7` | days to mark a cookie as "expiring" |
| `CORS_ORIGINS` | (empty) | `*` or a csv of allowed origins |
| `FRONTEND_DIR` | `/app/frontend` | where to serve `index.html` from |

## Notes

- Keep `yt-dlp` up to date (the image already runs `--upgrade` at build time).
- Cookie files are secrets — treated as such, kept out of git.

## Credits

This project stands entirely on the shoulders of:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — the downloader that does all the real work.
  Licensed under [The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) (public domain).
  If it works for you, consider starring and supporting the project.
- **[FFmpeg](https://ffmpeg.org)** — muxing, audio extraction and thumbnail generation.
- [Flask](https://flask.palletsprojects.com/) and [Tailwind CSS](https://tailwindcss.com/) for the wrapper.

## License

This wrapper is released under the **MIT License** — see [LICENSE](LICENSE).

yt-dlp and FFmpeg are separate projects invoked as external tools; they are **not** bundled
here and keep their own licenses (The Unlicense and LGPL/GPL respectively).
