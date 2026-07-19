#!/usr/bin/env bash
# check_llm_endpoint_localhost.sh — Gate gegen die Localhost-Falle im LLM-Routing.
#
# Hintergrund (siehe docker-compose.yml environment-Block, Warnung "localhost-Falle"):
# Das Compose-File setzt `LLM_BASE_URL=${LLM_BASE_URL:-http://host.docker.internal:11434/v1}`.
# Wenn die `.env` `LLM_BASE_URL=http://localhost:11434/v1` (oder 127.0.0.1) liefert,
# ueberschreibt das den Default. Im Container ist `localhost` aber der Container selbst,
# nicht der Mac/Linux-Host — Ollama laeuft dort nicht. Folge: Connection refused auf
# 11434, alle LLM-Calls (Chat, Persona-Generation) scheitern, Agenten bleiben stumm.
#
# Verhalten:
#   - Prueft LLM_BASE_URL, OPENAI_API_BASE_URL, EMBEDDING_BASE_URL in .env (Repo-Root).
#   - Schlacht faellt bei `localhost`, `127.0.0.1`, oder `0.0.0.0` in der URL.
#   - Ausnahmen: Service-Discovery (`redis:`, `neo4j:`, `ollama:`, `mongo:` als Host).
#   - `--diagnose`: zeigt die kaputten Zeilen + Fix-Vorschlag.
#
# Verwendung (lokal):  bash scripts/check_llm_endpoint_localhost.sh [--diagnose]
# Verwendung (Gate):   in scripts/pre-push-gate.sh eingebunden, Scope `routing`.
#
# Exit-Codes:
#   0  green — keine Localhost-Falle
#   1  red   — Localhost-Falle erkannt
#   2  skip  — .env nicht vorhanden oder nicht lesbar (CI ohne Repo-Vollzugriff)

