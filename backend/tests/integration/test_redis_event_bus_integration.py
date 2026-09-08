"""Echter Redis-Integrationstest für ``RedisEventBus`` (Slice 9).

Muster aus ``tests/test_event_bus_redis.py`` übernommen, aber ohne dessen
modulweiten Skip-Guard — das Überspringen bei fehlendem Redis übernimmt
hier die ``redis_client``-Fixture aus ``tests/integration/conftest.py``
(``AGORA_TEST_REDIS_URL``).
"""

from __future__ import annotations

import os
import threading
import time
from typing import List

import pytest

from app.services.artifact_store import LocalFilesystemArtifactStore
from app.services.event_bus import CHANNEL_CONTROL, SimulationEvent
from app.services.event_bus_redis import RedisEventBus

pytestmark = pytest.mark.integration

SIM_ID = "sim_itest_redis_bus"


@pytest.fixture
def bus(tmp_path, redis_client):
    # redis_client stellt sicher, dass Redis erreichbar ist (sonst skip);
    # RedisEventBus baut sich seine eigene Verbindung aus derselben URL auf.
    redis_url = os.environ["AGORA_TEST_REDIS_URL"]
    store = LocalFilesystemArtifactStore(simulations_root=str(tmp_path))
    event_bus = RedisEventBus(redis_url, artifact_store=store)

    for key in redis_client.scan_iter(f"agora:sim:{SIM_ID}:*"):
        redis_client.delete(key)

    yield event_bus

    for key in redis_client.scan_iter(f"agora:sim:{SIM_ID}:*"):
        redis_client.delete(key)
    event_bus.close()


def test_control_publish_reaches_live_subscriber_over_real_redis(bus):
    """Publish/Subscribe-Rundlauf über einen echten Redis-Server."""
    received: List[SimulationEvent] = []
    ready = threading.Event()

    def consume() -> None:
        ready.set()
        for event in bus.subscribe(
            SIM_ID, CHANNEL_CONTROL, timeout=2.0, poll_interval=0.05
        ):
            received.append(event)
            if event.payload.get("paused") is True:
                return

    t = threading.Thread(target=consume, daemon=True)
    t.start()
    ready.wait()
    # Zeit geben, damit der Subscriber SUBSCRIBE auf der Redis-Verbindung
    # ausgeführt hat, bevor publiziert wird.
    time.sleep(0.15)

    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type="control.update",
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    t.join(timeout=2.5)

    assert any(e.payload.get("paused") is True for e in received), (
        f"Subscriber hat kein Pause-Event über echtes Redis erhalten "
        f"(gesehen: {[e.payload for e in received]})"
    )
