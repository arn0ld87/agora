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

# --- node: muss zu engines.node aus package.json passen ---
# Der Bereich ist nicht "ab X aufwaerts", sondern der von vitest 5 geforderte
# ^22.12.0 || ^24.0.0 || >=26.0.0. Die ungeraden Majors 23 und 25 sind
# ausgeschlossen, weil sie keine LTS-Linien sind und vitest sie nicht traegt.
# Wer hier einen simplen ">= 22"-Vergleich einsetzt, laesst Node 23/25 durch
# und baut damit genau den Widerspruch wieder ein, den dieser Block aufloest:
# ein Installer, der eine Umgebung durchwinkt, die die Manifeste ablehnen.
if ! command -v node &>/dev/null; then
  die "node ist nicht installiert.\n  → https://nodejs.org/  (empfohlen: nvm oder Homebrew)"
fi
NODE_VER=$(node --version | tr -d 'v')
NODE_MAJOR=$(semver_major "$NODE_VER")
NODE_MINOR=$(semver_minor "$NODE_VER")
# >>> node-support-block (wird von backend/tests/test_install_node_engine.py
# als Ganzes extrahiert und gegen engines.node aus package.json geprueft —
# die Marker sind der Vertrag mit diesem Test, nicht Deko.)
node_supported() {
  local major="$1"
  local minor="${2:-0}"
  case "$major" in
    22) [[ "$minor" -ge 12 ]] ;;
    24) return 0 ;;
    *)  [[ "$major" -ge 26 ]] ;;
  esac
}
# <<< node-support-block
if ! node_supported "$NODE_MAJOR" "$NODE_MINOR"; then
  die "node $NODE_VER wird nicht unterstuetzt — benoetigt ^22.12.0 || ^24.0.0 || >=26.0.0 (vitest 5).\n  → nvm install 24 && nvm use 24"
fi
success "node $NODE_VER"

# --- uv ---
if ! command -v uv &>/dev/null; then
  die "uv ist nicht installiert.\n  → https://docs.astral.sh/uv/  (curl -LsSf https://astral.sh/uv/install.sh | sh)"
fi
UV_VER=$(uv --version 2>/dev/null | awk '{print $2}')
success "uv $UV_VER"

# --- docker + curl (nur Pflicht bei --docker-Modus) ---
if [[ "$MODE" == "docker" ]]; then
  if ! command -v docker &>/dev/null; then
    die "docker ist nicht installiert.\n  → https://docs.docker.com/get-docker/"
  fi
  if ! command -v curl &>/dev/null; then
    die "curl ist nicht installiert — wird für den Readiness-Check benötigt.\n  → apt-get install curl  oder  brew install curl"
  fi
  if ! docker info &>/dev/null; then
    die "Docker-Daemon läuft nicht — bitte Docker starten."
  fi
  if ! docker compose version &>/dev/null; then
    die "docker compose (Plugin) nicht gefunden.\n  → https://docs.docker.com/compose/install/"
  fi
  DOCKER_VER=$(docker --version | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)
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
      warn "  openssl rand 32 | base64 | tr '+/' '-_' | tr -d '=\n'"
    else
      die "Vorlage $template nicht gefunden."
    fi
  else
    info ".env bereits vorhanden — wird nicht überschrieben."
  fi
}

# Bekannte Platzhalter aus `.env.example`/`.env.docker.example` — Vereinigung
# von SECRET_KEY_PLACEHOLDERS und NEO4J_PASSWORD_PLACEHOLDERS aus
# backend/app/config.py:31-42. install.sh laeuft vor der Dependency-
# Installation und kann diese Python-Liste nicht importieren, deshalb die
# Zweitkopie hier. Drift-Guard-Test:
# backend/tests/test_install_ensure_secret.py::test_placeholder_list_matches_config
# haelt beide Listen synchron.
# >>> ensure-secret-block (wird von backend/tests/test_install_ensure_secret.py
# als Ganzes extrahiert und in einer Subshell ausgefuehrt — die Marker sind
# der Vertrag mit diesem Test, nicht Deko.)
ENSURE_SECRET_PLACEHOLDERS=(change-me change-me-use-token_urlsafe-32 agora password neo4j)

