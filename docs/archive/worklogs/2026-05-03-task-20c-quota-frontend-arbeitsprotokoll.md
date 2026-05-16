# Sub-Slice 20c — PersonaQuotaPlan Frontend-Editor in Step 2

**Datum:** 2026-05-03
**Branch:** `feat/task-20c-quota-frontend`
**Layer:** 4 (Frontend)
**Refs:** Schließt die 20a/20b/22-Quoten-Pipeline ab. Backend-Quelle:
[`backend/app/contracts/persona_contract.py`](backend/app/contracts/persona_contract.py),
Schema: [`schemas/persona-quota-plan.schema.json`](schemas/persona-quota-plan.schema.json).

## Symptom

Nach 20a/20b/22 war die serverseitige Quoten-Pipeline komplett: API
nimmt Plan, Service expandiert Pool auf Quote, Plan wird in
`simulation_config.json` persistiert. Aber das Frontend hatte keinen
Editor — User mussten den Plan per Postman/`curl` als
`payload.quota_plan = {...}` setzen, was praktisch unbenutzbar war.

## Fix

### 1. Zod-Spiegel + Helper

Neu: [`frontend/src/contracts/personaQuotaContract.ts`](frontend/src/contracts/personaQuotaContract.ts)

- `PersonaQuotaPlanSchema`: `z.object({ targets, total }).strict()` mit
  `superRefine`, das `total != sum(targets)` und leere `targets` als
  custom-Issues markiert. 1:1 zum Backend-Pydantic-Vertrag.
- `buildQuotaPlanFromEntries(entries)`: konvertiert UI-State
  (`Array<{segment, count}>`) in API-Body-Format
  (`{targets, total}`), droppt leere Segment-Strings.
- Tests: 10 Cases in
  [`frontend/src/contracts/__tests__/personaQuotaContract.spec.ts`](frontend/src/contracts/__tests__/personaQuotaContract.spec.ts) —
  konsistenter Plan akzeptiert, total-Mismatch / leerer Plan / count<1
  / count>200 / total>500 / extra-Felder abgelehnt; Helper-Roundtrip
  ergibt Schema-konformen Plan.

### 2. Step2EnvSetup.vue

- **State:** `useQuotaPlan` (boolean), `quotaEntries` (reactive Array
  of `{segment, count}`), `quotaTotal` (computed sum),
  `quotaValidationError` (computed Zod-Issue-Message).
- **LocalStorage:** Key `agora.quotaPlan`, persistiert das Plan-Objekt
  (nicht die Entries-Array, damit Reload-Resilience auch über
  Browser-Restarts funktioniert). `_loadQuotaEntries()` rekonstruiert
  die Entry-Reihenfolge aus `Object.entries(targets)` (insertion-order).
- **UI:** Optionaler Toggle „Persona-Quote pro Segment erzwingen" neben
  dem bestehenden „Max. Anzahl Agenten begrenzen". Wenn aktiv: Liste
  von Eingabezeilen `[segment-name] [count] [−]`, `+ Segment hinzufügen`-
  Button, Total-Anzeige, ⚠-Hint bei Validierungsfehler. Hint-Text
  erinnert daran, dass `segment` exakt einem `entity_type` aus der
  Ontology entsprechen muss (sonst failt Backend-Generator-Erzwingung
  in 20b mit klarem `ValueError`).
- **Payload:** `startPrepare()` baut `payload.quota_plan` nur wenn
  `useQuotaPlan` aktiv und Schema-Validierung erfolgreich. Bei Fehler
  → `addLog` + `update-status: error`, kein API-Call (verhindert
  unnötige HTTP-400-Roundtrips).

## Tests

- **Frontend:** 10 neue Cases in
  [`frontend/src/contracts/__tests__/personaQuotaContract.spec.ts`](frontend/src/contracts/__tests__/personaQuotaContract.spec.ts).
  `npm test -- --run` → 16 Files, 135 Tests, alle grün.
- **Backend (Regression):** `uv run pytest -x -q` → 1283 passed, keine
  Drift gegen 20a/20b/22.
- **Build:** `npm run build` clean, ein Hauptbundle 621 kB (gzip 204 kB),
  CSS 128 kB (gzip 20 kB). Bundle-Größe unverändert ggü. main, +Quoten-
  UI ist im normalen Tree-Shake mit drin.
- **Lint:** `npm run lint` clean.

## Verifikation

```
$ npm test -- --run
16 Test Files passed | 135 Tests passed

$ npm run build
✓ built in 3.25s

$ uv run pytest -x -q
1283 passed, 2 skipped

$ uv run python -m app.contracts.dump_schemas
✓ alle Schemas (kein Drift)

$ docker exec agora curl -fsS http://localhost:5001/health
{"service":"Agora Backend","status":"ok"}
```

End-to-End-Verifikation ist nutzerseitig — User aktiviert Toggle in
Step 2, definiert Segmente, klickt „Generate", Sim läuft mit
expandierter Persona-Quote durch.

## Geänderte Dateien

- `frontend/src/contracts/personaQuotaContract.ts` (neu)
- `frontend/src/contracts/__tests__/personaQuotaContract.spec.ts` (neu)
- `frontend/src/components/Step2EnvSetup.vue` — Quoten-State + UI + Payload + CSS
- `CHANGELOG.md` — `[Unreleased]` / Added-Block

## Quoten-Pipeline ist jetzt komplett

| Slice | Layer | Was |
|---|---|---|
| 06 | Contracts | `PersonaQuotaPlan` + `PersonaQuotaActual` Pydantic-Modelle, post-generation Validator |
| 20a | API | `_parse_quota_plan` Body-Parser + Pass-Through in `simulation_prepare` und `runs.py` |
| 22 | Persistence | `_phase_generate_config` schreibt Plan in `simulation_config.json`, Restart liest ihn wieder |
| 20b | Service | `_expand_entities_for_quota` Round-Robin-Expansion vor Phase 2 |
| **20c** | **Frontend** | **Step2-Editor + Zod-Spiegel + LocalStorage-Persistenz** |

Damit löst die Pipeline Alex' Use-Case aus dem Wahrnehmungsanalyse-Prompt
(50 Personas + 4 Multiplikatoren in 10 Segmenten) — sofern die Ontology
die 10 Segment-Types liefert (`ONTOLOGY_MAX_ENTITY_TYPES` ggf. hochsetzen).
