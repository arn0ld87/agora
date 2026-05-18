"""Tests für _run_with_retry-Helper in SearchService (Fix 2).

RED-Phase: schlägt fehl, weil search_service.py noch keinen Retry-Wrapper
hat und die Warning-Wording-Prüfung gegen das alte "(index may not exist yet)"
greift.

Hinweis zu Logger-Patching: Der agora.search-Logger nutzt einen custom
Handler (get_logger), der nicht in caplog propagiert. Warning-Tests patchen
deshalb ``app.storage.search_service.logger.warning`` direkt.
"""
from unittest.mock import MagicMock, patch

import pytest
from neo4j.exceptions import ServiceUnavailable, TransientError, ClientError

from app.storage.search_service import SearchService


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def svc():
    """SearchService mit gemocktem EmbeddingService."""
    embedding = MagicMock()
    embedding.embed.return_value = [0.1] * 1536
    return SearchService(embedding, vector_weight=0.7, keyword_weight=0.3)


def _fake_record(uuid="x", name="y", score=0.9):
    """Baut einen Neo4j-Record-Fake, der dict()-kompatibel ist."""
    node = {"uuid": uuid, "name": name}
    rec = MagicMock()
    rec.__getitem__ = lambda self, key: node if key == "n" else score
    # __iter__ wird bei dict(record["n"]) nicht direkt gebraucht — node ist dict.
    rec.__getitem__ = MagicMock(side_effect=lambda key: node if key == "n" else score)
    return rec


def _fake_result(records):
    """Iterierbares Result-Objekt, das records zurückgibt."""
    result = MagicMock()
    result.__iter__ = MagicMock(return_value=iter(records))
    return result


# ---------------------------------------------------------------------------
# Test 1: Retry bei ServiceUnavailable (2× fail, dann Erfolg)
# ---------------------------------------------------------------------------


def test_vector_search_retries_on_service_unavailable(svc):
    """session.run wirft 2× ServiceUnavailable, dann liefert es ein gültiges Result.

    _run_node_vector_search muss 1 Element zurückgeben und session.run 3× aufgerufen haben.
    """
    record = _fake_record()
    success_result = _fake_result([record])

    session = MagicMock()
    session.run.side_effect = [
        ServiceUnavailable("boom"),
        ServiceUnavailable("boom again"),
        success_result,
    ]

    with patch("app.utils.retry.time.sleep"):
        results = svc._run_node_vector_search(session, "g1", [0.1] * 1536, 5)

    assert len(results) == 1
    assert session.run.call_count == 3


# ---------------------------------------------------------------------------
# Test 2: IndexNotFound → leere Liste + Warning ohne verbotenen Text
# ---------------------------------------------------------------------------


def test_index_not_found_warning_wording(svc):
    """ClientError mit IndexNotFound-Code liefert [] und das Warning enthält
    'IndexNotFound' aber NICHT den alten Text 'index may not exist yet'.
    """
    err = ClientError()
    err.code = "Neo.ClientError.Schema.IndexNotFound"

    session = MagicMock()
    session.run.side_effect = err

    with patch("app.storage.search_service.logger") as mock_logger:
        results = svc._run_node_vector_search(session, "g1", [0.1] * 1536, 5)

    assert results == []
    assert mock_logger.warning.called, "logger.warning muss aufgerufen worden sein"
    all_warning_args = [str(a) for call in mock_logger.warning.call_args_list for a in call.args]
    combined = " ".join(all_warning_args)
    assert "IndexNotFound" in combined, (
        f"Warning-Args sollen 'IndexNotFound' enthalten, erhalten: {combined!r}"
    )
    assert "index may not exist yet" not in combined, (
        "Verbotenes Wording 'index may not exist yet' im Warning gefunden"
    )


# ---------------------------------------------------------------------------
# Test 3: TransientError erschöpft → leere Liste + Warning mit 'transient'
# ---------------------------------------------------------------------------


def test_transient_error_returns_empty_after_exhausted_retries(svc):
    """TransientError (erschöpft) → [] und Warning enthält 'transient'."""
    session = MagicMock()
    session.run.side_effect = TransientError("db overloaded")

    with (
        patch("app.storage.search_service.logger") as mock_logger,
        patch("app.utils.retry.time.sleep"),  # kein echtes Warten in Tests
    ):
        results = svc._run_node_vector_search(session, "g1", [0.1] * 1536, 5)

    assert results == []
    assert mock_logger.warning.called, "logger.warning muss aufgerufen worden sein"
    all_warning_args = [str(a) for call in mock_logger.warning.call_args_list for a in call.args]
    combined = " ".join(all_warning_args).lower()
    assert "transient" in combined, (
        f"Warning-Args sollen 'transient' enthalten, erhalten: {combined!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: Happy Path — genau 1× session.run bei keyword search
# ---------------------------------------------------------------------------


def test_happy_path_single_session_run_call(svc):
    """_run_node_keyword_search ruft session.run bei Erfolg exakt 1× auf."""
    node = {"uuid": "abc", "name": "Testknoten"}
    rec = MagicMock()
    rec.__getitem__ = MagicMock(side_effect=lambda key: node if key == "n" else 0.8)
    success_result = _fake_result([rec])

    session = MagicMock()
    session.run.return_value = success_result

    results = svc._run_node_keyword_search(session, "g1", "Testquery", 10)

    session.run.assert_called_once()
    assert isinstance(results, list)
