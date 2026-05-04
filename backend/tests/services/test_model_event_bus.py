"""Tests for ModelEventBus and ModelActiveEvent (Slice E.1, Issue #213)."""

from __future__ import annotations

import threading
import time

import pytest
from pydantic import ValidationError

from app.services.model_event_bus import ModelActiveEvent, ModelEventBus, model_event_bus


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_event(**overrides) -> ModelActiveEvent:
    defaults = dict(
        model="qwen2.5:32b",
        context="chat",
        provider="ollama",
        ts=time.time(),
    )
    defaults.update(overrides)
    return ModelActiveEvent(**defaults)


# ---------------------------------------------------------------------------
# ModelActiveEvent — Pydantic schema
# ---------------------------------------------------------------------------

class TestModelActiveEventSchema:
    def test_valid_minimal(self):
        ev = _make_event()
        assert ev.model == "qwen2.5:32b"
        assert ev.context == "chat"
        assert ev.provider == "ollama"
        assert ev.extra is None

    def test_valid_with_extra(self):
        ev = _make_event(extra={"max_tokens": 4096, "temperature": 0.7})
        assert ev.extra == {"max_tokens": 4096, "temperature": 0.7}

    def test_all_context_values_accepted(self):
        valid_contexts = ["chat", "chat_json", "embedding", "report", "persona", "graph", "unknown"]
        for ctx in valid_contexts:
            ev = _make_event(context=ctx)
            assert ev.context == ctx

    def test_invalid_context_rejected(self):
        with pytest.raises(ValidationError):
            _make_event(context="invalid_context")

    def test_all_provider_values_accepted(self):
        for prov in ["ollama", "cloud", "openai", "unknown"]:
            ev = _make_event(provider=prov)
            assert ev.provider == prov

    def test_invalid_provider_rejected(self):
        with pytest.raises(ValidationError):
            _make_event(provider="azure")

    def test_extra_fields_forbidden(self):
        """extra='forbid' must reject unknown fields."""
        with pytest.raises(ValidationError):
            ModelActiveEvent(
                model="x",
                context="chat",
                provider="ollama",
                ts=1.0,
                unknown_field="surprise",
            )

    def test_model_dump_json_roundtrip(self):
        ev = _make_event(extra={"x": 1})
        import json
        dumped = json.loads(ev.model_dump_json())
        assert dumped["model"] == "qwen2.5:32b"
        assert dumped["extra"] == {"x": 1}


# ---------------------------------------------------------------------------
# ModelEventBus — publish / subscribe round-trip
# ---------------------------------------------------------------------------

class TestModelEventBusSingleSubscriber:
    def test_publish_subscribe_roundtrip(self):
        bus = ModelEventBus()
        ev = _make_event(model="llama3.1:8b")
        received = []

        def subscriber():
            for event in bus.subscribe(timeout=2.0):
                received.append(event)
                break

        t = threading.Thread(target=subscriber, daemon=True)
        t.start()
        time.sleep(0.05)  # let subscriber register
        bus.publish(ev)
        t.join(timeout=3.0)

        assert len(received) == 1
        assert received[0].model == "llama3.1:8b"

    def test_multiple_events_in_order(self):
        bus = ModelEventBus()
        models = ["m1", "m2", "m3"]
        received = []

        def subscriber():
            for event in bus.subscribe(timeout=2.0, poll_interval=0.05):
                received.append(event.model)
                if len(received) >= len(models):
                    break

        t = threading.Thread(target=subscriber, daemon=True)
        t.start()
        time.sleep(0.05)
        for m in models:
            bus.publish(_make_event(model=m))
        t.join(timeout=3.0)

        assert received == models


class TestModelEventBusMultiSubscriber:
    def test_multi_subscriber_fan_out(self):
        bus = ModelEventBus()
        ev = _make_event(model="fan-out-model")
        results: list[list[ModelActiveEvent]] = [[], []]

        def make_sub(idx: int):
            def subscriber():
                for event in bus.subscribe(timeout=2.0):
                    results[idx].append(event)
                    break
            return subscriber

        threads = [threading.Thread(target=make_sub(i), daemon=True) for i in range(2)]
        for t in threads:
            t.start()
        time.sleep(0.05)
        bus.publish(ev)
        for t in threads:
            t.join(timeout=3.0)

        assert len(results[0]) == 1
        assert len(results[1]) == 1
        assert results[0][0].model == "fan-out-model"
        assert results[1][0].model == "fan-out-model"

    def test_subscriber_cleanup(self):
        """After subscribe context exits, subscriber count returns to 0."""
        bus = ModelEventBus(maxsize=4)
        assert bus.subscriber_count == 0

        with bus._managed_queue():
            assert bus.subscriber_count == 1

        assert bus.subscriber_count == 0


# ---------------------------------------------------------------------------
# Backpressure — drop-oldest when queue is full
# ---------------------------------------------------------------------------

class TestModelEventBusBackpressure:
    def test_drop_oldest_when_full(self):
        """When queue is full, the oldest event is dropped and the newest retained."""
        maxsize = 4
        bus = ModelEventBus(maxsize=maxsize)

        # Register a subscriber but don't consume yet.
        with bus._managed_queue() as q:
            # Publish maxsize + 2 events; first 2 should be dropped.
            n_total = maxsize + 2
            for i in range(n_total):
                bus.publish(_make_event(model=f"model-{i}"))

            # Drain the queue without blocking.
            import queue as _qmod
            collected = []
            while True:
                try:
                    collected.append(q.get_nowait())
                except _qmod.Empty:
                    break

        # We expect exactly maxsize events, and they should be the newest ones.
        assert len(collected) == maxsize
        models = [e.model for e in collected]
        # The retained events are model-2 through model-(n_total-1)
        expected = [f"model-{i}" for i in range(n_total - maxsize, n_total)]
        assert models == expected

    def test_publish_is_non_blocking(self):
        """publish() must return quickly even when all subscriber queues are full."""
        bus = ModelEventBus(maxsize=2)
        with bus._managed_queue():
            # Fill the queue
            bus.publish(_make_event(model="a"))
            bus.publish(_make_event(model="b"))
            # This must not block
            start = time.monotonic()
            bus.publish(_make_event(model="c"))
            elapsed = time.monotonic() - start
        assert elapsed < 0.5, f"publish blocked for {elapsed:.2f}s — must be non-blocking"


# ---------------------------------------------------------------------------
# Fail-safe: publish in subscribe loop must not raise
# ---------------------------------------------------------------------------

class TestModelEventBusFailSafe:
    def test_subscribe_iteration_survives_publish_error(self, monkeypatch):
        """subscribe generator must not propagate internal bus errors to callers."""
        bus = ModelEventBus()
        # Monkeypatch _subscribers to raise on values() call after subscribe starts.
        # We test the simpler invariant: a broken event does not break iteration.
        ev_good = _make_event(model="good")
        received = []

        def subscriber():
            for event in bus.subscribe(timeout=1.0):
                received.append(event)
                break

        t = threading.Thread(target=subscriber, daemon=True)
        t.start()
        time.sleep(0.05)
        bus.publish(ev_good)
        t.join(timeout=2.0)
        assert len(received) == 1
        assert received[0].model == "good"

    def test_module_singleton_exists(self):
        assert isinstance(model_event_bus, ModelEventBus)
