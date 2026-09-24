"""
Tests for backend/app/jobs/__init__.py — enqueue() stub.

Spec: jobs.enqueue() is the single point of change for background-job dispatch.
Today: threading.Thread(daemon=True). Future: RQ (Wave 2).

Ref: agora_code_review_2026-05-17.md §1.3
"""

import logging
import re
import threading
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def attach_caplog_to_agora_jobs(caplog):
    """
    setup_logger() sets propagate=False on agora.* loggers so pytest caplog
    (which hooks the root logger) misses records.  We attach caplog's handler
    directly to the agora.jobs logger for the duration of each test.
    """
    jobs_logger = logging.getLogger("agora.jobs")
    jobs_logger.addHandler(caplog.handler)
    orig_level = jobs_logger.level
    jobs_logger.setLevel(logging.DEBUG)
    yield
    jobs_logger.removeHandler(caplog.handler)
    jobs_logger.setLevel(orig_level)


# ---------------------------------------------------------------------------
# 1. ID format
# ---------------------------------------------------------------------------

def test_enqueue_returns_unique_job_id_with_prefix():
    from app.jobs import enqueue

    id1 = enqueue("test_job_a", lambda: None)
    id2 = enqueue("test_job_b", lambda: None)

    assert re.match(r"^job_[0-9a-f]{12}$", id1), f"unexpected id: {id1!r}"
    assert re.match(r"^job_[0-9a-f]{12}$", id2), f"unexpected id: {id2!r}"
    assert id1 != id2


# ---------------------------------------------------------------------------
# 2. args/kwargs forwarding
# ---------------------------------------------------------------------------

def test_enqueue_runs_target_with_args_and_kwargs():
    from app.jobs import enqueue

    results: list = []
    done = threading.Event()

    def my_target(a, b, *, keyword):
        results.append((a, b, keyword))
        done.set()

    enqueue("test_job", my_target, "alpha", "beta", keyword="gamma")

    assert done.wait(timeout=1.0), "target never executed within 1 s"
    assert results == [("alpha", "beta", "gamma")]


# ---------------------------------------------------------------------------
# 3. daemon=True
# ---------------------------------------------------------------------------

def test_enqueue_target_runs_in_daemon_thread():
    from app.jobs import enqueue

    created_threads: list[threading.Thread] = []
    original_init = threading.Thread.__init__

    def capture_init(self, *a, **kw):
        original_init(self, *a, **kw)
        created_threads.append(self)

    with patch.object(threading.Thread, "__init__", capture_init):
        enqueue("test_daemon_job", lambda: None)

    assert created_threads, "no Thread was constructed"
    assert all(t.daemon for t in created_threads), "Thread must be daemon=True"


# ---------------------------------------------------------------------------
# 4. log at INFO
# ---------------------------------------------------------------------------

def test_enqueue_logs_at_info(caplog):
    from app.jobs import enqueue

    evt = threading.Event()

    with caplog.at_level(logging.INFO, logger="agora.jobs"):
        job_id = enqueue("my_special_job", lambda: evt.set())

    evt.wait(timeout=1.0)

    records = [r for r in caplog.records if r.name == "agora.jobs"]
    assert records, "no log record from agora.jobs"
    combined = " ".join(r.getMessage() for r in records)
    assert "my_special_job" in combined, f"job_name missing in log: {combined!r}"
    assert job_id in combined, f"job_id missing in log: {combined!r}"
    assert records[0].levelno == logging.INFO


# ---------------------------------------------------------------------------
# 5. exception in target → logged as ERROR, not raised
# ---------------------------------------------------------------------------

def test_enqueue_propagates_exception_into_thread_log(caplog):
    import time
    from app.jobs import enqueue

    done = threading.Event()

    def boom():
        done.set()
        raise RuntimeError("intentional test failure")

    with caplog.at_level(logging.ERROR, logger="agora.jobs"):
        enqueue("failing_job", boom)

    done.wait(timeout=1.0)
    # Give the thread a moment to log after setting the event.
    time.sleep(0.05)

    error_records = [
        r for r in caplog.records
        if r.name == "agora.jobs" and r.levelno == logging.ERROR
    ]
    assert error_records, "expected an ERROR log from agora.jobs on target exception"
    combined = " ".join(r.getMessage() for r in error_records)
    assert "failing_job" in combined or "intentional test failure" in combined


# ---------------------------------------------------------------------------
# Prozess-Identitaet fuer die Startup-Reconciliation (Issue #1472)
# ---------------------------------------------------------------------------


