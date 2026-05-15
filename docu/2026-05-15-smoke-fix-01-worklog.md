# Worklog 2026-05-15 — Smoke-Fix Slice 01

**Branch:** `feat/smoke-fix-01-strict-schema` → merged `--no-ff` in `feat/smoke-fix-2026-05-15-epic`
**Worker:** `agora-refactor-worker` (Sonnet)
**Layer:** 0 (Pydantic-Contracts + LLM-Client Schema-Dump)
**Closes:** smoke-report-2026-05-15 Befund #1

## Problem

OpenAI strict structured outputs schlägt mit HTTP 400 fehl:

```
Invalid schema for response_format 'report_plan': In context=(),
'required' is required to be supplied and to be an array including every
key in properties. Missing 'description'.
```

Pydantic v2 generiert `required[]` nur aus Feldern OHNE `default`. `PlanSection.description`, `PlanResponse.summary`, `PlanResponse.sections`, `SectionKeyTakeaway.confidence`, `SectionMetadata.key_takeaways`/`data_gaps` hatten Defaults und fielen aus `required`.

## Fix

1. **`backend/app/services/report_agent/schemas.py`** — alle Defaults entfernt, betroffene Felder zu Pflichtfeldern gemacht.
2. **`backend/app/utils/llm_client.py`** — neuer Helper `_harden_schema_for_openai_strict()`:
   - Tiefe Kopie des Schemas, mutiert Original nicht.
   - Rekursiv über `$defs`, `items`, `properties`, `allOf`/`anyOf`/`oneOf`.
   - Pro `object`-Knoten: `required = list(properties.keys())` + `additionalProperties: false`.
   - Wird unmittelbar vor Bau von `response_format={"type":"json_schema",...}` aufgerufen.

## Tests

Neu: `backend/tests/contracts/test_plan_response_strict.py` (5 Tests):
- `test_plan_section_required_includes_all_properties`
- `test_plan_response_required_includes_all_properties`
- `test_section_metadata_required_includes_all_properties`
- `test_llm_client_hardens_schema_for_strict`
- `test_strict_schema_recursion_handles_nested_objects`

Angepasst: `backend/tests/services/test_report_agent_strict_schema.py::test_plan_section_default_description` → `test_plan_section_description_is_required` (prüft jetzt `ValidationError` bei fehlendem Pflichtfeld).

## Verification-Gate

- `pytest tests/contracts/test_plan_response_strict.py tests/test_llm_client.py tests/services/test_report_agent_strict_schema.py` → 38 passed
- `pytest -x -q` (volle Suite) → 2189 passed, 9 skipped (2 pre-existing Failures unverändert: `test_resume_report_generate_passes_llm_model_from_run_metadata`, `test_neo4j_storage_reconnect_after_fork`; beide auf origin/main bereits rot wegen fehlendem `LLM_API_KEY` im Test-Env)
- `ruff check app/ tests/` → All checks passed
- `mypy app` → Success: no issues found in 167 source files

## Bemerkung / Out-of-Scope

- `_harden_schema_for_openai_strict` wird unbedingt aufgerufen, auch für Nicht-OpenAI-Provider. Helper produziert valides JSON-Schema, daher keine Regression. Provider-spezifische Weiche wäre eigene Optimierungs-Slice — bewusst nicht in 01.
- `enable_thinking`/`max_tokens=16384` für Ollama-Outline-Pfad ist Slice 02.

## Slice-Commit

`9760815` feat(report): Pydantic strict-schema fix für OpenAI structured outputs (Smoke #1)
