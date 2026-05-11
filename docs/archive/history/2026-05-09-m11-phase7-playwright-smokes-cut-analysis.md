# M11 Phase 7 / M11.4 — Playwright-Smokes Schnittanalyse

**Stand:** 2026-05-09  
**Slice:** M11.4 (Phase 7 in der `PLAN.md` `Arbeitsreihenfolge`)  
**Quelle:** [`docs/agora_next_steps_after_p0_2026-05-07.md`](agora_next_steps_after_p0_2026-05-07.md) § P1-D · [`PLAN.md`](../PLAN.md) `Aktiv offen` M11.4

## Ziel

Drei stabile End-to-End-Smokes für den Agora-Kernworkflow, ausführbar in CI, **ohne** zur 90-Test-Pyramide zu wachsen. Pflichtumfang aus PLAN.md:

1. **Health/Login** — App lädt, `/health` erreichbar, Auth-Token funktioniert
2. **Upload + Graph** — kleines Testdokument hochladen, Graph-Erstellung starten, Status `READY` prüfen
3. **Minimalreport** — vorhandenen kleinen Fixture-Run nutzen, Report generieren, Basisbestandteile im UI prüfen

## Methodik

Code-Verifikation am 2026-05-09 mit `code-review-graph` (4 653 Knoten, 35 529 Kanten) + `grep`. Endpoints, Auth-Flows, existing Smoke-Skripte und Fixture-Standorte gegen den realen Code-Stand 2d42962 (post-M11.8b) abgeglichen.

---

## 1 · Berührungspunkte (Endpoints + Frontend-Pfade)

### Smoke 1 (Health/Login)

| Layer | Berührung | Quelle |
|---|---|---|
| Reverse-Proxy | `GET /healthz` (statisches `200 ok`) | `deploy/nginx/agora.conf` |
| App-Level | `GET /health` (Flask-route ohne Auth) | `backend/app/__init__.py:243` |
| API | `GET /api/status` (Auth-pflichtig, returnt `auth_mode: "single_user_token"`) | `backend/app/api/status.py:160` |
| Auth | `POST /api/auth/ticket` (signed ticket für SSE/Downloads) | `backend/app/api/auth.py:66` |
| Frontend | App-Mount, Auth-Header-Setup, Smoke-Reload | `frontend/src/main.ts`, `frontend/src/api/stream.ts` |

### Smoke 2 (Upload + Graph)

| Layer | Berührung | Quelle |
|---|---|---|
| API | `POST /api/graph/ontology/generate` (Rate-Limit-gegated, M10.5) | `backend/app/api/graph.py::generate_ontology` |
| Backend-Service | `OntologyGenerator` + Neo4j-Storage | `backend/app/services/ontology_generator.py` |
| Frontend | Step1Upload-Wizard + Step2EnvSetup (Markdown-Upload, Status-Polling) | `frontend/src/components/Step1Upload.vue`, `Step2EnvSetup.vue` |
| Storage | `create_graph` in Neo4j | `backend/app/storage/graph_storage.py` |
| LLM | Ollama-Call für Entity-Extraction | `app.utils.llm_client` |

### Smoke 3 (Minimalreport)

| Layer | Berührung | Quelle |
|---|---|---|
| API | `POST /api/report/generate`, `POST /api/report/generate/status`, `GET /api/report/<id>/sections` | `backend/app/api/report.py:74,226,649` |
| Backend-Service | `ReportAgent.plan_outline` + ReACT-Loop + Section-Generation | `backend/app/services/report_agent/{agent,planning,sections,workflow}.py` |
| LLM | mehrere Ollama-Calls (Outline + 11 Sections + ReACT-Tool-Calls) | `app.utils.llm_client` |
| Frontend | Step4Report-Wizard | `frontend/src/components/Step4Report.vue` |

**Folgerung:** Smoke 2 und 3 brauchen einen **echten oder gemockten LLM-Pfad**. Ein Smoke ohne LLM-Pfad ist methodisch wertlos für das Output-Vertrag-Hardening (M11.8) und würde den Bewertungs-Befund 5,8/10 nicht adressieren. Die LLM-Mock-Strategie ist daher vor M11.4b/c zu klären.

---

## 2 · Backend-Stack-Requirements je Smoke

