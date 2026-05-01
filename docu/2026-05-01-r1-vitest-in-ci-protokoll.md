# R1 — Vitest in CI Frontend-Job · Arbeitsprotokoll

**Datum:** 2026-05-01
**Slice:** R1

## Implementierung

`.github/workflows/ci.yml`: Frontend-Job ergänzt einen Step `Run frontend tests (Vitest)` zwischen Lint und Build. Damit wird `npm test` im CI ausgeführt; lokal vorhandenes Vitest-Setup (`frontend/src/composables/__tests__/`, `frontend/src/utils/__tests__/`) wird automatisch grün gemeldet oder bricht den Build.

Akzeptanz aus Repo-Review: PR triggert Vitest, Frontend-Job zeigt Test-Counts. Mit aktuell 5 Test-Files / 40 Tests.

`npm run check` grün, kein lokaler Lint-Drift.
