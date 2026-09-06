"""Regressionstest: kooperatives gevent-Scheduling statt ThreadPoolExecutor
in ``GraphBuilderService.add_text_batches``.

Kontext: ``backend/wsgi.py`` ruft ``gevent.monkey.patch_all()`` auf — jeder
Socket im Prozess ist damit ein kooperativer gevent-Socket, gebunden an den
Hub des Threads, der ihn erzeugt hat. ``ThreadPoolExecutor`` verteilt die
Chunk-Verarbeitung aber auf echte OS-Threads, jeder mit eigenem gevent-Hub,
während die Neo4j-Connections aus dem prozessweiten Driver-Pool stammen und
damit potenziell einem fremden Hub gehören. Produktionsfolge (armserver):
"Failed to write data to connection" / "defunct connection", 1–2s
Retry-Backoff pro Chunk.

Die Produktionsimplementierung nutzt bewusst KEIN ``gevent.pool.Pool.
imap_unordered`` (erster Anlauf dieses Fixes) — nach Verlassen der
``imap_unordered``-Iteration gibt es keinen Zugriff mehr auf bereits
gestartete, aber noch laufende Greenlets. Das brauchen wir aber für den
Cancel-Pfad: bereits laufende Chunks müssen ihre Neo4j-Transaktion fertig
committen dürfen (Episode + Entities + Relations werden einzeln geschrieben —
ein hartes Kill mittendrin hinterließe einen inkonsistenten Graphen), und
ihre Episode-UUIDs müssen best effort nachgesammelt werden, exakt wie im
ThreadPoolExecutor-Pfad (Review-Finding PR #1371, Befund 5). Die
Produktionsimplementierung spawnt Greenlets deshalb manuell in einem
Sliding-Window (``{greenlet: idx}``, Gegenstück zum ``{future: idx}`` des
Thread-Pfads) und konsumiert sie über ``gevent.wait``/``gevent.joinall``.

Diese Tests laufen bewusst gegen ECHTES gevent (kein Mock von
``gevent.spawn``/``gevent.wait``/``gevent.joinall``) — nur die Erkennung
(``gevent.monkey.is_module_patched``) wird über ``monkeypatch`` erzwungen,
OHNE ``monkey.patch_all()`` aufzurufen (das hätte globale ssl-Seiteneffekte,
s. ``tests/test_gevent_fork.py``). So prüfen die Tests echtes kooperatives
Scheduling statt eines nachgebauten Mock-Verhaltens.

Abgedeckte Szenarien:
  1. Gepatchtes ``socket`` (gevent erkannt) → kooperativer Greenlet-Pfad,
     ``ThreadPoolExecutor`` wird NICHT verwendet.
  2. Kein gevent (socket nicht gepatcht) → ``ThreadPoolExecutor``-Pfad
     bleibt unverändert, ``gevent.spawn`` wird NICHT aufgerufen.
  3. Beide Pfade: Ergebnisreihenfolge ist indexstabil (Position i gehört zu
     Chunk i), unabhängig von der Fertigstellungsreihenfolge.
  4. Beide Pfade: ``progress_callback`` läuft für jeden Chunk genau einmal,
     ``completed`` steigt monoton.
  5. Beide Pfade: ein Fehler in einem Chunk propagiert nach außen (kein
     stilles Verschlucken).
  6. Gevent-Pfad, Cancel: ``GraphBuildCancelled`` fliegt, UUIDs bereits
     laufender Chunks sind enthalten, noch nicht gestartete Chunks werden
     nie verarbeitet (Nachbau des Thread-Pfad-Verhaltens aus
     ``test_graph_build_cancel.py``).
"""

from __future__ import annotations

import time
from unittest.mock import MagicMock

import gevent
import pytest
from gevent import monkey as gevent_monkey

from app.services.graph_builder import GraphBuildCancelled, GraphBuilderService
from app.services.sim.cancel_flag import clear_cancel, request_cancel


