"""Contract tests for SimulationEventBus adapters (Issue #9 Phase A).

Both :class:`InMemoryEventBus` and :class:`FilePollingEventBus` must honour
the same port contract: publish/subscribe semantics, fan-out to multiple
subscribers, correlated request/response, and timeout behaviour.

Semantics convention:
* "Subscriber first, then publish" — events raised after subscription arrive.
  Both adapters must honour this shape; it's the intersection with Redis
  pub/sub, which lands in Phase B.
* Retained state (last-value-wins on persistent channels) is a
  file-adapter-only guarantee today and gets its own targeted tests.
"""

from __future__ import annotations

import threading
import time
from typing import Callable, List

import pytest

from app.services.artifact_store import LocalFilesystemArtifactStore
from app.services.event_bus import (
    CHANNEL_CONTROL,
    CHANNEL_RPC_COMMAND,
    CHANNEL_STATE,
    FilePollingEventBus,
    InMemoryEventBus,
    SimulationEvent,
    SimulationEventBus,
    rpc_response_channel,
)


SIM_ID = "sim_bus_test"


@pytest.fixture(
    params=["memory", "file"],
    ids=["InMemoryEventBus", "FilePollingEventBus"],
)
def bus_factory(request, tmp_path) -> Callable[[], SimulationEventBus]:
    if request.param == "memory":
        return lambda: InMemoryEventBus()
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    return lambda: FilePollingEventBus(store=store)


@pytest.fixture
def bus(bus_factory) -> SimulationEventBus:
    return bus_factory()


def _drain_into(
    target: List[SimulationEvent],
    bus: SimulationEventBus,
    simulation_id: str,
    channel: str,
    *,
    ready: threading.Event,
    stop_after: int,
    timeout: float = 2.0,
    poll_interval: float = 0.05,
) -> None:
    """Collect up to ``stop_after`` events on ``channel`` in a background thread."""
    ready.set()
    for event in bus.subscribe(
        simulation_id, channel, timeout=timeout, poll_interval=poll_interval
    ):
        target.append(event)
        if len(target) >= stop_after:
            return


# ---------------------------------------------------------------------------
# Publish → subscribe (subscriber first)
# ---------------------------------------------------------------------------


def test_publish_surfaces_to_live_subscriber(bus):
    received: List[SimulationEvent] = []
    ready = threading.Event()
    t = threading.Thread(
        target=_drain_into,
        args=(received, bus, SIM_ID, CHANNEL_CONTROL),
        kwargs={"ready": ready, "stop_after": 1},
        daemon=True,
    )
    t.start()
    ready.wait()
    # Give the subscriber a beat to register its cursor / start polling.
    time.sleep(0.1)
    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    t.join(timeout=2.0)

    assert received, "subscriber received no event"
    assert received[0].payload.get("paused") is True


# ---------------------------------------------------------------------------
# Retained state (file adapter only — persistent-artifact semantics)
# ---------------------------------------------------------------------------


def test_file_adapter_merges_partial_control_publishes(tmp_path):
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    bus = FilePollingEventBus(store=store)

    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"stop_requested": True},
        ),
    )
    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    state = store.read_json(SIM_ID, "control_state", default={})
    assert state["paused"] is True
    assert state["stop_requested"] is True


def test_file_adapter_late_subscriber_sees_retained_state(tmp_path):
    """File adapter ⇒ retained state: a late subscriber sees the latest control snapshot."""
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    bus = FilePollingEventBus(store=store)

    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    received: List[SimulationEvent] = []
    for event in bus.subscribe(SIM_ID, CHANNEL_CONTROL, timeout=0.5, poll_interval=0.05):
        received.append(event)
        if event.payload.get("paused") is True:
            break
    assert received and received[-1].payload.get("paused") is True


# ---------------------------------------------------------------------------
# Fan-out (in-memory pub/sub semantics)
# ---------------------------------------------------------------------------


