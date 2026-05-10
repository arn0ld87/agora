# Arbeitsprotokoll P4.1 — Report-Modi strict/balanced/explorative

**Datum:** 2026-05-11
**Slice:** P4.1 (PLAN.md §5.1)
**Status:** grün — 49 Backend-Tests, 13 Frontend-Tests

---

## Was wurde gemacht

### Layer-0-Anker (bereits vorhanden, nicht angefasst)
- `backend/app/contracts/report_v3.py` — `ReportMode = Literal["strict", "balanced", "explorative"]`, `DEFAULT_REPORT_MODE = "balanced"`, `ReportV3.report_mode`-Feld
- `backend/app/contracts/__init__.py` — Re-Exporte

### Layer-1+ Verdrahtung (dieser Slice)

**`backend/app/api/report.py`**
- Import: `ReportMode`, `DEFAULT_REPORT_MODE` aus `app.contracts`
- `_VALID_REPORT_MODES` Konstante
- `_resolve_report_mode()` Helper: liest `?mode=`-Query-Param, validiert gegen Literal-Werte, 400 bei Unknown, Default bei None
- POST /generate: `_resolve_report_mode()` vor Manager-Aufruf; `report_mode` in `agent.generate_report(report_mode=...)` und `ReportManager.save_report(report_mode=...)` durchgereicht

**`backend/app/services/report_agent/manager.py`**
- `build_report_v3`: neuer Keyword-Parameter `report_mode: ReportMode = DEFAULT_REPORT_MODE`
  - `strict`: Low-confidence Claims (`confidence == "low"`) werden gedroppt
  - Kein-Evidence-Claims: bereits vorher gedroppt (existierendes Verhalten, alle Modi)
  - `report_mode` ins `ReportV3`-Konstrukt eingesetzt
- `save_report`: neuer Keyword-Parameter `report_mode: ReportMode = DEFAULT_REPORT_MODE`, reicht an `build_report_v3` weiter

**`backend/app/services/report_agent/workflow.py`**
- `generate_report`: neuer Keyword-Parameter `report_mode: ReportMode = DEFAULT_REPORT_MODE`
- Quote-Anchor-Validator: `explorative` → überspringen; `balanced` → Best-Effort-Repair-Retry (unverändert); `strict` → Repair-Retry mit `logger.error` bei Fehlschlag (statt `logger.warning`)
- Mode wird im Log-Statement mitgeführt

**`backend/app/services/report_agent/markdown_renderer.py`**
- `_MODE_BANNER`-Dict mit Blockquote-Texten für alle drei Modi
- `render_report_v3`: Banner nach Report-Header, vor erstem Section-Header eingefügt

**`backend/app/services/report_agent/agent.py`**
- `generate_report`-Methode: `report_mode: str = "balanced"` als Keyword-Parameter, Delegation an `generate_report_impl(..., report_mode=report_mode)`

**`frontend/src/contracts/reportV3Contract.ts`**
- `ReportModeSchema = z.enum(["strict", "balanced", "explorative"])`
- `DEFAULT_REPORT_MODE = "balanced"` als Export
- `ReportV3Schema`: `report_mode: ReportModeSchema.default("balanced")` ergänzt

**`frontend/src/contracts/__tests__/reportV3Contract.spec.ts`**
- MINIMAL_REPORT_V3: `report_mode: "balanced"` ergänzt
- 3 neue Tests: Default-Fallback, Accept strict/explorative, Reject unknown

---

## Mode-Switch-Strategie

Der Mode-Switch sitzt **an zwei Stellen**:

1. **`manager.py::build_report_v3`** — Post-hoc-Filterung auf fertiger Evidence-Map:
   - `strict`: Low-confidence Claims gedroppt (alle anderen bleiben)
   - `balanced`/`explorative`: kein zusätzlicher Drop über den Evidence-Gate hinaus

2. **`workflow.py::generate_report`** — Inline-Steuerung des Quote-Anchor-Validators:
   - `explorative`: Validator vollständig übersprungen
   - `balanced`: Best-Effort-Repair-Retry (unverändertes Verhalten)
   - `strict`: Repair-Retry + `logger.error` bei persistentem Fehlschlag

Bewusste Entscheidung gegen Strategy-Pattern: Der Switch ist schmal und lokalisiert. Ein Strategy-Pattern würde mehr Indirektionsschichten erzeugen als der Nutzen rechtfertigt.

---

## Risiken

- **Strict-Mode + Low-Conf-Drop**: Wenn alle Claims low-confidence sind, kann der Report leer wirken. Das ist beabsichtigtes Verhalten (kein Evidence → kein Claim in strict).
- **explorative-Banner**: Sichtbar im Markdown, kein Validator. Nutzer muss die Verantwortung für nicht-belegte Inhalte übernehmen.
- **Agent.generate_report-Signatur**: `report_mode: str = "balanced"` statt `ReportMode` im Typ-Hint (Agent-Layer bleibt typing-lite), weil `agent.py` noch nicht vollständig Pydantic-migriert ist. `# type: ignore` im Delegationsaufruf.

---

## Test-Counts

| Kategorie | Anzahl | Status |
|---|---|---|
| `test_report_v3_contract.py` (P4.1 neu) | 6 | grün |
| `test_report_modes.py` (neu) | 8 | grün |
| `test_report_modes_workflow.py` (neu) | 11 | grün |
| `reportV3Contract.spec.ts` (3 neu) | 13 gesamt | grün |
| Backend gesamt | 1866 passed, 9 skipped | grün |
