"""Herkunft regelbasierter Persona-Profile (Issue #1029, Befund B-02).

Nach drei fehlgeschlagenen LLM-Versuchen wird die Persona nicht verworfen,
sondern regelbasiert erzeugt („Kaufmännische Sachbearbeitung
(AdministrativeEmployee)", Themen „Allgemein · Gesellschaft"). Diese
Profile nehmen regulär an der Simulation teil, und ihre Beiträge waren im
Report nicht von echten Personas zu unterscheiden — `OasisAgentProfile`
besaß kein Feld für Herkunft oder Qualität.
"""

from unittest.mock import MagicMock, patch

from app.contracts.persona_contract import PersonaModel
from app.contracts.pipeline_degradation_contract import (
    DegradationKind,
    DegradationSeverity,
)
from app.services.degradation_collector import DegradationCollector
from app.services.oasis_profile_generator import OasisAgentProfile, OasisProfileGenerator


def _generator() -> OasisProfileGenerator:
    return OasisProfileGenerator(api_key="k", base_url="http://localhost:1", model_name="m")


class TestRuleBasedMarking:
    def test_rule_based_payload_is_always_marked(self):
        """Die Kennzeichnung sitzt in der Methode, nicht beim Aufrufer.

        Sonst kann eine Aufrufstelle sie vergessen — und genau davon gibt
        es mehrere.
        """
        payload = _generator()._generate_profile_rule_based(
            "Acme GmbH", "Organization", "Ein Unternehmen.", {}
        )
        assert payload["generation_source"] == "rule_based"

    def test_deliberate_rule_based_carries_no_error(self):
        """``use_llm=False`` ist eine Wahl, kein Ausfall."""
        payload = _generator()._generate_profile_rule_based(
            "Acme GmbH", "Organization", "Ein Unternehmen.", {}
        )
        assert payload.get("generation_error") is None

    def test_failure_path_carries_the_cause(self):
        payload = _generator()._generate_profile_rule_based(
            "Acme GmbH", "Organization", "Ein Unternehmen.", {},
            generation_error="LLM tot",
        )
        assert payload["generation_source"] == "rule_based"
        assert payload["generation_error"] == "LLM tot"


class TestLlmFallbackMarksTheProfile:
    def test_three_failed_attempts_produce_a_marked_profile(self):
        """Der Regressionstest zum Befund: dreimal ungültiges JSON.

        Ohne Kennzeichnung ist das entstehende Profil nach dem
        Erzeugungszeitpunkt nicht mehr von einem echten zu unterscheiden.
        """
        generator = _generator()
        llm = MagicMock(name="LLMClient")
        llm.chat_json.side_effect = ValueError("kein gültiges JSON")

        with patch("app.llm.client.LLMClient", return_value=llm), \
                patch("time.sleep"):
            payload = generator._generate_profile_with_llm(
                entity_name="Acme GmbH",
                entity_type="Organization",
                entity_summary="Ein Unternehmen.",
                entity_attributes={},
                context="",
            )

        assert llm.chat_json.call_count == 3
        assert payload["generation_source"] == "rule_based"
        assert "kein gültiges JSON" in payload["generation_error"]


class TestProfileDefaults:
    def test_profile_defaults_to_llm(self):
        """Bestehende Aufrufer erzeugen unverändert LLM-Profile."""
        profile = OasisAgentProfile(
            user_id=1, user_name="a_1", name="Alice", bio="bio", persona="persona"
        )
        assert profile.generation_source == "llm"
        assert profile.generation_error is None


