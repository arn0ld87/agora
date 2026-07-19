#!/usr/bin/env bash
# fix-llm-localhost-falle.sh — Kommentiert die Localhost-Falle in .env aus.
#
# Symptom: Agenten machen nichts, weil LLM_BASE_URL im Container auf localhost:11434
# zeigt (Container selbst, kein Ollama). docker-compose.yml warnt explizit vor
# dieser Falle — die .env-Werte gewinnen ueber den Compose-Default.
#
# Verhalten:
#   - Macht Backup unter .env.bak (einmalig; vorhandenes .env.bak wird ueberschrieben).
#   - Kommentiert Zeilen aus, deren Wert `localhost`, `127.0.0.1` oder `0.0.0.0`
#     in LLM_BASE_URL / OPENAI_API_BASE_URL / EMBEDDING_BASE_URL enthaelt.
#   - LLM_MODEL_NAME und andere Felder werden NICHT angetastet.
#   - Idempotent: bereits auskommentierte Zeilen bleiben unveraendert.
#
# Verwendung:  bash scripts/fix-llm-localhost-falle.sh
#
# Anschliessend: docker compose up -d agora (Container neu starten)
#                bash scripts/check_llm_endpoint_localhost.sh  (Verifikation)
#
# Exit-Codes:
#   0  alle problematischen Zeilen erfolgreich auskommentiert (oder keine vorhanden)
#   1  Fehler beim Edit (z. B. .env nicht schreibbar)
#   2  .env nicht gefunden

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE="$REPO_ROOT/.env"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'
RESET=$'\033[0m'

if [[ ! -f "$ENV_FILE" ]]; then
  echo "${RED}  ✗ .env nicht gefunden unter $ENV_FILE${RESET}" >&2
  exit 2
fi

if [[ ! -w "$ENV_FILE" ]]; then
  echo "${RED}  ✗ .env nicht schreibbar — Permission-Denial.${RESET}" >&2
  echo "    Loesung: 'chmod u+w $ENV_FILE' oder als Owner ausfuehren." >&2
  exit 1
fi

echo "${BLUE}==> Localhost-Falle in $ENV_FILE fixen${RESET}"

# DEBUG_FIX=1 scannt die .env und gibt fuer jede LLM_-Zeile Key/Value/Match-Status aus,
# OHNE die Datei zu aendern. Dient der Diagnose, warum der Helper NOOP sagt, obwohl
# der Lint die Localhost-Falle findet.
#
# Reihenfolge bewusst VOR dem Backup: ein Diagnose-Lauf fasst die .env nicht an,
# ein Backup waere ein toter Artefakt und wuerde ein bestehendes .env.bak
# ueberschreiben, ohne dass es je einen echten Edit gegeben hat.
if [[ "${DEBUG_FIX:-}" == "1" ]]; then
  DEBUG_PY=$(mktemp -t llm_debug.XXXXXX).py
  trap 'rm -f "$DEBUG_PY"' EXIT
  cat > "$DEBUG_PY" << 'PYEOF'
import re, sys, pathlib
env_path = pathlib.Path(sys.argv[1])
KV_RE = re.compile(r"^(\s*)([A-Z0-9_]+)(\s*)=(\s*)(.*?)(\s*)$")
LOOPBACK_RE = re.compile(r"(?:^|//)(localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?", re.IGNORECASE)
FIELDS = ("LLM_BASE_URL", "OPENAI_API_BASE_URL", "EMBEDDING_BASE_URL")
content = env_path.read_text()
print(f"=== DEBUG-FIX: scanning {env_path}", file=sys.stderr)
print(f"  file size: {len(content)} bytes, {content.count(chr(10))} newlines", file=sys.stderr)
for i, raw in enumerate(content.splitlines(), 1):
    line = raw.rstrip()
    if not line.strip():
        continue
    if line.lstrip().startswith("#"):
        continue
    if not any(line.startswith(k) for k in FIELDS):
        continue
    m = KV_RE.match(line)
    if not m:
        print(f"  L{i}: NO-KV-MATCH raw={line!r}", file=sys.stderr)
        continue
    key = m.group(2)
    value = m.group(5).strip().strip('"').strip("'")
    matched = LOOPBACK_RE.search(value)
    print(f"  L{i}: key={key!r} value={value!r} loopback={bool(matched)}", file=sys.stderr)
