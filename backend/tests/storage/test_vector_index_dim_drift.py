"""
Tests for Vector-Index Dimension-Drift guard (Issue #263).

Strategy: instantiate Neo4jStorage via ``object.__new__`` (same pattern as
test_neo4j_resilience.py) to bypass the real driver and connectivity check,
then inject a mock session and call ``_ensure_vector_index_dim`` /
``_ensure_schema`` directly.

Scenarios:
  1. No index exists         → CREATE runs, no DROP.
  2. Index dim mismatch      → DROP + CREATE runs.
  3. Index dim matches       → no DROP, CREATE still runs (IF NOT EXISTS no-op).
"""

from unittest.mock import MagicMock, patch

from app.storage.neo4j_storage import Neo4jStorage
from app.config import Config


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_storage() -> Neo4jStorage:
    """Return a Neo4jStorage shell with no real driver."""
    inst = object.__new__(Neo4jStorage)
    inst._is_connected = True
    inst._last_error = None
    inst._last_success_ts = None
    inst._driver = MagicMock()
    return inst


def _mock_session_for_dim(existing_dim: int | None) -> MagicMock:
    """Return a mock session whose SHOW INDEXES query returns *existing_dim*.

    Pass ``None`` to simulate an absent index (``result.single()`` returns
    ``None``).
    """
    session = MagicMock()
    show_result = MagicMock()
    if existing_dim is None:
        show_result.single.return_value = None
    else:
        show_result.single.return_value = {"dim": existing_dim}
    session.run.return_value = show_result
    return session


# ---------------------------------------------------------------------------
# Unit tests for _ensure_vector_index_dim
# ---------------------------------------------------------------------------


class TestEnsureVectorIndexDim:
    """Low-level tests for the private helper method."""

    def test_no_index_no_drop(self):
        """Szenario 1: Index existiert nicht → kein DROP."""
        storage = _make_storage()
        session = _mock_session_for_dim(None)

        storage._ensure_vector_index_dim(session, "entity_embedding", 1536)

        # session.run was called exactly once (the SHOW INDEXES query).
        # No DROP should have been issued.
        assert session.run.call_count == 1
        for c in session.run.call_args_list:
            assert "DROP" not in str(c).upper()

    def test_dim_mismatch_triggers_drop(self):
        """Szenario 2: Gespeicherte Dim ≠ Config.VECTOR_DIM → DROP INDEX."""
        storage = _make_storage()
        session = _mock_session_for_dim(2560)

        storage._ensure_vector_index_dim(session, "entity_embedding", 1536)

        # Two calls: SHOW INDEXES + DROP INDEX
        assert session.run.call_count == 2
        drop_call = session.run.call_args_list[1]
        assert "DROP INDEX entity_embedding" in drop_call[0][0]

    def test_dim_match_no_drop(self):
        """Szenario 3: Gespeicherte Dim == Config.VECTOR_DIM → no-op."""
        storage = _make_storage()
        session = _mock_session_for_dim(1536)

        storage._ensure_vector_index_dim(session, "entity_embedding", 1536)

        # Only the SHOW INDEXES query, no DROP.
        assert session.run.call_count == 1
        for c in session.run.call_args_list:
            assert "DROP" not in str(c).upper()

    def test_warning_logged_on_mismatch(self):
        """Bei Dimension-Mismatch muss ein Warning-Log erscheinen.

        Die agora-Logger-Hierarchie hat ``propagate=False``, daher wird
        ``logger.warning`` direkt gemockt statt ``caplog`` zu nutzen.
        """
        storage = _make_storage()
        session = _mock_session_for_dim(2560)

        with patch("app.storage.neo4j_storage.logger") as mock_logger:
            storage._ensure_vector_index_dim(session, "fact_embedding", 1536)

        mock_logger.warning.assert_called_once()
        args = mock_logger.warning.call_args[0]
        formatted = args[0] % args[1:]
        assert "fact_embedding" in formatted
        assert "2560" in formatted

    def test_fact_embedding_drop(self):
        """Szenario 2 gilt auch für fact_embedding."""
        storage = _make_storage()
        session = _mock_session_for_dim(768)

        storage._ensure_vector_index_dim(session, "fact_embedding", 1536)

        assert session.run.call_count == 2
        drop_call = session.run.call_args_list[1]
        assert "DROP INDEX fact_embedding" in drop_call[0][0]


