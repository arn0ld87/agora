"""Regressionstests fuer Epic #1713 Slice S1 (Action-Log-Hygiene).

Zwei Defekte in ``run_parallel_simulation.py`` / ``sim_runtime/platform_runner.py``:

1. Der Initial-Post wird ueber ``_log_initial_post`` manuell in Runde 0
   geloggt (via ``on_published``-Callback), OASIS schreibt ihn aber auch in
   die ``trace``-Tabelle. Weil ``last_rowid`` danach bei 0 blieb, las die
   erste Hauptrunde dieselbe(n) Trace-Zeile(n) erneut — der Startpost landete
   doppelt im Action-Log. Fix: ``last_rowid`` nach dem Initial-Post-Step auf
   ``get_max_trace_rowid(db_path)`` ziehen.
2. ``fetch_new_actions_from_db`` filterte ``reposted_id`` aus der
   Whitelist-Kopie und ``_enrich_action_context`` setzte fuer REPOST nie ein
   numerisches ``original_post_id`` (nur die angereicherten Textfelder) —
   ein Reader konnte den Ziel-Post eines Reposts nicht referenzieren.

Beide Funktionen leben seit diesem Slice gemeinsam in
``scripts/oasis_action_ingest.py`` und werden von ``run_parallel_simulation``
(Twitter- und Reddit-Pfad) *und* ``sim_runtime/platform_runner.py``
(Single-Platform-Pfad) verwendet — ein Test deckt damit beide Konsumenten ab.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import oasis_action_ingest as ingest  # type: ignore[import-not-found]  # noqa: E402

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


def _make_db_with_initial_post(tmp_path: Path) -> str:
    """Baut eine DB nach, wie sie nach ``env.step(initial_actions)`` aussieht:
    ein einzelner ``create_post``-Eintrag in ``trace`` (der Startpost)."""
    db_path = tmp_path / "twitter_simulation.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (0, 0, "mara_l", "Mara Lindner"),
    )
    conn.execute(
        "INSERT INTO post (post_id, user_id, content) VALUES (?, ?, ?)",
        (1, 0, "Startpost der Simulation."),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (0, "2026-09-29 09:00:00", "create_post",
         json.dumps({"content": "Startpost der Simulation.", "post_id": 1})),
    )
    conn.commit()
    conn.close()
    return str(db_path)


class TestNoDoubleStartPost:
    """#1713: last_rowid muss nach dem Initial-Post-Step auf den DB-Stand
    gezogen werden, sonst liest Runde 1 den Startpost erneut."""

    def test_max_trace_rowid_matches_written_row(self, tmp_path) -> None:
        db_path = _make_db_with_initial_post(tmp_path)
        assert ingest.get_max_trace_rowid(db_path) == 1

    def test_missing_db_yields_zero(self, tmp_path) -> None:
        assert ingest.get_max_trace_rowid(str(tmp_path / "missing.db")) == 0

    def test_without_fix_first_round_rereads_start_post(self, tmp_path) -> None:
        # Dokumentiert den Defekt: last_rowid bleibt 0 (alter Code) ->
        # fetch_new_actions_from_db liest die Startpost-Zeile in Runde 1
        # noch einmal.
        db_path = _make_db_with_initial_post(tmp_path)
        actions, _ = ingest.fetch_new_actions_from_db(db_path, 0, {0: "Mara Lindner"})
        assert len(actions) == 1
        assert actions[0]["action_type"] == "CREATE_POST"

    def test_with_fix_first_round_sees_no_actions(self, tmp_path) -> None:
        # Der Fix: last_rowid = get_max_trace_rowid(db_path) nach dem
        # Initial-Post-Step. Runde 1 fetcht dann korrekt nichts Neues.
        db_path = _make_db_with_initial_post(tmp_path)
        last_rowid = ingest.get_max_trace_rowid(db_path)
        actions, new_last_rowid = ingest.fetch_new_actions_from_db(
            db_path, last_rowid, {0: "Mara Lindner"}
        )
        assert actions == []
        assert new_last_rowid == last_rowid

    def test_genuinely_new_round_action_still_logged_after_fix(self, tmp_path) -> None:
        # last_rowid auf den Initial-Post-Stand ziehen darf spaetere,
        # echte Round-1-Actions nicht mit verschlucken.
        db_path = _make_db_with_initial_post(tmp_path)
        last_rowid = ingest.get_max_trace_rowid(db_path)

        conn = sqlite3.connect(db_path)
        conn.execute(
            "INSERT INTO post (post_id, user_id, content) VALUES (?, ?, ?)",
            (2, 0, "Erste echte Runde."),
        )
        conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (0, "2026-09-29 09:30:00", "create_post",
             json.dumps({"content": "Erste echte Runde.", "post_id": 2})),
        )
        conn.commit()
        conn.close()

        actions, _ = ingest.fetch_new_actions_from_db(db_path, last_rowid, {0: "Mara Lindner"})
        assert len(actions) == 1
        assert actions[0]["action_args"]["content"] == "Erste echte Runde."


class TestRepostCarriesTargetIds:
    """#1713: reposted_id fehlte in der Whitelist, original_post_id wurde
    nie als numerisches Feld gesetzt — ein Reader konnte den repostierten
    Post nicht referenzieren, nur seinen (angereicherten) Text."""

    def _build_repost_db(self, tmp_path: Path) -> str:
        db_path = tmp_path / "twitter_simulation.db"
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
            "INSERT INTO post (post_id, user_id, content) VALUES (?, ?, ?)",
            (42, 3, "Das Original."),
        )
        # OASIS legt fuer einen Repost einen neuen Post mit
        # original_post_id = Zielpost an (oasis/social_platform/platform.py).
        conn.execute(
            "INSERT INTO post (post_id, user_id, original_post_id, content) VALUES (?, ?, ?, ?)",
            (99, 7, 42, ""),
        )
        conn.execute(
            "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
            (7, "2026-09-29 09:05:00", "repost",
             json.dumps({"reposted_id": 42, "new_post_id": 99})),
        )
        conn.commit()
        conn.close()
        return str(db_path)

    def test_reposted_id_survives_whitelist(self, tmp_path) -> None:
        db_path = self._build_repost_db(tmp_path)
        actions, _ = ingest.fetch_new_actions_from_db(
            db_path, 0, {3: "Mara Lindner", 7: "Jonas Berg"}
        )
        repost = [a for a in actions if a["action_type"] == "REPOST"][0]
        assert repost["action_args"]["reposted_id"] == 42
        assert repost["action_args"]["new_post_id"] == 99

    def test_enrichment_sets_numeric_original_post_id(self, tmp_path) -> None:
        db_path = self._build_repost_db(tmp_path)
        actions, _ = ingest.fetch_new_actions_from_db(
            db_path, 0, {3: "Mara Lindner", 7: "Jonas Berg"}
        )
        repost = [a for a in actions if a["action_type"] == "REPOST"][0]
        assert repost["action_args"]["original_post_id"] == 42
        assert repost["action_args"]["original_content"] == "Das Original."
        assert repost["action_args"]["original_author_name"] == "Mara Lindner"


def test_run_parallel_simulation_reexports_shared_ingest_functions() -> None:
    """rps.fetch_new_actions_from_db(...) etc. muessen fuer bestehende Tests
    (z. B. test_action_context_enrichment.py) unveraendert funktionieren,
    obwohl die Implementierung jetzt in oasis_action_ingest.py liegt."""
    import run_parallel_simulation as rps  # type: ignore[import-not-found]

    assert rps.fetch_new_actions_from_db is ingest.fetch_new_actions_from_db
    assert rps.get_max_trace_rowid is ingest.get_max_trace_rowid
    assert rps.get_agent_names_from_config is ingest.get_agent_names_from_config
