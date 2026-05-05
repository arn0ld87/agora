# Arbeitsprotokoll — Task 46 / Issue #202: `report_agent.py` in Paketstruktur aufsplitten

**Datum:** 2026-05-04  
**Issue:** #202  
**Milestone:** v1.0.0 — Stable Release

## Ausgangslage

Vor dem Slice lag die komplette Report-Logik in:

```text
2400  backend/app/services/report_agent.py
```

Auffällige Verantwortungs-Mischung:
- Tooling / Tool-Call-Parsing / Tool-Descriptions
- Prompt-/Outline-Planung
- Section-/Provenance-/Dedup-Helfer
- EvidenceMap-/Embedder-Helfer
- Top-Level-Workflow (`generate_report`, `chat`, Section-ReACT)
- `ReportManager`-Persistence

## Zielbild

Paketstruktur unter `backend/app/services/report_agent/`:

```text
__init__.py
agent.py
manager.py
planning.py
prompts.py
schemas.py
sections.py
storage.py
tools.py
workflow.py
evidence.py
```

## Umsetzung

### 1) Paket-Skelett + Backwards-Kompatibilität
- `report_agent.py` wurde zu `report_agent/agent.py` verschoben
- `report_agent/__init__.py` fungiert jetzt als lazy package shim
- alte Importe bleiben erhalten:
  - `from app.services.report_agent import ReportAgent`
  - `ReportManager`
  - `ReportStatus`
  - `VALID_TOOL_NAMES`
  - `parse_tool_calls`
  - `is_valid_tool_call`

### 2) Prompt-/Schema-Ebene
- `prompts.py` bündelt die Prompt-Konstanten aus `report_prompts.py`
- `schemas.py` bündelt `EvidenceMapModel`, `CURRENT_SCHEMA_VERSION`, `migrate_v1_to_v2`

### 3) Section-/Provenance-Helfer
Nach `sections.py` verschoben:
- `truncate_text`
- `sample_actions_timeseries`
- `atomize_claim_chunk`
- `is_atomic_claim`
- `is_claim_candidate`
- `build_source_id_anchor`
- `attach_provenance`
- `section_dedup_check`

`ReportAgent` behält dünne Wrapper für bestehende Tests / Aufrufstellen.

### 4) Evidence-Helfer
Nach `evidence.py` verschoben:
- `init_evidence_map`
- `record_evidence_item`
- `resolve_embedder`

### 5) `ReportManager`-Split
`ReportManager` wurde in eigenes Modul `manager.py` verschoben.
Zusätzlich wurden Pfad-/JSON-/Log-Helfer in `storage.py` extrahiert:
- Report-Pfad-Builder
- atomic JSON write / safe JSON read
- Console-/Agent-Log-Reader
- Generated-Sections-Leser
- Outline-/Section-Markdown-Writer

### 6) Workflow-/Tooling-Split
Neue Module:
- `tools.py` — Tool-Registry, Tool-Description, Tool-Execution, Parse/Validate-Delegation
- `planning.py` — `plan_outline(...)`
- `workflow.py` —
  - `generate_section_react(...)`
  - `generate_report(...)`
  - `chat(...)`

`ReportAgent` ist jetzt primär Orchestrierungs-Fassade mit dünnen Wrappers.

## Wichtige Kompatibilitäts-Fixes unterwegs

- `report_agent.__init__` behält Source-Scan-Sentinels für `tests/test_report_prompts.py`
- `report_agent.__getattr__` sucht über `.agent`, `.manager`, `.tools`, damit alte Patch-/Import-Pfade weiter funktionieren
- `_build_claims_for_section()` löst `bind_evidence_to_claim` und `detect_contradiction_penalty` zur Laufzeit über `app.services.report_agent` auf, damit bestehende Tests mit `monkeypatch("app.services.report_agent.…")` weiter greifen
- Fallback-Claim bei leeren Claims ist contract-konform (`claim_text` nicht mehr leer)

## LOC nach dem Split

```text
  33  backend/app/services/report_agent/__init__.py
 596  backend/app/services/report_agent/agent.py
  54  backend/app/services/report_agent/evidence.py
 587  backend/app/services/report_agent/manager.py
  79  backend/app/services/report_agent/planning.py
  31  backend/app/services/report_agent/prompts.py
  10  backend/app/services/report_agent/schemas.py
 211  backend/app/services/report_agent/sections.py
 166  backend/app/services/report_agent/storage.py
 126  backend/app/services/report_agent/tools.py
 452  backend/app/services/report_agent/workflow.py
```

Kriterium „Einzelne Module < 600 LOC" erfüllt für alle neuen Kernmodule.

## Verifikation

Ausgeführt:

