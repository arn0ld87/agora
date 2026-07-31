#!/usr/bin/env bash
set -euo pipefail

# E2E-Stack-Up — startet Compose-Stack und wartet auf /healthz.
# Wird von frontend/tests/e2e/global-setup.ts aufgerufen.

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
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

# Proxy-Port aufloesen — Praezedenz: Process-Env > bestehende .env > 80.
#
# Die .env-Stufe ist wichtig, seit dieses Skript den Port immer schreibt
# (Issue #989): wer AGORA_PROXY_PORT dauerhaft in seiner .env stehen hat und
# E2E ohne Export startet, bekaeme den Wert sonst still ueberschrieben — und
# damit den Publish-Port seines lokalen Proxy-Stacks veraendert.
#
# Der Default 80 stammt aus playwright.config.ts (`http://127.0.0.1:80`) und
# gilt bewusst nicht der Compose-Default 8080 des Proxy-Overrides: die
# Health-Waits unten und Playwright muessen denselben Port treffen.
PROXY_PORT="${AGORA_PROXY_PORT:-}"
if [[ -z "$PROXY_PORT" ]]; then
  PROXY_PORT="$(sed -n 's/^AGORA_PROXY_PORT=//p' "${REPO_ROOT}/.env" | tail -1)"
fi
PROXY_PORT="${PROXY_PORT:-80}"

# Reverse-Proxy-Health (statisches nginx-200) + App-Health (proxied -> Backend).
# Beide müssen pass sein, sonst startet Playwright zu früh und sieht 502 Bad
# Gateway, weil nginx hochgekommen ist, das Backend aber noch im Boot.
HEALTHZ_URL="http://127.0.0.1:${PROXY_PORT}/healthz"
HEALTH_URL="http://127.0.0.1:${PROXY_PORT}/health"

# Slice 5.6: Fernet-Master-Key für den LLM-Provider-Secrets-Store
# (llm_provider_secrets_store.py, env AGORA_SECRET_KEY). Wird beim Seeden
# von Provider-Connections MIT api_key benötigt (frontend/tests/e2e/
# global-setup.ts seed). Ohne diesen Key schlägt _secrets_store.upsert mit
# RuntimeError fehl → API 503 store_unavailable beim e2e-globalSetup, jeder
# Smoke-Job reißt. Wert muss ein gültiger Fernet-Key sein (urlsafe base64,
# 32 Bytes).
#
# Pre-existing Gap (sichtbar geworden, seit e2e-smokes auch auf pull_request
# läuft): das e2e-smokes-Workflow generiert AGORA_SECRET_KEY in keinem der 6
# Jobs (nur AGORA_AUTH_TOKEN/SECRET_KEY/NEO4J_PASSWORD). Früher lief e2e nur
# auf push:main, dort war das gleiche 503 also unsichtbar. Fallback hier
# statt im Workflow: self-contained für alle 6 Jobs + lokale Dev-Runs.
# E2E-seeded Provider-Connections werden nicht zwischen Runs persistiert,
# ein pro-Run-ephemeraler Key ist semantisch korrekt.
if [[ -z "${AGORA_SECRET_KEY:-}" ]]; then
  AGORA_SECRET_KEY="$(python3 -c 'import os,base64; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
  echo "[e2e-up] AGORA_SECRET_KEY not set in env — generated ephemeral Fernet key for this run" >&2
fi

