# Agora — Status (Single Source of Truth)

Stand: 2026-05-04

**Aktualisiert via `scripts/sync-status.sh`.** README, CLAUDE.md und ROADMAP verweisen auf diese Datei — Versionsstände und Test-Counts werden nicht mehr inline kopiert.

## Versionen

| Komponente | Pfad | Version |
|---|---|---|
| Backend | `backend/pyproject.toml` | 0.9.0 |
| Frontend | `frontend/package.json` | 0.9.0 |
| Root | `package.json` | 0.9.0 |

## Tests

| Kategorie | Anzahl | Methode |
|---|---|---|
| Backend Tests (collected) | 1370 | `cd backend && uv run pytest --collect-only -q` |
| Frontend Spec-Files | 17 | `find frontend/src \( -name '*.spec.ts' -o -name '*.spec.js' \)` |

_Hinweise: 2 Redis-Integrationstests skippen sauber ohne `TEST_REDIS_URL` und sind in der Backend-Summe enthalten (sie zählen als collected, werden aber zur Laufzeit übersprungen)._
_Die Frontend-Zeile zählt Dateien, nicht einzelne Test-Cases. Pro Spec-File laufen mehrere `it`-Blöcke; die exakte Test-Case-Anzahl liefert `cd frontend && npx vitest list`._

## Backend-Coverage (M11.2)

Gemessen 2026-05-04 mit `uv run pytest --cov=app --cov-report=term -q` (1425 passed, 9 skipped, Marker `-m 'not llm'` aktiv).

| Scope | Coverage | Basis |
|---|---|---|
| `app/` gesamt | 55 % | 12 842 Statements, 5 733 missed |
| `app/services/` | 51 % | 6 964 Statements, 3 427 missed |

**Aktive CI-Schwelle: 53 %** (`--cov-fail-under=53` in `pyproject.toml`).

Begründung der Schwellenwahl: Ist-Wert (55 %) liegt unter der PLAN-Default-Schwelle von 70 %. Daher gilt die Formel `floor(Ist - 2) = floor(53)`. Die 70 %-Marke ist vorerst nicht erreichbar, weil `app/services/simulation_runner.py` (809 Statements, 22 % Coverage) und `app/services/graph_tools.py` (667 Statements, 19 % Coverage) als OASIS-Integrationsschicht nur über vollständige Subprozess-Tests abdeckbar sind, die externe Ollama-Instanz und Neo4j voraussetzen. Diese Pfade sind mit `@pytest.mark.llm` markiert und laufen nicht in CI. Roadmap: monatlich +2 Punkte ab 2026-06-04 bis Ziel 85 %.

**Roadmap:**

| Datum | Schwelle | Notizen |
|---|---|---|
| 2026-05-04 | 53 % | Startwert (M11.2) |
| 2026-06-04 | 55 % | +2 Punkte |
| 2026-07-04 | 57 % | +2 Punkte |
| … | … | monatlich +2 |
| Ziel | 85 % | Langfristziel |

Coverage-Report wird als CI-Artifact `backend-coverage` (14 Tage Retention) hochgeladen und kann von Codecov/Sonar konsumiert werden.

## Frontend-Coverage (M11.3)

Gemessen 2026-05-04 mit `npm run test:coverage` (`vite.config.js` include `src/**/*.{js,ts,vue}`, 24 Spec-Files, 170 Tests passed). Der vollständige `include`-Glob erfasst auch untestete Views (`Home.vue`, `MainView.vue`, `ReportView.vue`, `RunsView.vue`, `SimulationView.vue`, `InstructionView.vue`) — daher fallen die Zahlen niedriger aus als eine rein transitive Messung.

| Metrik | Coverage | Basis |
|---|---|---|
| Statements | 37.38 % | 1 570 / 4 199 |
| Branches | **26.70 %** | 837 / 3 134 |
| Functions | 27.14 % | 272 / 1 002 |
| Lines | 39.16 % | 1 478 / 3 774 |

