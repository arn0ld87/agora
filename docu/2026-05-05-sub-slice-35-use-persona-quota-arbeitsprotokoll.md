# Sub-Slice 35 — usePersonaQuota-Composable — Arbeitsprotokoll

**Datum:** 2026-05-05
**Branch:** feat/layer-4-task-47b-use-persona-quota
**Issue:** #203 (Task 47)

---

## Ziel

`Step2EnvSetup.vue` weiter reduzieren, indem Quota-State, LocalStorage-Persistenz und Zod-Validierung in ein eigenes Composable (`usePersonaQuota.ts`) ausgelagert werden.

---

## Cut-Linie (was wo landet)

### Im Composable (`usePersonaQuota.ts`):
- `STORAGE_QUOTA_PLAN`-Konstante (`'agora.quotaPlan'`)
- `_loadQuotaEntries()` — liest und deserialisiert bestehende LocalStorage-Einträge
- `_newEntryId()` — generiert eindeutige Entry-IDs (modulscoped counter)
- `useQuotaPlan` Ref (Toggle ob Plan aktiv)
- `quotaEntries` Ref (Array von `{ id, segment, count }`)
- `quotaTotal` ComputedRef (Summe aller counts)
- `quotaValidationError` ComputedRef (leer wenn valid/disabled, Zod-Issue-Message wenn invalid)
- LocalStorage-Watch (persistiert Änderungen)
- `addQuotaSegment()` / `removeQuotaSegment(idx)` Aktionen

### Bleibt in `Step2EnvSetup.vue`:
- `triggerPrepare()` — baut den API-Payload auf und delegiert an `useSimulationPrepare.startPrepare()`. Nutzt `quotaValidationError` aus dem Composable statt inline-Zod-Check. Benötigt weiter `buildQuotaPlanFromEntries` aus `personaQuotaContract` für den Payload-Build.
- `QuotaPlanEditor`-Bindung (v-model unverändert: `:enabled="useQuotaPlan"` / `:entries="quotaEntries"`)

### Unverändert: `QuotaPlanEditor.vue`
`QuotaPlanEditor.vue` (Sub-Slice 31) wurde nicht angefasst. Die Komponente ist ein controlled component mit eigenem lokalen State (props → lokal → emit). `quotaTotal`, `validationError`, `addSegment`, `removeSegment` in der Komponente sind UI-lokal und korrekt dort — sie operieren auf den lokalisierten Kopien der Props. Der Composable hält den kanonischen State, der via v-model mit der Komponente synchronisiert wird.

---

## LOC-Delta

- **Vorher:** 1666 LOC (`Step2EnvSetup.vue`, Baseline HEAD 04c0b70)
- **Nachher:** 1633 LOC
- **Delta:** −33 LOC

### Warum nicht −80 bis −110 LOC (wie in der Spec)?

Die Spec wurde vor Sub-Slice 31 (07eeadf) formuliert. Sub-Slice 31 hat bereits `quotaTotal`, `validationError`, `addSegment`, `removeSegment`, `_newEntryId` in `QuotaPlanEditor.vue` ausgelagert. Zum Baseline des aktuellen Slices (04c0b70) befanden sich in `Step2EnvSetup.vue` noch:

- STORAGE-Konstante (1 Z.)
- `useQuotaPlan`-Ref (1 Z.)
- `_loadQuotaEntries()`-Funktion (15 Z.)
- `quotaEntries`-Ref (1 Z.)
- Watch-Block für LocalStorage (6 Z.)
- Inline-Zod-Check in `triggerPrepare` (9 Z. → 4 Z.)

Effektive Einsparung: ~35 Zeilen entfernt - 7 Zeilen Composable-Destructuring + Import = netto −33.

Der größere Teil des Quota-Blocks war schon in Sub-Slice 31 extrahiert worden. Die Spec-Schätzung war für einen Zustand vor Sub-Slice 31 kalkuliert.

---

## Test-Counts

| Suite | Ergebnis |
|---|---|
| `usePersonaQuota.spec.ts` (neu) | 16 passed |
| `Step2EnvSetup`-Regression | 3 passed |
| Frontend `npm run check` gesamt | 282 passed, 35 test files |
| Backend `pytest -x -q` | 1541 passed, 9 skipped |
| Schema-Drift | clean |

---

## Test-Abdeckung (6 Cases)

1. **Add/Remove:** addQuotaSegment fügt Eintrag mit eindeutiger id hinzu; removeQuotaSegment(idx) entfernt korrekt; quotaTotal aktualisiert sich.
2. **Total-Computed:** 5/10/3 → 18; leere Liste → 0; nicht-numerische count → 0.
3. **Zod-Valid:** plausibler Plan mit aktiviertem Toggle → quotaValidationError === ''.
4. **Zod-Invalid:** leere Einträge / leerer Segment-Name / count=0 → Fehlerstring nicht leer.
5. **LocalStorage-Round-Trip:** Vorbeladen von localStorage → neue Composable-Instanz liest Einträge; Änderungen werden nach nextTick persistiert.
6. **Toggle-Reset:** useQuotaPlan=false → quotaValidationError leer unabhängig vom Plan-Zustand.

---

## Design-Entscheidungen

- **`t`-Injection via Parameter** statt `useI18n()` direkt: Tests benötigen keinen vue-i18n-Provider. Pattern konsistent mit `useSimulationPrepare.ts` (onLog-Injection).
- **`_counter` modulscoped**: ID-Eindeutigkeit über Composable-Instanzen hinweg, analog zu `QuotaPlanEditor.vue`.
- **`_loadQuotaEntries` vs. onMounted**: Laden in Modul-Scope (bei Composable-Aufruf) statt onMounted — konsistent mit dem bisherigen Verhalten in `Step2EnvSetup.vue`.
- **LocalStorage-Key unverändert** (`agora.quotaPlan`) — keine Migration, bestehende User-Daten bleiben erhalten.

---

## Risiken / Offene Punkte

- `fetchProfilesRealtime` in `Step2EnvSetup.vue` (Zeilen 318, 404, 436) ist nicht in der Datei definiert — pre-existing issue, durch diesen Slice weder eingeführt noch entfernt. Sollte in einem separaten Follow-up adressiert werden (vermutlich gehört das zur `useSimulationPrepare`-Rückgabe als exponierte Methode).
- Der Ziel-LOC <800 für `Step2EnvSetup.vue` (Task #203) erfordert weitere Sub-Slices (z. B. Persona-Library-Logik, Model-Picker-Logik).
