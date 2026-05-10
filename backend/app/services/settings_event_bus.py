"""In-process event bus for runtime settings changes.

The Settings API persists operator changes immediately. This bus publishes a
small metadata-only event after successful writes so in-process consumers can
refresh cached runtime settings without polling.
"""

from __future__ import annotations

import queue
import threading
import time
from collections.abc import Iterable
from contextlib import contextmanager
from typing import Generator, Iterator, Literal

from pydantic import BaseModel, ConfigDict

from ..utils.logger import get_logger

logger = get_logger("agora.settings_event_bus")

_SUBSCRIBER_MAXSIZE = 64


class SettingsChangedEvent(BaseModel):
    """Metadata-only notification for a successful settings write."""

    model_config = ConfigDict(extra="forbid")

    type: Literal["settings.changed"] = "settings.changed"
    keys: list[str]
    source: Literal["settings", "settings.secrets"]
    ts: float


class SettingsEventBus:
    """Threadsafe non-blocking fan-out bus for settings change events."""

    def __init__(self, maxsize: int = _SUBSCRIBER_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._lock = threading.Lock()
        self._subscribers: dict[int, queue.Queue[SettingsChangedEvent]] = {}

    def publish(self, event: SettingsChangedEvent) -> None:
        """Publish *event* without blocking settings writes."""
        with self._lock:
            queues = list(self._subscribers.values())
        for q in queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(event)
                except queue.Full:
                    logger.warning(
                        "settings_event_bus: subscriber queue still full after drop-oldest; "
                        "event discarded (keys=%s)",
                        event.keys,
                    )

    @contextmanager
    def _managed_queue(self) -> Generator[queue.Queue[SettingsChangedEvent], None, None]:
        q: queue.Queue[SettingsChangedEvent] = queue.Queue(maxsize=self._maxsize)
        qid = id(q)
        with self._lock:
            self._subscribers[qid] = q
        try:
            yield q
        finally:
            with self._lock:
                self._subscribers.pop(qid, None)

    def subscribe(
        self,
        *,
        timeout: float | None = None,
    ) -> Iterator[SettingsChangedEvent]:
        """Yield settings change events until *timeout* expires."""
        with self._managed_queue() as q:
            if timeout is None:
                while True:
                    yield q.get()

            deadline = time.monotonic() + timeout
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return
                try:
                    yield q.get(timeout=remaining)
                except queue.Empty:
                    return

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)


settings_event_bus: SettingsEventBus = SettingsEventBus()


def publish_settings_changed(
    keys: Iterable[str],
    *,
    source: Literal["settings", "settings.secrets"],
) -> None:
    """Publish a ``settings.changed`` event for the changed keys.

    Only key names and the source endpoint are sent; values are intentionally
    omitted so secret writes never leak through the event stream.
    """
    changed_keys = sorted({str(key) for key in keys})
    if not changed_keys:
        return
    settings_event_bus.publish(
        SettingsChangedEvent(keys=changed_keys, source=source, ts=time.time())
    )


__all__ = [
    "SettingsChangedEvent",
    "SettingsEventBus",
    "publish_settings_changed",
    "settings_event_bus",
]
