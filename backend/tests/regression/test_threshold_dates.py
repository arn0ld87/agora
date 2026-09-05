"""Issue #1343 — Datumsangaben dürfen nicht als Mengen-Thresholds landen.

Der AURORA-Referenzlauf produzierte aus „15. Oktober 2026“ den Eintrag
``planungsmeilenstein_15_oktober`` mit ``value=15.0`` und ``unit="October"``.
Diese Tests sichern das Verhalten über die ganze Pipeline: der verstümmelte
Eintrag wird verworfen, ein korrekt gemeldetes Datum überlebt Merge, Dedup,
Provenance-Bindung und beide Renderpfade.
"""

from __future__ import annotations

from typing import Any, Dict

from app.contracts.report_v3 import Threshold
from app.services.report_agent.metadata_merge import merge_section_metadata
from app.services.report_agent.markdown_renderer import render_threshold_table
from app.services.report_agent.threshold_provenance import (
    bind_threshold_provenance,
    canonical_threshold_key,
    dedup_thresholds,
)
from app.services.report_agent.workflow import _build_red_team_excerpt


def _numeric(**overrides: Any) -> Threshold:
    payload: Dict[str, Any] = {
        "id": "th_01",
        "label": "Schulungsquote vor Produktivstart",
        "value": 80.0,
        "unit": "percent",
        "purpose": "target",
        "origin": "model_proposal",
    }
    payload.update(overrides)
    return Threshold.model_validate(payload)


def _date_threshold(threshold_id: str = "production_start") -> Threshold:
    return Threshold.model_validate(
        {
            "id": threshold_id,
            "label": "Produktivstart",
            "value": "15. Oktober 2026",
            "kind": "date",
            "purpose": "target",
            "origin": "document_requirement",
        }
    )


def _record(text: str, evidence_id: str) -> Dict[str, Any]:
    return {"evidence_id": evidence_id, "source_kind": "seed_corpus", "snippet": text}


# --- Merge -------------------------------------------------------------------


def test_the_mangled_artifact_from_the_issue_is_rejected():
    """{value: 15.0, unit: 'October'} ist kein brauchbarer Schwellwert — er
    wird verworfen statt ins Artefakt zu rutschen."""
    sections = [
        {
            "structured_metadata": {
                "thresholds": [
                    {
                        "id": "planungsmeilenstein_15_oktober",
                        "label": "Planungsmeilenstein",
                        "value": 15.0,
                        "unit": "October",
                        "purpose": "target",
                        "origin": "simulation_proposal",
                    },
                ]
            }
        }
    ]

    merged = merge_section_metadata(sections)

    assert merged.thresholds == []
    assert any("thresholds" in entry for entry in merged.rejected)


def test_a_properly_reported_date_survives_the_merge():
    sections = [
        {
            "structured_metadata": {
                "thresholds": [
                    {
                        "id": "production_start",
                        "label": "Produktivstart",
                        "value": "15. Oktober 2026",
                        "purpose": "target",
                        "origin": "document_requirement",
                    },
                ]
            }
        }
    ]

    merged = merge_section_metadata(sections)

    assert len(merged.thresholds) == 1
    assert merged.thresholds[0].kind == "date"
    assert merged.thresholds[0].value == "2026-10-15"
    assert not merged.rejected


# --- Kanonischer Schlüssel / Deduplizierung ----------------------------------


def test_two_mentions_of_the_same_date_deduplicate_to_one():
    left = _date_threshold("production_start")
    right = _date_threshold("meilenstein_klon")

    assert canonical_threshold_key(left) == canonical_threshold_key(right)
    assert dedup_thresholds([left, right]) == [left]


def test_a_date_and_a_quantity_with_the_same_label_keep_separate_keys():
    """Ein Datum und eine Zahl sind nie derselbe Sachverhalt — auch nicht bei
        gleichem Label."""
    assert canonical_threshold_key(_date_threshold()) != canonical_threshold_key(
        _numeric(label="Produktivstart", value=15.0)
    )


# --- Provenance-Bindung ------------------------------------------------------


def test_a_date_threshold_is_left_alone_by_numeric_binding():
    """Die numerische Fact-Suche vergleicht float-Werte — an einem Datum würde
    sie crashen oder Unsinn binden. Daten bleiben, was sie sind."""
    seed = _record("Der Produktivstart ist der 15. Oktober 2026.", "ev_seed_date")

    bound = bind_threshold_provenance([_date_threshold()], [seed])

    assert bound[0].evidence_refs == []
    assert bound[0].evidence_status == "heuristic"


# --- Rendering ---------------------------------------------------------------


def test_the_markdown_table_shows_the_iso_date_without_unit():
    table = render_threshold_table([_date_threshold()])

    assert "2026-10-15" in table
    assert "None" not in table


def test_the_red_team_draft_carries_dates_without_crashing():
    excerpt = _build_red_team_excerpt_fixture()

    assert "production_start" in excerpt
    assert "2026-10-15" in excerpt


def _build_red_team_excerpt_fixture() -> str:
    from datetime import datetime, timezone

    from app.contracts.report_v3 import ReportV3

    evidence_id = "ev_00000000000000000000000000000001"
    report = ReportV3(
        report_id="report_1343",
        generated_at=datetime(2026, 8, 23, tzinfo=timezone.utc),
        # ReportV3 prueft die Belege im Index — derselbe Weg wie im
        # Red-Team-Excerpt-Test.
        evidence_index={
            evidence_id: {
                "evidence_id": evidence_id,
                "producer_key": "threshold-dates-fixture",
                "type": "seed_document",
                "source": "fixture",
                "snippet": "Belegtext.",
                "source_kind": "seed_corpus",
            }
        },
        thresholds=[_date_threshold()],
    )
    return _build_red_team_excerpt(report)
