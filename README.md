# WhatsApp Status Mirror (Whapi)

Minimal service that mirrors WhatsApp Status updates from a SOURCE account to a TARGET account using Whapi.cloud webhooks + API.

## Features
- Receives status webhooks from Whapi.
- Downloads photo/video status media from SOURCE.
- Prepares status-friendly media (1080x1920 with padding; H.264/AAC for videos).
- Reposts to TARGET account as a status.
- Persists everything in SQLite for idempotency and retries.

## Requirements
- Python 3.12+
- ffmpeg + ffprobe installed and available in PATH (for video preparation)

## Configuration
Create a `.env` file in the repo root:

```env
WHAPI_API_URL=https://gate.whapi.cloud
WHAPI_SOURCE_TOKEN=source_token_here
WHAPI_TARGET_TOKEN=target_token_here
WEBHOOK_SECRET=shared_secret_here
DB_PATH=data/wa_mirror.db
STORAGE_DIR=data/storage
LOG_LEVEL=INFO
```

## Install

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run locally

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8080
```

## Webhook endpoint
- POST `http(s)://<host>/webhook/whapi`
- If Whapi provides a signature header, the service will verify it.
- Otherwise, include `?secret=WEBHOOK_SECRET` or header `X-Webhook-Secret`.

## Expose webhook (HTTPS)
Use a reverse proxy (Caddy, Nginx, Traefik) or a tunnel (ngrok) to expose HTTPS.
Whapi webhooks require public HTTPS URLs.

## Set webhook in Whapi
Configure the webhook URL in the Whapi dashboard for the SOURCE account. Use:

```
https://<your-domain>/webhook/whapi?secret=WEBHOOK_SECRET
```

## Systemd example
Save as `/etc/systemd/system/wa-mirror.service`:

```ini
[Unit]
Description=WhatsApp Status Mirror
After=network.target

[Service]
Type=simple
WorkingDirectory=/opt/wa-mirror
EnvironmentFile=/opt/wa-mirror/.env
ExecStart=/opt/wa-mirror/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Enable:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now wa-mirror
```

## Self-check
Run a minimal local check:

```bash
python -m app.selfcheck
```

This initializes the database/storage and inserts a sample webhook event.
