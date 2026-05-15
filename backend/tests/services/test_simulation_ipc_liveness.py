"""PID-Liveness-Check für SimulationIPCClient.check_env_alive (Smoke-Live 2026-05-15).

Wenn der OASIS-Subprozess crasht oder gekillt wird, bleibt ``env_status.json``
beim letzten geschriebenen Status (``alive``) hängen. Der Client muss
zusätzlich per ``os.kill(pid, 0)`` prüfen, ob die PID noch existiert,
sonst läuft Report-Agent ``interview_agents`` 180 s ins IPC-Timeout.
"""

from __future__ import annotations

import os
from unittest.mock import patch


from app.services.simulation_ipc import SimulationIPCClient


class _StubStore:
    def __init__(self, status: dict | None) -> None:
        self._status = status
        self.read_calls: list[tuple[str, str]] = []

    def read_json(self, sim_id: str, name: str, default=None):
        self.read_calls.append((sim_id, name))
        return self._status if self._status is not None else default


def _make_client(status: dict | None) -> SimulationIPCClient:
    client = SimulationIPCClient.__new__(SimulationIPCClient)
    client.simulation_id = "sim-test-001"
    client._store = _StubStore(status)  # type: ignore[attr-defined]
    return client


def test_check_env_alive_returns_false_when_no_status_file() -> None:
    client = _make_client(status=None)
    assert client.check_env_alive() is False


def test_check_env_alive_returns_false_when_status_not_alive() -> None:
    client = _make_client(status={"status": "stopped", "pid": 9999})
    assert client.check_env_alive() is False


def test_check_env_alive_returns_true_when_pid_alive() -> None:
    """Status=alive + PID des aktuellen Test-Prozesses → True (self-test)."""
    client = _make_client(status={"status": "alive", "pid": os.getpid()})
    assert client.check_env_alive() is True


def test_check_env_alive_returns_false_when_pid_dead() -> None:
    """Status=alive aber PID gehört keinem laufenden Prozess → False.

    Das ist der Live-Bug 2026-05-15: OASIS-Subprozess crashte ohne
    Status-Update, ``check_env_alive`` glaubte blind dem File und der
    Report-Agent hing 180 s im IPC-Timeout.
    """
    # Sehr hohe PID, die garantiert nicht existiert.
    client = _make_client(status={"status": "alive", "pid": 999999999})
    with patch("app.services.simulation_ipc.os.kill", side_effect=ProcessLookupError):
        assert client.check_env_alive() is False


def test_check_env_alive_returns_true_when_pid_missing() -> None:
    """Alter Status-File ohne PID-Feld (Legacy) → File-only-Check, bleibt True."""
    client = _make_client(status={"status": "alive"})
    assert client.check_env_alive() is True


def test_check_env_alive_returns_true_when_pid_not_int() -> None:
    """PID-Feld mit nicht-int-Wert wird ignoriert (defensiv)."""
    client = _make_client(status={"status": "alive", "pid": "not-a-pid"})
    assert client.check_env_alive() is True


def test_check_env_alive_handles_permission_error() -> None:
    """``PermissionError`` von ``os.kill`` → Prozess existiert, treat as alive."""
    client = _make_client(status={"status": "alive", "pid": 1})
    with patch("app.services.simulation_ipc.os.kill", side_effect=PermissionError):
        assert client.check_env_alive() is True
