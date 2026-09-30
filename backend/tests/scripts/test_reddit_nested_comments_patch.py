"""Regressionstests fuer ``install_reddit_nested_comments_patch`` (#1713 S5).

Laeuft gegen die ECHTE installierte ``camel-oasis``-Version (0.2.5) mit
temporaeren SQLite-Datenbanken statt Mocks fuer OASIS-Teile: Platform,
SocialAction und PlatformUtils sind reale Instanzen aus dem installierten
Paket. Nur die Redis-/Runner-Umgebung drumherum existiert nicht in diesem
Prozess -- die brauchen wir hier nicht.

Die Patches in ``_sim_common.install_reddit_nested_comments_patch`` mutieren
globale OASIS-Klassen (``oasis.social_platform.database.create_db``,
``oasis.social_platform.platform.Platform.create_comment``,
``oasis.social_agent.agent_action.SocialAction.create_comment``,
``oasis.social_platform.platform_utils.PlatformUtils._add_comments_to_posts``).
Damit andere Tests im selben Prozess unbeeinflusst bleiben, sichert die
Fixture ``_restore_oasis_state`` die vier Referenzen vor jedem Test und stellt
sie danach wieder her.
"""

from __future__ import annotations

import importlib.metadata
import sqlite3
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import _sim_common as sc  # type: ignore[import-not-found]  # noqa: E402

import oasis.social_agent.agent_action as _oasis_aa  # noqa: E402
import oasis.social_platform.database as _oasis_db  # noqa: E402
import oasis.social_platform.platform as _oasis_platform  # noqa: E402
import oasis.social_platform.platform_utils as _oasis_pu  # noqa: E402
from oasis.social_platform.channel import Channel  # noqa: E402


@pytest.fixture()
def _restore_oasis_state():
    """Sichert und restauriert die vier von OASIS gepatchten Referenzen.

    Laeuft um JEDEN Test in diesem Modul, damit ein Test, der den Patch
    installiert, keine anderen Tests (in diesem oder anderen Modulen der
    Session) mit gepatchten OASIS-Klassen zurueckl aesst.
    """
    orig_db_create_db = _oasis_db.create_db
    orig_platform_create_db = _oasis_platform.create_db
    orig_platform_create_comment = _oasis_platform.Platform.create_comment
    orig_sa_create_comment = _oasis_aa.SocialAction.create_comment
    orig_add_comments = _oasis_pu.PlatformUtils._add_comments_to_posts

    yield

    _oasis_db.create_db = orig_db_create_db
    _oasis_platform.create_db = orig_platform_create_db
    _oasis_platform.Platform.create_comment = orig_platform_create_comment
    _oasis_aa.SocialAction.create_comment = orig_sa_create_comment
    _oasis_pu.PlatformUtils._add_comments_to_posts = orig_add_comments


def _comment_columns(db_path: Path) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(comment)")
        return {row[1] for row in cursor.fetchall()}
    finally:
        conn.close()


class TestVersionGuard:
    """(a) Patch nur bei camel-oasis==0.2.5 aktiv, sonst sichtbare Degradation."""

    def test_wrong_version_returns_false_and_warns(self, monkeypatch, caplog, _restore_oasis_state) -> None:
        real_version = importlib.metadata.version

        def _fake_version(name: str) -> str:
            if name == "camel-oasis":
                return "0.2.4"
            return real_version(name)

        monkeypatch.setattr(importlib.metadata, "version", _fake_version)
        # ``app.utils.logger.setup_logger`` konfiguriert den Parent-Logger
        # "agora" mit ``propagate = False`` (Doppel-Ausgabe-Schutz), damit
        # Records vom Root-Logger (an dem caplog per Default lauscht) nicht
        # erreichbar sind. Handler direkt am emittierenden Logger andocken.
        with caplog.at_level("WARNING", logger="agora._sim_common"):
            result = sc.install_reddit_nested_comments_patch()
        assert result is False
        assert any(
            "erwartet camel-oasis==0.2.5" in record.getMessage()
            and "0.2.4" in record.getMessage()
            for record in caplog.records
        )
        # Bei falscher Version darf die OASIS-Klasse unveraendert bleiben.
        assert not getattr(_oasis_db.create_db, "_agora_nested_comments_applied", False)

    def test_correct_version_returns_true(self, _restore_oasis_state) -> None:
        assert importlib.metadata.version("camel-oasis") == "0.2.5"
        result = sc.install_reddit_nested_comments_patch()
        assert result is True