class TestSerializationCarriesTheOrigin:
    """Die Persona-Galerie liest ``reddit_profiles.json``.

    Ohne die Herkunft in ``to_reddit_format`` bliebe die Kennzeichnung im
    Frontend wirkungslos — die Karte bekäme das Feld nie zu sehen.
    """

    def _profile(self, source: str, error: str | None = None) -> OasisAgentProfile:
        return OasisAgentProfile(
            user_id=1,
            user_name="alice_1",
            name="Alice",
            bio="bio",
            persona="persona",
            generation_source=source,
            generation_error=error,
        )

    def test_reddit_format_carries_a_fallback(self):
        payload = self._profile("rule_based", "LLM tot").to_reddit_format()
        assert payload["generation_source"] == "rule_based"
        assert payload["generation_error"] == "LLM tot"

    def test_twitter_format_carries_a_fallback(self):
        payload = self._profile("rule_based", "LLM tot").to_twitter_format()
        assert payload["generation_source"] == "rule_based"

    def test_llm_profiles_keep_the_previous_shape(self):
        """Nur bei Abweichung vom Default geschrieben.

        Ein normales Profil bleibt byte-identisch zum bisherigen Format —
        OASIS und bestehende Dateien sehen keine Änderung.
        """
        payload = self._profile("llm").to_reddit_format()
        assert "generation_source" not in payload
        assert "generation_error" not in payload

    def test_to_dict_always_carries_the_origin(self):
        payload = self._profile("llm").to_dict()
        assert payload["generation_source"] == "llm"
        assert payload["generation_error"] is None


class TestPersonaContract:
    def test_contract_accepts_the_new_fields(self):
        persona = PersonaModel(
            user_id=1,
            user_name="alice_1",
            name="Alice",
            bio="Eine Person mit Interessen.",
            persona="x" * 300,
            generation_source="rule_based",
            generation_error="LLM-Generierung fehlgeschlagen",
        )
        assert persona.generation_source == "rule_based"

    def test_personas_from_before_the_change_still_validate(self):
        """Additiv mit Default — persistierte Personas ohne das Feld bleiben gültig."""
        persona = PersonaModel(
            user_id=1,
            user_name="alice_1",
            name="Alice",
            bio="Eine Person mit Interessen.",
            persona="x" * 300,
        )
        assert persona.generation_source == "llm"

    def test_unknown_source_is_rejected(self):
        import pytest
        from pydantic import ValidationError

        with pytest.raises(ValidationError):
            PersonaModel(
                user_id=1,
                user_name="alice_1",
                name="Alice",
                bio="Eine Person mit Interessen.",
                persona="x" * 300,
                generation_source="handgeschnitzt",
            )


class TestDegradationReporting:
    def _profiles(self, failed: int, total: int) -> list[OasisAgentProfile]:
        profiles = []
        for index in range(total):
            profile = OasisAgentProfile(
                user_id=index + 1,
                user_name=f"a_{index}",
                name=f"Agent {index}",
                bio="bio",
                persona="persona",
            )
            if index < failed:
                profile.generation_source = "rule_based"
                profile.generation_error = "LLM tot"
            profiles.append(profile)
        return profiles

    def test_reports_once_with_the_count(self):
        """Ein Befund für die ganze Runde, nicht einer pro Persona."""
        collector = DegradationCollector()
        generator = _generator()

        generator._report_persona_degradation(self._profiles(4, 10), collector)

        events = collector.report().events
        assert len(events) == 1
        assert events[0].kind is DegradationKind.PERSONA_RULE_BASED_FALLBACK
        assert events[0].severity is DegradationSeverity.WARNING
        assert events[0].context["fallback_personas"] == 4
        assert events[0].context["total_personas"] == 10

    def test_clean_run_reports_nothing(self):
        collector = DegradationCollector()
        _generator()._report_persona_degradation(self._profiles(0, 10), collector)
        assert collector.report().events == []

    def test_deliberate_rule_based_is_not_a_degradation(self):
        """``use_llm=False`` erzeugt Platzhalter ohne Ausfall — kein Befund.

        Die Meldung hängt deshalb an ``generation_error``, nicht an
        ``generation_source``.
        """
        collector = DegradationCollector()
        profiles = self._profiles(0, 3)
        for profile in profiles:
            profile.generation_source = "rule_based"

        _generator()._report_persona_degradation(profiles, collector)

        assert collector.report().events == []
