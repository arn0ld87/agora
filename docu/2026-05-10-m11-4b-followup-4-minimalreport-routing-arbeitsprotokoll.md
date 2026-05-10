# M11.4b-Followup-4 · Minimalreport-Smoke Routing/State-Fix

**Datum:** 2026-05-10
**Branch:** `fix/m11-4b-followup-4-outline-assertion`
**Status:** DONE

## Symptom

CI-Run `15c0aa2`: Minimalreport-Smoke schlägt fehl mit:

```
Error: ol.outline muss sichtbar sein (ReportOutlinePanel geladen)
expect(locator).toBeVisible() failed — element(s) not found, timeout 30000ms
Locator: locator('ol.outline')
```

Der Failure-Snapshot zeigt im `<main>`-Bereich den Graph-View sichtbar und zusätzlich
einen Schema-Mismatch-Alert:

```
Schema-Mismatch in report:
- outline.sections: Invalid input
```

## Trace-Analyse

Der Page-Snapshot enthielt einen `role=alert`-Banner:
```yaml
- alert [ref=e65]:
  - strong [ref=e66]: "Schema-Mismatch in report:"
  - list [ref=e67]:
    - listitem [ref=e68]: "outline.sections: Invalid input"
```

Das ist kein Routing-Problem (Variante B: Wizard-State). Die Route `/report/:reportId`
ist korrekt definiert und rendert `ReportView.vue` → `Step4Report.vue` (Variante A).

## Root Cause

**Zod-Spiegel-Drift:** `frontend/src/contracts/reportContract.ts:113`

```typescript
// ALT (falsch):
sections: z.array(ReportOutlineSectionSchema).min(2).max(5),

// NEU (korrekt):
sections: z.array(ReportOutlineSectionSchema).min(1).max(15),
```

Die Pydantic-Gegenstelle `backend/app/contracts/report_contract.py:160` wurde bereits
in **M11.4b-Followup-2** von `max_length=5` auf `max_length=15` angehoben (mit Kommentar
"M11.4b-Followup-2: max_length auf 15 angehoben"). Der Zod-Spiegel wurde nicht synchronisiert.

### Kausalkette

1. E2E-Stub (`llm_e2e_stub.py::_stub_plan_response`) generiert 11 Pflichtabschnitte.
2. Backend-Pydantic akzeptiert 11 Sections (max_length=15) → sendet Outline mit 11 Einträgen.
3. Frontend `Step4Report.vue:225` ruft `ReportOutlineSchema.parse(st.outline)` auf.
4. Zod schlägt fehl (11 > max(5)) → `recordSchemaError('outline', err)` → `schemaError.value` gesetzt.
5. `reportOutline.value` bleibt `null`.
6. `ReportOutlinePanel` wird nicht gerendert (`v-if="reportOutline"` in Step4Report).
7. `ol.outline` existiert nicht im DOM → E2E-Assert timeout.

## Variante-Entscheidung

**Variante A** (direkte Route mit korrektem Pfad) ist korrekt. Die Route `/report/:reportId`
rendert `Step4Report` korrekt. Das Problem liegt nicht in der Route oder im Wizard-State,
sondern in einem Schema-Drift zwischen Backend-Pydantic und Frontend-Zod.

Die Annahme aus der Task-Beschreibung ("Variante B oder C ist wahrscheinlich richtig")
ist am Code **falsifiziert**. Der Spec-Pfad (`goto('/report/${report_id}')`) ist korrekt.

**Spec-Vorgehen aus Cut-Analyse §5 angepasst:** Ursprüngliche Annahme war
Wizard-State-Problem. Nach Code-Analyse ist es ein Zod-Contract-Drift — der Spec bleibt
unverändert, nur der Contract wird korrigiert.

## Geänderte Dateien

### `frontend/src/contracts/reportContract.ts`

- Zeile 113: `.min(2).max(5)` → `.min(1).max(15)`
- Kommentar ergänzt mit Verweis auf M11.4b-Followup-2 und Drift-Ursache.

### `frontend/src/contracts/__tests__/reportContract.spec.ts`

- Import `ReportOutlineSchema` hinzugefügt.
- Neue `describe`-Suite `ReportOutlineSchema (Drift-Guard max-sections)`:
  - Akzeptiert 11 Sections (Stub-Pflichtabschnitte) — Regression-Guard.
  - Akzeptiert 15 Sections (Backend max_length=15).
  - Lehnt 16 Sections ab (über Backend-Grenze).
  - Lehnt leere sections-Liste ab (min=1).

## Verifikation

```
npm test -- --run   →  45 Test Files, 465 Tests, alle passed
npm run lint        →  0 Fehler
npm run typecheck   →  0 Fehler
npm run build       →  ✓ built in 1.74s
npx playwright test --list  →  6 Tests in 3 Files (minimal-report.spec.ts:130 enthalten)
```

## Warum kein Spec-Edit

Der Spec navigiert korrekt zu `/report/${report_id}` und assertiert `ol.outline`.
Beides ist korrekt und entspricht der App-Architektur. Der Fehler war im Contract,
nicht im Test-Pfad.