**Aktive CI-Schwelle: 24 %** (alle vier Metriken, `thresholds` in `vite.config.js`).

Begründung der Schwellenwahl: Niedrigster Wert ist `branches` mit 26.70 %. Dieser liegt weit unter dem PLAN-Default von 60 %. Die Fallback-Formel `floor(Ist - 2) = floor(26.70 - 2) = 24` greift. Die 60 %-Marke ist vorerst nicht erreichbar, weil:

1. Fünf vollständig untestete Views-Dateien (`Home.vue`, `MainView.vue`, `ReportView.vue`, `RunsView.vue`, `SimulationView.vue`, `InstructionView.vue`) werden durch den `include`-Glob erfasst, aber haben 0 % Coverage — sie erfordern Playwright-E2E-Tests (M11.4).
2. `GraphCanvas.vue` und `GraphPanel.vue` haben 0 % Branches: Canvas-/WebGL-APIs sind in jsdom nicht verfügbar.
3. `Step2EnvSetup.vue` hat 9.52 % Branches (~200 Conditional-Zweige im Wizard-Flow).

Diese Lücken sind strukturell. Roadmap: monatlich +2 Punkte ab 2026-06-04 bis Ziel 80 %.

**Roadmap:**

| Datum | Schwelle | Notizen |
|---|---|---|
| 2026-05-04 | 24 % | Startwert (M11.3) |
| 2026-06-04 | 26 % | +2 Punkte |
| 2026-07-04 | 28 % | +2 Punkte |
| … | … | monatlich +2 |
| Ziel | 80 % | Langfristziel (inkl. Playwright E2E, M11.4+) |

Coverage-Report wird als CI-Artifact `frontend-coverage` (14 Tage Retention) hochgeladen.

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
| 9 | Prod-Deployment | grün — Reverse-Proxy ✅, gevent ✅, Bundle-Token-Gate ✅, `?token=`-Block ✅, signed-tickets-Frontend ✅, Prod-Stack-Smoke in CI ✅ (`docker-image.yml::prod-proxy-smoke` als strict PR-Gate dank AGORA_SKIP_EMBEDDING_PROBE), Auth-ADR ✅ (M10.4 Single-User-only-v1 Accepted). |
| 10 | Security Watchlist | grün — CVE-Monitor wöchentlich aktiv (`.github/workflows/cve-monitor.yml`), Hardstop 2026-07-30 verdrahtet, Risk-Register mit Eskalationspfad. Issues #121–#126 weiter open bis Upstream patcht. |

## Aktuelles Milestone

**M9 abgeschlossen, M10 abgeschlossen (M10.5 Rate-Limits offen).** Übergang zu M11.

