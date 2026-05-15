# Worklog — FE-Redesign Followups Phase C: Dynamische Cmd+K-Commands

**Datum:** 2026-05-15
**Branch:** feat/fe-redesign-followups-c
**Commit:** 6ba0d8d

---

## C1 — Datenquellen-Audit

### Stores (frontend/src/stores/)
- `commandsStore.ts` — Cmd+K-Palette-Store (Slice 4)
- `shell.ts` — Sidebar/Inspector-State

### Composables (relevante Treffer)
- `useRunsPolling.ts` — **EXISTIERT**. Dünner Wrapper um `usePolling`, validiert via `RunsListResponseSchema` (Zod). Liefert `runs: Ref<RunDetail[]>` mit `status`, `run_id`, `entity_id`, `summary.document_name`.
- **Kein separater Reports-Store gefunden.** Recent-Reports werden aus completed `RunDetail`-Einträgen mit `linked_ids.report_id` oder `artifacts.report_id` abgeleitet.

**Gewählte Variante:** Existing Composable `useRunsPolling` — kein eigener Composable nötig.

**Skip-Begründung (code-review-graph):** `get_minimal_context_tool` war nicht verfügbar (Tool-Name-Diskrepanz in aktueller MCP-Version). Direkte Exploration via `find` + `Read` war ausreichend (eindeutiger Composable-Fund).

---

## C2 — commandsStore Erweiterung

**Datei:** `frontend/src/stores/commandsStore.ts`

### Änderungen
- `Command`-Interface: `keywords?: string[]` ergänzt (für Keyword-basiertes Filtern)
- `dynamicCommands: ref<Command[]>([])` — reaktiver State für Sim/Report-Commands
- `bindDynamicCommands(router)`: Idempotent, startet `useRunsPolling(10_000)` und hängt `watch` auf `runs`
  - `ACTIVE_STATUSES = Set(['pending', 'processing', 'paused'])` → `sim:${run_id}` Commands
  - Label: `Lauf: ${document_name} (laufend|pausiert|wartend)`
  - Navigation: `router.push({ name: 'StepSimulation', params: { simulationId: run.entity_id } })`
  - Completed Runs mit `linked_ids.report_id` oder `artifacts.report_id` → `report:${reportId}` Commands (max 5)
  - Navigation: `router.push({ name: 'StepReport', params: { reportId } })`
- `unbindDynamicCommands()`: Stoppt Watch, leert dynamicCommands
- `allDynamic` computed als `dynamicCommands`-Export
- `filter()` erweitert: sucht zusätzlich in `keywords`-Array

### Technische Entscheidung
`start()` aus `useRunsPolling` via `Promise.resolve(start())` gewrappt — robust gegen Test-Environments wo `usePolling` als `vi.fn()` ohne Promise-Rückgabe gemockt ist.

---

## C3 — AppShell Wiring

**Datei:** `frontend/src/components/v4/shell/AppShell.vue`

- `useRouter()` + `useCommandsStore()` importiert
- `onMounted`: `commandsStore.bindDynamicCommands(router)` — einmalig, idempotent

---

## C4 — Tests

**Datei:** `frontend/src/stores/__tests__/commandsStore.spec.ts`

3 neue Tests (Phase C):
1. `(Phase C) dynamicCommands erscheinen wenn laufender Run vorhanden` — processing-Run → sim:run-abc-123 mit Label + Keywords
2. `(Phase C) filter() matchet dynamische Sim-Commands per Keyword "sim"` — pending-Run → filterbar
3. `(Phase C) unbindDynamicCommands() leert Commands und erlaubt Re-Bind` — Lifecycle korrekt

**`useRunsPolling` global gemockt** in der Test-Datei über `vi.mock('@/composables/useRunsPolling')` mit kontrolliertem `mockRuns = ref([])`.

**Fixes StepWrapperViews.spec.ts:** `useRunsPolling`-Mock ergänzt, da AppShell.vue jetzt `bindDynamicCommands` in `onMounted` aufruft. Das gemockte `usePolling` (ohne Promise-Rückgabe) hätte `.catch is not a function` verursacht.

---

## Verification

```
bun run typecheck  → exit 0
bun run test:coverage → 920/920 Tests grün (121 Dateien)
bun run build     → exit 0
bun run lint      → exit 0
```

Unhandled EnvironmentTeardownErrors in `CompareView.spec.ts` + `HistoryView.spec.ts` sind pre-existing (Slice 4), nicht durch Phase C verursacht.

---

## Test-Delta

- Vorher: 917 Tests
- Nachher: 920 Tests (+3)

---

## Bundle-Delta

- `AppShell-*.js`: ~7.54 kB gz (commandsStore liegt im gleichen Chunk)
- Delta: < +2 kB gz (Ziel ≤ +3 kB erfüllt)

---

## Dynamic Commands

- **Laufende Sims:** ja — status in `{pending, processing, paused}` → `sim:*`-Commands
- **Recent Reports:** ja — completed Runs mit `report_id` in `linked_ids` oder `artifacts` → `report:*`-Commands (max 5)

---

## Gaps

Keine. Falls kein Run `report_id` in `linked_ids`/`artifacts` hat, erscheinen keine Report-Commands — das ist korrekt (kein Fallback nötig, da Reports ohne ID nicht navigierbar wären).
