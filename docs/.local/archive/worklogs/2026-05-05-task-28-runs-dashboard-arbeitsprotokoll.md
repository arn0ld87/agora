# Arbeitsprotokoll: Sub-Slice 28 — RunsDashboard.vue (Closes #63)

**Datum:** 2026-05-05
**Branch:** task-28-runs-dashboard
**Worktree:** `/Volumes/T7/Projekte/agora/.claude/worktrees/task-28-runs-dashboard`

---

## Was wurde geändert

| Datei | Typ | LOC-Delta |
|---|---|---|
| `frontend/src/composables/useRunsPolling.ts` | neu | +57 |
| `frontend/src/components/RunsDashboard.vue` | neu | +265 |
| `frontend/src/views/RunDetailView.vue` | neu | +196 |
| `frontend/src/views/RunsView.vue` | geändert | −10 / +8 (HistoryDatabase → RunsDashboard, script auf TS) |
| `frontend/src/router/index.ts` | geändert | +5 (neue Route `/runs/:id` → `RunDetail`) |
| `frontend/src/i18n/locales/de.json` | geändert | +22 (`runs.dashboard.*`) |
| `frontend/src/i18n/locales/en.json` | geändert | +22 (`runs.dashboard.*`) |
| `frontend/src/components/__tests__/RunsDashboard.spec.ts` | neu | +190 |
| `CHANGELOG.md` | geändert | +1 |

---

## Verifikation: Pflicht-Checks

```
rg RunsDashboard frontend/src/views/RunsView.vue     → OK
rg HistoryDatabase frontend/src/views/RunsView.vue   → OK (entfernt)
rg useRunsPolling frontend/src/components/RunsDashboard.vue → OK
runs.dashboard in de.json und en.json                → OK (Schlüssel existieren, korrekt verschachtelt)
npm run check (vue-tsc + vitest + build)              → GRUEN (241 Tests, Build OK)
```

---

## Architektur-Entscheidungen

### useRunsPolling als separates Composable

Die Spezifikation sah einen dünnen Wrapper vor (~30 LOC). Grund: Testbarkeit.
`usePolling` ist generisch und hat eigene Tests; `useRunsPolling` kapselt die Zod-Validierung
und die API-Integration. Wird `useRunsPolling` in Tests per `vi.mock('../../api/runs')` gemockt,
bleibt `usePolling` unberührt — kein Koppeln von Polling-Timing-Tests mit Schema-Tests.

### HistoryDatabase bleibt unangetastet

`HistoryDatabase.vue` hat eigene Tests (`HistoryDatabase.spec.ts`) und wird nicht mehr in
`RunsView.vue` eingebunden, aber die Datei selbst bleibt erhalten. Grund: andere Teile
des Stacks könnten die Komponente noch referenzieren; ausserdem würde ein Löschen oder
Umbenennen während des laufenden Worktree-Rebase-Flusses Konflikte erzeugen.

### Drill-down per Route statt Drawer/Modal

Eine Drawer-Lösung wäre in-place eleganter, verkompliziert aber URL-Sharing und
Browser-History. `/runs/:id` als eigene Route ermöglicht direktes Navigieren per
URL und macht den Back-Button semantisch korrekt. Für zukünftiges SSE-Polling
(Phase 2) ist eine eigene Route einfacher zu verdrahten als ein Drawer-State.

### Zod-Validierung: last-known-good bei Parse-Fehler

Bei `safeParse`-Fehler wird `error.value` gesetzt, aber `runs.value` bleibt
unverändert. Grund: Ein transienter API-Fehler oder Schema-Drift nach einem Backend-Deploy
soll nicht die gesamte Liste löschen. Der Nutzer sieht den Fehler-Banner, aber die letzte
bekannte Liste bleibt sichtbar.

### Envelope-Struktur

Der axios-Interceptor in `api/index.ts` gibt bei Erfolg `response.data` (das JSON-Body-Objekt)
direkt zurück. Bei `/api/runs` ist das `{ success: true, data: { runs: [...], total: N } }`.
`useRunsPolling.tick()` greift auf `.data` des Envelope-Objekts zu und parst es mit
`RunsListResponseSchema` — das erwartet `{ runs: [...], total: N }`.

---

## Test-Ergebnisse

```
 Test Files  31 passed (31)
      Tests  241 passed (241)
   Duration  7.71s
```

Alle 5 neuen Tests grün:
- `test_pills_filter_runs_by_status_bucket` — Filter korrekt für alle 3 Buckets
- `test_polling_calls_listRuns_every_5s_when_mounted` — initialer + Timer-Tick
- `test_polling_stops_on_unmount` — kein weiterer Aufruf nach `unmount()`
- `test_click_on_row_navigates_to_detail` — `router.push` mit korrekten Params
- `test_empty_state_when_no_runs` — Empty-Text sichtbar

---

## Phase-2-Hinweise

- **Virtuelles Scrollen:** Bei >200 Runs (nicht realistisch bei lokalem Stack)
  könnte `@tanstack/virtual` oder Intersection-Observer-basiertes lazy-rendering sinnvoll sein.
- **SSE statt Polling:** Backend-`/api/runs/stream` (SSE) würde das 5s-Polling ersetzen.
  `useEventStream.ts` ist im Codebase vorhanden und könnte als Basis dienen.
- **RunDetailView Polling:** Aktuell One-Shot-Load + Refresh-Button. Bei laufenden Runs
  wäre Auto-Refresh (5s, nur bei `status in ['pending', 'processing', 'paused']`) sinnvoll.
- **Resume/Stop-Buttons in RunDetailView:** Wenn `run.resume_capability.available === true`,
  könnte ein Resume-Button direkt in der Detail-View erscheinen (analog zu HistoryDatabase).
