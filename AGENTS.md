# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## What this project is

Felix's Calendar Agent (`gws-calendar-bot`) is a Telegram bot that acts as a Google Calendar and Google Tasks assistant. Users send natural-language messages (or photos of event details) and the bot creates Google Calendar events or manages Google Tasks on their behalf. The bot is deployed on Google Cloud Run as the `gws-calendar-bot` service.

## Running locally

```bash
# First-time or after dependency changes — sets up .venv, installs deps, validates env, starts bot
./start.sh

# Subsequent runs (venv already exists)
source .venv/bin/activate
python -m bot.main
```

Copy `.env.example` to `.env` and fill in all three variables before running.

The `gws` CLI (`@googleworkspace/cli` npm package) must be installed locally for the calendar and task tools to work. In Docker it is installed automatically.

## Environment variables

| Variable | Required | Default |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | — |
| `OPENAI_API_KEY` | yes | — |
| `OWNER_TELEGRAM_ID` | yes | — |
| `USER_TIMEZONE` | no | `Asia/Kuala_Lumpur` |
| `AGENT_MODEL` | no | `gpt-5.6-luna` |
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | yes (runtime) | `/gws-config/credentials.json` in Docker |
| `GWS_CREDENTIALS` | yes (Cloud Run) | Written to `/gws-config/credentials.json` at startup |
| `GWS_CLIENT_SECRET` | yes (Cloud Run) | Written to `/gws-config/client_secret.json` at startup |

## Architecture

The request flow is:

```
Telegram update
  → bot/main.py   (python-telegram-bot handlers)
  → bot/agent.py  (OpenAI Agents SDK — model configurable via `AGENT_MODEL`, default `gpt-5.6-luna`, per-chat history)
  → bot/tools.py  (calendar/task tools → shell out to `gws`)
```

**`bot/main.py`** — Registers four handlers: `/start`, `/help`, plain text messages, and photo messages. Photo messages download the image, base64-encode it, and pass it to the agent alongside the caption.

**`bot/agent.py`** — Builds a new `Agent` instance on every request (so the system prompt gets a fresh timestamp). Maintains per-chat conversation history in the module-level `_history` dict (in-memory, lost on restart), capped at 20 messages.

**`bot/tools.py`** — Defines OpenAI agent tools for calendar event proposals, calendar reads, task reads, and task write proposals. Confirmed writes shell out to `gws calendar +insert` or `gws tasks ...`; task/calendar reads run immediately.

## Deployment

Push to `main` deploys via [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml): it builds the Docker image, pushes it to Artifact Registry, and runs `gcloud run deploy` on the `gws-calendar-bot` Cloud Run service. GitHub authenticates through Workload Identity Federation (no stored keys); config comes from GitHub repository variables `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_DEPLOY_SERVICE_ACCOUNT`, `GCP_WORKLOAD_IDENTITY_PROVIDER`.

- **Service settings:** min=max=1 instance, CPU always allocated (`--no-cpu-throttling`) because the bot long-polls Telegram
- **Secrets:** Secret Manager (`TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `OWNER_TELEGRAM_ID`, `GWS_CREDENTIALS`, `GWS_CLIENT_SECRET`), mounted as env vars
- **Start:** `scripts/entrypoint.sh` writes GWS JSON from env vars to `/gws-config`, then runs `python -m bot.main`. When `$PORT` is set (Cloud Run), `bot/main.py` also serves a trivial health endpoint.
- **One-time infra bootstrap:** `PROJECT_ID=... ./scripts/gcp-setup.sh`

Useful commands:

```bash
gcloud run services describe gws-calendar-bot --region <region>
gcloud run services logs read gws-calendar-bot --region <region> --limit 200
gcloud secrets versions add NAME --data-file=-
```

Never commit secrets. Adding a new secret version does not update a running revision until the next deploy (or `gcloud run services update gws-calendar-bot --region <region> --update-env-vars=REDEPLOY=$(date +%s)`).
