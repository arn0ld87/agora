# Arbeitsprotokoll — Sub-Slice J.1: refreshQuality aus 3-s-Tick herauslösen

**Datum:** 2026-05-04
**Branch:** `fix/j1-refresh-quality-watch`
**Refs:** Issue #219, P1, `docu/2026-05-03-request-rate-audit.md` Empfehlung 1

---

## Symptom

`Step2EnvSetup.vue` rief innerhalb von `fetchProfilesRealtime` bei jedem Poll-Tick
`personaReview.refreshQuality(props.simulationId)` auf. Da der Poll-Loop alle 3 s läuft,
feuerte `refreshQuality` (= `GET /api/simulation/<sim>/profiles/quality`) ebenfalls alle 3 s
— ein versteckter Doppel-HTTP-Call pro Runde, der in der Backend-Last nicht sichtbar war.

Fundstelle vor dem Fix:

```javascript
// Step2EnvSetup.vue:640-643 (vor Fix)
if (profiles.value.length) {
  personaReview.refreshQuality(props.simulationId)
}
```

## Root Cause

Der ursprüngliche Entwickler hatte `refreshQuality` als Seiteneffekt in den Tick gehängt,
um sicherzustellen, dass Quality-Daten nach Profil-Updates aktuell sind. Tatsächlich ändert
sich die Qualitätsbewertung aber nicht durch bloßes Pollen — nur durch user-initiierte
Aktionen (approve/reject/edit) oder beim erstmaligen Erscheinen der Profile. Der Call
im Tick war damit redundant ab dem zweiten Tick.

## Fix

### Entscheidung: 2-Watch-Variante

**Option A:** Einzelner `watch([profilesLength, simulationId], ...)` mit kombinierter Logik.
**Option B:** Zwei separate `watch`-Handler — einer für `profiles.value.length`, einer für
`props.simulationId`.

Gewählt: **Option B (2 Watches)** — klarer, weil die zwei Concerns orthogonal sind:
1. "Wann feuere ich refreshQuality?" → watch auf `profiles.value.length`
2. "Wann resette ich den Guard?" → watch auf `props.simulationId`

Ein kombinierter Watch hätte beide Concerns in einem Handler vermischt und die
Logik schwieriger lesbar gemacht.

### Guard-Mechanismus

`_qualityFetchedForSim` (ref, initialisiert `null`) speichert die simulationId, für die
`refreshQuality` bereits aufgerufen wurde. Vergleich beim Trigger verhindert
Doppel-Calls auch bei künstlichen Reactive-Zyklen.

### Sim-Wechsel-Handling

Der `watch` auf `props.simulationId` setzt `_qualityFetchedForSim` auf `null` zurück,
sobald eine neue simulationId reinkommt. Beim nächsten Profil-Batch (0 → n>0) des
neuen Sims feuert `refreshQuality` dann wieder einmal.

### Nicht entfernt

Die `refreshQuality`-Aufrufe in den approve/reject/edit-Handlern (Zeilen 199, 214, 241)
wurden nicht angefasst — das sind beabsichtigte user-triggered Updates.

## Verify

### rg-Prüfung

```
rg -n "refreshQuality" frontend/src/components/Step2EnvSetup.vue
```

Ergebnis:
- Zeilen 199, 214, 241: approve/reject/edit-Handler (unverändert, korrekt)
- Zeile 667: im `watch`-Handler (neu)
- Kein Treffer mehr innerhalb von `fetchProfilesRealtime`

### Vitest-Output

```
Test Files  19 passed (19)
     Tests  153 passed (153)
  Start at  06:09:21
  Duration  3.21s
```

Neue Tests in `Step2EnvSetup.spec.ts`:
- `ruft refreshQuality bei 5 Polling-Ticks genau 1× auf` — grün
- `ruft refreshQuality bei erneutem Sim-Wechsel (simulationId-Änderung) wieder 1× auf` — grün

### npm run check

`vue-tsc --noEmit` zeigt 2 pre-existierende TS-Fehler in `Step4Report.spec.ts`
(Zeilen 416/420, `schema_version: number` nicht assignable zu `2`, und `data: object`
nicht assignable zu vollem Typ) — diese waren auf dem Baseline-Branch bereits vorhanden
und sind out-of-scope für J.1.

Vitest: 153/153 grün. Build: erfolgreich.

### Schema-Diff

```
git diff --exit-code schemas/
# → sauber, kein Drift
```

## Out of Scope

- `Step4Report.spec.ts`-TS-Fehler (pre-existing, anderer Slice)
- Refactor von `usePersonaReview` (explizit verboten laut Task-Spec)
- Backend-Änderungen

