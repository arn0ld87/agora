#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# shellcheck source=lib/env-file.sh
source "${SCRIPT_DIR}/lib/env-file.sh"

# Issue #989: Der Stub-Schalter darf den E2E-Lauf nicht ueberleben.
#
# e2e-up.sh schreibt AGORA_E2E_LLM_MODE in die .env, weil docker compose sie
# mit Vorrang vor der Process-Env liest. Blieb er stehen, uebernahm ihn der
# naechste normale `docker compose up` des Entwicklungs-Stacks — das Backend
# lief dann still im Stub-Modus und lieferte deterministische Fake-Reports
# statt echter Modellantworten. Kein Fehler, keine Warnung, nur eine Zeile
# "E2E-Stub aktiv — ueberspringe LLM-Call" tief im Log.
#
# Bewusst nur dieser eine Schluessel: AGORA_SECRET_KEY und die uebrigen
# Runtime-Werte bleiben stehen, weil damit verschluesselte Secrets sonst
# unlesbar wuerden.
#
# Als EXIT-Trap registriert, nicht als letzte Zeile: `docker compose down`
# scheitert unter `set -e` haeufiger als man denkt (Daemon weg, Volume
# belegt) — genau dann darf der Schalter erst recht nicht liegen bleiben.
_on_exit() {
  local rc=$?
  local drop_rc=0
  agora_env_drop_key AGORA_E2E_LLM_MODE "${REPO_ROOT}/.env" || drop_rc=$?
  case "$drop_rc" in
    0) echo "[e2e-down] AGORA_E2E_LLM_MODE aus .env entfernt (Stub-Modus beendet)" >&2 ;;
    1) : ;;  # war nicht gesetzt
    *) echo "::error::[e2e-down] Stub-Schalter konnte NICHT entfernt werden — .env vor dem naechsten Dev-Start pruefen" >&2 ;;
  esac
  agora_env_cleanup_tmp
  # Exitcode des eigentlichen `down` erhalten, nicht durch den Trap ersetzen.
  return "$rc"
}
trap _on_exit EXIT

cd "$REPO_ROOT"
echo "[e2e-down] stopping compose stack + volumes..." >&2
# --remove-orphans: `mock-models` existiert nur im E2E-Override. Solange dieses
# Skript die Datei nicht mitlud, kannte `down` den Service nicht und liess den
# Container als Orphan des Projekts stehen (Issue #989). Ueber e2e-compose.sh
# ist die Dateiliste jetzt identisch mit der von e2e-up.sh; das Flag bleibt als
# Absicherung fuer Services, die aus einer aelteren Stack-Generation stammen.
"$SCRIPT_DIR/e2e-compose.sh" down -v --remove-orphans
