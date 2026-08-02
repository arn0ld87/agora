"""Contract-Tests für die Pipeline-Degradierung (Issue #1029).

Der Vertrag ist die gemeinsame Sprache dreier Stellen, die bisher still
degradiert sind. Er muss strikt bleiben — ein zusätzliches Feld, das
irgendwo unterwegs anfällt, darf nicht unbemerkt durchrutschen, sonst
entsteht genau wieder die Klasse Problem, gegen die er gebaut wurde.
"""

import pytest
from pydantic import ValidationError

from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
    PipelineDegradationModel,
    PipelineDegradationReport,
)


class TestPipelineDegradationModel:
    def test_minimal_event_gets_defaults(self):
        event = PipelineDegradationModel(
            kind=DegradationKind.EMBEDDING_UNAVAILABLE,
            severity=DegradationSeverity.WARNING,
            detail="Embedding weg",
        )
        assert event.occurrences == 1
        assert event.context == {}
        assert event.occurred_at is not None
        assert event.is_blocking is False

    def test_blocking_flag_follows_severity(self):
        event = PipelineDegradationModel(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.BLOCKING,
            detail="keine Kanten",
        )
        assert event.is_blocking is True

    def test_extra_fields_are_rejected(self):
        with pytest.raises(ValidationError):
            PipelineDegradationModel(
                kind=DegradationKind.EMBEDDING_UNAVAILABLE,
                severity=DegradationSeverity.WARNING,
                detail="x",
                unexpected="smuggled",
            )

    def test_empty_detail_is_rejected(self):
        """Ein Hinweis ohne Begründung ist so wertlos wie kein Hinweis."""
        with pytest.raises(ValidationError):
            PipelineDegradationModel(
                kind=DegradationKind.EMBEDDING_UNAVAILABLE,
                severity=DegradationSeverity.WARNING,
                detail="",
            )

    def test_occurrences_must_be_positive(self):
        with pytest.raises(ValidationError):
            PipelineDegradationModel(
                kind=DegradationKind.EMBEDDING_UNAVAILABLE,
                severity=DegradationSeverity.WARNING,
                detail="x",
                occurrences=0,
            )

    def test_context_accepts_scalars_only(self):
        event = PipelineDegradationModel(
            kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
            severity=DegradationSeverity.BLOCKING,
            detail="unter Schwelle",
            context={"node_count": 3, "ratio": 0.5, "model": "gemini-3.5-flash-lite"},
        )
        assert event.context["node_count"] == 3

        with pytest.raises(ValidationError):
            PipelineDegradationModel(
                kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
                severity=DegradationSeverity.BLOCKING,
                detail="unter Schwelle",
                context={"nested": {"not": "allowed"}},
            )


class TestPipelineDegradationReport:
    def test_empty_report_is_falsy_and_not_blocking(self):
        report = PipelineDegradationReport()
        assert not report
        assert report.has_blocking is False
        assert report.schema_version == 1

    def test_has_blocking_is_true_if_any_event_blocks(self):
        report = PipelineDegradationReport(
            events=[
                PipelineDegradationModel(
                    kind=DegradationKind.EMBEDDING_UNAVAILABLE,
                    severity=DegradationSeverity.WARNING,
                    detail="warn",
                ),
                PipelineDegradationModel(
                    kind=DegradationKind.GRAPH_BELOW_THRESHOLD,
                    severity=DegradationSeverity.BLOCKING,
                    detail="block",
                ),
            ]
        )
        assert bool(report) is True
        assert report.has_blocking is True

    def test_roundtrip_through_json(self):
        report = PipelineDegradationReport(
            events=[
                PipelineDegradationModel(
                    kind=DegradationKind.PERSONA_RULE_BASED_FALLBACK,
                    severity=DegradationSeverity.WARNING,
                    detail="LLM dreimal gescheitert",
                    occurrences=7,
                    context={"attempts": 3},
                )
            ]
        )

        restored = PipelineDegradationReport.model_validate(
            report.model_dump(mode="json")
        )

        assert restored.events[0].kind is DegradationKind.PERSONA_RULE_BASED_FALLBACK
        assert restored.events[0].occurrences == 7
        assert restored.events[0].context == {"attempts": 3}


class TestEnumValues:
    """Die Enum-Werte sind Teil des Vertrags — der Zod-Spiegel hängt daran."""

    def test_kind_values_are_stable(self):
        assert {kind.value for kind in DegradationKind} == {
            "embedding_unavailable",
            "graph_below_threshold",
            "persona_rule_based_fallback",
        }

    def test_severity_values_are_stable(self):
        assert {severity.value for severity in DegradationSeverity} == {
            "warning",
            "blocking",
        }
