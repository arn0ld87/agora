# P4.4 — Drei E2E-Smokes für Report-Modi (strict/balanced/explorative)

**Datum:** 2026-05-11
**Branch:** `feat/p4-4-e2e-mode-smokes`
**Worktree:** `.claude/worktrees/p4-4-e2e`
**Refs:** PLAN.md §5.4, P4.1 (Verdrahtung gelandet 2026-05-11 mit `0add4f6` Backend + `f1034cc` Frontend), Issue v1.0-Output-Vertrag

## Befund

P4.1 ist auf `main` durch (`ReportMode` Literal in `report_v3.py:22`, `_resolve_report_mode` in `api/report.py:83`, `report_mode` als Pflichtfeld auf `ReportV3`). Damit ist P4.4 entblockt — der einzige verbleibende v1.0-Slice. PLAN.md §5.4 fordert drei Playwright-Smokes mit Mode-Banner-Snapshot.

## Spec-Schnitt

`frontend/tests/e2e/report-modes.spec.ts` (neu) macht in einer `test.describe.serial`-Gruppe:

| Test | Was wird abgedeckt |
|---|---|
| `mode=strict liefert passenden Mode-Banner` | `?mode=strict` triggert Report, MD-Export enthält `**Report-Modus:** … strict …` |
| `mode=balanced liefert passenden Mode-Banner` | analog für balanced |
| `mode=explorative liefert passenden Mode-Banner` | analog für explorative |
| `ohne mode-Param Default = balanced` | sicherer Fallback gegen Default-Drift |

Setup (`test.beforeAll`) macht den Vorlauf einmal: Auth-Token-Injection, Markdown-Upload, Graph-Build (Polling bis ready), Simulation-Create. Pro Mode-Test wird dann `triggerReport(..., {mode, forceRegenerate: true})` gerufen — `force_regenerate` verhindert, dass der zweite und dritte Trigger durch `_can_reuse_existing_report` (api/report.py:140) als Cache-Hit zurückgegeben werden.

## Helper-Erweiterung

`frontend/tests/e2e/helpers/report.ts::triggerReport` bekommt optionalen vierten Parameter:

```ts
options: { mode?: 'strict' | 'balanced' | 'explorative'; forceRegenerate?: boolean } = {}
```

`mode` wandert als Query-Parameter (`?mode=…`), `force_regenerate` in den Body — exakte Vertragsentsprechung zu `_resolve_report_mode` (`request.args.get("mode")`) und `generate_report` (`data.get("force_regenerate")`). Default-leeres Options-Objekt heißt: existierender Aufruf in `minimal-report.spec.ts` bricht nicht.

## Designentscheidungen

### Warum nur Markdown-Banner, kein JSON-Assert auf `report_mode`?

Der `?format=json`-Branch in `api/report.py:644` baut `ReportContractModel` (v2-Envelope, `schema_version=2`). Das v2-Modell hat **kein** `report_mode`-Feld — das lebt nur auf `ReportV3` (`report_v3.py:196`). Optionen wären gewesen:

1. **ZIP-Bundle entpacken** — `?format=zip` enthält `report-v3.json` direkt, aber Node hat kein eingebautes ZIP-API; das hieße `adm-zip`-Test-Dep dazuziehen.
2. **`?format=json`-Branch erweitern**, ReportV3 statt v2-Envelope zurückgeben — Scope-Creep, eigener Slice.
3. **Markdown-Banner als einzigen Smoke-Anker nehmen** — der Banner ist die einzige user-facing Wirkung von `report_mode` im Export-Pfad. Fängt jeden Drift, der das `report_mode`-Feld falsch in den Renderer pumpt.

Option 3 entspricht PLAN.md §5.4 wörtlich („Snapshot-Vergleich auf den Mode-Banner im exportierten Markdown") und ist die kleinste Spec, die echten Wert liefert. Strengere Field-Level-Asserts auf ReportV3 gehören in Backend-Snapshot-Tests (`backend/tests/eval/`), nicht in einen E2E-Smoke.

### Warum `force_regenerate=true` statt drei Simulationen?

`_can_reuse_existing_report` cached den Report pro `simulation_id` (sofern kein `llm_model_override` und keine Runtime-LLM-Override). Bei drei Modi auf derselben Simulation würde der zweite Trigger den ersten Report wiederverwenden — falsche Modus-Antwort. `force_regenerate=true` umgeht den Cache. Drei separate Simulationen anzulegen wäre die andere Option, würde aber den Setup-Overhead verdreifachen (Graph-Build dauert ~30 s pro Simulation).

### Warum `test.describe.serial`?

Bei `force_regenerate=true` und gleicher `simulation_id` schreibt der Report-Manager Status-Files mit dem `report_id` als Schlüssel — parallel laufende Modi würden sich nicht direkt überschreiben, aber die Status-Polling-Loops könnten fremde Reports sehen. Sequentiell ist robuster und kostet im Stub-Modus nur ~3-5 min Gesamtlaufzeit.

## Stub-Modus-Verhalten

`AGORA_E2E_LLM_MODE=stub` aktiviert deterministische LLM-Antworten (`llm_e2e_stub.py`). Pro Modus Build-Zeit ca. 30–90 s im Stub (analog `minimal-report.spec.ts`). Stub liefert 11 Sections, 1 Persona, kein Tabellen-Markdown — der Mode-Banner wird trotzdem gerendert, weil er aus `_MODE_BANNER` und nicht aus LLM-Output kommt.

## Verify

- [x] `npm run typecheck` (vue-tsc) → grün
- [x] `npm run lint` (eslint) → grün
- [x] `npm test -- --run` (Vitest, alle bestehenden Tests) → 500 / 500 passed
- [ ] `npm run test:e2e -- --grep "report modes"` → läuft erst in CI (lokal kein Docker-Stack hier)

## Was nicht in diesem PR ist

- `?format=json` um `report_mode` erweitern (eigener Slice).
- Backend-Snapshot-Test gegen die exakten `_MODE_BANNER`-Strings (PLAN.md §5.4 verlangt nur den Markdown-Smoke).
- ZIP-Bundle-Smoke (P4.3 ist bereits durch eigenen E2E-fähigen Pfad abgedeckt).

## Folgeaktionen nach Merge

1. PLAN.md §5.5 Phase-4-DoD: alle vier Häkchen werden grün.
2. PLAN.md §6 Definition of Done für v1.0: Phase-4-Häkchen grün; Score-Re-Bewertung gegen `docs/archive/old-plans/agora_bewertung_komplett.md` als nächster Schritt.
3. v1.0.0-Tag-Vorbereitung: Changelog, SBOM, License-Report.
