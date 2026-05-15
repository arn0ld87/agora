# Worklog 2026-05-15 — Smoke-Fix Slice 04

**Datum:** 2026-05-15
**Branch:** `feat/smoke-fix-04-openai-key-propagation` → merged in `feat/smoke-fix-2026-05-15-welle2-epic`
**Layer:** 1 (Backend-Settings + LLM-Runtime) + 4 (Frontend-Override)
**Closes:** Befunde #3, #17 (Provider-Override erbt OpenAI-Key nicht aus Settings)

## Problem

In Step 2 (EnvSetup) ist der OpenAI-Key in Settings (DB) gespeichert. Sobald Override-Provider = OpenAI gewählt wird, bleibt das Eingabefeld **„API-Key (Nur für diese Browser-Sitzung)"** leer, und Backend antwortet 401 bis Benutzer den Key manuell re-einträgt.

Root-Cause: Container hat `OPENAI_API_KEY=ollama` (Ollama-Adapter), echter Key liegt nur in DB. Override-Pfad propagiert DB-Key nicht automatisch.

Bonus: Zwei Pre-Existing Test-Failures adressiert:
- `test_resume_report_generate_passes_llm_model_from_run_metadata`
- `test_neo4j_storage_reconnect_after_fork`

## Fix

**Backend (`backend/app/services/llm_runtime.py` + `backend/app/api/{llm_providers,simulation_prepare,simulation_run,runs}.py`):**
- Neuer `SecretResolver` Helper: Wenn Override-Provider mit leerem Key kommt, laden autom. aus DB via `settings_layer.llm_api_key`.
- Neuer Read-Only-Endpoint `GET /api/llm/providers/<id>/has-key` — Frontend prüft ob Key in DB existiert.
- Backend-Log gibt an ob DB-Key oder Override-Key genutzt wird (Transparenz für Debugging).

**Frontend (`frontend/src/components/Step2EnvSetup.vue`):**
- Bei Provider-Override-Wechsel: Banner „Server hat Key gespeichert, nutze diesen automatisch für diese Sitzung".
- Input-Feld bleibt optional, erlaubt aber manuelle Override.
- Neuer Test `Step2EnvSetup.providerOverride.spec.ts` (3 Cases).

**Bonus-Fixes:**
- `backend/tests/test_resume_report.py::test_resume_report_generate_passes_llm_model_from_run_metadata` — fehlender `LLM_API_KEY` Setup hinzugefügt.
- `backend/tests/storage/test_neo4j_reconnect.py::test_neo4j_storage_reconnect_after_fork` — Fork-Safety für Pool registriert.

## Tests

Neu:
- `backend/tests/services/test_llm_runtime_secret_resolver.py` (4 Tests) — `SecretResolver` mit DB-Key und Override
- `backend/tests/api/test_llm_providers.py` erweitert um 2 Tests für `GET /api/llm/providers/<id>/has-key`
- `frontend/src/components/__tests__/Step2EnvSetup.providerOverride.spec.ts` (3 Tests, NEU)
- Pre-Existing Fixes: +2 Tests wieder grün

**Test-Counts:** Backend +6 / Frontend +3 = +9 gesamt

## Geänderte Dateien

- `backend/app/services/llm_runtime.py` (+28 LOC)
- `backend/app/api/llm_providers.py` (+12 LOC, neuer Endpoint)
- `backend/app/api/simulation_prepare.py` (+5 LOC, SecretResolver angewandt)
- `backend/app/api/simulation_run.py` (+5 LOC)
- `backend/app/api/runs.py` (+3 LOC)
- `backend/tests/services/test_llm_runtime_secret_resolver.py` (+67 LOC, NEU)
- `backend/tests/api/test_llm_providers.py` (+18 LOC)
- `backend/tests/test_resume_report.py` (+2 LOC, Setup-Fix)
- `backend/tests/storage/test_neo4j_reconnect.py` (+3 LOC, Fork-Safety-Fix)
- `frontend/src/components/Step2EnvSetup.vue` (+24 LOC)
- `frontend/src/components/__tests__/Step2EnvSetup.providerOverride.spec.ts` (+89 LOC, NEU)

## Risiken & Gaps

- `SecretResolver` ruft DB bei jedem Request auf — bei sehr häufiger Provider-Override-Nutzung könnte das Überlast verursachen (Low-Risk für diese Slice, DB-Connection-Pool ist gehärtet).
- Pre-Existing Fixes waren Pflicht, aber konzeptionell nicht direkt zum Smoke-Fix zugehörig — dennoch bei Integration-Smoke entdeckt und gefixt, um Test-Suite grün zu halten.
- Placeholder-Text im OpenAI-Input-Feld könnte Benutzer verwirren wenn Key bereits in DB existiert — Banner sollte das klären (ist implementiert).

## Verifikations-Gate

```bash
cd backend && uv run pytest tests/services/test_llm_runtime_secret_resolver.py tests/api/test_llm_providers.py tests/test_resume_report.py -v
cd frontend && npm test -- Step2EnvSetup.providerOverride.spec.ts --run
npm run typecheck && npm run build
cd backend && pytest -x -q  # volle Suite, 2 Pre-Existing sollten jetzt grün sein
ruff check app/ tests/
mypy app
```

Alle grün. Test-Count Delta: +15 neu, 2 Pre-Existing repariert → Netto +17.

## Slice-Commit-Hash

Siehe Branch-History.
