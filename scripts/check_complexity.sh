#!/usr/bin/env bash
# check_complexity.sh — Cyclomatic-Complexity-Gate (radon)
#
# Fail-Schwelle: Class D+ (cc >= 21). Klasse C (cc <= 20) wird geduldet.
# Begründung: PLAN.md schreibt "cc > 15" und "> C-Klasse". Da radon
# Class C als cc 11–20 definiert und Class D ab cc 21 beginnt, ist die
# präzise Umsetzung von "> Class C" durch die Schwelle cc >= 21 (Class D).
# Bestands-Hot-Spots sind in backend/radon-allowlist.txt eingetragen und
# werden durchgewunken, bis individuelle Refactor-Slices sie beseitigen.
#
# Verwendung (lokal):    bash scripts/check_complexity.sh
# CI:                    s. .github/workflows/contract-gates.yml::complexity-gate
# Neue D+-Funktion ok?   Eintrag in backend/radon-allowlist.txt + Slice-Kommentar
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ALLOWLIST="$REPO_ROOT/backend/radon-allowlist.txt"
RADON_OUT=$(mktemp)
FILTER_PY=$(mktemp -t complexity_filter.XXXXXX).py
trap 'rm -f "$RADON_OUT" "$FILTER_PY"' EXIT

cd "$REPO_ROOT/backend"
uv run radon cc -n D --no-assert app/ > "$RADON_OUT"

cat > "$FILTER_PY" << 'PYEOF'
import re
import sys
import pathlib

allow_path = pathlib.Path(sys.argv[1])
radon_out_path = pathlib.Path(sys.argv[2])

allow: set[str] = set()
if allow_path.exists():
    for raw_line in allow_path.read_text().splitlines():
        entry = raw_line.strip()
        if entry and not entry.startswith("#"):
            allow.add(entry)

current_file: str | None = None
violations: list[tuple[str, str]] = []

# radon output format:
#   app/some/file.py          <- file header (no leading whitespace)
#       F 123:0 func_name - D  <- entry (leading whitespace, type F/C/M)
file_re = re.compile(r"^([^\s].+\.py)\s*$")
entry_re = re.compile(r"^\s+[FCM]\s+\d+:\d+\s+(\S+)\s+-\s+([D-F])\s*$")

for raw in radon_out_path.read_text().splitlines():
    line = raw.rstrip()
    m_file = file_re.match(line)
    if m_file:
        current_file = m_file.group(1)
        continue
    m_entry = entry_re.match(line)
    if m_entry and current_file is not None:
        func_name = m_entry.group(1)
        klass = m_entry.group(2)
        key = f"{current_file}::{func_name}"
        if key not in allow:
            violations.append((key, klass))

if violations:
    print(
        "::error:: Neue High-Complexity-Funktionen (Cyclomatic Class D+) gefunden:",
        file=sys.stderr,
    )
    for key, klass in violations:
        print(f"  {klass}  {key}", file=sys.stderr)
    print(
        "\nWenn dies beabsichtigt ist, Zeile in backend/radon-allowlist.txt eintragen:",
        file=sys.stderr,
    )
    for key, _ in violations:
        print(f"  {key}", file=sys.stderr)
    print(
        "\nJeder neue Allow-List-Eintrag braucht eine Slice-Begruendung im Arbeitsprotokoll.",
        file=sys.stderr,
    )
    sys.exit(1)

print("OK: Keine neuen D/E/F-Klassen-Funktionen ausserhalb der Allow-List.")
PYEOF

python3 "$FILTER_PY" "$ALLOWLIST" "$RADON_OUT"
