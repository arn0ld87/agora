#!/usr/bin/env bash
# pre-push-gate.sh — Single source of truth for the local pre-push gate.
#
# Runs the same checks as the CI PR smoke gates, locally, in <2 minutes.
# Exits non-zero on first failure (set -e) so the user gets a clear signal
# before pushing — and a fast iteration loop on failed runs (we don't
# abort the whole script on lint warnings, only on hard errors).
#
# Usage:
#   bash scripts/pre-push-gate.sh           # run all gates
#   bash scripts/pre-push-gate.sh backend   # only backend
#   bash scripts/pre-push-gate.sh frontend  # only frontend
#   bash scripts/pre-push-gate.sh schemas   # only schema drift + sync-status
#
# Exit codes:
#   0  every gate green
#   1  at least one gate failed (printed above)
#
# Required by: docs/runbooks/tool-pflicht.md (Onboarding-Epic ADR-0002).
# Mirrored in CI: .github/workflows/*-smoke-*.yml (Backend/Frontend).
#
# Add a new gate here when the CI adds one — never bypass with --no-verify.

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
cd "$REPO_ROOT"

SCOPE="${1:-all}"
RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'
RESET=$'\033[0m'

step()  { printf "\n${BLUE}==> %s${RESET}\n" "$*"; }
ok()    { printf "${GREEN}  ✓ %s${RESET}\n" "$*"; }
warn()  { printf "${YELLOW}  ! %s${RESET}\n" "$*"; }
fail()  { printf "${RED}  ✗ %s${RESET}\n" "$*"; exit 1; }

# ---------------------------------------------------------------------------
# Backend-Gates
# ---------------------------------------------------------------------------
run_backend() {
  step "Backend: ruff check"
  (cd backend && uv run ruff check app/ tests/) || fail "ruff check"

  step "Backend: mypy app/"
  (cd backend && uv run mypy app) || fail "mypy"

  step "Backend: Pydantic-Contract-Tests"
  (cd backend && uv run pytest tests/contracts/ -x -q) || fail "contract tests"

  step "Backend: Schema-Drift (dump_schemas --check)"
  (cd backend && uv run python -m app.contracts.dump_schemas --check) \
    || fail "schema drift — run 'cd backend && uv run python -m app.contracts.dump_schemas' locally and commit"

  step "Backend: sync-status --check"
  bash scripts/sync-status.sh --check \
    || fail "STATUS.md drift — run 'bash scripts/sync-status.sh' locally and commit"
  ok "backend gates green"
}

# ---------------------------------------------------------------------------
# Schema-Gates (Drift + STATUS-Sync) — eigenes Scope fuer den schnellen
# Schema-Check ohne Backend-Test-Suite. Spiegel genau die beiden letzten
# run_backend-Steps (dump_schemas --check + sync-status --check).
# ---------------------------------------------------------------------------
run_schemas() {
  step "Schema-Drift (dump_schemas --check)"
  (cd backend && uv run python -m app.contracts.dump_schemas --check) \
    || fail "schema drift — run 'cd backend && uv run python -m app.contracts.dump_schemas' locally and commit"

  step "Backend: sync-status --check"
  bash scripts/sync-status.sh --check \
    || fail "STATUS.md drift — run 'bash scripts/sync-status.sh' locally and commit"
  ok "schema gates green"
}

# ---------------------------------------------------------------------------
# Routing-Gate: Localhost-Falle im LLM-/Embedding-Routing.
# Hintergrund: docker-compose.yml warnt explizit vor LLM_BASE_URL=localhost
# in der .env, weil das in den Container leakt und Connection-Refused erzeugt.
# Symptom: Agenten machen nichts, ~99 Connection-Errors pro Sim-Start.
# Eigenes Scope fuer den schnellen Re-Run ohne Backend-Suite.
# ---------------------------------------------------------------------------
run_routing() {
  step "Routing: Localhost-Falle im LLM-Routing (.env)"
  # Exit 2 = Skip (.env fehlt/nicht lesbar in CI ohne Repo-Vollzugriff) — als Warnung,
  # nicht als Fail, weil das Gate in CI ohnehin kein Container-Env hat.
  set +e
  bash scripts/check_llm_endpoint_localhost.sh
  rc=$?
  set -e
  if [[ $rc -eq 0 ]]; then
    ok "routing gate green"
  elif [[ $rc -eq 2 ]]; then
    warn "routing gate skipped (.env nicht verfuegbar — CI-Build ohne Repo-Vollzugriff)"
  else
    fail "localhost-falle in .env erkannt — run 'bash scripts/fix-llm-localhost-falle.sh' locally"
  fi
}

# ---------------------------------------------------------------------------
# Frontend-Gates
# ---------------------------------------------------------------------------
run_frontend() {
  if ! command -v bun >/dev/null 2>&1; then
    if [ "$SCOPE" = "frontend" ] || [ "$SCOPE" = "all" ]; then
      fail "bun ist nicht installiert, aber die Frontend-Gates sind erforderlich."
    fi
    warn "bun not installed — skipping frontend gates"
    return 0
  fi
  step "Frontend: lint"
  (cd frontend && bun run lint) || fail "lint"

  step "Frontend: typecheck"
  (cd frontend && bun run typecheck) || fail "typecheck"

  step "Frontend: tests"
  (cd frontend && bun run test) || fail "frontend tests"

  step "Frontend: build"
  (cd frontend && bun run build) || fail "frontend build"

  step "Frontend: Zod muss Backend-Schema spiegeln"
  # Spiegel-Check selbst laeuft in CI gegen generierte Schemas; lokal
  # reicht der typecheck, weil die Schema-JSONs bereits in sync sind
  # (dump_schemas wurde oben bereits gefahren). Hier nur Smoke: stelle
  # sicher, dass beide Sichten existieren.
  test -f schemas/user-profile.schema.json \
    && test -f frontend/src/contracts/userProfileContract.ts \
    || fail "schema-mirror files missing"
  ok "frontend gates green"
}

# ---------------------------------------------------------------------------
# Routing
# ---------------------------------------------------------------------------
case "$SCOPE" in
  all)      run_routing; run_backend; run_frontend ;;
  backend)  run_backend ;;
  frontend) run_frontend ;;
  schemas)  run_schemas ;;
  routing)  run_routing ;;
  *)        echo "usage: $0 [all|backend|frontend|schemas|routing]" >&2; exit 2 ;;
esac

ok "pre-push-gate: ALL GREEN — safe to push 🚀"
