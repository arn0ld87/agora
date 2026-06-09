#!/usr/bin/env bash
# install.sh — Ein-Befehl-Installation für Agora
# Verwendung:
#   ./install.sh            Host-Dev-Modus (bun + uv, ohne Docker)
#   ./install.sh --docker   Docker-Compose-Modus (Neo4j + Redis inklusive)
#   ./install.sh --check    Lint + Tests laufen lassen
set -euo pipefail

# ---------------------------------------------------------------------------
# Farben / Ausgabe
# ---------------------------------------------------------------------------
RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; BOLD='\033[1m'; RESET='\033[0m'
info()    { printf "${BOLD}[agora]${RESET} %s\n" "$*"; }
success() { printf "${GREEN}[agora]${RESET} %s\n" "$*"; }
warn()    { printf "${YELLOW}[agora] WARN:${RESET} %s\n" "$*"; }
die()     { printf "${RED}[agora] FEHLER:${RESET} %s\n" "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
# Hilfsfunktion: Versionsnummer aus String extrahieren (major.minor)
# ---------------------------------------------------------------------------
semver_major() { echo "$1" | grep -oE '[0-9]+' | head -1; }
semver_minor() { echo "$1" | grep -oE '[0-9]+' | sed -n '2p'; }

# ---------------------------------------------------------------------------
# Argument parsen
# ---------------------------------------------------------------------------
MODE="host"
for arg in "$@"; do
  case "$arg" in
    --docker) MODE="docker" ;;
    --check)  MODE="check"  ;;
    -h|--help)
      echo "Verwendung: $0 [--docker | --check]"
      echo "  (kein Flag)  Host-Dev-Modus: bun + uv, Neo4j/Redis extern erforderlich"
      echo "  --docker     Docker-Compose-Modus: Neo4j + Redis werden mitgestartet"
      echo "  --check      Lint + Tests (bun run check)"
      exit 0
      ;;
    *) die "Unbekanntes Argument: $arg  (--help für Hilfe)" ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---------------------------------------------------------------------------
# Voraussetzungen prüfen
# ---------------------------------------------------------------------------
info "Prüfe Voraussetzungen …"

# --- bun >= 1.3 ---
if ! command -v bun &>/dev/null; then
  die "bun ist nicht installiert.\n  → https://bun.sh  (curl -fsSL https://bun.sh/install | bash)"
fi
BUN_VER=$(bun --version 2>/dev/null)
BUN_MAJOR=$(semver_major "$BUN_VER")
BUN_MINOR=$(semver_minor "$BUN_VER")
if [[ "$BUN_MAJOR" -lt 1 ]] || { [[ "$BUN_MAJOR" -eq 1 ]] && [[ "${BUN_MINOR:-0}" -lt 3 ]]; }; then
  die "bun $BUN_VER ist zu alt — benötigt >= 1.3.\n  → bun upgrade"
fi
success "bun $BUN_VER"

# --- node >= 20 ---
if ! command -v node &>/dev/null; then
  die "node ist nicht installiert.\n  → https://nodejs.org/  (empfohlen: nvm oder Homebrew)"
fi
NODE_VER=$(node --version | tr -d 'v')
NODE_MAJOR=$(semver_major "$NODE_VER")
if [[ "$NODE_MAJOR" -lt 20 ]]; then
  die "node $NODE_VER ist zu alt — benötigt >= 20.\n  → nvm install 20 && nvm use 20"
fi
success "node $NODE_VER"

# --- uv ---
if ! command -v uv &>/dev/null; then
  die "uv ist nicht installiert.\n  → https://docs.astral.sh/uv/  (curl -LsSf https://astral.sh/uv/install.sh | sh)"
fi
UV_VER=$(uv --version 2>/dev/null | awk '{print $2}')
success "uv $UV_VER"

# --- docker (nur Pflicht bei --docker-Modus) ---
if [[ "$MODE" == "docker" ]]; then
  if ! command -v docker &>/dev/null; then
    die "docker ist nicht installiert.\n  → https://docs.docker.com/get-docker/"
  fi
  if ! docker info &>/dev/null; then
    die "Docker-Daemon läuft nicht — bitte Docker starten."
  fi
  DOCKER_VER=$(docker --version | grep -oE '[0-9]+\.[0-9]+')
  success "docker $DOCKER_VER"
fi

