"""Tests für Bus-Drop-Counter-Integration in RedisEventBus._subscribe_live (Slice 2c).

TDD-Spec (RED first):
- decode_error: ungültiges JSON → bus_event_drop_counter(reason="decode_error")
- schema_error: valides JSON aber Pydantic-ValidationError → reason="schema_error"
- valid_event: kein Drop-Counter-Increment

Fixture-Strategie:
  ``metrics_provider``-Pattern aus tests/observability/test_metrics.py:
  isolierter InMemoryMetricReader + Monkeypatch des Modul-Caches.
"""

from __future__ import annotations

import json
import threading
from typing import Any, Generator
from unittest.mock import MagicMock

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader

import app.observability.metrics as metrics_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_metrics_cache(monkeypatch):
    """Modul-Cache vor jedem Test zurücksetzen."""
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
    """Isolierter MeterProvider mit InMemoryMetricReader — identisch zu test_metrics.py."""
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


def _collect_datapoints(reader: InMemoryMetricReader, instrument_name: str) -> list:
    data = reader.get_metrics_data()
    result = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for metric in sm.metrics:
                if metric.name == instrument_name:
                    result.extend(metric.data.data_points)
    return result


# ---------------------------------------------------------------------------
# Helper: minimales Redis-Stub-Umfeld für _subscribe_live
# ---------------------------------------------------------------------------


def _make_pubsub_stub(messages: list[dict[str, Any]]) -> MagicMock:
    """Gibt einen PubSub-Stub zurück der genau `messages` liefert, dann None."""
    pubsub = MagicMock()
    call_count = [0]

    def _get_message(timeout: float = 0.1):
        idx = call_count[0]
        call_count[0] += 1
        if idx < len(messages):
            return messages[idx]
        return None  # stoppt den Loop via timeout-Mechanismus

    pubsub.get_message.side_effect = _get_message
    return pubsub


def _make_bus_with_pubsub(pubsub_stub: MagicMock, store_stub: MagicMock) -> Any:
    """Gibt eine RedisEventBus-Instanz mit gemocktem Redis-Client zurück."""
    from app.services.event_bus_redis import RedisEventBus

    redis_mock = MagicMock()
    redis_mock.pubsub.return_value = pubsub_stub
    redis_mock.ping.return_value = True

    bus = RedisEventBus.__new__(RedisEventBus)
    bus._redis = redis_mock
    bus._store = store_stub
    bus._url = "redis://localhost:6379"
    bus._file_bus = MagicMock()
    return bus


def _make_store_stub(snapshot: Any = None) -> MagicMock:
    """Minimal-Stub für SimulationArtifactStore."""
    store = MagicMock()
    store.read_json.return_value = snapshot
    return store


# ---------------------------------------------------------------------------
# Case 1: JSONDecodeError → reason="decode_error"
# ---------------------------------------------------------------------------


class TestBusDropCounterDecodeError:
    def test_decode_error_increments_drop_counter(self, metrics_provider):
        """Ungültiges JSON im Bus-Message → drop_counter mit reason='decode_error'."""
        provider, reader = metrics_provider

        pubsub = _make_pubsub_stub([
            {"type": "message", "data": "NOT_VALID_JSON{{{{"},
        ])
        store = _make_store_stub()
        bus = _make_bus_with_pubsub(pubsub, store)

        # Genau eine Iteration via timeout=0
        results = list(bus._subscribe_live("sim-1", "control", timeout=0.05, poll_interval=0.01))

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.bus.events.dropped")
        reason_dps = [dp for dp in dps if dp.attributes.get("reason") == "decode_error"]
        assert len(reason_dps) >= 1, f"Kein decode_error DataPoint. Alle DPs: {dps}"
        assert any(dp.value >= 1 for dp in reason_dps)
        assert results == []


# ---------------------------------------------------------------------------
# Case 2: Pydantic-ValidationError → reason="schema_error"
# ---------------------------------------------------------------------------


class TestBusDropCounterSchemaError:
    def test_schema_error_increments_drop_counter(self, metrics_provider):
        """Valides JSON aber ungültige SimulationEvent-Struktur → reason='schema_error'."""
        provider, reader = metrics_provider

        # Valides JSON, aber SimulationEvent.from_dict erwartet 'type' + 'simulation_id'
        bad_payload = json.dumps({"completely": "wrong", "structure": True})
        pubsub = _make_pubsub_stub([
            {"type": "message", "data": bad_payload},
        ])
        store = _make_store_stub()
        bus = _make_bus_with_pubsub(pubsub, store)

        results = list(bus._subscribe_live("sim-1", "control", timeout=0.05, poll_interval=0.01))

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.bus.events.dropped")
        reason_dps = [dp for dp in dps if dp.attributes.get("reason") == "schema_error"]
        assert len(reason_dps) >= 1, f"Kein schema_error DataPoint. Alle DPs: {dps}"
        assert any(dp.value >= 1 for dp in reason_dps)
        assert results == []


# ---------------------------------------------------------------------------
# Case 3: Valides Event → kein Drop-Counter-Increment
# ---------------------------------------------------------------------------


class TestBusNoDropOnValidEvent:
    def test_valid_event_no_drop(self, metrics_provider):
        """Valides SimulationEvent → kein Drop-Counter-Increment."""
        provider, reader = metrics_provider

        valid_payload = json.dumps({
            "type": "control.update",
            "simulation_id": "sim-42",
            "payload": {"paused": False},
            "ts": "2026-05-15T10:00:00",
        })
        pubsub = _make_pubsub_stub([
            {"type": "message", "data": valid_payload},
        ])
        store = _make_store_stub()
        bus = _make_bus_with_pubsub(pubsub, store)

        results = list(bus._subscribe_live("sim-42", "control", timeout=0.05, poll_interval=0.01))

        provider.force_flush()

        dps = _collect_datapoints(reader, "agora.bus.events.dropped")
        assert len(dps) == 0, f"Unerwartete Drop-DataPoints: {dps}"
        assert len(results) == 1