| Smoke | Flask | Neo4j | Redis | Ollama / LLM | gevent | nginx |
|---|---|---|---|---|---|---|
| 1 Health/Login | ✅ Pflicht | ❌ optional | ❌ optional | ❌ nicht nötig | ✅ realer Modus | ✅ Reverse-Proxy |
| 2 Upload+Graph | ✅ Pflicht | ✅ Pflicht | ✅ Pflicht (Pub/Sub-IPC) | ✅ Pflicht (Mock vertretbar) | ✅ realer Modus | ✅ Reverse-Proxy |
| 3 Minimalreport | ✅ Pflicht | ✅ Pflicht | ✅ Pflicht | ✅ Pflicht (Mock vertretbar) | ✅ realer Modus | ✅ Reverse-Proxy |

Damit ist der reale Test-Stack identisch mit dem in `docker-image.yml::prod-proxy-smoke` schon laufenden Compose-Setup (`docker-compose.yml` + `docker-compose.prod.yml` + Reverse-Proxy-Overlay). **Reuse statt parallel** — kein zweiter Compose-Stack.

---

## 3 · Vorhandene Bausteine (was wir NICHT neu bauen)

| Vorhanden | Pfad | Wiederverwendung |
|---|---|---|
| Compose-Stack | `docker-compose.yml`, `docker-compose.prod.yml`, `deploy/compose/docker-compose.prod-with-proxy.yml` | E2E-Stack 1:1 wie `prod-proxy-smoke` |
| Smoke-Skript | `scripts/verify-deploy.sh` (144 LOC, M11 Phase 1 Follow-up) | Health + Auth-Ticket + DOMPurify-Bundle-Vertrag — **wird nicht ersetzt**, Playwright ergänzt UI-Smoke |
| `/healthz` | `deploy/nginx/agora.conf` | Reverse-Proxy-Health-Probe |
| `/health` | `backend/app/__init__.py:243` | App-Level-Health |
| `POST /api/auth/ticket` | `backend/app/api/auth.py:66` | Signed-Ticket-Issue (Auth-Smoke) |
| Eval-Fixtures | `backend/tests/eval/fixtures/{good,bad}/` | Source für Upload-Smoke (`good/<scenario>/seed.md`) |
| Output-Contract-Snapshot | `backend/tests/eval/snapshots/output-contract-required-sections.txt` (M11.8b) | Smoke-3-Assertion: 11 Pflichtabschnitt-Header im Report-UI |

---

## 4 · Architektur-Entscheidungen (vorgeschlagen)

### 4.1 Workflow-Modell

**Vorschlag:** **Separater Workflow** `.github/workflows/e2e-smokes.yml`, NICHT `ci.yml`-Erweiterung.

**Begründung:**
- Compose-Stack-Boot (~3 min) + 3 Playwright-Smokes (~5 min) ≈ 8–12 min. PR-Pipeline würde überlastet (Konsens analog `docker-image.yml::prod-proxy-smoke`, der seit 2026-05-06 nur auf `main`/Tags/`workflow_dispatch`/`release/**`/`rc/**` läuft).
- E2E-Failures sollen Release blocken, aber nicht jeden Feature-PR — Auth-Modell, Bundle-Token-Gate und Coverage-Gates fangen sub-E2E-Risiken bereits ab.

**Trigger:**
```yaml
on:
  push:
    branches: [main]
  pull_request:
    branches: [main]
    paths:
      - 'frontend/src/**'
      - 'frontend/tests/e2e/**'
      - 'frontend/playwright.config.ts'
      - 'backend/app/api/**'
      - 'backend/app/services/report_agent/**'
      - 'backend/app/utils/llm_client.py'
      - 'backend/app/utils/llm_e2e_stub.py'
      - 'docker-compose*.yml'
      - 'Dockerfile'
      - 'deploy/**'
      - '.github/workflows/e2e-smokes.yml'
  workflow_dispatch:
  schedule:
    - cron: '0 3 * * *'  # nightly
```

PR-Trigger hier mit `paths`-Filter — nur wenn der E2E-Pfad realistisch betroffen ist, sonst `paths-ignore` analog Doku-Slices. Wichtig: Die Test-Files (`frontend/tests/e2e/**`), die Playwright-Konfig (`playwright.config.ts`), der LLM-Stub-Pfad (`backend/app/utils/llm_e2e_stub.py`) und der Workflow selbst (`e2e-smokes.yml`) müssen mit drin sein — sonst wird ein Edit am Test- oder Stub-Verhalten nie via E2E-Smoke validiert.

### 4.2 Backend-Stack-Strategie

**Vorschlag:** Reuse `scripts/verify-deploy.sh`-Compose-Stack über ein dediziertes Setup-Skript (`scripts/e2e-up.sh` / `scripts/e2e-down.sh`), **nicht** über Playwrights `webServer`-Hook.

**Begründung gegen `webServer`-Hook:**

