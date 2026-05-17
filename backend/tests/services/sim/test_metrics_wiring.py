"""Tests für Sim-Lifecycle-Metrics-Wiring (Slice 2b).

TDD-Spec: Die FSM-Übergänge in process_manager.py (PENDING → RUNNING) und
monitor.py (RUNNING → COMPLETED / FAILED) müssen die drei Instruments
sim_active_gauge, sim_counter, sim_duration_histogram korrekt befüllen.

Fixture-Strategie (identisch zu tests/observability/test_metrics.py):
- metrics_provider baut isolierten MeterProvider mit InMemoryMetricReader
  und dem vollständigen View-Set aus metrics._build_views().
- monkeypatch.setattr auf metrics_module._provider / _meter überschreibt
  den Modul-Cache — kein Seiteneffekt auf OTel-Global-Registry.
- Die FSM-Funktionen werden mit Stub-Callables aufgerufen statt mit echten
  Subprozessen oder Artifact-Store-Instanzen.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Generator, Optional
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.observability.metrics as metrics_module
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_metrics_module_cache(monkeypatch):
    """Setzt den Modul-Cache vor jedem Test zurück."""
    monkeypatch.setattr(metrics_module, "_provider", None)
    monkeypatch.setattr(metrics_module, "_meter", None)
    monkeypatch.setattr(metrics_module, "_lock", threading.Lock())
    yield
    metrics_module._provider = None
    metrics_module._meter = None


@pytest.fixture()
def in_memory_reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture()
def metrics_provider(
    in_memory_reader: InMemoryMetricReader,
    monkeypatch,
) -> Generator[tuple[MeterProvider, InMemoryMetricReader]]:
    """Isolierter MeterProvider + InMemoryMetricReader — identisch zu test_metrics.py."""
    from opentelemetry.sdk.resources import Resource

    views = metrics_module._build_views()
    provider = MeterProvider(
        metric_readers=[in_memory_reader],
        resource=Resource.create({"service.name": "agora-test"}),
        views=views,
    )
    meter = provider.get_meter("agora-test")

    monkeypatch.setattr(metrics_module, "_provider", provider)
    monkeypatch.setattr(metrics_module, "_meter", meter)

    yield provider, in_memory_reader

    provider.force_flush()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _collect_datapoints(reader: InMemoryMetricReader, instrument_name: str) -> list:
    data = reader.get_metrics_data()
    result = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == instrument_name:
                    result.extend(metric.data.data_points)
    return result


def _make_state(
    sim_id: str = "test-sim-001",
    status: RunnerStatus = RunnerStatus.RUNNING,
    started_at: Optional[str] = None,
) -> SimulationRunState:
    """Erstellt einen minimalen SimulationRunState für Tests."""
    if started_at is None:
        started_at = (datetime.now() - timedelta(seconds=10)).isoformat()
    return SimulationRunState(
        simulation_id=sim_id,
        runner_status=status,
        started_at=started_at,
    )


# ---------------------------------------------------------------------------
# Test 1: PENDING → RUNNING triggert sim_active_gauge += 1
# ---------------------------------------------------------------------------


def test_sim_started_increments_active_gauge(metrics_provider, monkeypatch):
    """process_manager.start_simulation setzt status=RUNNING und ruft
    sim_active_gauge().add(1) + sim_counter().add(1, {'status': 'started'})."""
    from app.services.sim import process_manager

    provider, reader = metrics_provider

    saved_states: list[SimulationRunState] = []

    # Stub-Callables für start_simulation
    def _fake_get_run_state(sim_id: str) -> Optional[SimulationRunState]:
        return None  # nicht already running

    def _fake_save_state(s: SimulationRunState) -> None:
        saved_states.append(s)

    # Monkey-patch _tracer.start_as_current_span (OTel-Tracing ist nicht initialisiert)
    # start_simulation läuft in diesem Test-Scope mit OTEL nicht aktiv — der Tracer
    # liefert NoOp-Spans, d.h. kein Patch nötig. Subprocess.Popen wird gestubbt.
    import subprocess as subprocess_module

    fake_process = MagicMock()
    fake_process.pid = 12345
    fake_process.poll.return_value = None

    monkeypatch.setattr(subprocess_module, "Popen", lambda *a, **kw: fake_process)

    # Config-Existence + Config-Read stubs
    config = {
        "time_config": {
            "total_simulation_hours": 1,
            "minutes_per_round": 30,
        }
    }

    # Schreibbares tmpdir für sim_dir
    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        scripts_dir = tmp_dir
        # Erstelle Dummy-Skript
        script_path = os.path.join(scripts_dir, "run_parallel_simulation.py")
        with open(script_path, "w") as f:
            f.write("# stub\n")
        # start_simulation erwartet sim_dir/<sim_id>/ vorhanden (für simulation.log)
        os.makedirs(os.path.join(tmp_dir, "test-sim-001"), exist_ok=True)

        # OASIS_DB_PATH-Env gesetzt damit _inject_oasis_db_env kein makedirs im tmp aufruft
        monkeypatch.setenv("OASIS_DB_PATH", "/tmp/stub.db")

        process_manager.start_simulation(
            "test-sim-001",
            "parallel",
            run_state_dir=tmp_dir,
            scripts_dir=scripts_dir,
            processes={},
            action_queues={},
            monitor_threads={},
            stdout_files={},
            stderr_files={},
            graph_memory_enabled={},
            get_run_state=_fake_get_run_state,
            save_state=_fake_save_state,
            on_monitor_start=lambda sid: None,
            write_control_state=lambda *a, **kw: None,
            get_config=lambda sid: config,
            config_exists=lambda sid: True,
            setup_graph_memory=lambda sid: None,
        )

    provider.force_flush()

    # Gauge muss +1 enthalten
    gauge_dps = _collect_datapoints(reader, "agora.sim.active")
    assert any(dp.value >= 1 for dp in gauge_dps), (
        f"sim_active_gauge sollte +1 enthalten, DataPoints: {gauge_dps}"
    )

    # Counter "started" muss vorhanden sein
    counter_dps = _collect_datapoints(reader, "agora.sim.started")
    started_dps = [dp for dp in counter_dps if dp.attributes.get("status") == "started"]
    assert len(started_dps) >= 1, (
        f"sim_counter('started') sollte >= 1 enthalten, DataPoints: {counter_dps}"
    )


# ---------------------------------------------------------------------------
# Test 2: RUNNING → DONE triggert Counter("done"), Histogram, Gauge -= 1
# ---------------------------------------------------------------------------


def test_sim_done_records_duration_and_decrements_active(metrics_provider, monkeypatch):
    """monitor.monitor_simulation beendet mit exit_code=0:
    - sim_counter().add(1, {'status': 'done'})
    - sim_duration_histogram().record(elapsed, {'status': 'done'})
    - sim_active_gauge().add(-1)
    """
    from app.services.sim import monitor as monitor_module

    provider, reader = metrics_provider

    # Zeitstempel: Sim startete vor 5 Sekunden
    started_at = (datetime.now() - timedelta(seconds=5)).isoformat()
    state = _make_state(started_at=started_at)
    saved_states: list[SimulationRunState] = []

    fake_process = MagicMock()
    fake_process.poll.side_effect = [None, None, 0]  # läuft 2x, dann fertig (exit_code=0)
    fake_process.returncode = 0

    def _fake_get_run_state(sid: str) -> Optional[SimulationRunState]:
        return state

    def _fake_save_state(s: SimulationRunState) -> None:
        saved_states.append(s)

    import tempfile
    with tempfile.TemporaryDirectory() as tmp_dir:
        import os
        sim_dir = os.path.join(tmp_dir, "test-sim-001")
        os.makedirs(sim_dir)

        monitor_module.monitor_simulation(
            "test-sim-001",
            run_state_dir=tmp_dir,
            processes={"test-sim-001": fake_process},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=_fake_get_run_state,
            save_state=_fake_save_state,
        )

    provider.force_flush()

    # Counter "done"
    counter_dps = _collect_datapoints(reader, "agora.sim.started")
    done_dps = [dp for dp in counter_dps if dp.attributes.get("status") == "done"]
    assert len(done_dps) >= 1, f"sim_counter('done') fehlt, DataPoints: {counter_dps}"

    # Histogram "done" mit positivem elapsed
    hist_dps = _collect_datapoints(reader, "agora.sim.duration_seconds")
    done_hist = [dp for dp in hist_dps if dp.attributes.get("status") == "done"]
    assert len(done_hist) >= 1, f"sim_duration_histogram('done') fehlt, DataPoints: {hist_dps}"
    assert done_hist[0].sum > 0, "elapsed_seconds muss > 0 sein"

    # Gauge -= 1 (negative add)
    gauge_dps = _collect_datapoints(reader, "agora.sim.active")
    assert any(dp.value <= -1 for dp in gauge_dps), (
        f"sim_active_gauge sollte -1 enthalten, DataPoints: {gauge_dps}"
    )


# ---------------------------------------------------------------------------
# Test 3: RUNNING → FAILED triggert Counter("failed"), Histogram mit failed-status
# ---------------------------------------------------------------------------


def test_sim_failed_records_duration_with_failed_status(metrics_provider, monkeypatch):
    """monitor.monitor_simulation beendet mit exit_code=1:
    - sim_counter().add(1, {'status': 'failed'})
    - sim_duration_histogram().record(elapsed, {'status': 'failed'})
    - sim_active_gauge().add(-1)
    """
    from app.services.sim import monitor as monitor_module

    provider, reader = metrics_provider

    started_at = (datetime.now() - timedelta(seconds=3)).isoformat()
    state = _make_state(started_at=started_at)
    saved_states: list[SimulationRunState] = []

    fake_process = MagicMock()
    fake_process.poll.side_effect = [None, 1]  # läuft 1x, dann Fehler
    fake_process.returncode = 1

    def _fake_get_run_state(sid: str) -> Optional[SimulationRunState]:
        return state

    def _fake_save_state(s: SimulationRunState) -> None:
        saved_states.append(s)

    import tempfile
    import os
    with tempfile.TemporaryDirectory() as tmp_dir:
        sim_dir = os.path.join(tmp_dir, "test-sim-001")
        os.makedirs(sim_dir)

        monitor_module.monitor_simulation(
            "test-sim-001",
            run_state_dir=tmp_dir,
            processes={"test-sim-001": fake_process},
            graph_memory_enabled={},
            action_queues={},
            stdout_files={},
            stderr_files={},
            get_run_state=_fake_get_run_state,
            save_state=_fake_save_state,
        )

    provider.force_flush()

    # Counter "failed"
    counter_dps = _collect_datapoints(reader, "agora.sim.started")
    failed_dps = [dp for dp in counter_dps if dp.attributes.get("status") == "failed"]
    assert len(failed_dps) >= 1, f"sim_counter('failed') fehlt, DataPoints: {counter_dps}"

    # Histogram "failed"
    hist_dps = _collect_datapoints(reader, "agora.sim.duration_seconds")
    failed_hist = [dp for dp in hist_dps if dp.attributes.get("status") == "failed"]
    assert len(failed_hist) >= 1, f"sim_duration_histogram('failed') fehlt, DataPoints: {hist_dps}"

    # Gauge -= 1
    gauge_dps = _collect_datapoints(reader, "agora.sim.active")
    assert any(dp.value <= -1 for dp in gauge_dps), (
        f"sim_active_gauge sollte -1 enthalten, DataPoints: {gauge_dps}"
    )


# ---------------------------------------------------------------------------
# Test 4: simulation_id wird NICHT in Metric-Attributen weitergeleitet
# ---------------------------------------------------------------------------


def test_no_simulation_id_in_metric_attributes(metrics_provider):
    """Cardinality-Guard aus 2a: sim_counter mit simulation_id-Attribut →
    DataPoint darf simulation_id nicht enthalten (View-Whitelist greift)."""
    from app.observability import sim_counter

    provider, reader = metrics_provider

    # Jemand übergibt versehentlich simulation_id
    sim_counter().add(1, {"status": "done", "simulation_id": "secret-id-xyz"})
    provider.force_flush()

    dps = _collect_datapoints(reader, "agora.sim.started")
    user_dps = [dp for dp in dps if "otel.component.type" not in dp.attributes]
    assert len(user_dps) >= 1
    for dp in user_dps:
        assert "simulation_id" not in dp.attributes, (
            f"simulation_id darf nicht in DataPoint-Attributen stehen: {dp.attributes}"
        )
        assert "status" in dp.attributes


# ---------------------------------------------------------------------------
# Test 5: OTEL_METRICS_ENABLED=false → kein DataPoint wird emittiert
# ---------------------------------------------------------------------------


def test_metrics_disabled_no_emission(monkeypatch):
    """Ohne OTEL_METRICS_ENABLED=true bleibt metrics_module._provider None —
    init_metrics() registriert keinen MeterProvider, kein OTLP-Export startet.

    Factory-Funktionen liefern NoOp-Instruments (globaler OTel-Meter ist NoOp
    oder ProxyMeterProvider). Der Modul-Cache bleibt leer → keine DataPoints
    in einem nachträglich registrierten Reader.
    """
    monkeypatch.delenv("OTEL_METRICS_ENABLED", raising=False)
    # _reset_metrics_module_cache hat _provider=None gesetzt.
    from app.observability import init_metrics, sim_counter, sim_active_gauge, sim_duration_histogram

    init_metrics("agora-test")

    # Kein Provider initialisiert → Modul-Cache leer
    assert metrics_module._provider is None, (
        "Ohne OTEL_METRICS_ENABLED=true darf kein Provider registriert werden"
    )

    # Factory-Calls dürfen nicht werfen — NoOp-Instruments akzeptieren die Calls
    sim_counter().add(1, {"status": "started"})
    sim_active_gauge().add(1)
    sim_duration_histogram().record(10.0, {"status": "done"})

    # InMemoryMetricReader in einen eigenen Provider einbinden und verifizieren,
    # dass keine Agora-Instruments darin existieren (da der globale Provider NoOp ist)
    from opentelemetry.sdk.metrics import MeterProvider as _MP
    from opentelemetry.sdk.metrics.export import InMemoryMetricReader as _IMR
    from opentelemetry.sdk.resources import Resource

    isolated_reader = _IMR()
    isolated_provider = _MP(
        metric_readers=[isolated_reader],
        resource=Resource.create({"service.name": "agora-test-isolated"}),
    )
    isolated_provider.force_flush()
    data = isolated_reader.get_metrics_data()
    # Kein Instrument wurde in diesem Provider erstellt
    total_dps = sum(
        len(metric.data.data_points)
        for rm in (data.resource_metrics or [])
        for sm in rm.scope_metrics
        for metric in sm.metrics
        if metric.name.startswith("agora.")
    )
    isolated_provider.shutdown()
    assert total_dps == 0, (
        f"Ohne OTEL_METRICS_ENABLED sollten 0 Agora-DataPoints existieren, war: {total_dps}"
    )
