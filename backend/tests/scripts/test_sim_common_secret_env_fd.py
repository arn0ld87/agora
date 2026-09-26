"""Finding B1 (Security-Review 2026-09-26, #1688): das Runner-Skript liest
ein per Pipe-FD uebergebenes Workspace-Secret einmalig ins Prozess-Env statt
es ueber die OS-Subprozess-Umgebung entgegenzunehmen — jeder Prozess mit
demselben OS-User kann ``/proc/<pid>/environ`` eines Geschwisterprozesses
lesen, auf einer Demo-Instanz potenziell die Simulation eines fremden
Workspace.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import load_workspace_secret_env_from_fd  # noqa: E402


def test_reads_secret_payload_from_fd_into_environ(monkeypatch):
    read_fd, write_fd = os.pipe()
    os.write(write_fd, json.dumps({"LLM_API_KEY": "ws-secret", "OPENAI_API_KEY": "ws-secret"}).encode("utf-8"))
    os.close(write_fd)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    load_workspace_secret_env_from_fd()

    assert os.environ["LLM_API_KEY"] == "ws-secret"
    assert os.environ["OPENAI_API_KEY"] == "ws-secret"
    # Die FD-Nummer selbst ist kein Secret, wird aber trotzdem entfernt —
    # sie zeigt nach dem Lesen auf eine bereits geschlossene FD.
    assert "AGORA_SECRET_ENV_FD" not in os.environ


def test_no_op_when_fd_env_var_is_absent(monkeypatch):
    """Operator-Runs setzen ``AGORA_SECRET_ENV_FD`` nie — No-Op, unveraendertes
    Legacy-Verhalten."""
    monkeypatch.delenv("AGORA_SECRET_ENV_FD", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "operator-key-from-env")

    load_workspace_secret_env_from_fd()

    assert os.environ["LLM_API_KEY"] == "operator-key-from-env"


def test_closes_fd_and_no_op_on_garbage_payload(monkeypatch):
    """Ein nicht als JSON lesbarer Payload darf den Runner-Start nicht zum
    Absturz bringen — best effort, kein Secret-Leak durch eine Exception mit
    dem rohen Payload im Traceback."""
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"not-json")
    os.close(write_fd)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))

    load_workspace_secret_env_from_fd()

    assert "AGORA_SECRET_ENV_FD" not in os.environ
    with pytest.raises(OSError):
        os.read(read_fd, 1)  # FD wurde geschlossen