print("=== END DEBUG-FIX ===", file=sys.stderr)
PYEOF
  python3 "$DEBUG_PY" "$ENV_FILE" >&2
  echo "${YELLOW}  (DEBUG_FIX=1: keine Aenderungen an .env, kein Backup)${RESET}"
  exit 0
fi

# Backup idempotent — nur anlegen, wenn .env.bak noch nicht existiert.
# Sonst wuerde jeder weitere Lauf das vorherige Backup ueberschreiben
# und die cp-Recovery-Schnittstelle weiter unten verliert den
# Pre-Fix-Zustand.
BACKUP="$ENV_FILE.bak"
if [[ ! -f "$BACKUP" ]]; then
  cp "$ENV_FILE" "$BACKUP"
  echo "${GREEN}  ✓ Backup unter $BACKUP${RESET}"
else
  echo "${YELLOW}  ✓ Backup existiert bereits unter $BACKUP (nicht ueberschrieben)${RESET}"
fi

FILTER_PY=$(mktemp -t llm_localhost_fix.XXXXXX).py
trap 'rm -f "$FILTER_PY"' EXIT

cat > "$FILTER_PY" << 'PYEOF'
"""Kommentiert Localhost-Falle-Zeilen in .env aus.

Idempotent: bereits auskommentierte Zeilen werden nicht doppelt auskommentiert.
"""
import re
import sys
import pathlib

env_path = pathlib.Path(sys.argv[1])

FIELDS = ("LLM_BASE_URL", "OPENAI_API_BASE_URL", "EMBEDDING_BASE_URL")
LOOPBACK_RE = re.compile(r"(?:^|//)(localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?", re.IGNORECASE)
KV_RE = re.compile(r"^(\s*)([A-Z0-9_]+)(\s*)=(\s*)(.*?)(\s*)$")

lines = env_path.read_text().splitlines()
out: list[str] = []
fixed: list[tuple[str, str]] = []

for line in lines:
    if not line.strip() or line.lstrip().startswith("#"):
        out.append(line)
        continue
    m = KV_RE.match(line)
    if not m:
        out.append(line)
        continue
    # Direkte m.group()-Zugriffe statt m.groups()-Destructuring — das `=` in der
    # Regex ist literal (nicht captured), daher liefert m.groups() nur 6 Werte,
    # und ein Destructuring mit "eq" als Variable verschiebt alles um 1.
    key = m.group(2)
    value = m.group(5).strip().strip('"').strip("'")
    if key not in FIELDS:
        out.append(line)
        continue
    if not LOOPBACK_RE.search(value):
        out.append(line)
        continue
    # Service-Discovery-Ausnahme: redis://redis:6379 etc. nicht antasten.
    host_match = re.search(r"://([^/]+)", value)
    host = host_match.group(1).split(":")[0] if host_match else value.split("/")[0]
    if re.match(r"^(redis|neo4j|ollama|mongo|postgres|mysql)(:[0-9]+)?(/.*)?$", host):
        out.append(line)
        continue
    # Auskommentieren — exakte Original-Form erhalten (kein Whitespace-Change)
    fixed.append((key, value))
    out.append(f"# {line.lstrip()}  # auskommentiert via fix-llm-localhost-falle.sh (Localhost-Falle)")

if fixed:
    env_path.write_text("\n".join(out) + "\n")
    print("FIXED", file=sys.stderr)
    for key, value in fixed:
        print(f"  - {key}={value}", file=sys.stderr)
else:
    print("NOOP", file=sys.stderr)
    print("  keine problematischen Zeilen gefunden", file=sys.stderr)
PYEOF

set +e
python3 "$FILTER_PY" "$ENV_FILE" 2>&1
RC=$?
set -e

if [[ $RC -ne 0 ]]; then
  echo "${RED}  ✗ Edit fehlgeschlagen (RC=$RC)${RESET}" >&2
  echo "    Backup wiederherstellen mit: cp $BACKUP $ENV_FILE" >&2
  exit 1
fi

echo
echo "${GREEN}  ✓ Fix angewendet${RESET}"
echo
echo "${YELLOW}  -> Naechste Schritte:${RESET}"
echo "     1) Container neu starten:  docker compose up -d agora"
echo "     2) Verifikation:           bash scripts/check_llm_endpoint_localhost.sh"
echo "     3) Loop-Check:             docker logs agora --since 30s 2>&1 | grep -c 'Connection error'"
echo
echo "${YELLOW}  Falls etwas schief geht: cp $BACKUP $ENV_FILE${RESET}"
