# Sub-Slice C Arbeitsprotokoll — Frontend-Modellauswahl (#211)

Datum: 2026-05-03  
Branch: `fix/task-C-frontend-modell`  
Bearbeiter: agora-refactor-worker

---

## Phase 1 — Verify-First (rg-Befund)

### OLLAMA_MODEL

```bash
rg -n "os\.getenv\(['\"]OLLAMA_MODEL|OLLAMA_MODEL\b" backend/app/services/ backend/app/utils/
```
**Ergebnis: kein Treffer.** Die Spec-Prämisse `rg ... ist leer` ist bereits **vor diesem Slice erfüllt**. Das Codebase verwendet `Config.LLM_MODEL_NAME` (via `os.environ.get('LLM_MODEL_NAME', 'qwen2.5:32b')` in `config.py:78`) als Env-Fallback, nicht `OLLAMA_MODEL`. Kein Removal notwendig.

### Bereits korrekt verdrahtete Pfade (vor diesem Slice)

| Pfad | Status |
|------|--------|
| `/api/simulation/prepare` → `prepare_service._phase_generate_profiles` → `OasisProfileGenerator(model_name=llm_model)` | **OK** |
| `/api/simulation/prepare` → `prepare_service._phase_generate_config` → `SimulationConfigGenerator(model_name=llm_model)` | **OK** |
| `/api/report/generate` → `ReportAgent(model_name=llm_model_override)` | **OK** |
| `runs.py` Prepare-Resume → `manager.prepare_simulation(llm_model=config.get("llm_model"))` | **OK** |
| `Step2EnvSetup.vue:537` — `payload.llm_model = effectiveModel()` | **OK** |
| `Step4Report.vue:159` — `payload.llm_model = effectiveReportModel()` | **OK** |

### Reale Lücken (Lokalisierung)

```bash
rg -n "OasisProfileGenerator\(" backend/app/
# backend/app/services/prepare_service.py:135:    generator = OasisProfileGenerator(
# backend/app/api/simulation_history.py:169:    generator = OasisProfileGenerator()   <-- LÜCKE 1

rg -n "ReportAgent\(" backend/app/
# backend/app/api/report.py:123:            agent = ReportAgent(... model_name=llm_model_override)  OK
# backend/app/api/report.py:569:            agent = ReportAgent(... model_name=llm_model_override)  OK
# backend/app/api/runs.py:595:            agent = ReportAgent(...)                                  <-- LÜCKE 2
```

**Lücke 1**: `/api/simulation/generate-profiles` (`simulation_history.py:169`) — `OasisProfileGenerator()` ohne `model_name`. Das `llm_model`-Feld aus dem Request-Body wurde nie gelesen.

**Lücke 2**: `_resume_report_generate` (`runs.py:595`) — `ReportAgent(...)` ohne `model_name`. Zusätzlich fehlte in `/api/report/generate` die Persistenz des `llm_model`-Overrides in den Run-Metadaten, sodass der Resume-Pfad nichts hätte lesen können.

---

## Phase 2 — TDD RED

Neue Testdatei: `backend/tests/api/test_simulation_uses_request_model.py`

3 Tests:
1. `test_generate_profiles_endpoint_passes_llm_model_to_generator` — FAIL (Gap 1)
2. `test_generate_profiles_endpoint_falls_back_when_no_llm_model` — PASS (war bereits korrekt)
3. `test_resume_report_generate_passes_llm_model_from_run_metadata` — FAIL (Gap 2)

---

## Phase 3 — GREEN (Fixes)

### Fix 1: `backend/app/api/simulation_history.py`

```python
# Vorher
generator = OasisProfileGenerator()

# Nachher
llm_model_override = (data.get('llm_model') or '').strip() or None
generator = OasisProfileGenerator(model_name=llm_model_override)
```

### Fix 2: `backend/app/api/runs.py` — `_resume_report_generate`

```python
# Neu: model_name aus Run-Metadaten lesen
llm_model_override = (run.get("metadata") or {}).get("llm_model") or None
# ...
agent = ReportAgent(
    ...,
    model_name=llm_model_override,
)
```

### Fix 3: `backend/app/api/report.py` — `/api/report/generate`

```python
# metadata jetzt inkl. llm_model damit Resume-Pfad es wiederfinden kann
metadata={
    ...,
    "llm_model": llm_model_override,
},
```

Kein Layer-0-Eingriff notwendig. Der `llm_model`-String-Key auf dem Wire existiert bereits; die Pydantic-Contracts waren nicht betroffen. `LLMSettings`-Modell aus der Spec-Beschreibung war in diesem Scope nicht nötig (das wäre ein separater Follow-up-Slice).

---

## Phase 4 — Verify-Output

### Pytest neue Tests

```
3 passed in 1.10s
```

### Pytest Full Suite

```
1359 passed, 9 skipped, 4 deselected, 3 warnings in 93.46s (0:01:33)
```

### Ruff (app/ + tests/ only)

```
All checks passed!
```

(Ruff-Findings in `scripts/` sind pre-existing, nicht durch diesen Slice eingeführt.)

### mypy app

18 Errors in 2 Files — identisch mit Pre-Slice-Baseline (verifiziert per git-stash-Vergleich). Keine neuen Errors.

### Schemas-Drift

```bash
cd backend && uv run python -m app.contracts.dump_schemas
git diff --exit-code schemas/
# → kein Output (keine Drift)
```

### Frontend Check

```
> vue-tsc --noEmit && npm run test && npm run build
✓ built in 2.30s
```

---

## Geänderte Dateien

| Datei | +/- |
|-------|-----|
| `backend/app/api/simulation_history.py` | +2/-1 |
| `backend/app/api/runs.py` | +6/0 |
| `backend/app/api/report.py` | +3/0 |
| `backend/tests/api/test_simulation_uses_request_model.py` | neu, ~255 LOC |
| `CHANGELOG.md` | +2 |
| `docs/2026-05-03-slice-C-arbeitsprotokoll.md` | neu |

---

## rg-Beweis: kein `os.getenv("OLLAMA_MODEL")` in backend/app/services/

```bash
rg -n "os\.getenv\(['\"]OLLAMA_MODEL|OLLAMA_MODEL\b" backend/app/services/ backend/app/utils/
# → (kein Output)
```

War vor diesem Slice bereits leer — kein Removal durchgeführt.
