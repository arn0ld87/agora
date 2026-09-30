"""Contract-Tests fuer die v2-Felder von PostCreatedEvent (Slice UI-2a, #1713).

Rueckwaertskompatibilitaet: ein Payload ohne die neuen Felder muss weiterhin
gueltig sein (siehe test_post_event_contract.py). Diese Datei deckt die
neuen Felder selbst ab: Defaults, kind-Validierung, body/repost-Interaktion.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts.post_event_contract import PostCreatedEvent, PostKind


def _base_payload(**overrides) -> dict:
    payload = {
        "event_type": "post_created",
        "simulation_id": "sim-1",
        "post_id": "twitter:p-1",
        "parent_post_id": None,
        "platform": "twitter",
        "persona_id": "persona-1",
        "persona_name": "Test Persona",
        "voice_register": "neutral-de",
        "is_simulated": True,
        "body": "Hallo Welt",
        "timestamp": datetime.now(timezone.utc),
    }
    payload.update(overrides)
    return payload


class TestBackwardCompat:
    def test_legacy_payload_without_v2_fields_is_valid(self) -> None:
        ev = PostCreatedEvent.model_validate(_base_payload())
        assert ev.kind is None
        assert ev.round_num is None
        assert ev.parent_comment_id is None
        assert ev.root_post_id is None
        assert ev.quoted_post_id is None
        assert ev.reposted_post_id is None
        assert ev.quote_body is None
        assert ev.parent_persona_id is None
        assert ev.parent_persona_name is None
        assert ev.like_count is None


class TestKind:
    def test_kind_defaults_to_none(self) -> None:
        ev = PostCreatedEvent.model_validate(_base_payload())
        assert ev.kind is None

    @pytest.mark.parametrize("kind", ["post", "comment", "quote", "repost"])
    def test_kind_accepts_known_values(self, kind: str) -> None:
        payload = _base_payload(kind=kind, body="x")
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.kind == PostKind(kind)

    def test_kind_rejects_unknown_value(self) -> None:
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(_base_payload(kind="retweet"))


class TestBodyRepostException:
    def test_repost_allows_empty_body(self) -> None:
        payload = _base_payload(kind="repost", body="", reposted_post_id="twitter:p-0")
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.body == ""

    def test_non_repost_rejects_empty_body(self) -> None:
        for kind in ("post", "comment", "quote", None):
            with pytest.raises(ValidationError):
                PostCreatedEvent.model_validate(_base_payload(kind=kind, body=""))

    def test_legacy_no_kind_still_requires_body(self) -> None:
        with pytest.raises(ValidationError):
            PostCreatedEvent.model_validate(_base_payload(body=""))


class TestNewReferenceFields:
    def test_round_num_and_sim_time_roundtrip(self) -> None:
        payload = _base_payload(round_num=3)
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.round_num == 3

    def test_quote_fields_roundtrip(self) -> None:
        payload = _base_payload(
            kind="quote",
            quoted_post_id="twitter:p-9",
            quote_body="Original-Text",
        )
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.quoted_post_id == "twitter:p-9"
        assert ev.quote_body == "Original-Text"

    def test_repost_fields_roundtrip(self) -> None:
        payload = _base_payload(kind="repost", body="", reposted_post_id="twitter:p-2")
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.reposted_post_id == "twitter:p-2"

    def test_parent_persona_fields_roundtrip(self) -> None:
        payload = _base_payload(
            kind="comment",
            parent_post_id="reddit:p-1",
            parent_persona_id="agent-2",
            parent_persona_name="Mara Lindner",
        )
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.parent_persona_id == "agent-2"
        assert ev.parent_persona_name == "Mara Lindner"

    def test_like_count_roundtrip(self) -> None:
        payload = _base_payload(like_count=5)
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.like_count == 5

    def test_root_post_id_roundtrip(self) -> None:
        payload = _base_payload(root_post_id="reddit:p-0")
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.root_post_id == "reddit:p-0"

    def test_parent_comment_id_defaults_none_always(self) -> None:
        # Vorerst nie befuellt (Backfill folgt in Folge-Slice) — trotzdem
        # muss das Feld selbst annehmbar sein, falls ein Caller es setzt.
        payload = _base_payload(parent_comment_id="reddit:comment:1")
        ev = PostCreatedEvent.model_validate(payload)
        assert ev.parent_comment_id == "reddit:comment:1"


class TestSchemaDump:
    def test_schema_dump_contains_v2_fields(self) -> None:
        repo_root = Path(__file__).resolve().parents[3]
        schema_path = repo_root / "schemas" / "post-created-event.schema.json"
        assert schema_path.exists(), f"Schema-Dump fehlt: {schema_path}"
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        props = schema.get("properties", {})
        for field in (
            "kind",
            "round_num",
            "parent_comment_id",
            "root_post_id",
            "quoted_post_id",
            "reposted_post_id",
            "quote_body",
            "parent_persona_id",
            "parent_persona_name",
            "like_count",
        ):
            assert field in props, f"{field} muss im dumped Schema vorhanden sein"
