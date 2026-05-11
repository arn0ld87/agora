# Arbeitsprotokoll — Slice #137 SUB2: Frontend Auto-Freeze

**Datum:** 2026-05-04
**Branch:** `feat/task-137-graph-build-batch-marker`
**Scope:** Frontend-only (SUB1 Backend war bereits implementiert)

---

## Kontext

Issue #137 fordert, dass die D3-Force-Simulation während des Graph-Aufbaus
nach jedem committeten Chunk für ~800 ms eingefroren wird, damit der User
dem schrittweisen Aufbau folgen kann. SUB1 (Backend) hat dafür
`progress_detail.batch_count`/`total_batches`/`batch_at` in die Task-Status-
Antwort eingefügt. SUB2 verdrahtet diesen Wert im Frontend.

---

## Architektur-Entscheidung: Polling-basiert statt SSE

Der Auto-Freeze-Trigger kommt **nicht** über einen separaten SSE-Channel,
sondern über das bestehende `pollTaskStatus`-Polling in `MainView.vue`
(Intervall 2 s). Begründung:

- Der Orchestrator hat SSE für diese Feature explizit als out-of-scope markiert
  ("Polling-Pfad ist bewusste Architektur-Entscheidung").
- Das Task-Status-Polling läuft bereits; `progress_detail` ist ein neues Feld
  im selben Response-Envelope. Kein neuer HTTP-Endpunkt, kein zweiter Fan-out.
- 2-s-Polling-Jitter ist bei einem 800-ms-Freeze-Fenster akzeptabel: der User
  sieht pro Batch mindestens einen Freeze, ggf. leicht verzögert.
- Ein SSE-Channel würde Signed-Ticket-Auth, Reconnect-Logik und einen neuen
  Backend-Endpoint erfordern — unverhältnismäßig für ein UI-Komfort-Feature.

---

## Manual-Pause-Detektion in `useGraphRender`

Das Composable führt zwei Flags:

| Flag | Typ | Bedeutung |
|---|---|---|
| `isPaused` | `Ref<boolean>` | Effektiver Render-Zustand (paused/running); vom Caller lesbar |
| `_isManuallyPaused` | `boolean` (Modul-intern) | Intent-Flag: wurde die Pause vom User über `pauseSimulation()`/`togglePause()` ausgelöst? |

**Regel:**
- `pauseSimulation()` setzt `_isManuallyPaused = true`.
- `resumeSimulation()` setzt `_isManuallyPaused = false`.
- `_triggerAutoFreeze()` setzt `isPaused = true` ohne `_isManuallyPaused` zu berühren.
- Wenn `_isManuallyPaused = true` beim Eintreffen eines neuen Batches: Auto-Freeze
  wird komplett übersprungen (kein Timer gesetzt).
- Wenn der User während eines laufenden Auto-Freezes `pauseSimulation()` aufruft:
  `_isManuallyPaused` wird `true`. Der Timer-Callback prüft `_isManuallyPaused`
  vor `resumeSimulation()` und bricht ab — der manuelle Zustand bleibt erhalten.

Dieses Design vermeidet Race-Conditions ohne Mutex: Alles läuft im selben
JS-Thread; die Flag-Checks sind synchron.

---

## Implementierte Dateien

### Geändert

- **`frontend/src/api/graph.ts`**
  `BuildProgressDetail`-Interface und `progress_detail`-Feld in
  `TaskStatusResponse` waren von SUB1 bereits eingefügt. Keine weitere Änderung
  durch SUB2.

- **`frontend/src/composables/useGraphRender.ts`**
  War von einem vorherigen Agent-Run bereits vollständig implementiert
  (batchSignal-Option, _triggerAutoFreeze, _isManuallyPaused, onScopeDispose-
  Cleanup). SUB2 hat nur verifiziert dass der Code korrekt ist.

- **`frontend/src/views/MainView.vue`**
  - `batchSignal = ref(null)` deklariert.
  - In `pollTaskStatus`: `batchSignal.value = task.progress_detail` wenn nicht null.
  - Bei `status === 'completed'` und `'failed'`: `batchSignal.value = null`.
  - Template: `:batchSignal="batchSignal"` an `<GraphPanel>` durchgereicht.
  - TypeScript-spezifische Syntax (`type`-Import, `ref<T>()`) entfernt, da
    `<script setup>` ohne `lang="ts"` (vue-tsc-Fehler).

- **`frontend/src/components/GraphPanel.vue`**
  - `batchSignal: { type: Object, default: null }` als neues Prop.
  - `:batch-signal="batchSignal"` an `<GraphCanvas>` weitergegeben.

- **`frontend/src/components/graph/GraphCanvas.vue`**
  - `batchSignal: { type: Object, default: null }` als neues Prop.
  - `batchSignalRef = computed(() => props.batchSignal ?? null)` als reaktiver Wrapper.
  - `batchSignal: batchSignalRef` in `useGraphRender`-Aufruf eingehängt.
  - `computed` zu Vue-Import hinzugefügt.

### Neu erstellt

- **`frontend/src/composables/__tests__/useGraphRender.spec.ts`**
  7 Tests (5 Szenarien, 4a als separates Case):
  1. `batch-trigger` — batch_count-Anstieg → isPaused=true, nach 800 ms false.
  2. `no-op same count` — gleicher batch_count → kein Freeze.
  3. `manual-pause wins` — manuell pausiert → Batch-Trigger ignoriert.
  4a. `manual-during-freeze` — User pausiert während Freeze → Timer resumed nicht.
  5. `cleanup` — Unmount bricht Timer ab, kein Crash.

- **`docs/2026-05-04-137-sub2-auto-freeze-arbeitsprotokoll.md`** (diese Datei)

### CHANGELOG

SUB1- und SUB2-Einträge zu einem konsolidierten Eintrag unter `[Unreleased] Added`
zusammengefasst.

---

## Test-Plan

D3 und `buildGraphRenderData` sind vollständig gemockt — die Tests laufen im
jsdom-Environment ohne echtes SVG-Layout. Fake-Timers (`vi.useFakeTimers`)
steuern den `setTimeout`-Zyklus. Der `_isManuallyPaused`-Flag ist Modul-intern;
Tests steuern ihn über die öffentliche `pauseSimulation()`-API.

Vorher: 163 Tests in 22 Dateien.
Nachher: 170 Tests in 24 Dateien (+7 Tests, +2 Dateien).

---

## SUB3 — Settings-Integration (out-of-scope)

`autoFreezeMs` ist als optionaler Parameter in `UseGraphRenderArgs` vorgesehen
mit Default `800`. Die Settings-Wiring-Anbindung (User-konfigurierbar über
`#133`/Slice D/#212) ist bewusst **out-of-scope** für diesen Sub-Slice.

Blockiert auf: Slice D / Issue #212 (Settings-Store-Erweiterung).
Nächster Schritt: In `useGraphRender`-Aufruf in `GraphCanvas.vue` den Wert aus
dem Settings-Pinia-Store lesen, sobald #212 geliefert ist.

---

## Akzeptanz-Verify

```
npm run check  →  vue-tsc 0 Fehler | 170 Tests passed | vite build ✓
```
