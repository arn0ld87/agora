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
# 2026-08-08: Das lokale Gate ist ein schneller Sanity-Check, kein CI-Ersatz.
# Die teuren Schritte (mypy, Backend-PR-Subset-Pytest, Frontend-Vitest-Suite)
# laufen per Default NICHT mehr lokal — CI fährt sie auf jedem PR ohnehin
# (ci.yml: mypy app, pytest --cov --cov-fail-under=60, bun run test:coverage).
# GATE_FULL=1 stellt das alte Vollverhalten wieder her:
#   GATE_FULL=1 bash scripts/pre-push-gate.sh backend
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

  if [ "${GATE_FULL:-0}" = "1" ]; then
    step "Backend: mypy app/ (GATE_FULL=1)"
    (cd backend && uv run mypy app) || fail "mypy"
  else
    warn "mypy uebersprungen (GATE_FULL=1 erzwingt ihn; CI fährt ihn auf jedem PR)"
  fi

  step "Backend: Pydantic-Contract-Tests"
  (cd backend && uv run pytest tests/contracts/ -x -q) || fail "contract tests"

  # 2026-08-03 (Issue #1055): Pre-Push-Backend-Tests (Sub-Set, kein Coverage).
  # Spiegel des ``Backend tests (PR subset, no coverage)``-Steps in
  # ``.github/workflows/ci.yml``. Lokal wie CI mit FLASK_DEBUG=false,
  # damit die Tests gegen das Produktionsverhalten laufen -- ein
  # Debug-only Sentinel-Leak (Issue #1058) bricht hier nicht.
  # Issue #1054 (offen, pre-existing) lässt test_oasis_preflight rot;
  # plus Drift in #1060, #1061, #1062, #1063, #1065.
  # #1064 Generate-Profiles-Endpoint (2 Tests).
  # #1059 (LLM-Client-Metriken-Tests) ist mit #1066 gefixt; die fünf
  # Tests dort sind aus dem Deselect raus. Deselect bis die übrigen
  # Fixes gemerged sind; Liste schrumpft weiter.
  # 2026-08-05 (Issue #1106): pytest-xdist parallelisiert den Subset-Lauf;
  # identische Testmenge (--deselect/--ignore unveraendert), Contract-Tests-
  # Step bleibt seriell. Gemessen auf M3/16GB: seriell 117s; `-n 4` mit
  # Warning-Capture 270s+ bzw. Shutdown-Hang (>1.6 Mio Warnings werden pro
  # Worker ueber die execnet-Pipe serialisiert), `-n 4 -p no:warnings` 33s.
  # `-p no:warnings` ist hier keine Abschwaechung: das Repo definiert keine
  # filterwarnings-Regeln (insb. kein `error`), Warnings sind im Smoke reine
  # Anzeige. `-n auto` (=8) bewusst nicht: acht App-Importe sprengen 16 GB.
  # Gezielte Warning-Filter bleiben Issue #1090.
  # 2026-08-08: nur noch unter GATE_FULL=1 — CI faehrt die volle Suite mit
  # Coverage-Gate auf jedem PR, lokal bleibt das Gate ein Sanity-Check.
  if [ "${GATE_FULL:-0}" = "1" ]; then
  step "Backend: tests (PR subset, no coverage, GATE_FULL=1)"
  (cd backend && FLASK_DEBUG=false uv run pytest tests/ \
      -n 4 -p no:warnings \
      --ignore=tests/contracts \
      --deselect tests/scripts/test_oasis_preflight.py::TestPreflightSkipSwitch::test_skip_env_skips_probe_and_warns \
      --deselect tests/services/test_oasis_voice_register.py::test_llm_valid_voice_register_lands_in_profile \
      --deselect tests/services/test_oasis_voice_register.py::test_llm_invalid_voice_register_fallback_neutral_de \
      --deselect tests/services/test_oasis_voice_register.py::test_llm_missing_voice_register_fallback_neutral_de \
      --deselect tests/test_quota_persistence.py::test_phase_generate_config_persists_quota_plan \
      --deselect tests/test_quota_persistence.py::test_phase_generate_config_omits_quota_plan_when_none \
      --deselect tests/services/test_bug_reproductions.py::test_repro_bug_b_oasis_profile_generator_thinking_tokens_parsing \
      --deselect tests/test_entity_propagation.py::test_expanded_entities_propagate_to_config_generator \
      --deselect tests/api/test_simulation_uses_request_model.py::test_generate_profiles_endpoint_falls_back_when_no_llm_model \
      --deselect tests/api/test_simulation_uses_request_model.py::test_generate_profiles_endpoint_passes_llm_model_to_generator \
      --deselect tests/test_nltk_import_guard.py::test_ingestion_entrypoint_can_parse \
      -q --no-cov -x) \
    || fail "backend tests"
  else
    warn "Backend-Test-Subset uebersprungen (GATE_FULL=1 erzwingt ihn; CI faehrt die volle Suite)"
  fi

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

  if [ "${GATE_FULL:-0}" = "1" ]; then
    step "Frontend: tests (GATE_FULL=1)"
    (cd frontend && bun run test) || fail "frontend tests"
  else
    warn "Frontend-Tests uebersprungen (GATE_FULL=1 erzwingt sie; CI faehrt test:coverage)"
  fi

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
