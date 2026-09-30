"""Regressionstest fuer ``author_agent_id`` in der Trace-Enrichment (#1713 UI-2a).

``_get_post_info`` gab bisher nur ``content``/``author_name`` zurueck — der
Emitter braucht zusaetzlich die stabile Persona-ID des Autors (agent_id),
um ``parent_persona_id`` zu fuellen (Contract-Feld aus PostCreatedEvent v2),
statt nur den Anzeigenamen. Deckt REPOST, QUOTE_POST und CREATE_COMMENT ab —
die drei Enrichment-Pfade, die ``_get_post_info`` aufrufen.
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
CREATE TABLE comment (
    comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    post_id INTEGER,
    user_id INTEGER,
    content TEXT DEFAULT '',
    created_at DATETIME,
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


def _base_db(tmp_path: Path) -> str:
    db_path = tmp_path / "twitter_simulation.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_SCHEMA)
    conn.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (3, 33, "mara_l", "Mara Lindner"),
    )
    conn.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (?, ?, ?, ?)",
        (7, 77, "jonas_b", "Jonas Berg"),
    )
    conn.execute(
        "INSERT INTO post (post_id, user_id, content) VALUES (?, ?, ?)",
        (42, 3, "Das Original."),
    )
    conn.commit()
    conn.close()
    return str(db_path)


def _base_db_with_nested_comments(tmp_path: Path) -> str:
    """Wie ``_base_db``, aber mit der ``parent_comment_id``-Spalte auf ``comment``.

    Simuliert das Ergebnis von ``install_reddit_nested_comments_patch`` (#1713
    S5), das die Spalte per ``ALTER TABLE`` nachruestet.
    """
    db_path = _base_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute("ALTER TABLE comment ADD COLUMN parent_comment_id INTEGER")
    conn.commit()
    conn.close()
    return db_path


def test_get_post_info_returns_author_agent_id(tmp_path) -> None:
    db_path = _base_db(tmp_path)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    info = ingest._get_post_info(cursor, 42, {33: "Mara Lindner"})
    conn.close()
    assert info is not None
    assert info["author_agent_id"] == 33


def test_repost_enrichment_carries_original_author_agent_id(tmp_path) -> None:
    db_path = _base_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO post (post_id, user_id, original_post_id, content) VALUES (?, ?, ?, ?)",
        (99, 7, 42, ""),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (7, "2026-09-29 09:05:00", "repost", json.dumps({"reposted_id": 42, "new_post_id": 99})),
    )
    conn.commit()
    conn.close()

    actions, _ = ingest.fetch_new_actions_from_db(
        db_path, 0, {33: "Mara Lindner", 77: "Jonas Berg"}
    )
    repost = [a for a in actions if a["action_type"] == "REPOST"][0]
    assert repost["action_args"]["original_author_agent_id"] == 33


def test_quote_post_enrichment_carries_original_author_agent_id(tmp_path) -> None:
    db_path = _base_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO post (post_id, user_id, original_post_id, content, quote_content) "
        "VALUES (?, ?, ?, ?, ?)",
        (100, 7, 42, "Das Original.", "Genau das sehe ich auch so."),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (7, "2026-09-29 09:06:00", "quote_post", json.dumps({"quoted_id": 42, "new_post_id": 100})),
    )
    conn.commit()
    conn.close()

    actions, _ = ingest.fetch_new_actions_from_db(
        db_path, 0, {33: "Mara Lindner", 77: "Jonas Berg"}
    )
    quote = [a for a in actions if a["action_type"] == "QUOTE_POST"][0]
    assert quote["action_args"]["original_author_agent_id"] == 33
    assert quote["action_args"]["quote_content"] == "Genau das sehe ich auch so."


def test_create_comment_enrichment_carries_post_author_agent_id(tmp_path) -> None:
    db_path = _base_db(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content) VALUES (?, ?, ?, ?)",
        (5, 42, 7, "Antwort darauf"),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (7, "2026-09-29 09:07:00", "create_comment",
         json.dumps({"content": "Antwort darauf", "comment_id": 5})),
    )
    conn.commit()
    conn.close()

    actions, _ = ingest.fetch_new_actions_from_db(
        db_path, 0, {33: "Mara Lindner", 77: "Jonas Berg"}
    )
    comment = [a for a in actions if a["action_type"] == "CREATE_COMMENT"][0]
    assert comment["action_args"]["post_author_agent_id"] == 33
    assert comment["action_args"]["post_author_name"] == "Mara Lindner"


def test_create_comment_enrichment_carries_parent_comment_id_when_column_present(
    tmp_path,
) -> None:
    """(#1713 S5) Ingest liest parent_comment_id aus der comment-Tabelle, wenn
    die Spalte vorhanden ist (nested-comments-Patch aktiv, Reddit)."""
    db_path = _base_db_with_nested_comments(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, parent_comment_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (5, 42, 7, "Elternkommentar", None),
    )
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, parent_comment_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (6, 42, 3, "Antwort auf Elternkommentar", 5),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (3, "2026-09-29 09:08:00", "create_comment",
         json.dumps({"content": "Antwort auf Elternkommentar", "comment_id": 6})),
    )
    conn.commit()
    conn.close()

    actions, _ = ingest.fetch_new_actions_from_db(
        db_path, 0, {33: "Mara Lindner", 77: "Jonas Berg"}
    )
    comment = [a for a in actions if a["action_type"] == "CREATE_COMMENT"][0]
    assert comment["action_args"]["parent_comment_id"] == 5


def test_create_comment_enrichment_top_level_parent_comment_id_is_none(tmp_path) -> None:
    """Top-Level-Kommentar (kein Parent): parent_comment_id wird als None
    ausgelesen, kein Fehler beim Lookup (#1713 S5)."""
    db_path = _base_db_with_nested_comments(tmp_path)
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content, parent_comment_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (5, 42, 7, "Top-Level-Kommentar", None),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (7, "2026-09-29 09:09:00", "create_comment",
         json.dumps({"content": "Top-Level-Kommentar", "comment_id": 5})),
    )
    conn.commit()
    conn.close()

    actions, _ = ingest.fetch_new_actions_from_db(
        db_path, 0, {33: "Mara Lindner", 77: "Jonas Berg"}
    )
    comment = [a for a in actions if a["action_type"] == "CREATE_COMMENT"][0]
    assert comment["action_args"]["parent_comment_id"] is None


def test_create_comment_enrichment_without_parent_column_is_resume_safe(tmp_path) -> None:
    """(#1713 S5) Aeltere/nicht-Reddit-DB ohne parent_comment_id-Spalte: kein
    Fehler, das Feld bleibt schlicht unbefuellt (Resume-Sicherheit)."""
    db_path = _base_db(tmp_path)  # OHNE ALTER TABLE -- Spalte fehlt bewusst
    conn = sqlite3.connect(db_path)
    conn.execute(
        "INSERT INTO comment (comment_id, post_id, user_id, content) VALUES (?, ?, ?, ?)",
        (5, 42, 7, "Antwort ohne Parent-Spalte"),
    )
    conn.execute(
        "INSERT INTO trace (user_id, created_at, action, info) VALUES (?, ?, ?, ?)",
        (7, "2026-09-29 09:10:00", "create_comment",
         json.dumps({"content": "Antwort ohne Parent-Spalte", "comment_id": 5})),
    )
    conn.commit()
    conn.close()

    actions, _ = ingest.fetch_new_actions_from_db(
        db_path, 0, {33: "Mara Lindner", 77: "Jonas Berg"}
    )
    comment = [a for a in actions if a["action_type"] == "CREATE_COMMENT"][0]
    assert "parent_comment_id" not in comment["action_args"]
