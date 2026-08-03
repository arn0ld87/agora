#!/usr/bin/env bash
# scripts/check-pip-audit-hardstop.sh
#
# Fail-fast wenn nach dem pip-audit-Hardstop-Datum die --ignore-vuln-Liste
# noch non-empty ist. Hintergrund: ADR-0004 / ALE-20 hat den Hardstop auf
# 2026-09-28 gesetzt; danach MUSS die Liste leer sein (Code-Kommentar in
# .github/workflows/ci.yml, security-Job, pip-audit-Step).
#
# Usage:
#   PIP_AUDIT_HARDCUTOFF=2026-09-28 \
#     PIP_AUDIT_FLAGS="--ignore-vuln IDONOTEXIST" \
#     bash scripts/check-pip-audit-hardstop.sh
#
# Exit:
#   0 - Liste leer oder Datum noch nicht erreicht
#   2 - Hardstop verletzt: Datum >= Hardcutoff UND --ignore-vuln non-empty
#
# Env-Vars:
#   PIP_AUDIT_HARDCUTOFF  ISO-Datum (YYYY-MM-DD), default 2026-09-28
#   PIP_AUDIT_FLAGS       Flags, die in der CI an pip-audit durchgereicht werden

set -euo pipefail

HARDCUTOFF="${PIP_AUDIT_HARDCUTOFF:-2026-09-28}"
FLAGS="${PIP_AUDIT_FLAGS:-}"
TODAY="$(date -u +%F)"

# Datum-Vergleich als ISO-Strings (YYYY-MM-DD sortiert lexikografisch korrekt).
# Inklusiv: am Cutoff-Tag selbst muss die Liste bereits leer sein (AGENTS.md L76
# verbietet CVE-Ausnahmen ohne Hardstop; ein Tag ``< Hardcutoff`` wuerde das
# aushebeln — das letzte 24-Stunden-Fenster vor dem Hardstop waere unguelltig).
if [[ ! "$TODAY" >= "$HARDCUTOFF" ]]; then
  echo "OK: $TODAY ist vor oder am Hardcutoff $HARDCUTOFF — pip-audit --ignore-vuln ist erlaubt."
  exit 0
fi

# Datum ist nach Hardcutoff. Liste prüfen.
# ``grep -o`` zählt Vorkommen, ``grep -c`` zählt Treffer-Zeilen. Wir wollen
# Vorkommen (mehrere ``--ignore-vuln`` pro Zeile sind üblich). ``|| true``,
# damit leere Eingabe nicht ``set -e`` reißt.
IGNORE_COUNT="$(grep -o -- '--ignore-vuln' <<<"$FLAGS" 2>/dev/null | wc -l | tr -d ' ' || true)"
if [[ "$IGNORE_COUNT" -eq 0 ]]; then
  echo "OK: $TODAY ist nach Hardcutoff $HARDCUTOFF und --ignore-vuln-Liste ist leer."
  exit 0
fi

echo "::error::pip-audit --ignore-vuln-Liste ist non-empty nach Hardcutoff $HARDCUTOFF." >&2
echo "Heute: $TODAY" >&2
echo "Anzahl --ignore-vuln: $IGNORE_COUNT" >&2
echo "Refs: ADR-0004 / ALE-20. Liste muss bis Hardcutoff geleert werden," >&2
echo "andernfalls muss Hardcutoff per ADR-Update verschoben werden." >&2
exit 2
