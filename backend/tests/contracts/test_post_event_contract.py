"""Contract-Tests für PostCreatedEvent.

Layer 0 — Single Source of Truth. extra="forbid", Enum-Werte hart,
Pflichtfelder hart.
"""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from app.contracts.post_event_contract import (
    Platform,
    PostCreatedEvent,
    VoiceRegister,
)


def _valid_payload() -> dict:
    return {
        "event_type": "post_created",
        "simulation_id": "sim-123",
        "post_id": "post-abc",
        "parent_post_id": None,
        "platform": "reddit",
        "persona_id": "persona-7",
        "persona_name": "Alex Schneider",
        "voice_register": "neutral-de",
        "is_simulated": True,
        "body": "Mein erster Post.",
        "timestamp": datetime(2026, 5, 15, 12, 0, tzinfo=timezone.utc).isoformat(),
    }


class TestPostCreatedEvent:
    def test_accepts_valid_payload(self) -> None:
        ev = PostCreatedEvent.model_validate(_valid_payload())
        assert ev.platform is Platform.REDDIT
        assert ev.parent_post_id is None
        assert ev.is_simulated is True

    def test_rejects_unknown_field(self) -> None:
        payload = _valid_payload()
        payload["new_field"] = "x"
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_rejects_unknown_platform(self) -> None:
        payload = _valid_payload()
        payload["platform"] = "mastodon"
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_parent_post_id_allowed_for_reddit(self) -> None:
        payload = _valid_payload()
        payload["parent_post_id"] = "post-parent"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.parent_post_id == "post-parent"

    def test_voice_register_required(self) -> None:
        payload = _valid_payload()
        del payload["voice_register"]
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_is_simulated_default_true(self) -> None:
        payload = _valid_payload()
        del payload["is_simulated"]
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.is_simulated is True

    def test_event_type_literal_post_created(self) -> None:
        payload = _valid_payload()
        payload["event_type"] = "wrong"
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_twitter_platform_accepted(self) -> None:
        payload = _valid_payload()
        payload["platform"] = "twitter"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.platform is Platform.TWITTER

    def test_formal_de_voice_register_accepted(self) -> None:
        payload = _valid_payload()
        payload["voice_register"] = "formal-de"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.voice_register is VoiceRegister.FORMAL_DE

    def test_neutral_de_voice_register_accepted(self) -> None:
        payload = _valid_payload()
        payload["voice_register"] = "neutral-de"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.voice_register is VoiceRegister.NEUTRAL_DE

    def test_technical_de_voice_register_accepted(self) -> None:
        payload = _valid_payload()
        payload["voice_register"] = "technical-de"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.voice_register is VoiceRegister.TECHNICAL_DE

    def test_skeptisch_de_voice_register_accepted(self) -> None:
        payload = _valid_payload()
        payload["voice_register"] = "skeptisch-de"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.voice_register is VoiceRegister.SKEPTISCH_DE

    def test_rejects_legacy_voice_register_vocabulary(self) -> None:
        """Altes Vokabular (formal/casual/jugendsprache) ist nicht mehr gültig."""
        for legacy in ("formal", "casual", "jugendsprache"):
            payload = _valid_payload()
            payload["voice_register"] = legacy
            with pytest.raises(ValidationError):
                PostCreatedEvent.model_validate(payload)

    def test_body_required_non_empty(self) -> None:
        payload = _valid_payload()
        del payload["body"]
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_simulation_id_required(self) -> None:
        payload = _valid_payload()
        del payload["simulation_id"]
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)


class TestPostCreatedEventSentimentScore:
    """Phase B — neue optionale Felder sentiment + score."""

    def test_sentiment_default_is_none(self) -> None:
        ev = PostCreatedEvent.model_validate(_valid_payload())
        assert ev.sentiment is None

    def test_sentiment_accepts_null(self) -> None:
        payload = {**_valid_payload(), "sentiment": None}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.sentiment is None

    def test_sentiment_accepts_zero(self) -> None:
        payload = {**_valid_payload(), "sentiment": 0.0}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.sentiment == 0.0

    def test_sentiment_accepts_positive_one(self) -> None:
        payload = {**_valid_payload(), "sentiment": 1.0}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.sentiment == 1.0

    def test_sentiment_accepts_negative_one(self) -> None:
        payload = {**_valid_payload(), "sentiment": -1.0}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.sentiment == -1.0

    def test_sentiment_rejects_above_range(self) -> None:
        payload = {**_valid_payload(), "sentiment": 1.5}
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_sentiment_rejects_below_range(self) -> None:
        payload = {**_valid_payload(), "sentiment": -1.5}
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_score_default_is_zero(self) -> None:
        ev = PostCreatedEvent.model_validate(_valid_payload())
        assert ev.score == 0

    def test_score_accepts_positive(self) -> None:
        payload = {**_valid_payload(), "score": 42}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.score == 42

    def test_score_accepts_negative(self) -> None:
        payload = {**_valid_payload(), "score": -7}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.score == -7

    def test_score_accepts_zero(self) -> None:
        payload = {**_valid_payload(), "score": 0}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.score == 0

    def test_twitter_post_score_default_zero(self) -> None:
        """Twitter-Posts haben kein Voting — score bleibt 0."""
        payload = {**_valid_payload(), "platform": "twitter"}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.score == 0


class TestPostCreatedEventPersonaName:
    """#1216 5a — persona_name als Anzeigename (persona_id bleibt Identifikator)."""

    def test_persona_name_accepted(self) -> None:
        ev = PostCreatedEvent.model_validate(_valid_payload())
        assert ev.persona_name == "Alex Schneider"

    def test_persona_name_required(self) -> None:
        payload = _valid_payload()
        del payload["persona_name"]
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_persona_name_rejects_empty(self) -> None:
        payload = {**_valid_payload(), "persona_name": ""}
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_persona_name_rejects_whitespace_only(self) -> None:
        payload = {**_valid_payload(), "persona_name": "   "}
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(payload)

    def test_persona_id_stays_separate_from_name(self) -> None:
        """persona_id ist der stabile Identifikator, persona_name die Anzeige."""
        payload = {**_valid_payload(), "persona_id": "agent-14", "persona_name": "Mira"}
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.persona_id == "agent-14"
        assert ev.persona_name == "Mira"
