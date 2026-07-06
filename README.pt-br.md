# yt-dlp Stack (Docker)

[English](README.md) · **Português (BR)**

API Flask + frontend mobile-first (Tailwind) para baixar vídeo/áudio com
[**yt-dlp**](https://github.com/yt-dlp/yt-dlp), rodando em Docker.

> Movido a [yt-dlp](https://github.com/yt-dlp/yt-dlp) e [FFmpeg](https://ffmpeg.org).
> Este projeto é só uma casca (UI/API) — todo o trabalho pesado é feito por eles.

## Destaques

- **Frontend mobile-first** (Tailwind via CDN), tema claro flat minimalista, 3 abas: **Baixar**, **Cookies** e **Manual**.
- **Container self-contained** — o frontend é assado na imagem e servido pelo próprio Flask
  em `/`. Cada rota da API responde em path bare **e** sob `/api` (funciona com ou sem proxy).
- **Aba Manual embutida** — início rápido, fluxo, URLs, cookies, FAQ e APIs direto na UI.
- **Gerenciador de cookies pela UI** — renove cookies sem redeploy. Mostra saúde
  (ativo / expirando / expirado) e dias restantes por plataforma; cola texto ou
  envia arquivo `.txt`; botão **Testar** valida se o cookie ainda autentica.
- **Jobs com ID + progresso por job** (SSE), múltiplos downloads em paralelo (`MAX_WORKERS`).
- **Downloads recentes com multi-seleção** — baixar/excluir em lote e **selecionar tudo**.
- **Compartilhamento** — Web Share API com o arquivo (abre WhatsApp, Instagram, etc. no
  celular); fallback com WhatsApp / Telegram / copiar link.
- **Thumbnails** — frame aleatório do miolo do vídeo; capa embutida ou waveform para áudio.
- **Segurança**: path traversal bloqueado em download/delete/thumb, validação de formato e cookie.
- **APIs legadas mantidas** (clientes antigos seguem funcionando), marcadas com header `Deprecation`.

## Subir

```bash
docker compose up -d --build
```

Frontend em `/`, API sob `/api` (e também em path bare). Arquivos em `/downloads/<nome>`. Health: `/healthz`.

## Build: público vs interno

O `Dockerfile` usa **defaults públicos** (`python:3.12-slim`, `pypi.org`, mirror Debian
padrão) — qualquer um consegue buildar. Um build interno (atrás de um proxy/registry como
Nexus) sobrescreve via `--build-arg`:

| ARG | Default público | Exemplo interno |
|-----|-----------------|-----------------|
| `BASE_IMAGE` | `python:3.12-slim` | `docker-cache.exemplo.com/library/python:3.12-slim` |
| `PIP_INDEX_URL` | `https://pypi.org/simple` | `https://nexus.exemplo.com/repository/pypi-proxy/simple` |
| `APT_MIRROR` | *(vazio = mirror padrão)* | `https://nexus.exemplo.com/repository` |

```bash
# build interno
BASE_IMAGE=... APT_MIRROR=... PIP_INDEX_URL=... docker compose build
```

No CI do Gitea (`.gitea/workflows/deploy.yml`) esses valores vêm de **repo variables**
(`BASE_IMAGE`, `APT_MIRROR`, `PIP_INDEX_URL`) — configure-as em Settings → Actions →
Variables. Se não existirem, o build cai no default público. O CI do GitHub
(`.github/workflows/build.yml`) só valida o build público, sem publicar imagem.

## Cookies (a parte fácil agora)

1. Abra a aba **Cookies** na UI.
2. Exporte com a extensão **"Get cookies.txt LOCALLY"** (formato Netscape) na plataforma logada.
3. Cole o conteúdo (ou anexe o `.txt`) no card da plataforma → **Salvar cookie**.
4. (Opcional) **Testar** para confirmar.

Cookies ficam no volume gravável `./cookies/<plataforma>.txt` (nunca versionado).
Deploys antigos com `www.youtube.com_cookies.txt` / `www.tiktok.com_cookies.txt`
continuam como fallback read-only.

Plataformas: YouTube, TikTok, Instagram (adicionar mais = 1 entrada em `PLATFORMS` no `api/app.py`).

## API

### Novas (recomendadas) — prefixo `/api`
| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/healthz` | status, versão do yt-dlp, fila |
| GET | `/platforms` | plataformas suportadas |
| POST | `/download` | `{url, format}` → `{status, job_id}` |
| GET | `/jobs` | lista de jobs |
| GET | `/jobs/<id>` | 1 job |
| GET | `/jobs/<id>/events` | SSE por job (emite `finished` / `error`) |
| GET | `/files` | lista de arquivos |
| GET / HEAD | `/downloads/<name>` | serve o arquivo (download + metadados) |
| DELETE | `/files/<name>` | apaga arquivo |
| GET | `/thumb/<name>` | thumbnail (frame do vídeo / capa ou waveform do áudio) |
| GET | `/cookies` | status de todos os cookies |
| PUT | `/cookies/<platform>` | salva cookie (texto cru, `{content}` json, ou multipart `file`) |
| DELETE | `/cookies/<platform>` | remove cookie |
| POST | `/cookies/<platform>/test` | testa autenticação |

### Legadas (DEPRECATED, ainda funcionam)
`POST /download` · `GET /progress` (SSE global) · `GET /files` · `GET /download-file/<name>` · `POST /delete {name}`
— respondem com header `Deprecation: true` + `Link` para a sucessora.

## Variáveis de ambiente

| Var | Default | Descrição |
|-----|---------|-----------|
| `DOWNLOAD_DIR` | `/downloads` | saída dos arquivos |
| `COOKIES_DIR` | `/cookies` | cookies gerenciados (gravável) |
| `THUMBS_DIR` | `/tmp/ytdlp-thumbs` | cache das thumbnails (efêmero) |
| `MAX_WORKERS` | `2` | downloads simultâneos |
| `COOKIE_WARN_DAYS` | `7` | dias p/ marcar cookie como "expirando" |
| `CORS_ORIGINS` | (vazio) | `*` ou csv de origens permitidas |
| `FRONTEND_DIR` | `/app/frontend` | onde servir o `index.html` |

## Observações

- Mantenha `yt-dlp` atualizado (a imagem já faz `--upgrade` no build).
- Arquivos de cookies são segredos — tratados como tal, fora do git.

## Créditos

Este projeto se apoia inteiramente em:

- **[yt-dlp](https://github.com/yt-dlp/yt-dlp)** — o downloader que faz todo o trabalho de verdade.
  Licenciado sob a [The Unlicense](https://github.com/yt-dlp/yt-dlp/blob/master/LICENSE) (domínio público).
  Se te ajudou, considere dar uma estrela e apoiar o projeto.
- **[FFmpeg](https://ffmpeg.org)** — muxing, extração de áudio e geração de thumbnails.
- [Flask](https://flask.palletsprojects.com/) e [Tailwind CSS](https://tailwindcss.com/) pela casca.

## Licença

Esta casca é distribuída sob a **Licença MIT** — veja [LICENSE](LICENSE).

yt-dlp e FFmpeg são projetos separados, invocados como ferramentas externas; **não** são
embutidos aqui e mantêm suas próprias licenças (The Unlicense e LGPL/GPL, respectivamente).
