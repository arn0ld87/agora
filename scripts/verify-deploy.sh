#!/usr/bin/env bash
# Verifiziert dass die zuletzt committeten Fixes im Container live sind.
# Sub-Slice 45: Auto-Detect Proxy-Stack, neue Probes gegen :80/healthz, /health, /.
set -uo pipefail
cd "$(dirname "$0")/.."

# Port-Konfiguration (ueberschreibbar via ENV)
PROXY_PORT="${AGORA_PROXY_PORT:-80}"
BACKEND_PORT="${AGORA_BACKEND_PORT:-5001}"

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
  cid="$(docker compose ps -q "$service" 2>/dev/null || true)"

  [ -n "$cid" ] || return 1
  [ "$(docker inspect -f '{{.State.Running}}' "$cid" 2>/dev/null)" = "true" ]
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

exit 0
