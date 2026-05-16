# Report Agent Package Split Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Teile `backend/app/services/report_agent.py` in eine Paketstruktur auf, ohne öffentliche Imports (`from app.services.report_agent import …`) oder bestehende Backend-Tests zu brechen.

**Architecture:** Der Split bleibt strikt backwards-kompatibel: `backend/app/services/report_agent/` wird zum Paket, `__init__.py` re-exportiert die bisher öffentliche API, und die Logik wird schrittweise in kleine Module verschoben. Reihenfolge: zuerst Import-/Re-Export-Sicherungsnetz, dann prompts/schemas, dann section/evidence-Helfer, zuletzt Orchestrierung (`ReportAgent`, `ReportManager`).

**Tech Stack:** Python 3.11, Flask, uv, pytest, Pydantic v2, bestehende `app.models.report`, `app.contracts`, `report_prompts.py`, `evidence_binder.py`, `confidence_calculator.py`.

---

## Arbeitskontext

**Worktree:** `/Volumes/T7/Projekte/agora/.worktrees/issue-202-report-agent`

**Ausgangslage verifiziert:**
- `backend/app/services/report_agent.py` = **2400 LOC**
- Tests importieren direkt aus `app.services.report_agent` in mehreren Dateien, u. a.
  - `backend/tests/test_report_export.py`
  - `backend/tests/test_report_manager.py`
  - `backend/tests/test_report_agent_contracts.py`
  - `backend/tests/services/test_report_agent_sampling.py`
  - `backend/tests/services/test_report_agent_provenance.py`
  - `backend/tests/services/test_report_agent_section_dedup.py`
  - `backend/tests/test_report_agent_contradiction_wiring.py`
  - `backend/tests/test_anti_dekoration.py`

**Risiko:** Ein Paket-Split ohne Re-Export-Sicherungsnetz bricht sofort viele Tests.

---

### Task 1: Imports und öffentliche API einfrieren

**Files:**
- Create: `backend/tests/services/test_report_agent_reexports.py`
- Read: `backend/tests/test_report_export.py`
- Read: `backend/tests/test_report_manager.py`
- Read: `backend/tests/test_report_agent_contracts.py`
- Read: `backend/app/services/report_agent.py`

**Step 1: Write the failing test**

```python
from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)


def test_report_agent_public_reexports_exist():
    assert ReportAgent is not None
    assert ReportManager is not None
    assert Report is not None
    assert ReportOutline is not None
    assert ReportSection is not None
    assert ReportStatus is not None
```

**Step 2: Run test to verify current baseline**

Run:
```bash
cd backend && uv run pytest tests/services/test_report_agent_reexports.py -v
```
Expected: PASS on current monolith.

**Step 3: Add a second guard for helper stability**

Ergänze im selben Testfile eine kleine Liste statischer Helper, die von Tests genutzt werden:
```python
def test_report_agent_static_helpers_still_exist():
    assert hasattr(ReportAgent, "_sample_actions_timeseries")
    assert hasattr(ReportAgent, "_build_source_id_anchor")
    assert hasattr(ReportAgent, "_attach_provenance")
    assert hasattr(ReportAgent, "_atomize_claim_chunk")
    assert hasattr(ReportAgent, "_is_claim_candidate")
    assert hasattr(ReportAgent, "_is_atomic_claim")
```

**Step 4: Run tests**

```bash
cd backend && uv run pytest tests/services/test_report_agent_reexports.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/tests/services/test_report_agent_reexports.py
git commit -m "test(report-agent): pin public reexports before package split"
```

---

### Task 2: Package-Skelett anlegen, ohne Verhalten zu ändern

**Files:**
- Create: `backend/app/services/report_agent/__init__.py`
- Create: `backend/app/services/report_agent/agent.py`
- Create: `backend/app/services/report_agent/prompts.py`
- Create: `backend/app/services/report_agent/evidence.py`
- Create: `backend/app/services/report_agent/sections.py`
- Create: `backend/app/services/report_agent/schemas.py`
- Modify: `backend/app/services/report_agent.py`
- Test: `backend/tests/services/test_report_agent_reexports.py`

