"""P3.2: Deterministischer Markdown-Renderer fuer ReportV3."""
from __future__ import annotations

from datetime import datetime, timezone

from app.contracts.report_v3 import Claim, DataGap, Persona, ReportV3, Segment
from app.services.report_agent.markdown_renderer import (
    render_data_gaps,
    render_persona_table,
    render_report_v3,
    render_segment_table,
)


def test_report_v3_renderer_outputs_tables_and_data_gaps() -> None:
    report = ReportV3(
        report_id="report_abcdef123456",
        generated_at=datetime(2026, 5, 10, tzinfo=timezone.utc),
        personas=[
            Persona(
                id="P01",
                voice_register="neutral-de",
                alter_range="35-50",
                beruf="Gruenderin",
                region="DACH",
            )
        ],
        segments=[
            Segment(
                id="S01",
                name="KMU",
                beschreibung="Kleine und mittlere Unternehmen",
                persona_ids=["P01"],
            )
        ],
        claims=[
            Claim(
                id="claim_01",
                statement="Sicherheitsbedenken sind ein sichtbarer Hemmfaktor.",
                evidence_refs=["kg:metric:echo_chamber_index"],
                confidence="medium",
                aggregation_basis="persona",
            )
        ],
        data_gaps=[
            DataGap(
                id="gap_01",
                beschreibung="Preisbereitschaft ist nicht belegt.",
                severity="medium",
                suggested_fixes=["Interview nacherheben"],
            )
        ],
    )

    markdown = render_report_v3(report)

    assert "# Agora ReportV3" in markdown
    assert "| P01 | neutral-de | 35-50 | Gruenderin | DACH |" in markdown
    assert "| S01 | KMU | Kleine und mittlere Unternehmen | P01 |" in markdown
    assert "| claim_01 | medium | persona | Sicherheitsbedenken" in markdown
    assert "| gap_01 | medium | Preisbereitschaft ist nicht belegt. | Interview nacherheben |" in markdown


def test_empty_tables_render_explicit_empty_state() -> None:
    assert "Keine Personas" in render_persona_table([])
    assert "Keine Segmente" in render_segment_table([])
    assert "Keine Data Gaps" in render_data_gaps([])
