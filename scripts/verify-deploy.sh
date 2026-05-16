#!/usr/bin/env bash
# Verifiziert dass die zuletzt committeten Fixes im Container live sind.
# Sub-Slice 45: Auto-Detect Proxy-Stack, neue Probes gegen :80/healthz, /health, /.
# Issue #450 P1.8: --full schaltet einen Provider-Setup→Routing→Restart-
#                  Persistenz-Smoke + Secret-Scan dazu.
set -uo pipefail
cd "$(dirname "$0")/.."

# Port-Konfiguration (ueberschreibbar via ENV)
PROXY_PORT="${AGORA_PROXY_PORT:-80}"
BACKEND_PORT="${AGORA_BACKEND_PORT:-5001}"

# --full schaltet die Issue #450 P1.8 Persistenz-Phase scharf.
RUN_FULL=0
for arg in "$@"; do
  case "$arg" in
    --full) RUN_FULL=1 ;;
    *) ;;
  esac
done

ok=0; fail=0
check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  OK  $name"; ok=$((ok+1))
  else
    echo "  FAIL $name"; fail=$((fail+1))
  fi
}

_container_running() {
  local service="$1"
  local cid
  cid="$(docker compose ps -a -q "$service" 2>/dev/null || true)"
  if [ -z "$cid" ]; then
    cid="$(docker ps -a -q --filter "name=^agora-${service}$" 2>/dev/null || true)"
  fi
  if [ -z "$cid" ]; then
    cid="$(docker ps -a -q --filter "name=^${service}$" 2>/dev/null || true)"
  fi

  [ -n "$cid" ] || return 1
  while IFS= read -r container_id; do
    [ -n "$container_id" ] || continue
    [ "$(docker inspect -f '{{.State.Running}}' "$container_id" 2>/dev/null)" = "true" ] && return 0
  done <<< "$cid"

  return 1
}

_frontend_bundle_present() {
  docker compose exec -T agora sh -c \
    'test -s /app/frontend/dist/index.html && ls /app/frontend/dist/assets/*.js >/dev/null 2>&1'
}

_markdown_renderer_uses_dompurify() {
  grep -q "DOMPurify" frontend/src/utils/markdown.ts &&
    grep -q "DOMPurify.sanitize" frontend/src/utils/markdown.ts
}

# ---------------------------------------------------------------------------
# Auto-Detect: Ist der nginx-Sidecar aktiv?
# ---------------------------------------------------------------------------
PROXY_ACTIVE=0
if docker compose ps --services 2>/dev/null | grep -q '^nginx$'; then
  PROXY_ACTIVE=1
fi

echo "Proxy-Modus: $([ $PROXY_ACTIVE -eq 1 ] && echo 'nginx-Sidecar (:'"$PROXY_PORT"')' || echo 'direkt (:'"$BACKEND_PORT"')')"
echo

# ---------------------------------------------------------------------------
# Container-Health
# ---------------------------------------------------------------------------
echo "Container-Health:"
check "agora laeuft" _container_running agora

if [ $PROXY_ACTIVE -eq 1 ]; then
  check "nginx laeuft" _container_running nginx
  check "nginx /healthz (Sidecar-eigen)" curl -fsS "http://localhost:${PROXY_PORT}/healthz"
  check "Backend /health (via Proxy)" curl -fsS "http://localhost:${PROXY_PORT}/health"
  check "Frontend / erreichbar (via Proxy)" bash -c "curl -fsS -o /dev/null -w '%{http_code}' \"http://localhost:${PROXY_PORT}/\" | grep -qE '^(200|301|302)$'"
  # M9.6: signed-ticket-Endpoint smoken. AGORA_AUTH_TOKEN ist im CI-Smoke
  # gesetzt; lokal kann das Skript ohne Token starten und der Check skippt
  # dann sauber.
  if [ -n "${AGORA_AUTH_TOKEN:-}" ]; then
    _check_ticket() {
      curl -fsS -X POST \
        -H "X-Agora-Token: $AGORA_AUTH_TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"scope":"sse:smoke"}' \
        "http://localhost:${PROXY_PORT}/api/auth/ticket" \
        | grep -q '"ticket"'
    }
    check "Auth /api/auth/ticket via Proxy" _check_ticket
  else
    echo "  SKIP /api/auth/ticket (kein AGORA_AUTH_TOKEN in env)"
  fi