class _RecordingRegistry:
    def __init__(self) -> None:
        self.runs: dict = {}
        self.calls: list = []

    def update_run(self, run_id: str, **updates):
        self.calls.append((run_id, updates))
        self.runs.setdefault(run_id, {}).setdefault("metadata", {}).update(
            updates.get("metadata") or {}
        )
        return self.runs[run_id]


def _patched_registry(monkeypatch) -> _RecordingRegistry:
    registry = _RecordingRegistry()
    monkeypatch.setattr(
        "app.services.run_registry.RunRegistry", lambda: registry, raising=True
    )
    return registry


def test_enqueue_stamps_the_worker_identity_when_a_run_id_is_given(monkeypatch):
    """Ohne diesen Stempel hat ein In-Process-Job keine pruefbare Liveness —
    nach einem SIGTERM bleibt sein Manifest fuer immer auf 'processing'."""
    from app.jobs import enqueue
    from app.jobs.identity import worker_token

    registry = _patched_registry(monkeypatch)
    done = threading.Event()

    enqueue("simulation_prepare", done.set, run_id="run_abc")
    done.wait(timeout=5)

    assert registry.calls, "kein update_run aufgerufen"
    run_id, updates = registry.calls[0]
    assert run_id == "run_abc"
    assert updates["metadata"]["worker_token"] == worker_token()
    assert updates["metadata"]["worker_pid"] > 0


def test_enqueue_without_run_id_touches_no_registry(monkeypatch):
    from app.jobs import enqueue

    registry = _patched_registry(monkeypatch)
    done = threading.Event()

    enqueue("adhoc", done.set)
    done.wait(timeout=5)

    assert registry.calls == []


def test_a_failing_registry_never_prevents_the_job(monkeypatch, caplog):
    """Bookkeeping darf den Job nicht verhindern — ein nicht gestempelter Job
    ist schlechter beobachtbar, ein nicht gestarteter ist kaputt."""
    from app.jobs import enqueue

    class _Broken:
        def update_run(self, *_a, **_k):
            raise OSError("registry unavailable")

    monkeypatch.setattr(
        "app.services.run_registry.RunRegistry", lambda: _Broken(), raising=True
    )
    done = threading.Event()

    enqueue("simulation_prepare", done.set, run_id="run_abc")

    assert done.wait(timeout=5), "Job lief nicht trotz Registry-Fehler"


def test_identity_survives_a_restart_as_orphaned(monkeypatch):
    """Die Kette als Ganzes: gestempelt, Prozess weg, Reconciliation greift."""
    from app.jobs import enqueue
    from app.services.sim.reconciliation import reconcile_stale_jobs

    registry = _patched_registry(monkeypatch)
    done = threading.Event()
    enqueue("simulation_prepare", done.set, run_id="run_abc")
    done.wait(timeout=5)
    stamped = dict(registry.runs["run_abc"]["metadata"])

    class _AfterRestart:
        """Derselbe Registry-Inhalt, gelesen von einem anderen Prozess."""

        def __init__(self) -> None:
            self.updates: list = []

        def list_runs(self, *, statuses, run_type, limit):
            if run_type != "simulation_prepare":
                return []
            return [
                {
                    "run_id": "run_abc",
                    "run_type": "simulation_prepare",
                    "status": "processing",
                    "entity_id": "sim_0123456789ab",
                    "linked_ids": {"simulation_id": "sim_0123456789ab"},
                    "metadata": stamped,
                }
            ]

        def update_run(self, run_id, **updates):
            self.updates.append((run_id, updates))
            return {}

    after = _AfterRestart()

    # Im selben Prozess gilt der Job als lebend ...
    assert reconcile_stale_jobs(after, fail_simulation_state=lambda *_: None).skipped_run_ids == [
        "run_abc"
    ]
    assert after.updates == []

    # ... aus Sicht eines anderen Prozesses als verwaist.
    result = reconcile_stale_jobs(
        after, owns=lambda _meta: False, fail_simulation_state=lambda *_: None
    )
    assert result.reconciled_run_ids == ["run_abc"]
    assert after.updates[0][1]["status"] == "failed"
    assert after.updates[0][1]["termination_reason"] == "process_restart"


# ---------------------------------------------------------------------------
# Lease-Heartbeat (Issue #1472, Architekturentscheidung 2026-09-24)
#
# Alle Tests setzen das Heartbeat-Intervall auf einen sehr kleinen Wert
# (0.02s statt des Produktions-Defaults) und warten mit kurzen, begrenzten
# ``time.sleep``/``Event.wait``-Aufrufen (< 0.2s) — kein echtes Sleep über
# Sekunden.
# ---------------------------------------------------------------------------


