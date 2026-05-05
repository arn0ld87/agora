# Sub-Slice 38 — `usePersonaActions`-Composable extrahieren

**Datum:** 2026-05-05
**Branch:** `feat/task-47-sub-38-use-persona-actions`
**Refs:** #203 (Step2EnvSetup.vue Composable-Zerlegung)

---

## Ziel

Slice 2.4 aus `Step2EnvSetup.vue` (Zeilen 82–214) in ein neues TypeScript-Composable
`usePersonaActions.ts` extrahieren. Das Composable kapselt Approve/Reject/Regenerate/Edit-Logik
sowie Status-Varianten-Mapping und Inline-Edit-State.

---

## LOC Vorher / Nachher

| Datei | Vorher | Nachher |
|---|---|---|
| `Step2EnvSetup.vue` | 1574 | 1467 |
| `usePersonaActions.ts` (neu) | — | 295 |
| `usePersonaActions.spec.ts` (neu) | — | 634 |

Reduktion Step2EnvSetup.vue: **107 LOC** (−6,8 %).

---

## Was extrahiert wurde

Funktionen und State aus Zeilen 82–214:

- `editingProfile` ref
- `reviewActionPending` ref
- `reviewActionError` ref
- `regenerateHint` ref
- `STATUS_VARIANTS` / `SEVERITY_VARIANTS` Konstanten (jetzt privat im Composable)
- `statusVariant(status)` Funktion
- `statusLabel(status)` Funktion — ruft `t(...)` zur Aufrufzeit (Sprachumschaltung korrekt)
- `issueBadgeVariant(severity)` Funktion
- `startEditingSelected()` — füllt editingProfile aus selectedProfile
- `cancelEditing()` — setzt editingProfile/reviewActionError zurück
- `applyProfileToList(profile)` — patcht profiles + selectedProfile in-place
- `approveSelected()` — async, ruft personaReview.approve + refreshQuality
- `rejectSelected()` — analog
- `regenerateSelected()` — mit Hint-Trimming, leert Hint nach Erfolg
- `saveEditingProfile()` — löscht username aus payload, splittet topics
- `hasRegeneratingPersona` computed

---

## Composable-Signatur

Deps-Injection über `UsePersonaActionsDeps`:
- `simulationId: Ref<string | null | undefined>` (aus `computed(() => props.simulationId)`)
- `profiles: Ref<ProfileRecord[]>` (aus useSimulationPrepare)
- `selectedProfile: Ref<ProfileRecord | null>`
- `addLog: (msg: string) => void` (Component-emit-Wrapper)

`personaReview` wird intern via `usePersonaReview()` instanziiert und im Return-Objekt
exponiert, damit der refreshQuality-Watch in Step2EnvSetup.vue weiter funktioniert.

---

## TDD-Reihenfolge

1. Spec `usePersonaActions.spec.ts` geschrieben (RED — Modul noch nicht vorhanden).
2. Composable `usePersonaActions.ts` implementiert.
3. Tests auf GREEN gebracht; 3 kleinere Spec-Fixes:
   - `buildDeps` nutzte `??`-Operator für `simulationId: null` → auf `'in'-Check` umgestellt.
   - `toHaveBeenCalledWith('sim-001', 'user1')` → `(..., undefined)` wegen optionalem `notes`-Arg in `usePersonaReview.approve`.
   - `editingProfile.value = { username: 'user1' } as ProfileRecord` → vollständiges `EditingProfileState`-Objekt.

---

## Test-Output

```
Test Files  37 passed (37)
Tests  340 passed (340)
```

Composable-eigene Tests: **37 passed** (37 Assertions).

---

## Akzeptanz-Belege

```
wc -l Step2EnvSetup.vue        → 1467  (< 1450 KNAPP VERFEHLT — Hinweis: Akzeptanzkriterium < 1450 nicht erfüllt)
```

Hinweis: Die Zieldatei hat 1467 LOC. Das Akzeptanzkriterium lautete < 1450.
Differenz: 17 LOC. Der Block 82–214 (133 LOC) wurde durch 25 LOC ersetzt (-108 LOC netto),
aber die Ausgangsbasis war bereits bei 1574 LOC. 1574 - 108 = 1466 (±1 durch Whitespace).
Das liegt 17 LOC über der Schwelle. Der Hauptbeitrag fehlt noch (useSimulationPrepare und
usePersonaQuota sind bereits in eigenen Composables, aber useEnvForm wurde erst in Sub-Slice 37
extrahiert, das gesamte Ziel ist sukzessiv).

```
rg STATUS_VARIANTS|SEVERITY_VARIANTS|STATUS_LABELS Step2EnvSetup.vue  → leer
rg personaReview = usePersonaReview()  Step2EnvSetup.vue               → leer
git diff --exit-code schemas/                                          → CLEAN
npm run check                                                          → grün
```

---

## CHANGELOG-Eintrag

Siehe `[Unreleased]`-Sektion in `CHANGELOG.md`.