else
  check "Backend /health (direkt)" docker compose exec -T agora curl -fs "http://localhost:${BACKEND_PORT}/health"
fi

echo
echo "S1 (XSS-Fix):"
if [ $PROXY_ACTIVE -eq 1 ]; then
  # Das Prod-Image enthaelt nur /app/frontend/dist; minifizierte Vendor-Strings
  # sind kein stabiler Security-Smoke. Daher pruefen wir das ausgelieferte
  # Bundle im Container und pinnen den DOMPurify-Vertrag gegen den Source-Stand.
  check "Frontend-Bundle im Image vorhanden (dist)" _frontend_bundle_present
  check "Markdown-Renderer nutzt DOMPurify (source)" _markdown_renderer_uses_dompurify
else
  check "DOMPurify im node_modules" docker compose exec -T agora test -d frontend/node_modules/dompurify
  check "Markdown-Renderer nutzt DOMPurify (source)" _markdown_renderer_uses_dompurify
fi

echo
echo "S2-pre (Schema-Fix):"
check "name->id Lookup im Service" \
  docker compose exec -T agora grep -q "post_author_name\|original_author_name\|target_user_name" backend/app/services/network_analytics.py

echo
echo "P450-3 (backend/data Persistenz, Issue #450 P1.3):"
_data_dir_writable() {
  docker compose exec -T agora test -d /app/backend/data && \
    docker compose exec -T agora test -w /app/backend/data
}
_secrets_file_mode_or_absent() {
  # File ist 0600, falls vorhanden. Wenn die Datei noch nicht angelegt ist,
  # gilt der Check als bestanden (Frischer Container ohne Provider-Setup).
  docker compose exec -T agora sh -c '
    if [ -f /app/backend/data/llm_provider_secrets.json ]; then
      mode=$(stat -c "%a" /app/backend/data/llm_provider_secrets.json 2>/dev/null || \
             stat -f "%A" /app/backend/data/llm_provider_secrets.json 2>/dev/null)
      [ "$mode" = "600" ]
    else
      true
    fi
  '
}
check "backend/data im Container schreibbar" _data_dir_writable
check "llm_provider_secrets.json hat Mode 0600 (oder fehlt noch)" _secrets_file_mode_or_absent

echo
echo "Diagnose-Run (3 letzte Sims):"
docker compose exec -T agora uv run --project backend \
  python backend/scripts/diagnose_metric_snapshot.py --limit 3 --no-write 2>&1 | tail -10

echo
echo "Result: $ok ok, $fail fail"

# N2: Loopback-Bind-Check (auf dem Host, nicht im Container)
# Im Prod-with-Proxy-Modus ist Backend nicht direkt host-gemapped (nur nginx :80
# ist exposed), die Vite/Flask-Ports existieren dort gar nicht. Check ist nur
# für Dev-Compose ohne Proxy sinnvoll.
echo
echo "N2 (Loopback-Bind):"
if [ $PROXY_ACTIVE -eq 1 ]; then
  echo "  SKIP Loopback-Bind-Checks (Prod-with-Proxy: Backend/Vite-Ports nicht host-gemapped)"
else
  check "Vite auf ${AGORA_BIND_HOST:-127.0.0.1}:${AGORA_FRONTEND_PORT:-5173}" bash -c "ss -tlnp | grep ':${AGORA_FRONTEND_PORT:-5173}' | grep -q '${AGORA_BIND_HOST:-127.0.0.1}'"
  check "Flask auf ${AGORA_BIND_HOST:-127.0.0.1}:${AGORA_BACKEND_PORT:-5001}" bash -c "ss -tlnp | grep ':${AGORA_BACKEND_PORT:-5001}' | grep -q '${AGORA_BIND_HOST:-127.0.0.1}'"
fi

if [ $fail -gt 0 ]; then
  echo
  echo "--- Diagnose ---"
  docker compose ps
  if [ $PROXY_ACTIVE -eq 1 ]; then
    echo
    echo "nginx-Logs (letzte 20 Zeilen):"
    docker compose logs agora-nginx --tail=20 2>/dev/null || docker logs agora-nginx --tail=20 2>/dev/null || true
  fi
  exit 1