# Pflicht-Secret in .env sicherstellen. Fehlt der Wert ODER steht dort noch
# ein bekannter Platzhalter (s. ENSURE_SECRET_PLACEHOLDERS), wird er generiert
# und inplace in .env geschrieben (GNU- und BSD-sed-kompatibel). Ohne die
# Platzhalter-Erkennung waere dieser Aufruf im Host-Modus wirkungslos, weil
# .env.example nicht-leere Platzhalter wie `change-me-use-token_urlsafe-32`
# enthaelt.
#
# AGORA_SECRET_KEY und AGORA_FERNET_KEY muessen gueltige Fernet-Keys sein
# (siehe llm_provider_secrets_store.py / api_keys_persistence.py) —
# secrets.token_urlsafe(32) waere ein ungueltiger Fernet-Key und liesse die
# Anwendung beim ersten Zugriff mit RuntimeError abbrechen.
# base64.urlsafe_b64encode(os.urandom(32)) entspricht exakt
# Fernet.generate_key(), funktioniert aber mit der Standardbibliothek —
# `cryptography` ist an dieser Stelle im Installationsablauf typischerweise
# 32 kryptografisch zufaellige Bytes als URL-sicheres Base64.
#   padded   -> 44 Zeichen inkl. "="-Padding, bitgleich zu
#               `Fernet.generate_key()` (base64.urlsafe_b64encode(os.urandom(32)))
#   stripped -> 43 Zeichen ohne Padding, bitgleich zu `secrets.token_urlsafe(32)`
#
# install.sh laeuft VOR `uv sync`, darf also keinen Projekt-Interpreter
# voraussetzen — und auf einem sauberen macOS mit den dokumentierten
# Voraussetzungen (bun, node, uv) gibt es ueberhaupt kein System-`python3`,
# weil `uv` seinen eigenen Interpreter mitbringt. Deshalb eine Fallback-Kette
# statt eines harten `python3`-Aufrufs; alle drei Wege liefern dasselbe
# Format aus derselben Entropiequelle (32 Bytes aus dem CSPRNG des Systems).
random_urlsafe_32() {
  local mode="$1"
  local raw=""
  if command -v python3 &>/dev/null; then
    raw=$(python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())")
  elif command -v openssl &>/dev/null; then
    raw=$(openssl rand 32 | base64 | tr -d '\n' | tr '+/' '-_')
  elif [[ -r /dev/urandom ]]; then
    raw=$(head -c 32 /dev/urandom | base64 | tr -d '\n' | tr '+/' '-_')
  else
    die "Kein Zufallsgenerator verfuegbar (weder python3 noch openssl noch /dev/urandom) — Secrets koennen nicht erzeugt werden."
  fi
  if [[ "$mode" == "stripped" ]]; then
    raw="${raw//=/}"
  fi
  # 32 Bytes ergeben genau 44 Base64-Zeichen (43 ohne Padding). Weicht das ab,
  # hat der Generator etwas anderes geliefert als erwartet — dann lieber
  # abbrechen als ein zu kurzes Secret in die .env schreiben.
  local expected=44
  [[ "$mode" == "stripped" ]] && expected=43
  if [[ "${#raw}" -ne "$expected" ]]; then
    die "Zufallswert hat ${#raw} statt $expected Zeichen — Secret-Generierung abgebrochen."
  fi
  printf '%s' "$raw"
}