# Kritische Werte aus dem Runner-Env in die .env schreiben — docker compose
# variable substitution liest .env mit Vorrang vor Process-Env, daher reicht
# Export auf Runner-Ebene NICHT. Das überschreibt die Placeholder aus
# .env.example; Backend's Config.validate() lehnt Placeholder-Werte mit
# RuntimeError ab.
#
# Issue #989: Frueher wurde hier reines `>>` verwendet. In CI faellt das nicht
# auf, weil die .env pro Job frisch aus .env.example entsteht — lokal wuchs sie
# dagegen mit jedem Lauf. Zwei konkrete Schaeden daraus:
#
#   * AGORA_SECRET_KEY landete mehrfach mit je frisch erzeugtem Fernet-Key in
#     der Datei. Der letzte gewinnt, also wurden Secrets, die ein frueherer
#     Lauf verschluesselt hat, unlesbar.
#   * AGORA_E2E_LLM_MODE=stub blieb nach dem Lauf stehen. Der Entwicklungs-
#     Stack uebernahm den Schalter beim naechsten Start und lieferte still
#     Stub-Reports statt echter Modellantworten — ohne Fehlermeldung.
#
# Deshalb: pro Schluessel genau eine Zeile, bestehende Definitionen desselben
# Schluessels werden vorher entfernt. Die Logik liegt in scripts/lib/env-file.sh,
# weil e2e-down.sh dieselbe braucht.
# shellcheck source=lib/env-file.sh
source "${SCRIPT_DIR}/lib/env-file.sh"
trap agora_env_cleanup_tmp EXIT

_env_upsert() {
  agora_env_upsert "$1" "$2" "${REPO_ROOT}/.env"
}

[[ -n "${AGORA_AUTH_TOKEN:-}" ]] && _env_upsert AGORA_AUTH_TOKEN "${AGORA_AUTH_TOKEN}"
[[ -n "${SECRET_KEY:-}" ]] && _env_upsert SECRET_KEY "${SECRET_KEY}"
_env_upsert AGORA_SECRET_KEY "${AGORA_SECRET_KEY}"
[[ -n "${NEO4J_PASSWORD:-}" ]] && _env_upsert NEO4J_PASSWORD "${NEO4J_PASSWORD}"
# Immer schreiben, nicht nur bei gesetzter Variable (Issue #989): der
# Proxy-Override publiziert ohne die Variable auf 8080, waehrend dieses Skript
# und playwright.config.ts auf 80 warten. Ein lokaler Lauf ohne gesetzten Port
# lief damit garantiert in den Health-Timeout. PROXY_PORT traegt bereits den
# aufgeloesten Wert — inklusive eines bereits in der .env stehenden, der damit
# erhalten bleibt statt ueberschrieben zu werden.
_env_upsert AGORA_PROXY_PORT "${PROXY_PORT}"
# Ollama gibt es im CI-Stack nicht — Backend-Boot würde sonst an der
# Live-Embedding-Probe scheitern (Issue #276). Statische Dimension-Check
# läuft weiter.
[[ -n "${AGORA_SKIP_EMBEDDING_PROBE:-}" ]] && _env_upsert AGORA_SKIP_EMBEDDING_PROBE "${AGORA_SKIP_EMBEDDING_PROBE}"
# docker compose liest .env mit Vorrang vor Process-Env; daher reicht
# Job-Level `env: AGORA_E2E_LLM_MODE: stub` allein NICHT. Hier setzen,
# damit der Backend-Container den Stub-Pfad in llm_client.py aktiviert
# und keinen Live-Ollama-Call versucht (es gibt im CI-Stack keinen Ollama).
#
# Wird der Schalter NICHT gesetzt, muss eine Altlast aus einem frueheren Lauf
# aktiv entfernt werden: sonst erbte ein normaler Entwicklungs-Start den
# Stub-Modus stillschweigend weiter.
if [[ -n "${AGORA_E2E_LLM_MODE:-}" ]]; then
  _env_upsert AGORA_E2E_LLM_MODE "${AGORA_E2E_LLM_MODE}"
elif agora_env_drop_key AGORA_E2E_LLM_MODE "${REPO_ROOT}/.env"; then
  echo "[e2e-up] stale AGORA_E2E_LLM_MODE from a previous run removed from .env" >&2
fi
echo "[e2e-up] runtime credentials written to .env (one line per key)" >&2

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
#
# Compose-Invocation liegt seit Issue #989 in scripts/e2e-compose.sh, damit
# up, down und der Log-Dump im Playwright-Teardown nicht auseinanderlaufen.
"$SCRIPT_DIR/e2e-compose.sh" up -d --build

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
      "$SCRIPT_DIR/e2e-compose.sh" logs --tail=80 >&2 || true
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
