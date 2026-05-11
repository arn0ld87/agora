# Sub-Slice 33 — Persona-Regenerate Frontend-Wiring (Issue #70)

**Datum:** 2026-05-05
**Branch:** `feat/layer-8-task-30b-persona-regenerate-ui`
**Autor:** agora-frontend-worker

## Was

Frontend-Wiring für den Backend-Regenerate-Endpoint aus Sub-Slice 32 (commit cb3cd75).

- `POST /api/simulation/<sim>/profiles/<username>/regenerate` (Backend-Endpoint)
- State-Machine: pending|approved|rejected → regenerating → pending
- Start-Gate: blockt, solange irgendeine Persona im Status `regenerating` ist

## Geänderte Dateien

| Datei | Typ | Beschreibung |
|---|---|---|
| `frontend/src/api/simulation.ts` | Changed | `regenerateSimulationProfile()` hinzugefügt |
| `frontend/src/composables/usePersonaReview.ts` | Changed | `regenerate()` Methode + Interface-Erweiterung |
| `frontend/src/components/Step2EnvSetup.vue` | Changed | Regenerate-Button + Hint-Input + State-Pill + Start-Gate-Block |
| `frontend/src/i18n/locales/de.json` | Changed | 4 neue `step2.persona.*`-Keys |
| `frontend/src/i18n/locales/en.json` | Changed | 4 neue `step2.persona.*`-Keys |
| `frontend/src/composables/__tests__/usePersonaReview.spec.ts` | Neu | 9 Vitest-Cases für `regenerate()` |

## Warum

Sub-Slice 32 lieferte Backend + Tests. Der Commit-Body markierte explizit „Frontend-Wiring + UI-Buttons folgen separat." Dieser Slice schließt diesen offenen Punkt.

## Akzeptanzkriterien (alle grün)

- `regenerateSimulationProfile` in `api/simulation.ts` vorhanden
- `regenerate()` im Composable-Return-Objekt neben `approve`, `reject`
- Regenerate-Button im Persona-Modal (neben Approve/Reject)
- Optionaler Hint-Input (Inline-Textarea im Modal, kein Modal-Overkill)
- State-Pill `regenerating` in `STATUS_VARIANTS`/`STATUS_LABELS`
- Start-Button blockiert wenn `hasRegeneratingPersona === true`
- Tooltip/Disabled-Hint mit `t('step2.persona.regeneratingBlock')`
- Alle 4 i18n-Keys in de.json + en.json, keine hartkodierten Strings
- Vitest-Spec: 9 Fälle (Erfolg, mit Hint, ohne Hint, Idempotenz, success=false, Fallback-Fehlermeldung, Netzwerkfehler, Rückgabe-Struktur, Approve/Reject-Regression)

## Technische Entscheidungen

- `regenerate()` im Composable folgt dem identischen Pattern wie `approve()`/`reject()`: `ProfileEnvelope`-Cast via `unknown`, `res?.success`-Check, `throw` bei Fehler.
- Hint-Input als schlichtes `<input type="text">` unterhalb der Review-Issues-Liste im Modal — kein Modal-Overkill, kein Dialog-in-Dialog.
- `hasRegeneratingPersona` als `computed` auf `profiles.value` — kein separater API-Polling-Endpunkt nötig, da `profiles` bereits per Realtime-Polling befüllt wird.
- `STATUS_VARIANTS.regenerating = 'accent'` — visuell unterscheidbar von approved (success) und rejected (error).
- Keine Backend-Edits — Endpoint ist aus Sub-Slice 32 vollständig vorhanden.
