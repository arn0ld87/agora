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
| 9 | Prod-Deployment | grün — Reverse-Proxy ✅, gevent ✅, Bundle-Token-Gate ✅, `?token=`-Block ✅, signed-tickets-Frontend ✅, Prod-Stack-Smoke in CI ✅ (`docker-image.yml::prod-proxy-smoke` als PR-Gate). Offen nur noch Auth-ADR (M10.4). |
| 10 | Security Watchlist | grün — CVE-Monitor wöchentlich aktiv (`.github/workflows/cve-monitor.yml`), Hardstop 2026-07-30 verdrahtet, Risk-Register mit Eskalationspfad. Issues #121–#126 weiter open bis Upstream patcht. |

## Aktuelles Milestone

**M9 abgeschlossen, M10 überwiegend abgeschlossen.** Übergang zu M11.

Detail: [`PLAN.md § Status-Sync 2026-05-04`](../PLAN.md#status-sync-2026-05-04). Subagent-Mapping pro Slice: [`docu/plan.heuristic.md`](plan.heuristic.md).

**Erledigt (Code-verifiziert 2026-05-04):**
- F1 Reverse-Proxy (`deploy/nginx/`, `deploy/compose/docker-compose.prod-with-proxy.yml`)
- F2.1 Bundle-Token-Gate (`Dockerfile` `ALLOW_BUILD_TIME_TOKEN=false` Default)
- F2.2 `?token=` in Prod blockt (`backend/app/utils/auth.py`)
- F3 Gunicorn `-k gevent`
- SSE-Auth-Frontend auf signed tickets (`frontend/src/api/stream.ts`)
- M9.6 Prod-Stack-Smoke als PR-Gate (`docker-image.yml::prod-proxy-smoke`, `verify-deploy.sh` mit `/healthz`/`/health`/`/`/`/api/auth/ticket`)
- M10.1/M10.2/M10.3 CVE-Monitor + Hardstop 2026-07-30 + Risk-Register-Eskalationspfad (`.github/workflows/cve-monitor.yml`, `docu/dependency-risk-register.md`)

**Aktiv offen (nächste 3 Slices in Reihenfolge):**
1. M10.4 Auth-Zielbild-ADR — `docu/decisions/0001-auth-model.md`.
2. M10.5 Rate-Limit-Konzept — `/api/auth/ticket`, Uploads, LLM-Trigger, Report-Gen.
3. M11.1 Evidence-Quality-Gate hard schalten (`--soft` aus `contract-gates.yml`).

Mittelfristig: M11.1 Evidence-Gate hard, M11.2/M11.3 Coverage-Gates, M11.4 Playwright-Smokes, F7/F8 Hotspot-Splits (#202/#203).

## Aktualisierungs-Protokoll

- 2026-05-03: Sub-Slice 44 — STATUS.md inaugural, Test-Counts und Versionsstände zentralisiert, Inline-Zahlen aus README/CLAUDE.md entfernt, ROADMAP auf v0.9.0+ / 2026-05-03 geheben.
- 2026-05-04: F5 Doku-Sync (1) — Test-Counts auf 1370 (1330 → 1370 nach Layer-9-Slices), README inline-Zahl entfernt.
- 2026-05-04: Doku-Sync 2026-05-04 — `AGENTS.md` v0.6.0 → v0.9.0+, `CLAUDE.md` Layer-9-Hot-Spots auf realen Code-Stand, `PLAN.md` Status-Sync-Block, neue `docu/plan.heuristic.md` als Subagent-Routing-SSoT, User-Drop-Audit-Snapshots nach `docu/history/`.
- 2026-05-04: M9.6 Prod-Stack-Smoke — `docker-image.yml::prod-proxy-smoke` läuft jetzt auch auf `pull_request: [main]` (Doku-PRs ausgeschlossen via `paths-ignore`). `scripts/verify-deploy.sh` smoket zusätzlich `/api/auth/ticket` via Proxy. M9 ist damit code- und CI-seitig grün; nächste Slice-Priorität verschiebt sich auf M10.
- 2026-05-04: M10.1/M10.2/M10.3 CVE-Monitor + Hardstop — Neuer Workflow `.github/workflows/cve-monitor.yml` läuft Mo 06:00 UTC `pip-audit --strict` ohne `--ignore-vuln` und schreibt das Ergebnis in `$GITHUB_STEP_SUMMARY`. Hardstop am 2026-07-30 verdrahtet: ab dann fail bei pip-audit-Findings. `docu/dependency-risk-register.md` um Eskalationspfad-Sektion (Vendoring / Soft-Fork / Replacement / Risikoakzeptanz-PR) und Upstream-Release-Watch-Spalte erweitert (die Owner-Spalte war bereits vorhanden). Layer 10 von „dokumentiert" auf „grün".
