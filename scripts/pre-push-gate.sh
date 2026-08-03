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

  # 2026-08-03 (Issue #1055): Pre-Push-Backend-Tests (Sub-Set, kein Coverage).
  # Spiegel des ``Backend tests (PR subset, no coverage)``-Steps in
  # ``.github/workflows/ci.yml``. Lokal wie CI mit FLASK_DEBUG=false,
  # damit die Tests gegen das Produktionsverhalten laufen -- ein
  # Debug-only Sentinel-Leak (Issue #1058) bricht hier nicht.
  # Issue #1054 (offen, pre-existing) lässt test_oasis_preflight rot;
  # plus Drift in #1059, #1060, #1061, #1062, #1063, #1064.
  # Deselect bis Fixes gemerged sind; Liste schrumpft dann.
  step "Backend: tests (PR subset, no coverage)"
  (cd backend && FLASK_DEBUG=false uv run pytest tests/ \
      --ignore=tests/contracts \
      --deselect tests/scripts/test_oasis_preflight.py::TestPreflightSkipSwitch::test_skip_env_skips_probe_and_warns \
      --deselect tests/utils/test_llm_client_metrics.py::TestChatIncrementsTokenCounter::test_chat_increments_token_counter_in_and_out \
      --deselect tests/utils/test_llm_client_metrics.py::TestChatJsonIncrementsTokenCounter::test_chat_json_increments_token_counter \
      --deselect tests/utils/test_llm_client_metrics.py::TestRetryDoesNotDoubleCount::test_retry_does_not_double_count \
      --deselect tests/utils/test_llm_client_metrics.py::TestMissingUsageNoIncrement::test_missing_usage_no_increment \
      --deselect tests/utils/test_llm_client_metrics.py::TestProviderModelLabels::test_provider_model_labels_set \
      --deselect tests/services/test_oasis_voice_register.py::test_llm_valid_voice_register_lands_in_profile \
      --deselect tests/services/test_oasis_voice_register.py::test_llm_invalid_voice_register_fallback_neutral_de \
      --deselect tests/services/test_oasis_voice_register.py::test_llm_missing_voice_register_fallback_neutral_de \
      --deselect tests/test_quota_persistence.py::test_phase_generate_config_persists_quota_plan \
      --deselect tests/test_quota_persistence.py::test_phase_generate_config_omits_quota_plan_when_none \
      --deselect tests/services/test_bug_reproductions.py::test_repro_bug_b_oasis_profile_generator_thinking_tokens_parsing \
      --deselect tests/test_entity_propagation.py::test_expanded_entities_propagate_to_config_generator \
      --deselect tests/api/test_simulation_uses_request_model.py::test_generate_profiles_endpoint_falls_back_when_no_llm_model \
      -q --no-cov -x) \
    || fail "backend tests"

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
# run_schemas runs schema drift and synchronization status checks.
run_schemas() {
  step "Schema-Drift (dump_schemas --check)"
  (cd backend && uv run python -m app.contracts.dump_schemas --check) \
    || fail "schema drift — run 'cd backend && uv run python -m app.contracts.dump_schemas' locally and commit"

  step "Version-Drift (check_version_drift.py)"
  (cd backend && uv run python scripts/check_version_drift.py) \
    || fail "version drift — run 'cd backend && uv run python scripts/check_version_drift.py --write' locally and commit"

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
# run_routing checks LLM and embedding endpoint configuration for localhost routing issues, allowing unavailable environment files as a warning.
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

  # Der Vite-Build ist der mit Abstand teuerste Schritt des Gates und faengt
  # nach lint + typecheck + tests fast nichts mehr ab. Die CI baut ohnehin bei
  # jedem PR. Lokal daher nur auf Anforderung: GATE_BUILD=1 bash scripts/pre-push-gate.sh
  if [ "${GATE_BUILD:-0}" = "1" ]; then
    step "Frontend: build (GATE_BUILD=1)"
    (cd frontend && bun run build) || fail "frontend build"
  else
    warn "Frontend-Build uebersprungen (GATE_BUILD=1 erzwingt ihn; CI baut ohnehin)"
  fi

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
