"""Regressionstest: kooperativer gevent-Pool statt ThreadPoolExecutor in
``GraphBuilderService.add_text_batches``.

Kontext: ``backend/wsgi.py`` ruft ``gevent.monkey.patch_all()`` auf — jeder
Socket im Prozess ist damit ein kooperativer gevent-Socket, gebunden an den
Hub des Threads, der ihn erzeugt hat. ``ThreadPoolExecutor`` verteilt die
Chunk-Verarbeitung aber auf echte OS-Threads, jeder mit eigenem gevent-Hub,
während die Neo4j-Connections aus dem prozessweiten Driver-Pool stammen und
damit potenziell einem fremden Hub gehören. Produktionsfolge (armserver):
"Failed to write data to connection" / "defunct connection", 1–2s
Retry-Backoff pro Chunk.

``oasis_profile_generator.py`` hat dasselbe Problem für die
Persona-Generierung bereits über ``gevent.pool.Pool`` statt
``ThreadPoolExecutor`` gelöst — dieser Test beweist dasselbe Muster für
``add_text_batches``.

Abgedeckte Szenarien:
  1. Gepatchtes ``socket`` (gevent erkannt) → kooperativer Pool-Pfad,
     ``ThreadPoolExecutor`` wird NICHT verwendet.
  2. Kein gevent (socket nicht gepatcht) → ``ThreadPoolExecutor``-Pfad
     bleibt unverändert, ``gevent.pool.Pool`` wird NICHT instanziert.
  3. Beide Pfade: Ergebnisreihenfolge ist indexstabil (Position i gehört zu
     Chunk i), unabhängig von der Fertigstellungsreihenfolge.
  4. Beide Pfade: ``progress_callback`` läuft für jeden Chunk genau einmal,
     ``completed`` steigt monoton.
  5. Beide Pfade: ein Fehler in einem Chunk propagiert nach außen (kein
     stilles Verschlucken).
"""

from __future__ import annotations

import sys
import time
from unittest.mock import MagicMock

import pytest

from app.services.graph_builder import GraphBuilderService


class _FakeStorage:
    """Minimaler ``storage.add_text``-Stub.

    ``sleep_map`` erlaubt es, Chunks bewusst außer der Reihe fertigzustellen
    (ThreadPoolExecutor-Pfad) — damit die Index-Stabilität nicht zufällig
    durch eine ohnehin sequenzielle Verarbeitung „bewiesen“ wird.
    """

    def __init__(self, *, fail_chunk: str | None = None, sleep_map: dict | None = None):
        self.calls: list[str] = []
        self._fail_chunk = fail_chunk
        self._sleep_map = sleep_map or {}

    def add_text(self, graph_id, chunk, **kwargs):
        self.calls.append(chunk)
        delay = self._sleep_map.get(chunk)
        if delay:
            time.sleep(delay)
        if chunk == self._fail_chunk:
            raise RuntimeError(f"neo4j hiccup on {chunk}")
        return f"episode-{chunk}"


class _FakeGeventPool:
    """Minimaler ``gevent.pool.Pool``-Stub.

    Liefert Ergebnisse absichtlich in umgekehrter Submission-Reihenfolge, um
    zu beweisen, dass ``episode_uuids[idx]`` unabhängig von der
    Fertigstellungsreihenfolge korrekt indiziert wird — genau wie
    ``as_completed`` im Thread-Pfad keine Submission-Reihenfolge garantiert.
    """

    def __init__(self, size):
        self.size = size
        self.killed = False

    def imap_unordered(self, func, iterable):
        for item in reversed(list(iterable)):
            yield func(item)

    def join(self):
        pass

    def kill(self):
        self.killed = True


