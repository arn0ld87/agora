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
from app.services.event_bus_redis import RedisEventBus, _channel_key

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


def test_control_publish_reaches_live_subscriber_over_real_redis(bus, redis_client):
    """Publish/Subscribe-Rundlauf ueber einen echten Redis-Server.

    Zwei Fallen, die dieser Test aktiv ausschliesst (Codex-Review PR #1481):

    1. ``RedisEventBus._subscribe_live`` liefert Late-Subscribern zuerst den
       aufbewahrten Filesystem-Snapshot des ``control_state``-Artefakts. Der
       synthetisierte Event traegt dabei immer ``type=f"{channel}.update"``.
       Wuerde dieser Test denselben Typ publizieren, koennte er ueber den
       Snapshot gruen werden, ohne dass je eine Pub/Sub-Nachricht floss.
       Deshalb publiziert er einen Typ, den der Snapshot-Pfad nicht erzeugen
       kann, und assertiert genau darauf.
    2. Ein festes ``sleep`` ist nur eine Zeit-Vermutung. Stattdessen wartet der
       Test auf die Bestaetigung des Servers selbst: ``PUBSUB NUMSUB`` meldet
       den Subscriber erst, wenn Redis das SUBSCRIBE verarbeitet hat.
    """
    marker_type = "control.itest_pubsub_marker"
    received: List[SimulationEvent] = []

    def consume() -> None:
        for event in bus.subscribe(
            SIM_ID, CHANNEL_CONTROL, timeout=5.0, poll_interval=0.05
        ):
            received.append(event)
            if event.type == marker_type:
                return

    t = threading.Thread(target=consume, daemon=True)
    t.start()

    # Auf die Server-seitige Bestaetigung warten statt zu schlafen.
    key = _channel_key(SIM_ID, CHANNEL_CONTROL)
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if int(redis_client.pubsub_numsub(key)[0][1]) >= 1:
            break
        time.sleep(0.02)
    else:
        raise AssertionError(
            f"Redis meldete innerhalb von 5s keinen Subscriber auf {key} — "
            "der Test haette ohne echte Subscription publiziert."
        )

    bus.publish(
        CHANNEL_CONTROL,
        SimulationEvent(
            type=marker_type,
            simulation_id=SIM_ID,
            payload={"paused": True},
        ),
    )
    t.join(timeout=5.5)

    assert any(e.type == marker_type for e in received), (
        "Subscriber hat den Marker-Event nicht ueber echtes Redis erhalten "
        f"(gesehen: {[(e.type, e.payload) for e in received]}). Ein ueber den "
        "Retained-Snapshot gelieferter Event traegt control.update und wuerde "
        "diese Assertion nicht erfuellen."
    )


def test_retained_snapshot_is_distinguishable_from_a_pubsub_message(bus, tmp_path):
    """Pinnt die Luecke fest, die der Test oben umgeht (Codex-Review PR #1481).

    Liegt ein ``control_state``-Artefakt vor, liefert ``subscribe`` es sofort
    als synthetisierten Event — ohne dass jemand publiziert hat. Dessen Payload
    kann inhaltlich identisch zu einem echten Pub/Sub-Event sein; ihn
    unterscheidbar macht ausschliesslich der Typ ``control.update``.

    Faellt diese Assertion, ist der Snapshot-Pfad nicht mehr unterscheidbar —
    und der Publish/Subscribe-Test darueber verliert seine Aussagekraft, ohne
    selbst rot zu werden.
    """
    bus._store.write_json(SIM_ID, "control_state", {"paused": True})

    received: List[SimulationEvent] = []
    for event in bus.subscribe(SIM_ID, CHANNEL_CONTROL, timeout=1.0, poll_interval=0.05):
        received.append(event)
        break

    assert received, "Der Retained-Snapshot wurde gar nicht ausgeliefert"
    assert received[0].type == f"{CHANNEL_CONTROL}.update", (
        "Der Snapshot-Pfad muss einen eigenen, erkennbaren Typ tragen — sonst "
        "kann der Publish/Subscribe-Test ueber ihn gruen werden, ohne dass je "
        f"eine Nachricht floss (erhalten: {received[0].type})"
    )
    assert received[0].payload.get("paused") is True, (
        "Der Snapshot liefert denselben Payload wie ein echtes Event — genau "
        "deshalb reicht eine Payload-Assertion allein nicht aus"
    )
