# Arbeitsprotokoll Sub-Slice 15 — Step4Report.vue strict-Zod-Parse

**Datum:** 2026-05-02
**Branch:** feat/layer-4-task-15-step4report-strict-zod
**Issue:** Closes #172
**Layer:** 4

## Ziel

Tolerante Fallback-Renderer in `Step4Report.vue` entfernen und durch strikte Zod-Parse-Pfade ersetzen. Schema-Mismatch soll einen sichtbaren UI-Banner erzeugen statt still durchzurutschen.

## Geaenderte Dateien

### `frontend/src/contracts/reportContract.ts`

- `ReportOutline`-Type via `z.infer` ergaenzt (war als Schema vorhanden, aber kein Type-Export).
- `ApiErrorEnvelope.error` auf optional gestellt (war `string` Pflicht, was Test-Case "kein error-String" brach).

### `frontend/src/components/Step4Report.vue`

- `<script setup>` auf `<script setup lang="ts">` umgestellt.
- Import-Block: `ReportSchema`, `ReportOutlineSchema`, `EvidenceMapSchema`, typisierte Imports aus `reportContract.ts`.
- Neuer `schemaError`-State (`ref`) + `recordSchemaError(where, error)`-Funktion — extrahiert Zod-Issue-Pfade strukturiert.
- **`pollStatus`**: `reportOutline.value = st.outline || reportOutline.value` ersetzt durch `ReportOutlineSchema.parse(st.outline)` mit `recordSchemaError`.
- **`pollStatus` + `onMounted`**: `fullReport.value = full.data` (beide Stellen) ersetzt durch `ReportSchema.parse(full.data)` mit `recordSchemaError`.
- **`loadEvidence`**: `catch { /* optional */ }` ersetzt durch `EvidenceMapSchema.parse(res.data)` mit `recordSchemaError('evidence', err)`. Kein stilles Schlucken mehr.
- **`claimConfidenceScore`**: Fallback auf `claim?.confidence` als Number entfernt — liest nur `confidence_score`.
- **`claimConfidenceLabel`**: Fallback auf `claim?.confidence` als String entfernt — liest nur `confidence_label`.
- **`claimEvidenceItems`**: `evidence_items`-Fallback entfernt — liest nur `claim.evidence`.
- **`evidenceSnippet`**: Mehrfach-Fallback (`value → source → JSON.stringify(item.raw)`) entfernt — liest nur `item.snippet`.
- **`reportMarkdown`**: Fallbacks auf `full_text`, `markdown`, `sections[].content` entfernt — liest nur `markdown_content` (Vertragsfeld im ReportSchema).
- UI-Banner `<div class="schema-error" role="alert">` im Template-Root, CSS via Design-System-Tokens (`--status-error`).
- Alle API-Call-Return-Werte mit lokalen Interface-Typen (`ApiResult`, `StatusApiResult`) versehen, da die JS-API-Dateien keine TS-Deklarationen haben.

### `frontend/src/api/envelope.ts`

- `ApiErrorEnvelope.error` von `string` auf `string?` (optional) geaendert — spiegelt Test-Case Z. 46 in `envelope.spec.ts` der explizit den "kein error-String"-Fallback prueft.

### `frontend/eslint.config.js`

- Separater Block fuer `*.vue`-Files mit `vue-eslint-parser` als Parser und `parserOptions.parser: false` (vue-eslint-parser-Feature: ueberspringt `<script lang="ts">`-Block). TS-Pruefung laeuft ausschliesslich via `vue-tsc`. Ohne diesen Block wuerde ESLint an TypeScript-Syntax in Vue-Files scheitern, da `@typescript-eslint/parser` nicht installiert ist.

### `frontend/src/components/__tests__/Step4Report.spec.ts` (neu)

3 Test-Cases:
1. Valider Payload → kein Banner.
2. Unbekanntes Top-Level-Feld im Report-Payload (`.strict()` greift) → Banner mit `report`.
3. Fehlendes `simulation_id` in EvidenceMap → Banner mit `evidence`.

## Verifikation

- `npx vue-tsc --noEmit`: 0 Fehler.
- `npm run lint`: 0 Fehler.
- `npm test`: 97 Tests gruen (13 Test-Files).
- `uv run python -m app.contracts.dump_schemas && git diff schemas/`: clean.
- Akzeptanz-rg-Checks: alle 5 clean.

## Bewusste Entscheidungen

- `reportMarkdown`-Computed wurde auf `markdown_content` reduziert. Die alten Fallbacks (`full_text`, `markdown`, `sections[].content`) sind kein Teil des Vertrags und wurden nie vom Backend befoellt. Ihr Entfernen ist kein Breaking Change.
- `lang="ts"` fuer den gesamten Script-Block: alle pre-existing Fehler durch fehlende TS-Typen wurden gefixt (API-Cast-Interfaces, Parameter-Typen). Kein `any` im Ergebnis.
