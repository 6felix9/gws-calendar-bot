# Felix

A Telegram bot that creates and views Google Calendar events from natural-language messages and photos.

## How it works

Send Felix a message like "What do I have today?", "Lunch with Sarah on Friday at 1pm", or a photo of an event flyer. It can query your Google Calendar immediately, and it will ask for confirmation before creating new events.

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
| `GOOGLE_WORKSPACE_CLI_CREDENTIALS_FILE` | yes (runtime) | Path to GWS credentials JSON |

## Deployment

Push to `main` — GitHub Actions builds a Docker image and deploys it to a DigitalOcean Droplet. Required secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `TELEGRAM_BOT_TOKEN`, `OPENAI_API_KEY`, `GWS_CREDENTIALS`, `DROPLET_HOST`, `DROPLET_SSH_KEY`.
