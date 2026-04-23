"""Server-Sent Events stream for simulation run status (Issue #9 Phase C).

Bridges the :class:`SimulationEventBus` CHANNEL_STATE / CHANNEL_CONTROL
channels to the browser as an ``EventSource`` feed so the frontend can
drop its 2–3 s polling loop for run-state and pause flags.

Stream contract:

* ``event: state`` — full run-state snapshot (same shape as
  ``GET /api/simulation/<id>/run-status``)
* ``event: control`` — ``{"paused": bool, "stop_requested": bool, ...}``
* ``event: ping`` — heartbeat every 15 s so clients and proxies can detect
  dead connections

Auth: the regular bearer-token guard applies via the blueprint's
``before_request``. Browsers cannot set custom headers on ``EventSource``
so a ``?token=...`` query override is accepted too, validated against the
same ``AGORA_AUTH_TOKEN`` constant.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Dict, Iterator, Optional

from flask import Response, current_app, stream_with_context

from ..services.event_bus import (
    CHANNEL_CONTROL,
    CHANNEL_STATE,
    SimulationEvent,
    SimulationEventBus,
)
from ..utils.api_responses import json_error
from ..utils.logger import get_logger
from ..utils.validation import validate_simulation_id
from . import simulation_bp

logger = get_logger("agora.simulation_stream")

# SSE-specific knobs. Heartbeat keeps connections alive behind NAT/proxy
# timeouts (typical 30–60 s). Client-side poll falls back on reconnect.
_HEARTBEAT_SECONDS = 15.0
_POLL_INTERVAL = 0.5


def _sse_format(event: str, data: Any, event_id: Optional[str] = None) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    out = f"event: {event}\n"
    if event_id:
        out += f"id: {event_id}\n"
    out += f"data: {payload}\n\n"
    return out


def _event_to_sse(event_name: str, evt: SimulationEvent) -> str:
    return _sse_format(
        event_name,
        {
            "type": evt.type,
            "simulation_id": evt.simulation_id,
            "payload": evt.payload,
            "ts": evt.ts,
        },
        event_id=evt.ts or None,
    )


def _drain_channel(
    bus: SimulationEventBus,
    simulation_id: str,
    channel: str,
    q: "queue.Queue[Dict[str, Any]]",
    stop: threading.Event,
) -> None:
    """Background drainer — forwards bus events into the shared queue.

    One thread per subscribed channel. The generator-based subscribe API
    cleans up the underlying pub/sub on exit (``try/finally`` in the
    adapter), so setting ``stop`` and letting the poll cycle expire is
    enough to release resources.
    """
    try:
        for evt in bus.subscribe(
            simulation_id, channel, timeout=None, poll_interval=_POLL_INTERVAL
        ):
            if stop.is_set():
                return
            q.put({"channel": channel, "event": evt})
    except Exception:  # noqa: BLE001
        logger.exception("Stream drainer crashed for %s/%s", simulation_id, channel)


def _stream(simulation_id: str) -> Iterator[str]:
    bus: SimulationEventBus = current_app.extensions["event_bus"]
    q: "queue.Queue[Dict[str, Any]]" = queue.Queue()
    stop = threading.Event()
    threads = [
        threading.Thread(
            target=_drain_channel,
            args=(bus, simulation_id, channel, q, stop),
            name=f"sse-{simulation_id}-{channel}",
            daemon=True,
        )
        for channel in (CHANNEL_STATE, CHANNEL_CONTROL)
    ]
    for t in threads:
        t.start()

    yield _sse_format("hello", {"simulation_id": simulation_id, "ts": time.time()})
    last_heartbeat = time.monotonic()
    try:
        while True:
            try:
                msg = q.get(timeout=1.0)
            except queue.Empty:
                msg = None
            if msg is not None:
                channel = msg["channel"]
                evt: SimulationEvent = msg["event"]
                event_name = "state" if channel == CHANNEL_STATE else "control"
                yield _event_to_sse(event_name, evt)
            now = time.monotonic()
            if now - last_heartbeat >= _HEARTBEAT_SECONDS:
                yield _sse_format("ping", {"ts": time.time()})
                last_heartbeat = now
    finally:
        stop.set()


@simulation_bp.route('/<simulation_id>/stream', methods=['GET'])
def simulation_stream(simulation_id: str):
    """SSE endpoint for live run-state + control updates."""
    if not validate_simulation_id(simulation_id):
        return json_error("Invalid simulation_id format")

    response = Response(
        stream_with_context(_stream(simulation_id)),
        mimetype="text/event-stream",
    )
    # Disable proxy buffering for nginx and friends; keep-alive is implicit.
    response.headers["Cache-Control"] = "no-cache, no-transform"
    response.headers["X-Accel-Buffering"] = "no"
    response.headers["Connection"] = "keep-alive"
    return response