def test_in_memory_fan_out_to_n_subscribers():
    bus = InMemoryEventBus()
    n = 4
    received: List[List[SimulationEvent]] = [[] for _ in range(n)]
    ready = threading.Barrier(n + 1)

    def consume(idx: int) -> None:
        ready.wait()
        for event in bus.subscribe(SIM_ID, CHANNEL_STATE, timeout=1.0, poll_interval=0.05):
            received[idx].append(event)
            if len(received[idx]) >= 3:
                return

    threads = [threading.Thread(target=consume, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    ready.wait()
    time.sleep(0.05)
    for i in range(3):
        bus.publish(
            CHANNEL_STATE,
            SimulationEvent(type="state.update", simulation_id=SIM_ID, payload={"i": i}),
        )
    for t in threads:
        t.join(timeout=2.0)

    for i, events in enumerate(received):
        assert len(events) == 3, f"Subscriber {i} saw {len(events)} events"
        assert [e.payload["i"] for e in events] == [0, 1, 2]


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------


def test_in_memory_state_events_are_ordered():
    bus = InMemoryEventBus()
    received: List[SimulationEvent] = []
    ready = threading.Event()
    t = threading.Thread(
        target=_drain_into,
        args=(received, bus, SIM_ID, CHANNEL_STATE),
        kwargs={"ready": ready, "stop_after": 3},
        daemon=True,
    )
    t.start()
    ready.wait()
    time.sleep(0.05)

    stamps = ["2026-04-23T10:00:00", "2026-04-23T10:00:01", "2026-04-23T10:00:02"]
    for s in stamps:
        bus.publish(
            CHANNEL_STATE,
            SimulationEvent(
                type="state.update",
                simulation_id=SIM_ID,
                payload={"updated_at": s},
                ts=s,
            ),
        )
    t.join(timeout=2.0)

    assert [e.payload["updated_at"] for e in received] == stamps


# ---------------------------------------------------------------------------
# Request/response correlation
# ---------------------------------------------------------------------------


def test_request_response_correlation(bus):
    """Command goes out, responder matches by correlation_id, client receives it."""

    def responder() -> None:
        for cmd in bus.subscribe(
            SIM_ID, CHANNEL_RPC_COMMAND, timeout=2.0, poll_interval=0.05
        ):
            assert cmd.correlation_id, "Commands must carry correlation_id"
            response_channel = rpc_response_channel(cmd.correlation_id)
            bus.publish(
                response_channel,
                SimulationEvent(
                    type="rpc.response.completed",
                    simulation_id=SIM_ID,
                    payload={"status": "completed", "result": {"echo": cmd.payload}},
                    correlation_id=cmd.correlation_id,
                ),
            )
            return

    t = threading.Thread(target=responder, daemon=True)
    t.start()

    response = bus.request_response(
        SIM_ID,
        command_type="interview",
        args={"agent_id": 7, "prompt": "hello"},
        timeout=2.0,
        poll_interval=0.05,
    )
    t.join(timeout=3.0)

    assert response.payload["status"] == "completed"
    assert response.payload["result"]["echo"]["agent_id"] == 7


def test_request_response_times_out(bus):
    """No responder → request_response raises TimeoutError within the window."""
    start = time.monotonic()
    with pytest.raises(TimeoutError):
        bus.request_response(
            SIM_ID,
            command_type="interview",
            args={"agent_id": 1, "prompt": "noone_home"},
            timeout=0.3,
            poll_interval=0.05,
        )
    elapsed = time.monotonic() - start
    assert elapsed < 1.5, f"Timeout took {elapsed:.2f}s (expected ~0.3s)"


# ---------------------------------------------------------------------------
# Isolation between simulations
# ---------------------------------------------------------------------------


def test_events_do_not_leak_between_simulations(bus):
    received_a: List[SimulationEvent] = []
    ready = threading.Event()
    t = threading.Thread(
        target=_drain_into,
        args=(received_a, bus, "sim_a", CHANNEL_CONTROL),
        kwargs={"ready": ready, "stop_after": 1},
        daemon=True,
    )
    t.start()
    ready.wait()
    time.sleep(0.05)

    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id="sim_b",
            payload={"paused": False},
        ),
    )
    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id="sim_a",
            payload={"paused": True},
        ),
    )
    t.join(timeout=2.0)

    assert received_a, "sim_a subscriber got no event"
    assert received_a[0].simulation_id == "sim_a"
    assert received_a[0].payload.get("paused") is True


# ---------------------------------------------------------------------------
# SimulationEvent round-trip serialization
# ---------------------------------------------------------------------------


def test_simulation_event_roundtrip():
    event = SimulationEvent(
        type="interview",
        simulation_id=SIM_ID,
        payload={"agent_id": 3, "prompt": "hi"},
        correlation_id="abc-123",
    )
    data = event.to_dict()
    restored = SimulationEvent.from_dict(data)
    assert restored == event