# noch nicht installiert.
ensure_secret() {
  local key="$1"
  local current
  current=$(grep -E "^${key}=" .env | head -1 | cut -d'=' -f2- || true)
  local current_norm
  current_norm=$(printf '%s' "$current" | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  local needs_value=0
  if [[ -z "$current_norm" ]]; then
    needs_value=1
  else
    local ph
    for ph in "${ENSURE_SECRET_PLACEHOLDERS[@]}"; do
      if [[ "$current_norm" == "$ph" ]]; then
        needs_value=1
        break
      fi
    done
  fi
  if [[ "$needs_value" -eq 0 ]]; then
    return 0
  fi
  local val
  case "$key" in
    AGORA_SECRET_KEY|AGORA_FERNET_KEY)
      val=$(random_urlsafe_32 padded)
      ;;
    *)
      val=$(random_urlsafe_32 stripped)
      ;;
  esac
  if grep -qE "^${key}=" .env; then
    # Zeile vorhanden (leer oder Platzhalter) — inplace ersetzen
    # (GNU- und BSD-sed-kompatibel).
    if sed --version >/dev/null 2>&1; then
      sed -i "s|^${key}=.*\$|${key}=${val}|" .env
    else
      sed -i '' "s|^${key}=.*\$|${key}=${val}|" .env
    fi
  else
    # Schlüssel fehlt ganz (ältere .env vor Einführung des Keys) — anhängen.
    # Ohne diesen Zweig fasst sed nichts an und der Key bleibt still ungesetzt.
    [[ -s .env && -n "$(tail -c 1 .env)" ]] && printf '\n' >>.env
    printf '%s=%s\n' "$key" "$val" >>.env
  fi
  if ! grep -qE "^${key}=[^[:space:]]+" .env; then
    die "$key konnte nicht in .env gesetzt werden."
  fi
  # Verteidigungs-Check: nach der Generierung darf kein bekannter Platzhalter
  # mehr in .env stehen. Sollte bei korrekter Generatorlogik nie greifen,
  # bricht install.sh aber mit klarer Meldung ab statt eine kaputte .env
  # durchzureichen.
  local final_norm
  final_norm=$(grep -E "^${key}=" .env | head -1 | cut -d'=' -f2- | tr -d '[:space:]' | tr '[:upper:]' '[:lower:]')
  local ph2
  for ph2 in "${ENSURE_SECRET_PLACEHOLDERS[@]}"; do
    if [[ "$final_norm" == "$ph2" ]]; then
      die "$key steht nach der automatischen Generierung noch auf einem bekannten Platzhalter — Installation abgebrochen."
    fi
  done
  info "  $key automatisch erzeugt"
}
# <<< ensure-secret-block

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

  info "Prüfe Pflicht-Secrets …"
  ensure_secret SECRET_KEY
  ensure_secret AGORA_AUTH_TOKEN
  ensure_secret NEO4J_PASSWORD
  # Die beiden Master-Keys gelten im Docker-Modus genauso: ohne
  # AGORA_FERNET_KEY wirft api_keys_persistence.py ausserhalb des
  # Debug-Modus RuntimeError, ohne AGORA_SECRET_KEY faellt
  # llm_provider_secrets_store.py beim ersten Zugriff aus. Beide
  # fehlten hier, weil .env.docker.example sie nie gefuehrt hat.
  ensure_secret AGORA_SECRET_KEY
  ensure_secret AGORA_FERNET_KEY

  BACKEND_PORT="${AGORA_BACKEND_PORT:-5001}"
  FRONTEND_PORT="${AGORA_FRONTEND_PORT:-5173}"
  BIND_HOST="${AGORA_BIND_HOST:-127.0.0.1}"
  # Bei 0.0.0.0 kann curl nicht direkt connecten — loopback nutzen
  if [[ "$BIND_HOST" == "0.0.0.0" ]]; then
    CHECK_HOST="127.0.0.1"
  else
    CHECK_HOST="$BIND_HOST"
  fi

  info "Starte docker compose up --build -d …"
  docker compose up --build -d

  # Auf /readyz warten
  READYZ_URL="http://${CHECK_HOST}:${BACKEND_PORT}/readyz"
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
  printf "  ${BOLD}Frontend${RESET}           http://${CHECK_HOST}:${FRONTEND_PORT}\n"
  printf "  ${BOLD}Backend Readiness${RESET}  http://${CHECK_HOST}:${BACKEND_PORT}/readyz\n"
  printf "  ${BOLD}Backend Health${RESET}     http://${CHECK_HOST}:${BACKEND_PORT}/health\n"
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

info "Prüfe Pflicht-Secrets …"
ensure_secret SECRET_KEY
# `.env.example` fuehrt AGORA_AUTH_TOKEN nur auskommentiert und setzt
# FLASK_DEBUG=false. Ohne Token bricht `backend/run.py` beim Start mit
# "AGORA_AUTH_TOKEN missing in non-debug mode" aus `Config.validate()` ab —
# der Host-Modus muss ihn deshalb genauso erzeugen wie der Docker-Modus.
ensure_secret AGORA_AUTH_TOKEN
ensure_secret AGORA_SECRET_KEY
ensure_secret AGORA_FERNET_KEY

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
