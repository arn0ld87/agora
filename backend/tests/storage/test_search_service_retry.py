"""Tests für _run_with_retry-Helper in SearchService (Fix 2, execute_read-Pfad).

Nach Migration zu session.execute_read übernimmt der Neo4j-Driver das
transiente Retry intern. Die Tests verifizieren:
  - Error-Klassifikation (IndexNotFound, transient, generic)
  - Warning-Wording (Substrings)
  - Happy-Path (execute_read wird genau einmal aufgerufen)
  - Transient-Exception nach execute_read → []

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


def _fake_node_record(uuid="x", name="y", score=0.9):
    """Baut einen Neo4j-Record-Fake, der dict()-kompatibel ist (node-Variante)."""
    node = {"uuid": uuid, "name": name}
    rec = MagicMock()
    rec.__getitem__ = MagicMock(side_effect=lambda key: node if key == "n" else score)
    return rec


# ---------------------------------------------------------------------------
# Test 1: ServiceUnavailable nach execute_read → [] + Warning mit 'transient'
#
# Der Driver-interne Retry ist über Mock-Session nicht simulierbar.
# Wir testen stattdessen, dass eine von execute_read propagierte
# ServiceUnavailable korrekt abgefangen und als [] zurückgegeben wird.
# ---------------------------------------------------------------------------


def test_vector_search_retries_on_service_unavailable(svc):
    """Wenn session.execute_read ServiceUnavailable wirft (Driver hat aufgegeben),
    gibt _run_node_vector_search [] zurück und loggt ein Warning mit 'transient'.
    """
    session = MagicMock()
    session.execute_read.side_effect = ServiceUnavailable("boom")

    with patch("app.storage.search_service.logger") as mock_logger:
        results = svc._run_node_vector_search(session, "g1", [0.1] * 1536, 5)

    assert results == []
    assert session.execute_read.call_count == 1
    assert mock_logger.warning.called
    all_args = [str(a) for c in mock_logger.warning.call_args_list for a in c.args]
    combined = " ".join(all_args).lower()
    assert "transient" in combined, (
        f"Warning-Args sollen 'transient' enthalten, erhalten: {combined!r}"
    )


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
    session.execute_read.side_effect = err

    with patch("app.storage.search_service.logger") as mock_logger:
        results = svc._run_node_vector_search(session, "g1", [0.1] * 1536, 5)

    assert results == []
    assert mock_logger.warning.called, "logger.warning muss aufgerufen worden sein"
    all_warning_args = [str(a) for c in mock_logger.warning.call_args_list for a in c.args]
    combined = " ".join(all_warning_args)
    assert "IndexNotFound" in combined, (
        f"Warning-Args sollen 'IndexNotFound' enthalten, erhalten: {combined!r}"
    )
    assert "index may not exist yet" not in combined, (
        "Verbotenes Wording 'index may not exist yet' im Warning gefunden"
    )


# ---------------------------------------------------------------------------
# Test 3: TransientError nach execute_read → leere Liste + Warning mit 'transient'
# ---------------------------------------------------------------------------


def test_transient_error_returns_empty_after_exhausted_retries(svc):
    """TransientError von execute_read (Driver hat Retries erschöpft) → []
    und Warning enthält 'transient'.
    """
    session = MagicMock()
    session.execute_read.side_effect = TransientError("db overloaded")

    with patch("app.storage.search_service.logger") as mock_logger:
        results = svc._run_node_vector_search(session, "g1", [0.1] * 1536, 5)

    assert results == []
    assert mock_logger.warning.called, "logger.warning muss aufgerufen worden sein"
    all_warning_args = [str(a) for c in mock_logger.warning.call_args_list for a in c.args]
    combined = " ".join(all_warning_args).lower()
    assert "transient" in combined, (
        f"Warning-Args sollen 'transient' enthalten, erhalten: {combined!r}"
    )


# ---------------------------------------------------------------------------
# Test 4: Happy Path — execute_read wird genau 1× aufgerufen, tx.run liefert Records
# ---------------------------------------------------------------------------


def test_happy_path_single_session_run_call(svc):
    """_run_node_keyword_search ruft session.execute_read bei Erfolg exakt 1× auf.

    execute_read führt den Callback mit einem Mock-tx aus; tx.run liefert Records.
    """
    node = {"uuid": "abc", "name": "Testknoten"}
    rec = MagicMock()
    rec.__getitem__ = MagicMock(side_effect=lambda key: node if key == "n" else 0.8)

    mock_tx = MagicMock()
    mock_tx.run.return_value = iter([rec])

    session = MagicMock()
    # execute_read ruft den übergebenen Callback mit mock_tx auf
    session.execute_read.side_effect = lambda cb: list(cb(mock_tx))

    results = svc._run_node_keyword_search(session, "g1", "Testquery", 10)

    session.execute_read.assert_called_once()
    mock_tx.run.assert_called_once()
    assert isinstance(results, list)
