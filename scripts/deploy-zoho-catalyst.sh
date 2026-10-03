#!/usr/bin/env bash
# Deploy LogiFlow backend to Zoho Catalyst AppSail (custom Docker runtime).
#
# Prerequisites (one-time, run by a human):
#   npm install -g zcatalyst-cli
#   catalyst login --dc in
#   catalyst init --org <orgId> -p <projectId> -ni   # from the repo root; creates catalyst.json
#   Docker Desktop running
#
# Usage:
#   ./scripts/deploy-zoho-catalyst.sh
#   SERVICE_NAME=logiflow ./scripts/deploy-zoho-catalyst.sh
#
# AppSail limits that differ from Cloud Run: 30s per request (budgets are clamped in
# backend/Dockerfile.appsail), idle instances stop after 5 minutes, linux/amd64 images only.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SERVICE_NAME="${SERVICE_NAME:-logiflow}"
BASE_TAG="logiflow-api:base"
APPSAIL_TAG="logiflow-api:appsail"
ENV_FILE="${ENV_FILE:-${ROOT}/backend/.env}"

command -v catalyst >/dev/null || { echo "catalyst CLI missing: npm install -g zcatalyst-cli"; exit 1; }
docker info >/dev/null 2>&1 || { echo "Docker daemon not running — start Docker Desktop"; exit 1; }
[[ -f "${ROOT}/catalyst.json" ]] || { echo "No catalyst.json in ${ROOT} — run: catalyst init --org <orgId> -p <projectId> -ni"; exit 1; }

echo "==> Building ${BASE_TAG} (linux/amd64) ..."
docker buildx build --platform linux/amd64 --load -t "${BASE_TAG}" "${ROOT}/backend"

echo "==> Building ${APPSAIL_TAG} (AppSail time budgets) ..."
docker buildx build --platform linux/amd64 --load \
  --build-arg BASE_IMAGE="${BASE_TAG}" \
  -f "${ROOT}/backend/Dockerfile.appsail" \
  -t "${APPSAIL_TAG}" "${ROOT}/backend"

echo "==> Deploying AppSail service ${SERVICE_NAME} ..."
cd "${ROOT}"
catalyst deploy appsail --name "${SERVICE_NAME}" --source "docker://${APPSAIL_TAG}" --port 8080 -ni

echo ""
echo "Deployed. Standalone Docker deploys read env vars from the Catalyst console only."
echo "Console → AppSail → ${SERVICE_NAME} → Configuration:"
echo "  - Memory: 2048 MB, health check path: /health"
echo "  - Environment variables (copy values from ${ENV_FILE}):"
if [[ -f "${ENV_FILE}" ]]; then
  while IFS='=' read -r key _; do
    [[ -z "${key}" || "${key}" =~ ^# ]] && continue
    echo "      ${key}"
  done < "${ENV_FILE}"
fi
echo ""
echo "URL: https://${SERVICE_NAME}-<ZAID>.development.catalystappsail.in/health"
echo "Then point frontend BACKEND_URL / NEXT_PUBLIC_API_URL / NEXT_PUBLIC_COMPOSE_URL at it."

[[ "${DEPLOY_WEB:-1}" == "1" ]] || exit 0

# Frontend: NEXT_PUBLIC_* and rewrite targets are baked at build time from frontend/vercel.json.
WEB_SERVICE_NAME="${WEB_SERVICE_NAME:-logiflow-web}"
WEB_TAG="logiflow-web:appsail"
WEB_SITE_URL="${WEB_SITE_URL:-https://${WEB_SERVICE_NAME}-50046515745.development.catalystappsail.in}"
WEB_ARGS=()
while IFS= read -r arg; do WEB_ARGS+=(--build-arg "${arg}"); done < <(
  WEB_SITE_URL="${WEB_SITE_URL}" python3 -c "
import json, os
e = json.load(open('${ROOT}/frontend/vercel.json'))['env']
e['NEXT_PUBLIC_SITE_URL'] = os.environ['WEB_SITE_URL']
for k, v in e.items():
    print(f'{k}={v}')
")

echo "==> Building ${WEB_TAG} (linux/amd64) ..."
docker buildx build --platform linux/amd64 --load "${WEB_ARGS[@]}" \
  -f "${ROOT}/frontend/Dockerfile.appsail" -t "${WEB_TAG}" "${ROOT}/frontend"

echo "==> Deploying AppSail service ${WEB_SERVICE_NAME} ..."
catalyst deploy appsail --name "${WEB_SERVICE_NAME}" --source "docker://${WEB_TAG}" --port 8080 -ni
echo "Frontend: ${WEB_SITE_URL}"
