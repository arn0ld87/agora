# Agora — Status (Single Source of Truth)

Stand: 2026-05-10

**Aktualisiert via `scripts/sync-status.sh`.** README, CLAUDE.md und ROADMAP verweisen auf diese Datei — Versionsstände und Test-Counts werden nicht mehr inline kopiert.

## Versionen

<!-- BEGIN_AUTOGEN_VERSIONS -->
| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.9.1-dev |
| Frontend | `frontend/package.json` | 0.9.1-dev |
| Root | `package.json` | 0.9.1-dev |
<!-- END_AUTOGEN_VERSIONS -->

## Tests

<!-- BEGIN_AUTOGEN_TESTS -->
| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 1738 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Test-Files | 47 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' -o -name '*.test.ts' -o -name '*.test.js' \)` |
<!-- END_AUTOGEN_TESTS -->

_Hinweise: 2 Redis-Integrationstests skippen sauber ohne `TEST_REDIS_URL` und sind in der Backend-Summe enthalten (sie zählen als collected, werden aber zur Laufzeit übersprungen)._
_Die Frontend-Zeile zählt Dateien, nicht einzelne Test-Cases. Gezählt werden Vitest-Pattern `*.spec.{js,ts}` und `*.test.{js,ts}`; pro Test-File laufen mehrere `it`-Blöcke. Die exakte Test-Case-Anzahl liefert `cd frontend && npx vitest list`._

## Backend-Coverage (M11.2)

Gemessen 2026-05-04 mit `uv run pytest --cov=app --cov-report=term -q` (1425 passed, 9 skipped, Marker `-m 'not llm'` aktiv).

| Scope | Coverage | Basis |
|---|---|---|
| `app/` gesamt | 55 % | 12 842 Statements, 5 733 missed |
| `app/services/` | 51 % | 6 964 Statements, 3 427 missed |

**Aktive CI-Schwelle: 55 %** (`--cov-fail-under=55` in `.github/workflows/ci.yml`).

Begründung der Schwellenwahl: Ist-Wert (61.41 %, gemessen 2026-05-10) liegt deutlich über der neuen Schwelle. Die PLAN-Default-Schwelle von 70 % ist vorerst nicht erreichbar, weil `app/services/simulation_runner.py` (809 Statements, 22 % Coverage) und `app/services/graph_tools.py` (667 Statements, 19 % Coverage) als OASIS-Integrationsschicht nur über vollständige Subprozess-Tests abdeckbar sind, die externe Ollama-Instanz und Neo4j voraussetzen. Diese Pfade sind mit `@pytest.mark.llm` markiert und laufen nicht in CI. Roadmap: monatlich +2 Punkte bis Ziel 85 %.

**Roadmap:**

| Datum | Schwelle | Notizen |
|---|---|---|
| 2026-05-04 | 53 % | Startwert (M11.2) |
| 2026-05-10 | 55 % | vorgezogen, Ist deckt (Followup-5 stabil) |
| 2026-06-10 | 57 % | +2 Punkte |
| 2026-07-10 | 59 % | +2 Punkte |
| … | … | monatlich +2 |
| Ziel | 85 % | Langfristziel |

Coverage-Report wird als CI-Artifact `backend-coverage` (14 Tage Retention) hochgeladen und kann von Codecov/Sonar konsumiert werden.

## Frontend-Coverage (M11.3)

Gemessen 2026-05-07 mit `npm run test:coverage` (`vite.config.js` include `src/**/*.{js,ts,vue}`, 43 Spec-Files, 449 Tests passed). Der vollständige `include`-Glob erfasst auch untestete Views (`Home.vue`, `MainView.vue`, `ReportView.vue`, `RunsView.vue`, `SimulationView.vue`, `InstructionView.vue`) — daher fallen die Zahlen niedriger aus als eine rein transitive Messung.

| Metrik | Coverage | Basis |
|---|---|---|
| Statements | 49.29 % | 2 446 / 4 962 |
| Branches | **38.01 %** | 1 304 / 3 430 |
| Functions | 38.23 % | 445 / 1 164 |
| Lines | 51.29 % | 2 296 / 4 476 |

