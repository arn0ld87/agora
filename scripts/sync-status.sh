#!/usr/bin/env bash
set -euo pipefail

# sync-status.sh — Updates marker-delimited sections in docu/STATUS.md
# Replaces only the content between HTML-comment markers:
#   <!-- BEGIN_AUTOGEN_VERSIONS --> ... <!-- END_AUTOGEN_VERSIONS -->
#   <!-- BEGIN_AUTOGEN_TESTS -->    ... <!-- END_AUTOGEN_TESTS -->
# All manually maintained sections (Layer-Status, Coverage, Milestone,
# Aktualisierungs-Protokoll) are left untouched.
#
# Usage:
#   bash scripts/sync-status.sh           # update STATUS.md in-place
#   bash scripts/sync-status.sh --check   # drift-check only (exit 1 on drift)

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
STATUS_FILE="$REPO_ROOT/docu/STATUS.md"

CHECK_MODE=false
if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=true
fi

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
get_version_from_pyproject() {
  grep '^version' "$1" | head -1 | sed 's/^version = "\([^"]*\)".*/\1/'
}

get_version_from_json() {
  jq -r .version "$1" 2>/dev/null || echo "unknown"
}

# ---------------------------------------------------------------------------
# Collect values
# ---------------------------------------------------------------------------
BACKEND_VERSION=$(get_version_from_pyproject "$REPO_ROOT/backend/pyproject.toml")
FRONTEND_VERSION=$(get_version_from_json "$REPO_ROOT/frontend/package.json")
ROOT_VERSION=$(get_version_from_json "$REPO_ROOT/package.json")

BACKEND_TESTS="unknown"
if command -v uv &>/dev/null; then
  # Optional timeout: GNU coreutils auf Linux/CI, gtimeout auf macOS, sonst kein Wrapper.
  if command -v timeout &>/dev/null; then
    TIMEOUT_CMD=(timeout 180)
  elif command -v gtimeout &>/dev/null; then
    TIMEOUT_CMD=(gtimeout 180)
  else
    TIMEOUT_CMD=()
  fi
  COLLECT_TMP=$(mktemp)
  if ${TIMEOUT_CMD[@]+${TIMEOUT_CMD[@]}} bash -c "cd '$REPO_ROOT/backend' && uv run pytest --collect-only -q | tail -3" > "$COLLECT_TMP" 2>&1; then
    MATCH=$(grep -oE '[0-9]+ tests collected' "$COLLECT_TMP" | grep -oE '[0-9]+' | head -1 || true)
    if [[ -n "$MATCH" ]]; then
      BACKEND_TESTS="$MATCH"
    else
      echo "WARNING: pytest --collect-only ran but no count found" >&2
    fi
  else
    echo "WARNING: pytest --collect-only timed out or failed — keeping 'unknown'" >&2
  fi
  rm -f "$COLLECT_TMP"
fi

FRONTEND_SPEC_FILES=$(find "$REPO_ROOT/frontend/src" \( -name '*.spec.ts' -o -name '*.spec.js' \) 2>/dev/null | wc -l | tr -d ' ')

# ---------------------------------------------------------------------------
# Build replacement blocks (content between markers, without the marker lines)
# ---------------------------------------------------------------------------
VERSIONS_BLOCK="| Komponente | Pfad | Version |
|---|---|---|
| Backend | \`backend/pyproject.toml\` | $BACKEND_VERSION |
| Frontend | \`frontend/package.json\` | $FRONTEND_VERSION |
| Root | \`package.json\` | $ROOT_VERSION |"

TESTS_BLOCK="| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | $BACKEND_TESTS | \`cd backend && uv run pytest --collect-only -q\` |
| Frontend Spec-Files | $FRONTEND_SPEC_FILES | \`find frontend/src \\( -name '*.spec.ts' -o -name '*.spec.js' \\)\` |"

# ---------------------------------------------------------------------------
# replace_block: replaces content between BEGIN/END markers using Python3.
# Args: MARKER_NAME NEW_CONTENT FILE
# Exits with error if marker is missing.
# ---------------------------------------------------------------------------
replace_block() {
  local marker_name="$1"
  local new_content="$2"
  local file="$3"

  python3 - "$marker_name" "$new_content" "$file" <<'PYEOF'
import sys
import re
import pathlib

marker_name = sys.argv[1]
new_content = sys.argv[2]
file_path   = sys.argv[3]

text  = pathlib.Path(file_path).read_text(encoding="utf-8")
begin = f"<!-- BEGIN_AUTOGEN_{marker_name} -->"
end   = f"<!-- END_AUTOGEN_{marker_name} -->"

pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end), re.DOTALL)
if not pattern.search(text):
    sys.stderr.write(
        f"::error::Marker {begin} oder {end} fehlt in {file_path}\n"
    )
    sys.exit(1)

new_block = f"{begin}\n{new_content}\n{end}"
new_text  = pattern.sub(new_block, text)
pathlib.Path(file_path).write_text(new_text, encoding="utf-8")
PYEOF
}

# ---------------------------------------------------------------------------
# Apply to target (real file or tempfile for --check)
# ---------------------------------------------------------------------------
TARGET_FILE="$STATUS_FILE"
if [[ "$CHECK_MODE" == true ]]; then
  TARGET_FILE=$(mktemp)
  cp "$STATUS_FILE" "$TARGET_FILE"
fi

replace_block "VERSIONS" "$VERSIONS_BLOCK" "$TARGET_FILE"
replace_block "TESTS"    "$TESTS_BLOCK"    "$TARGET_FILE"

# ---------------------------------------------------------------------------
# --check: compare and report
# ---------------------------------------------------------------------------
if [[ "$CHECK_MODE" == true ]]; then
  if diff -q "$STATUS_FILE" "$TARGET_FILE" >/dev/null 2>&1; then
    echo "OK: docu/STATUS.md in sync" >&2
    rm -f "$TARGET_FILE"
    exit 0
  else
    echo "DRIFT: docu/STATUS.md weicht von autogenerated Inhalt ab" >&2
    echo "Diff (STATUS.md vs. generated):" >&2
    diff "$STATUS_FILE" "$TARGET_FILE" >&2 || true
    rm -f "$TARGET_FILE"
    exit 1
  fi
else
  echo "OK: $STATUS_FILE aktualisiert" >&2
  echo "Tipp: bash scripts/sync-status.sh --check zur Drift-Verifikation" >&2
fi