class _FakeStorage:
    """Minimaler ``storage.add_text``-Stub.

    ``sleep_map`` erlaubt es, Chunks bewusst außer der Reihe fertigzustellen
    — damit die Index-Stabilität nicht zufällig durch eine ohnehin
    sequenzielle Verarbeitung „bewiesen" wird. ``sleep_fn`` ist austauschbar:
    ``time.sleep`` für den Thread-Pfad (reale OS-Thread-Nebenläufigkeit),
    ``gevent.sleep`` für den gevent-Pfad (kooperativer Yield-Punkt, ohne den
    ein synchroner Fake-Call nie an den Hub abgibt).
    """

    def __init__(self, *, fail_chunk=None, sleep_map=None, sleep_fn=time.sleep, cancel_after=None, run_id=None):
        self.calls: list[str] = []
        self._fail_chunk = fail_chunk
        self._sleep_map = sleep_map or {}
        self._sleep_fn = sleep_fn
        self._cancel_after = cancel_after
        self._run_id = run_id

    def add_text(self, graph_id, chunk, **kwargs):
        self.calls.append(chunk)
        if self._cancel_after == chunk:
            request_cancel(self._run_id)
        delay = self._sleep_map.get(chunk)
        if delay:
            self._sleep_fn(delay)
        if chunk == self._fail_chunk:
            raise RuntimeError(f"neo4j hiccup on {chunk}")
        return f"episode-{chunk}"


def _force_gevent_detection(monkeypatch, *, patched: bool):
    """Erzwingt ``is_gevent`` ohne ``monkey.patch_all()`` aufzurufen.

    Ersetzt nur ``gevent.monkey.is_module_patched`` auf dem ECHTEN Modul —
    ``gevent.spawn``/``wait``/``joinall`` bleiben unangetastet und laufen im
    Test also mit echtem kooperativem Scheduling.
    """
    monkeypatch.setattr(
        gevent_monkey, "is_module_patched", lambda name: patched and name == "socket"
    )


def test_add_text_batches_uses_gevent_pool_when_socket_patched(monkeypatch):
    """Gepatchtes socket → kooperativer Greenlet-Pfad, kein ThreadPoolExecutor."""
    _force_gevent_detection(monkeypatch, patched=True)

    import app.services.graph_builder as gb_module

    def _fail_if_used(*_args, **_kwargs):
        raise AssertionError("ThreadPoolExecutor darf im gevent-Pfad nicht laufen")

    monkeypatch.setattr(gb_module, "ThreadPoolExecutor", _fail_if_used)
    spy_spawn = MagicMock(wraps=gevent.spawn)
    monkeypatch.setattr(gevent, "spawn", spy_spawn)

    # Bewusst außer der Reihe fertig: c1 am langsamsten, c3 am schnellsten.
    storage = _FakeStorage(sleep_map={"c1": 0.03, "c2": 0.015, "c3": 0.0}, sleep_fn=gevent.sleep)
    service = GraphBuilderService(storage=storage)

    progress_calls: list[tuple] = []

    def progress_callback(msg, frac, completed, total):
        progress_calls.append((msg, frac, completed, total))

    result = service.add_text_batches(
        "graph-x", ["c1", "c2", "c3"], batch_size=3, progress_callback=progress_callback
    )

    # Indexstabil trotz Fertigstellung in umgekehrter Reihenfolge.
    assert result == ["episode-c1", "episode-c2", "episode-c3"]
    assert len(progress_calls) == 3
    assert [c[2] for c in progress_calls] == [1, 2, 3], "completed muss monoton steigen"
    assert [c[3] for c in progress_calls] == [3, 3, 3]
    assert spy_spawn.call_count == 3


def test_add_text_batches_falls_back_to_threadpool_without_gevent(monkeypatch):
    """Kein gevent (socket nicht gepatcht) → ThreadPoolExecutor-Pfad unverändert."""
    _force_gevent_detection(monkeypatch, patched=False)
    spy_spawn = MagicMock(wraps=gevent.spawn)
    monkeypatch.setattr(gevent, "spawn", spy_spawn)

    # Bewusst außer der Reihe fertig: c1 am langsamsten, c3 am schnellsten.
    storage = _FakeStorage(sleep_map={"c1": 0.06, "c2": 0.03, "c3": 0.0}, sleep_fn=time.sleep)
    service = GraphBuilderService(storage=storage)

    progress_calls: list[tuple] = []

    def progress_callback(msg, frac, completed, total):
        progress_calls.append((msg, frac, completed, total))

    result = service.add_text_batches(
        "graph-x", ["c1", "c2", "c3"], batch_size=3, progress_callback=progress_callback
    )

    # Indexstabil trotz Fertigstellung in umgekehrter Reihenfolge.
    assert result == ["episode-c1", "episode-c2", "episode-c3"]
    assert len(progress_calls) == 3
    completed_values = [c[2] for c in progress_calls]
    assert completed_values == [1, 2, 3], "completed muss monoton steigen"
    spy_spawn.assert_not_called()


