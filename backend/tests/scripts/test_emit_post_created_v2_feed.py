"""Unit-Tests fuer die v2-Feed-Felder von ``_emit_post_created_to_redis``
(#1713 UI-2a): kind, round_num, root_post_id, quoted_post_id/quote_body,
reposted_post_id, parent_persona_id/-name.

Ergaenzt ``test_emit_post_created.py`` (Bestand, #1216/#1009) statt es zu
ersetzen.
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
    client = MagicMock()
    client.publish = AsyncMock()
    monkeypatch.setattr(rps, "_get_redis_client", lambda _url: client)
    return client


async def _emit(client_payload_capture, **overrides):
    del client_payload_capture  # nur zur Lesbarkeit am Call-Ort
    base = {
        "simulation_id": "sim_test",
        "platform": "twitter",
        "redis_url": "redis://localhost",
    }
    base.update(overrides)
    await rps._emit_post_created_to_redis(**base)


class TestKindMapping:
    @pytest.mark.asyncio
    async def test_create_post_has_kind_post(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 1,
                "agent_name": "Mara Lindner",
                "action_type": "CREATE_POST",
                "action_args": {"post_id": 1, "content": "Hallo Welt"},
            },
            round_num=1,
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["kind"] == "post"
        assert payload["round_num"] == 1
        assert payload["parent_comment_id"] is None

    @pytest.mark.asyncio
    async def test_create_comment_has_kind_comment_and_root(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            platform="reddit",
            action_data={
                "agent_id": 7,
                "agent_name": "Jonas Berg",
                "action_type": "CREATE_COMMENT",
                "action_args": {
                    "comment_id": 99,
                    "post_id": 42,
                    "content": "Antwort darauf",
                    "post_author_name": "Mara Lindner",
                    "post_author_agent_id": 3,
                },
            },
            round_num=2,
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["kind"] == "comment"
        assert payload["root_post_id"] == "reddit:42"
        assert payload["parent_persona_name"] == "Mara Lindner"
        assert payload["parent_persona_id"] == "3"

    @pytest.mark.asyncio
    async def test_repost_has_kind_repost_empty_body_and_reference(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 7,
                "agent_name": "Jonas Berg",
                "action_type": "REPOST",
                "action_args": {
                    "new_post_id": 99,
                    "original_post_id": 42,
                    "original_content": "Das Original.",
                    "original_author_name": "Mara Lindner",
                    "original_author_agent_id": 3,
                },
            },
            round_num=3,
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["kind"] == "repost"
        assert payload["body"] == ""
        assert payload["reposted_post_id"] == "twitter:42"
        assert payload["root_post_id"] == "twitter:42"
        assert payload["parent_persona_name"] == "Mara Lindner"
        assert payload["parent_persona_id"] == "3"
        assert payload["quoted_post_id"] is None

    @pytest.mark.asyncio
    async def test_quote_has_kind_quote_own_body_and_quote_body(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 9,
                "agent_name": "Ada Torres",
                "action_type": "QUOTE_POST",
                "action_args": {
                    "new_post_id": 100,
                    "quoted_id": 42,
                    "quote_content": "Genau das sehe ich auch so.",
                    "original_content": "Das Original.",
                    "original_author_name": "Mara Lindner",
                    "original_author_agent_id": 3,
                },
            },
            round_num=4,
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["kind"] == "quote"
        # body ist die eigene Kommentierung, nicht das zitierte Original.
        assert payload["body"] == "Genau das sehe ich auch so."
        assert payload["quote_body"] == "Das Original."
        assert payload["quoted_post_id"] == "twitter:42"
        assert payload["parent_persona_name"] == "Mara Lindner"
        # Ein Zitat startet einen eigenen Strang — kein root_post_id.
        assert payload["root_post_id"] is None

    @pytest.mark.asyncio
    async def test_quote_without_own_text_is_noop(self, monkeypatch) -> None:
        """Contract verlangt body!=='' fuer kind=quote — ohne quote_content
        emittiert die Funktion nicht, statt ein ungueltiges Payload zu senden."""
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 9,
                "agent_name": "Ada Torres",
                "action_type": "QUOTE_POST",
                "action_args": {
                    "new_post_id": 100,
                    "quoted_id": 42,
                    "original_content": "Das Original.",
                },
            },
            round_num=4,
        )
        assert client.publish.await_count == 0

    @pytest.mark.asyncio
    async def test_repost_without_reference_omits_root_and_reposted(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 7,
                "agent_name": "Jonas Berg",
                "action_type": "REPOST",
                "action_args": {"new_post_id": 99},
            },
            round_num=1,
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["reposted_post_id"] is None
        assert payload["root_post_id"] is None
        assert payload["body"] == ""


class TestLikeCountAndRoundNum:
    @pytest.mark.asyncio
    async def test_new_post_has_zero_like_count(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 1,
                "agent_name": "Mara Lindner",
                "action_type": "CREATE_POST",
                "action_args": {"post_id": 1, "content": "Hallo Welt"},
            },
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["like_count"] == 0

    @pytest.mark.asyncio
    async def test_round_num_defaults_to_none(self, monkeypatch) -> None:
        client = _captured_publish(monkeypatch)
        await _emit(
            client,
            action_data={
                "agent_id": 1,
                "agent_name": "Mara Lindner",
                "action_type": "CREATE_POST",
                "action_args": {"post_id": 1, "content": "Hallo Welt"},
            },
        )
        payload = json.loads(client.publish.await_args.args[1])
        assert payload["round_num"] is None
