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


def test_persisted_v3_validates(tmp_path, monkeypatch):
    """P3.1/P3.2: finalisierte Reports schreiben valide v3-Artefakte."""
    from app.services.report_agent import Report, ReportManager, ReportStatus  # noqa: PLC0415

    monkeypatch.setattr(ReportManager, "REPORTS_DIR", str(tmp_path / "reports"))
    report_id = "report_abcdef123456"
    ReportManager.save_evidence_map(report_id, {
        "schema_version": 2,
        "report_id": report_id,
        "simulation_id": "sim_abcdef123456",
        "global_evidence": [],
        "sections": [
            {
                "section_index": 1,
                "section_title": "Executive Summary",
                "section_summary": "Initial framing",
                "claims": [
                    {
                        "claim_id": "claim_01",
                        "claim_text": "Sicherheitsbedenken sind ein sichtbarer Hemmfaktor.",
                        "confidence_label": "medium",
                        "confidence_score": 0.64,
                        "evidence": [
                            {
                                "type": "graph_metric",
                                "source": "simulation_metrics",
                                "snippet": "echo_chamber_index: 0.42",
                                "source_id_anchor": "kg:metric:echo_chamber_index",
                                "supports_claim": True,
                            }
                        ],
                        "audit_trail": [],
                    }
                ],
                "data_gaps": [
                    {
                        "gap_id": "gap_01",
                        "claim_text": "Preisbereitschaft ist im Seed-Korpus nicht belegt.",
                        "gap_reason": "no_evidence_bound",
                        "suggested_fix": "Preisbereitschaft per Interview nacherheben.",
                    }
                ],
            }
        ],
    })
    ReportManager.save_report(
        Report(
            report_id=report_id,
            simulation_id="sim_abcdef123456",
            graph_id="graph_abcdef123456",
            simulation_requirement="Test requirement",
            status=ReportStatus.COMPLETED,
            markdown_content="# Demo",
        )
    )

    report_v3_path = tmp_path / "reports" / report_id / "report-v3.json"
    raw = json.loads(report_v3_path.read_text(encoding="utf-8"))
    restored = ReportV3.model_validate(raw)
    report_v3_markdown = tmp_path / "reports" / report_id / "report-v3.md"

    assert restored.schema_version == 3
    assert restored.report_id == report_id
    assert restored.claims[0].evidence_refs == ["kg:metric:echo_chamber_index"]
    assert restored.data_gaps[0].id == "gap_01"
    assert "Sicherheitsbedenken sind ein sichtbarer Hemmfaktor." in report_v3_markdown.read_text(encoding="utf-8")
    assert "Preisbereitschaft ist im Seed-Korpus nicht belegt." in report_v3_markdown.read_text(encoding="utf-8")


# ---- migrate_v2_to_v3 Unit-Tests ----

def test_migrate_v2_to_v3_minimal():
    """migrate_v2_to_v3 erzeugt ein ReportV3-valides dict aus einem minimalen v2-dict."""
    from app.services.evidence_migrations import migrate_v2_to_v3  # noqa: PLC0415

    v2 = {
        "report_id": "rep-migration-001",
        "sections": [
            {
                "section_index": 1,
                "claims": [
                    {
                        "claim_id": "c01",
                        "claim_text": "Nachhaltige Mobilität ist ein zentrales Thema.",
                        "confidence_label": "medium",
                        "evidence": [
                            {
                                "source_id_anchor": "kg:node:mobility-001",
                                "type": "graph_node",
                            }
                        ],
                    }
                ],
                "data_gaps": [
                    {
                        "gap_id": "g01",
                        "claim_text": "Regionale Unterschiede nicht abgedeckt.",
                        "gap_reason": "insufficient_data",
                        "suggested_fix": "Regionale Studie beauftragen.",
                    }
                ],
            }
        ],
    }
    result = migrate_v2_to_v3(v2)
    report_v3 = ReportV3.model_validate(result)

    assert report_v3.schema_version == 3
    assert report_v3.report_id == "rep-migration-001"
    assert len(report_v3.claims) == 1
    assert report_v3.claims[0].confidence == "medium"
    assert report_v3.claims[0].evidence_refs == ["kg:node:mobility-001"]
    # DataGap aus Claim + DataGap aus Migration-Hinweis (keine Personas)
    gap_ids = {dg.id for dg in report_v3.data_gaps}
    assert "g01" in gap_ids
    assert "dg-migration-personas" in gap_ids


def test_migrate_v2_to_v3_empty_sections_produces_valid_v3():
    """migrate_v2_to_v3 mit leerer Sections-Liste → valide ReportV3 mit leeren Listen."""
    from app.services.evidence_migrations import migrate_v2_to_v3  # noqa: PLC0415

    result = migrate_v2_to_v3({"report_id": "rep-empty", "sections": []})
    report_v3 = ReportV3.model_validate(result)

    assert report_v3.report_id == "rep-empty"
    assert report_v3.claims == []
    assert len(report_v3.data_gaps) == 1  # Nur der Personas-Hinweis
    assert report_v3.data_gaps[0].id == "dg-migration-personas"


