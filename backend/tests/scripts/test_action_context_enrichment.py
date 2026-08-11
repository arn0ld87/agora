"""Regressionstests für die Action-Anreicherung aus der OASIS-SQLite (#1209 5b–5d).

Der Live-Feed hing an einer Annahme, die die realen OASIS-Trace-Daten nicht
erfüllen: ``_emit_post_created_to_redis`` erwartete für ``CREATE_COMMENT``
einen ``post_id`` in ``action_args``. Die Trace-Zeile einer Kommentar-Aktion
trägt aber ausschließlich ``content`` und ``comment_id`` — der Elternpost steht
nur in der ``comment``-Tabelle. Damit verwarf der Emitter jeden realen
Kommentar und der Reddit-Feed blieb praktisch leer (86 % der Reddit-Aktivität
sind Kommentare).

Die Fixtures bilden deshalb das echte OASIS-Schema und die echten Trace-Payloads
nach, statt die fehlenden Felder in den Test hineinzureichen.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path
from typing import Any, Dict
from unittest.mock import AsyncMock, MagicMock

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402

# Schema-Auszug der echten OASIS-SQLite (reddit_simulation.db / twitter_simulation.db).
_SCHEMA = """
CREATE TABLE user (
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER,
    user_name TEXT,
    name TEXT,
    bio TEXT,
    created_at DATETIME,
    num_followings INTEGER DEFAULT 0,
    num_followers INTEGER DEFAULT 0
);
CREATE TABLE post (
    post_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    original_post_id INTEGER,
    content TEXT DEFAULT '',
    quote_content TEXT,
    created_at DATETIME,
    num_likes INTEGER DEFAULT 0,
    num_dislikes INTEGER DEFAULT 0,
    num_shares INTEGER DEFAULT 0,
    num_reports INTEGER DEFAULT 0
);
CREATE TABLE comment (
    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER,
    user_id INTEGER,
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    num_likes INTEGER DEFAULT 0,
    num_dislikes INTEGER DEFAULT 0
);
CREATE TABLE trace (
    user_id INTEGER,
    created_at DATETIME,
    action TEXT,
    info TEXT,
    PRIMARY KEY(user_id, created_at, action, info)
);
"""


def _build_db(tmp_path: Path, *, num_likes: int = 0, num_dislikes: int = 0) -> str:
    """Baut eine OASIS-SQLite mit einem Post und einem Kommentar darauf.

    Die Trace-Zeilen tragen exakt die Keys, die OASIS real schreibt:
    ``create_post`` → ``content`` + ``post_id``; ``create_comment`` →
    ``content`` + ``comment_id`` (ohne ``post_id``).
    """
    db_path = tmp_path / "reddit_simulation.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (3, 3, "mara_l", "Mara Lindner"),
    )
    conn.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (7, 7, "jonas_b", "Jonas Berg"),
    )
    conn.execute(
        "INSERT INTO post (post_id, user_id, content, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?)",
        (42, 3, "Die Migration ist beschlossen.", num_likes, num_dislikes),
    )
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (99, 42, 7, "Das greift zu kurz.", num_likes, num_dislikes),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (3, "2026-08-11 10:00:00", "create_post",
         json.dumps({"content": "Die Migration ist beschlossen.", "post_id": 42})),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (7, "2026-08-11 10:01:00", "create_comment",
         json.dumps({"content": "Das greift zu kurz.", "comment_id": 99})),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _fetch(db_path: str) -> Dict[str, Dict[str, Any]]:
    """Liest alle Actions und indiziert sie nach action_type."""
    actions, _ = rps.fetch_new_actions_from_db(
        db_path, 0, {3: "Mara Lindner", 7: "Jonas Berg"}
    )
    return {a["action_type"]: a for a in actions}


class TestCommentParentResolution:
    def test_create_comment_resolves_parent_post_from_comment_table(self, tmp_path) -> None:
        # Der Defekt: die Trace-Zeile kennt nur comment_id. Ohne Auflösung über
        # die comment-Tabelle bleibt post_id leer und der Emitter verwirft den
        # Kommentar (#1209 5c).
        by_type = _fetch(_build_db(tmp_path))
        comment = by_type["CREATE_COMMENT"]
        assert comment["action_args"]["comment_id"] == 99
        assert comment["action_args"]["post_id"] == 42

    def test_create_comment_enrichment_reaches_parent_post_content(self, tmp_path) -> None:
        # Folgefehler desselben Defekts: der Kontext-Zweig für CREATE_COMMENT
        # war tot, weil er an demselben fehlenden post_id hing.
        by_type = _fetch(_build_db(tmp_path))
        args = by_type["CREATE_COMMENT"]["action_args"]
        assert args["post_content"] == "Die Migration ist beschlossen."
        assert args["post_author_name"] == "Mara Lindner"

    def test_unknown_comment_id_leaves_post_id_unset(self, tmp_path) -> None:
        # Ein Kommentar ohne Zeile in der comment-Tabelle darf keinen Parent
        # erfinden — lieber kein Feed-Event als ein falscher Reply-Tree-Ast.
        db_path = _build_db(tmp_path)
        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (7, "2026-08-11 10:02:00", "create_comment",
             json.dumps({"content": "Waise.", "comment_id": 4711})),
        )
        conn.commit()
        conn.close()
        actions, _ = rps.fetch_new_actions_from_db(db_path, 0, {3: "Mara Lindner", 7: "Jonas Berg"})
        orphan = [a for a in actions if a["action_args"].get("comment_id") == 4711]
        assert len(orphan) == 1
        assert "post_id" not in orphan[0]["action_args"]


class TestEngagementScore:
    def test_create_post_carries_real_score_from_db(self, tmp_path) -> None:
        by_type = _fetch(_build_db(tmp_path, num_likes=5, num_dislikes=2))
        assert by_type["CREATE_POST"]["action_args"]["score"] == 3

    def test_create_comment_carries_real_score_from_db(self, tmp_path) -> None:
        by_type = _fetch(_build_db(tmp_path, num_likes=4, num_dislikes=1))
        assert by_type["CREATE_COMMENT"]["action_args"]["score"] == 3

    def test_score_is_zero_without_votes(self, tmp_path) -> None:
        by_type = _fetch(_build_db(tmp_path))
        assert by_type["CREATE_POST"]["action_args"]["score"] == 0

    def test_score_resolves_new_post_id_fallback(self, tmp_path) -> None:
        # _emit_post_created_to_redis akzeptiert post_id, new_post_id und id.
        # Der Score-Lookup muss denselben Fallback kennen, sonst trägt ein Post
        # mit abweichendem Schlüssel wieder eine unechte 0 in den Feed.
        #
        # `id` ist bewusst nicht abgedeckt: fetch_new_actions_from_db filtert
        # die Trace-Keys auf eine feste Liste, und `id` steht nicht darauf — der
        # Schlüssel kann action_args auf diesem Pfad nie erreichen. Der Test
        # weiter unten hält das fest.
        id_key = "new_post_id"
        db_path = tmp_path / "reddit_simulation.db"
        conn = sqlite3.connect(db_path)
        conn.executescript(_SCHEMA)
        conn.execute(
            "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
            (3, 3, "mara_l", "Mara Lindner"),
        )
        conn.execute(
            "INSERT INTO post (post_id, user_id, content, num_likes, num_dislikes) "
            "VALUES (?, ?, ?, ?, ?)",
            (42, 3, "Post mit Resonanz.", 6, 2),
        )
        conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (3, "2026-08-11 10:00:00", "create_post",
             json.dumps({"content": "Post mit Resonanz.", id_key: 42})),
        )
        conn.commit()
        conn.close()
        actions, _ = rps.fetch_new_actions_from_db(str(db_path), 0, {3: "Mara Lindner"})
        post = [a for a in actions if a["action_type"] == "CREATE_POST"][0]
        assert post["action_args"]["score"] == 4


def _captured_publish(monkeypatch):
    client = MagicMock()
    client.publish = AsyncMock()
    monkeypatch.setattr(rps, "_get_redis_client", lambda _url: client)
    return client


class TestEmitFromRealTraceData:
    """Ende zu Ende: echte Trace-Zeile → fetch → emit. Kein Feld wird
    im Test nachgereicht, das OASIS nicht selbst schreibt."""

    @pytest.mark.asyncio
    async def test_real_comment_trace_row_reaches_feed_with_parent(
        self, tmp_path, monkeypatch
    ) -> None:
        client = _captured_publish(monkeypatch)
        by_type = _fetch(_build_db(tmp_path, num_likes=4, num_dislikes=1))
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data=by_type["CREATE_COMMENT"],
            redis_url="redis://localhost",
        )
        assert client.publish.await_count == 1
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["post_id"] == "reddit:comment:99"
        assert payload["parent_post_id"] == "reddit:42"
        assert payload["persona_name"] == "Jonas Berg"
        assert payload["score"] == 3

    @pytest.mark.asyncio
    async def test_real_post_trace_row_carries_accumulated_score(
        self, tmp_path, monkeypatch
    ) -> None:
        client = _captured_publish(monkeypatch)
        by_type = _fetch(_build_db(tmp_path, num_likes=5, num_dislikes=2))
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data=by_type["CREATE_POST"],
            redis_url="redis://localhost",
        )
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["post_id"] == "reddit:42"
        assert payload["score"] == 3

    @pytest.mark.asyncio
    async def test_twitter_has_no_voting_score(self, tmp_path, monkeypatch) -> None:
        # Twitter kennt kein Up/Down-Voting; der Snapshot-Pfad setzt dort
        # ebenfalls 0. Der Live-Emit muss dieselbe Semantik tragen.
        client = _captured_publish(monkeypatch)
        by_type = _fetch(_build_db(tmp_path, num_likes=9, num_dislikes=0))
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="twitter",
            action_data=by_type["CREATE_POST"],
            redis_url="redis://localhost",
        )
        _channel, raw = client.publish.await_args.args
        payload = json.loads(raw)
        assert payload["score"] == 0

    @pytest.mark.asyncio
    async def test_payload_carries_no_sentiment_field(self, tmp_path, monkeypatch) -> None:
        # sentiment ist aus dem Vertrag entfernt (#1209 5b) — es gab nie einen
        # Sentiment-Service und das Feld trug nie einen Wert. Der Contract ist
        # extra="forbid": ein mitgesendetes Feld würde die Validierung brechen.
        client = _captured_publish(monkeypatch)
        by_type = _fetch(_build_db(tmp_path))
        await rps._emit_post_created_to_redis(
            simulation_id="sim_test",
            platform="reddit",
            action_data=by_type["CREATE_POST"],
            redis_url="redis://localhost",
        )
        _channel, raw = client.publish.await_args.args
        assert "sentiment" not in json.loads(raw)
