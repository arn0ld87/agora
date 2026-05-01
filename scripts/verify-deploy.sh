#!/usr/bin/env bash
# Verifiziert dass die zuletzt committeten Fixes im Container live sind.
set -uo pipefail
cd "$(dirname "$0")/.."

ok=0; fail=0
check() {
  local name="$1"; shift
  if "$@" >/dev/null 2>&1; then
    echo "  ✅ $name"; ok=$((ok+1))
  else
    echo "  ❌ $name"; fail=$((fail+1))
  fi
}

echo "Container-Health:"
check "agora läuft" docker compose ps agora --status running -q
check "Backend /health" docker compose exec -T agora curl -fs http://localhost:5001/health

echo
echo "S1 (XSS-Fix):"
check "DOMPurify im node_modules" docker compose exec -T agora test -d frontend/node_modules/dompurify
check "markdown-Util importiert DOMPurify" docker compose exec -T agora grep -q "DOMPurify" frontend/src/utils/markdown.js

echo
echo "S2-pre (Schema-Fix):"
check "name→id Lookup im Service" \
  docker compose exec -T agora grep -q "post_author_name\|original_author_name\|target_user_name" backend/app/services/network_analytics.py

echo
echo "Diagnose-Run (3 letzte Sims):"
docker compose exec -T agora uv run --project backend \
  python backend/scripts/diagnose_metric_snapshot.py --limit 3 --no-write 2>&1 | tail -10

echo
echo "Result: $ok ok, $fail fail"
exit "$fail"