# ---------------------------------------------------------------------------
# Integration-level tests for _ensure_schema (mock driver)
# ---------------------------------------------------------------------------


class TestEnsureSchemaVectorIndexGuard:
    """_ensure_schema muss die Dim-Guard-Methode vor jedem CREATE VECTOR INDEX
    aufrufen und bei Mismatch den Drop durchführen."""

    def _make_storage_with_session(self, session: MagicMock) -> Neo4jStorage:
        storage = _make_storage()
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=session)
        ctx.__exit__ = MagicMock(return_value=False)
        storage._driver.session.return_value = ctx
        return storage

    def test_schema_no_drop_when_no_index(self):
        """Szenario 1 via _ensure_schema: kein Index vorhanden → normaler CREATE."""
        # session.run: first two calls for SHOW INDEXES return "no row",
        # remaining calls are the actual schema CREATE/fulltext queries.
        session = MagicMock()
        no_index_result = MagicMock()
        no_index_result.single.return_value = None
        # Make all session.run calls return the "no index" result by default
        session.run.return_value = no_index_result

        storage = self._make_storage_with_session(session)

        with patch.object(Config, "VECTOR_DIM", 1536):
            storage._ensure_schema()

        call_args = [str(c) for c in session.run.call_args_list]
        drop_calls = [a for a in call_args if "DROP" in a.upper()]
        assert drop_calls == [], "Kein DROP erwartet wenn kein Index existiert"

    def test_schema_drops_mismatched_entity_index(self):
        """Szenario 2: entity_embedding hat dim=2560, Config.VECTOR_DIM=1536 → DROP."""
        session = MagicMock()

        def run_side_effect(query, **kwargs):
            result = MagicMock()
            # First SHOW INDEXES (entity_embedding) → dim=2560
            if "SHOW INDEXES" in query and kwargs.get("name") == "entity_embedding":
                result.single.return_value = {"dim": 2560}
            # Second SHOW INDEXES (fact_embedding) → absent
            elif "SHOW INDEXES" in query and kwargs.get("name") == "fact_embedding":
                result.single.return_value = None
            else:
                result.single.return_value = None
            return result

        session.run.side_effect = run_side_effect

        storage = self._make_storage_with_session(session)

        with patch.object(Config, "VECTOR_DIM", 1536):
            storage._ensure_schema()

        call_args = [str(c) for c in session.run.call_args_list]
        drop_calls = [a for a in call_args if "DROP INDEX entity_embedding" in a]
        assert len(drop_calls) == 1, "Genau ein DROP INDEX entity_embedding erwartet"
        # fact_embedding must not be dropped (it was absent)
        fact_drop_calls = [a for a in call_args if "DROP INDEX fact_embedding" in a]
        assert fact_drop_calls == []

    def test_schema_no_drop_when_dim_matches(self):
        """Szenario 3: entity_embedding + fact_embedding dim=1536, Config=1536 → no DROP."""
        session = MagicMock()

        def run_side_effect(query, **kwargs):
            result = MagicMock()
            if "SHOW INDEXES" in query:
                result.single.return_value = {"dim": 1536}
            else:
                result.single.return_value = None
            return result

        session.run.side_effect = run_side_effect

        storage = self._make_storage_with_session(session)

        with patch.object(Config, "VECTOR_DIM", 1536):
            storage._ensure_schema()

        call_args = [str(c) for c in session.run.call_args_list]
        drop_calls = [a for a in call_args if "DROP" in a.upper()]
        assert drop_calls == [], "Kein DROP erwartet wenn Dim übereinstimmt"
