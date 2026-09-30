"""Feed-Snapshot v2-Felder (#1713 UI-2a): kind, root/quoted/reposted_post_id,
quote_body, parent_persona_id/-name, like_count.

Ergaenzt ``test_simulation_feed_snapshot.py`` (Bestand, #1009) statt es zu
ersetzen. Schema (``original_post_id``/``quote_content`` auf ``post``)
entspricht einem realen OASIS-Lauf (belegt an sim_54c1c2a6a875).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.post_event_contract import PostCreatedEvent


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app


_SCHEMA = """
CREATE TABLE user (
    user_id INTEGER PRIMARY KEY,
    agent_id INTEGER,
    user_name TEXT,
    name TEXT,
    bio TEXT,
    created_at DATETIME,
    num_followings INTEGER DEFAULT 0,
    num_followers INTEGER DEFAULT 0
);
CREATE TABLE post (
    post_id INTEGER PRIMARY KEY,
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
    comment_id INTEGER PRIMARY KEY,
    post_id INTEGER,
    user_id INTEGER,
    content TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    num_likes INTEGER DEFAULT 0,
    num_dislikes INTEGER DEFAULT 0
);
"""


def _make_db_with_repost_and_quote(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(_SCHEMA)
    cur.executemany(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        [
            (1, 101, "mara_l", "Mara Lindner"),
            (2, 102, "jonas_b", "Jonas Berg"),
            (3, 103, "ada_t", "Ada Torres"),
        ],
    )
    # Original.
    cur.execute(
        "INSERT INTO post (post_id, user_id, content, created_at, num_likes) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 1, "Das Original.", "2026-05-14 23:33:55", 3),
    )
    # Repost von user 2 (content bleibt leer wie bei einem echten OASIS-Repost).
    cur.execute(
        "INSERT INTO post (post_id, user_id, original_post_id, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (2, 2, 1, "", "2026-05-14 23:34:00"),
    )
    # Quote von user 3: content dupliziert das Original, quote_content ist
    # die eigene Kommentierung (belegt an sim_54c1c2a6a875).
    cur.execute(
        "INSERT INTO post (post_id, user_id, original_post_id, content, quote_content, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (3, 3, 1, "Das Original.", "Genau das sehe ich auch so.", "2026-05-14 23:35:00"),
    )
    # Kommentar auf das Original.
    cur.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (10, 1, 2, "Antwort darauf", "2026-05-14 23:36:00"),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def _sim_dir(monkeypatch, tmp_path):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    sim_id = "sim_abc123def456"
    sim_dir = tmp_path / "simulations" / sim_id
    sim_dir.mkdir(parents=True)
    return sim_id, sim_dir


class TestFeedSnapshotV2Kind:
    def _fetch_events(self, sim_id: str) -> dict[str, PostCreatedEvent]:
        app = _build_app()
        resp = app.test_client().get(f"/api/simulation/{sim_id}/feed-snapshot?platform=reddit")
        posts = resp.get_json()["data"]["posts"]
        events = [PostCreatedEvent.model_validate(p) for p in posts]
        return {e.post_id: e for e in events}

    def test_original_post_has_kind_post(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_db_with_repost_and_quote(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"user_id": i, "name": n, "voice_register": "neutral-de"} for i, n in [
                (1, "Mara Lindner"), (2, "Jonas Berg"), (3, "Ada Torres"),
            ]]),
            encoding="utf-8",
        )
        by_id = self._fetch_events(sim_id)
        original = by_id["reddit:1"]
        assert original.kind.value == "post"
        assert original.root_post_id is None
        assert original.like_count == 3

    def test_repost_has_kind_repost_and_reference(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_db_with_repost_and_quote(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"user_id": i, "name": n, "voice_register": "neutral-de"} for i, n in [
                (1, "Mara Lindner"), (2, "Jonas Berg"), (3, "Ada Torres"),
            ]]),
            encoding="utf-8",
        )
        by_id = self._fetch_events(sim_id)
        repost = by_id["reddit:2"]
        assert repost.kind.value == "repost"
        assert repost.body == ""
        assert repost.reposted_post_id == "reddit:1"
        assert repost.root_post_id == "reddit:1"
        assert repost.parent_persona_name == "Mara Lindner"
        assert repost.parent_persona_id == "101"

    def test_quote_has_kind_quote_own_body_and_quote_body(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_db_with_repost_and_quote(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"user_id": i, "name": n, "voice_register": "neutral-de"} for i, n in [
                (1, "Mara Lindner"), (2, "Jonas Berg"), (3, "Ada Torres"),
            ]]),
            encoding="utf-8",
        )
        by_id = self._fetch_events(sim_id)
        quote = by_id["reddit:3"]
        assert quote.kind.value == "quote"
        assert quote.body == "Genau das sehe ich auch so."
        assert quote.quote_body == "Das Original."
        assert quote.quoted_post_id == "reddit:1"
        assert quote.parent_persona_name == "Mara Lindner"
        # Ein Zitat startet einen eigenen Strang.
        assert quote.root_post_id is None

    def test_comment_has_kind_comment_and_parent_persona(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_db_with_repost_and_quote(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"user_id": i, "name": n, "voice_register": "neutral-de"} for i, n in [
                (1, "Mara Lindner"), (2, "Jonas Berg"), (3, "Ada Torres"),
            ]]),
            encoding="utf-8",
        )
        by_id = self._fetch_events(sim_id)
        comment = by_id["reddit:comment:10"]
        assert comment.kind.value == "comment"
        assert comment.root_post_id == "reddit:1"
        assert comment.parent_persona_name == "Mara Lindner"
        assert comment.parent_persona_id == "101"

    def test_round_num_is_none_snapshot_has_no_round_data(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_db_with_repost_and_quote(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"user_id": i, "name": n, "voice_register": "neutral-de"} for i, n in [
                (1, "Mara Lindner"), (2, "Jonas Berg"), (3, "Ada Torres"),
            ]]),
            encoding="utf-8",
        )
        by_id = self._fetch_events(sim_id)
        assert all(e.round_num is None for e in by_id.values())
