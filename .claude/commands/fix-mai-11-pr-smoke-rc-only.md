---
description: MAI-11 — docker-image.yml::prod-proxy-smoke läuft nur auf RC/Release-Branches und workflow_dispatch, nicht mehr auf Feature-PRs.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-11-pr-smoke-rc-only — PR-Smoke nur für RC/Release

## Ziel

`docker-image.yml::prod-proxy-smoke` triggert automatisch nur auf `release/**`/`rc/**` Branches, Tags `v*` und `workflow_dispatch`. Feature-PRs müssen das Label `needs-prod-smoke` setzen, um den Smoke zu erzwingen — keine stille 30-min-Penalty mehr für normale Feature-Arbeit.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-11/`.
- Branch: `feat/mai-11-pr-smoke-rc-only`.

## Schritt-für-Schritt

### Schritt 1: Aktuellen Trigger lesen

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-11
grep -A 30 "prod-proxy-smoke:" .github/workflows/docker-image.yml | head -50
```

### Schritt 2: Trigger-Block ersetzen

`.github/workflows/docker-image.yml` — `on:`-Block des Workflow:

```yaml
on:
  push:
    branches: [main]
    tags: ['v*']
  pull_request:
    branches: [main]
    types: [opened, synchronize, ready_for_review, labeled]
    # PRs aus release/**/rc/** triggern immer, normale Feature-PRs nur mit Label.
  workflow_dispatch:
```

Und der `prod-proxy-smoke`-Job bekommt einen `if`-Guard:

```yaml
  prod-proxy-smoke:
    name: Prod-Stack Reverse-Proxy-Smoke
    runs-on: ubuntu-latest
    timeout-minutes: 35
    if: |
      github.event_name == 'workflow_dispatch' ||
      (github.event_name == 'push' && (
        github.ref == 'refs/heads/main' ||
        startsWith(github.ref, 'refs/tags/v')
      )) ||
      (github.event_name == 'pull_request' && (
        startsWith(github.head_ref, 'release/') ||
        startsWith(github.head_ref, 'rc/') ||
        contains(github.event.pull_request.labels.*.name, 'needs-prod-smoke')
      ))
    steps:
      # ... bestehende Steps unverändert ...
```

### Schritt 3: Label vorbereiten

```bash
gh label create needs-prod-smoke \
  --description "Erzwingt prod-proxy-smoke auf Feature-PRs (MAI-11)" \
  --color "FF8800" \
  || gh label edit needs-prod-smoke \
     --description "Erzwingt prod-proxy-smoke auf Feature-PRs (MAI-11)" \
     --color "FF8800"
```

### Schritt 4: Doku ergänzen

`docu/security-hardening.md` (oder wo der Smoke-Workflow dokumentiert ist):

```markdown
### Prod-Stack-Smoke

Stand MAI-11 (2026-05-14):

- Automatisch auf: `main`-Push, Tags `v*`, RC/Release-Branches (`release/**`, `rc/**`).
- Manuell: `workflow_dispatch` über GitHub-UI.
- Feature-PRs: Smoke läuft NUR mit Label `needs-prod-smoke`.

Begründung: Smoke kostet ~30 min pro Iteration; auf normalen Feature-PRs
ist die Drift-Wahrscheinlichkeit niedrig. Bei Touches an Dockerfile,
docker-compose*.yml, deploy/** oder backend/app/utils/auth.py wird das
Label gesetzt — am einfachsten via `gh pr edit <N> --add-label needs-prod-smoke`.
```

### Schritt 5: Workflow-Validation

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-11
npx --yes @action-validator/cli@latest \
  .github/workflows/docker-image.yml
```

## Verifikation

```bash
# 1) Workflow-Syntax OK
gh workflow view docker-image.yml > /dev/null

# 2) Bedingungs-Test: dry-run mit verschiedenen Refs (lokal nicht direkt machbar,
#    aber `gh workflow run` mit verschiedenen Triggern testet das im GH-UI)

# 3) Label existiert
gh label list | grep "needs-prod-smoke"
```

### Test-PR-Sequenz (manuell, nach Merge auf main)

1. **Feature-PR ohne Label**: Branch `feat/test-no-smoke` → PR öffnen → Workflow-Liste prüfen → `prod-proxy-smoke` darf NICHT triggern.
2. **Label nachreichen**: `gh pr edit <N> --add-label needs-prod-smoke` → Workflow startet (durch `synchronize` oder `labeled` Event).
3. **RC-PR**: Branch `rc/test-rc-smoke` → PR auf `main` → Workflow triggert automatisch.
4. **Tag-Push**: `git tag v0.0.0-test && git push --tags` → Workflow triggert (anschließend Tag wieder löschen).

## Warum?

STATUS.md 2026-05-06: PR-Smoke wurde wegen 30-min-Laufzeit pausiert. Vor v1.0 war geplant, das neu zu bewerten. Stand jetzt: v1.0 ist released. Eine generelle PR-Trigger-Reaktivierung wäre Rückschritt. MAI-11 macht den Smoke per Label opt-in für PRs, automatisch für Release-Pfade — das ist die langfristig stabile Konfiguration.

## Nächste Schritte

1. Worklog mit Test-PR-Sequenz-Resultaten.
2. CHANGELOG: `MAI-11 · prod-proxy-smoke nur auf release/rc/Tags/main automatisch; Feature-PRs opt-in via needs-prod-smoke-Label.`
3. `/fix-mai-05-voice-lint-ci` (Block E Start).
