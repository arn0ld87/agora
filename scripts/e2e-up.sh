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
  # Slice 5.6: Fernet-Master-Key für den LLM-Provider-Secrets-Store
  # (llm_provider_secrets_store.py, env AGORA_SECRET_KEY). Wird beim Seeden
  # von Provider-Connections MIT api_key benötigt (frontend/tests/e2e/
  # global-setup.ts seed). Ohne diesen Key schlägt _secrets_store.upsert mit
  # RuntimeError fehl → API 503 store_unavailable. Wert muss ein gültiger
  # Fernet-Key sein (urlsafe base64, 32 Bytes); im Runner generieren via
  #   python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())'
  [[ -n "${AGORA_SECRET_KEY:-}" ]] && echo "AGORA_SECRET_KEY=${AGORA_SECRET_KEY}"
  [[ -n "${NEO4J_PASSWORD:-}" ]] && echo "NEO4J_PASSWORD=${NEO4J_PASSWORD}"
  [[ -n "${AGORA_PROXY_PORT:-}" ]] && echo "AGORA_PROXY_PORT=${AGORA_PROXY_PORT}"
  # Ollama gibt es im CI-Stack nicht — Backend-Boot würde sonst an der
  # Live-Embedding-Probe scheitern (Issue #276). Statische Dimension-Check
  # läuft weiter.
  [[ -n "${AGORA_SKIP_EMBEDDING_PROBE:-}" ]] && echo "AGORA_SKIP_EMBEDDING_PROBE=${AGORA_SKIP_EMBEDDING_PROBE}"
  # docker compose liest .env mit Vorrang vor Process-Env; daher reicht
  # Job-Level `env: AGORA_E2E_LLM_MODE: stub` allein NICHT. Hier appenden,
  # damit der Backend-Container den Stub-Pfad in llm_client.py:386 aktiviert
  # und keinen Live-Ollama-Call versucht (es gibt im CI-Stack keinen Ollama).
  [[ -n "${AGORA_E2E_LLM_MODE:-}" ]] && echo "AGORA_E2E_LLM_MODE=${AGORA_E2E_LLM_MODE}"
} >> "${REPO_ROOT}/.env"
echo "[e2e-up] runtime credentials appended to .env" >&2

# Followup #8: Bind-Mount-Sources mit Container-User-UID anlegen, sonst
# erzeugt der Docker-Daemon die Verzeichnisse als root und das Backend
# (User `agora`, UID 1000) kann nicht reinschreiben — RunRegistry.__new__
# bricht dann mit PermissionError ab (CI-Failure 25595884785).
# Gleiches gilt für backend/instance (LlmProfilesStore legt beim Import
# instance/llm_profiles.db an — sqlite3.OperationalError "unable to open
# database file", CI-Failure 27233527207) und backend/data
# (llm_provider_secrets.json / workspace_llm_routing.json, 0600 vom Backend).
mkdir -p \
  "${REPO_ROOT}/backend/uploads/run_registry" \
  "${REPO_ROOT}/backend/uploads/simulations" \
  "${REPO_ROOT}/backend/instance" \
  "${REPO_ROOT}/backend/data"
if [[ "$(id -u)" == "0" ]]; then
  # CI-Runner laufen oft als root — explizit auf Container-User chownen.
  chown -R 1000:1000 "${REPO_ROOT}/backend/uploads" "${REPO_ROOT}/backend/instance" "${REPO_ROOT}/backend/data"
else
  # Lokaler Mac/Linux-Dev — chmod auf weltweit beschreibbare VERZEICHNISSE
  # reicht, weil der Bind-Mount-Source dem Dev-User gehört, nicht UID 1000.
  # Bewusst ohne -R: rekursives chmod würde restriktive Datei-Modes
  # plattmachen (LlmProviderSecretsStore schreibt llm_provider_secrets.json
  # mit 0600 nach backend/data — Gemini-Review #627).
  chmod 0777 \
    "${REPO_ROOT}/backend/uploads" \
    "${REPO_ROOT}/backend/uploads/run_registry" \
    "${REPO_ROOT}/backend/uploads/simulations" \
    "${REPO_ROOT}/backend/instance" \
    "${REPO_ROOT}/backend/data"
fi
echo "[e2e-up] backend/uploads, backend/instance, backend/data prepared with writable permissions" >&2

echo "[e2e-up] starting compose stack on port ${PROXY_PORT}..." >&2
# E2E-Override hebt read_only=true aus M11 Phase 3 auf, weil RunRegistry
# beim Boot auf /app/backend/uploads/run_registry schreibt — nicht in den
# tmpfs. Prod-Hardening bleibt unangetastet (override wird nur hier geladen).
docker compose \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml \
  -f deploy/compose/docker-compose.e2e.override.yml \
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