`docker compose up -d` startet im Hintergrund und gibt sofort die Kontrolle zurück. Playwright kann den Lebenszyklus dieser Container nicht erkennen oder verwalten — der Prozess bleibt nach `playwright test` aktiv, und Re-Runs treffen auf einen schon laufenden Stack mit unvollständig gecleantem State.

**Alternative Pattern (verbindlich für M11.4a):**

```ts
// playwright.config.ts
export default defineConfig({
  globalSetup: './tests/e2e/global-setup.ts',
  globalTeardown: './tests/e2e/global-teardown.ts',
  use: { baseURL: process.env.AGORA_E2E_BASE_URL ?? 'http://127.0.0.1:80' },
  // KEIN webServer-Hook
});
```

`global-setup.ts` ruft `bash scripts/e2e-up.sh` (Compose-Up + Wait-for-Health-Probe), `global-teardown.ts` ruft `bash scripts/e2e-down.sh` (Compose-Down inkl. Volumes). Damit ist der Container-Lifecycle deterministisch und bei Test-Abbruch (Ctrl-C, CI-Timeout) sauber abgewickelt.

**baseURL-Strategie (Localhost-Falle):**

| Umgebung | baseURL | Begründung |
|---|---|---|
| Lokal-Entwickler (macOS/Linux) | `http://127.0.0.1:${AGORA_PROXY_PORT:-80}` | Reverse-Proxy bindet Default auf Port 80, Override via `.env` |
| GitHub Actions Runner (Ubuntu) | `http://127.0.0.1:${AGORA_PROXY_PORT:-80}` | Stack läuft direkt auf dem Runner, kein Container-im-Container |
| Playwright IM Container (z.B. `mcr.microsoft.com/playwright`) | `http://host.docker.internal:${AGORA_PROXY_PORT:-80}` | Docker-internes DNS; macOS/Windows out-of-the-box, Linux braucht `--add-host=host.docker.internal:host-gateway` |

baseURL ist immer aus `process.env.AGORA_E2E_BASE_URL` zu lesen, mit `127.0.0.1`-Default. Das macht den späteren Container-Modus-Schwenk eine Env-Variable, kein Code-Change.

**LLM-Mock:** **Neu zu bauen,** aber **getrennt** vom Production-Code.

Statt einer Verzweigung in `app.utils.llm_client.chat_json` (vermischt Test-Logik mit Prod, Risiko unbeabsichtigter Aktivierung in Prod):

- Neue Datei `backend/app/utils/llm_e2e_stub.py` mit deterministischem Stub.
- Neue Provider-Schicht: `app.utils.llm_client._select_backend()` returnt entweder den echten Ollama/OpenAI-Backend oder das Stub-Backend.
- Stub-Backend wird **ausschließlich** aktiviert, wenn ALLE drei Bedingungen erfüllt sind:
  1. `os.environ.get("AGORA_E2E_LLM_MODE") == "stub"`
  2. `current_app.debug` oder `app.config["TESTING"]` ist `True` (nicht in Prod-Mode)
  3. `os.environ.get("FLASK_ENV", "production") != "production"`
- Bei Prod-Default und gesetztem `AGORA_E2E_LLM_MODE=stub` → Logger-Error + Fallback auf echten Backend (fail-safe).

**Out-of-Scope für M11.4a (Health):** kein LLM-Mock nötig.  
**In-Scope für M11.4b/c:** LLM-Stub als eigener Sub-Slice **vor** M11.4b — sonst nondeterministisch.

### 4.3 Auth-Setup

**Vorschlag:**
- `AGORA_AUTH_TOKEN` als CI-Secret + lokaler Default `e2e-test-token-fixed-for-ci`
- Playwright `globalSetup` injiziert Token via `localStorage.setItem('agora_token', ...)` **vor** dem ersten Page-Load — analog zum bestehenden Frontend-Auth-Flow
- Bundle-Token-Gate `ALLOW_BUILD_TIME_TOKEN=false` bleibt hart (Phase 1 Default), Token kommt nicht ins Bundle, sondern via Browser-Storage

**Signed-Ticket-Flow (für SSE-Smokes in 4b/c):** Smoke ruft `POST /api/auth/ticket` mit Bearer-Token auf, nutzt den `?ticket=…` für SSE-Streams.

### 4.4 Fixture-Strategie

| Fixture | Quelle | Verwendung |
|---|---|---|
| Markdown-Upload (Smoke 2) | `backend/tests/eval/fixtures/good/<scenario>/seed.md` | re-use, gleiche Quelle wie eval-baselines |
| Test-Token | CI-Secret + lokaler Default | env `AGORA_AUTH_TOKEN` |
| Erwartete Section-Header (Smoke 3) | `backend/tests/eval/snapshots/output-contract-required-sections.txt` (M11.8b) | UI-Assertion: alle 11 Header sichtbar |

