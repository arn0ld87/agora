# Arbeitsprotokoll Sub-Slice 39 — usePersonaLibrary

**Datum:** 2026-05-06
**Refs:** #203 (Step2EnvSetup.vue Decomposition)
**Branch:** feat/task-47-sub-39-use-persona-library

## Ziel

Persona-Library + CRUD-Block aus `Step2EnvSetup.vue` in ein neues TypeScript-Composable `usePersonaLibrary.ts` extrahieren.

## LOC-Vorher/Nachher

| Datei | Vorher | Nachher |
|---|---|---|
| `Step2EnvSetup.vue` | 1467 | 1314 |
| `usePersonaLibrary.ts` | — | 271 |

Netto-Reduktion Step2EnvSetup.vue: **153 LOC** (10,4 %).

## Was extrahiert wurde

### State (Library)
- `personaTemplates` — Ref<unknown[]>
- `isLoadingPersonaLibrary` — Ref<boolean>
- `personaLibraryError` — Ref<string>
- `savingPersonaKeys` — Ref<Set<string>>
- `usingPersonaTemplateIds` — Ref<Set<string>>

### State (Manual Editor)
- `showAddPersonaModal` — Ref<boolean>
- `newPersona` — Ref mit Default-Shape
- `isSavingPersona` — Ref<boolean>

### Helpers
- `profileKey(profile)` — pure, bevorzugt template_id
- `profilePayload(profile)` — Whitelist-Filter (17 Felder), strippt undefined/null/leer

### Actions
- `resetNewPersona()` — setzt newPersona auf DEFAULT_SHAPE zurück
- `submitNewPersona()` — CSV→Array, age-Strip, addSimulationProfile, Modal-Close
- `loadPersonaLibrary()` — listPersonaTemplates, Error-Handling
- `savePersona(profile)` — savingPersonaKeys-Toggle, savePersonaTemplate, Reload
- `saveAllPersonas()` — Loop über profiles.value
- `usePersonaTemplate(template)` — source_entity_type: 'library', fetchProfilesRealtime
- `removePersonaTemplate(templateId)` — confirm-Gate, deletePersonaTemplate
- `removePersona(username)` — confirm-Gate, deleteSimulationProfile

## Dependency-Injection-Pattern

```ts
export interface UsePersonaLibraryDeps {
  simulationId: Ref<string | null | undefined>
  profiles: Ref<unknown[]>
  fetchProfilesRealtime: () => Promise<void> | void
  addLog: (msg: string) => void
  confirmFn?: (msg: string) => boolean  // Test-Override
}
```

`confirmFn` nutzt `deps.confirmFn ?? globalThis.confirm` — vollständig testbar ohne DOM.

## API-Imports aus Step2EnvSetup.vue entfernt

- `addSimulationProfile` — jetzt im Composable
- `deleteSimulationProfile` — jetzt im Composable
- `listPersonaTemplates` — jetzt im Composable
- `savePersonaTemplate` — jetzt im Composable
- `deletePersonaTemplate` — jetzt im Composable

Vorab via `rg` geprüft: alle 5 Funktionen wurden ausschließlich im extrahierten Block verwendet.

## TDD-Verlauf

RED: Spec-File erstellt, Composable fehlte → Compile-Fehler bestätigt.
GREEN: Composable implementiert → 37 Tests sofort grün.

## Test-Output

```
Test Files  1 passed (1)
     Tests  37 passed (37)
  Duration  1.09s
```

## Akzeptanz-Belege

| Kriterium | Ergebnis |
|---|---|
| LOC Step2EnvSetup.vue < 1340 | 1314 ✓ |
| npm test (full) | 377 passed, 38 files ✓ |
| npm run check | vue-tsc OK, build OK ✓ |
| rg-Restspur (Definitionen) | leer ✓ |
| Schema-Drift | leer ✓ |

## Nicht angetastet

- `filteredPersonas` / `visiblePersonas` (Z. 279+) — bleibt im Component für Sub-Slice 40.
- `selectedProfile`, `personaSearch`, `showAllPersonas` — UI-State, bleibt im Component.
- Filter-Block (Sub-Slice 40).
