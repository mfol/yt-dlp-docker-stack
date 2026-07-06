# yt-dlp Stack (Docker)

API Flask + frontend (Tailwind, mobile-first) para baixar video/audio com `yt-dlp`.

## Destaques

- **Frontend mobile-first** (Tailwind via CDN), tema claro flat minimalista, 3 abas: **Baixar**, **Cookies** e **Manual**.
- **Container self-contained** — o frontend e assado na imagem e servido pelo proprio Flask
  em `/`. Cada rota da API responde em path bare **e** sob `/api` (funciona com ou sem proxy).
- **Aba Manual embutida** — inicio rapido, fluxo, URLs, cookies, FAQ e APIs direto na UI.
- **Gerenciador de cookies pela UI** — renove cookies sem redeploy. Mostra saude
  (ativo / expirando / expirado) e dias restantes por plataforma; cola texto ou
  envia arquivo `.txt`; botao **Testar** valida se o cookie ainda autentica.
- **Jobs com ID + progresso por job** (SSE), multiplos downloads em paralelo (`MAX_WORKERS`).
- **Downloads recentes com multi-selecao** — baixar/excluir em lote e **selecionar tudo**.
- **Compartilhamento** — Web Share API com o arquivo (abre WhatsApp, Instagram, etc. no
  celular); fallback com WhatsApp / Telegram / copiar link.
- **Thumbnails** — frame aleatorio do miolo do video; capa embutida ou waveform para audio.
- **Seguranca**: path traversal bloqueado em download/delete/thumb, validacao de formato e cookie.
- **APIs legadas mantidas** (clientes antigos seguem funcionando), marcadas com header `Deprecation`.

## Subir

```bash
docker compose up -d --build
```

Frontend em `/`, API sob `/api` (e tambem em path bare). Arquivos em `/downloads/<nome>`. Health: `/healthz`.

## Build: publico vs interno

O `Dockerfile` usa **defaults publicos** (`python:3.12-slim`, `pypi.org`, mirror Debian
padrao) — qualquer um consegue buildar. Um build interno (atras de um proxy/registry como
Nexus) sobrescreve via `--build-arg`:

| ARG | Default publico | Exemplo interno |
|-----|-----------------|-----------------|
| `BASE_IMAGE` | `python:3.12-slim` | `docker-cache.exemplo.com/library/python:3.12-slim` |
| `PIP_INDEX_URL` | `https://pypi.org/simple` | `https://nexus.exemplo.com/repository/pypi-proxy/simple` |
| `APT_MIRROR` | *(vazio = mirror padrao)* | `https://nexus.exemplo.com/repository` |

```bash
# build interno
BASE_IMAGE=... APT_MIRROR=... PIP_INDEX_URL=... docker compose build
```

No CI do Gitea (`.gitea/workflows/deploy.yml`) esses valores vem de **repo variables**
(`BASE_IMAGE`, `APT_MIRROR`, `PIP_INDEX_URL`) — configure-as em Settings → Actions →
Variables. Se nao existirem, o build cai no default publico. O CI do GitHub
(`.github/workflows/build.yml`) so valida o build publico, sem publicar imagem.

## Cookies (a parte facil agora)

1. Abra a aba **Cookies** na UI.
2. Exporte com a extensao **"Get cookies.txt LOCALLY"** (formato Netscape) na plataforma logada.
3. Cole o conteudo (ou anexe o `.txt`) no card da plataforma → **Salvar cookie**.
4. (Opcional) **Testar** para confirmar.

Cookies ficam no volume gravavel `./cookies/<plataforma>.txt` (nunca versionado).
Deploys antigos com `www.youtube.com_cookies.txt` / `www.tiktok.com_cookies.txt`
continuam como fallback read-only.

Plataformas: YouTube, TikTok, Instagram (adicionar mais = 1 entrada em `PLATFORMS` no `api/app.py`).

## API

### Novas (recomendadas) — prefixo `/api`
| Metodo | Rota | Descricao |
|--------|------|-----------|
| GET | `/healthz` | status, versao do yt-dlp, fila |
| GET | `/platforms` | plataformas suportadas |
| POST | `/download` | `{url, format}` → `{status, job_id}` |
| GET | `/jobs` | lista de jobs |
| GET | `/jobs/<id>` | 1 job |
| GET | `/jobs/<id>/events` | SSE por job (emite `finished` / `error`) |
| GET | `/files` | lista de arquivos |
| GET / HEAD | `/downloads/<name>` | serve o arquivo (download + metadados) |
| DELETE | `/files/<name>` | apaga arquivo |
| GET | `/thumb/<name>` | thumbnail (frame do video / capa ou waveform do audio) |
| GET | `/cookies` | status de todos os cookies |
| PUT | `/cookies/<platform>` | salva cookie (texto cru, `{content}` json, ou multipart `file`) |
| DELETE | `/cookies/<platform>` | remove cookie |
| POST | `/cookies/<platform>/test` | testa autenticacao |

### Legadas (DEPRECATED, ainda funcionam)
`POST /download` · `GET /progress` (SSE global) · `GET /files` · `GET /download-file/<name>` · `POST /delete {name}`
— respondem com header `Deprecation: true` + `Link` para a sucessora.

## Variaveis de ambiente

| Var | Default | Descricao |
|-----|---------|-----------|
| `DOWNLOAD_DIR` | `/downloads` | saida dos arquivos |
| `COOKIES_DIR` | `/cookies` | cookies gerenciados (gravavel) |
| `THUMBS_DIR` | `/tmp/ytdlp-thumbs` | cache das thumbnails (efemero) |
| `MAX_WORKERS` | `2` | downloads simultaneos |
| `COOKIE_WARN_DAYS` | `7` | dias p/ marcar cookie como "expirando" |
| `CORS_ORIGINS` | (vazio) | `*` ou csv de origens permitidas |
| `FRONTEND_DIR` | `/app/frontend` | onde servir o `index.html` |

## Atualizar no Raspberry Pi

```bash
cd /caminho/pai/do/projeto
mv yt-dlp-stack yt-dlp-stack_backup_$(date +%F_%H%M)
git clone ssh://git@git.packtudo.com:2222/packtudo/yt-dlp.git yt-dlp-stack
cd yt-dlp-stack
docker compose up -d --build
```

Cookies agora pela UI — nao precisa recolocar arquivo manualmente (mas o fallback antigo segue valido).

## Observacoes

- Mantenha `yt-dlp` atualizado (a imagem ja faz `--upgrade` no build).
- Arquivos de cookies sao segredos — tratados como tal, fora do git.