def test_add_text_batches_gevent_pool_propagates_chunk_failure(monkeypatch):
    """Ein Chunk-Fehler muss im gevent-Pfad nach außen durchschlagen, nicht
    still verschluckt werden."""
    _force_gevent_detection(monkeypatch, patched=True)

    storage = _FakeStorage(fail_chunk="c2", sleep_fn=gevent.sleep)
    service = GraphBuilderService(storage=storage)

    progress_calls: list[tuple] = []

    def progress_callback(msg, frac, completed, total):
        progress_calls.append((msg, frac, completed, total))

    with pytest.raises(RuntimeError, match="neo4j hiccup on c2"):
        service.add_text_batches(
            "graph-x", ["c1", "c2", "c3"], batch_size=3, progress_callback=progress_callback
        )

    # Alle drei Chunks wurden gestartet (max_workers default >= 3) — c2
    # scheitert, die Exception propagiert aus add_text_batches heraus.
    assert "c2" in storage.calls


def test_add_text_batches_threadpool_propagates_chunk_failure(monkeypatch):
    """Baseline (unverändert): ein Chunk-Fehler propagiert auch im
    ThreadPoolExecutor-Pfad nach außen."""
    _force_gevent_detection(monkeypatch, patched=False)

    storage = _FakeStorage(fail_chunk="c2")
    service = GraphBuilderService(storage=storage)

    with pytest.raises(RuntimeError, match="neo4j hiccup on c2"):
        service.add_text_batches("graph-x", ["c1", "c2", "c3"], batch_size=3)


def test_add_text_batches_gevent_pool_cancel_lets_running_chunks_finish(monkeypatch):
    """Cancel im gevent-Pfad: Nachbau von
    ``test_graph_build_cancel.py::test_add_text_batches_cancel_mid_loop_raises_with_partial_uuids``
    für den gevent-Zweig.

    ``GRAPH_PARALLEL_CHUNKS`` wird auf 2 gepatcht: das Sliding-Window startet
    dann nur c1+c2, c3/c4 bleiben in ``pending`` und werden — sofern der
    Abbruch greift — NIE gestartet. c1 löst den Cancel beim Fertigwerden
    aus; c2 läuft zu diesem Zeitpunkt noch (kooperativer Sleep) und muss
    trotzdem fertig committen und nachgesammelt werden, statt gekillt zu
    werden — das ist genau das Review-Finding aus PR #1371, Befund 5, hier
    für den gevent-Pfad reproduziert.
    """
    from app.config import Config

    _force_gevent_detection(monkeypatch, patched=True)
    monkeypatch.setattr(Config, "GRAPH_PARALLEL_CHUNKS", 2)

    spy_spawn = MagicMock(wraps=gevent.spawn)
    monkeypatch.setattr(gevent, "spawn", spy_spawn)

    run_id = "run_gevent_cancel_test"
    clear_cancel(run_id)
    try:
        storage = _FakeStorage(
            cancel_after="c1",
            sleep_map={"c2": 0.05},
            sleep_fn=gevent.sleep,
            run_id=run_id,
        )
        service = GraphBuilderService(storage=storage)

        with pytest.raises(GraphBuildCancelled) as excinfo:
            service.add_text_batches(
                "graph-x", ["c1", "c2", "c3", "c4"], batch_size=3, run_id=run_id
            )

        # c1 löste den Cancel aus, c2 lief zu dem Zeitpunkt noch — beide
        # UUIDs müssen trotzdem in der Exception stehen (Nachsammeln, keine
        # stille Untererfassung).
        assert excinfo.value.episode_uuids == ["episode-c1", "episode-c2"]

        # c3/c4 standen nur in "pending" und wurden nie gestartet.
        assert storage.calls == ["c1", "c2"]
        assert spy_spawn.call_count == 2, (
            "Noch nicht gestartete Chunks (c3, c4) dürfen nach dem Abbruch "
            "nicht mehr verarbeitet werden"
        )
    finally:
        clear_cancel(run_id)