---

## Followup nach Gemini-Review (PR #245)

**Datum:** 2026-05-04
**Gemini-Inline-Comment-IDs:** 3179364163 (HIGH), 3179364165 (MEDIUM), 3179364167 (MEDIUM)

### Gemini-Findings

1. **HIGH (3179364163) — `Step2EnvSetup.vue:657`:** Sim-Wechsel ohne Unmount setzt `profiles` nicht zurück. Wenn die neue Sim direkt Profile hat (`profiles.value.length > 0`), ist `prev !== 0` → `watch(() => profiles.value.length)` feuert nicht → kein `refreshQuality` für die neue Sim. Die 2-watch-Variante mit separatem Guard-Reset ist damit unvollständig: Der `simulationId`-Watch setzt den Guard zurück, aber der `profiles.length`-Watch triggert nur bei `prev === 0 && n > 0` — was bei schnellem Sim-Wechsel mit direkt vorhandenen Profilen nie eintritt.

2. **MEDIUM (3179364165) — `Step2EnvSetup.vue:670`:** Race-Condition. `props.simulationId` wird im Watch-Callback direkt referenziert, kann sich aber zwischen Guard-Setzung und `refreshQuality`-Call durch eine weitere schnelle Prop-Änderung verändert haben. `simId` sollte einmalig aus dem destrukturierten Callback-Argument bezogen werden.

3. **MEDIUM (3179364167) — `Step2EnvSetup.spec.ts:182`:** Der Sim-Wechsel-Test schiebt manuell `profiles: []` als Zwischen-Tick ein. Dieser leere Tick passiert in der realen Anwendung nicht — der Test deckt damit nur den unrealistischen Pfad ab und maskiert die in Finding 1 beschriebene Lücke.

### Lösung: 1-watch-Variante

Die 2-watch-Variante wurde vollständig durch einen einzelnen kombinierten Watch ersetzt:

```typescript
watch(
  () => [props.simulationId, profiles.value.length] as const,
  ([simId, n]) => {
    if (!simId) return
    if (n <= 0) return
    if (_qualityFetchedForSim.value === simId) return
    _qualityFetchedForSim.value = simId   // Guard vor dem Call (race-safe)
    personaReview.refreshQuality(simId)
  },
  { immediate: false },
)
```

**Warum 1-watch besser ist:**

- **HIGH adressiert:** Beim Sim-Wechsel ändert sich `simId` im Tuple — der Watch feuert unabhängig davon, ob `profiles.value.length` sich geändert hat. Selbst wenn die neue Sim direkt Profile hat, ist `simId !== _qualityFetchedForSim.value` → Trigger.
- **MEDIUM (Race) adressiert:** `simId` wird einmalig aus den destrukturierten Watch-Argumenten bezogen, nicht erneut von `props.simulationId` gelesen. Guard wird VOR dem `refreshQuality`-Call gesetzt.
- **MEDIUM (Test) adressiert:** Der Spec-Test wurde auf den realistischen Pfad umgeschrieben — neue Sim antwortet direkt mit Profilen, kein leerer Zwischen-Tick. Zusätzlich neuer Test-Case "Guard hält bei wachsender Profile-Anzahl (3 → 5 → 7)".

### Warum die ursprüngliche 2-watch-Entscheidung retrospektiv suboptimal war

Im Arbeitsprotokoll (Abschnitt "Entscheidung: 2-Watch-Variante") wurde Option B mit dem Argument gewählt, zwei orthogonale Concerns klarer zu trennen. Gemini hat zu Recht aufgezeigt, dass die zwei Handler nicht wirklich orthogonal sind: Der `profiles.length`-Watch hat eine implizite Abhängigkeit von `simulationId` (über den Guard), die in der 2-watch-Variante durch Reihenfolge-Annahmen zwischen den zwei Watches abgesichert wird. Diese Kopplung ist in einer einzigen Watch-Source mit Tuple-Destrukturierung expliziter und atomarer.

### Test-Refactor

- Bestehender "Sim-Wechsel"-Case umgeschrieben: Sim B antwortet direkt mit 5 Profilen.
- Neuer Case "Guard hält bei 3 → 5 → 7 Profile-Wachstum": verifikation dass `refreshQuality` 1× bleibt.
- Originaler "5 Ticks → 1 Call"-Case bleibt unverändert.
- Alle Assertions mit `toHaveBeenCalledTimes(N)` und `toHaveBeenNthCalledWith(K, simId)`.
