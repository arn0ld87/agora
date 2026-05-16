---
description: MAI-01 — P4.4 Report-Mode-Smokes als vierten Job in e2e-smokes.yml verdrahten.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-01-mode-smokes-ci — Mode-Smokes in CI

## Ziel

`frontend/tests/e2e/report-modes.spec.ts` läuft in CI als vierter Job neben `health-smoke`, `upload-graph-smoke`, `minimal-report-smoke`. Damit ist P4.4 final-gated.

## Voraussetzungen

- Worktree liegt unter `/Volumes/T7/Projekte/agora-worktrees/mai-01/`.
- Branch: `feat/mai-01-mode-smokes-ci`.
- `gh` ist eingeloggt.

## Schritt-für-Schritt

### Schritt 1: Status-Check

```bash
# Prüfen ob report-modes.spec.ts bereits in e2e-smokes.yml referenziert wird.
cd /Volumes/T7/Projekte/agora-worktrees/mai-01
rg -n "report-modes" .github/workflows/e2e-smokes.yml \
  && echo "BEREITS VERDRAHTET — Slice obsolet" \
  || echo "OFFEN, weiter mit Schritt 2"
```

### Schritt 2: Job ergänzen

```bash
# Editor: neuen Job report-modes-smoke nach minimal-report-smoke einfügen.
# Vorlage: kopiert minimal-report-smoke + tauscht den playwright-Aufruf.
```

Inhalt des neuen Job-Blocks in `.github/workflows/e2e-smokes.yml`:

```yaml
  report-modes-smoke:
    name: Playwright Report-Modes-Smoke (P4.4)
    runs-on: ubuntu-latest
    timeout-minutes: 30
    env:
      AGORA_PROXY_PORT: '80'
      AGORA_E2E_BASE_URL: http://127.0.0.1:80
      AGORA_SKIP_EMBEDDING_PROBE: 'true'
      # Stub-Modus: deterministisch für alle drei Modi (strict/balanced/explorative)
      AGORA_E2E_LLM_MODE: 'stub'
    steps:
      - name: Harden Runner
        uses: step-security/harden-runner@a5ad31d6a139d249332a2605b85202e8c0b78450 # v2.19.1
        with:
          egress-policy: audit

      - uses: actions/checkout@v6
      - uses: actions/setup-node@v6
        with:
          node-version: '20'
          cache: npm
          cache-dependency-path: frontend/package-lock.json
      - name: Generate ephemeral E2E credentials
        run: |
          {
            echo "AGORA_AUTH_TOKEN=$(openssl rand -hex 24)"
            echo "SECRET_KEY=$(openssl rand -hex 32)"
            echo "NEO4J_PASSWORD=$(openssl rand -hex 16)"
          } >> "$GITHUB_ENV"
      - name: Install frontend deps
        working-directory: frontend
        run: npm ci
      - name: Build frontend bundle
        working-directory: frontend
        run: npm run build
      - name: Install Playwright browsers (Chromium-only)
        working-directory: frontend
        run: npx playwright install --with-deps chromium
      - name: Run Playwright Report-Modes-Smoke
        working-directory: frontend
        run: npx playwright test report-modes.spec.ts --reporter=list,github
      - name: Upload trace on failure
        if: failure()
        uses: actions/upload-artifact@v7
        with:
          name: playwright-trace-report-modes
          path: frontend/test-results/
          retention-days: 14
```

### Schritt 3: paths-Filter erweitern (oben in der Datei)

```yaml
# Im on.pull_request.paths-Block sicherstellen, dass auch
# frontend/tests/e2e/report-modes.spec.ts den Job triggert.
# Der bestehende Filter 'frontend/tests/e2e/**' deckt das schon ab —
# falls verfeinert wurde, hier prüfen.
```

### Schritt 4: Smoke-Lauf simulieren

```bash
# Workflow-Syntax validieren.
cd /Volumes/T7/Projekte/agora-worktrees/mai-01
npx --yes @action-validator/cli@latest \
  .github/workflows/e2e-smokes.yml
```

## Verifikation

```bash
# 1) Workflow listet 4 Jobs.
grep -E "^  [a-z-]+-smoke:" .github/workflows/e2e-smokes.yml | wc -l
# Erwartet: 4

# 2) report-modes-smoke ist drin.
rg -n "report-modes-smoke:" .github/workflows/e2e-smokes.yml
# Erwartet: 1 Match

# 3) actionlint
gh workflow view e2e-smokes.yml || echo "Workflow noch nicht auf main — push first."
```

## Warum?

P4.4 ist laut PLAN.md §5.4 der letzte v1.0-Output-Vertrag-Slice. Der Smoke-Test ist vorhanden (`frontend/tests/e2e/report-modes.spec.ts`), aber bisher führt keine CI-Pipeline ihn aus — die Mode-Verdrahtung wird also nicht regression-getestet.

## Nächste Schritte

1. Worklog `docs/2026-05-14-mai-01-arbeitsprotokoll.md` schreiben.
2. CHANGELOG `[Unreleased]` ergänzen: `MAI-01 · P4.4 Mode-Smokes als CI-Job verdrahtet (e2e-smokes.yml::report-modes-smoke).`
3. `/agora-mai-next-task` für MAI-04 starten.
