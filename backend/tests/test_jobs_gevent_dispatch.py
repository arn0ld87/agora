"""Hintergrundjobs muessen unter gevent kooperativ laufen, nicht als OS-Thread.

``backend/wsgi.py`` ruft ``gevent.monkey.patch_all()``, bevor die App
importiert wird. Jeder Socket im Prozess ist danach ein kooperativer
gevent-Socket, gebunden an den Hub des Threads, der ihn erzeugt hat. Ein
echter OS-Thread bringt seinen eigenen Hub mit, greift aber auf Connections
aus prozessweiten Pools zu (Neo4j-Driver, HTTP-Sessions). Produktionsbild
vom 2026-09-06: ``Failed to write data to connection neo4j:7687``,
``Failed to read from defunct connection``, serverseitig ``Response write
failure``, und beim LLM-Call ``RemoteDisconnected``. Jeder betroffene Aufruf
zahlt Retry-Backoff, ohne dass etwas offensichtlich kaputt aussieht.

Die Tests halten fest, dass die Weiche greift und dass beide Zweige
dieselbe Fehlersemantik haben.
"""

from __future__ import annotations

import logging

import pytest

from app import jobs


class _Recorder:
    """Merkt sich, ob und womit der jeweilige Spawn-Weg gerufen wurde."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple, dict]] = []

    def __call__(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return self

    # gevent.spawn liefert ein Greenlet, threading.Thread eine Instanz mit
    # .start() — beide Rueckgaben werden vom Produktivcode ignoriert, der
    # Stub muss nur aufrufbar bleiben.
    def start(self) -> None:
        return None


@pytest.fixture
def _force_mode(monkeypatch: pytest.MonkeyPatch):
    """Erzwingt den Rueckgabewert von ``execution_mode`` ohne echtes Patching.

    ``gevent.monkey.patch_all()`` im Test aufzurufen haette globale, nicht
    zurueckdrehbare Seiteneffekte auf die gesamte Suite.
    """

    def _apply(mode: str) -> None:
        monkeypatch.setattr(jobs, "execution_mode", lambda: mode)

    return _apply


# ---------------------------------------------------------------------------
# execution_mode
# ---------------------------------------------------------------------------


class TestExecutionMode:
    def test_reports_gevent_when_socket_is_patched(self, monkeypatch):
        import gevent.monkey

        monkeypatch.setattr(gevent.monkey, "is_module_patched", lambda name: name == "socket")
        assert jobs.execution_mode() == "gevent"

    def test_reports_thread_when_socket_is_not_patched(self, monkeypatch):
        import gevent.monkey

        monkeypatch.setattr(gevent.monkey, "is_module_patched", lambda _name: False)
        assert jobs.execution_mode() == "thread"

    def test_falls_back_to_thread_without_gevent(self, monkeypatch):
        """Ohne gevent (CLI-Skripte, Tests) bleibt es beim Thread."""
        import builtins

        real_import = builtins.__import__

        def _no_gevent(name, *args, **kwargs):
            if name == "gevent" or name.startswith("gevent."):
                raise ImportError("no gevent")
            return real_import(name, *args, **kwargs)

        monkeypatch.setattr(builtins, "__import__", _no_gevent)
        assert jobs.execution_mode() == "thread"


# ---------------------------------------------------------------------------
# enqueue
# ---------------------------------------------------------------------------


class TestEnqueueDispatch:
    def test_gevent_mode_spawns_greenlet_not_thread(self, monkeypatch, _force_mode):
        import gevent
        import threading

        spawn = _Recorder()
        thread = _Recorder()
        monkeypatch.setattr(gevent, "spawn", spawn)
        monkeypatch.setattr(threading, "Thread", thread)
        _force_mode("gevent")

        job_id = jobs.enqueue("demo", lambda: None)

        assert job_id.startswith("job_")
        assert len(spawn.calls) == 1
        assert thread.calls == [], "unter gevent darf kein OS-Thread entstehen"

    def test_thread_mode_uses_thread_not_greenlet(self, monkeypatch, _force_mode):
        import gevent
        import threading

        spawn = _Recorder()
        thread = _Recorder()
        monkeypatch.setattr(gevent, "spawn", spawn)
        monkeypatch.setattr(threading, "Thread", thread)
        _force_mode("thread")

        jobs.enqueue("demo", lambda: None)

        assert len(thread.calls) == 1
        assert spawn.calls == []
        assert thread.calls[0][1]["daemon"] is True

    def test_log_names_the_execution_mode(self, monkeypatch, _force_mode, caplog):
        """``backend=thread`` allein hat in der Praxis verschleiert, dass ein
        OS-Thread unter gevent lief — der Modus muss in der Zeile stehen."""
        import gevent

        monkeypatch.setattr(gevent, "spawn", _Recorder())
        _force_mode("gevent")

        target_logger = logging.getLogger("agora.jobs")
        monkeypatch.setattr(target_logger, "propagate", True)
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        with caplog.at_level(logging.INFO, logger="agora.jobs"):
            jobs.enqueue("demo", lambda: None)

        messages = [r.getMessage() for r in caplog.records if "enqueued job" in r.getMessage()]
        assert len(messages) == 1
        assert "mode=gevent" in messages[0]


# ---------------------------------------------------------------------------
# Fehlersemantik: identisch in beiden Zweigen
# ---------------------------------------------------------------------------


class TestJobErrorHandling:
    @pytest.mark.parametrize("mode", ["gevent", "thread"])
    def test_target_exception_is_logged_not_raised(self, monkeypatch, _force_mode, caplog, mode):
        """Ein fehlschlagender Job darf den Aufrufer nie mitreissen."""
        import gevent
        import threading

        captured: list = []

        # Beide Spawn-Wege synchron ausfuehren, damit der Fehler im Test
        # ueberhaupt auftritt — sonst liefe er in einem echten Greenlet bzw.
        # Thread und der Assert griffe ins Leere.
        def _run_now(fn, *args, **kwargs):
            captured.append(fn)
            fn(*args, **kwargs)
            return _Recorder()

        class _ImmediateThread:
            def __init__(self, target=None, args=(), kwargs=None, daemon=None):
                self._target = target
                self._args = args
                self._kwargs = kwargs or {}

            def start(self) -> None:
                captured.append(self._target)
                self._target(*self._args, **self._kwargs)

        monkeypatch.setattr(gevent, "spawn", _run_now)
        monkeypatch.setattr(threading, "Thread", _ImmediateThread)
        _force_mode(mode)

        def _boom() -> None:
            raise RuntimeError("job kaputt")

        target_logger = logging.getLogger("agora.jobs")
        monkeypatch.setattr(target_logger, "propagate", True)
        monkeypatch.setattr(logging.getLogger("agora"), "propagate", True)
        with caplog.at_level(logging.ERROR, logger="agora.jobs"):
            jobs.enqueue("demo", _boom)  # darf nicht werfen

        assert captured, "der Job wurde gar nicht ausgefuehrt"
        errors = [r.getMessage() for r in caplog.records if "job failed" in r.getMessage()]
        assert len(errors) == 1
        assert "job kaputt" in errors[0]


# ---------------------------------------------------------------------------
# spawn_background: derselbe Schalter fuer die nackten Thread-Aufrufer
# ---------------------------------------------------------------------------


class TestSpawnBackground:
    def test_gevent_mode_spawns_greenlet(self, monkeypatch, _force_mode):
        import gevent
        import threading

        spawn = _Recorder()
        thread = _Recorder()
        monkeypatch.setattr(gevent, "spawn", spawn)
        monkeypatch.setattr(threading, "Thread", thread)
        _force_mode("gevent")

        jobs.spawn_background(lambda: None)

        assert len(spawn.calls) == 1
        assert thread.calls == []

    def test_thread_mode_uses_daemon_thread(self, monkeypatch, _force_mode):
        import gevent
        import threading

        spawn = _Recorder()
        thread = _Recorder()
        monkeypatch.setattr(gevent, "spawn", spawn)
        monkeypatch.setattr(threading, "Thread", thread)
        _force_mode("thread")

        jobs.spawn_background(lambda: None)

        assert len(thread.calls) == 1
        assert spawn.calls == []
        assert thread.calls[0][1]["daemon"] is True

    def test_forwards_arguments(self, monkeypatch, _force_mode):
        import gevent

        spawn = _Recorder()
        monkeypatch.setattr(gevent, "spawn", spawn)
        _force_mode("gevent")

        marker = object()
        jobs.spawn_background(print, marker, sep="-")

        args, kwargs = spawn.calls[0]
        assert args[1] is marker
        assert kwargs == {"sep": "-"}


# ---------------------------------------------------------------------------
# Aufrufer duerfen nicht am Dispatch vorbei einen nackten Thread starten
# ---------------------------------------------------------------------------


def test_runs_api_has_no_bare_thread_dispatch():
    """Regressionsnetz: die drei Fire-and-forget-Starts in ``api/runs.py``
    liefen bis 2026-09-06 als nackte ``threading.Thread``-Aufrufe und damit
    unter gevent im falschen Hub."""
    from pathlib import Path

    source = Path(__file__).resolve().parents[1] / "app" / "api" / "runs.py"
    text = source.read_text(encoding="utf-8")
    assert "threading.Thread(" not in text
    assert "spawn_background(" in text
