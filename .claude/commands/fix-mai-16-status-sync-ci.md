---
description: MAI-16 — scripts/sync-status.sh --check failed bei manuell editiertem STATUS.md ohne korrekten generator-Run.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-16-status-sync-ci — `sync-status.sh --check` in CI

## Ziel

`scripts/sync-status.sh --check` regeneriert `docs/STATUS.md` aus den Quellen (`PLAN.md`-Headers, `gh run list`, Coverage-Reports, Issue-Counts), vergleicht mit Disk-Inhalt und failt CI bei Drift. Damit kann STATUS.md nicht mehr stillschweigend per Hand falsch gepflegt werden.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-16/`.
- Branch: `feat/mai-16-status-sync-ci`.
- `scripts/sync-status.sh` muss als Generator-Skript existieren (Phase 6 Refactoring-Plan).

## Schritt-für-Schritt

### Schritt 1: Skript inspizieren

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-16
test -x scripts/sync-status.sh || echo "FEHLT — vorher Phase 6 nachholen"
cat scripts/sync-status.sh | head -40
```

### Schritt 2: --check-Modus ergänzen

`scripts/sync-status.sh`:

```bash
#!/usr/bin/env bash
# MAI-16: sync-status mit --check-Modus.
#
# Usage:
#   ./scripts/sync-status.sh           # regeneriert docs/STATUS.md
#   ./scripts/sync-status.sh --check   # exit 1 bei Drift (für CI)

set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
STATUS_FILE="${REPO_ROOT}/docs/STATUS.md"
CHECK_MODE=0

if [[ "${1:-}" == "--check" ]]; then
  CHECK_MODE=1
fi

# (Bestehende Regenerations-Logik in eine Funktion ziehen:)
regenerate_status_md() {
  local target_path="$1"
  # ... Header-Block aus PLAN.md ...
  # ... gh run list für CI-Status ...
  # ... Coverage-Reports lesen ...
  # ... Issue-Counts ...
  cat > "$target_path" <<EOF
# Agora Status

> Stand: $(date -u +"%Y-%m-%d %H:%MZ")
> Quelle: scripts/sync-status.sh — NICHT von Hand editieren.

## CI-Status

$(gh run list --workflow=ci.yml --limit 1 --json status,conclusion,headBranch --jq '.[0] | "Branch: \(.headBranch) — \(.status)/\(.conclusion)"')

## Coverage

- Backend: $(jq -r '.totals.percent_covered' backend/coverage.json 2>/dev/null || echo 'n/a')%
- Frontend: $(jq -r '.total.lines.pct' frontend/coverage/coverage-summary.json 2>/dev/null || echo 'n/a')%

## Offene P0/P1-Issues

$(gh issue list --label P0,P1 --state open --json number,title --jq '.[] | "- #\(.number) \(.title)"')

EOF
}

if [[ "$CHECK_MODE" -eq 1 ]]; then
  TMP_STATUS=$(mktemp)
  trap 'rm -f "$TMP_STATUS"' EXIT
  regenerate_status_md "$TMP_STATUS"
  if ! diff -u "$STATUS_FILE" "$TMP_STATUS"; then
    echo "::error::STATUS.md gedriftet — bitte ./scripts/sync-status.sh ausführen und committen." >&2
    exit 1
  fi
  echo "OK: STATUS.md ist synchron."
  exit 0
fi

regenerate_status_md "$STATUS_FILE"
echo "OK: STATUS.md regeneriert unter $STATUS_FILE"
```

### Schritt 3: CI-Job

`.github/workflows/ci.yml` — neuer Step in einem bestehenden Lint-Job (oder eigener Job):

```yaml
      - name: STATUS.md drift check (MAI-16)
        run: |
          ./scripts/sync-status.sh --check
        # exit 1 bei manuell editiertem STATUS.md ohne sync-status-Run
```

### Schritt 4: Lokal test-run

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-16

# Sollte clean sein
./scripts/sync-status.sh --check
echo "Exit: $?"

# Drift künstlich erzeugen
echo "FAKE EDIT" >> docs/STATUS.md
./scripts/sync-status.sh --check
echo "Exit: $?"  # Erwartet 1

# Rückgängig
git checkout -- docs/STATUS.md
```

### Schritt 5: Doku aktualisieren

`CLAUDE.md` (im Status-/Worklog-Abschnitt) und `AGENTS.md`:

```markdown
### STATUS.md ist generiert

`docs/STATUS.md` wird von `scripts/sync-status.sh` regeneriert. MAI-16-CI-Check
failed bei manuell editiertem File. Für Updates:

    ./scripts/sync-status.sh   # regeneriert
    git add docs/STATUS.md
    git commit -m "chore: sync STATUS.md"
```

## Verifikation

```bash
# 1) Skript ist ausführbar und liefert exit 0
./scripts/sync-status.sh --check
echo "Exit: $?"

# 2) Drift-Erkennung funktioniert (siehe Schritt 4)

# 3) Workflow-Syntax
npx --yes @action-validator/cli@latest .github/workflows/ci.yml

# 4) Voll-Test (kein Regression)
cd backend && uv run pytest -x -q
```

## Warum?

Refactoring-Plan Phase 6: „STATUS.md ist Single Source of Truth, aber wird heute von Hand gepflegt — bricht regelmäßig." Mit `--check` als CI-Gate kann das File nicht mehr ohne Generator-Run von der Realität abweichen. Der Generator selbst liest aus den eigentlichen Quellen (`gh run`, Coverage-JSONs, Issues), also bleibt das Update billig.

## Nächste Schritte

1. Worklog mit Drift-Demo-Output (siehe Schritt 4).
2. CHANGELOG: `MAI-16 · sync-status.sh --check als CI-Pflicht-Gate für STATUS.md.`
3. `/fix-mai-17-radon-gate` (letzter Slice der Mai-Welle).
