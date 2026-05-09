"""
Contract-Tests für report_v3.py — ReportV3-Container mit 11 Pflichtabschnitt-DTOs.

Spec-Quelle: docu/2026-05-09-output-vertrag-bewertung-evidence-quality.md (Abschnitt 6.1/8).
Reihenfolge: M11.8c.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.report_v3 import (
    Claim,
    ChangeRecommendation,
    ContentIdea,
    DataGap,
    FrictionPoint,
    Multiplier,
    Persona,
    PositioningVariant,
    ProjectImpact,
    ReportV3,
    Segment,
    TrustSignal,
)


# ---- Importierbarkeit aller 12 Klassen ----

def test_all_classes_importable():
    """Alle 12 Klassen (ReportV3 + 11 DTOs) sind importierbar."""
    for cls in [
        ReportV3, Persona, Segment, Claim, Multiplier,
        FrictionPoint, TrustSignal, ChangeRecommendation,
        ProjectImpact, PositioningVariant, ContentIdea, DataGap,
    ]:
        assert cls is not None, f"{cls.__name__} nicht importierbar"


# ---- extra="forbid" greift ----

def test_extra_field_rejected_on_persona():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Persona(
            id="p1",
            voice_register="neutral-de",
            alter_range="30–45",
            beruf="Entwicklerin",
            region="Bayern",
            unbekanntes_feld="sollte fehlschlagen",
        )


def test_extra_field_rejected_on_claim():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Claim(
            id="c1",
            statement="Dieser Claim ist ausreichend lang.",
            evidence_refs=["ev-001"],
            confidence="medium",
            aggregation_basis="persona",
            mysterioes="xyz",
        )


def test_extra_field_rejected_on_report_v3():
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReportV3(
            report_id="r1",
            generated_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
            unbekannt="x",
        )


# ---- Pflichtfelder: Claim ----

def test_claim_without_evidence_refs_rejected():
    """Claim ohne evidence_refs → ValidationError (min_length=1)."""
    with pytest.raises(ValidationError):
        Claim(
            id="c1",
            statement="Dieser Claim ist ausreichend lang.",
            evidence_refs=[],  # Leer — verletzt min_length=1
            confidence="medium",
            aggregation_basis="persona",
        )


def test_claim_without_confidence_rejected():
    """Claim ohne confidence → ValidationError (Pflichtfeld)."""
    with pytest.raises(ValidationError):
        Claim.model_validate({
            "id": "c1",
            "statement": "Dieser Claim ist ausreichend lang.",
            "evidence_refs": ["ev-001"],
            "aggregation_basis": "persona",
            # confidence fehlt
        })


def test_claim_invalid_confidence_rejected():
    """Claim mit ungültigem confidence-Wert → ValidationError (Literal)."""
    with pytest.raises(ValidationError):
        Claim(
            id="c1",
            statement="Dieser Claim ist ausreichend lang.",
            evidence_refs=["ev-001"],
            confidence="ultra",  # type: ignore[arg-type]
            aggregation_basis="persona",
        )


# ---- Pflichtfelder: Persona ----

def test_persona_without_voice_register_rejected():
    """Persona ohne voice_register → ValidationError (Pflichtfeld)."""
    with pytest.raises(ValidationError):
        Persona.model_validate({
            "id": "p1",
            "alter_range": "25–35",
            "beruf": "UX-Designer",
            "region": "Berlin",
            # voice_register fehlt
        })


def test_persona_invalid_voice_register_rejected():
    """Persona mit unbekanntem voice_register → ValidationError (Literal)."""
    with pytest.raises(ValidationError):
        Persona(
            id="p1",
            voice_register="englisch-cool",  # type: ignore[arg-type]
            alter_range="25–35",
            beruf="UX-Designer",
            region="Berlin",
        )


# ---- schema_version == 3 (Literal) ----

def test_schema_version_must_be_3():
    """Literal[3] verhindert schema_version=2."""
    with pytest.raises(ValidationError):
        ReportV3.model_validate({
            "schema_version": 2,
            "report_id": "r1",
            "generated_at": "2026-05-09T00:00:00Z",
        })


def test_schema_version_defaults_to_3():
    """Ohne explizite schema_version wird 3 gesetzt."""
    r = ReportV3(
        report_id="r1",
        generated_at=datetime(2026, 5, 9, tzinfo=timezone.utc),
    )
    assert r.schema_version == 3


# ---- Roundtrip: model_dump_json → model_validate_json ----

def test_minimal_report_v3_roundtrip():
    """Minimaler ReportV3 → model_dump_json() → model_validate_json() ist identisch."""
    original = ReportV3(
        report_id="rep-001",
        generated_at=datetime(2026, 5, 9, 12, 0, 0, tzinfo=timezone.utc),
        personas=[
            Persona(
                id="p1",
                voice_register="formal-de",
                alter_range="40–55",
                beruf="Geschäftsführer",
                region="Schweiz",
                needs=["Zuverlässigkeit", "Sicherheit"],
                values=["Qualität"],
                evidence_refs=["ev-001"],
            )
        ],
        claims=[
            Claim(
                id="c1",
                statement="Sicherheitsbedenken sind der primäre Hemmfaktor.",
                evidence_refs=["ev-001"],
                confidence="high",
                persona_ids=["p1"],
                aggregation_basis="persona",
            )
        ],
        data_gaps=[
            DataGap(
                id="dg1",
                beschreibung="Keine Daten zur Preisbereitschaft vorhanden.",
                severity="medium",
                suggested_fixes=["A/B-Test durchführen", "Marktforschung beauftragen"],
            )
        ],
    )

    json_str = original.model_dump_json()
    restored = ReportV3.model_validate_json(json_str)

    assert restored.report_id == original.report_id
    assert restored.schema_version == 3
    assert len(restored.personas) == 1
    assert restored.personas[0].voice_register == "formal-de"
    assert len(restored.claims) == 1
    assert restored.claims[0].evidence_refs == ["ev-001"]
    assert len(restored.data_gaps) == 1


# ---- JSON-Schema-Generierung ----

def test_json_schema_generates_without_error():
    """ReportV3.model_json_schema() lädt fehlerfrei."""
    schema = ReportV3.model_json_schema()
    assert isinstance(schema, dict)
    assert schema.get("title") == "ReportV3"


def test_json_schema_contains_all_11_section_lists():
    """JSON-Schema enthält alle 11 Pflichtabschnitte als list-Properties."""
    schema = ReportV3.model_json_schema()
    props = schema.get("properties", {})
    expected_sections = [
        "personas",
        "segments",
        "claims",
        "multipliers",
        "friction_points",
        "trust_signals",
        "change_recommendations",
        "project_impacts",
        "positioning_variants",
        "content_ideas",
        "data_gaps",
    ]
    for section in expected_sections:
        assert section in props, f"Pflichtabschnitt '{section}' fehlt im JSON-Schema"


def test_json_schema_is_valid_json():
    """JSON-Schema kann serialisiert und deserialisiert werden."""
    schema = ReportV3.model_json_schema()
    roundtrip = json.loads(json.dumps(schema))
    assert roundtrip["title"] == "ReportV3"


# ---- Import via app.contracts (Re-Export-Test) ----

def test_re_export_from_contracts_package():
    """Alle 12 Symbole sind über app.contracts importierbar."""
    from app.contracts import (  # noqa: PLC0415
        Claim as C,
        ChangeRecommendation as CR,
        ContentIdea as CI,
        DataGap as DG,
        FrictionPoint as FP,
        Multiplier as M,
        Persona as Pe,
        PositioningVariant as PV,
        ProjectImpact as PI,
        ReportV3 as RV,
        Segment as Se,
        TrustSignal as TS,
    )
    assert RV is ReportV3
    assert Pe is Persona
    assert Se is Segment
    assert C is Claim
    assert M is Multiplier
    assert FP is FrictionPoint
    assert TS is TrustSignal
    assert CR is ChangeRecommendation
    assert PI is ProjectImpact
    assert PV is PositioningVariant
    assert CI is ContentIdea
    assert DG is DataGap


def test_re_export_from_schemas_module():
    """ReportV3 ist über app.services.report_agent.schemas als Alias verfügbar."""
    from app.services.report_agent.schemas import ReportV3 as RV3_alias  # noqa: PLC0415
    assert RV3_alias is ReportV3
