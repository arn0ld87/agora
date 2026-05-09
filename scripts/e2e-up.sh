#!/usr/bin/env bash
set -euo pipefail

# E2E-Stack-Up — startet Compose-Stack und wartet auf /healthz.
# Wird von frontend/tests/e2e/global-setup.ts aufgerufen.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
PROXY_PORT="${AGORA_PROXY_PORT:-80}"
# Reverse-Proxy-Health (statisches nginx-200) + App-Health (proxied -> Backend).
# Beide müssen pass sein, sonst startet Playwright zu früh und sieht 502 Bad
# Gateway, weil nginx hochgekommen ist, das Backend aber noch im Boot.
HEALTHZ_URL="http://127.0.0.1:${PROXY_PORT}/healthz"
HEALTH_URL="http://127.0.0.1:${PROXY_PORT}/health"
TIMEOUT_S="${AGORA_E2E_HEALTH_TIMEOUT_S:-360}"

cd "$REPO_ROOT"

# .env wird von docker-compose erwartet, ist aber per .gitignore in CI-Checkouts
# nicht vorhanden. Falls sie fehlt, .env.example als Default-Vorlage kopieren.
if [[ ! -f "${REPO_ROOT}/.env" ]]; then
  if [[ -f "${REPO_ROOT}/.env.example" ]]; then
    echo "[e2e-up] no .env found, seeding from .env.example" >&2
    cp "${REPO_ROOT}/.env.example" "${REPO_ROOT}/.env"
  else
    echo "::error::[e2e-up] neither .env nor .env.example present" >&2
    exit 1
  fi
fi

# Kritische Werte aus dem Runner-Env in die .env appenden — docker compose
# variable substitution liest .env mit Vorrang vor Process-Env, daher reicht
# Export auf Runner-Ebene NICHT. Letzte Definition gewinnt; das überschreibt
# die Placeholder aus .env.example. Backend's Config.validate() lehnt
# Placeholder-Werte mit RuntimeError ab.
{
  [[ -n "${AGORA_AUTH_TOKEN:-}" ]] && echo "AGORA_AUTH_TOKEN=${AGORA_AUTH_TOKEN}"
  [[ -n "${SECRET_KEY:-}" ]] && echo "SECRET_KEY=${SECRET_KEY}"
  [[ -n "${NEO4J_PASSWORD:-}" ]] && echo "NEO4J_PASSWORD=${NEO4J_PASSWORD}"
  [[ -n "${AGORA_PROXY_PORT:-}" ]] && echo "AGORA_PROXY_PORT=${AGORA_PROXY_PORT}"
  # Ollama gibt es im CI-Stack nicht — Backend-Boot würde sonst an der
  # Live-Embedding-Probe scheitern (Issue #276). Statische Dimension-Check
  # läuft weiter.
  [[ -n "${AGORA_SKIP_EMBEDDING_PROBE:-}" ]] && echo "AGORA_SKIP_EMBEDDING_PROBE=${AGORA_SKIP_EMBEDDING_PROBE}"
} >> "${REPO_ROOT}/.env"
echo "[e2e-up] runtime credentials appended to .env" >&2

echo "[e2e-up] starting compose stack on port ${PROXY_PORT}..." >&2
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml \
  up -d --build

wait_for() {
  local url="$1"
  local label="$2"
  local local_deadline="$3"
  while true; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "[e2e-up] ${label} OK" >&2
      return 0
    fi
    if [[ $(date +%s) -ge $local_deadline ]]; then
      echo "::error::[e2e-up] ${label} timeout (url=${url})" >&2
      docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=80 >&2 || true
      return 1
    fi
    sleep 2
  done
}

deadline=$(( $(date +%s) + TIMEOUT_S ))

echo "[e2e-up] waiting for reverse-proxy ${HEALTHZ_URL}..." >&2
wait_for "$HEALTHZ_URL" "/healthz" "$deadline" || exit 1

echo "[e2e-up] waiting for backend ${HEALTH_URL} (proxied through nginx)..." >&2
wait_for "$HEALTH_URL" "/health" "$deadline" || exit 1

echo "[e2e-up] stack ready (proxy + backend healthy)" >&2
