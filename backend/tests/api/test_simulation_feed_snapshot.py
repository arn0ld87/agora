"""Contract-Test für den Feed-Snapshot-Endpoint (#1009).

Verifiziert, dass ``GET /api/simulation/<id>/feed-snapshot`` die SQLite-Post-/
Comment-/User-Tabellen gegen die Profil-Datei joined und eine Liste liefert,
die gegen ``PostCreatedEvent`` validiert — ohne erfundene Feldwerte.

Abgedeckt:
- post_id ist plattformpräfixt (``reddit:N``), kein Dedup-Konflikt.
- persona_name und voice_register werden aus Profil aufgelöst.
- timestamp ist tz-aware (UTC-Offset).
- score ist der echte akkumulierte Voting-Stand (num_likes - num_dislikes).
- Kommentare erscheinen mit parent_post_id = Elternpost.
- Twitter-Snapshot nutzt ``neutral-de`` als voice_register (CSV persistiert keins).
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


def _make_reddit_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(
        """
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
    )
    cur.executemany(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        [(1, 101, "lena_h", "Lena Hoffmann"), (2, 102, "mira_w", "Mira Winter")],
    )
    cur.executemany(
        "INSERT INTO post (post_id, user_id, content, created_at, num_likes, num_dislikes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        [
            (10, 1, "Erster Post", "2026-05-14 23:33:55", 5, 2),
            (11, 2, "Zweiter Post", "2026-05-14 23:34:00", 0, 0),
        ],
    )
    cur.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, created_at, num_likes) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (20, 10, 2, "Antwort auf Post 1", "2026-05-14 23:41:30", 1),
    )
    conn.commit()
    conn.close()


def _make_twitter_db(db_path: Path) -> None:
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.executescript(
        """
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
        """
    )
    cur.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (1, 201, "ada_t", "Ada Torres"),
    )
    cur.execute(
        "INSERT INTO post (post_id, user_id, content, created_at, num_likes) "
        "VALUES (?, ?, ?, ?, ?)",
        (1, 1, "Tweet 1", "2026-05-14 23:33:55", 7),
    )
    conn.commit()
    conn.close()


@pytest.fixture()
def _sim_dir(monkeypatch, tmp_path):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    sim_id = "sim_abcdef012345"
    sim_dir = tmp_path / "simulations" / sim_id
    sim_dir.mkdir(parents=True)
    return sim_id, sim_dir


class TestFeedSnapshot:
    def test_reddit_snapshot_validates_against_contract(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_reddit_db(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps(
                [
                    {"user_id": 1, "name": "Lena Hoffmann", "voice_register": "formal-de"},
                    {"user_id": 2, "name": "Mira Winter", "voice_register": "neutral-de"},
                ]
            ),
            encoding="utf-8",
        )

        app = _build_app()
        resp = app.test_client().get(f"/api/simulation/{sim_id}/feed-snapshot?platform=reddit")
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["success"] is True
        posts = body["data"]["posts"]
        # 2 Posts + 1 Comment
        assert len(posts) == 3

        # Jeder Eintrag validiert gegen den Layer-0-Vertrag.
        events = [PostCreatedEvent.model_validate(p) for p in posts]
        by_id = {e.post_id: e for e in events}

        # Posts: plattformpräfixt, kein Dedup-Konflikt mit Twitter-Post 1.
        assert "reddit:10" in by_id
        assert "reddit:11" in by_id
        post10 = by_id["reddit:10"]
        assert post10.parent_post_id is None
        assert post10.persona_id == "101"
        assert post10.persona_name == "Lena Hoffmann"
        assert post10.voice_register.value == "formal-de"
        assert post10.score == 3  # 5 likes - 2 dislikes
        # timestamp ist tz-aware (Offset vorhanden)
        assert post10.timestamp.tzinfo is not None

        # Kommentar hängt unter seinem Elternpost.
        comment = by_id["reddit:comment:20"]
        assert comment.parent_post_id == "reddit:10"
        assert comment.persona_name == "Mira Winter"
        assert comment.body == "Antwort auf Post 1"

    def test_snapshot_sorted_chronologically(self, _sim_dir) -> None:
        sim_id, sim_dir = _sim_dir
        _make_reddit_db(sim_dir / "reddit_simulation.db")
        (sim_dir / "reddit_profiles.json").write_text(
            json.dumps([{"user_id": 1, "name": "Lena", "voice_register": "neutral-de"}]),
            encoding="utf-8",
        )

        app = _build_app()
        posts = app.test_client().get(
            f"/api/simulation/{sim_id}/feed-snapshot?platform=reddit"
        ).get_json()["data"]["posts"]
        timestamps = [p["timestamp"] for p in posts]
        assert timestamps == sorted(timestamps)

    def test_twitter_snapshot_uses_neutral_de_voice_register(self, _sim_dir) -> None:
        """Twitter-CSV persistiert kein voice_register → neutral-de (Generator-Default)."""
        sim_id, sim_dir = _sim_dir
        _make_twitter_db(sim_dir / "twitter_simulation.db")
        (sim_dir / "twitter_profiles.csv").write_text(
            "user_id,name,username,user_char,description\n"
            "1,Ada Torres,ada_t,x,bio\n",
            encoding="utf-8",
        )

        app = _build_app()
        posts = app.test_client().get(
            f"/api/simulation/{sim_id}/feed-snapshot?platform=twitter"
        ).get_json()["data"]["posts"]
        assert len(posts) == 1
        ev = PostCreatedEvent.model_validate(posts[0])
        assert ev.post_id == "twitter:1"
        assert ev.platform.value == "twitter"
        assert ev.voice_register.value == "neutral-de"
        assert ev.persona_name == "Ada Torres"
        assert ev.score == 0  # Twitter hat kein Voting

    def test_missing_database_returns_empty(self, _sim_dir) -> None:
        sim_id, _sim_dir_unused = _sim_dir
        app = _build_app()
        posts = app.test_client().get(
            f"/api/simulation/{sim_id}/feed-snapshot?platform=reddit"
        ).get_json()["data"]["posts"]
        assert posts == []

    def test_invalid_simulation_id_rejected(self, _sim_dir) -> None:
        app = _build_app()
        resp = app.test_client().get("/api/simulation/not-a-sim-id/feed-snapshot")
        assert resp.status_code in (400, 404)