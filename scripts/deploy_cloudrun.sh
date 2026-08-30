#!/usr/bin/env bash
# Deploy Replay to Google Cloud Run.
#
#   ./scripts/deploy_cloudrun.sh my-project-id
#
# Cloud Run builds the Dockerfile for you, so no local Docker is needed. It
# injects $PORT, which the image already honours.
#
# Why the flags matter:
#   --timeout 900       Cloud Run defaults to a 300s request timeout. A
#                       rehearsal can exceed that, and the request would be
#                       cut off mid-verification. This is the single most
#                       important flag here.
#   --cpu 1             A full vCPU. The free tier covers roughly 1,500
#                       rehearsals a month at this size.
#   --memory 1Gi        Room for the agents plus the scenario subprocesses.
#   --max-instances 2   A public URL running paid model calls should not be
#                       able to scale out under load.
#   --min-instances 0   Scale to zero when idle. Cold start is a few seconds,
#                       so no keep-warm ping is needed.

set -euo pipefail

PROJECT="${1:-}"
REGION="${REGION:-us-east1}"
SERVICE="${SERVICE:-replay}"

if [ -z "$PROJECT" ]; then
  echo "Usage: $0 <gcp-project-id>" >&2
  exit 1
fi

if ! command -v gcloud >/dev/null 2>&1; then
  echo "gcloud is not installed. See https://cloud.google.com/sdk/docs/install" >&2
  exit 1
fi

: "${AWS_ACCESS_KEY_ID:?set AWS_ACCESS_KEY_ID in your shell before deploying}"
: "${AWS_SECRET_ACCESS_KEY:?set AWS_SECRET_ACCESS_KEY in your shell before deploying}"

echo "Project : $PROJECT"
echo "Region  : $REGION   (keep this near the Bedrock region to avoid a round trip)"
echo

gcloud config set project "$PROJECT" --quiet

echo "Enabling the APIs Cloud Run needs..."
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  artifactregistry.googleapis.com \
  --quiet

echo "Building and deploying..."
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  --allow-unauthenticated \
  --cpu 1 \
  --memory 1Gi \
  --timeout 900 \
  --concurrency 4 \
  --min-instances 0 \
  --max-instances 2 \
  --set-env-vars "AWS_REGION=us-east-1,AWS_ACCESS_KEY_ID=${AWS_ACCESS_KEY_ID},AWS_SECRET_ACCESS_KEY=${AWS_SECRET_ACCESS_KEY}" \
  --quiet

echo
gcloud run services describe "$SERVICE" --region "$REGION" \
  --format="value(status.url)"
