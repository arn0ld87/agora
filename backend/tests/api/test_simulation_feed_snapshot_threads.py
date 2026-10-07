"""Feed-Snapshot beendeter Laeufe: Twitter-Antworten, Runde, Elternkommentar (#1801 E4).

Schema und Aktionsprotokoll entsprechen realen Laeufen (belegt an
``sim_504dc7b26443``): ``comment`` hat dort keine Runden- und keine
Elternkommentar-Spalte, ``actions.jsonl`` traegt die Runde (``round``) und
``comment_id`` bzw. ``new_post_id`` in den Aktionsargumenten, ``CREATE_POST``
nur ``content``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from app.api import simulation_bp
from app.contracts.post_event_contract import PostCreatedEvent
from app.services.sim.snapshot_rounds import load_round_index


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.extensions = {}
    app.register_blueprint(simulation_bp, url_prefix="/api/simulation")
    return app


_USER_POST = """
CREATE TABLE user (
    user_id INTEGER PRIMARY KEY, agent_id INTEGER, user_name TEXT, name TEXT,
    bio TEXT, created_at DATETIME,
    num_followings INTEGER DEFAULT 0, num_followers INTEGER DEFAULT 0
);
CREATE TABLE post (
    post_id INTEGER PRIMARY KEY, user_id INTEGER, original_post_id INTEGER,
    content TEXT DEFAULT '', quote_content TEXT, created_at DATETIME,
    num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0,
    num_shares INTEGER DEFAULT 0, num_reports INTEGER DEFAULT 0
);
"""
_COMMENT = """
CREATE TABLE comment (
    comment_id INTEGER PRIMARY KEY, post_id INTEGER, user_id INTEGER,
    content TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    num_likes INTEGER DEFAULT 0, num_dislikes INTEGER DEFAULT 0
    {extra}
);
"""


def _make_db(path: Path, *, parent_column: bool, comments: list[tuple[Any, ...]]) -> None:
    """Zwei Nutzer, Originalpost 1 (user 1), Quote 2 (user 2), Kommentare nach Bedarf.

    ``comments``: (comment_id, post_id, user_id, content, created_at[, parent]).
    """
    conn = sqlite3.connect(str(path))
    cur = conn.cursor()
    cur.executescript(_USER_POST)
    cur.executescript(_COMMENT.format(extra=", parent_comment_id INTEGER" if parent_column else ""))
    cur.executemany(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        [(1, 101, "mara", "Mara Lindner"), (2, 102, "jonas", "Jonas Berg")],
    )
    cur.execute(
        "INSERT INTO post (post_id, user_id, content, created_at) VALUES (1, 1, 'Erster Beitrag', "
        "'2026-08-02 15:00:00')"
    )
    cur.execute(
        "INSERT INTO post (post_id, user_id, original_post_id, content, quote_content, created_at) "
        "VALUES (2, 2, 1, 'Erster Beitrag', 'Zitat dazu', '2026-08-02 15:01:00')"
    )
    for row in comments:
        if parent_column:
            parent = row[5] if len(row) > 5 else None
            cur.execute(
                "INSERT INTO comment (comment_id, post_id, user_id, content, created_at, "
                "parent_comment_id) VALUES (?, ?, ?, ?, ?, ?)",
                (*row[:5], parent),
            )
        else:
            cur.execute(
                "INSERT INTO comment (comment_id, post_id, user_id, content, created_at) "
                "VALUES (?, ?, ?, ?, ?)",
                row[:5],
            )
    conn.commit()
    conn.close()


def _write_actions(path: Path, records: list[dict[str, Any] | str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [r if isinstance(r, str) else json.dumps(r) for r in records]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _start(platform: str) -> dict[str, Any]:
    return {"event_type": "simulation_start", "platform": platform, "total_rounds": 3}


def _action(rnd: int, agent: int, kind: str, args: dict[str, Any], *, ok: bool = True) -> dict[str, Any]:
    return {
        "round": rnd,
        "timestamp": "2026-08-02T15:00:00",
        "agent_id": agent,
        "agent_name": f"A{agent}",
        "action_type": kind,
        "action_args": args,
        "result": None,
        "success": ok,
    }


@pytest.fixture()
def _sim(monkeypatch, tmp_path):
    from app.config import Config

    monkeypatch.setattr(Config, "UPLOAD_FOLDER", str(tmp_path))
    sim_id = "sim_1801e4aa0001"
    sim_dir = tmp_path / "simulations" / sim_id
    sim_dir.mkdir(parents=True)
    (sim_dir / "reddit_profiles.json").write_text(
        json.dumps(
            [
                {"user_id": 1, "name": "Mara Lindner", "voice_register": "neutral-de"},
                {"user_id": 2, "name": "Jonas Berg", "voice_register": "neutral-de"},
            ]
        ),
        encoding="utf-8",
    )
    (sim_dir / "twitter_profiles.csv").write_text(
        "user_id,name,username,user_char,description\n"
        "1,Mara Lindner,mara,x,bio\n2,Jonas Berg,jonas,x,bio\n",
        encoding="utf-8",
    )
    return sim_id, sim_dir


def _events(sim_id: str, platform: str) -> dict[str, PostCreatedEvent]:
    resp = _build_app().test_client().get(
        f"/api/simulation/{sim_id}/feed-snapshot?platform={platform}"
    )
    assert resp.status_code == 200
    return {
        e.post_id: e
        for e in (PostCreatedEvent.model_validate(p) for p in resp.get_json()["data"]["posts"])
    }


class TestTwitterReplies:
    def test_twitter_comment_appears_with_parent_and_round(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(
            sim_dir / "twitter_simulation.db",
            parent_column=False,
            comments=[(7, 1, 2, "Antwort auf den Tweet", "2026-08-02 15:02:00")],
        )
        _write_actions(
            sim_dir / "twitter" / "actions.jsonl",
            [
                _start("twitter"),
                _action(0, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _action(1, 102, "QUOTE_POST", {"new_post_id": "2", "quoted_id": "1"}),
                _action(2, 102, "CREATE_COMMENT", {"content": "Antwort auf den Tweet", "comment_id": "7"}),
            ],
        )
        by_id = _events(sim_id, "twitter")

        reply = by_id["twitter:comment:7"]
        assert reply.kind.value == "comment"
        assert reply.platform.value == "twitter"
        assert reply.parent_post_id == "twitter:1"
        assert reply.root_post_id == "twitter:1"
        assert reply.parent_persona_id == "101"
        assert reply.parent_persona_name == "Mara Lindner"
        assert reply.persona_name == "Jonas Berg"
        assert reply.score == 0  # Twitter kennt kein Voting
        assert reply.round_num == 2
        # Spalte fehlt auf Twitter-Altstand -> kein Elternkommentar erfunden.
        assert reply.parent_comment_id is None

    def test_twitter_without_comment_table_keeps_posts_only(self, _sim) -> None:
        sim_id, sim_dir = _sim
        conn = sqlite3.connect(str(sim_dir / "twitter_simulation.db"))
        conn.executescript(_USER_POST)
        conn.execute("INSERT INTO user (user_id, agent_id, name) VALUES (1, 101, 'Mara Lindner')")
        conn.execute(
            "INSERT INTO post (post_id, user_id, content, created_at) "
            "VALUES (1, 1, 'Nur ein Post', '2026-08-02 15:00:00')"
        )
        conn.commit()
        conn.close()
        assert set(_events(sim_id, "twitter")) == {"twitter:1"}


class TestRounds:
    def test_rounds_filled_where_keys_are_unique(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(
            sim_dir / "reddit_simulation.db",
            parent_column=False,
            comments=[(5, 1, 2, "Kommentar", "2026-08-02 15:02:00")],
        )
        _write_actions(
            sim_dir / "reddit" / "actions.jsonl",
            [
                _start("reddit"),
                _action(0, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _action(3, 102, "QUOTE_POST", {"new_post_id": "2", "quoted_id": "1"}),
                _action(2, 102, "CREATE_COMMENT", {"content": "Kommentar", "comment_id": "5"}),
            ],
        )
        by_id = _events(sim_id, "reddit")
        assert by_id["reddit:1"].round_num == 0  # Startpost: Runde 0 ist ein echter Wert
        assert by_id["reddit:2"].round_num == 3
        assert by_id["reddit:comment:5"].round_num == 2

    def test_round_stays_none_without_actions_file(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(
            sim_dir / "reddit_simulation.db",
            parent_column=False,
            comments=[(5, 1, 2, "Kommentar", "2026-08-02 15:02:00")],
        )
        by_id = _events(sim_id, "reddit")
        assert len(by_id) == 3
        assert all(e.round_num is None and e.parent_comment_id is None for e in by_id.values())

    def test_start_post_logged_again_later_resolves_to_round_zero(self, _sim) -> None:
        """Startpost taucht spaeter ein zweites Mal im Protokoll auf, DB hat eine Zeile."""
        sim_id, sim_dir = _sim
        _make_db(sim_dir / "reddit_simulation.db", parent_column=False, comments=[])
        _write_actions(
            sim_dir / "reddit" / "actions.jsonl",
            [
                _start("reddit"),
                _action(0, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _action(1, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _action(1, 102, "QUOTE_POST", {"new_post_id": "2", "quoted_id": "1"}),
            ],
        )
        by_id = _events(sim_id, "reddit")
        assert by_id["reddit:1"].round_num == 0
        assert by_id["reddit:2"].round_num == 1

    def test_round_stays_none_when_later_duplicate_has_no_round_zero_entry(self, _sim) -> None:
        """Zwei Protokolleintraege (Runde 2 und 3), eine DB-Zeile, kein Startpost -> unklar."""
        sim_id, sim_dir = _sim
        _make_db(sim_dir / "reddit_simulation.db", parent_column=False, comments=[])
        _write_actions(
            sim_dir / "reddit" / "actions.jsonl",
            [
                _start("reddit"),
                _action(2, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _action(3, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
            ],
        )
        assert _events(sim_id, "reddit")["reddit:1"].round_num is None

    def test_failed_actions_do_not_count(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(sim_dir / "reddit_simulation.db", parent_column=False, comments=[])
        _write_actions(
            sim_dir / "reddit" / "actions.jsonl",
            [
                _start("reddit"),
                _action(0, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _action(2, 101, "CREATE_POST", {"content": "Erster Beitrag"}, ok=False),
            ],
        )
        assert _events(sim_id, "reddit")["reddit:1"].round_num == 0

    def test_log_spanning_several_starts_is_not_used(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(sim_dir / "reddit_simulation.db", parent_column=False, comments=[])
        _write_actions(
            sim_dir / "reddit" / "actions.jsonl",
            [
                _start("reddit"),
                _action(0, 101, "CREATE_POST", {"content": "Erster Beitrag"}),
                _start("reddit"),
                _action(0, 102, "QUOTE_POST", {"new_post_id": "2", "quoted_id": "1"}),
            ],
        )
        assert all(e.round_num is None for e in _events(sim_id, "reddit").values())

    def test_unreadable_line_is_skipped_not_fatal(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(sim_dir / "reddit_simulation.db", parent_column=False, comments=[])
        _write_actions(
            sim_dir / "reddit" / "actions.jsonl",
            [
                _start("reddit"),
                "{kaputt",
                _action(4, 102, "QUOTE_POST", {"new_post_id": "2", "quoted_id": "1"}),
            ],
        )
        assert _events(sim_id, "reddit")["reddit:2"].round_num == 4

    def test_index_ambiguous_comment_id_gives_none(self, tmp_path) -> None:
        path = tmp_path / "actions.jsonl"
        _write_actions(
            path,
            [
                _action(1, 1, "CREATE_COMMENT", {"comment_id": "9"}),
                _action(2, 1, "CREATE_COMMENT", {"comment_id": "9"}),
                _action(3, 1, "CREATE_COMMENT", {"comment_id": "10"}),
            ],
        )
        index = load_round_index(str(path))
        assert index.comment(9) is None
        ten = index.comment(10)
        assert ten is not None and ten.round_num == 3
        assert index.comment(11) is None


class TestParentComment:
    def test_nested_reddit_comment_carries_parent_comment_id(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(
            sim_dir / "reddit_simulation.db",
            parent_column=True,
            comments=[
                (5, 1, 2, "Oberster Kommentar", "2026-08-02 15:02:00", None),
                (6, 1, 1, "Antwort auf den Kommentar", "2026-08-02 15:03:00", 5),
            ],
        )
        by_id = _events(sim_id, "reddit")
        top = by_id["reddit:comment:5"]
        nested = by_id["reddit:comment:6"]
        assert top.parent_comment_id is None
        assert nested.parent_comment_id == "5"
        # Der Strang haengt weiter am Post (wie im Live-Emit).
        assert nested.parent_post_id == "reddit:1"
        assert nested.root_post_id == "reddit:1"

    def test_legacy_comment_table_without_parent_column_keeps_old_shape(self, _sim) -> None:
        sim_id, sim_dir = _sim
        _make_db(
            sim_dir / "reddit_simulation.db",
            parent_column=False,
            comments=[(5, 1, 2, "Kommentar", "2026-08-02 15:02:00")],
        )
        comment = _events(sim_id, "reddit")["reddit:comment:5"]
        assert comment.parent_comment_id is None
        assert comment.parent_post_id == "reddit:1"


class TestTwitterIntegerTimestamps:
    """Echte Twitter-DBs speichern den OASIS-Zeitschritt (Ganzzahl) als created_at."""

    @staticmethod
    def _make_twitter_step_db(path: Path) -> None:
        conn = sqlite3.connect(str(path))
        conn.executescript(_USER_POST)
        conn.executescript(_COMMENT.format(extra=""))
        conn.executemany(
            "INSERT INTO user (user_id, agent_id, name) VALUES (?, ?, ?)",
            [(1, 101, "Mara Lindner"), (2, 102, "Jonas Berg")],
        )
        conn.executemany(
            "INSERT INTO post (post_id, user_id, original_post_id, content, quote_content, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (1, 1, None, "Erster Beitrag", None, 0),
                (2, 2, 1, "Erster Beitrag", "Zitat dazu", 1),
                (3, 2, None, "Unbelegter Beitrag", None, 1),
            ],
        )
        conn.execute(
            "INSERT INTO comment (comment_id, post_id, user_id, content, created_at) "
            "VALUES (7, 1, 2, 'Antwort', 2)"
        )
        conn.commit()
        conn.close()

    def test_step_integer_falls_back_to_action_timestamp(self, _sim) -> None:
        sim_id, sim_dir = _sim
        self._make_twitter_step_db(sim_dir / "twitter_simulation.db")
        stamps = {
            "start": "2026-08-02T15:00:00.000001",
            "quote": "2026-08-02T15:01:00.000001",
            "reply": "2026-08-02T15:02:00.000001",
        }
        records = [
            _start("twitter"),
            {**_action(0, 101, "CREATE_POST", {"content": "Erster Beitrag"}), "timestamp": stamps["start"]},
            {**_action(1, 102, "QUOTE_POST", {"new_post_id": "2"}), "timestamp": stamps["quote"]},
            {**_action(2, 102, "CREATE_COMMENT", {"comment_id": "7"}), "timestamp": stamps["reply"]},
        ]
        _write_actions(sim_dir / "twitter" / "actions.jsonl", records)

        by_id = _events(sim_id, "twitter")
        # Post 3 hat keinen Protokolleintrag -> kein Zeitstempel -> ausgelassen,
        # nicht erfunden.
        assert set(by_id) == {"twitter:1", "twitter:2", "twitter:comment:7"}
        assert by_id["twitter:1"].timestamp.isoformat().startswith("2026-08-02T15:00:00")
        assert by_id["twitter:2"].timestamp.isoformat().startswith("2026-08-02T15:01:00")
        assert by_id["twitter:comment:7"].timestamp.isoformat().startswith("2026-08-02T15:02:00")
        assert [by_id[k].round_num for k in ("twitter:1", "twitter:2", "twitter:comment:7")] == [0, 1, 2]

    def test_step_integer_without_actions_yields_no_events(self, _sim) -> None:
        sim_id, sim_dir = _sim
        self._make_twitter_step_db(sim_dir / "twitter_simulation.db")
        assert _events(sim_id, "twitter") == {}
