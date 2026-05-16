"""Cooperative Cancel-Flag für laufende Simulation-Runs.

Design: Thread-safe in-memory Store (``threading.Event`` pro run_id).
Der Endpoint-Handler setzt das Flag; Worker-Schleifen (SimulationRunner,
ReportAgent) prüfen es zwischen Stage-Boundaries — KEIN hartes Task.cancel().

Idempotenz: ``request_cancel`` mehrfach aufzurufen ist kein Fehler.
``clear_cancel`` wird bei sauberem Run-Start aufgerufen, um alteTFlags
nach einem Neustart nicht zu erben.

Kein Redis, kein File-IO — rein in-process. Falls künftig multi-worker
gebraucht wird, dieses Modul gegen einen Redis-Adapter austauschen ohne
den Aufruf-Interface zu ändern.
"""

from __future__ import annotations

import threading
from typing import Dict

_lock = threading.Lock()
_cancel_flags: Dict[str, threading.Event] = {}


def _get_or_create(run_id: str) -> threading.Event:
    with _lock:
        if run_id not in _cancel_flags:
            _cancel_flags[run_id] = threading.Event()
        return _cancel_flags[run_id]


def request_cancel(run_id: str) -> None:
    """Setze das Cancel-Flag für ``run_id``.

    Idempotent — mehrfach aufrufen ist kein Fehler.
    """
    _get_or_create(run_id).set()


def is_cancel_requested(run_id: str) -> bool:
    """Liefert ``True``, wenn ``request_cancel(run_id)`` mindestens einmal aufgerufen wurde."""
    with _lock:
        event = _cancel_flags.get(run_id)
    return event is not None and event.is_set()


def clear_cancel(run_id: str) -> None:
    """Lösche das Cancel-Flag für ``run_id`` (z. B. vor einem Neustart).

    Idempotent — auch wenn kein Flag existiert kein Fehler.
    """
    with _lock:
        event = _cancel_flags.pop(run_id, None)
    if event is not None:
        event.clear()


__all__ = [
    "request_cancel",
    "is_cancel_requested",
    "clear_cancel",
]
