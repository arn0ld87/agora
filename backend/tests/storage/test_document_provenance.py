"""Dokument-Provenance auf dem Episode-Knoten (Issue #1152 Slice 1, Teil B).

ADR-0013 §3 ist hart: bestehende Graphen ohne ``document_id``/``chunk_id``
müssen unverändert funktionieren — kein Schema-Zwang, keine Migration, kein
Backfill. Diese Datei prüft deshalb beide Richtungen an der echten
``Neo4jWriteMixin``-Persistenz (nur der Driver/Session ist gemockt, nicht die
Cypher-Konstruktion selbst):

1. Ist eine Dokument-Provenance bekannt, landet sie als Property auf dem
   ``MERGE (ep:Episode {uuid}) ON CREATE SET ...``-Aufruf.
2. Ist sie unbekannt (Altprojekt ohne Manifest-Sidecar), bleiben die
   Parameter ``None`` — Neo4j legt weder für ``null``-wertige
   Map-Properties noch für eine ``SET``-Zuweisung von ``null`` eine
   Property an, der Knoten bleibt also wie bisher.
3. ``Neo4jWriteMixin.add_text`` reicht ``document_id``/``chunk_id``
   unverändert an ``_persist_episode`` durch.
"""

from __future__ import annotations

from unittest.mock import MagicMock


class _CypherCapture:
    """Captures (query, params) tuples from tx.run() calls."""

    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def make_tx(self):
        tx = MagicMock()
        tx.run.side_effect = self._capture
        return tx

    def _capture(self, query, **params):
        self.calls.append((query, params))
        record = MagicMock()
        record.__getitem__ = lambda self, key: "uuid-captured"
        result = MagicMock()
        result.single.return_value = record
        return result

    @property
    def episode_creates(self):
        # Seit dem Retry-Idempotenz-Fix lautet das Statement
        # ``MERGE (ep:Episode {uuid}) ON CREATE SET ...`` statt ``CREATE``.
        # Gematcht wird deshalb auf den Knoten, nicht auf das Verb.
        return [(q, p) for q, p in self.calls if "(ep:Episode" in q]


def _capture_persist_episode_cypher(*, document_id=None, chunk_id=None) -> _CypherCapture:
    """Run ``_persist_episode`` and return the captured Cypher calls.

    Mirrors the harness in ``tests/storage/test_entity_dedupe_typed.py``:
    only ``_get_session``/``_call_with_retry`` are replaced, the Cypher
    construction inside ``_persist_episode`` runs unmodified.
    """
    from app.storage.neo4j_write import Neo4jWriteMixin

    capture = _CypherCapture()

    mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
    mixin._ontology_mutation_service = None  # type: ignore[attr-defined]

    tx = capture.make_tx()

    def fake_call_with_retry(execute_write_fn_or_inner, inner_fn=None, *args, **kwargs):
        if inner_fn is not None:
            result = inner_fn(tx)
        else:
            result = execute_write_fn_or_inner(tx)
        record = MagicMock()
        record.__getitem__ = lambda self, key: "uuid-captured"
        return result if result is not None else "uuid-captured"

    mixin._call_with_retry = fake_call_with_retry  # type: ignore[attr-defined]

    mock_session = MagicMock()
    session_ctx = MagicMock()
    session_ctx.__enter__ = MagicMock(return_value=mock_session)
    session_ctx.__exit__ = MagicMock(return_value=False)
    mixin._get_session = MagicMock(return_value=session_ctx)  # type: ignore[attr-defined]

    Neo4jWriteMixin._persist_episode(
        mixin,
        graph_id="g1",
        episode_id="ep-001",
        text="test text",
        now="2026-01-01T00:00:00+00:00",
        entities=[],
        relations=[],
        entity_embeddings=[],
        relation_embeddings=[],
        round_num=None,
        document_id=document_id,
        chunk_id=chunk_id,
    )

    return capture


class TestEpisodeDocumentProvenance:
    def test_chunk_with_document_provenance_lands_on_episode_node(self):
        """Bekannte Dokument-Provenance landet als Property auf dem Episode-Knoten."""
        capture = _capture_persist_episode_cypher(document_id="report", chunk_id=3)

        creates = capture.episode_creates
        assert len(creates) == 1, "Genau ein (ep:Episode ...)-Aufruf erwartet"
        _, params = creates[0]

        assert params["document_id"] == "report"
        assert params["chunk_id"] == 3

    def test_chunk_without_manifest_writes_episode_without_provenance_properties(self):
        """Ohne Manifest (Altprojekt) bleiben die Parameter None — kein Fehler.

        Neo4j legt für eine ``SET``-Zuweisung von null keine Property an;
        der gemockte Cypher-Call selbst darf trotzdem ohne Exception
        durchlaufen und muss die Parameter explizit als None tragen.
        """
        capture = _capture_persist_episode_cypher(document_id=None, chunk_id=None)

        creates = capture.episode_creates
        assert len(creates) == 1
        _, params = creates[0]

        assert params["document_id"] is None
        assert params["chunk_id"] is None


