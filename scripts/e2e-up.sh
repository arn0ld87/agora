#!/usr/bin/env bash
set -euo pipefail

# E2E-Stack-Up — startet Compose-Stack und wartet auf /healthz.
# Wird von frontend/tests/e2e/global-setup.ts aufgerufen.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PROXY_PORT="${AGORA_PROXY_PORT:-80}"
HEALTH_URL="http://127.0.0.1:${PROXY_PORT}/healthz"
TIMEOUT_S="${AGORA_E2E_HEALTH_TIMEOUT_S:-180}"

cd "$REPO_ROOT"

echo "[e2e-up] starting compose stack on port ${PROXY_PORT}..." >&2
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml \
  up -d --build

echo "[e2e-up] waiting for ${HEALTH_URL} (timeout ${TIMEOUT_S}s)..." >&2
deadline=$(( $(date +%s) + TIMEOUT_S ))
while true; do
  if curl -fsS "$HEALTH_URL" >/dev/null 2>&1; then
    echo "[e2e-up] healthz OK" >&2
    exit 0
  fi
  if [[ $(date +%s) -ge $deadline ]]; then
    echo "::error::[e2e-up] healthz timeout after ${TIMEOUT_S}s" >&2
    docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=50 >&2 || true
    exit 1
  fi
  sleep 2
done
