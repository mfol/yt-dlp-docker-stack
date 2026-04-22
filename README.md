# yt-dlp Stack (Docker)

API Flask + frontend simples para baixar videos/audio com `yt-dlp`, rodando em Docker.

## O que foi ajustado

Foram aplicadas melhorias para reduzir falhas no YouTube (especialmente Shorts) dentro do container:

- Runtime do container atualizado em `api/Dockerfile`:
  - instalacao de `nodejs`, `ffmpeg`, `curl` e `ca-certificates`
  - upgrade de `yt-dlp` e `flask`
  - limpeza de cache do `apt`
- Ajustes de download em `api/app.py`:
  - `DOWNLOAD_DIR` via variavel de ambiente (`DOWNLOAD_DIR`) com fallback `/downloads`
  - adicao de `--no-playlist` e `--newline`
  - suporte a URLs `youtube.com` e `youtu.be`
  - adicao de extractor args para YouTube: `youtube:player_client=web,android,tv`
  - formato de video alterado para `bv*+ba/b` com merge para `mp4`
- Seguranca/repositorio:
  - criado `.gitignore` para nao versionar cookies e pasta de downloads

## Estrutura

- `api/app.py`: API Flask que enfileira e executa downloads
- `api/Dockerfile`: imagem da API
- `docker-compose.yml`: orquestracao local
- `frontend/`: interface web
- `downloads/`: arquivos gerados (nao versionados)

## Subir no Docker

```bash
docker compose up -d --build
```

## Cookies (local, nao versionar)

Crie estes arquivos na raiz do projeto (mesmo nivel do `docker-compose.yml`):

- `www.youtube.com_cookies.txt`
- `www.tiktok.com_cookies.txt`

Formato: Netscape cookie file.

## Atualizar projeto no Raspberry Pi (sem git anterior)

Opcao recomendada: backup + clone limpo.

```bash
sudo apt update && sudo apt install -y git
cd /caminho/pai/do/projeto
mv yt-dlp-stack yt-dlp-stack_backup_$(date +%F_%H%M)
git clone ssh://git@git.packtudo.com:2222/packtudo/yt-dlp.git yt-dlp-stack
cd yt-dlp-stack
```

Depois, recoloque os arquivos de cookies e execute:

```bash
docker compose up -d --build
```

## Observacoes

- Se o YouTube mudar novamente os desafios de assinatura, mantenha o `yt-dlp` atualizado.
- Arquivos de cookies contem sessao/autenticacao. Trate como segredo.
