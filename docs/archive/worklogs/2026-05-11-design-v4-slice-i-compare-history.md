# Design-v4 Slice I — Compare & History Views

**Datum:** 2026-05-11
**Branch:** `feat/design-v4-slice-i-compare-history`
**Basis:** `feat/design-v4-slice-a-tokens` + merge B + C + D

## Ziel

Compare und History bekommen einen v4-AppShell-Wrapper. Inhalt der
Komponenten (`BranchComparePanel`, `HistoryDatabase`) bleibt unberuehrt.

## File-Map

| Datei | Typ | Beschreibung |
|---|---|---|
| `frontend/src/views/v4/CompareView.vue` | neu | AppShell + PageHeader + BranchComparePanel; laedt Branches via `listSimulationBranches` |
| `frontend/src/views/v4/HistoryView.vue` | neu | AppShell + PageHeader + HistoryDatabase |
| `frontend/src/router/index.ts` | ergaenzt | `/v4/compare/:simulationId` (CompareV4) + `/v4/history` (HistoryV4) am Ende |
| `frontend/src/views/v4/__tests__/CompareView.spec.ts` | neu | 3 Smoke-Tests |
| `frontend/src/views/v4/__tests__/HistoryView.spec.ts` | neu | 4 Smoke-Tests |

## Architektur-Entscheidungen

### CompareView braucht Props

`BranchComparePanel` erwartet `simulationId: string` und
`availableBranches` als Pflicht-Props — kein interner State-Store.
CompareView loedt `simulationId` via Route-Prop (`/v4/compare/:simulationId`)
und holt `availableBranches` per `listSimulationBranches` in `onMounted`.
Fehler- und Lade-Zustand werden im View behandelt — BranchComparePanel
selbst bleibt unberuehrt (kein Refactor in diesem Slice).

### HistoryView ist simpler

`HistoryDatabase` benoetigt keine Props; eigener interner `onMounted`-Fetch.
Der Wrapper ist ein reines Shell-Layout.

## v4-Komponenten verwendet

- `AppShell` (Slice B)
- `PageHeader` (Slice B)
- `Breadcrumbs`-Typ via Import (Slice B)

## Test-Delta

- Vorher: 593 Tests (65 Test-Files)
- Nachher: 600 Tests (67 Test-Files)
- Delta: +7 Tests (CompareView 3, HistoryView 4)

## Bundle-Delta

| Chunk | Groesse |
|---|---|
| `HistoryView-*.js` | 0.35 kB (gzip 0.27 kB) — reiner Wrapper |
| `CompareView-*.js` | 20.61 kB (gzip 5.02 kB) — inkl. BranchComparePanel |
| `CompareView-*.css` | 8.97 kB (gzip 1.75 kB) |

## Folgeschritte

### BranchComparePanel Inhalts-Refactor (spaeterer Slice)

BranchComparePanel (873 LOC) ist der naechste Kandidat:
- `simulationId` + `availableBranches` koennen in einen Store oder
  Composable wandern, damit der View schlanker wird.
- Interne API-Calls (Branches laden) koennen in CompareView zentralisiert
  werden (bereits begonnen).
- CSS-Variablen auf v4-Tokens migrieren (aktuell Mix aus alten Custom-Properties).
- i18n-Keys pruefen (bereits vorhanden, kein Dringlichkeit).

### Sidebar active="compare"

Aktuell ist kein eigener Sidebar-Eintrag fuer "Compare" definiert.
CompareView uebergibt der Sidebar via `AppShell` den aktiven State
`comparev4` (automatisch aus Route-Name abgeleitet). Ein expliziter
Sidebar-Eintrag kann in Slice F oder einem Folge-Slice ergaenzt werden.
