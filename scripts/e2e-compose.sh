#!/usr/bin/env bash
set -euo pipefail

# Single Source of Truth fuer die Compose-Invocation des E2E-Stacks (Issue #989).
#
# Aufruf: scripts/e2e-compose.sh <compose-subcommand> [args...]
#   scripts/e2e-compose.sh up -d --build
#   scripts/e2e-compose.sh down -v --remove-orphans
#   scripts/e2e-compose.sh logs agora --tail=500
#
# Warum ein eigenes Skript statt dreimal derselben Liste:
# e2e-up.sh, e2e-down.sh und frontend/tests/e2e/global-teardown.ts mussten die
# `-f`-Kette bisher haendisch gleich halten. global-teardown.ts traegt dazu den
# Kommentar "Compose-Befehl muss identisch mit e2e-down.sh / e2e-up.sh sein" —
# genau das war er nicht: e2e-down.sh lud das E2E-Override nicht mit, wodurch
# der `mock-models`-Container als Orphan des Projekts zurueckblieb.
#
# --project-name: fester Projektname statt des Compose-Defaults (Name des
# Verzeichnisses). Ohne ihn heisst das Projekt im Hauptrepo `agora`, in einem
# Worktree aber z. B. `989-e2e-env-idempotent` — `down` aus dem einen Verzeichnis
# raeumte den Stack des anderen nicht ab. Ueber AGORA_E2E_PROJECT ueberschreibbar,
# falls jemand zwei E2E-Stacks nebeneinander braucht.
SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
REPO_ROOT=$(cd "$SCRIPT_DIR/.." && pwd)

# Die `-f`-Pfade sind relativ zum Repo-Root aufgeloest; Compose nimmt das
# Verzeichnis der ersten Datei als Projektverzeichnis.
cd "$REPO_ROOT"

exec docker compose \
  --project-name "${AGORA_E2E_PROJECT:-agora-e2e}" \
  -f docker-compose.yml \
  -f docker-compose.prod.yml \
  -f deploy/compose/docker-compose.prod-with-proxy.yml \
  -f deploy/compose/docker-compose.e2e.override.yml \
  "$@"
