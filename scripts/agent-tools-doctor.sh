#!/usr/bin/env bash
# Doctor-Skript: prüft alle Tools durch und bricht bei fehlenden
# Abhängigkeiten nicht ab — Sammelstatus als Exit-Code am Ende.
set -uo pipefail

repo_root="$(git rev-parse --show-toplevel)"
status=0

printf '%s\n' '== Codex =='
if command -v codex >/dev/null 2>&1; then
  codex --version || status=1
else
  printf '%s\n' 'FEHLT: codex nicht im PATH'
  status=1
fi

printf '%s\n' '== context-mode =='
printf '%s\n' 'MCP-Doctor in Codex ausführen: mcp__context_mode__ctx_doctor'

printf '%s\n' '== code-review-graph =='
if command -v uvx >/dev/null 2>&1; then
  uvx --from 'code-review-graph==2.3.6' code-review-graph --version || status=1
  uvx --from 'code-review-graph==2.3.6' code-review-graph status --repo "$repo_root" || status=1
else
  printf '%s\n' 'FEHLT: uvx nicht im PATH'
  status=1
fi

printf '%s\n' 'OK: keine Auth- oder Secret-Dateien gelesen'
exit "$status"