**Aktive CI-Schwelle: 26 %** (alle vier Metriken, `thresholds` in `vite.config.js`). Angehoben 2026-05-10 (vorgezogen, war 2026-06-04 geplant). Ist-Werte 2026-05-10: statements=50.46 %, branches=39.56 %, functions=38.59 %, lines=52.50 % — alle vier deutlich über 26 %.

Historische Begründung der Schwellenwahl: Der M11.3-Startwert war `branches` mit 26.70 %. Dieser lag weit unter dem PLAN-Default von 60 %. Die Fallback-Formel `floor(Ist - 2) = floor(26.70 - 2) = 24` griff. Die 60 %-Marke ist vorerst nicht erreichbar, weil:

1. Fünf vollständig untestete Views-Dateien (`Home.vue`, `MainView.vue`, `ReportView.vue`, `RunsView.vue`, `SimulationView.vue`, `InstructionView.vue`) werden durch den `include`-Glob erfasst, aber haben 0 % Coverage — sie erfordern Playwright-E2E-Tests (M11.4).
2. `GraphCanvas.vue` und `GraphPanel.vue` haben 0 % Branches: Canvas-/WebGL-APIs sind in jsdom nicht verfügbar.
3. `Step2EnvSetup.vue` hat 9.52 % Branches (~200 Conditional-Zweige im Wizard-Flow).

Diese Lücken sind strukturell. Roadmap: monatlich +2 Punkte ab 2026-06-04 bis Ziel 80 %.

**Roadmap:**

| Datum | Schwelle | Notizen |
|---|---|---|
| 2026-05-04 | 24 % | Startwert (M11.3) |
| 2026-05-10 | 26 % | vorgezogen, Ist deckt (Followup-5 stabil) |
| 2026-06-10 | 28 % | +2 Punkte |
| 2026-07-10 | 30 % | +2 Punkte |
| … | … | monatlich +2 |
| Ziel | 80 % | Langfristziel (inkl. Playwright E2E, M11.4+) |

Coverage-Report wird als CI-Artifact `frontend-coverage` (14 Tage Retention) hochgeladen.

## Static-Analysis-Gates (Phase 2)

Stand 2026-05-07:

| Gate | Command | Status |
|---|---|---|
| Backend Types | `cd backend && uv run mypy app` | Pflicht in `ci.yml::backend` |
| Backend Lint | `cd backend && uv run ruff check .` | Ruff-Zielmenge `E/F/B/I/UP/SIM`, Phase-2-Baseline fuer bestehende Import-/pyupgrade-/simplify-Funde |
| Frontend Types | `cd frontend && npm run typecheck` (`vue-tsc --noEmit`) | Pflicht in `ci.yml::frontend` |
| Frontend Lint | `cd frontend && npm run lint` | Vue-SFC-`<script>`-Parsing via `@typescript-eslint/parser` |

TypeScript-Optionen: `allowJs=false`, weil unter `frontend/src/` kein JS-Restbestand vorhanden ist. `noUncheckedIndexedAccess` und `exactOptionalPropertyTypes` bleiben vorerst deaktiviert; ein Probelauf am 2026-05-07 erzeugte breite Folgefehler in API-Envelope, Step2-/Graph-Tests und Persona-Library-Composables.

## Layer-Status (Übersicht)

