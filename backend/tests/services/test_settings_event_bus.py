"""Tests for the runtime settings change event bus."""

from __future__ import annotations

import threading
import time

from pydantic import ValidationError

from app.services.settings_event_bus import (
    SettingsChangedEvent,
    SettingsEventBus,
    publish_settings_changed,
    settings_event_bus,
)


def _event(**overrides) -> SettingsChangedEvent:
    defaults = {
        "keys": ["LLM_MODEL_NAME"],
        "source": "settings",
        "ts": time.time(),
    }
    defaults.update(overrides)
    return SettingsChangedEvent(**defaults)


def test_settings_changed_event_rejects_extra_fields():
    try:
        SettingsChangedEvent(keys=["A"], source="settings", ts=1.0, value="extra")
    except ValidationError as exc:
        assert "Extra inputs are not permitted" in str(exc)
    else:
        raise AssertionError("extra field was accepted")


def test_publish_subscribe_roundtrip():
    bus = SettingsEventBus()
    received = []

    def subscriber():
        for event in bus.subscribe(timeout=2.0):
            received.append(event)
            break

    t = threading.Thread(target=subscriber, daemon=True)
    t.start()
    time.sleep(0.05)
    bus.publish(_event(keys=["REPORT_LANGUAGE"]))
    t.join(timeout=3.0)

    assert [event.keys for event in received] == [["REPORT_LANGUAGE"]]


def test_subscriber_cleanup():
    bus = SettingsEventBus()
    assert bus.subscriber_count == 0
    with bus._managed_queue():
        assert bus.subscriber_count == 1
    assert bus.subscriber_count == 0


def test_drop_oldest_when_full():
    bus = SettingsEventBus(maxsize=2)
    with bus._managed_queue() as q:
        bus.publish(_event(keys=["A"]))
        bus.publish(_event(keys=["B"]))
        bus.publish(_event(keys=["C"]))

        assert q.get_nowait().keys == ["B"]
        assert q.get_nowait().keys == ["C"]


def test_module_singleton_and_helper(monkeypatch):
    captured = []
    monkeypatch.setattr(settings_event_bus, "publish", lambda event: captured.append(event))

    publish_settings_changed({"B", "A"}, source="settings")

    assert len(captured) == 1
    assert captured[0].type == "settings.changed"
    assert captured[0].keys == ["A", "B"]
    assert captured[0].source == "settings"
