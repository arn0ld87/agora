"""ModelEventBus — lightweight in-process pub/sub for 'model.active' events (Slice E.1, #213).

This bus is intentionally separate from :class:`SimulationEventBus`:

* ``SimulationEvent`` requires a ``simulation_id`` — LLM calls happen outside
  simulations too (persona generation, report generation, graph builds).
* The simulation bus is designed for Flask↔OASIS subprocess IPC with file- and
  Redis-backed transports.  Here we need transient, in-process fan-out to SSE
  subscribers — a plain queue per subscriber is sufficient.

Design decisions:
* Module-level singleton ``model_event_bus``.
* ``publish`` is non-blocking (fire-and-forget): when a subscriber queue is
  full the *oldest* entry is dropped before inserting the new one so slow
  clients never block LLM callers.
* ``subscribe`` returns a context-manager-based generator that unregisters its
  queue on exit — prevents memory leaks when SSE connections close.
* ``maxsize`` is intentionally small (64) — these events are fast and transient;
  a slow reader should lose old data, not buffer indefinitely.
"""

from __future__ import annotations

import queue
import threading
import time
from contextlib import contextmanager
from typing import Any, Generator, Iterator, Literal

from pydantic import BaseModel, ConfigDict

from ..utils.logger import get_logger

logger = get_logger("agora.model_event_bus")

# Maximum queued events per subscriber before drop-oldest eviction kicks in.
_SUBSCRIBER_MAXSIZE = 64


# ---------------------------------------------------------------------------
# Event model
# ---------------------------------------------------------------------------


class ModelActiveEvent(BaseModel):
    """Published immediately before every LLM API call.

    Consumers (e.g. the SSE endpoint) forward this as a JSON frame so the
    frontend can display which model is currently working.
    """

    model_config = ConfigDict(extra="forbid")

    model: str
    context: Literal[
        "chat",
        "chat_json",
        "embedding",
        "report",
        "persona",
        "graph",
        "unknown",
    ]
    provider: Literal["ollama", "cloud", "openai", "unknown"]
    ts: float
    extra: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Bus
# ---------------------------------------------------------------------------


class ModelEventBus:
    """Threadsafe in-process fan-out bus for :class:`ModelActiveEvent`.

    Callers publish events via :meth:`publish` (non-blocking, fire-and-forget).
    SSE streaming handlers subscribe via :meth:`subscribe` which returns a
    context-manager-aware generator.
    """

    def __init__(self, maxsize: int = _SUBSCRIBER_MAXSIZE) -> None:
        self._maxsize = maxsize
        self._lock = threading.Lock()
        # Each subscriber gets its own queue keyed by object id.
        self._subscribers: dict[int, queue.Queue[ModelActiveEvent]] = {}

    def publish(self, event: ModelActiveEvent) -> None:
        """Publish *event* to all current subscribers.

        Non-blocking: when a subscriber's queue is at capacity the oldest
        event is dropped (``get_nowait`` + ``put_nowait``) before the new
        one is inserted.  A per-subscriber failure never raises to the caller.
        """
        with self._lock:
            queues = list(self._subscribers.values())
        for q in queues:
            try:
                q.put_nowait(event)
            except queue.Full:
                # Drop oldest, insert newest.
                try:
                    q.get_nowait()
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(event)
                except queue.Full:
                    logger.warning(
                        "model_event_bus: subscriber queue still full after drop-oldest; "
                        "event discarded (model=%s)",
                        event.model,
                    )

    @contextmanager
    def _managed_queue(self) -> Generator[queue.Queue[ModelActiveEvent], None, None]:
        """Register a new subscriber queue, yield it, then unregister on exit."""
        q: queue.Queue[ModelActiveEvent] = queue.Queue(maxsize=self._maxsize)
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
        poll_interval: float = 0.2,
    ) -> Iterator[ModelActiveEvent]:
        """Context-manager-safe generator that yields :class:`ModelActiveEvent` items.

        .. note::
            Use inside a ``with`` block or via :meth:`_managed_queue` directly
            to guarantee queue cleanup.  The SSE endpoint uses the low-level
            :meth:`_managed_queue` for precise lifecycle management.

        Args:
            timeout: Seconds of total streaming time (``None`` = infinite).
            poll_interval: How long to block on each ``queue.get`` before
                yielding to the heartbeat / timeout check.
        """
        with self._managed_queue() as q:
            deadline = None if timeout is None else time.monotonic() + timeout
            while True:
                if deadline is not None and time.monotonic() >= deadline:
                    return
                remaining = (
                    poll_interval
                    if deadline is None
                    else min(poll_interval, max(0.0, deadline - time.monotonic()))
                )
                try:
                    event = q.get(timeout=remaining)
                    yield event
                except queue.Empty:
                    continue

    @property
    def subscriber_count(self) -> int:
        """Number of currently active subscribers (test helper)."""
        with self._lock:
            return len(self._subscribers)


# ---------------------------------------------------------------------------
# Module-level singleton
# ---------------------------------------------------------------------------

model_event_bus: ModelEventBus = ModelEventBus()

__all__ = [
    "ModelActiveEvent",
    "ModelEventBus",
    "model_event_bus",
]
