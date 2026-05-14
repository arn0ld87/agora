---
description: MAI-03 — ReportV3 bekommt eigenen hypotheses[]-Slot statt Quetschung in data_gaps[]. Layer-0-Touch + Zod-Spiegel.
allowed-tools: Read, Bash, Grep, Glob, Edit, Write
---

# /fix-mai-03-hypotheses-slot — R11 Hypothesen-Slot voll integrieren

## Ziel

`ReportV3.hypotheses: list[Hypothesis]` existiert als eigenes Feld. `manager.py::build_report_v3()` mappt Hypothesen nicht mehr in `data_gaps[]`, sondern in den dedizierten Slot. `sections.py::render_hypotheses_for_section()` rendert sie pro Section als `### Hypothesen ohne Evidence`-Subblock.

## Voraussetzungen

- Worktree: `/Volumes/T7/Projekte/agora-worktrees/mai-03/`.
- Branch: `feat/mai-03-hypotheses-slot`.
- **MAI-02 muss durch sein** — sonst sind die `hypotheses[]` in `evidence_map` leer.
- **Opus-Pre-Review-Pflicht** (Layer-0 Contract-Touch + Schema-Migration).

## Schritt-für-Schritt

### Schritt 1: Pre-Flight

```bash
cd /Volumes/T7/Projekte/agora-worktrees/mai-03
rg -n "class ReportSectionHypothesisModel\|class Hypothesis" backend/app/
rg -n "hypotheses" backend/app/contracts/report_v3.py
rg -n "hypotheses" backend/app/services/report_agent/manager.py
rg -n "render_hypotheses" backend/app/services/report_agent/sections.py
```

### Schritt 2: Pydantic-Model erweitern

`backend/app/contracts/report_v3.py`:

```python
class Hypothesis(BaseModel):
    """Hypothese ohne harte Evidence — separater Slot in ReportV3.

    Unterscheidung zu DataGap:
    - DataGap = strukturelle Lücke (z.B. "keine GenZ-Personas im Sample").
    - Hypothesis = inhaltliche Behauptung ohne Beleg, mit Rationale.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    hypothesis_text: str
    rationale: str
    suggested_evidence: list[str] = Field(default_factory=list)
    origin_section_index: int | None = None
    confidence_score: float = Field(default=0.0, ge=0.0, le=1.0)


class ReportV3(BaseModel):
    # ... bestehende Felder ...
    data_gaps: list[DataGap] = Field(default_factory=list)
    hypotheses: list[Hypothesis] = Field(default_factory=list)  # NEU
    # ...
```

### Schritt 3: Zod-Spiegel im Frontend

`frontend/src/contracts/reportV3Contract.ts`:

```typescript
export const HypothesisSchema = z.object({
  id: z.string(),
  hypothesis_text: z.string(),
  rationale: z.string(),
  suggested_evidence: z.array(z.string()).default([]),
  origin_section_index: z.number().int().nullable().optional(),
  confidence_score: z.number().min(0).max(1).default(0),
}).strict()
export type Hypothesis = z.infer<typeof HypothesisSchema>

export const ReportV3Schema = z.object({
  // ... bestehende Felder ...
  data_gaps: z.array(DataGapSchema).default([]),
  hypotheses: z.array(HypothesisSchema).default([]),  // NEU
  // ...
}).strict()
```

### Schritt 4: build_report_v3 anpassen

`backend/app/services/report_agent/manager.py`:

```python
from ...contracts.report_v3 import Hypothesis as ReportV3Hypothesis

@classmethod
def build_report_v3(cls, report, evidence_map, *, report_mode=DEFAULT_REPORT_MODE) -> ReportV3:
    claims: list[ReportV3Claim] = []
    data_gaps: list[ReportV3DataGap] = []
    hypotheses: list[ReportV3Hypothesis] = []  # NEU

    for section in evidence_map.get("sections") or []:
        # ... Claims-Mapping bleibt unverändert ...

        # data_gaps bleibt für strukturelle Lücken
        for gap in section.get("data_gaps") or []:
            # ... (Logik unverändert)
            data_gaps.append(ReportV3DataGap(...))

        # Hypothesen NICHT MEHR in data_gaps, sondern in eigenen Slot
        for hypothesis in section.get("hypotheses") or []:
            if not isinstance(hypothesis, dict):
                continue
            text = str(hypothesis.get("hypothesis_text") or "").strip()
            if not text:
                continue
            hypotheses.append(ReportV3Hypothesis(
                id=str(hypothesis.get("hypothesis_id") or f"hyp_{len(hypotheses) + 1:02d}"),
                hypothesis_text=text,
                rationale=str(hypothesis.get("rationale") or ""),
                suggested_evidence=[
                    str(item) for item in (hypothesis.get("suggested_evidence") or [])
                    if str(item).strip()
                ],
                origin_section_index=hypothesis.get("origin_section_index"),
                confidence_score=float(hypothesis.get("confidence_score") or 0.0),
            ))

    return ReportV3(
        report_id=report.report_id,
        generated_at=datetime.now(timezone.utc),
        report_mode=report_mode,
        claims=claims,
        data_gaps=data_gaps,
        hypotheses=hypotheses,  # NEU
    )
```

