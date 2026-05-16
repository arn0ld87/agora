"""MAI-03: Hypothesen-Slot in ReportV3."""
from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.report_v3 import Hypothesis, ReportV3
from app.models.report import Report, ReportStatus
from app.services.report_agent.manager import ReportManager
from app.services.report_agent.markdown_renderer import render_report_v3


def test_hypotheses_field_default_empty() -> None:
    report = ReportV3(
        report_id="r1",
        generated_at=datetime.now(timezone.utc),
        report_mode="balanced",
    )

    assert report.hypotheses == []


def test_build_report_v3_routes_hypotheses_to_dedicated_slot() -> None:
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
                        "rationale": "Aus Bewertung Abschnitt 13",
                        "suggested_evidence": ["Persona-Interview"],
                        "confidence_score": 0.42,
                    }
                ],
            }
        ]
    }
    report = Report(
        report_id="r1",
        simulation_id="s1",
        graph_id="g1",
        simulation_requirement="test",
        status=ReportStatus.COMPLETED,
    )

    v3 = ReportManager.build_report_v3(report, evidence_map, report_mode="balanced")

    assert len(v3.hypotheses) == 1
    # Slice 3 (Issue #495): stabile Re-ID → H{section_idx}_{slot:02d}
    assert v3.hypotheses[0].id == "H1_01"
    assert v3.hypotheses[0].hypothesis_text == "Test-Hypothese"
    assert v3.hypotheses[0].rationale == "Aus Bewertung Abschnitt 13"
    assert v3.hypotheses[0].suggested_evidence == ["Persona-Interview"]
    assert v3.hypotheses[0].origin_section_index == 1
    assert v3.hypotheses[0].confidence_score == 0.42
    assert v3.data_gaps == []


def test_render_report_v3_outputs_hypotheses_separately_from_data_gaps() -> None:
    report = ReportV3(
        report_id="r1",
        generated_at=datetime(2026, 5, 14, tzinfo=timezone.utc),
        hypotheses=[
            Hypothesis(
                id="hyp_01",
                hypothesis_text="Test-Hypothese",
                rationale="Aus Bewertung Abschnitt 13",
                suggested_evidence=["Persona-Interview"],
                confidence_score=0.42,
            )
        ],
    )

    markdown = render_report_v3(report)

    assert "## Hypothesen ohne Evidence" in markdown
    assert "| hyp_01 | Test-Hypothese | Aus Bewertung Abschnitt 13 | Persona-Interview | 0.42 |" in markdown
    assert "## Data Gaps" in markdown
    assert "Hypothesen ohne Evidence / Data Gaps" not in markdown