Detail: [`PLAN.md § Status-Sync 2026-05-04`](../PLAN.md#status-sync-2026-05-04). Subagent-Mapping pro Slice: [`docu/plan.heuristic.md`](plan.heuristic.md).

**Erledigt (Code-verifiziert 2026-05-04):**
- F1 Reverse-Proxy (`deploy/nginx/`, `deploy/compose/docker-compose.prod-with-proxy.yml`)
- F2.1 Bundle-Token-Gate (`Dockerfile` `ALLOW_BUILD_TIME_TOKEN=false` Default)
- F2.2 `?token=` in Prod blockt (`backend/app/utils/auth.py`)
- F3 Gunicorn `-k gevent`
- SSE-Auth-Frontend auf signed tickets (`frontend/src/api/stream.ts`)
- M9.6 Prod-Stack-Smoke als strict PR-Gate (`docker-image.yml::prod-proxy-smoke` mit `AGORA_SKIP_EMBEDDING_PROBE=true`; `continue-on-error` nur noch bei Tag-Pushes, Issue #276)
- M10.1/M10.2/M10.3 CVE-Monitor + Hardstop 2026-07-30 + Risk-Register-Eskalationspfad (`.github/workflows/cve-monitor.yml`, `docu/dependency-risk-register.md`)
- M10.4 Auth-Zielbild-ADR Single-User-only-v1 (`docu/decisions/0001-auth-model.md` Accepted) + Code-Update `_get_auth_mode()` returnt `"single_user_token"` + README/security-hardening Single-User-Block + Token-Rotation-Prozedur
- M11.1 Evidence-Quality-Gate hard (`--soft` raus aus `contract-gates.yml`, Hard-Gate gegen `tests/eval/fixtures/good/`, Bad-Cases gepinnt durch Snapshot-Test)

**Aktiv offen (nächste 3 Slices in Reihenfolge):**
1. M10.5 Rate-Limit-Konzept — `/api/auth/ticket`, Uploads, LLM-Trigger, Report-Gen.
2. M11.2/M11.3 Coverage-Gates Backend (70 %) / Frontend (60 %).
3. M11.4 Playwright-Smokes (3 E2E-Tests: Health/Login, Upload+Graph, Minimalreport).

Mittelfristig: M11.2/M11.3 Coverage-Gates, M11.4 Playwright-Smokes, M11.5 Komplexitäts-Gate, F8 Hotspot-Split Frontend (#203). #202 geschlossen 2026-05-05 (report_agent als Package).

## Aktualisierungs-Protokoll

- 2026-05-03: Sub-Slice 44 — STATUS.md inaugural, Test-Counts und Versionsstände zentralisiert, Inline-Zahlen aus README/CLAUDE.md entfernt, ROADMAP auf v0.9.0+ / 2026-05-03 geheben.
- 2026-05-04: F5 Doku-Sync (1) — Test-Counts auf 1370 (1330 → 1370 nach Layer-9-Slices), README inline-Zahl entfernt.
- 2026-05-04: Doku-Sync 2026-05-04 — `AGENTS.md` v0.6.0 → v0.9.0+, `CLAUDE.md` Layer-9-Hot-Spots auf realen Code-Stand, `PLAN.md` Status-Sync-Block, neue `docu/plan.heuristic.md` als Subagent-Routing-SSoT, User-Drop-Audit-Snapshots nach `docu/history/`.
- 2026-05-04: M9.6 Prod-Stack-Smoke — `docker-image.yml::prod-proxy-smoke` läuft jetzt auch auf `pull_request: [main]` (Doku-PRs ausgeschlossen via `paths-ignore`). `scripts/verify-deploy.sh` smoket zusätzlich `/api/auth/ticket` via Proxy. M9 ist damit code- und CI-seitig grün; nächste Slice-Priorität verschiebt sich auf M10.
- 2026-05-04: M10.1/M10.2/M10.3 CVE-Monitor + Hardstop — Neuer Workflow `.github/workflows/cve-monitor.yml` läuft Mo 06:00 UTC `pip-audit --strict` ohne `--ignore-vuln` und schreibt das Ergebnis in `$GITHUB_STEP_SUMMARY`. Hardstop am 2026-07-30 verdrahtet: ab dann fail bei pip-audit-Findings. `docu/dependency-risk-register.md` um Eskalationspfad-Sektion (Vendoring / Soft-Fork / Replacement / Risikoakzeptanz-PR) und Upstream-Release-Watch-Spalte erweitert (die Owner-Spalte war bereits vorhanden). Layer 10 von „dokumentiert" auf „grün".
- 2026-05-04: M10.4 Auth-Zielbild-ADR — `docu/decisions/0001-auth-model.md` als **Proposed** angelegt mit drei Optionen (Single-User-only-v1 / HttpOnly-Session / Bearer+Refresh). Empfehlung: Option A (Single-User-only-v1 explizit machen). Begründung: Local-first ist Kernprinzip, Hauptangriffsvektoren sind bereits geschlossen (F2.1/F2.2/P0.2/S2/S3), v1.0-Termin erreichbar. Wartet auf User-Sign-off. Folge-Slices nach Accept: README/security-hardening-Update, `auth_mode`-Feld in `/api/status`, Token-Rotation-Prozedur. ADR-Index unter `docu/decisions/README.md` mit Konvention.
- 2026-05-04: M10.4-Followup — ADR-0001 von **Proposed** auf **Accepted** gehoben (User-Sign-off via Merge PR #277). `backend/app/api/status.py::_get_auth_mode()` returnt jetzt `"single_user_token"` statt `"token"` — der Prefix `single_user_` macht für Operatoren in `/api/status` sichtbar, dass Agora kein Multi-User-Modell hat. Tests in `tests/test_anonymous_in_healthcheck.py` angepasst.
- 2026-05-04: M11.2 Backend-Coverage-Gate — `pytest-cov>=5.0.0` in beide Dev-Dep-Listen (`[project.optional-dependencies] dev` + `[dependency-groups] dev`). `addopts` um `--cov=app --cov-report=term-missing --cov-report=xml --cov-fail-under=53` erweitert. Startschwelle 53 % (Ist 55 %, Formel `floor(Ist - 2)`; 70 %-PLAN-Default nicht erreichbar wegen OASIS-Integrationspfad ohne Ollama/Neo4j in CI). Coverage-Report als Artifact `backend-coverage` (14 Tage) in `ci.yml`. Coverage-Sektion in `docu/STATUS.md` mit Roadmap.
- 2026-05-04: M11.3 Frontend-Coverage-Gate — `@vitest/coverage-v8@4.1.5` in `devDependencies`. `package.json` `test:coverage`-Script neu; `check` auf `test:coverage` umgestellt; `test` bleibt schneller Gate-freier TDD-Pfad. `vite.config.js` Coverage-Block: provider v8, reporters text/lcov/html, include `src/**/*.{js,ts,vue}`, thresholds 24 % (alle vier Metriken). Startschwelle 24 % (Ist-Wert branches 26.70 % ist Bottleneck beim vollständigen `include`-Glob; Fallback-Formel `floor(Ist - 2) = 24`; 60 %-PLAN-Default nicht erreichbar wegen 6 untesteter Views + jsdom-inkompatibler Canvas/D3-Pfade). Coverage-Report als Artifact `frontend-coverage` (14 Tage) in `ci.yml`. Coverage-Sektion in `docu/STATUS.md` mit Roadmap.
- 2026-05-04: M10.4-Doku-Folge — README.md (DE+EN-Status-Block) auf Single-User-only mit Verweis auf ADR-0001 erweitert. `docu/security-hardening.md` neue Sektion „Auth-Modell v1.0" mit (a) Garantien-Liste (kein User-Konzept, kein Logout, kein Audit, kein Multi-User), (b) Was-schützt-was-nicht-Gegenüberstellung inkl. fehlender Rate-Limits als Hardstop bis M10.5, (c) Token-Rotation-Prozedur als 6-Schritt-Anleitung mit `curl`-Verifikation, (d) Trigger für ADR-Supersedes (Klassenraum, Public-Internet, Compliance), (e) Hardstops-Liste für v1.0. Layer-9 in STATUS damit final auf grün; v1.0-Auth-Story ist closed.
- 2026-05-05: Issue #276 Embedding-Probe-Skip — `AGORA_SKIP_EMBEDDING_PROBE=true` in `docker-image.yml::prod-proxy-smoke` eingeführt. `validate_embedding_configuration()` bekommt `skip_probe`-Parameter; bei gesetztem Flag läuft nur die statische KNOWN_EMBEDDING_DIMS-Validation, der Live-HTTP-Probe-Call gegen Ollama entfällt. Container startet im CI-Runner ohne Ollama sauber hoch. `continue-on-error: github.event_name == 'pull_request'`-Workaround aus PR-Trigger entfernt — PR-Smokes sind jetzt strict. Tag-Pushes bleiben lenient (externe Image-Pulls instabil). M9.6 von informational auf strict gesetzt.
