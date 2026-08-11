"""Unit-Tests für _emit_post_created_to_redis (#1216, #1009).

Verifiziert das gebaute Payload, ohne Redis zu brauchen: ``_get_redis_client``
wird gemockt. Abgedeckt:
- persona_name aus agent_name
- voice_register-Vokabular formal-de/neutral-de/technical-de/skeptisch-de
- post_id ist plattformpräfixt (<platform>:<id>), parent_post_id ebenfalls
- CREATE_COMMENT emittiert mit parent_post_id = Elternpost
- Twitter-Plattformwert
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402


def _captured_publish(monkeypatch):
    """Mocket _get_redis_client; liefert (client, publish-Call-Liste)."""
    client = MagicMock()
    client.publish = AsyncMock()
    monkeypatch.setattr(rps, "_get_redis_client", lambda _url: client)
    return client


class TestEmitPostCreated:
    @pytest.mark.asyncio
    async def test_create_post_payload_has_persona_name_and_prefixed_id(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data={
                "agent_id": 5,
                "agent_name": "Mara Lindner",
                "action_type": "CREATE_POST",
                "action_args": {"post_id": 42, "content": "Hallo Welt", "voice_register": "formal-de"},
            },
            redis_url="redis://localhost",
        )
        assert client.publish.await_count == 1
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["post_id"] == "reddit:42"
        assert payload["parent_post_id"] is None
        assert payload["persona_id"] == "5"
        assert payload["persona_name"] == "Mara Lindner"
        assert payload["voice_register"] == "formal-de"
        assert payload["platform"] == "reddit"
        assert payload["event_type"] == "post_created"

    @pytest.mark.asyncio
    async def test_create_comment_emits_with_parent_post_id(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data={
                "agent_id": 7,
                "agent_name": "Jonas Berg",
                "action_type": "CREATE_COMMENT",
                "action_args": {"comment_id": 99, "post_id": 42, "content": "Antwort darauf"},
            },
            redis_url="redis://localhost",
        )
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["post_id"] == "reddit:comment:99"
        assert payload["parent_post_id"] == "reddit:42"
        assert payload["persona_name"] == "Jonas Berg"
        assert payload["body"] == "Antwort darauf"

    @pytest.mark.asyncio
    async def test_legacy_voice_register_falls_back_to_neutral_de(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data={
                "agent_id": 1,
                "agent_name": "Test",
                "action_type": "CREATE_POST",
                "action_args": {"post_id": 1, "content": "x", "voice_register": "casual"},
            },
            redis_url="redis://localhost",
        )
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["voice_register"] == "neutral-de"

    @pytest.mark.asyncio
    async def test_twitter_platform_value_and_prefix(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="twitter",
            action_data={
                "agent_id": 3,
                "agent_name": "Ada Torres",
                "action_type": "CREATE_POST",
                "action_args": {"post_id": 7, "content": "Tweet"},
            },
            redis_url="redis://localhost",
        )
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["platform"] == "twitter"
        assert payload["post_id"] == "twitter:7"
        assert payload["score"] == 0

    @pytest.mark.asyncio
    async def test_no_redis_url_is_noop(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data={"agent_id": 1, "agent_name": "X", "action_type": "CREATE_POST",
                         "action_args": {"post_id": 1, "content": "x"}},
            redis_url=None,
        )
        assert client.publish.await_count == 0

    @pytest.mark.asyncio
    async def test_missing_post_id_is_noop(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data={"agent_id": 1, "agent_name": "X", "action_type": "CREATE_POST",
                         "action_args": {"content": "x"}},
            redis_url="redis://localhost",
        )
        assert client.publish.await_count == 0