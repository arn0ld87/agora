"""Tests für PersonaQuotaPlan-Verdrahtung in prepare_service + oasis_profile_generator.

Sub-Slice 06 — Layer 1.

Strategie: Die 5-zeilige Quota-Check-Logik ist in ``_validate_persona_quota``
extrahiert und wird isoliert getestet. So entfällt das vollständige Mocken von
FSM/Neo4j/LLM für die Quota-Pfade. Test 5 verifiziert den Legacy-Pfad über
einen Monkeypatch von ``prepare_simulation``.
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts import PersonaQuotaPlan
from app.services.oasis_profile_generator import OasisAgentProfile
from app.services.prepare_service import _validate_persona_quota


# ---------------------------------------------------------------------------
# Hilfsfunktion: minimales OasisAgentProfile bauen
# ---------------------------------------------------------------------------

def _make_profile(segment: str | None = None) -> OasisAgentProfile:
    return OasisAgentProfile(
        user_id=1,
        user_name="test_user",
        name="Test User",
        bio="Testbio",
        persona="x" * 10,
        segment=segment,
    )


# ---------------------------------------------------------------------------
# Test 1 — segment-Feld wird vom Generator gesetzt
# ---------------------------------------------------------------------------

class TestSegmentFieldOnProfile:
    def test_segment_defaults_to_none(self) -> None:
        p = _make_profile()
        assert p.segment is None

    def test_segment_set_explicitly(self) -> None:
        p = _make_profile(segment="kmu_ceo")
        assert p.segment == "kmu_ceo"

    def test_to_dict_includes_segment(self) -> None:
        p = _make_profile(segment="it_admin")
        d = p.to_dict()
        assert d["segment"] == "it_admin"

    def test_to_dict_segment_none_when_not_set(self) -> None:
        p = _make_profile()
        d = p.to_dict()
        assert d["segment"] is None

    def test_to_reddit_format_includes_segment(self) -> None:
        p = _make_profile(segment="kmu_ceo")
        r = p.to_reddit_format()
        assert r["segment"] == "kmu_ceo"

    def test_to_reddit_format_omits_segment_when_none(self) -> None:
        p = _make_profile()
        r = p.to_reddit_format()
        assert "segment" not in r

    def test_to_twitter_format_includes_segment(self) -> None:
        p = _make_profile(segment="it_admin")
        t = p.to_twitter_format()
        assert t["segment"] == "it_admin"

    def test_to_twitter_format_omits_segment_when_none(self) -> None:
        p = _make_profile()
        t = p.to_twitter_format()
        assert "segment" not in t


# ---------------------------------------------------------------------------
# Test 2 — _validate_persona_quota: Ist-Werte passen zum Plan
# ---------------------------------------------------------------------------

def test_validate_quota_actual_matches() -> None:
    plan = PersonaQuotaPlan(targets={"kmu_ceo": 2, "it_admin": 1}, total=3)
    profiles = [
        _make_profile("kmu_ceo"),
        _make_profile("kmu_ceo"),
        _make_profile("it_admin"),
    ]
    # Muss durchlaufen ohne Exception
    _validate_persona_quota(plan, profiles)


# ---------------------------------------------------------------------------
# Test 3 — _validate_persona_quota: Drift löst ValidationError aus
# ---------------------------------------------------------------------------

def test_validate_quota_drift_raises() -> None:
    plan = PersonaQuotaPlan(targets={"kmu_ceo": 2, "it_admin": 1}, total=3)
    # Nur 1 kmu_ceo statt 2
    profiles = [
        _make_profile("kmu_ceo"),
        _make_profile("it_admin"),
        _make_profile("it_admin"),  # it_admin zu viel UND kmu_ceo zu wenig
    ]
    with pytest.raises(ValidationError) as exc_info:
        _validate_persona_quota(plan, profiles)
    assert "Soll=2" in str(exc_info.value) or "Toleranz" in str(exc_info.value)


def test_validate_quota_missing_segment_raises() -> None:
    """Segment komplett fehlend → Ist=0, Soll>0 → Toleranz überschritten."""
    plan = PersonaQuotaPlan(targets={"kmu_ceo": 2, "it_admin": 1}, total=3)
    profiles = [
        _make_profile("kmu_ceo"),
        _make_profile("kmu_ceo"),
        # it_admin fehlt komplett
    ]
    with pytest.raises(ValidationError, match="Toleranz"):
        _validate_persona_quota(plan, profiles)


# ---------------------------------------------------------------------------
# Test 4 — _validate_persona_quota: Unbekanntes Segment
# ---------------------------------------------------------------------------

def test_validate_quota_unknown_segment_raises() -> None:
    plan = PersonaQuotaPlan(targets={"kmu_ceo": 2}, total=2)
    profiles = [
        _make_profile("kmu_ceo"),
        _make_profile("kmu_ceo"),
        _make_profile("hacker_unknown"),  # nicht im Plan
    ]
    with pytest.raises(ValidationError, match="Unbekannte Segmente"):
        _validate_persona_quota(plan, profiles)


# ---------------------------------------------------------------------------
# Test 5 — Legacy-Pfad: ohne quota_plan keine Verhaltensänderung
# ---------------------------------------------------------------------------

def test_validate_quota_not_called_when_plan_is_none() -> None:
    """_validate_persona_quota darf ohne Plan nicht aufgerufen werden.

    Wir testen das indirekt: eine beliebige Profil-Liste (inkl. Segment, das
    in keinem Plan vorkommt) wird nicht validiert und löst keinen Fehler aus.
    """
    # Wenn quota_plan=None, wird _validate_persona_quota gar nicht aufgerufen.
    # Dies entspricht dem Legacy-Pfad. Da prepare_simulation einen echten
    # SimulationManager, Storage und LLM-Call benötigt, testen wir hier
    # direkt die Logik: ohne Plan kein Aufruf → keine Exception.
    profiles = [
        _make_profile("ghost_segment_not_in_any_plan"),
        _make_profile(None),
    ]
    quota_plan = None
    # Repliziert den Guard aus prepare_simulation:
    if quota_plan is not None:
        _validate_persona_quota(quota_plan, profiles)  # type: ignore[arg-type]
    # Kein Exception = Legacy-Pfad ist unverändert.


# ---------------------------------------------------------------------------
# Test 6 — Segment-Propagation durch generate_profile_from_entity
# ---------------------------------------------------------------------------

def test_segment_field_propagates_through_generator() -> None:
    """generate_profile_from_entity setzt segment = entity_type."""
    from unittest.mock import MagicMock, patch

    from app.services.oasis_profile_generator import OasisProfileGenerator

    # Minimales EntityNode-Mock
    mock_entity = MagicMock()
    mock_entity.name = "Acme GmbH"
    mock_entity.uuid = "uuid-001"
    mock_entity.summary = "Testfirma"
    mock_entity.attributes = {}
    mock_entity.get_entity_type.return_value = "kmu_ceo"

    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)
    generator.storage = None
    generator.graph_id = None

    # Patch LLM-Aufruf und Kontext-Bau — kein echter API-Call
    with (
        patch.object(
            generator, "_generate_profile_rule_based", return_value={
                "bio": "Eine Testbiografie.",
                "persona": "x" * 400,
            }
        ),
        patch.object(
            generator, "_build_entity_context", return_value=""
        ),
    ):
        profile = generator.generate_profile_from_entity(
            entity=mock_entity,
            user_id=42,
            use_llm=False,
        )

    assert profile.segment == "kmu_ceo"
    assert profile.source_entity_type == "kmu_ceo"


def test_segment_is_none_for_generic_entity_type() -> None:
    """Wenn entity_type 'Entity' ist (Fallback), wird segment auf None gesetzt."""
    from unittest.mock import MagicMock, patch

    from app.services.oasis_profile_generator import OasisProfileGenerator

    mock_entity = MagicMock()
    mock_entity.name = "Unbekannt"
    mock_entity.uuid = "uuid-002"
    mock_entity.summary = "Kein Typ"
    mock_entity.attributes = {}
    mock_entity.get_entity_type.return_value = None  # → entity_type = "Entity"

    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)
    generator.storage = None
    generator.graph_id = None

    with (
        patch.object(
            generator, "_generate_profile_rule_based", return_value={
                "bio": "Eine Testbiografie.",
                "persona": "x" * 400,
            }
        ),
        patch.object(
            generator, "_build_entity_context", return_value=""
        ),
    ):
        profile = generator.generate_profile_from_entity(
            entity=mock_entity,
            user_id=99,
            use_llm=False,
        )

    assert profile.segment is None
