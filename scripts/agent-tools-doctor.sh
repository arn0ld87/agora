#!/usr/bin/env bash
set -euo pipefail

repo_root="$(git rev-parse --show-toplevel)"

printf '%s\n' '== Codex =='
codex --version

printf '%s\n' '== context-mode =='
printf '%s\n' 'MCP-Doctor in Codex ausführen: mcp__context_mode__ctx_doctor'

printf '%s\n' '== code-review-graph =='
uvx --from 'code-review-graph==2.3.6' code-review-graph --version
uvx --from 'code-review-graph==2.3.6' code-review-graph status --repo "$repo_root"

printf '%s\n' 'OK: keine Auth- oder Secret-Dateien gelesen'