def test_enqueue_writes_a_lease_with_heartbeat_and_ttl(monkeypatch):
    """enqueue() schreibt seit #1472 eine vollstaendige Lease, nicht mehr nur
    den reinen PID+Token-Stempel."""
    from app.jobs import enqueue
    from app.jobs.identity import worker_token

    registry = _patched_registry(monkeypatch)
    done = threading.Event()

    enqueue("simulation_prepare", done.set, run_id="run_lease")
    done.wait(timeout=5)

    run_id, updates = registry.calls[0]
    metadata = updates["metadata"]
    assert run_id == "run_lease"
    assert metadata["worker_token"] == worker_token()
    assert metadata["worker_pid"] > 0
    assert "heartbeat_at" in metadata
    assert metadata["lease_ttl_s"] > 0


def test_heartbeat_updates_metadata_while_the_job_is_running(monkeypatch):
    import time

    from app.config import Config
    from app.jobs import enqueue

    registry = _patched_registry(monkeypatch)
    monkeypatch.setattr(Config, "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS", 0.02)

    job_running = threading.Event()
    release_job = threading.Event()

    def slow_job():
        job_running.set()
        release_job.wait(timeout=2)

    enqueue("simulation_prepare", slow_job, run_id="run_hb_tick")
    assert job_running.wait(timeout=2), "Job-Target lief nie an"

    time.sleep(0.08)  # mindestens ein Heartbeat-Tick bei 0.02s Intervall
    release_job.set()

    heartbeat_only_updates = [
        upd
        for rid, upd in registry.calls
        if rid == "run_hb_tick"
        and set(upd.get("metadata", {}).keys()) == {"heartbeat_at"}
    ]
    assert heartbeat_only_updates, (
        "kein periodisches heartbeat_at-Update waehrend der Job lief beobachtet"
    )


def test_heartbeat_thread_stops_after_the_job_completes(monkeypatch):
    """Heartbeat endet mit dem Job — Erfolgsfall."""
    import time

    from app.config import Config
    from app.jobs import enqueue

    _patched_registry(monkeypatch)
    monkeypatch.setattr(Config, "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    done = threading.Event()

    enqueue("simulation_prepare", done.set, run_id="run_hb_ok")
    assert done.wait(timeout=5)
    time.sleep(0.1)  # dem _wrapper()-finally-Block Zeit zum Join geben

    alive = [t for t in threading.enumerate() if t.name == "agora-job-heartbeat-run_hb_ok"]
    assert alive == [], f"Heartbeat-Thread laeuft nach Job-Ende noch: {alive}"


def test_heartbeat_thread_stops_after_the_job_raises(monkeypatch):
    """Heartbeat endet mit dem Job — auch im Exception-Fall (Anforderung 2)."""
    import time

    from app.config import Config
    from app.jobs import enqueue

    _patched_registry(monkeypatch)
    monkeypatch.setattr(Config, "AGORA_JOB_LEASE_HEARTBEAT_INTERVAL_SECONDS", 0.02)
    done = threading.Event()

    def boom():
        done.set()
        raise RuntimeError("intentional heartbeat-lifecycle test failure")

    enqueue("simulation_prepare", boom, run_id="run_hb_boom")
    assert done.wait(timeout=5)
    time.sleep(0.1)

    alive = [t for t in threading.enumerate() if t.name == "agora-job-heartbeat-run_hb_boom"]
    assert alive == [], f"Heartbeat-Thread laeuft nach Exception noch: {alive}"


def test_heartbeat_loop_stops_immediately_once_the_stop_event_is_set():
    """Direkter Unit-Test von ``_heartbeat_loop`` ohne den vollen enqueue()-Pfad:
    ``stop_event.wait`` liefert sofort True, kein Warten auf das naechste
    Intervall (Anforderung: Heartbeat-Intervall deutlich kleiner als TTL, aber
    der Stop selbst darf nicht am Intervall haengen)."""
    from app.jobs import _heartbeat_loop

    stop_event = threading.Event()
    stop_event.set()  # bereits vor dem ersten Tick gesetzt

    thread = threading.Thread(
        target=_heartbeat_loop, args=("run_x", stop_event, 30.0), daemon=True
    )
    thread.start()
    thread.join(timeout=1)

    assert not thread.is_alive(), "Loop haette sofort beenden muessen"
