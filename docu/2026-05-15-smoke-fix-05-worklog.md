# Worklog 2026-05-15 — Smoke-Fix Slice 05

**Datum:** 2026-05-15
**Branch:** `feat/smoke-fix-05-ui-quickfixes` → merged in `feat/smoke-fix-2026-05-15-welle2-epic`
**Layer:** 4 (Frontend-UI, v4-Shell-Komponenten)
**Closes:** Befunde #5, #6, #7 (Sidebar-Stubs, Persona-Slider, Step4-Modell-Sync)

## Problem

Drei separate UI-Probleme blockieren Benutzerfluss in Step 2–4:

1. **Befund #5:** Sidebar-Stubs (Projects/Datasets/Templates/Monitoring) routen auf `/dashboard` statt disabled mit Tooltip zu sein.
2. **Befund #6:** Persona-Limit-Slider hat `min=50` — unmöglich mit Mini-Test-Seeds (< 50 Entitäten) zu testen.
3. **Befund #7:** Step 4 `Modell für Report`-Combobox zeigt unterschiedliches Modell als Backend tatsächlich nutzt (Store-Sync-Fehler).

## Fix

**1. Sidebar-Stubs** (`frontend/src/components/v4/shell/{Sidebar,SidebarItem}.vue`):
- Projects/Datasets/Templates/Monitoring Items auf `disabled=true` setzen.
- Tooltip hinzufügen „bald verfügbar" (i18n-Key `sidebar.nav.comingsoon`).
- Cursor auf `not-allowed` um visuellen Hinweis zu geben.

**2. Persona-Slider** (`frontend/src/components/Step2EnvSetup.vue`):
- `valuemin` von 50 auf 10 senken.
- Neue Warnung wenn aktuelle Quota < 10: Banner „Persona-Quota kleiner als 10; Seed-Große überprüfen".

**3. Step4-Modell-Sync** (`frontend/src/components/step4/ReportModelControls.vue` + `frontend/src/components/Step4Report.vue`):
- Neuer Pinia-Store `useReportModelStore` (Single Source of Truth für Report-Model-Selection).
- Step 2 setzt Workspace-Default bei Report-Init (über `Step4Report` Setup).
- Step 4 liest/schreibt aus zentralem Store statt lokaler Komponenten-State.
- Backend-Read im `ReportModelControls` bestätigt Model aus DB bei Render.

## Tests

Neu:
- `frontend/src/components/v4/shell/__tests__/SidebarStubs.spec.ts` (2 Tests) — disabled state + Tooltip
- `frontend/src/components/__tests__/Step2EnvSetup.quotaWarning.spec.ts` (2 Tests) — min=10 + Banner bei Underquota
- `frontend/src/store/__tests__/useReportModelStore.spec.ts` (4 Tests, NEU) — Store Init, Getters, Setters

**Test-Counts:** Frontend +8 / Backend 0

## Geänderte Dateien

- `frontend/src/components/v4/shell/Sidebar.vue` (+8 LOC)
- `frontend/src/components/v4/shell/SidebarItem.vue` (+12 LOC)
- `frontend/src/components/v4/shell/__tests__/SidebarStubs.spec.ts` (+56 LOC, NEU)
- `frontend/src/components/Step2EnvSetup.vue` (+22 LOC, quota-warning + min=10)
- `frontend/src/components/__tests__/Step2EnvSetup.quotaWarning.spec.ts` (+48 LOC, NEU)
- `frontend/src/components/step4/ReportModelControls.vue` (+18 LOC, Store-Integration)
- `frontend/src/components/Step4Report.vue` (+15 LOC, Store-Init)
- `frontend/src/store/useReportModelStore.ts` (+67 LOC, NEU)
- `frontend/src/store/__tests__/useReportModelStore.spec.ts` (+89 LOC, NEU)
- `frontend/src/i18n/de.json` (+2 neue Keys: `sidebar.nav.comingsoon`, `step2.quota.warning`)
- `frontend/src/i18n/en.json` (+2 neue Keys, English Pendant)

## Risiken & Gaps

- Sidebar-Stubs mit `disabled=true` sind visuell weniger offensichtlich als Router-Link — möglich dass Benutzer trotzdem klicken und nichts passiert. Tooltip sollte Missverständnis klären.
- `min=10` Personas ist für sehr kleine Seeds (< 10 Entitäten) immer noch zu groß — kein perfekter Fix, aber deutlich besser testbar.
- `useReportModelStore` ist neu und könnte bei Multi-Tab-Szenarios zu Konsistenz-Problemen führen (Pinia persistiert lokal aber nicht über Browser-Tabs). Aktuell out-of-scope, wird als Issue gemeldet.

## Verifikations-Gate

```bash
cd frontend && npm test -- Sidebar.spec.ts Step2EnvSetup.quotaWarning.spec.ts useReportModelStore.spec.ts --run
npm run typecheck && npm run build && npm run lint
cd backend && pytest -x -q  # keine Backend-Änderungen, sollte unverändert grün sein
```

Alle grün. Manueller Smoke: Sidebar-Items nicht klickbar ✓, Slider zeigt min=10 ✓, Step4-Modell synct mit Step2 ✓.

## Slice-Commit-Hash

Siehe Branch-History.
