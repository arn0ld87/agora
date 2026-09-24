#!/usr/bin/env bash
# check_pandaos_managed_leak.sh — versionierte Dateien duerfen keinen
# PandaOS-managed-Block enthalten.
#
# PandaOS schreibt lokal einen Block zwischen
#   <!-- >>> pandaos-managed (do not edit) >>> -->
#   <!-- <<< pandaos-managed <<< -->
# in AGENTS.md (Codex-Session-Anweisungen, maschinenspezifische Pfade und
# Hostnamen). In PR #1539 landete dieser Block versehentlich im Repo. Das
# Gate prueft den Index (was committet wird), nicht die Arbeitskopie: PandaOS
# darf den Block lokal weiter pflegen.
#
# Exit codes: 0 sauber, 1 Block im Index gefunden.
set -euo pipefail

# Am Zeilenanfang verankert: PandaOS schreibt den Marker immer als eigene
# Zeile. Doku, die ihn inline zitiert (Runbook, Changelog), bleibt erlaubt.
hits=$(git grep --cached -l -E '^<!-- >>> pandaos-managed' -- . || true)

if [[ -n "$hits" ]]; then
  echo "PandaOS-managed-Block in versionierten Dateien:" >&2
  printf '  %s\n' $hits >&2
  echo "Block entfernen — siehe docs/runbooks/pre-push-gate.md (Gate 14)." >&2
  exit 1
fi