**Step 1: Create the package directory**

Lege das Paketverzeichnis an, aber verschiebe noch keinen echten Logikblock.

**Step 2: Minimal `__init__.py` schreiben**

```python
from .agent import (
    FORBIDDEN_EVIDENCE_TYPES,
    ReportAgent,
    ReportManager,
    Report,
    ReportOutline,
    ReportSection,
    ReportStatus,
    EvidenceItem,
)

__all__ = [
    "FORBIDDEN_EVIDENCE_TYPES",
    "ReportAgent",
    "ReportManager",
    "Report",
    "ReportOutline",
    "ReportSection",
    "ReportStatus",
    "EvidenceItem",
]
```

**Step 3: Copy monolith into `agent.py` as temporary baseline**

- verschiebe den **gesamten** aktuellen Inhalt von `backend/app/services/report_agent.py` zunächst 1:1 nach `backend/app/services/report_agent/agent.py`
- ersetze `backend/app/services/report_agent.py` durch einen Kompatibilitäts-Wrapper:

```python
from .report_agent import *  # falls Paketimport nicht geht, siehe Step 4
```

**Achtung:** Wegen Namenskollision Datei/Package ist der saubere Zielzustand:
- `backend/app/services/report_agent.py` **entfernen**
- Paket `backend/app/services/report_agent/`

Vorher prüfen, ob Python im Projekt Paket vor Modul korrekt auflöst. Falls nötig, Schrittweise:
1. temporär `backend/app/services/report_agent_pkg/` vermeiden? **Nein** – YAGNI.
2. Direkt sauber umstellen und Tests laufen lassen.

**Step 4: Run re-export test**

```bash
cd backend && uv run pytest tests/services/test_report_agent_reexports.py -v
```
Expected: PASS. Falls Import-Resolver kippt, zuerst diesen Schritt reparieren bevor weitere Logik verschoben wird.

**Step 5: Commit**

```bash
git add backend/app/services/report_agent backend/tests/services/test_report_agent_reexports.py backend/app/services/report_agent.py
git commit -m "refactor(report-agent): convert monolith into package scaffold"
```

---

### Task 3: Prompt- und Schema-Oberfläche auslagern

**Files:**
- Modify: `backend/app/services/report_agent/agent.py`
- Modify: `backend/app/services/report_agent/prompts.py`
- Modify: `backend/app/services/report_agent/schemas.py`
- Test: `backend/tests/test_report_prompts.py`
- Test: `backend/tests/test_report_agent_contracts.py`

**Step 1: Move prompt imports/re-exports into `prompts.py`**

`prompts.py` soll nur die bisher aus `report_prompts.py` geholten Konstanten bündeln:
```python
from ..report_prompts import (
    PLAN_SYSTEM_PROMPT_TEMPLATE,
    PLAN_USER_PROMPT_TEMPLATE,
    SECTION_SYSTEM_PROMPT_TEMPLATE,
    SECTION_USER_PROMPT_TEMPLATE,
    REACT_OBSERVATION_TEMPLATE,
    REACT_INSUFFICIENT_TOOLS_MSG,
    REACT_INSUFFICIENT_TOOLS_MSG_ALT,
    REACT_TOOL_LIMIT_MSG,
    REACT_UNUSED_TOOLS_HINT,
    REACT_FORCE_FINAL_MSG,
    CHAT_SYSTEM_PROMPT_TEMPLATE,
    CHAT_OBSERVATION_SUFFIX,
)
```

**Step 2: Move schema-facing exports into `schemas.py`**

```python
from ...contracts import EvidenceMapModel
from ..evidence_migrations import CURRENT_SCHEMA_VERSION, migrate_v1_to_v2
```

**Step 3: Update `agent.py` imports**

