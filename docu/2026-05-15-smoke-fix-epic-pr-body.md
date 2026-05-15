## Summary

Erste Welle Bugfixes aus dem manuellen Smoke-Run vom 2026-05-15 (Dev-Stack,
gpt-5.4-nano + kimi-k2.6). Aktuell **nur Slice 01 (P1 #1)** enthalten — die
restlichen Slices (02–07 aus dem Smoke-Plan) bleiben offen und werden in
einem separaten Epic-PR nachgereicht.

- **Slice 01 [Layer 0] — Pydantic strict-schema fix:** `PlanSection` /
  `PlanResponse` / `SectionMetadata` Felder ohne Default → required.
  `llm_client._harden_schema_for_openai_strict()` normiert das Pydantic-Schema
  rekursiv (alle `required = list(properties.keys())`, `additionalProperties:
  false`, inkl. `$defs`, `items`, `allOf`/`anyOf`/`oneOf`) bevor es als
  `response_format={"type":"json_schema",...}` rausgeht. Behebt OpenAI 400
  „Missing 'description' in required" beim Outline-Planning.

- **Smoke-Report:** Vollständige Bug-Liste (P1–P3) inkl. Root-Cause,
  betroffene Dateien und Fix-Vorschläge unter `docu/2026-05-15-smoke-report.md`
  + drei Screenshot-Beweise (`docu/2026-05-15-smoke-step*.png`).

## Closes

- Smoke-Report 2026-05-15 Befund **#1** (OpenAI strict-schema 400).

## Offen (separate PRs, siehe Smoke-Report)

| # | Severity | Slice-Slug | Note |
|---|---|---|---|
| 2 | P1 | `02-ollama-outline` | max_tokens=16384, enable_thinking=False, retry-loop |
| 3 + 17 | P1 | `04-openai-key-propagation` | DB-Key bei Override-Provider serverseitig auflösen |
| 4 | P1 | `03-auth-ticket-refresh` | POST /api/auth/ticket ohne X-Ticket-Header bei valid session |
| 5, 6, 7 | P2 | `05-ui-quickfixes` | Sidebar-Stubs, Persona-Slider min=10, Step-4-Combobox-Sync |
| 8, 9, 10 | P3 | `06-i18n-audit` | Englische Section-Titel, fehlende `dashboard.active.phase.ontology_generate` + `graph.edgeLabels.*` |
| 7 (Doku) | – | `07-doku` | STATUS.md + CHANGELOG-Eintrag |

## Test plan

- [x] `pytest tests/contracts/test_plan_response_strict.py -v` → 5 passed
- [x] `pytest tests/test_llm_client.py` → grün
- [x] `pytest tests/services/test_report_agent_strict_schema.py` → grün
- [x] Volle Suite `pytest -x -q` → 2189 passed, 9 skipped (2 pre-existing Failures unverändert: `test_resume_report_generate_passes_llm_model_from_run_metadata`, `test_neo4j_storage_reconnect_after_fork` — beide bereits auf `origin/main` rot, fehlender `LLM_API_KEY` im Test-Env)
- [x] `ruff check app/ tests/` → All checks passed
- [x] `mypy app` → Success: no issues found in 167 source files
- [x] `python -m app.contracts.dump_schemas` → keine API-Schema-Drift (Layer-0-Änderung ist Report-Agent-intern, nicht API-Contract)

## Risiko

`_harden_schema_for_openai_strict` wird derzeit für **jeden** `chat_json`-Aufruf
mit Pydantic-Schema aktiv, also auch für Ollama/json_object-Fallback-Pfade.
Helper mutiert das Original nicht (deep-copy) und produziert valides
JSON-Schema — keine Regression erwartet, Provider-Weiche wäre eigene
Optimierungs-Slice (out of scope).

🤖 Generated with [Claude Code](https://claude.com/claude-code)