def test_migrate_v2_to_v3_simulation_id_in_hint():
    """simulation_id taucht im DataGap-Hinweis auf."""
    from app.services.evidence_migrations import migrate_v2_to_v3  # noqa: PLC0415

    result = migrate_v2_to_v3(
        {"report_id": "rep-x", "sections": []},
        simulation_id="sim_test_123",
    )
    report_v3 = ReportV3.model_validate(result)
    hint_gap = next(
        (dg for dg in report_v3.data_gaps if dg.id == "dg-migration-personas"),
        None,
    )
    assert hint_gap is not None
    assert "sim_test_123" in hint_gap.beschreibung


def test_migrate_v2_to_v3_skips_claims_without_evidence():
    """Claims ohne evidence_refs werden nicht in v3 übernommen."""
    from app.services.evidence_migrations import migrate_v2_to_v3  # noqa: PLC0415

    v2 = {
        "report_id": "rep-no-ev",
        "sections": [
            {
                "section_index": 1,
                "claims": [
                    {
                        "claim_id": "c_no_ev",
                        "claim_text": "Ein Claim ohne Evidence-Belege.",
                        "confidence_label": "high",
                        "evidence": [],
                    }
                ],
            }
        ],
    }
    result = migrate_v2_to_v3(v2)
    report_v3 = ReportV3.model_validate(result)
    assert report_v3.claims == []


def test_write_and_read_report_v3_roundtrip(tmp_path):
    """write_report_v3 + read_report_v3 Roundtrip ist identisch."""
    from app.services.report_agent.storage import write_report_v3, read_report_v3  # noqa: PLC0415

    reports_dir = str(tmp_path / "reports")
    report_id = "rep-rw-001"
    original = ReportV3(
        report_id=report_id,
        generated_at=datetime(2026, 5, 10, 10, 0, 0, tzinfo=timezone.utc),
        claims=[
            Claim(
                id="c1",
                statement="Sicherheitsbedenken hemmen die Adoption sichtbar.",
                evidence_refs=["ev-001"],
                confidence="high",
                aggregation_basis="persona",
            )
        ],
        data_gaps=[
            DataGap(
                id="dg1",
                beschreibung="Preisbereitschaft nicht belegt.",
                severity="medium",
            )
        ],
    )
    written_path = write_report_v3(report_id, original, reports_dir=reports_dir)
    assert written_path.endswith("report-v3.json")

    restored = read_report_v3(report_id, reports_dir=reports_dir)
    assert restored is not None
    assert restored.schema_version == 3
    assert restored.report_id == report_id
    assert restored.claims[0].evidence_refs == ["ev-001"]
    assert restored.data_gaps[0].id == "dg1"


def test_read_report_v3_returns_none_when_missing(tmp_path):
    """read_report_v3 liefert None wenn keine report-v3.json existiert."""
    from app.services.report_agent.storage import read_report_v3  # noqa: PLC0415

    result = read_report_v3("nonexistent", reports_dir=str(tmp_path / "reports"))
    assert result is None


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


# ---- report_mode: Default, Enum-Validation, Roundtrip (P4.1) ----

def test_report_mode_default_is_balanced():
    """ReportV3 ohne explizites report_mode-Feld → Default 'balanced'."""
    r = ReportV3(
        report_id="r-mode-default",
        generated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
    )
    assert r.report_mode == "balanced"


def test_report_mode_strict_accepted():
    """report_mode='strict' ist ein gültiger Literal-Wert."""
    r = ReportV3(
        report_id="r-mode-strict",
        generated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        report_mode="strict",
    )
    assert r.report_mode == "strict"


def test_report_mode_explorative_accepted():
    """report_mode='explorative' ist ein gültiger Literal-Wert."""
    r = ReportV3(
        report_id="r-mode-explorative",
        generated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        report_mode="explorative",
    )
    assert r.report_mode == "explorative"


def test_report_mode_invalid_rejected():
    """Ungültiger report_mode → ValidationError (Literal-Constraint)."""
    with pytest.raises(ValidationError):
        ReportV3.model_validate({
            "report_id": "r-bad-mode",
            "generated_at": "2026-05-11T00:00:00Z",
            "report_mode": "nuclear",
        })


def test_report_mode_roundtrip():
    """report_mode wird via model_dump_json / model_validate_json korrekt erhalten."""
    original = ReportV3(
        report_id="r-mode-rt",
        generated_at=datetime(2026, 5, 11, tzinfo=timezone.utc),
        report_mode="strict",
    )
    json_str = original.model_dump_json()
    restored = ReportV3.model_validate_json(json_str)
    assert restored.report_mode == "strict"


def test_report_mode_re_exported_from_contracts():
    """ReportMode und DEFAULT_REPORT_MODE sind über app.contracts importierbar."""
    from app.contracts import ReportMode, DEFAULT_REPORT_MODE  # noqa: PLC0415
    assert DEFAULT_REPORT_MODE == "balanced"
    # Literal-Werte überprüfbar über __args__ (typing.get_args)
    import typing  # noqa: PLC0415
    args = typing.get_args(ReportMode)
    assert set(args) == {"strict", "balanced", "explorative"}