class TestIdempotenz:
    """Der Patch darf nur einmal gewrapped werden, auch bei Mehrfachaufruf."""

    def test_second_call_does_not_rewrap(self, _restore_oasis_state) -> None:
        first = sc.install_reddit_nested_comments_patch()
        patched_create_db = _oasis_db.create_db
        patched_create_comment = _oasis_platform.Platform.create_comment

        second = sc.install_reddit_nested_comments_patch()

        assert first is True
        assert second is True
        assert _oasis_db.create_db is patched_create_db
        assert _oasis_platform.Platform.create_comment is patched_create_comment


class TestAlterResumeSicher:
    """(b) Schema-Patch: ALTER TABLE ADD COLUMN nur wenn die Spalte fehlt."""

    def test_fresh_db_gets_column(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        db_path = tmp_path / "fresh.db"
        conn, cursor = _oasis_db.create_db(str(db_path))
        conn.close()
        assert "parent_comment_id" in _comment_columns(db_path)

    def test_resume_on_db_without_column_adds_it(self, tmp_path, _restore_oasis_state) -> None:
        # Erst mit der UNGEPATCHTEN create_db eine "alte" DB ohne die Spalte
        # anlegen (simuliert einen Lauf, der vor Slice S5 gestartet wurde).
        db_path = tmp_path / "resume.db"
        conn, _cursor = _oasis_db.create_db(str(db_path))
        conn.close()
        assert "parent_comment_id" not in _comment_columns(db_path)

        # Patch installieren und create_db erneut auf derselben Datei aufrufen
        # (Resume-Pfad: OASIS ruft create_db beim (Wieder-)Start erneut auf).
        sc.install_reddit_nested_comments_patch()
        conn2, _cursor2 = _oasis_db.create_db(str(db_path))
        conn2.close()
        assert "parent_comment_id" in _comment_columns(db_path)

    def test_resume_on_db_with_column_does_not_error(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        db_path = tmp_path / "already_patched.db"
        conn, _cursor = _oasis_db.create_db(str(db_path))
        conn.close()
        assert "parent_comment_id" in _comment_columns(db_path)

        # Zweiter Aufruf auf einer DB, die die Spalte bereits hat, darf kein
        # "duplicate column name" werfen.
        conn2, _cursor2 = _oasis_db.create_db(str(db_path))
        conn2.close()
        assert "parent_comment_id" in _comment_columns(db_path)


def _make_platform(tmp_path: Path, name: str) -> "_oasis_platform.Platform":
    db_path = tmp_path / name
    return _oasis_platform.Platform(str(db_path), channel=Channel())


def _insert_user_and_posts(platform) -> dict[str, int]:
    cursor = platform.db_cursor
    cursor.execute(
        "INSERT INTO user (user_id, agent_id, user_name, name) VALUES (1, 1, 'u1', 'User Eins')"
    )
    cursor.execute("INSERT INTO post (post_id, user_id, content) VALUES (1, 1, 'Post A')")
    cursor.execute("INSERT INTO post (post_id, user_id, content) VALUES (2, 1, 'Post B')")
    platform.db.commit()
    return {"post_a": 1, "post_b": 2}


@pytest.mark.asyncio
class TestPlatformCreateComment:
    """(c) Platform.create_comment: 2-/3-Tupel, Parent-Validierung."""

    async def test_no_parent_succeeds_and_parent_is_null(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        platform = _make_platform(tmp_path, "no_parent.db")
        ids = _insert_user_and_posts(platform)

        result = await platform.create_comment(1, (ids["post_a"], "Top-Level"))

        assert result["success"] is True
        cursor = platform.db_cursor
        cursor.execute(
            "SELECT parent_comment_id FROM comment WHERE comment_id = ?",
            (result["comment_id"],),
        )
        assert cursor.fetchone()[0] is None

    async def test_valid_parent_on_same_post_succeeds(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        platform = _make_platform(tmp_path, "valid_parent.db")
        ids = _insert_user_and_posts(platform)

        parent = await platform.create_comment(1, (ids["post_a"], "Elternkommentar"))
        reply = await platform.create_comment(
            1, (ids["post_a"], "Antwort", parent["comment_id"])
        )

        assert reply["success"] is True
        cursor = platform.db_cursor
        cursor.execute(
            "SELECT parent_comment_id FROM comment WHERE comment_id = ?",
            (reply["comment_id"],),
        )
        assert cursor.fetchone()[0] == parent["comment_id"]

    async def test_parent_belongs_to_foreign_post_fails(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        platform = _make_platform(tmp_path, "foreign_post.db")
        ids = _insert_user_and_posts(platform)

        comment_on_b = await platform.create_comment(1, (ids["post_b"], "Kommentar auf B"))
        # parent_comment_id gehoert zu Post B, aber wir kommentieren auf Post A.
        result = await platform.create_comment(
            1, (ids["post_a"], "Falscher Strang", comment_on_b["comment_id"])
        )

        assert result["success"] is False
        assert "error" in result

    async def test_nonexistent_parent_fails(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        platform = _make_platform(tmp_path, "missing_parent.db")
        ids = _insert_user_and_posts(platform)

        result = await platform.create_comment(1, (ids["post_a"], "Antwort", 999_999))

        assert result["success"] is False
        assert "error" in result


class TestAddCommentsToPostsParentField:
    """(e) PlatformUtils._add_comments_to_posts liefert parent_comment_id."""

    @pytest.mark.asyncio
    async def test_comments_carry_parent_comment_id(self, tmp_path, _restore_oasis_state) -> None:
        sc.install_reddit_nested_comments_patch()
        platform = _make_platform(tmp_path, "add_comments.db")
        ids = _insert_user_and_posts(platform)

        parent = await platform.create_comment(1, (ids["post_a"], "Elternkommentar"))
        reply = await platform.create_comment(
            1, (ids["post_a"], "Antwort", parent["comment_id"])
        )

        cursor = platform.db_cursor
        cursor.execute(
            "SELECT post_id, user_id, original_post_id, content, quote_content, "
            "created_at, num_likes, num_dislikes, num_shares FROM post WHERE post_id = ?",
            (ids["post_a"],),
        )
        posts_results = cursor.fetchall()

        posts = platform.pl_utils._add_comments_to_posts(posts_results)

        assert len(posts) == 1
        comments_by_id = {c["comment_id"]: c for c in posts[0]["comments"]}
        assert comments_by_id[parent["comment_id"]]["parent_comment_id"] is None
        assert comments_by_id[reply["comment_id"]]["parent_comment_id"] == parent["comment_id"]


class TestSocialActionToolSchema:
    """(d) SocialAction.create_comment: CAMEL-Tool-Schema kennt parent_comment_id."""

    def test_openai_tool_schema_contains_parent_comment_id(self, _restore_oasis_state) -> None:
        from camel.toolkits import FunctionTool

        sc.install_reddit_nested_comments_patch()
        social_action = _oasis_aa.SocialAction(agent_id=1, channel=Channel())
        schema = FunctionTool(social_action.create_comment).get_openai_tool_schema()

        properties = schema["function"]["parameters"]["properties"]
        assert "parent_comment_id" in properties
        assert schema["function"]["name"] == "create_comment"
