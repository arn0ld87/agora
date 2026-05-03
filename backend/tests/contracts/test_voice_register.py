"""Voice-Lint CI-Check (Sub-Slice 11, Layer 2).

Pinnt DACH-Voice-Constraints:
- Nur 4 erlaubte voice_register-Werte
- Default ist neutral-de
- None erlaubt für Legacy-Daten
- _rule_based_voice_register ist deterministisch und liefert nur erlaubte Werte
"""

import pytest
from pydantic import ValidationError

from app.contracts.persona_contract import PersonaModel
from app.services.oasis_profile_generator import OasisProfileGenerator

VALID_VOICE_REGISTERS = {"formal-de", "neutral-de", "technical-de", "skeptisch-de"}


class TestVoiceRegisterContract:
    """Contract-Tests für VoiceRegister-Literal und PersonaModel.voice_register."""

    @pytest.mark.parametrize("value", sorted(VALID_VOICE_REGISTERS))
    def test_valid_voice_register_accepted(self, value: str) -> None:
        """Jeder der 4 erlaubten Werte muss in PersonaModel akzeptiert werden."""
        p = PersonaModel(
            user_id=1,
            user_name="test_user",
            name="Test",
            bio="A test persona for voice register validation.",
            persona="x" * 300,
            voice_register=value,  # type: ignore[arg-type]
        )
        assert p.voice_register == value

    def test_invalid_voice_register_rejected(self) -> None:
        """Ungültiger Wert muss von PersonaModel rejected werden."""
        with pytest.raises(ValidationError):
            PersonaModel(
                user_id=1,
                user_name="test_user",
                name="Test",
                bio="A test persona for voice register validation.",
                persona="x" * 300,
                voice_register="casual-de",  # type: ignore[arg-type]
            )

    def test_voice_register_default_is_neutral_de(self) -> None:
        """Default muss neutral-de sein."""
        p = PersonaModel(
            user_id=1,
            user_name="test_user",
            name="Test",
            bio="A test persona for voice register validation.",
            persona="x" * 300,
        )
        assert p.voice_register == "neutral-de"

    def test_voice_register_none_allowed(self) -> None:
        """None muss für Legacy-Daten erlaubt sein."""
        p = PersonaModel(
            user_id=1,
            user_name="test_user",
            name="Test",
            bio="A test persona for voice register validation.",
            persona="x" * 300,
            voice_register=None,
        )
        assert p.voice_register is None


class TestVoiceRegisterGeneration:
    """Tests für _rule_based_voice_register Heuristik."""

    def test_rule_based_returns_only_valid_values(self) -> None:
        """_rule_based_voice_register darf nur erlaubte Werte liefern."""
        test_inputs = [
            ("Student", "Student"),
            ("Expert", "Engineer"),
            ("Journalist", "Redakteur"),
            ("Company", "CEO"),
            ("GovernmentAgency", "Official"),
            ("NGO", "Aktivist"),
            ("Developer", "DevOps"),
            ("Random", "Unknown"),
            ("", ""),
        ]
        for entity_type, profession in test_inputs:
            result = OasisProfileGenerator._rule_based_voice_register(entity_type, profession)
            assert result in VALID_VOICE_REGISTERS, (
                f"_rule_based_voice_register({entity_type!r}, {profession!r}) "
                f"returned invalid value {result!r}"
            )

    def test_rule_based_is_deterministic(self) -> None:
        """Gleicher Input muss immer gleichen Output liefern."""
        for _ in range(5):
            assert OasisProfileGenerator._rule_based_voice_register("Developer", "Software") == "technical-de"
            assert OasisProfileGenerator._rule_based_voice_register("Journalist", "Redakteur") == "skeptisch-de"
            assert OasisProfileGenerator._rule_based_voice_register("Company", "CEO") == "neutral-de"
            assert OasisProfileGenerator._rule_based_voice_register("GovernmentAgency", "Official") == "formal-de"
