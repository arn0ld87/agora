# Arbeitsprotokoll M11.4a — Playwright-Setup + Health-Smoke

**Stand:** 2026-05-09
**Slice:** M11.4a — Playwright-Setup + Health-Smoke
**Vertrag:** Schnittanalyse PR #337 §4 + §5 (`docu/2026-05-09-m11-phase7-playwright-smokes-cut-analysis.md`)
**Branch:** `feat/m11-4a-playwright-setup-health`

---

## Geänderte / Neue Dateien

| Datei | Status | Beschreibung |
|---|---|---|
| `frontend/package.json` | geändert | `@playwright/test ^1.49.0` + `playwright ^1.49.0` als devDeps |
| `frontend/package-lock.json` | geändert | npm-Lock nach `npm install --package-lock-only` |
| `frontend/playwright.config.ts` | NEU | globalSetup/globalTeardown, baseURL aus env, Chromium-only, 1 Worker, 0 Retries |
| `frontend/tsconfig.playwright.json` | NEU | Separate TS-Konfiguration für E2E: CommonJS-Module + Node-Auflösung, damit `__dirname` in globalSetup/globalTeardown korrekt kompiliert |
| `frontend/tests/e2e/global-setup.ts` | NEU | Ruft `scripts/e2e-up.sh` auf; AGORA_E2E_SKIP_STACK-Guard |
| `frontend/tests/e2e/global-teardown.ts` | NEU | Ruft `scripts/e2e-down.sh` auf; non-fatal error handling |
| `frontend/tests/e2e/helpers/auth.ts` | NEU | `injectAuthToken` (localStorage) + `bearerHeader`; STORAGE_KEY='agora_token' verifiziert |
| `frontend/tests/e2e/helpers/stack.ts` | NEU | `probeBackendHealth` via Playwright-request-API |
| `frontend/tests/e2e/health.spec.ts` | NEU | 4 Assertions: /healthz, /health, SPA-Mount, /api/status |
| `scripts/e2e-up.sh` | NEU | Compose-Up + Health-Polling via /healthz, executable |
| `scripts/e2e-down.sh` | NEU | Compose-Down -v, executable |
| `.github/workflows/e2e-smokes.yml` | NEU | CI-Workflow mit paths-Filter, workflow_dispatch, nightly-Schedule |
| `CHANGELOG.md` | geändert | M11.4a-Eintrag unter [Unreleased] > Added |
| `docu/STATUS.md` | geändert | sync-status.sh --check (kein Drift) |

---

## Architektur-Entscheidungen (Schnittanalyse §4 1:1 umgesetzt)

### globalSetup/globalTeardown statt webServer-Hook (§4.2)

`docker compose up -d` liefert sofort die Kontrolle zurück — Playwright kann den Container-Lifecycle nicht verwalten. Bei Abbruch (Ctrl-C, CI-Timeout) bliebe der Stack aktiv und verunreinigt Folge-Runs. Die globalSetup/globalTeardown-Pattern kapseln Lifecycle deterministisch.

### baseURL aus `process.env.AGORA_E2E_BASE_URL ?? 'http://127.0.0.1:80'` (§4.2 Localhost-Falle)

Kein hartkodiertes `localhost` oder `:8080`. `127.0.0.1` als Loopback-Literal ist unter macOS und Linux einheitlich. Override per env-Variable macht den späteren Container-Modus-Schwenk zu einer Env-Variable ohne Code-Change.

### Chromium-only, 1 Worker, 0 Retries (§4.5)

Firefox/WebKit erst bei konkreten Cross-Browser-Bug-Reports. 0 Retries ist bewusst: Flaky Test = Bug, nicht Retry-Fall.

### Auth via localStorage, NICHT VITE_AGORA_TOKEN (§4.3)

Bundle-Token-Gate Phase 1 (`ALLOW_BUILD_TIME_TOKEN=false`) bleibt hart. Token kommt ausschließlich via `localStorage.setItem('agora_token', ...)` — verifiziert gegen `frontend/src/api/index.ts:41` wo `window.localStorage.getItem('agora_token')` der primäre Auth-Pfad ist.

### tsconfig.playwright.json (Extra-Entscheidung, nicht in §4 spezifiziert)

Die Haupt-tsconfig nutzt `"module": "ESNext"` + `"moduleResolution": "Bundler"` — in diesem Modus ist `__dirname` nicht definiert. Playwright-interne TS-Transformation erwartet CommonJS-kompatiblen Code für globalSetup/globalTeardown. Eine dedizierte `tsconfig.playwright.json` mit `"module": "CommonJS"` + `"moduleResolution": "Node"` löst das ohne die Haupt-tsconfig anzufassen. Playwright greift die Konfig über `tsconfig`-Option in `defineConfig` auf.

---

## Auth-Storage-Key-Verifikation

```
grep -rn "agora_token\|localStorage.*token\|getItem.*token" frontend/src/
```

Ergebnis: `frontend/src/api/index.ts:41` — `window.localStorage.getItem('agora_token')` ist der primäre Storage-Pfad. Der Key `agora_token` ist identisch mit `STORAGE_KEY` in `helpers/auth.ts`.

---

## SPA-Mount-Anker (Test 3)

Gewählt: `page.locator('#app')`.

Begründung: `frontend/index.html:27` enthält `<div id="app"></div>`. `frontend/src/main.ts:17` mountet via `app.mount('#app')`. Kein data-testid auf dem Root-Element — der `#app`-Selektor ist die stabilste verfügbare Option und wird durch Vue garantiert befüllt, sobald die App gemountet hat. Ein leeres `#app` würde auf einen Mount-Fehler hinweisen.

---

## Lokale Verifikation (Schritt 9 — Docker-Stack)

Nicht durchgeführt. Der Docker-Stack unter macOS benötigt laufende Docker-Desktop-Instanz mit Port-80-Binding. CI ist der erste echte Run. Alle anderen Verifikationsschritte (Bash-Syntax, Playwright --list, npm-Lint, Typecheck, Vitest, Schema-Drift, Backend-Sanity) wurden lokal grün bestätigt.

---

## Out-of-Scope

- M11.4b-pre: LLM-Stub-Modus (`backend/app/utils/llm_e2e_stub.py`) — separater Sub-Slice vor M11.4b
- M11.4b: Upload + Graph-Smoke (`frontend/tests/e2e/upload-graph.spec.ts`)
- M11.4c: Minimalreport-Smoke (`frontend/tests/e2e/minimal-report.spec.ts`)
- Kein Backend-Code geändert
- Kein Layer-0-Touch (Pydantic-Contracts, JSON-Schemas unangetastet)

---

## Verifikations-Ergebnisse

| Schritt | Ergebnis |
|---|---|
| Schema-Drift clean | ja — `git diff --exit-code schemas/` sauber |
| Frontend-Lint | npm run lint — Exit 0 |
| Frontend-Typecheck | npm run typecheck — Exit 0 |
| Frontend-Tests (Vitest) | alle bestehenden Tests grün |
| Backend-Contracts-Import | OK |
| Backend-Schema-Dump | kein Drift |
| Ruff | clean |
| Voice-Lint | clean |
| STATUS.md --check | Exit 0 |
| Playwright --list | health.spec.ts: 4 Tests erkannt |
| Bash-Skript-Syntax | `bash -n` OK für beide Skripte |
| Executable-Bit | gesetzt + git-index getrackt |
| Lokaler Stack-Smoke | nicht durchgeführt (CI ist erster Run) |
