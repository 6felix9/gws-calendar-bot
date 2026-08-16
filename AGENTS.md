# AGENTS.md

This file provides guidance to coding agents when working with code in this repository.

## What this project is

Felix's Calendar Agent (`gws-calendar-bot`) is a Telegram bot that acts as a Google Calendar and Google Tasks assistant. Users send natural-language messages (or photos of event details) and the bot creates Google Calendar events or manages Google Tasks on their behalf. The bot is deployed on Railway as the `gws-calendar-bot` service in the **Felix's Calendar Agent** project.

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
| `GWS_CREDENTIALS` | yes (Railway) | Written to `/gws-config/credentials.json` at startup |
| `GWS_CLIENT_SECRET` | yes (Railway) | Written to `/gws-config/client_secret.json` at startup |

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

Push to `main` deploys via [`.github/workflows/deploy.yml`](.github/workflows/deploy.yml) using `railway up` to the **gws-calendar-bot** service. Requires a project-scoped `RAILWAY_TOKEN` GitHub secret.

- **Project:** Felix's Calendar Agent
- **Service:** `gws-calendar-bot`
- **Volume:** `gws-config` mounted at `/gws-config`
- **Start:** `scripts/railway-entrypoint.sh` writes GWS JSON from env vars, then runs `python -m bot.main`

## Railway CLI (source of truth for infra)

Do **not** use `.railway/railway.ts` or other in-repo Railway IaC. The globally installed Railway CLI and the Railway dashboard are the single source of truth for service configuration (variables, volumes, build settings, replicas).

Use the CLI for all infra changes:

```bash
railway link --project "Felix's Calendar Agent" --service gws-calendar-bot
railway status --json
railway variable list --service gws-calendar-bot --json
railway variable set KEY=value --service gws-calendar-bot
railway logs --service gws-calendar-bot --lines 200
railway up --service gws-calendar-bot --detach -m "description"
```

Secrets are set as Railway service variables on `gws-calendar-bot` (never committed). After changing variables, Railway redeploys automatically unless you pass `--skip-deploys`.