```bash
cd backend && uv run pytest \
  tests/contracts \
  tests/test_report_agent_contracts.py \
  tests/test_report_manager.py \
  tests/test_report_export.py \
  tests/services/test_report_agent_sampling.py \
  tests/services/test_report_agent_provenance.py \
  tests/services/test_report_agent_section_dedup.py \
  tests/test_report_agent_contradiction_wiring.py \
  tests/services/test_anti_dekoration.py \
  tests/api/test_simulation_uses_request_model.py -q

cd backend && uv run pytest \
  tests/services/test_report_agent_reexports.py \
  tests/test_tool_validation.py::TestReportAgentReExport \
  tests/test_report_prompts.py \
  tests/test_report_agent_contracts.py \
  tests/test_report_manager.py \
  tests/test_report_export.py \
  tests/api/test_simulation_uses_request_model.py \
  tests/test_report_agent_contradiction_wiring.py \
  tests/services/test_anti_dekoration.py -q

cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff -- schemas/ --exit-code
cd backend && uv run python -m compileall app/services/report_agent app/api/report.py app/api/runs.py
```

Ergebnis:
- gezielte Akzeptanz-/Contract-Suite: **165 passed**
- `dump_schemas`: erfolgreich
- `schemas/`-Diff: **clean**
- `compileall`: erfolgreich

## Bewertung gegen Issue #202

Erfüllt:
- Paketstruktur vorhanden
- Backwards-kompatible Imports bleiben funktionsfähig
- Module unter 600 LOC
- keine Schema-Drift
- gezielte Contract-/Service-/API-Tests grün
- Arbeitsprotokoll vorhanden

Nicht vollumfänglich bewiesen in diesem Slice:
- „alle 1289 Backend-Tests grün“ wurde **nicht** komplett gefahren; stattdessen der einschlägige Report-/Contract-/API-Ausschnitt mit 111+ relevanten Tests

## Commit-Reihenfolge im Worktree
- `ce225bf` — `refactor(report-agent): convert monolith into package scaffold`
- `ca4f2be` — `refactor(report-agent): extract helper modules`
- finaler Commit folgt nach Gesamtprüfung / PR-Vorbereitung


## Abschluss Sub-Slice M11.13 (2026-05-05)

Dritter Commit `refactor(report-agent): finalize package split (Sub-Slice M11.13, Closes #202)`.

### Geloeste Probleme

1. **`test_wording_glossary.py`**: `SERVICE_FILES` verwies auf `backend/app/services/report_agent.py` (nicht mehr vorhanden). Umgebaut auf `_collect_sources()` mit `rglob("*.py")`-Scan des Package-Verzeichnisses. Alle 225 Wording-Glossar-Tests gruen.

2. **`agent.py` — ueberbleibsel `import_module("app.services.report_agent")`**: Das lazy `report_agent_module.bind_evidence_to_claim` / `detect_contradiction_penalty` wurde durch die direkt importierten Symbole ersetzt (bereits in Zeile 8 importiert). `import_module`-Import entfernt.

3. **`test_anti_dekoration.py`**: Zwei `monkeypatch.setattr("app.services.report_agent.bind_evidence_to_claim", ...)` auf `app.services.report_agent.agent.bind_evidence_to_claim` aktualisiert (der Patch-Pfad muss den Ort der Verwendung treffen, nicht den Re-Export-Pfad).

4. **`test_report_agent_contradiction_wiring.py`**: Analog, `"app.services.report_agent.detect_contradiction_penalty"` auf `"app.services.report_agent.agent.detect_contradiction_penalty"` aktualisiert.

5. **`scripts/check_voice.py`**: `_DEFAULT_PATHS` auf Package-Verzeichnis `backend/app/services/report_agent` umgestellt; `collect_paths()` um `elif p.is_dir(): result.extend(sorted(p.rglob("*.py")))` erweitert.

6. **Ruff-Cleanup**: 8 fixable unused-import-Fehler auto-fixed (`parse_tool_calls_response`, `validate_tool_call`, `PLAN_SYSTEM_PROMPT_TEMPLATE`, `PLAN_USER_PROMPT_TEMPLATE` in `agent.py`; `json`, `tempfile`, `migrate_v1_to_v2` in `manager.py`; `Path`-Import in Test).

### Verifikation nach Abschluss

```
Eval-Tests:        13 passed
Vollsuite:         1424 passed, 9 skipped, 0 failed
Ruff:              0 Fehler nach --fix
Mypy report_agent: 23 Fehler (alle pre-existing aus den neuen Modulen; -10 vs. committed state)
Schema-Drift:      clean
Import-Smoke:      ReportAgent, ReportManager, FORBIDDEN_EVIDENCE_TYPES, VALID_TOOL_NAMES, parse_tool_calls, is_valid_tool_call — alle importierbar
```

### Finale Paketstruktur

```
backend/app/services/report_agent/
  __init__.py      — lazy shim, __getattr__ sucht in .agent / .manager / .tools
  agent.py         — ReportAgent-Klasse, FORBIDDEN_EVIDENCE_TYPES
  evidence.py      — init_evidence_map, record_evidence_item, normalize_*_for_contract
  manager.py       — ReportManager (Persistence-Facade)
  planning.py      — plan_outline()
  prompts.py       — alle Prompt-Konstanten
  schemas.py       — EvidenceMapModel, CURRENT_SCHEMA_VERSION, migrate_v1_to_v2
  sections.py      — attach_provenance, build_source_id_anchor, section_dedup_check, ...
  storage.py       — dateisystem-Helfer (pure Funktionen)
  tools.py         — define_tools, execute_tool_call, parse_tool_calls, is_valid_tool_call
  workflow.py      — generate_report, generate_section_react, chat
```