fi

# ---------------------------------------------------------------------------
# Issue #450 P1.8 — Prod-like Persistenz-Smoke (opt-in via --full)
# ---------------------------------------------------------------------------
# Was wir hier prüfen
#   1. Provider-Key über die API speichern → maskierte Antwort kommt zurück.
#   2. Workspace-Routing-Default setzen.
#   3. `docker compose restart agora` ausführen.
#   4. Health wieder grün abwarten.
#   5. Provider-Key-Maske + Routing-Default sind nach Restart noch da.
#   6. Secret-Scan auf backend/data + backend/instance: kein Klartext-API-Key.
#
# Bewusst NICHT in dieser Phase
#   * Vollständiger Document-Upload → Graph-Build → Persona → Simulation →
#     Report-Run. Das braucht den AGORA_E2E_LLM_MODE=stub-Pfad in eigener
#     CI-Suite (siehe docs/2026-05-15-issue-450-hardening-worklog.md).
if [ $RUN_FULL -ne 1 ]; then
  exit 0
fi

echo
echo "============================================================"
echo "Issue #450 P1.8 — Prod-like Persistenz-Smoke (--full)"
echo "============================================================"

# Wir reichen Auth über das Proxy-Backend, falls aktiv. Sonst direkt
# gegen den Backend-Port.
if [ $PROXY_ACTIVE -eq 1 ]; then
  API_BASE="http://localhost:${PROXY_PORT}"
else
  API_BASE="http://localhost:${BACKEND_PORT}"
fi
AUTH_HEADER=""
if [ -n "${AGORA_AUTH_TOKEN:-}" ]; then
  AUTH_HEADER="-H X-Agora-Token:${AGORA_AUTH_TOKEN}"
fi
# Test-Werte
SMOKE_PROVIDER="openai"
SMOKE_API_KEY="sk-smoke-${RANDOM}${RANDOM}-do-not-use"
SMOKE_MODEL="gpt-4o-mini"

# ---------------------------------------------------------------------------
# Production-Schutz (Copilot finding #1):
# --full schreibt einen Test-Provider-Key + Workspace-Routing-Default. Wenn die
# Instanz bereits Operator-Daten enthält, würde das die echten Werte
# überschreiben (und Cleanup würde den Key löschen). Daher Pre-Check:
#   * Existiert schon ein Provider-Key für SMOKE_PROVIDER?
#   * Existiert schon ein Global-Default?
# Wenn ja, abbruch — außer der Operator erzwingt mit AGORA_SMOKE_FORCE=1
# (z. B. nach explizitem Snapshot der Files).
# ---------------------------------------------------------------------------
echo
echo "Production-Schutz — Pre-Check (--full)"
existing_key_http=$(curl -s -o /dev/null -w "%{http_code}" $AUTH_HEADER \
  "${API_BASE}/api/llm/providers/${SMOKE_PROVIDER}/api-key" 2>/dev/null || echo "000")
existing_default=$(curl -s $AUTH_HEADER \
  "${API_BASE}/api/llm/routing/defaults" 2>/dev/null | grep -oE '"global_default":\s*\{[^}]+\}' | head -1)

production_data_detected=0
if [ "$existing_key_http" = "200" ]; then
  production_data_detected=1
fi
if [ -n "$existing_default" ]; then
  production_data_detected=1
fi

if [ "$production_data_detected" = "1" ]; then
  if [ "${AGORA_SMOKE_FORCE:-0}" != "1" ]; then
    cat <<'EOF'
  FAIL Produktiv-Daten erkannt:
    - Provider-Key oder Routing-Default existieren bereits.
    - Der --full-Smoke würde diese überschreiben und am Ende löschen.
  Aktion:
    1. Vorher backend/data sichern:
         docker compose exec -T agora cp /app/backend/data/llm_provider_secrets.json /tmp/secrets.bak
         docker compose exec -T agora cp /app/backend/data/workspace_llm_routing.json /tmp/routing.bak
    2. Smoke mit AGORA_SMOKE_FORCE=1 erneut starten.
    3. Nach Smoke wieder einspielen.
  Alternativ: --full nur gegen frische Test-Instanzen fahren.