Ersetze direkte Importe aus `..report_prompts`, `..contracts`, `..evidence_migrations` durch lokale Paketimporte (`from .prompts import ...`, `from .schemas import ...`).

**Step 4: Run tests**

```bash
cd backend && uv run pytest tests/test_report_prompts.py tests/test_report_agent_contracts.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/report_agent/agent.py backend/app/services/report_agent/prompts.py backend/app/services/report_agent/schemas.py
git commit -m "refactor(report-agent): split prompts and schema imports"
```

---

### Task 4: Section-/Provenance-Helfer nach `sections.py` extrahieren

**Files:**
- Modify: `backend/app/services/report_agent/agent.py`
- Modify: `backend/app/services/report_agent/sections.py`
- Test: `backend/tests/services/test_report_agent_sampling.py`
- Test: `backend/tests/services/test_report_agent_provenance.py`
- Test: `backend/tests/services/test_report_agent_section_dedup.py`

**Step 1: Write/confirm failing targeted tests if needed**

Wenn die bestehenden Tests schon grün gegen den Monolithen laufen, nutze sie als vorhandenes Sicherheitsnetz. Falls ein spezifischer Helper ungetestet ist, ergänze minimal einen Test.

**Step 2: Move static/pure helpers**

Kandidaten für `sections.py`:
- `_sample_actions_timeseries`
- `_build_source_id_anchor`
- `_attach_provenance`
- `_truncate`
- `_is_claim_candidate`
- `_is_atomic_claim`
- `_atomize_claim_chunk`
- ggf. weitere klar pure Hilfsfunktionen für Section-Dedup/Claim-Bildung

**Step 3: Keep `ReportAgent` API stable**

Wenn Tests `ReportAgent._sample_actions_timeseries(...)` aufrufen, dann in `agent.py` thin wrapper belassen:
```python
from .sections import sample_actions_timeseries as _sample_actions_timeseries_impl

class ReportAgent:
    @staticmethod
    def _sample_actions_timeseries(actions, k=8):
        return _sample_actions_timeseries_impl(actions, k)
```

**Step 4: Run tests**

```bash
cd backend && uv run pytest \
  tests/services/test_report_agent_sampling.py \
  tests/services/test_report_agent_provenance.py \
  tests/services/test_report_agent_section_dedup.py -v
```
Expected: PASS.

**Step 5: Commit**

```bash
git add backend/app/services/report_agent/agent.py backend/app/services/report_agent/sections.py backend/tests/services/test_report_agent_sampling.py backend/tests/services/test_report_agent_provenance.py backend/tests/services/test_report_agent_section_dedup.py
git commit -m "refactor(report-agent): extract section and provenance helpers"
```

---

### Task 5: Evidence-/Claim-Wiring nach `evidence.py` extrahieren

**Files:**
- Modify: `backend/app/services/report_agent/agent.py`
- Modify: `backend/app/services/report_agent/evidence.py`
- Test: `backend/tests/test_anti_dekoration.py`
- Test: `backend/tests/test_report_agent_contradiction_wiring.py`
- Test: `backend/tests/test_report_agent_contracts.py`

**Step 1: Move evidence-specific helpers**

Kandidaten:
- `_init_evidence_map`
- `_record_evidence_item`
- `_try_get_embedder`
- claim/evidence binding helper blocks rund um `_build_claims_for_section`
- Verarbeitung von `FORBIDDEN_EVIDENCE_TYPES`

**Step 2: Preserve method entrypoints on `ReportAgent`**

Wenn Tests oder Call-Sites `ReportAgent._build_claims_for_section(...)` direkt nutzen, lass in `agent.py` einen delegierenden Wrapper.

**Step 3: Run tests**

```bash
cd backend && uv run pytest \
  tests/test_anti_dekoration.py \
  tests/test_report_agent_contradiction_wiring.py \
  tests/test_report_agent_contracts.py -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/app/services/report_agent/agent.py backend/app/services/report_agent/evidence.py
git commit -m "refactor(report-agent): extract evidence and claim wiring"
```