### Schritt 5: Section-Rendering

`backend/app/services/report_agent/sections.py`:

```python
def render_hypotheses_for_section(evidence_section: dict | None) -> str:
    """Rendert Hypothesen einer Section als Markdown-Subblock."""
    if not evidence_section:
        return ""
    hypotheses = evidence_section.get("hypotheses") or []
    if not hypotheses:
        return ""

    lines = ["### Hypothesen ohne Evidence", ""]
    for hyp in hypotheses:
        if not isinstance(hyp, dict):
            continue
        text = hyp.get("hypothesis_text", "").strip()
        rationale = hyp.get("rationale", "").strip()
        suggested = hyp.get("suggested_evidence") or []
        lines.append(f"- **Hypothese:** {text}")
        if rationale:
            lines.append(f"  - *Rationale:* {rationale}")
        if suggested:
            joined = ", ".join(str(s) for s in suggested if str(s).strip())
            lines.append(f"  - *Suggested Evidence:* {joined}")
        lines.append("")
    return "\n".join(lines).rstrip()
```

### Schritt 6: Markdown-Renderer erweitern

`backend/app/services/report_agent/markdown_renderer.py`:

```python
def render_hypotheses_table(hypotheses: list[Hypothesis]) -> str:
    return _table(
        ["ID", "Hypothese", "Rationale", "Suggested Evidence", "Score"],
        [
            [
                h.id,
                h.hypothesis_text,
                h.rationale,
                _list_cell(h.suggested_evidence),
                f"{h.confidence_score:.2f}",
            ]
            for h in hypotheses
        ],
        "Keine Hypothesen im ReportV3-Artefakt.",
    )

# In render_report_v3() den Block hinzufügen:
def render_report_v3(report: ReportV3) -> str:
    # ... bestehende Parts ...
    parts.append("## Hypothesen ohne Evidence")
    parts.append(render_hypotheses_table(report.hypotheses))
    parts.append("## Data Gaps")
    parts.append(render_data_gaps(report.data_gaps))
    # ...
```

### Schritt 7: Schema regenerieren

```bash
cd backend && uv run python -m app.contracts.dump_schemas
# schemas/report-v3.schema.json bekommt hypotheses-Definition.
git diff schemas/report-v3.schema.json
```

### Schritt 8: Tests

`backend/tests/services/test_report_v3_hypotheses.py` (neu):

```python
"""MAI-03: Hypothesen-Slot in ReportV3."""

from datetime import datetime, timezone
from app.contracts.report_v3 import Hypothesis, ReportV3
from app.services.report_agent.manager import ReportManager
from app.models.report import Report


def test_hypotheses_field_default_empty():
    v3 = ReportV3(
        report_id="r1",
        generated_at=datetime.now(timezone.utc),
        report_mode="balanced",
    )
    assert v3.hypotheses == []


def test_build_report_v3_routes_hypotheses_to_dedicated_slot():
    evidence_map = {
        "sections": [
            {
                "section_index": 1,
                "claims": [],
                "data_gaps": [],
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp_01",
                        "hypothesis_text": "Test-Hypothese",
                        "rationale": "Aus Bewertung §13",
                        "suggested_evidence": ["Persona-Interview"],
                    }
                ],
            }
        ]
    }
    report = Report(report_id="r1", simulation_id="s1", graph_id="g1",
                    simulation_requirement="test")
    v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")
    assert len(v3.hypotheses) == 1
    assert v3.hypotheses[0].hypothesis_text == "Test-Hypothese"
    assert v3.data_gaps == []  # nicht mehr dort gelandet
```

## Verifikation

```bash
# 1) Contract-Tests
cd backend && uv run pytest tests/contracts/ -x -v

# 2) Hypothesen-Test
cd backend && uv run pytest tests/services/test_report_v3_hypotheses.py -x -v

# 3) Schema-Dump idempotent
cd backend && uv run python -m app.contracts.dump_schemas
cd .. && git diff --exit-code schemas/

# 4) Voll-Test
cd backend && uv run pytest -x -q

# 5) Frontend Zod-Schema
cd frontend && npm run check
```

## Warum?

Bewertung §13 Punkt 7: „Datenlücken automatisch ausgeben — macht Reports ehrlicher." Heute werden Hypothesen in `data_gaps[]` gequetscht, was den Unterschied zwischen "strukturelle Lücke" und "inhaltliche Behauptung ohne Beleg" verwischt. Eigener Slot trennt das sauber.

## Nächste Schritte

1. Worklog mit Schema-Diff-Erläuterung schreiben.
2. CHANGELOG: `MAI-03 · ReportV3.hypotheses[] als dedizierter Slot, getrennt von data_gaps[].`
3. `/fix-mai-14-contradiction-penalty` (Block B Abschluss).
