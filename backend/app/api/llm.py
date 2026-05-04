"""LLM model-active SSE stream (Slice E.1, Issue #213).

Streams :class:`~app.services.model_event_bus.ModelActiveEvent` events as
Server-Sent Events so the frontend can display which LLM is currently working.

Endpoint
--------
    GET /api/llm/model-stream?ticket=<signed>

Auth
----
Signed ticket with scope ``"llm-stream"`` (issued via
``POST /api/auth/ticket`` → ``{"scope": "llm-stream"}``).

Without a valid ticket the endpoint returns 401 JSON.  SSE connections
cannot carry ``Authorization`` headers (``EventSource`` browser API), so
the signed-ticket pattern is required.  Tickets are **non-single-use** so
``EventSource`` reconnects within the TTL work without requesting a new
ticket.

Frame format
------------
::

    retry: 5000\\n\\n
    id: <uuid>\\n
    data: <ModelActiveEvent JSON>\\n\\n
    : heartbeat\\n\\n          (every 15 s when idle)
"""

from __future__ import annotations

import queue as _queue_mod
import time
import uuid

from flask import Response, stream_with_context

from . import llm_bp
from ..utils.auth import allow_ticket_auth
from ..utils.logger import get_logger

logger = get_logger("agora.api.llm")

_SSE_RETRY_MS = 5000
_HEARTBEAT_SEC = 15.0
_POLL_INTERVAL = 0.2

_TICKET_SCOPE = "llm-stream"


@llm_bp.route("/model-stream", methods=["GET"])
@allow_ticket_auth(lambda: _TICKET_SCOPE, single_use=False)
def model_stream():
    """SSE endpoint: stream ModelActiveEvent frames.

    Auth: signed ticket with scope ``llm-stream`` via ``?ticket=``, or the
    standard bearer token via ``X-Agora-Token`` / ``Authorization: Bearer``.
    The ``@allow_ticket_auth`` decorator instructs the blueprint guard to
    accept ``?ticket=<signed>`` with ``single_use=False`` so EventSource
    reconnects within the ticket TTL succeed without a new ticket.
    """
    from ..services.model_event_bus import model_event_bus

    @stream_with_context
    def gen():
        yield f"retry: {_SSE_RETRY_MS}\n\n"
        with model_event_bus._managed_queue() as q:
            last_heartbeat = time.monotonic()
            while True:
                now = time.monotonic()
                try:
                    event = q.get(timeout=_POLL_INTERVAL)
                    frame_id = uuid.uuid4().hex
                    data = event.model_dump_json()
                    yield f"id: {frame_id}\ndata: {data}\n\n"
                    last_heartbeat = now
                except _queue_mod.Empty:
                    if now - last_heartbeat >= _HEARTBEAT_SEC:
                        yield ": heartbeat\n\n"
                        last_heartbeat = now

    headers = {
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(gen(), mimetype="text/event-stream", headers=headers)
