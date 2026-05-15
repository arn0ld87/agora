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
        "voice_register": "casual",
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

    def test_formal_voice_register_accepted(self) -> None:
        payload = _valid_payload()
        payload["voice_register"] = "formal"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.voice_register is VoiceRegister.FORMAL

    def test_jugendsprache_voice_register_accepted(self) -> None:
        payload = _valid_payload()
        payload["voice_register"] = "jugendsprache"
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.voice_register is VoiceRegister.JUGENDSPRACHE

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