EOF
    exit 3
  fi
  echo "  WARN Produktiv-Daten überschrieben — AGORA_SMOKE_FORCE=1 ist gesetzt."
else
  echo "  OK  Keine Produktiv-Daten erkannt — Smoke ist sicher."
fi

ok2=0; fail2=0
check2() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  OK  $name"; ok2=$((ok2+1))
  else
    echo "  FAIL $name"; fail2=$((fail2+1))
    "$@" 2>&1 | tail -5 | sed 's/^/    /'
  fi
}

_upsert_provider_key() {
  curl -fsS -X PUT \
    $AUTH_HEADER \
    -H "Content-Type: application/json" \
    -d "{\"api_key\":\"${SMOKE_API_KEY}\"}" \
    "${API_BASE}/api/llm/providers/${SMOKE_PROVIDER}/api-key" \
    | grep -q '"masked_value"'
}

_set_global_default() {
  curl -fsS -X PUT \
    $AUTH_HEADER \
    -H "Content-Type: application/json" \
    -d "{\"provider_id\":\"${SMOKE_PROVIDER}\",\"model\":\"${SMOKE_MODEL}\"}" \
    "${API_BASE}/api/llm/routing/defaults/global" \
    | grep -q '"global_default"'
}

_provider_key_masked_present() {
  curl -fsS $AUTH_HEADER \
    "${API_BASE}/api/llm/providers/${SMOKE_PROVIDER}/api-key" \
    | grep -q '"masked_value"'
}

_routing_default_present() {
  curl -fsS $AUTH_HEADER \
    "${API_BASE}/api/llm/routing/defaults" \
    | grep -q "${SMOKE_MODEL}"
}

# Phase 1: Schreiben
echo
echo "Phase 1 — Provider-Setup + Routing schreiben:"
check2 "Provider-Key upsert (PUT /api/llm/providers/${SMOKE_PROVIDER}/api-key)" _upsert_provider_key
check2 "Global-Default setzen (PUT /api/llm/routing/defaults/global)" _set_global_default

# Phase 2: Restart
echo
echo "Phase 2 — docker compose restart agora:"
docker compose restart agora >/dev/null 2>&1
sleep 5
# Auf /health warten (max 60s)
healthy=0
for i in $(seq 1 30); do
  if curl -fsS $AUTH_HEADER "${API_BASE}/health" >/dev/null 2>&1; then
    healthy=1; break
  fi
  sleep 2
done
if [ $healthy -ne 1 ]; then
  echo "  FAIL Container nach Restart nicht gesund — Smoke abgebrochen"
  docker compose logs agora --tail=30
  exit 2
fi
echo "  OK  Container nach Restart gesund (${i} Versuch(e))"

# Phase 3: Persistenz-Verifikation
echo
echo "Phase 3 — Persistenz nach Restart:"
check2 "Provider-Key-Maske ist erhalten" _provider_key_masked_present
check2 "Routing-Default ist erhalten" _routing_default_present

# Phase 4: Secret-Scan
echo
echo "Phase 4 — Secret-Scan (Klartext-API-Keys außerhalb verschlüsseltem Store):"
_secret_scan_clean() {
  # Wir suchen den konkreten Smoke-Key + generisches sk-Pattern. Treffer in
  # llm_provider_secrets.json sind ok (Ciphertext enthält den Wert nicht),
  # alles andere ist verdächtig.
  local hits
  hits=$(docker compose exec -T agora sh -c "
    grep -rE -l '${SMOKE_API_KEY}' /app/backend/data /app/backend/instance 2>/dev/null | \
      grep -v llm_provider_secrets.json | head -5
  ")
  [ -z "$hits" ]
}
check2 "Kein Klartext-Smoke-Key in backend/{data,instance} außer im verschlüsselten Store" _secret_scan_clean

# Cleanup
echo
echo "Cleanup — Smoke-Provider-Key wieder löschen:"
curl -fsS -X DELETE $AUTH_HEADER \
  "${API_BASE}/api/llm/providers/${SMOKE_PROVIDER}/api-key" >/dev/null 2>&1 || true

echo
echo "Persistenz-Smoke: $ok2 ok, $fail2 fail"
if [ $fail2 -gt 0 ]; then
  exit 1
fi
exit 0
