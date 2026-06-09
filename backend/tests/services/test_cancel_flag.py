"""Tests für die Cancel-Flag-Mechanik (app.services.sim.cancel_flag).

Abgedeckte Szenarien:
  1  request_cancel + is_cancel_requested round-trip
  2  Idempotenz: request_cancel mehrfach aufrufen ist kein Fehler
  3  clear_cancel entfernt das Flag
  4  is_cancel_requested auf unbekannte run_id liefert False (kein Fehler)
  5  Verschiedene run_ids sind unabhängig voneinander
  6  Thread-Sicherheit: gleichzeitige Writes + Reads konsistent
"""

from __future__ import annotations

import threading
import uuid


from app.services.sim.cancel_flag import (
    clear_cancel,
    is_cancel_requested,
    request_cancel,
)


def _unique_id() -> str:
    return f"run_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------------------
# Test 1: round-trip
# ---------------------------------------------------------------------------


def test_request_cancel_is_cancel_requested_roundtrip():
    run_id = _unique_id()
    clear_cancel(run_id)  # sauber starten

    assert not is_cancel_requested(run_id)
    request_cancel(run_id)
    assert is_cancel_requested(run_id)

    clear_cancel(run_id)


# ---------------------------------------------------------------------------
# Test 2: Idempotenz
# ---------------------------------------------------------------------------


def test_request_cancel_idempotent():
    run_id = _unique_id()
    clear_cancel(run_id)

    request_cancel(run_id)
    request_cancel(run_id)  # zweiter Aufruf darf kein Fehler werfen
    request_cancel(run_id)

    assert is_cancel_requested(run_id)

    clear_cancel(run_id)


# ---------------------------------------------------------------------------
# Test 3: clear_cancel entfernt Flag
# ---------------------------------------------------------------------------


def test_clear_cancel_removes_flag():
    run_id = _unique_id()
    request_cancel(run_id)
    assert is_cancel_requested(run_id)

    clear_cancel(run_id)
    assert not is_cancel_requested(run_id)


# ---------------------------------------------------------------------------
# Test 4: is_cancel_requested auf unbekannte ID — kein Fehler, False
# ---------------------------------------------------------------------------


def test_is_cancel_requested_unknown_id_returns_false():
    run_id = _unique_id()
    # Nie aufgerufen — Flag existiert nicht
    assert not is_cancel_requested(run_id)


# ---------------------------------------------------------------------------
# Test 5: Verschiedene run_ids sind unabhängig
# ---------------------------------------------------------------------------


def test_cancel_flags_are_independent():
    id_a = _unique_id()
    id_b = _unique_id()
    clear_cancel(id_a)
    clear_cancel(id_b)

    request_cancel(id_a)

    assert is_cancel_requested(id_a)
    assert not is_cancel_requested(id_b)

    clear_cancel(id_a)


# ---------------------------------------------------------------------------
# Test 6: Thread-Sicherheit
# ---------------------------------------------------------------------------


def test_cancel_flag_thread_safety():
    """Gleichzeitige request_cancel + is_cancel_requested sind konsistent."""
    run_id = _unique_id()
    clear_cancel(run_id)

    results: list[bool] = []
    errors: list[Exception] = []

    def writer():
        try:
            request_cancel(run_id)
        except Exception as exc:
            errors.append(exc)

    def reader():
        try:
            # Ergebnis ist True oder False — beides valide
            results.append(is_cancel_requested(run_id))
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer) for _ in range(10)]
    threads += [threading.Thread(target=reader) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5)

    assert not errors, f"Thread-Fehler: {errors}"
    # Nach allen Writern muss das Flag gesetzt sein
    assert is_cancel_requested(run_id)

    clear_cancel(run_id)
