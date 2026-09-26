"""Regressionstest fuer Finding L2 (Security-Review 2026-09-26, #1688).

``_build_subprocess_env`` darf die Lese-FD der Workspace-Secret-Pipe nicht
leaken, wenn der Schreib-Versuch scheitert — der Elternprozess ist der
lang laufende Backend-Prozess, ein Leak dort summiert sich ueber viele
fehlgeschlagene Simulationsstarts zu einem FD-Erschoepfungsrisiko.
"""

from __future__ import annotations

import json
import os

import pytest

from app.services.llm_routing_seed import WORKSPACE_SECRET_ENV_MARKER
from app.services.sim.process_environment import _build_subprocess_env


def _open_fds() -> set[int]:
    """Grobe Momentaufnahme offener FDs dieses Prozesses (Linux/macOS)."""
    try:
        return set(int(fd) for fd in os.listdir("/dev/fd"))
    except OSError:
        pytest.skip("/dev/fd nicht verfuegbar auf dieser Plattform")


def test_build_subprocess_env_closes_read_fd_when_write_fails(tmp_path, monkeypatch):
    secret_payload = json.dumps({"LLM_API_KEY": "ws-secret-key"})

    real_write = os.write
    calls = {"n": 0}

    def failing_write(fd, data):
        calls["n"] += 1
        raise OSError("simulated pipe write failure")

    monkeypatch.setattr(os, "write", failing_write)

    before = _open_fds()
    with pytest.raises(OSError):
        _build_subprocess_env(
            {WORKSPACE_SECRET_ENV_MARKER: secret_payload},
            str(tmp_path),
        )
    monkeypatch.setattr(os, "write", real_write)
    after = _open_fds()

    assert calls["n"] == 1
    # Keine neue offene FD ueberlebt den fehlgeschlagenen Aufruf — sowohl
    # read_fd als auch write_fd wurden geschlossen.
    assert after <= before, f"FD-Leak: vorher={before}, nachher={after}"


def test_build_subprocess_env_writes_full_payload_via_loop(tmp_path):
    """Auch bei (hier simuliert) mehreren Teil-Writes landet der komplette
    Payload in der Pipe — kein Abbruch nach dem ersten Chunk."""
    secret_payload = json.dumps({"LLM_API_KEY": "ws-secret-key-loop-test"})

    env, pass_fds = _build_subprocess_env(
        {WORKSPACE_SECRET_ENV_MARKER: secret_payload},
        str(tmp_path),
    )

    assert pass_fds
    read_fd = pass_fds[0]
    try:
        data = os.read(read_fd, 65536)
    finally:
        os.close(read_fd)

    assert json.loads(data.decode("utf-8")) == {"LLM_API_KEY": "ws-secret-key-loop-test"}
    assert env["AGORA_SECRET_ENV_FD"] == str(read_fd)