**Kein neuer Eval-Korpus.** Die externen Bewertungs-Files (`agora_1.pdf`, `evidence.json`) bleiben Out-of-Scope, falls sie überhaupt eingecheckt werden.

### 4.5 Browser-Strategie

**Chromium-only** für M11.4. Firefox/WebKit erst, wenn Smokes stabil laufen und Cross-Browser-Bug-Reports auftauchen. Drei Smokes × ein Browser = drei Smokes. Drei Smokes × drei Browser = neun = anfangende Test-Pyramide.

### 4.6 Playwright-Verzeichnis

```
frontend/
├── playwright.config.ts          # NEU — globalSetup/globalTeardown statt webServer
├── tests/
│   └── e2e/
│       ├── fixtures/
│       │   └── seed.example.md   # Symlink zu backend/tests/eval/fixtures/good/.../seed.md ODER kopiert
│       ├── helpers/
│       │   ├── auth.ts           # localStorage-Setup, Bearer-Header
│       │   └── stack.ts          # Health-Probe, Backend-Ready-Check
│       ├── global-setup.ts       # bash scripts/e2e-up.sh + wait-for-health
│       ├── global-teardown.ts    # bash scripts/e2e-down.sh
│       ├── health.spec.ts        # M11.4a
│       ├── upload-graph.spec.ts  # M11.4b
│       └── minimal-report.spec.ts # M11.4c
└── package.json                   # devDeps: @playwright/test, playwright

scripts/
├── e2e-up.sh                     # NEU — docker compose up -d + wait-for-/healthz
└── e2e-down.sh                   # NEU — docker compose down -v
```

---

## 5 · Cut-Vorschlag · Sub-Slices

### M11.4a · Setup + Health-Smoke

**Aufwand:** M  
**Files:**
- `frontend/package.json` — `@playwright/test`, `playwright` als devDeps
- `frontend/playwright.config.ts` — `globalSetup`/`globalTeardown`-Hooks (kein `webServer`), baseURL aus `process.env.AGORA_E2E_BASE_URL ?? 'http://127.0.0.1:80'`, Chromium-only, 1 Worker, 0 Retries
- `frontend/tests/e2e/global-setup.ts` + `global-teardown.ts`
- `scripts/e2e-up.sh` (Compose-Up + Health-Wait via `/healthz`-Polling, kein `sleep`)
- `scripts/e2e-down.sh` (Compose-Down inkl. `-v` für Volume-Cleanup)
- `frontend/tests/e2e/helpers/auth.ts` + `helpers/stack.ts`
- `frontend/tests/e2e/health.spec.ts` — 4 Assertions:
  1. `GET /healthz` → 200 (Reverse-Proxy)
  2. `GET /health` → 200 (App)
  3. App-Mount lädt Title + Hero-Element
  4. `GET /api/status` → 200 + `auth_mode: "single_user_token"` mit Test-Token
- `.github/workflows/e2e-smokes.yml` — Workflow-Skelett mit `health.spec.ts` only
- `docs/2026-05-09-m11-4a-playwright-setup-arbeitsprotokoll.md`
- `CHANGELOG.md` `[Unreleased]`
- `docs/status.md` (sync-status.sh-Pflicht)

**Akzeptanz:**
- `npx playwright test` lokal grün gegen `docker compose -f docker-compose.yml -f docker-compose.prod.yml`
- CI-Job grün auf Push:main
- PR-Trigger mit `paths`-Filter konfiguriert
- Schema-Drift clean, kein Layer-0-Touch

**Subagent:** `agora-frontend-worker` (Sonnet) — Vue/Vite-Stack, Playwright-Bibliothek, Frontend-Test-Hooks. Lead-Opus für CI-yml-Sanity-Check (separate Workflow-Datei).

### M11.4b-pre · LLM-Stub-Modus

**Aufwand:** S-M  
**Begründung:** Nondeterministische LLM-Calls in CI sind tot. Ohne Stub kein Smoke 2/3.  
**Files:**
- `backend/app/utils/llm_client.py` — neuer Branch `if os.environ.get("AGORA_E2E_LLM_MODE") == "stub": return _e2e_stub_response(...)`
- `backend/app/utils/llm_e2e_stub.py` (NEU) — deterministische Outline + Section-Bodies + ReACT-Tool-Returns
- Tests in `backend/tests/test_llm_e2e_stub.py` — pinnen die Stub-Antworten

**Subagent:** `agora-refactor-worker` (Sonnet).

### M11.4b · Upload + Graph-Smoke

