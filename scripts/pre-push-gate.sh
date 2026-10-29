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
# laufen per Default NICHT mehr lokal — die Required-PR-Smoke-Gates fahren sie
# auf jedem PR (Backend: mypy app + Test-Subset ohne Coverage; Frontend:
# bun run test + vite build); die vollen Coverage-Gates laufen label-gated
# bzw. außerhalb von PRs (Jobs "Backend tests + lint" / "Frontend build + lint").
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
  (cd backend && uv run ruff check .) || fail "ruff check"

  step "Backend: Komplexitäts-Gate (radon, MAI-17)"
  # Spiegel des CI-Jobs "Komplexitaets-Gate (radon)" im contract-gates-Workflow.
  # Blockiert neue Cyclomatic-Complexity-Hotspots (rank D+) lokal, bevor sie
  # erst auf push:main auffallen (#1213). Bestand steht in radon-allowlist.txt.
  (cd backend && uv run python scripts/check_complexity.py) \
    || fail "complexity gate — neue D+-Hotspots; siehe backend/radon-allowlist.txt"

  step "Backend: Typ-Schuld-Gate (mypy, Issue #1495)"
  # Spiegel des CI-Steps "Typ-Schuld-Gate (Issue #1495)" in ci.yml.
  # Blockiert neue mypy-Fehler in den Bereichen, die pyproject.toml per
  # ignore_errors abschaltet. Bestand steht in mypy-debt-baseline.txt.
  (cd backend && uv run python scripts/check_mypy_debt.py) \
    || fail "mypy debt gate — neue Typfehler; siehe backend/mypy-debt-baseline.txt"

  # Issue #1671: Ratchet und Schönungs-Check gegen v0.9.6 (Spiegel des
  # backend-pr-gate). Braucht den Tag lokal und ein Git-Repo; ein rsync-Spiegel
  # ohne .git (z. B. remote-backend.sh) ueberspringt mit Warnung, CI prueft.
  if git rev-parse --git-dir >/dev/null 2>&1; then
    step "Backend: Coverage-Ratchet und Schönungs-Check (Issue #1671)"
    (cd backend && uv run python scripts/check_coverage.py --integrity) \
      || fail "coverage integrity — Scope/Schwellen gegenueber v0.9.6 geschoent; siehe backend/coverage-baseline.json"
  else
    warn "Coverage-Ratchet uebersprungen (kein Git-Repo; CI faehrt ihn auf jedem PR)"
  fi

  if [ "${GATE_FULL:-0}" = "1" ]; then
    step "Backend: mypy app/ (GATE_FULL=1)"
    (cd backend && uv run mypy app) || fail "mypy"
  else
    warn "mypy uebersprungen (GATE_FULL=1 erzwingt ihn; CI fährt ihn auf jedem PR)"
  fi

  step "Backend: Pydantic-Contract-Tests"
  (cd backend && uv run pytest tests/contracts/ -n 4 --dist loadfile -x -q) || fail "contract tests"

  # 2026-08-03 (Issue #1055): Pre-Push-Backend-Tests (Sub-Set, kein Coverage).
  # Spiegel des ``Backend tests (PR subset, no coverage)``-Steps in
  # ``.github/workflows/ci.yml``.
  # 2026-08-05 (Issue #1106): pytest-xdist parallelisiert den Subset-Lauf;
  # Contract-Tests-Step bleibt seriell.
  # 2026-08-08: nur noch unter GATE_FULL=1 — CI faehrt die volle Suite mit
  # Coverage-Gate auf jedem PR, lokal bleibt das Gate ein Sanity-Check.
  # 2026-10-29: PR-Test-Splitting via select_pr_tests.py --ignore-contracts.
  if [ "${GATE_FULL:-0}" = "1" ]; then
    step "Backend: tests (PR subset, no coverage, GATE_FULL=1)"
    (cd backend && {
      read -r -a TEST_TARGETS <<< "$(uv run python scripts/select_pr_tests.py --ignore-contracts)"
      FLASK_DEBUG=false uv run pytest "${TEST_TARGETS[@]}" \
        -n 4 --dist loadfile -p no:warnings \
        -q --no-cov -x
    }) || fail "backend tests"
  else
    warn "Backend-Test-Subset uebersprungen (GATE_FULL=1 erzwingt ihn; CI faehrt die volle Suite)"
  fi

  step "Backend: Schema-Drift (dump_schemas --check)"
  (cd backend && uv run python -m app.contracts.dump_schemas --check) \
    || fail "schema drift — run 'cd backend && uv run python -m app.contracts.dump_schemas' locally and commit"

  step "Backend: sync-status --check (--skip-counts)"
  # --skip-counts: Test-Zaehler werden nicht mehr pro PR verifiziert/committet,
  # sondern nur in dedizierten Refresh-Laeufen — verhindert, dass parallele
  # PRs auf denselben STATUS-Zeilen kollidieren (Merge-Friction 2026-08-08).
  bash scripts/sync-status.sh --check --skip-counts \
    || fail "STATUS.md drift — run 'bash scripts/sync-status.sh' locally and commit"
  ok "backend gates green"
}

# ---------------------------------------------------------------------------
# Leak-Gate: PandaOS pflegt lokal einen managed Block in AGENTS.md
# (Codex-Session-Anweisungen mit maschinenspezifischen Hosts und Pfaden).
# PR #1539 hat ihn versehentlich committet. Das Gate prueft den Index, nicht
# die Arbeitskopie, und kostet nur einen `git grep` — deshalb in jedem Scope.
run_leak() {
  step "Leak: kein PandaOS-managed-Block in versionierten Dateien"
  bash scripts/check_pandaos_managed_leak.sh \
    || fail "PandaOS-Block im Index — siehe docs/runbooks/pre-push-gate.md (Gate 14)"
  ok "leak gate green"
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

  step "Backend: sync-status --check (--skip-counts)"
  bash scripts/sync-status.sh --check --skip-counts \
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
  all)      run_leak; run_routing; run_backend; run_frontend ;;
  backend)  run_leak; run_backend ;;
  frontend) run_leak; run_frontend ;;
  schemas)  run_leak; run_schemas ;;
  routing)  run_leak; run_routing ;;
  *)        echo "usage: $0 [all|backend|frontend|schemas|routing]" >&2; exit 2 ;;
esac

ok "pre-push-gate: ALL GREEN — safe to push 🚀"
