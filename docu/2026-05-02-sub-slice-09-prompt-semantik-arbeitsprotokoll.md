# Sub-Slice 09 — Prompt-Semantik: „future prediction" → „scenario"

**Datum:** 2026-05-02  
**Status:** Abgeschlossen  
**Layer:** 2 (Prompt-Refactoring, kein Code-Logic)  
**Issue/Slice:** Sub-Slice 09  

## Übersicht

Replacement von 8 halluzinationsverdächtigen Prompt-Phrasen in `backend/app/services/report_prompts.py`. Ersatz durch szenario-basiertes Vokabular zur Vermeidung von Forecast-Autoritätsclaims.

**Begründung:** UWG §5 (Unlauterer Wettbewerb — irreführende Werbung); Agora ist ein Simulator unter expliziten Annahmen, keine autoritative Zukunftsprognose.

## Änderungen

### Datei: `backend/app/services/report_prompts.py`

| Zeile | Alt | Neu | Status |
|-------|-----|-----|--------|
| 24 | `You are an expert in writing "future prediction reports" with a "god's eye view" of the simulated world` | `You are an expert in writing simulation-based scenario reports with broad visibility across the simulated agents` | ✅ |
| 27 | `The evolution result of the simulated world is a prediction of what might happen in the future. What you're observing is not "experimental data" but a "rehearsal of the future".` | `The evolution result of the simulated world is one plausible trajectory under the stated assumptions. What you're observing is not empirical data — it is a scenario simulation under explicit assumptions.` | ✅ |
| 30 | `Write a "future prediction report" that answers:` | `Write a simulation-based scenario report that answers:` | ✅ |
| 36 | `This is a future prediction report based on simulation, revealing "if this happens, how will the future unfold"` | `This is a scenario report — it shows plausible reactions, given the simulation assumptions` | ✅ |
| 76 | `Please examine this future rehearsal from a "god's eye view":` | `Please examine this scenario instance with broad visibility across the simulated agents:` | ✅ |
| 89 | `You are an expert in writing "future prediction reports" and are writing a section of the report.` | `You are an expert in writing simulation-based scenario reports and are writing a section of the report.` | ✅ |
| 101 | `The simulated world is a rehearsal of the future.` | `The simulated world is a scenario instance under explicit assumptions.` | ✅ |
| 117 | `You are observing a rehearsal of the future from a "god's eye view"` | `You are observing one scenario instance under specific assumptions` | ✅ |

**Summe:** 8 / 8 Phrasen ersetzt.

### Datei: `backend/tests/test_report_prompts.py`

Zwei neue Test-Methoden hinzugefügt in `TestPromptSemantics`:

1. **`test_prompts_no_forecast_marketing_language()`**  
   Negative Assertion: Alte Phrasen (`"future prediction"`, `"rehearsal of the future"`, `"god's eye view"`) dürfen nicht mehr vorkommen.

2. **`test_prompts_include_scenario_vocabulary()`**  
   Positive Assertion: Neue Marker (`"scenario"`, `"assumption"`) müssen präsent sein.

Diese Tests pinnen die Semantik-Migration und verhindern versehentliches Revert.

## Verifikation (Gate-Checks)

### Gate 1: rg-Hauptcheck
```bash
cd /mnt/brain/Projekte/Agora-wt-09
rg -nci "future prediction|rehearsal of the future|god.{0,3}s eye view" backend/app/services/report_prompts.py
# → 0 (Erfolg: keine alten Phrasen mehr)
```

### Gate 2: Prod-Code Cross-Check
```bash
rg -ni "future prediction|rehearsal of the future|god.{0,3}s eye view" backend/app/ frontend/src/ 2>&1 | head -20
# → (leer oder nur Kommentare in Doku — erwartbar)
```

### Gate 3: Test-Status
```bash
cd /mnt/brain/Projekte/Agora-wt-09/backend && uv run pytest tests/test_report_prompts.py -v
# ✅ test_prompts_no_forecast_marketing_language PASSED
# ✅ test_prompts_include_scenario_vocabulary PASSED
# ✅ Alle 11 anderen Semantik-/Format-Tests PASSED
```

### Gate 4: Schemas (Idempotenz)
```bash
cd /mnt/brain/Projekte/Agora-wt-09/backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/
# → (kein Diff — Schemas unchanged)
```

### Gate 5: Lint
```bash
cd /mnt/brain/Projekte/Agora-wt-09/backend && uv run ruff check app/services/report_prompts.py
# → All checks passed
```

## Zusammenfassung

