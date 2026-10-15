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
| `GWS_CREDENTIALS` | yes (Cloud Run) | Full JSON written to `/gws-config/credentials.json` at startup |
| `GWS_CLIENT_SECRET` | yes (Cloud Run) | OAuth client secret JSON written to `/gws-config/client_secret.json` |

## Deployment (Google Cloud)

Runs on **Cloud Run** (one always-on instance, CPU always allocated, since the bot long-polls Telegram), with images in **Artifact Registry** and secrets in **Secret Manager**. Push to `main` — GitHub Actions authenticates via Workload Identity Federation (no JSON keys), builds the image, pushes it, and runs `gcloud run deploy`.

One-time setup:

```bash
PROJECT_ID=your-project ./scripts/gcp-setup.sh
```

The script enables APIs, creates the Artifact Registry repo, service accounts, Secret Manager secrets and the Workload Identity pool, then prints the remaining steps. Add the secret values:

```bash
printf '%s' "$TELEGRAM_BOT_TOKEN" | gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=-
printf '%s' "$OPENAI_API_KEY" | gcloud secrets versions add OPENAI_API_KEY --data-file=-
printf '%s' "$OWNER_TELEGRAM_ID" | gcloud secrets versions add OWNER_TELEGRAM_ID --data-file=-
printf '%s' "$GWS_JSON" | gcloud secrets versions add GWS_CREDENTIALS --data-file=-
printf '%s' "$CLIENT_SECRET_JSON" | gcloud secrets versions add GWS_CLIENT_SECRET --data-file=-
```

Then set the GitHub repository **variables** `GCP_PROJECT_ID`, `GCP_REGION`, `GCP_DEPLOY_SERVICE_ACCOUNT` and `GCP_WORKLOAD_IDENTITY_PROVIDER` (values are printed by the setup script).

Logs: `gcloud run services logs read gws-calendar-bot --region <region>`.

Only one instance may run (`--max-instances 1`) so a single process polls Telegram. Stop any old Railway/DigitalOcean deployment before the first GCP deploy.
