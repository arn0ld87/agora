# Arbeitsprotokoll — M11.3: Frontend-Coverage-Gate

**Datum:** 2026-05-04
**Slice-ID:** M11.3 / PLAN.md F6.2
**Ziel:** `@vitest/coverage-v8` als DevDependency, Coverage-Gate in CI und `npm run check`, Startschwelle ermitteln und dokumentieren.

## Initial-Coverage-Messung

Gemessen mit der konfigurierten `include`-Regel `src/**/*.{js,ts,vue}` (24 Spec-Files, 170 Tests passed). Der vollständige `include`-Glob erfasst auch untestete Views, daher fallen die Zahlen niedriger aus als eine rein transitive Messung ohne explizites `include`.

```bash
cd frontend && npm run test:coverage
```

Ergebnis:

| Metrik | Coverage | Basis |
|---|---|---|
| Statements | 37.38 % | 1 570 / 4 199 |
| Branches | **26.70 %** | 837 / 3 134 |
| Functions | 27.14 % | 272 / 1 002 |
| Lines | 39.16 % | 1 478 / 3 774 |

**Niedrigster Wert: branches 26.70 % (Bottleneck-Metrik).**

## Begründung der gewählten Schwelle

Ist-Wert branches 26.70 % liegt weit unter der PLAN-Default-Schwelle von 60 %. Daher greift die Fallback-Formel:

> Ist < 60 % → `floor(Ist - 2)` = `floor(26.70 - 2)` = **24**

Die 60 %-Marke ist vorerst nicht erreichbar, weil:

1. Sechs vollständig untestete Views (`Home.vue`, `MainView.vue`, `ReportView.vue`, `RunsView.vue`, `SimulationView.vue`, `InstructionView.vue`) haben 0 % Coverage. Sie werden durch den `include`-Glob erfasst und setzen Playwright-E2E-Tests voraus (M11.4).
2. `GraphCanvas.vue` und `GraphPanel.vue` haben 0 % Branches: Canvas-/WebGL-APIs sind in jsdom nicht verfügbar.
3. `Step2EnvSetup.vue` hat 9.52 % Branches (~200 Conditional-Zweige im Wizard-Flow, nur über vollständige Interaktionssequenzen abdeckbar).

Diese Lücken sind strukturell und nicht durch neue Unit-Tests zu schließen, ohne die Browser-Rendering-Schicht zu mocken (eigener Scope: M11.4 Playwright).

## Geänderte Dateien

| Datei | Änderung |
|---|---|
| `frontend/package.json` | `@vitest/coverage-v8: ^4.1.5` in `devDependencies`; `test:coverage`-Script neu; `check`-Script auf `test:coverage` umgestellt |
| `frontend/package-lock.json` | Automatisch durch `npm install` aktualisiert |
| `frontend/vite.config.js` | `coverage`-Block im `test`-Objekt: provider v8, reporters text/lcov/html, include/exclude, thresholds 24 % |
| `.github/workflows/ci.yml` | Frontend-Test-Step auf `npm run test:coverage` umgestellt (Step-Name `Run frontend tests with coverage gate (M11.3)`); Upload-Artifact-Step `frontend-coverage` (14 Tage, `if-no-files-found: error`) ergänzt |
| `.gitignore` | `frontend/coverage/` und `frontend/lcov.info` ergänzt |
| `docs/status.md` | Neue Sektion `Frontend-Coverage (M11.3)` mit Messwerten, Schwellenbegründung und Roadmap-Tabelle; Aktualisierungsprotokoll-Eintrag |
| `CHANGELOG.md` | Eintrag unter `[Unreleased] ### Added` |
| `docs/2026-05-04-m113-frontend-coverage-arbeitsprotokoll.md` | dieses Dokument |

## Verify-Output

```
# 1. npm install
→ @vitest/coverage-v8@4.1.5 aufgelöst, kein Konflikt

# 2. npm run lint
→ Exit 0, keine ESLint-Findings

# 3. npm test (ohne Coverage-Gate — TDD-Pfad bleibt schnell)
→ 24 Test Files, 170 Tests passed

# 4. npm run test:coverage (mit Gate 24 %)
→ 24 Test Files, 170 Tests passed
→ Statements: 37.38 % ≥ 24 % ✓
→ Branches:   26.70 % ≥ 24 % ✓
→ Functions:  27.14 % ≥ 24 % ✓
→ Lines:      39.16 % ≥ 24 % ✓
→ Gate grün, kein ERROR

# 5. npm run check (vue-tsc + test:coverage + build)
→ grün
```

Alle fünf Checks grün.