---

### Task 6: `ReportManager` und Top-Level-Orchestrierung bereinigen

**Files:**
- Modify: `backend/app/services/report_agent/agent.py`
- Modify: `backend/app/services/report_agent/__init__.py`
- Test: `backend/tests/test_report_manager.py`
- Test: `backend/tests/test_report_export.py`
- Test: `backend/tests/api/test_simulation_uses_request_model.py`

**Step 1: Keep `ReportManager` in `agent.py` unless a separate `manager.py` becomes necessary**

YAGNI: Das Issue verlangt nicht zwingend `manager.py`. Wenn `agent.py` nach den bisherigen Schritten unter ~600 LOC fällt, belasse `ReportManager` dort. Falls nicht, dann extrahiere zusätzlich `manager.py` und re-exportiere in `__init__.py`.

**Step 2: Verify public imports**

Explizit sichern:
```python
from app.services.report_agent import (
    Report,
    ReportAgent,
    ReportManager,
    ReportOutline,
    ReportSection,
    ReportStatus,
)
```

**Step 3: Run tests**

```bash
cd backend && uv run pytest \
  tests/test_report_manager.py \
  tests/test_report_export.py \
  tests/api/test_simulation_uses_request_model.py \
  tests/services/test_report_agent_reexports.py -v
```
Expected: PASS.

**Step 4: Commit**

```bash
git add backend/app/services/report_agent backend/tests/test_report_manager.py backend/tests/test_report_export.py backend/tests/api/test_simulation_uses_request_model.py backend/tests/services/test_report_agent_reexports.py
git commit -m "refactor(report-agent): preserve public api after package split"
```

---

### Task 7: Vollverifikation und Schema-Drift-Check

**Files:**
- Modify: `docs/2026-05-04-task-46-report-agent-split-arbeitsprotokoll.md`
- Test: `backend/tests/contracts/`
- Test: `backend/tests/services/test_report_agent*.py`

**Step 1: Arbeitsprotokoll schreiben**

Create: `docs/2026-05-04-task-46-report-agent-split-arbeitsprotokoll.md`

Inhalt:
- vorher/nachher LOC pro Modul
- welche Blöcke wohin verschoben wurden
- welche Wrapper aus Backwards-Compat-Gründen geblieben sind
- welche Tests gelaufen sind
- ob `dump_schemas` driftfrei blieb

**Step 2: Run targeted backend suite**

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
  tests/test_anti_dekoration.py -v
```

**Step 3: Run schema dump and diff check**

```bash
cd backend && uv run python -m app.contracts.dump_schemas
cd /Volumes/T7/Projekte/agora/.worktrees/issue-202-report-agent && git diff -- schemas/
```
Expected: leerer Diff für `schemas/`.

**Step 4: Optional broader compile smoke**

```bash
cd backend && uv run python -m compileall app/services/report_agent app/api/runs.py app/api/report.py
```

**Step 5: Final commit**

```bash
git add backend/app/services/report_agent docs/2026-05-04-task-46-report-agent-split-arbeitsprotokoll.md
git commit -m "refactor(report-agent): split monolith into package"
```

---

## Abschlusskriterien für #202

Issue #202 ist erst dann closure-reif, wenn:
- Paket `backend/app/services/report_agent/` existiert
- `from app.services.report_agent import …` weiter funktioniert
- keine Schema-Drift erzeugt wurde
- die genannten Report-Agent-/Contract-Tests grün sind
- Arbeitsprotokoll vorliegt
- keine Einzeldatei im neuen Paket > 600 LOC bleibt (ehrlich nachmessen)

---

Plan complete and saved to `docs/plans/2026-05-04-issue-202-report-agent-split.md`. Two execution options:

**1. Subagent-Driven (this session)** - I dispatch fresh subagent per task, review between tasks, fast iteration

**2. Parallel Session (separate)** - Open new session with executing-plans, batch execution with checkpoints

Which approach?