"""Regression #1713 (Slice S1): der Single-Platform-Runner
(``sim_runtime/platform_runner.py``, Aufrufpfad ``run_twitter_simulation.py``
/ ``run_reddit_simulation.py``) rief den Action-Logger nie auf — ein Run ueber
diesen Pfad hatte kein ``actions.jsonl``, und Downstream-Reader
(``action_log_reader.py``, ``role_leakage.py``) sahen nichts.

``SinglePlatformRunner._log_round_actions`` ist die extrahierte Methode, die
jetzt pro Runde neue OASIS-Trace-Zeilen liest und mit ``round`` in
``actions.jsonl`` loggt — ohne den vollen ``oasis.make``/CAMEL-Env-Aufbau zu
brauchen, den ``run()`` sonst voraussetzt.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

platform_runner = pytest.importorskip("sim_runtime.platform_runner")
from action_logger import PlatformActionLogger  # type: ignore[import-not-found]  # noqa: E402

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
CREATE TABLE trace (
    user_id INTEGER,
    created_at DATETIME,
    action TEXT,
    info TEXT,
    PRIMARY KEY(user_id, created_at, action, info)
);
"""


def _make_runner(tmp_path: Path):
    """``SinglePlatformRunner`` ohne ``__init__`` (kein Config-File, kein
    Seed) — ``_log_round_actions`` braucht nur ``self.action_logger``."""
    runner = platform_runner.SinglePlatformRunner.__new__(
        platform_runner.SinglePlatformRunner
    )
    runner.action_logger = PlatformActionLogger("twitter", str(tmp_path))
    return runner


def _build_db_with_round1_post(tmp_path: Path) -> str:
    db_path = tmp_path / "twitter_simulation.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (0, 0, "mara_l", "Mara Lindner"),
    )
    conn.execute(
        "INSERT INTO post (post_id, user_id, content) VALUES (?, ?, ?)",
        (1, 0, "Erste Runde."),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (0, "2026-09-29 09:30:00", "create_post",
         json.dumps({"content": "Erste Runde.", "post_id": 1})),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _read_log_lines(tmp_path: Path) -> list[dict]:
    log_path = tmp_path / "twitter" / "actions.jsonl"
    return [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines()]


class TestLogRoundActionsSetsRound:
    def test_action_carries_requested_round_number(self, tmp_path) -> None:
        runner = _make_runner(tmp_path)
        db_path = _build_db_with_round1_post(tmp_path)

        actions_logged, new_last_rowid = runner._log_round_actions(
            db_path, 1, {0: "Mara Lindner"}, 0, simulated_minutes_after=30
        )

        assert actions_logged == 1
        assert new_last_rowid == 1

        entries = _read_log_lines(tmp_path)
        action_entries = [e for e in entries if e.get("action_type")]
        assert len(action_entries) == 1
        assert action_entries[0]["round"] == 1
        assert action_entries[0]["action_type"] == "CREATE_POST"
        assert action_entries[0]["agent_name"] == "Mara Lindner"

    def test_round_end_event_carries_same_round_number(self, tmp_path) -> None:
        runner = _make_runner(tmp_path)
        db_path = _build_db_with_round1_post(tmp_path)

        runner._log_round_actions(db_path, 1, {0: "Mara Lindner"}, 0, simulated_minutes_after=30)

        entries = _read_log_lines(tmp_path)
        round_end = [e for e in entries if e.get("event_type") == "round_end"][0]
        assert round_end["round"] == 1
        assert round_end["actions_count"] == 1

    def test_no_new_rows_logs_zero_actions_and_advances_no_rowid(self, tmp_path) -> None:
        runner = _make_runner(tmp_path)
        db_path = _build_db_with_round1_post(tmp_path)
        last_rowid = 1  # bereits verarbeitet (z.B. Initial-Post-Fix #1713)

        actions_logged, new_last_rowid = runner._log_round_actions(
            db_path, 2, {0: "Mara Lindner"}, last_rowid, simulated_minutes_after=60
        )

        assert actions_logged == 0
        assert new_last_rowid == last_rowid
        entries = _read_log_lines(tmp_path)
        round_end = [e for e in entries if e.get("event_type") == "round_end"][0]
        assert round_end["round"] == 2
        assert round_end["actions_count"] == 0
