"""Tests für app.observability.metrics (Slice 2a).

TDD-Spec: MeterProvider initialisiert gegated über OTEL_METRICS_ENABLED;
Cardinality-Guard via View-Whitelist; Factory-Roundtrips mit InMemoryMetricReader.

Fixture-Strategie:
  ``metrics_provider`` baut einen isolierten MeterProvider mit InMemoryMetricReader
  und dem vollständigen View-Set aus ``metrics._build_views()``. Der Module-Level-
  Cache (_provider / _meter) wird via Monkeypatch umgangen, indem die Factories
  direkt den Fixture-Provider nutzen. Dies erfordert keinen Reset des globalen
  ``metrics``-Namespace und vermeidet Seiteneffekte auf die OTel-Global-Registry.
"""

from __future__ import annotations

import threading
from typing import Generator

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.observability.metrics as metrics_module
from app.observability import (
    init_metrics,
    force_flush,
    sim_counter,
    sim_duration_histogram,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_metrics_module_cache(monkeypatch):
    """Setzt den Modul-Cache vor jedem Test zurück, damit Idempotenz-Tests
    sauber isoliert sind und kein State zwischen Tests leckt."""
    monkeypatch.setattr(metrics_module, "_provider", None)
    monkeypatch.setattr(metrics_module, "_meter", None)
    monkeypatch.setattr(metrics_module, "_lock", threading.Lock())
    yield
    # Teardown: Cache zurücksetzen damit folgende Tests sauber starten.
    metrics_module._provider = None
    metrics_module._meter = None


@pytest.fixture()
def in_memory_reader() -> InMemoryMetricReader:
    """Liefert einen frischen InMemoryMetricReader."""
    return InMemoryMetricReader()


@pytest.fixture()
def metrics_provider(
    in_memory_reader: InMemoryMetricReader,
    monkeypatch,
) -> Generator[tuple[MeterProvider, InMemoryMetricReader], None, None]:
    """Baut einen isolierten MeterProvider mit dem vollständigen View-Set
    aus ``metrics_module._build_views()`` und einem InMemoryMetricReader.

    Überschreibt den Modul-Cache, damit die Factory-Funktionen (sim_counter etc.)
    denselben Provider nutzen.
    """
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
    """Sammelt DataPoints für ein bestimmtes Instrument aus dem Reader."""
    data = reader.get_metrics_data()
    result = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == instrument_name:
                    result.extend(metric.data.data_points)
    return result


# ---------------------------------------------------------------------------
# Case 1: Default-Off — kein Provider ohne OTEL_METRICS_ENABLED=true
# ---------------------------------------------------------------------------


def test_default_off_no_provider(monkeypatch):
    """OTEL_METRICS_ENABLED unset → init_metrics triggert set_meter_provider nicht.

    Der globale Provider bleibt der OTel-Default (_ProxyMeterProvider oder
    NoOpMeterProvider), nicht eine MeterProvider-Instanz aus dem SDK.
    """
    monkeypatch.delenv("OTEL_METRICS_ENABLED", raising=False)
    init_metrics("agora-test")
    assert metrics_module._provider is None


def test_default_false_no_provider(monkeypatch):
    """OTEL_METRICS_ENABLED=false → identisch wie unset."""
    monkeypatch.setenv("OTEL_METRICS_ENABLED", "false")
    init_metrics("agora-test")
    assert metrics_module._provider is None


# ---------------------------------------------------------------------------
# Case 2: Enabled — Provider wird initialisiert
# ---------------------------------------------------------------------------


def test_enabled_initializes_provider(monkeypatch):
    """OTEL_METRICS_ENABLED=true → init_metrics registriert MeterProvider."""
    monkeypatch.setenv("OTEL_METRICS_ENABLED", "true")
    # Endpoint auf localhost setzen damit OTLPMetricExporter keinen DNS-Fehler
    # beim Konstruieren des Channels wirft (kein echter Export im Test).
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

    init_metrics("agora-test")

    assert metrics_module._provider is not None
    assert isinstance(metrics_module._provider, MeterProvider)


# ---------------------------------------------------------------------------
# Case 3: Idempotenz — zweiter Aufruf liefert denselben Provider
# ---------------------------------------------------------------------------


def test_module_cache_idempotent(monkeypatch):
    """Zweimaliger Aufruf von init_metrics → identische Provider-Instanz (gleiche id())."""
    monkeypatch.setenv("OTEL_METRICS_ENABLED", "true")
    monkeypatch.setenv("OTEL_EXPORTER_OTLP_ENDPOINT", "localhost:4317")

    init_metrics("agora-test")
    p1 = metrics_module._provider

    init_metrics("agora-test")
    p2 = metrics_module._provider

    assert p1 is p2


# ---------------------------------------------------------------------------
# Case 4: Counter-Roundtrip
# ---------------------------------------------------------------------------


def test_counter_roundtrip(metrics_provider):
    """sim_counter().add(1, {"status": "done"}) → Reader liefert DataPoint."""
    provider, reader = metrics_provider

    sim_counter().add(1, {"status": "done"})
    provider.force_flush()

    dps = _collect_datapoints(reader, "agora.sim.started")
    assert len(dps) >= 1
    assert any(dp.value == 1 for dp in dps)


# ---------------------------------------------------------------------------
# Case 5: Histogram-Roundtrip
# ---------------------------------------------------------------------------


def test_histogram_roundtrip(metrics_provider):
    """sim_duration_histogram().record(42.0, {"status": "done"}) → count=1, sum=42.0."""
    provider, reader = metrics_provider

    sim_duration_histogram().record(42.0, {"status": "done"})
    provider.force_flush()

    dps = _collect_datapoints(reader, "agora.sim.duration_seconds")
    assert len(dps) >= 1
    matching = [dp for dp in dps if dp.count == 1 and dp.sum == 42.0]
    assert len(matching) >= 1


# ---------------------------------------------------------------------------
# Case 6: Cardinality-Guard — simulation_id wird herausgefiltert
# ---------------------------------------------------------------------------


def test_cardinality_guard_strips_simulation_id(metrics_provider):
    """View-Whitelist für agora.sim.started enthält nur 'status'.

    simulation_id darf nicht im DataPoint auftauchen.
    """
    provider, reader = metrics_provider

    sim_counter().add(1, {"status": "done", "simulation_id": "abc-123"})
    provider.force_flush()

    dps = _collect_datapoints(reader, "agora.sim.started")
    user_dps = [
        dp for dp in dps
        if "otel.component.type" not in dp.attributes
    ]
    assert len(user_dps) >= 1
    for dp in user_dps:
        assert "simulation_id" not in dp.attributes
        assert "status" in dp.attributes


# ---------------------------------------------------------------------------
# Case 7: force_flush NoOp ohne init
# ---------------------------------------------------------------------------


def test_force_flush_noop_when_disabled():
    """force_flush() ohne vorheriges init_metrics() wirft nicht und liefert None."""
    # _reset_metrics_module_cache sorgt dafür dass _provider=None
    result = force_flush()
    assert result is None