**Aufwand:** M  
**Files:**
- `frontend/tests/e2e/upload-graph.spec.ts`:
  1. Auth-Setup
  2. Step1Upload-Markdown-Drop (Fixture aus `tests/eval/fixtures/good/`)
  3. `POST /api/graph/ontology/generate` triggern
  4. Status-Polling bis `READY`
  5. UI: Graph-Knoten ≥ 1 sichtbar
- `e2e-smokes.yml` Job-Erweiterung um `upload-graph.spec.ts` mit `AGORA_E2E_LLM_MODE=stub`-Env

**Subagent:** `agora-frontend-worker` (Sonnet).

### M11.4c · Minimalreport-Smoke

**Aufwand:** L  
**Files:**
- `frontend/tests/e2e/minimal-report.spec.ts`:
  1. Vor-bestehender Graph-State (entweder via Fixture-Inject oder via Smoke-2-Output)
  2. `POST /api/report/generate` triggern
  3. Status-Polling bis `READY` (mit Timeout 5 min im Stub-Modus)
  4. UI: Step4Report rendert alle 11 Sections aus Output-Contract-Snapshot
  5. Assertion: Persona-Tabelle ≥ `MIN_PERSONA_TABLE_ROWS` (50, wenn Stub mit Vollumfang)

**Subagent:** `agora-frontend-worker` (Sonnet) + Lead-Opus für Stub-Vertrag-Sanity.

---

## 6 · Risiken & Out-of-Scope

| Risiko | Bewertung | Mitigation |
|---|---|---|
| CI-Run-Time > 12 min | mittel | PR-Trigger mit `paths`-Filter; nightly-Schedule für volle Suite |
| Flaky Tests (race conditions) | hoch | strict `await expect().toBeVisible()` + condition-based-waiting (kein `setTimeout`); 0 Retries als Default — flaky test = bug |
| LLM-Stub driftet von echtem LLM | mittel | Stub-Antworten gegen `output-contract-required-sections.txt` snapshot-pinnen |
| Neo4j-Container braucht > 60 s zum Starten | mittel | `wait_for_neo4j` in `helpers/stack.ts` mit polling, kein hardcoded sleep |
| Bundle-Token-Gate vs. E2E-Auth | gelöst | Token via localStorage, NICHT via VITE_AGORA_TOKEN |
| Cross-Browser-Drift | niedrig (out of scope) | Chromium-only, Firefox/WebKit erst bei konkretem Bedarf |

**Out-of-Scope dieses Slices (Phase 7 als Ganzes):**
- Persona-Review-UI-Smokes (Layer 8 separat)
- Compare-API-Smokes (Layer 7 #66/#67)
- Performance-Tests (Lighthouse, axe)
- Visual-Regression-Tests (Percy / Chromatic)
- Mobile-Viewport-Smokes
- Multi-User-Konkurrenz-Smokes (Single-User-Modell laut ADR-0001)

---

## 7 · Reihenfolge der PRs

1. **PR (dieser Slice):** Phase-7-Schnittanalyse als Markdown
2. **PR M11.4a:** Setup + Health-Smoke (M, agora-frontend-worker)
3. **PR M11.4b-pre:** LLM-Stub-Modus (S-M, agora-refactor-worker)
4. **PR M11.4b:** Upload+Graph-Smoke (M, agora-frontend-worker)
5. **PR M11.4c:** Minimalreport-Smoke (L, agora-frontend-worker + Lead-Opus)

Damit ist Phase 7 in **5 Sub-Slices** zerlegt, jeder einzeln reviewbar und FF-mergebar. Plan-Order ggf. mit M11.4d für Coverage-Anhebung kombinierbar, aber bewusst getrennt halten.

---

## 8 · Akzeptanz dieses Schnittanalyse-Slices

- [x] Markdown-only, kein Code-Change
- [x] Endpoints + Auth-Flow gegen realen Code-Stand verifiziert
- [x] LLM-Stub als eigener Sub-Slice identifiziert (M11.4b-pre)
- [x] Wiederverwendung von `verify-deploy.sh` + Compose-Stack vorgegeben
- [x] PR-Trigger-Strategie analog `docker-image.yml::prod-proxy-smoke` festgehalten
- [x] Fixture-Quelle (`tests/eval/fixtures/good/`) referenziert
- [x] 5-PR-Cut für Phase 7 mit Aufwand und Subagent-Zuordnung

---

**Verbindlich für Folge-Slices:** Diese Schnittanalyse ist Vertrag für M11.4a–c. Abweichungen sind in einem späteren Schnittanalyse-Update zu dokumentieren, nicht stillschweigend zu vollziehen.