def _install_gevent_mock(monkeypatch, *, socket_patched: bool):
    """Installiert ``sys.modules["gevent"/"gevent.pool"/"gevent.monkey"]``.

    Spiegelt exakt das Mocking-Muster aus
    ``tests/test_gevent_fork.py::_build_mock_monkey`` — inklusive der
    Regression, dass ``gevent.monkey`` NUR ``is_module_patched`` kennt
    (die alte ``is_patched()``-API existiert seit gevent 23.x nicht mehr).
    """

    class MockGeventMonkey:
        def is_module_patched(self, name):
            return socket_patched and name == "socket"

    gevent_mock = MagicMock()
    gevent_mock.monkey = MockGeventMonkey()

    mock_pool_mod = MagicMock()
    mock_pool_mod.Pool.side_effect = _FakeGeventPool

    monkeypatch.setitem(sys.modules, "gevent", gevent_mock)
    monkeypatch.setitem(sys.modules, "gevent.pool", mock_pool_mod)
    monkeypatch.setitem(sys.modules, "gevent.monkey", MockGeventMonkey())
    return mock_pool_mod


def test_add_text_batches_uses_gevent_pool_when_socket_patched(monkeypatch):
    """Gepatchtes socket → kooperativer Pool-Pfad, kein ThreadPoolExecutor."""
    mock_pool_mod = _install_gevent_mock(monkeypatch, socket_patched=True)

    import app.services.graph_builder as gb_module

    def _fail_if_used(*_args, **_kwargs):
        raise AssertionError("ThreadPoolExecutor darf im gevent-Pfad nicht laufen")

    monkeypatch.setattr(gb_module, "ThreadPoolExecutor", _fail_if_used)

    storage = _FakeStorage()
    service = GraphBuilderService(storage=storage)

    progress_calls: list[tuple] = []

    def progress_callback(msg, frac, completed, total):
        progress_calls.append((msg, frac, completed, total))

    result = service.add_text_batches(
        "graph-x", ["c1", "c2", "c3"], batch_size=3, progress_callback=progress_callback
    )

    # Indexstabil: c3 wird zuerst fertig (reversed imap_unordered), landet
    # aber trotzdem an Position 2.
    assert result == ["episode-c1", "episode-c2", "episode-c3"]
    assert len(progress_calls) == 3
    assert [c[2] for c in progress_calls] == [1, 2, 3], "completed muss monoton steigen"
    assert [c[3] for c in progress_calls] == [3, 3, 3]
    mock_pool_mod.Pool.assert_called_once()


def test_add_text_batches_falls_back_to_threadpool_without_gevent(monkeypatch):
    """Kein gevent (socket nicht gepatcht) → ThreadPoolExecutor-Pfad unverändert."""
    mock_pool_mod = _install_gevent_mock(monkeypatch, socket_patched=False)

    # Bewusst außer der Reihe fertig: c1 am langsamsten, c3 am schnellsten.
    storage = _FakeStorage(sleep_map={"c1": 0.06, "c2": 0.03, "c3": 0.0})
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
    mock_pool_mod.Pool.assert_not_called()


def test_add_text_batches_gevent_pool_propagates_chunk_failure(monkeypatch):
    """Ein Chunk-Fehler muss im gevent-Pfad nach außen durchschlagen, nicht
    still verschluckt werden."""
    _install_gevent_mock(monkeypatch, socket_patched=True)

    storage = _FakeStorage(fail_chunk="c2")
    service = GraphBuilderService(storage=storage)

    progress_calls: list[tuple] = []

    def progress_callback(msg, frac, completed, total):
        progress_calls.append((msg, frac, completed, total))

    with pytest.raises(RuntimeError, match="neo4j hiccup on c2"):
        service.add_text_batches(
            "graph-x", ["c1", "c2", "c3"], batch_size=3, progress_callback=progress_callback
        )

    # Reversed Fertigstellungsreihenfolge: c3 zuerst (Erfolg, progress=1),
    # dann c2 (Fehler) — propagiert sofort, c1 wird nie erreicht.
    assert len(progress_calls) == 1
    assert progress_calls[0][2] == 1
    assert storage.calls == ["c3", "c2"]


def test_add_text_batches_threadpool_propagates_chunk_failure(monkeypatch):
    """Baseline (unverändert): ein Chunk-Fehler propagiert auch im
    ThreadPoolExecutor-Pfad nach außen."""
    _install_gevent_mock(monkeypatch, socket_patched=False)

    storage = _FakeStorage(fail_chunk="c2")
    service = GraphBuilderService(storage=storage)

    with pytest.raises(RuntimeError, match="neo4j hiccup on c2"):
        service.add_text_batches("graph-x", ["c1", "c2", "c3"], batch_size=3)
