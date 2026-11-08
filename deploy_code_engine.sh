#!/usr/bin/env bash
# =============================================================================
# VetRelay AI — IBM Code Engine Deploy Script
# Usage: IBM_CLOUD_API_KEY=<your-iam-key> bash deploy_code_engine.sh
# =============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# CONFIG  — edit these if you want different names
# ---------------------------------------------------------------------------
CE_PROJECT="vetrelay-ai"
CE_APP="vetrelay-ai-backend"
CE_REGION="us-south"
CE_IMAGE="icr.io/vetrelay/vetrelay-ai-backend:latest"
CE_PORT=8080
CE_CPU="0.5"
CE_MEMORY="1G"
CE_MIN_SCALE=1
CE_MAX_SCALE=3

# ---------------------------------------------------------------------------
# STEP 0 — ensure IBM_CLOUD_API_KEY is set
# ---------------------------------------------------------------------------
if [[ -z "${IBM_CLOUD_API_KEY:-}" ]]; then
  echo "ERROR: IBM_CLOUD_API_KEY env var not set."
  echo "  Get yours: IBM Cloud → Manage → Access (IAM) → API keys → Create"
  echo "  Then run:  IBM_CLOUD_API_KEY=<key> bash deploy_code_engine.sh"
  exit 1
fi

echo "==> Logging in to IBM Cloud..."
ibmcloud login --no-region --apikey "$IBM_CLOUD_API_KEY" -q
ibmcloud target -r "$CE_REGION" -q

# ---------------------------------------------------------------------------
# STEP 1 — Container Registry login + namespace
# ---------------------------------------------------------------------------
echo "==> Setting up IBM Container Registry (ICR)..."
ibmcloud cr login
ibmcloud cr namespace-add vetrelay 2>/dev/null || true   # ignore if exists

# ---------------------------------------------------------------------------
# STEP 2 — Build image using Code Engine build (no local Docker needed)
# ---------------------------------------------------------------------------
echo "==> Creating/selecting Code Engine project..."
ibmcloud ce project create --name "$CE_PROJECT" 2>/dev/null || \
  ibmcloud ce project select --name "$CE_PROJECT"
ibmcloud ce project select --name "$CE_PROJECT"

echo "==> Creating ICR API key for Code Engine..."
ibmcloud iam api-key-create vetrelay-icr-key --file /tmp/vetrelay_icr_key.json 2>/dev/null || true
ICR_KEY=$(python3 -c "import json; print(json.load(open('/tmp/vetrelay_icr_key.json'))['apikey'])" 2>/dev/null || echo "$IBM_CLOUD_API_KEY")

echo "==> Creating Code Engine registry secret for ICR..."
ibmcloud ce secret create-registry \
  --name vetrelay-icr \
  --server icr.io \
  --username iamapikey \
  --password "$ICR_KEY" 2>/dev/null || \
ibmcloud ce secret update-registry \
  --name vetrelay-icr \
  --server icr.io \
  --username iamapikey \
  --password "$ICR_KEY"

echo "==> Submitting Code Engine build from local source..."
ibmcloud ce buildrun submit \
  --name vetrelay-build \
  --image "$CE_IMAGE" \
  --registry-secret vetrelay-icr \
  --source . \
  --strategy dockerfile \
  --dockerfile Dockerfile \
  --wait 2>&1 || \
ibmcloud ce buildrun submit \
  --name "vetrelay-build-$(date +%s)" \
  --image "$CE_IMAGE" \
  --registry-secret vetrelay-icr \
  --source . \
  --strategy dockerfile \
  --dockerfile Dockerfile \
  --wait

echo "==> Build complete. Deploying application..."

# ---------------------------------------------------------------------------
# STEP 3 — Load env vars from .env
# ---------------------------------------------------------------------------
source .env 2>/dev/null || true

# ---------------------------------------------------------------------------
# STEP 4 — Create or update the CE application
# ---------------------------------------------------------------------------
CE_ENV_ARGS=(
  --env "CLOUDANT_APIKEY=${CLOUDANT_APIKEY:-}"
  --env "CLOUDANT_URL=${CLOUDANT_URL:-}"
  --env "CLOUDANT_DB_NAME=${CLOUDANT_DB_NAME:-vetrelay_intakes}"
  --env "WATSON_TTS_APIKEY=${WATSON_TTS_APIKEY:-}"
  --env "WATSON_TTS_URL=${WATSON_TTS_URL:-}"
  --env "WATSON_STT_APIKEY=${WATSON_STT_APIKEY:-}"
  --env "WATSON_STT_URL=${WATSON_STT_URL:-}"
  --env "WATSONX_API_KEY=${WATSONX_API_KEY:-}"
  --env "WATSONX_URL=${WATSONX_URL:-}"
  --env "WATSONX_PROJECT_ID=${WATSONX_PROJECT_ID:-}"
  --env "PYTHONPATH=."
)

echo "==> Deploying Code Engine application..."
ibmcloud ce application create \
  --name "$CE_APP" \
  --image "$CE_IMAGE" \
  --registry-secret vetrelay-icr \
  --port "$CE_PORT" \
  --cpu "$CE_CPU" \
  --memory "$CE_MEMORY" \
  --min-scale "$CE_MIN_SCALE" \
  --max-scale "$CE_MAX_SCALE" \
  "${CE_ENV_ARGS[@]}" 2>/dev/null || \
ibmcloud ce application update \
  --name "$CE_APP" \
  --image "$CE_IMAGE" \
  --port "$CE_PORT" \
  "${CE_ENV_ARGS[@]}"

echo ""
echo "==> Fetching application URL..."
APP_URL=$(ibmcloud ce application get --name "$CE_APP" --output json 2>/dev/null | \
  python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('status',{}).get('url',''))" 2>/dev/null || echo "")
echo "App URL: $APP_URL"

echo ""
echo "==> Health check..."
if [[ -n "$APP_URL" ]]; then
  sleep 5
  curl -sf "$APP_URL/healthz" && echo " ✓ /healthz OK" || echo " ✗ health check failed"
fi

echo ""
echo "✅  VetRelay AI deployed to IBM Code Engine!"
echo "   App:    $CE_APP"
echo "   URL:    ${APP_URL:-<check ibmcloud ce application get --name $CE_APP>}"
echo "   Docs:   ${APP_URL:-<url>}/docs"
echo "   Health: ${APP_URL:-<url>}/healthz"
