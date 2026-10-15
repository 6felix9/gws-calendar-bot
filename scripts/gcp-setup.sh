#!/usr/bin/env bash
# One-time GCP bootstrap: APIs, Artifact Registry, Secret Manager, service accounts,
# and Workload Identity Federation so GitHub Actions can deploy without a JSON key.
#
# Usage: PROJECT_ID=my-project ./scripts/gcp-setup.sh
# Optional: REGION (default asia-southeast1), GITHUB_REPO (default 6felix9/gws-calendar-bot)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?Set PROJECT_ID}"
REGION="${REGION:-asia-southeast1}"
GITHUB_REPO="${GITHUB_REPO:-6felix9/gws-calendar-bot}"
SERVICE=gws-calendar-bot
POOL=github
PROVIDER=github-actions

RUNTIME_SA="${SERVICE}@${PROJECT_ID}.iam.gserviceaccount.com"
DEPLOY_SA="github-deployer@${PROJECT_ID}.iam.gserviceaccount.com"
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"

gcloud config set project "$PROJECT_ID"

gcloud services enable \
  run.googleapis.com artifactregistry.googleapis.com secretmanager.googleapis.com \
  iamcredentials.googleapis.com iam.googleapis.com

gcloud artifacts repositories describe "$SERVICE" --location "$REGION" >/dev/null 2>&1 ||
  gcloud artifacts repositories create "$SERVICE" --repository-format docker --location "$REGION"

for sa in "$SERVICE:Runtime for $SERVICE" "github-deployer:GitHub Actions deployer"; do
  id="${sa%%:*}"; name="${sa#*:}"
  gcloud iam service-accounts describe "${id}@${PROJECT_ID}.iam.gserviceaccount.com" >/dev/null 2>&1 ||
    gcloud iam service-accounts create "$id" --display-name "$name"
done

for secret in TELEGRAM_BOT_TOKEN OPENAI_API_KEY OWNER_TELEGRAM_ID GWS_CREDENTIALS GWS_CLIENT_SECRET; do
  gcloud secrets describe "$secret" >/dev/null 2>&1 ||
    gcloud secrets create "$secret" --replication-policy automatic
  gcloud secrets add-iam-policy-binding "$secret" \
    --member "serviceAccount:${RUNTIME_SA}" --role roles/secretmanager.secretAccessor --quiet >/dev/null
done

# Deployer: push images, deploy Cloud Run, and act as the runtime service account.
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${DEPLOY_SA}" \
  --role roles/run.admin --quiet >/dev/null
gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${DEPLOY_SA}" \
  --role roles/artifactregistry.writer --quiet >/dev/null
gcloud iam service-accounts add-iam-policy-binding "$RUNTIME_SA" \
  --member "serviceAccount:${DEPLOY_SA}" --role roles/iam.serviceAccountUser --quiet >/dev/null

gcloud iam workload-identity-pools describe "$POOL" --location global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools create "$POOL" --location global --display-name "GitHub"

gcloud iam workload-identity-pools providers describe "$PROVIDER" \
  --workload-identity-pool "$POOL" --location global >/dev/null 2>&1 ||
  gcloud iam workload-identity-pools providers create-oidc "$PROVIDER" \
    --workload-identity-pool "$POOL" --location global \
    --issuer-uri "https://token.actions.githubusercontent.com" \
    --attribute-mapping "google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition "assertion.repository == '${GITHUB_REPO}'"

gcloud iam service-accounts add-iam-policy-binding "$DEPLOY_SA" \
  --role roles/iam.workloadIdentityUser --quiet >/dev/null \
  --member "principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/attribute.repository/${GITHUB_REPO}"

cat <<MSG

Done. Next steps:

1. Add secret values (repeat per secret):
     printf '%s' "\$VALUE" | gcloud secrets versions add TELEGRAM_BOT_TOKEN --data-file=-
   Secrets: TELEGRAM_BOT_TOKEN OPENAI_API_KEY OWNER_TELEGRAM_ID GWS_CREDENTIALS GWS_CLIENT_SECRET

2. Set these GitHub repository *variables* (Settings > Secrets and variables > Actions > Variables):
     GCP_PROJECT_ID                 = ${PROJECT_ID}
     GCP_REGION                     = ${REGION}
     GCP_DEPLOY_SERVICE_ACCOUNT     = ${DEPLOY_SA}
     GCP_WORKLOAD_IDENTITY_PROVIDER = projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${POOL}/providers/${PROVIDER}

3. Stop the Railway service, then push to main (or run the Deploy workflow) so only one bot polls Telegram.
MSG