# ---------------------------------------------------------------------------
# .env-Datei anlegen (idempotent)
# ---------------------------------------------------------------------------
setup_env() {
  local template="$1"
  if [[ ! -f ".env" ]]; then
    if [[ -f "$template" ]]; then
      cp "$template" .env
      warn ".env aus $template erstellt — bitte SECRET_KEY, AGORA_AUTH_TOKEN und NEO4J_PASSWORD setzen!"
      warn "  python3 -c \"import secrets; print(secrets.token_urlsafe(32))\""
    else
      die "Vorlage $template nicht gefunden."
    fi
  else
    info ".env bereits vorhanden — wird nicht überschrieben."
  fi
}

# ---------------------------------------------------------------------------
# MODUS: check
# ---------------------------------------------------------------------------
if [[ "$MODE" == "check" ]]; then
  info "Starte bun run check …"
  bun run check
  success "check abgeschlossen."
  exit 0
fi

# ---------------------------------------------------------------------------
# MODUS: docker
# ---------------------------------------------------------------------------
if [[ "$MODE" == "docker" ]]; then
  info "Docker-Compose-Modus"
  setup_env ".env.docker.example"

  BACKEND_PORT="${AGORA_BACKEND_PORT:-5001}"
  FRONTEND_PORT="${AGORA_FRONTEND_PORT:-5173}"
  BIND_HOST="${AGORA_BIND_HOST:-127.0.0.1}"

  info "Starte docker compose up --build -d …"
  docker compose up --build -d

  # Auf /readyz warten
  READYZ_URL="http://${BIND_HOST}:${BACKEND_PORT}/readyz"
  TIMEOUT=180
  INTERVAL=5
  ELAPSED=0
  info "Warte auf Backend-Readiness: ${READYZ_URL} (Timeout ${TIMEOUT}s) …"
  until curl -fsS "$READYZ_URL" &>/dev/null; do
    if [[ "$ELAPSED" -ge "$TIMEOUT" ]]; then
      die "Backend hat nach ${TIMEOUT}s nicht geantwortet.\n  → docker compose logs agora"
    fi
    sleep "$INTERVAL"
    ELAPSED=$((ELAPSED + INTERVAL))
    printf "  … %ds vergangen\r" "$ELAPSED"
  done
  printf "\n"

  echo ""
  success "Agora läuft!"
  echo ""
  printf "  ${BOLD}Frontend${RESET}           http://${BIND_HOST}:${FRONTEND_PORT}\n"
  printf "  ${BOLD}Backend Readiness${RESET}  http://${BIND_HOST}:${BACKEND_PORT}/readyz\n"
  printf "  ${BOLD}Backend Health${RESET}     http://${BIND_HOST}:${BACKEND_PORT}/health\n"
  printf "  ${BOLD}Neo4j Browser${RESET}      http://127.0.0.1:7474\n"
  echo ""
  info "Logs:  docker compose logs -f agora"
  info "Stop:  docker compose down"
  exit 0
fi

# ---------------------------------------------------------------------------
# MODUS: host (Default)
# ---------------------------------------------------------------------------
info "Host-Dev-Modus"
setup_env ".env.example"

# Root-Abhängigkeiten (concurrently etc.)
info "Installiere Root-Abhängigkeiten (bun install) …"
bun install

# Frontend
info "Installiere Frontend-Abhängigkeiten (cd frontend && bun install) …"
(cd frontend && bun install)

# Backend
info "Installiere Backend-Abhängigkeiten (cd backend && uv sync) …"
(cd backend && uv sync)

echo ""
success "Installation abgeschlossen!"
echo ""
printf "  ${BOLD}Starten:${RESET}   bun run dev\n"
printf "  ${BOLD}Frontend:${RESET}  http://localhost:5173\n"
printf "  ${BOLD}Backend:${RESET}   http://localhost:5001\n"
echo ""
warn "Dieser Modus benötigt externe Neo4j- und Redis-Instanzen."
warn "  Neo4j:  bolt://localhost:7687  (https://neo4j.com/download/)"
warn "  Redis:  redis://localhost:6379  (brew install redis && brew services start redis)"
warn ""
warn "Kein Neo4j/Redis lokal? Starte mit Docker: ./install.sh --docker"
echo ""
info "Konfiguration: .env bearbeiten (SECRET_KEY, NEO4J_PASSWORD, LLM-Endpunkte setzen)"
info "Weitere Guides: docs/deployment-dev.md"
