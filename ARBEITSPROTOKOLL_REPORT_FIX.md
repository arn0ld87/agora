# Arbeitsprotokoll — Report-Generierung Fixes

**Branch:** `fix/report-strict-schema-and-segment-mapper`
**Worktree:** `/private/tmp/agora-report-fix-1`
**Basis-Commit:** `6cf3cf0` (main, Merge PR #444)
**Status:** Slice 1 fertig und lokal verifiziert; PR offen, bis die Issue-Nr. geklärt ist.

---

## Auslöser

Report-Run `report_657534a8573d` schlug mit vier verketteten Fehlern fehl:

| # | Fehler | Quelle |
|---|---|---|
| A | `SectionMetadata` Pydantic-Validierung — LLM lieferte `sectionTitle`/`content` (camelCase + extra) statt `section_title`/`key_takeaways`/`data_gaps` | strict-Schema wurde nicht gesendet |
| B | `Segment` Pydantic-Validierung — LLM lieferte `{segment_analysis: {segments: [...]}}` statt flaches Einzel-Segment | Mapper-Strukturmismatch |
| C | `EvidenceMapModel` — `claim_09` mit Label `'high'` hatte keine Cross-Stakeholder-`agent_quote`-Evidence | Interview-Daten fehlten |
| D | `Simulation environment not running or closed, cannot execute Interview: sim_507108ad09b5` | OASIS-IPC-Socket tot |

Plus Sekundärsymptom: ReACT-Loop erreichte `max_iterations` / `Final Answer:`-Präfix fehlte → Force-Generate, keine echten Tool-Aufrufe.

---

## Ursachen-Analyse (Phase 1, abgeschlossen)

### A) Strict-Schema-Bypass
[`backend/app/utils/llm_client.py:649-661`](backend/app/utils/llm_client.py)
`LLM_DISABLE_JSON_MODE=true` (gesetzt per User-Profil-Instruction für Ollama-Workflows) setzt `response_format = None` **auch wenn `schema=…` übergeben wird**. Damit gibt es keine server-seitige Schema-Erzwingung mehr, das Modell halluziniert beliebige JSON-Strukturen, und Pydantic (`extra="forbid"`) lehnt ab.

### B) Mapper-Strukturmismatch
[`backend/app/services/report_agent/schemas.py:102-114`](backend/app/services/report_agent/schemas.py)
`_SECTION_TITLE_MAP["segment-tabelle"] = Segment` (Einzelobjekt), aber der Pflichtabschnitt enthält eine **Liste** von Segmenten. Gilt analog für `persona-tabelle`, `multiplikator-auswertung`, `top 10 reibungspunkte`, `top 10 vertrauenssignale`, `top 10 änderungen`, `positionierung`, `content-ideen`, `datenlücken`.

### C) High-Label ohne Cross-Stakeholder-Evidence
[`backend/app/contracts/report_contract.py:193-215`](backend/app/contracts/report_contract.py)
`ReportClaimModel.cross_stakeholder_for_high` verlangt ≥ 2 `agent_quote`-Evidenzen mit `supports_claim=True` aus unterschiedlichen `persona_stakeholder_group`. Vergeben wird das Label in [`agent.py:452`](backend/app/services/report_agent/agent.py) (`compute_confidence`) **ohne** Vor-Validierung gegen diese Regel.

### D) Tote OASIS-Simulation
[`backend/app/services/sim/interview_client.py:91-94`](backend/app/services/sim/interview_client.py)
`ipc_client.check_env_alive()` schlägt fehl. [`backend/app/services/graph_tools.py:344-347`](backend/app/services/graph_tools.py) wandelt den Fehler in eine `Warning` um und lässt die Pipeline weiterlaufen — die Sektionen werden "trocken" generiert.

---

## Erledigt

### Slice 1 — Worktree
- [x] `git worktree add /private/tmp/agora-report-fix-1 -b fix/report-strict-schema-and-segment-mapper main`

### Fix 1 — Strict-Schema-Bypass schließen (VOLLSTÄNDIG)
**Datei:** `backend/app/utils/llm_client.py` (chat_json)
**Änderung:** Wenn `schema is not None`, wird `LLM_DISABLE_JSON_MODE` ignoriert und ein Info-Log geschrieben. Schemalose Aufrufe behalten das alte Verhalten.

```python
disable_json_mode_env = os.environ.get('LLM_DISABLE_JSON_MODE', '').lower() in ('1', 'true', 'yes')
disable_json_mode = disable_json_mode_env and schema is None
if disable_json_mode_env and schema is not None:
    logger.info(
        "LLMClient.chat_json: LLM_DISABLE_JSON_MODE ignoriert — schema=%s "
        "erzwingt strict json_schema",
        schema.__name__ if isinstance(schema, type) else "dict",
    )
```

### Fix 2 — Table-Wrapper für Listen-Sektionen (VOLLSTÄNDIG)
**Datei:** `backend/app/services/report_agent/schemas.py`
**Ergebnis:** `_make_table_metadata(item_cls)` erzeugt gecachte `<Item>Table`-Modelle mit strict `items: list[<Item>]`; alle 10 listenförmigen Pflichtabschnitte inkl. `Projektwirkung` nutzen diese Wrapper.

---

## Noch offen

### Slice 1, Restarbeit

- [x] **`schemas.py`** — Helper `_make_table_metadata(item_cls)` eingefügt, `_SECTION_TITLE_MAP` auf Wrapper umgestellt. `Projektwirkung` ist in `ReportV3` `list[ProjectImpact]` und wird deshalb ebenfalls gewrappt.
- [x] **`tests/services/test_report_agent_strict_schema.py:185-217`** — Mapping-Tests prüfen Wrapper-Klasse, `<Item>Table`-Namen und `items: list[<Item>]`; Case-insensitive-Test angepasst.
- [x] **Verification Gate (Task #4)**:
  ```bash
  cd /private/tmp/agora-report-fix-1/backend && \
  UV_CACHE_DIR=/private/tmp/uv-cache-agora-report-fix-1 \
  uv run pytest tests/services/test_report_agent_strict_schema.py \
                tests/test_llm_client.py \
                tests/contracts/test_report_contract.py -v
  ```
- [x] **Zusatz-Check:** `uv run ruff check app/services/report_agent/schemas.py app/utils/llm_client.py tests/services/test_report_agent_strict_schema.py tests/test_llm_client.py`
- [x] **Commit** (atomar, conventional commit):
  - `fix(llm-client): strict json_schema vor LLM_DISABLE_JSON_MODE schützen`
  - `fix(report-agent): Table-Sektionen via list-wrapper extrahieren statt Einzel-DTO`
  - oder ein gemeinsamer Commit mit beidem unter `fix(report): …`
- [ ] **PR** öffnen mit `Closes <issue#>` — blockiert, bis die Issue-Nr. feststeht.

### Slice 2 (Fix 3) — Pre-flight `check_env_alive()`

- [ ] **Worktree:** `git worktree add /private/tmp/agora-report-fix-2 -b fix/report-preflight-sim-alive main`
- [ ] **Datei:** `backend/app/services/report_agent/manager.py` oder `agent.py` (vor `generate_report`)
- [ ] **Logik:** Bevor `report.status = PENDING` gesetzt wird, IPC-Health-Check gegen `simulation_id`. Bei Fehlschlag:
  - `report.status = ReportStatus.FAILED`
  - klare Fehlermeldung in `ReportManager.update_progress(...)` (z. B. `"Simulation sim_… nicht erreichbar — Run abgebrochen, OASIS-Env neu starten."`)
  - kein "trockenes Weiterschreiben"
- [ ] **Test:** `tests/services/test_report_agent_preflight.py` mit gemocktem `check_env_alive() → False`.
- [ ] **Side effect prüfen:** `graph_tools.py:344-347` darf weiter Warning loggen (für ad-hoc-Tool-Aufrufe), aber der Report-Run hat seinen Gate weiter oben.

### Slice 3 (Fix 4) — Confidence-Pre-Validation

- [ ] **Worktree:** `git worktree add /private/tmp/agora-report-fix-3 -b fix/report-confidence-prevalidate main`
- [ ] **Datei:** `backend/app/services/confidence_calculator.py` (oder wo `compute_confidence` lebt) + `agent.py:452`
- [ ] **Logik:** Vor Vergabe von `'high'` prüfen:
  1. Mindestens eine Evidence mit `supports_claim=True` vorhanden?
  2. Mindestens 2 unterschiedliche `persona_stakeholder_group` unter den `supports_claim=True`-Evidenzen?
  3. Keine `source_kind=inferred` unter den Evidenzen?
  Bei Verletzung → `'medium'` zurückgeben. Bei `'verified'` analog: zusätzlich `match_score >= 0.85`.
- [ ] **Test:** Vorhandene Validatoren in `report_contract.py:193-215` als Soll-Spezifikation in `tests/contracts/test_confidence_prevalidation.py` spiegeln. Parametrize über die drei Bedingungen.
- [ ] **Side effect:** Niedrigere Confidence-Labels führen zu mehr "medium-confidence"-Badges im Markdown — gewünscht. `render_claim_to_markdown` in `sections.py:149` rendert das bereits.

### Slice 4 — Sanitäre Maßnahmen (optional, am Ende)

- [ ] **ReACT-Loop** [`workflow.py:155-320`](backend/app/services/report_agent/workflow.py): `min_tool_calls` und `max_iterations` evaluieren. Wenn Pre-flight (Fix 3) ein Hard-Stop ist, kann `force-generate` enger gefasst werden — z. B. nicht „rohen Output als Final akzeptieren", sondern strikt einen finalen `chat_json`-Roundtrip mit dem Section-Schema erzwingen.
- [ ] **`Final Answer:`-Konvention**: bei aktivem strict-Schema (Fix 1) ist die Final-Answer-String-Konvention spröde. Migration in Richtung tool-call-only ReACT oder dedizierte Function-Calling-Variante prüfen.

---

## Verification-Gate-Plan (vor jedem Commit)

```bash
cd /private/tmp/agora-report-fix-1
source backend/.venv/bin/activate 2>/dev/null || true

# 1. Schemas + LLM-Client + Contracts
pytest backend/tests/services/test_report_agent_strict_schema.py \
       backend/tests/test_llm_client.py \
       backend/tests/contracts/test_report_contract.py -v

# 2. Smoke: gesamter report_agent-Modulbaum
pytest backend/tests/services/ -k report_agent -v

# 3. Optional: kompletter Backend-Suite (kann lang dauern)
pytest backend/tests/ --ignore=backend/tests/eval -q
```

Bei Grün: `git add -p` und atomaren Commit, sonst zurück zur Ursachen-Analyse.

---

## Code-Review-Graph Spurensicherung

Aufrufgraph zum Bug-Pfad (aus `.code-review-graph/graph.db`):

```
workflow.py::generate_section_metadata
  → schemas.py::_section_schema_for     (Mapper, Fix 2)
  → llm_client.py::LLMClient.chat_json  (Strict-Schema, Fix 1)
```

```
agent.py::compute_confidence            (Label-Vergabe, Fix 4)
  → report_contract.py::ReportClaimModel.cross_stakeholder_for_high  (Validator)
```

```
graph_tools.py::interview_agents        (Tool, kein Hard-Fail)
  → sim/interview_client.py::interview_agents_batch
  → check_env_alive()                   (Pre-flight, Fix 3)
```

---

## Nächste Aktion

`schemas.py` Helper + Map-Update einbauen, Tests anpassen, pytest laufen lassen, dann commit. Bei Grün: PR öffnen oder Slice 2 starten.