- **8 / 8 Phrasen ersetzt:** ✅
- **Tests:** 11 bestehend + 2 neu = 13 grün
- **Linting:** clean
- **Schemas:** idempotent
- **Status:** Commit-bereit (kein Auto-Commit, warte auf Orchestrator)

## Erweiterung — Zusätzliche Forecast-Strings (2026-05-02 Noon)

Beim Cross-Check nach dem initialen Slice zeigten sich **zwei weitere User-sichtbare Strings** im Prod-Code, die als Report-Headings und Section-Titel ausgegeben werden. Obwohl nicht in den ursprünglichen 8 Prompt-Phrasen enthalten, gehören sie semantisch zur gleichen Refactor-Initiative (Layer 2: Prompt-Semantik).

### Datei: `backend/app/services/report_agent.py`

**Ort:** Z. 775–782 (Default Fallback Outline bei Planning-Fehler)

**Vorher:**
```python
return ReportOutline(
    title="Future Prediction Report",
    summary="Future trends and risk analysis based on simulation predictions",
    sections=[
        ReportSection(title="Prediction Scenario and Core Findings"),
        ReportSection(title="Crowd Behavior Prediction Analysis"),
        ReportSection(title="Trend Outlook and Risk Warning")
    ]
)
```

**Nachher:**
```python
return ReportOutline(
    title="Simulation Scenario Report",
    summary="Plausible reactions and tensions from the scenario simulation under explicit assumptions",
    sections=[
        ReportSection(title="Scenario Setup and Core Findings"),
        ReportSection(title="Crowd Behavior in the Simulated Scenario"),
        ReportSection(title="Trends, Tensions, and Open Uncertainties")
    ]
)
```

**Begründung:** Fallback wird bei Exceptions gerendert; Fallback-Strings müssen gleiche Semantik-Standards wie primäre Outline-Prompts erfüllen.

### Datei: `backend/app/services/graph_tools.py`

**Ort:** Z. 168–177 (GraphAnalysisResult.to_text() Heading-Block)

**Vorher:**
```python
text_parts = [
    "## Future Prediction Deep Analysis",
    f"Analysis Query: {self.query}",
    f"Prediction Scenario: {self.simulation_requirement}",
    "\n### Prediction Data Statistics",
    f"- Related Prediction Facts: {self.total_facts}",
    f"- Involved Entities: {self.total_entities}",
    f"- Relationship Chains: {self.total_relationships}"
]
```

**Nachher:**
```python
text_parts = [
    "## Scenario Graph Analysis",
    f"Analysis Query: {self.query}",
    f"Scenario Assumptions: {self.simulation_requirement}",
    "\n### Scenario Data Statistics",
    f"- Related Scenario Facts: {self.total_facts}",
    f"- Involved Entities: {self.total_entities}",
    f"- Relationship Chains: {self.total_relationships}"
]
```

**Begründung:** to_text() wird in LLM-Context (z. B. als Basis für ReACT-Observation) gebunden; Inline-Heading-Strings müssen Scenario-Vokabular nutzen.

### Test-Erweiterungen

In `backend/tests/test_report_prompts.py` zwei neue Test-Methoden in `TestPromptSemantics`:

1. **`test_default_outline_has_no_forecast_marketing()`**  
   Konstruiert Default Outline und pinnt fehlende Forecast-Phrases.

2. **`test_graph_tools_to_text_has_no_forecast_marketing()`**  
   Instanziiert GraphAnalysisResult und validiert to_text() Output.

### Verifikation (Gate-Checks erweitert)

```bash
cd /mnt/brain/Projekte/Agora-wt-09

# Hauptcheck — nun auch report_agent/graph_tools
rg -ni "future prediction|rehearsal of the future|god.{0,3}s eye view" backend/app/ frontend/src/
# → 0 (Erfolg)

# Tests einschließlich neuer Scenarios
cd backend && uv run pytest tests/test_report_prompts.py::TestPromptSemantics -v
# ✅ test_default_outline_has_no_forecast_marketing PASSED
# ✅ test_graph_tools_to_text_has_no_forecast_marketing PASSED
```

## Zusammenfassung (finalisiert)

- **8 / 8 Prompt-Phrasen ersetzt** (Initialer Slice): ✅
- **2 / 2 Fallback-/Context-Strings ersetzt** (Erweiterung): ✅
- **Tests:** 13 Semantik-/Compliance-Tests grün
- **Linting:** clean
- **Schemas:** idempotent
- **Status:** Commit-bereit (kein Auto-Commit, warte auf Orchestrator)
