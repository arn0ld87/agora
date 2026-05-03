#!/usr/bin/env bash
set -euo pipefail

# sync-status.sh — Regenerates docu/STATUS.md with current test counts and versions
# Usage: bash scripts/sync-status.sh [--check]
# --check: dry-run mode, compare with existing docu/STATUS.md, exit 1 if drift detected

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Parse arguments
CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=true
fi

# Helper: Extract version from pyproject.toml / package.json
get_version_from_pyproject() {
  local file=$1
  grep '^version' "$file" | head -1 | sed 's/^version = "\([^"]*\)".*/\1/'
}

get_version_from_json() {
  local file=$1
  jq -r .version "$file" 2>/dev/null || echo "unknown"
}

# Extract versions
BACKEND_VERSION=$(get_version_from_pyproject "$REPO_ROOT/backend/pyproject.toml")
FRONTEND_VERSION=$(get_version_from_json "$REPO_ROOT/frontend/package.json")
ROOT_VERSION=$(get_version_from_json "$REPO_ROOT/package.json")

# Get test counts
# Backend: use pytest --collect-only with timeout
BACKEND_TESTS="unknown"
if command -v uv &>/dev/null; then
  if timeout 180 bash -c "cd '$REPO_ROOT/backend' && uv run pytest --collect-only -q 2>/dev/null | tail -3" > /tmp/pytest_collect.tmp 2>&1; then
    BACKEND_TESTS_MATCH=$(grep -oE '[0-9]+ tests collected' /tmp/pytest_collect.tmp | grep -oE '[0-9]+' | head -1 || echo "")
    if [[ -n "$BACKEND_TESTS_MATCH" ]]; then
      BACKEND_TESTS="$BACKEND_TESTS_MATCH"
    else
      echo "WARNING: pytest --collect-only ran but no count found" >&2
    fi
  else
    echo "WARNING: pytest --collect-only timed out or failed — using unknown" >&2
  fi
  rm -f /tmp/pytest_collect.tmp
fi

# Frontend: count spec files (deterministic, no vitest dependency).
# Note: Each spec file contains multiple `describe`/`it` cases. The actual
# test-case count is roughly an order of magnitude higher (run `npx vitest list`
# in `frontend/` to materialize it). We report spec-files because it is
# stable, deterministic, and does not require `npm install`.
FRONTEND_SPEC_FILES=$(find "$REPO_ROOT/frontend/src" \( -name '*.spec.ts' -o -name '*.spec.js' \) 2>/dev/null | wc -l)

# Get status date
STATUS_DATE=$(date +%Y-%m-%d)

# Build the STATUS.md content
STATUS_CONTENT=$(cat <<EOF
# Agora — Status (Single Source of Truth)

Stand: $STATUS_DATE

**Aktualisiert via \`scripts/sync-status.sh\`.** README, CLAUDE.md und ROADMAP verweisen auf diese Datei — Versionsstände und Test-Counts werden nicht mehr inline kopiert.

## Versionen

| Komponente | Pfad | Version |
|---|---|---|
| Backend | \`backend/pyproject.toml\` | $BACKEND_VERSION |
| Frontend | \`frontend/package.json\` | $FRONTEND_VERSION |
| Root | \`package.json\` | $ROOT_VERSION |

## Tests

| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | $BACKEND_TESTS | \`cd backend && uv run pytest --collect-only -q\` |
| Frontend Spec-Files | $FRONTEND_SPEC_FILES | \`find frontend/src \\( -name '*.spec.ts' -o -name '*.spec.js' \\)\` |

_Hinweise: 2 Redis-Integrationstests skippen sauber ohne \`TEST_REDIS_URL\` und sind in der Backend-Summe enthalten (sie zählen als collected, werden aber zur Laufzeit übersprungen)._
_Die Frontend-Zeile zählt Dateien, nicht einzelne Test-Cases. Pro Spec-File laufen mehrere \`it\`-Blöcke; die exakte Test-Case-Anzahl liefert \`cd frontend && npx vitest list\`._

## Layer-Status (Übersicht)

Verbindliche Detailtabelle und Layer-Semantik: [\`CLAUDE.md\` § Architektur-Layer](../CLAUDE.md#architektur-layer-status).

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel | grün |
| 1 | Backend-Hardening | grün |
| 2 | DACH-Voice + Glossar v1 | grün |
| 3 | Reader-Honesty | grün |
| 4 | Frontend strict-Zod | grün |
| 5 | Eval/Baseline-Suite | grün |
| 6 | Frontend-TypeScript-Migration | grün |
| 7–8 | Graph/Runs/Persona-Review | teilweise |
| 9 | Prod-Deployment (Reverse-Proxy, gevent, SSE-Auth) | offen |
| 10 | Security Watchlist | dokumentiert |

## Aktuelles Milestone

**M9 — Prod-Hardening (Mai 2026, 23 Wochen).**

Detail: [\`PLAN.md\` § Milestone M9](../PLAN.md).

Aktive Slices: F5 Doku-Sync, F1 Reverse-Proxy, F2 Auth-Hardening, F3 Gunicorn-Gevent.

## Aktualisierungs-Protokoll

- $STATUS_DATE: Sub-Slice 44 — STATUS.md inaugural, Test-Counts und Versionsstände zentralisiert, Inline-Zahlen aus README/CLAUDE.md entfernt, ROADMAP auf v0.9.0+ / 2026-05-03 geheben.
EOF
)

# Write to temp location for --check mode
OUTPUT_FILE="$REPO_ROOT/docu/STATUS.md"
if [[ "$CHECK_MODE" == true ]]; then
  OUTPUT_FILE="/tmp/STATUS.md.tmp"
fi

echo "$STATUS_CONTENT" > "$OUTPUT_FILE"

# Verify idempotency in check mode
if [[ "$CHECK_MODE" == true ]]; then
  if diff -q "$REPO_ROOT/docu/STATUS.md" /tmp/STATUS.md.tmp > /dev/null 2>&1; then
    echo "OK: docu/STATUS.md in sync" >&2
    rm -f /tmp/STATUS.md.tmp
    exit 0
  else
    echo "DRIFT: docu/STATUS.md differs from generated content" >&2
    echo "Run again without --check to regenerate." >&2
    rm -f /tmp/STATUS.md.tmp
    exit 1
  fi
else
  echo "OK: $OUTPUT_FILE written" >&2
  echo "Run again with --check to verify no drift" >&2
fi