class TestAddTextForwardsDocumentProvenance:
    def _mixin_with_persist_spy(self) -> MagicMock:
        from app.storage.neo4j_write import Neo4jWriteMixin

        mixin = object.__new__(Neo4jWriteMixin)  # type: ignore[arg-type]
        mixin._ontology_mutation_service = None  # type: ignore[attr-defined]
        mixin._embedding = MagicMock(name="Embedding")  # type: ignore[attr-defined]
        mixin._embedding.embed_batch.return_value = []

        ner = MagicMock(name="NER")
        ner.extract.return_value = {"entities": [], "relations": []}
        mixin._ner = ner  # type: ignore[attr-defined]
        mixin.get_ontology = MagicMock(return_value={})  # type: ignore[attr-defined]
        mixin._persist_episode = MagicMock()  # type: ignore[attr-defined]
        return mixin

    def test_add_text_forwards_document_id_and_chunk_id(self):
        from app.storage.neo4j_write import Neo4jWriteMixin

        mixin = self._mixin_with_persist_spy()

        Neo4jWriteMixin.add_text(
            mixin, "graph-1", "Text.", document_id="report-2", chunk_id=5
        )

        mixin._persist_episode.assert_called_once()
        _, kwargs = mixin._persist_episode.call_args
        assert kwargs["document_id"] == "report-2"
        assert kwargs["chunk_id"] == 5

    def test_add_text_without_document_provenance_defaults_to_none(self):
        """Rückwärtskompatibel: Aufrufer ohne Provenance-Angabe bleiben unverändert."""
        from app.storage.neo4j_write import Neo4jWriteMixin

        mixin = self._mixin_with_persist_spy()

        Neo4jWriteMixin.add_text(mixin, "graph-1", "Text.")

        mixin._persist_episode.assert_called_once()
        _, kwargs = mixin._persist_episode.call_args
        assert kwargs["document_id"] is None
        assert kwargs["chunk_id"] is None


class TestGetEpisodeProvenance:
    """Lesepfad (Etappe 2): ein UNWIND-Lookup je Suche, keine Platzhalter."""

    def _read_mixin(self, records):
        from app.storage.neo4j_read import Neo4jReadMixin

        capture: dict = {}

        def fake_call_with_retry(execute_read_fn, inner_fn=None, *args, **kwargs):
            tx = MagicMock()

            def _run(query, **params):
                capture["query"] = query
                capture["params"] = params
                return records

            tx.run.side_effect = _run
            target = inner_fn if inner_fn is not None else execute_read_fn
            return target(tx)

        mixin = object.__new__(Neo4jReadMixin)  # type: ignore[arg-type]
        mixin._call_with_retry = fake_call_with_retry  # type: ignore[attr-defined]

        session_ctx = MagicMock()
        session_ctx.__enter__ = MagicMock(return_value=MagicMock())
        session_ctx.__exit__ = MagicMock(return_value=False)
        mixin._get_session = MagicMock(return_value=session_ctx)  # type: ignore[attr-defined]
        return mixin, capture

    def test_returns_document_and_chunk_per_episode(self):
        from app.storage.neo4j_read import Neo4jReadMixin

        records = [
            {"uuid": "ep-1", "document_id": "interview-nord", "chunk_id": 7},
        ]
        mixin, capture = self._read_mixin(records)

        result = Neo4jReadMixin.get_episode_provenance(mixin, ["ep-1", "ep-1"])

        assert result == {
            "ep-1": {"document_id": "interview-nord", "chunk_id": 7}
        }
        # Dedupliziert: derselbe Parameter darf nicht zweimal im UNWIND landen.
        assert capture["params"]["ids"] == ["ep-1"]
        assert "e.document_id IS NOT NULL" in capture["query"]

    def test_empty_input_skips_the_query_entirely(self):
        from app.storage.neo4j_read import Neo4jReadMixin

        mixin, capture = self._read_mixin([])

        assert Neo4jReadMixin.get_episode_provenance(mixin, []) == {}
        assert Neo4jReadMixin.get_episode_provenance(mixin, ["", None]) == {}
        assert capture == {}
