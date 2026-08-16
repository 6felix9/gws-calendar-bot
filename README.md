# Felix's Calendar Agent

A Telegram bot (`gws-calendar-bot`) that creates, views, edits, and deletes Google Calendar events from natural-language messages and photos.

## How it works

Send Felix a message like "What do I have today?", "Lunch with Sarah on Friday at 1pm", "Move my lunch tomorrow to 1pm", "Delete my lunch tomorrow", or a photo of an event flyer. It can query your Google Calendar immediately. Creating, editing, or deleting events requires confirmation — each staged change gets its own Confirm/Cancel buttons, including mixed create/edit/delete batches in one message.

## Setup

**Prerequisites:** Python 3.11+, the [`gws` CLI](https://github.com/googleworkspace/gws-cli) installed globally (`npm install -g @googleworkspace/cli`), and GWS credentials configured.

```bash
cp .env.example .env
# Fill in TELEGRAM_BOT_TOKEN, OPENAI_API_KEY, OWNER_TELEGRAM_ID
./start.sh
```

## Environment variables

| Variable | Required | Description |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | yes | From [@BotFather](https://t.me/botfather) |
| `OPENAI_API_KEY` | yes | OpenAI API key |
| `OWNER_TELEGRAM_ID` | yes | Your Telegram user ID (bot ignores other users) |
| `USER_TIMEZONE` | no | Default: `Asia/Kuala_Lumpur` |
| `AGENT_MODEL` | no | Default: `gpt-5.6-luna` |
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | yes (runtime) | Path to GWS credentials JSON |
| `GWS_CREDENTIALS` | yes (Railway) | Full JSON written to `/gws-config/credentials.json` at startup |
| `GWS_CLIENT_SECRET` | yes (Railway) | OAuth client secret JSON written to `/gws-config/client_secret.json` |

## Deployment (Railway)

Push to `main` — GitHub Actions runs `railway up` against the **gws-calendar-bot** service in the **Felix's Calendar Agent** project. Add a project-scoped `RAILWAY_TOKEN` as a GitHub secret.

Manual deploy from this directory:

```bash
railway link --project "Felix's Calendar Agent" --service gws-calendar-bot
railway up --detach -m "local deploy"
```

Infra (variables, volumes, service settings) is managed via the Railway CLI or dashboard — not checked into this repo.

Set secrets on the service:

```bash
railway variable set TELEGRAM_BOT_TOKEN=... --service gws-calendar-bot
railway variable set OPENAI_API_KEY=... --service gws-calendar-bot
railway variable set OWNER_TELEGRAM_ID=... --service gws-calendar-bot
printf '%s' "$GWS_JSON" | railway variable set GWS_CREDENTIALS --stdin --service gws-calendar-bot
printf '%s' "$CLIENT_SECRET_JSON" | railway variable set GWS_CLIENT_SECRET --stdin --service gws-calendar-bot
```

After Railway is live, stop the old DigitalOcean container so only one bot polls Telegram.