Verbindliche Detailtabelle und Layer-Semantik: [`CLAUDE.md` § Architektur-Layer](../CLAUDE.md#architektur-layer-status).

| Layer | Inhalt | Status |
|---|---|---|
| 0 | Pydantic-Contracts + Zod-Spiegel | grün |
| 1 | Backend-Hardening | grün |
| 2 | DACH-Voice + Glossar v1 | grün |
| 3 | Reader-Honesty | grün |
| 4 | Frontend strict-Zod | grün |
| 5 | Eval/Baseline-Suite | grün |
| 6 | Frontend-TypeScript-Migration | grün |
| 7–8 | Graph/Runs/Persona-Review | teilweise |
| 9 | Prod-Deployment | grün mit gehärtetem Release-Gate und Runtime-Image-Hardening — Reverse-Proxy ✅, gevent ✅, Bundle-Token-Gate ✅, `?token=`-Block ✅, signed-tickets-Frontend ✅, Prod-Stack-Smoke in CI ✅ (`docker-image.yml::prod-proxy-smoke` auf `main`, Tags `v*`, Branches `release/**` oder `rc/**`, PRs von `release/**` oder `rc/**` nach `main` und `workflow_dispatch`; normale Feature-PRs bleiben wegen ~30 min Laufzeit ausgenommen), finaler `prod`-Stage ohne Node/npm/curl ✅, `read_only: true` im Prod-Compose ✅, Auth-ADR ✅ (M10.4 Single-User-only-v1 Accepted). |
| 10 | Security Watchlist | grün — CVE-Monitor wöchentlich aktiv (`.github/workflows/cve-monitor.yml`), Hardstop 2026-07-30 verdrahtet, Dependency Review ✅, CodeQL ✅, GHCR Build-Provenance-Attestation ✅, SBOM-Artefakt ✅, Risk-Register mit Eskalationspfad. Issues #121–#126 weiter open bis Upstream patcht. |

## Aktuelles Milestone

**M9 abgeschlossen, M10 abgeschlossen.** Übergang zu M11.

Detail: [`PLAN.md § Status-Sync 2026-05-04`](../PLAN.md#status-sync-2026-05-04). Subagent-Mapping pro Slice: [`docu/plan.heuristic.md`](plan.heuristic.md).

**Erledigt (Code-verifiziert 2026-05-04):**
- F1 Reverse-Proxy (`deploy/nginx/`, `deploy/compose/docker-compose.prod-with-proxy.yml`)
- F2.1 Bundle-Token-Gate (`Dockerfile` `ALLOW_BUILD_TIME_TOKEN=false` Default)
- F2.2 `?token=` in Prod blockt (`backend/app/utils/auth.py`)
- F3 Gunicorn `-k gevent`
- SSE-Auth-Frontend auf signed tickets (`frontend/src/api/stream.ts`)
- M9.6 Prod-Stack-Smoke vorhanden und Release-Gate gehärtet (`docker-image.yml::prod-proxy-smoke` mit `AGORA_SKIP_EMBEDDING_PROBE=true`; läuft auf `main`, Tags `v*`, Branches `release/**` oder `rc/**`, PRs von `release/**` oder `rc/**` nach `main` und `workflow_dispatch`; normale Feature-PRs bewusst ausgenommen, Issue #276)
- M10.1/M10.2/M10.3 CVE-Monitor + Hardstop 2026-07-30 + Risk-Register-Eskalationspfad (`.github/workflows/cve-monitor.yml`, `docu/dependency-risk-register.md`)
- M10.4 Auth-Zielbild-ADR Single-User-only-v1 (`docu/decisions/0001-auth-model.md` Accepted) + Code-Update `_get_auth_mode()` returnt `"single_user_token"` + README/security-hardening Single-User-Block + Token-Rotation-Prozedur
- M10.5 Rate-Limits für `/api/auth/ticket`, Uploads (`/api/graph/ontology/generate`), Simulation-LLM-Trigger (`/api/simulation/generate-profiles`, `/api/simulation/prepare`) und Report-Trigger (`/api/report/generate`, `/api/report/chat`) (#302)
- M11.1 Evidence-Quality-Gate hard (`--soft` raus aus `contract-gates.yml`, Hard-Gate gegen `tests/eval/fixtures/good/`, Bad-Cases gepinnt durch Snapshot-Test)
- M11 Phase 1 Release-Gating gehärtet (`docker-image.yml` SHA-gepinnt, strikter Tag-Smoke, latest nur Default-Branch)
- M11 Phase 2 Static-Analysis-Gates (`mypy app` + `npm run typecheck` blockierend)
- M11 Phase 3 Runtime-Image-Hardening (Multi-Stage, slim ohne Node/npm/curl, `read_only: true`, 747 MB → 320 MB)
- M11 Phase 4 Supply Chain (`dependency-review.yml`, `codeql.yml`, Build-Provenance-Attestation, SPDX-JSON-SBOM)
- M11 Phase 5 (`simulation_runner.py`-Refactor, 5 PRs)
- M11 Phase 5b (`graph_tools.py`-Refactor, 3 PRs)
- M11.2 Backend-Coverage-Gate (`--cov-fail-under=55`, vorgezogen 2026-05-10 von 53 %)
- M11.3 Frontend-Coverage-Gate (Threshold 26 %, vorgezogen 2026-05-10 von 24 %)
- ADR-0001 Single-User-only-v1 Accepted (M10.4)
- M10.5 Rate-Limits (PRs #303–#306, Issue #302)

**Aktiv offen (nächste 3 Slices in Reihenfolge):**
1. P1-A Dependabot-Aufräumen — PR #323 (`mistune`) + PR #326 (`pygments`).
2. Phase 6 Contract-Generation + Status-Sync (Contract-Dump reproduzierbar, Zod-Spiegel CI-geprüft, `scripts/sync-status.sh` Pflicht).
3. Phase 7 / M11.4 Playwright-Smokes (Health/Login, Upload+Graph, Minimalreport).

Mittelfristig: M11.2/M11.3 Coverage-Schwellen-Anhebung (Backend 55 → 70 %, Frontend 26 → 60 %, monatlich +2), M11.5 Komplexitäts-Gate, M11.6 API-Envelope, F8 Hotspot-Split Frontend (#203). Phase 5/5b abgeschlossen 2026-05-08, #202 geschlossen 2026-05-05.

## Aktualisierungs-Protokoll

- 2026-05-08: M11 Phase 5 + Phase 5b — Hotspot-Refactors abgeschlossen. Phase 5 (`simulation_runner.py`): 5 PRs, Helfer `run_state_store`/`action_log_reader`/`monitor_thread`/`interview_client`/`process_manager` extrahiert (Commits ff52643, 2142e0a, b177cd9, ef9f5b6, db2c0f8). Phase 5b (`graph_tools.py`): 3 PRs, Helfer `graph_dtos`/`graph_reader`/`insight_forge_tool` extrahiert (Commits 8ce5ecb, 7abd3df, b8493b8). Verhalten unverändert, Tests grün. Arbeitsprotokolle unter `docu/2026-05-08-m11-phase5*-arbeitsprotokoll.md`.
- 2026-05-08: Doku-Sync — `AGENTS.md` Status-Zeile (Layer 9–10 grün, M11 Phase 1–5b durch), `CLAUDE.md` „Aktive Hot-Spots" auf realen M11-Stand, `PLAN.md` Status-Sync 2026-05-08 mit aktualisierter Erledigt-/Offen-Tabelle und neuer PR-Reihenfolge, `docu/STATUS.md` aktuelles Milestone auf Phase 6/7/CVE-Aufräumen.
- 2026-05-03: Sub-Slice 44 — STATUS.md inaugural, Test-Counts und Versionsstände zentralisiert, Inline-Zahlen aus README/CLAUDE.md entfernt, ROADMAP auf v0.9.0+ / 2026-05-03 geheben.
- 2026-05-04: F5 Doku-Sync (1) — Test-Counts auf 1370 (1330 → 1370 nach Layer-9-Slices), README inline-Zahl entfernt.
- 2026-05-04: Doku-Sync 2026-05-04 — `AGENTS.md` v0.6.0 → v0.9.0+, `CLAUDE.md` Layer-9-Hot-Spots auf realen Code-Stand, `PLAN.md` Status-Sync-Block, neue `docu/plan.heuristic.md` als Subagent-Routing-SSoT, User-Drop-Audit-Snapshots nach `docu/history/`.
- 2026-05-04: M9.6 Prod-Stack-Smoke — `docker-image.yml::prod-proxy-smoke` lief ab diesem Stand auch auf `pull_request: [main]` (Doku-PRs ausgeschlossen via `paths-ignore`). `scripts/verify-deploy.sh` smoket zusätzlich `/api/auth/ticket` via Proxy.
- 2026-05-04: M10.1/M10.2/M10.3 CVE-Monitor + Hardstop — Neuer Workflow `.github/workflows/cve-monitor.yml` läuft Mo 06:00 UTC `pip-audit --strict` ohne `--ignore-vuln` und schreibt das Ergebnis in `$GITHUB_STEP_SUMMARY`. Hardstop am 2026-07-30 verdrahtet: ab dann fail bei pip-audit-Findings. `docu/dependency-risk-register.md` um Eskalationspfad-Sektion (Vendoring / Soft-Fork / Replacement / Risikoakzeptanz-PR) und Upstream-Release-Watch-Spalte erweitert (die Owner-Spalte war bereits vorhanden). Layer 10 von „dokumentiert" auf „grün".
- 2026-05-04: M10.4 Auth-Zielbild-ADR — `docu/decisions/0001-auth-model.md` als **Proposed** angelegt mit drei Optionen (Single-User-only-v1 / HttpOnly-Session / Bearer+Refresh). Empfehlung: Option A (Single-User-only-v1 explizit machen). Begründung: Local-first ist Kernprinzip, Hauptangriffsvektoren sind bereits geschlossen (F2.1/F2.2/P0.2/S2/S3), v1.0-Termin erreichbar. Wartet auf User-Sign-off. Folge-Slices nach Accept: README/security-hardening-Update, `auth_mode`-Feld in `/api/status`, Token-Rotation-Prozedur. ADR-Index unter `docu/decisions/README.md` mit Konvention.
- 2026-05-04: M10.4-Followup — ADR-0001 von **Proposed** auf **Accepted** gehoben (User-Sign-off via Merge PR #277). `backend/app/api/status.py::_get_auth_mode()` returnt jetzt `"single_user_token"` statt `"token"` — der Prefix `single_user_` macht für Operatoren in `/api/status` sichtbar, dass Agora kein Multi-User-Modell hat. Tests in `tests/test_anonymous_in_healthcheck.py` angepasst.
- 2026-05-04: M11.2 Backend-Coverage-Gate — `pytest-cov>=5.0.0` in beide Dev-Dep-Listen (`[project.optional-dependencies] dev` + `[dependency-groups] dev`). `addopts` um `--cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=53` erweitert. Startschwelle 53 % (Ist 55 %, Formel `floor(Ist - 2)`; 70 %-PLAN-Default nicht erreichbar wegen OASIS-Integrationspfad ohne Ollama/Neo4j in CI). Coverage-Report als Artifact `backend-coverage` (14 Tage) in `ci.yml`. Coverage-Sektion in `docu/STATUS.md` mit Roadmap.
- 2026-05-04: M11.3 Frontend-Coverage-Gate — `@vitest/coverage-v8@4.1.5` in `devDependencies`. `package.json` `test:coverage`-Script neu; `check` auf `test:coverage` umgestellt; `test` bleibt schneller Gate-freier TDD-Pfad. `vite.config.js` Coverage-Block: provider v8, reporters text/lcov/html, include `src/**/*.{js,ts,vue}`, thresholds 24 % (alle vier Metriken). Startschwelle 24 % (Ist-Wert branches 26.70 % ist Bottleneck beim vollständigen `include`-Glob; Fallback-Formel `floor(Ist - 2) = 24`; 60 %-PLAN-Default nicht erreichbar wegen 6 untesteter Views + jsdom-inkompatibler Canvas/D3-Pfade). Coverage-Report als Artifact `frontend-coverage` (14 Tage) in `ci.yml`. Coverage-Sektion in `docu/STATUS.md` mit Roadmap.
- 2026-05-04: M10.4-Doku-Folge — README.md (DE+EN-Status-Block) auf Single-User-only mit Verweis auf ADR-0001 erweitert. `docu/security-hardening.md` neue Sektion „Auth-Modell v1.0" mit (a) Garantien-Liste (kein User-Konzept, kein Logout, kein Audit, kein Multi-User), (b) Was-schützt-was-nicht-Gegenüberstellung inkl. fehlender Rate-Limits als Hardstop bis M10.5, (c) Token-Rotation-Prozedur als 6-Schritt-Anleitung mit `curl`-Verifikation, (d) Trigger für ADR-Supersedes (Klassenraum, Public-Internet, Compliance), (e) Hardstops-Liste für v1.0. Layer-9 in STATUS damit final auf grün; v1.0-Auth-Story ist closed.
- 2026-05-05: Issue #276 Embedding-Probe-Skip — `AGORA_SKIP_EMBEDDING_PROBE=true` in `docker-image.yml::prod-proxy-smoke` eingeführt. `validate_embedding_configuration()` bekommt `skip_probe`-Parameter; bei gesetztem Flag läuft nur die statische KNOWN_EMBEDDING_DIMS-Validation, der Live-HTTP-Probe-Call gegen Ollama entfällt. Container startet im CI-Runner ohne Ollama sauber hoch. `continue-on-error: github.event_name == 'pull_request'`-Workaround aus PR-Trigger entfernt; Tag-Pushes bleiben lenient (externe Image-Pulls instabil).
- 2026-05-06: PR-Trigger für `docker-image.yml` bewusst pausiert. Grund: Docker-Image-Build + Reverse-Proxy-Smoke kostet pro PR-Iteration ca. 30 Minuten. Der Smoke bleibt für `main`/Tags/`workflow_dispatch` erhalten und muss vor dem finalen Release-Gate neu bewertet bzw. reaktiviert werden.
- 2026-05-06: M10.5 Rate-Limits abgeschlossen — app-seitige Fixed-Window-Limits für /api/auth/ticket, /api/graph/ontology/generate, /api/simulation/generate-profiles, /api/simulation/prepare, /api/report/generate und /api/report/chat. PRs #303–#306, Issue #302.
- 2026-05-06: Phase 1 Release-Gating gehärtet — `docker-image.yml` published nicht mehr via `success() || tag`-Bypass, Tag-Smokes sind strikt, `latest` wird nur auf dem Default-Branch gesetzt, der Smoke extrahiert `frontend/dist` aus dem gebauten Image, Actions sind SHA-gepinnt, globale Permissions bleiben bei `contents: read`, Publish-Rechte liegen nur am `publish`-Job. Release-/RC-Smokes laufen automatisch fuer `release/**` und `rc/**`; normale Feature-PRs bleiben aus Laufzeitgruenden ausgenommen.
- 2026-05-07: Phase 1 Follow-up — `scripts/verify-deploy.sh` prueft Compose-Container ueber Docker-Running-State aus `docker compose ps -a` mit Container-Namen-Fallback statt Health-Status und ersetzt den DOMPurify-Minifier-Grep durch Runtime-Bundle-Praesenz plus Source-Vertrag gegen `frontend/src/utils/markdown.ts`; Ziel ist ein stabiler `docker-image.yml::prod-proxy-smoke` auf `main`.
- 2026-05-07: Phase 1 Publish-Follow-up — `docker-image.yml::publish` trennt den harten GHCR-Publish vom optionalen Docker-Hub-Mirror. Beide bleiben smoke-gated; Docker-Hub-HTTP-400 bei grossen Layern blockiert den GHCR-Release-Pfad bis zur Phase-3-Image-Verkleinerung nicht mehr.
- 2026-05-07: Phase 2 Static-Analysis-Gates — `ci.yml::backend` blockiert auf `uv run mypy app`, `ci.yml::frontend` blockiert auf `npm run typecheck`. Backend-mypy startet mit strengem Contract-Scope und Legacy-Baseline fuer API-/Service-Pfade; Ruff ist auf `E/F/B/I/UP/SIM` konfiguriert mit expliziter Phase-2-Baseline fuer bestehende Altlasten. Frontend `allowJs=false`; `noUncheckedIndexedAccess`/`exactOptionalPropertyTypes` nach Probelauf noch nicht aktiviert.
- 2026-05-07: Phase 3 Runtime/Container-Hardening — `Dockerfile` trennt `frontend-build`, `backend-build` und finalen `prod`-Stage. Das finale Image basiert auf `python:3.11-slim`, enthaelt kein Node/npm/curl, installiert Runtime-Dependencies via `uv sync --frozen --no-dev` und nutzt einen Python-Healthcheck. `docker-compose.prod.yml` setzt `read_only: true` mit expliziten tmpfs-Schreibpfaden; DNS und Neo4j-Image-/Memory-Werte sind ueber `.env` parametrierbar. Lokale Image-Groesse: 747 MB -> 320 MB (-57 %).
- 2026-05-07: Phase 4 Supply Chain — `dependency-review.yml` blockiert PRs bei neuen High-severity Dependency-Funden, `codeql.yml` scannt Python und JavaScript/TypeScript auf `main`, PRs und woechentlichem Schedule. `docker-image.yml::publish` erzeugt nach GHCR-Push eine Build-Provenance-Attestation und ein SPDX-JSON-SBOM-Artefakt.