set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)
ENV_FILE="$REPO_ROOT/.env"

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[0;33m'
BLUE=$'\033[0;34m'
RESET=$'\033[0m'

DIAGNOSE=false
if [[ "${1:-}" == "--diagnose" ]]; then
  DIAGNOSE=true
fi

if [[ ! -f "$ENV_FILE" ]]; then
  if $DIAGNOSE; then
    echo "${YELLOW}  ! .env nicht gefunden unter $ENV_FILE — Gate nicht ausfuehrbar${RESET}"
    echo "    Im CI ohne Repo-Vollzugriff ist das erwartet."
  fi
  exit 2
fi

if [[ ! -r "$ENV_FILE" ]]; then
  echo "::error:: .env unter $ENV_FILE nicht lesbar (Permission-Denial). Gate nicht ausfuehrbar." >&2
  exit 2
fi

# Felder, die nicht auf Loopback zeigen duerfen (ausser Service-Discovery).
FIELDS=("LLM_BASE_URL" "OPENAI_API_BASE_URL" "EMBEDDING_BASE_URL")
# Diese Host-Pattern sind explizit erlaubt (Compose-internes Service-Discovery).
SERVICE_HOST_PATTERN='^(redis|neo4j|ollama|mongo|postgres|mysql)(:[0-9]+)?(/.*)?$'

FILTER_PY=$(mktemp -t llm_endpoint_filter.XXXXXX).py
trap 'rm -f "$FILTER_PY"' EXIT

cat > "$FILTER_PY" << 'PYEOF'
"""Prueft .env auf Localhost-Falle im LLM-Routing.

Robuster als awk/sed: unterstuetzt beliebige Whitespace-Varianten und ignoriert
bereits auskommentierte Zeilen.
"""
import re
import sys
import pathlib

env_path = pathlib.Path(sys.argv[1])
fields = sys.argv[2].split(",")
service_host_pattern = re.compile(sys.argv[3])

# local-loopback hosts, die in der URL stehen duerfen => fallen unter die Falle.
LOOPBACK_RE = re.compile(r"(?:^|//)(localhost|127\.0\.0\.1|0\.0\.0\.0)(?::\d+)?", re.IGNORECASE)

# Zuordnung key=value (entfernt whitespace und optionale Anfuehrungszeichen)
KV_RE = re.compile(r"^\s*([A-Z0-9_]+)\s*=\s*(.*?)\s*$")

violations: list[tuple[str, str, str]] = []
seen_keys: set[str] = set()

for raw_line in env_path.read_text().splitlines():
    line = raw_line.rstrip()
    if not line or line.lstrip().startswith("#"):
        continue
    m = KV_RE.match(line)
    if not m:
        continue
    key, value = m.group(1), m.group(2).strip().strip('"').strip("'")
    if key in fields:
        seen_keys.add(key)
        if not LOOPBACK_RE.search(value):
            continue
        # Service-Discovery-Ausnahme: redis://redis:6379, bolt://neo4j:7687, etc.
        # Heuristik: nach '://' darf der Host ein Service-Name sein.
        host_match = re.search(r"://([^/]+)", value)
        host = host_match.group(1).split(":")[0] if host_match else value.split("/")[0]
        if service_host_pattern.match(host):
            continue
        violations.append((key, value, line))

# Zusatz-Smoke: Wenn ein Feld mehrfach definiert ist, ist das ein Smell (auch wenn
# keiner localhost ist). Wir markieren das nur, wenn der zweite Eintrag lokal ist.
duplicate_smell: list[tuple[str, int]] = []
counts: dict[str, int] = {}
for raw_line in env_path.read_text().splitlines():
    m = KV_RE.match(raw_line)
    if not m:
        continue
    key = m.group(1)
    if key in fields:
        counts[key] = counts.get(key, 0) + 1
for key, n in counts.items():
    if n > 1:
        duplicate_smell.append((key, n))

if violations:
    print("::error:: Localhost-Falle in LLM-Routing erkannt:", file=sys.stderr)
    for key, value, original in violations:
        print(f"  {key}={value}", file=sys.stderr)
    print("", file=sys.stderr)
    print("Fix: in .env die entsprechenden Zeilen auskommentieren,", file=sys.stderr)
    print("damit der Compose-Default (host.docker.internal:11434) greift.", file=sys.stderr)
    print("Helper: bash scripts/fix-llm-localhost-falle.sh", file=sys.stderr)
    print("", file=sys.stderr)
    print("Hintergrund: docker-compose.yml warnt explizit vor dieser Falle.", file=sys.stderr)
    sys.exit(1)

if duplicate_smell:
    print(
        "::warning:: Mehrfach-Definitionen in .env fuer LLM-Routing-Felder erkannt:",
        file=sys.stderr,
    )
    for key, n in duplicate_smell:
        print(f"  {key}: {n}x definiert (Smell — nur die letzte gewinnt)", file=sys.stderr)
    print(
        "Empfehlung: in .env nur eine Definition pro Feld lassen. Sonst droht",
        file=sys.stderr,
    )
    print(
        "Reihenfolgen-Drift bei spaeteren Edits.",
        file=sys.stderr,
    )

print("OK: Localhost-Falle im LLM-Routing nicht erkannt.")
sys.exit(0)
PYEOF

if $DIAGNOSE; then
  echo "${BLUE}==> Localhost-Falle-Diagnose fuer $ENV_FILE${RESET}"
fi

python3 "$FILTER_PY" "$ENV_FILE" "$(IFS=,; echo "${FIELDS[*]}")" "$SERVICE_HOST_PATTERN"
RC=$?

if [[ $RC -eq 0 ]]; then
  if $DIAGNOSE; then
    echo "${GREEN}  ✓ OK — keine Localhost-Falle${RESET}"
  fi
  exit 0
fi

if [[ $RC -eq 1 ]]; then
  if $DIAGNOSE; then
    echo
    echo "${YELLOW}  -> Fix-Vorschlag (manuell oder via Helper):${RESET}"
    echo "     bash scripts/fix-llm-localhost-falle.sh"
    echo "     docker compose up -d agora"
  fi
  exit 1
fi

# RC=2 = skip (env nicht da / nicht lesbar) — pre-push behandelt das als warn, nicht fail
exit $RC
