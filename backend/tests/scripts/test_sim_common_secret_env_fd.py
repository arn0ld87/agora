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

from _sim_common import (  # noqa: E402
    is_workspace_credential_scope,
    load_project_env,
    load_workspace_secret_env_from_fd,
)


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


# ---------------------------------------------------------------------------
# Finding H5 (#1688): AGORA_CREDENTIAL_SCOPE=workspace fail-closed behaviour
# ---------------------------------------------------------------------------


def _bind_workspace_scope(monkeypatch):
    monkeypatch.setenv("AGORA_CREDENTIAL_SCOPE", "workspace")


def test_is_workspace_credential_scope_reads_signal_without_popping(monkeypatch):
    monkeypatch.setenv("AGORA_CREDENTIAL_SCOPE", "workspace")
    assert is_workspace_credential_scope() is True
    # Read-only: repeated calls (unlike the FD var) must keep seeing it.
    assert is_workspace_credential_scope() is True
    assert "AGORA_CREDENTIAL_SCOPE" in os.environ


def test_workspace_scope_exits_nonzero_when_fd_env_var_is_absent(monkeypatch):
    """A workspace-scoped run must ALWAYS get a pipe — a missing
    AGORA_SECRET_ENV_FD is now a hard failure, not a silent operator-style
    no-op."""
    _bind_workspace_scope(monkeypatch)
    monkeypatch.delenv("AGORA_SECRET_ENV_FD", raising=False)

    with pytest.raises(SystemExit) as exc_info:
        load_workspace_secret_env_from_fd()
    assert "AGORA_SECRET_ENV_FD" in str(exc_info.value)


def test_workspace_scope_exits_nonzero_on_unreadable_fd(monkeypatch):
    _bind_workspace_scope(monkeypatch)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", "999999")  # never a valid open FD

    with pytest.raises(SystemExit):
        load_workspace_secret_env_from_fd()


def test_workspace_scope_exits_nonzero_on_empty_payload(monkeypatch):
    _bind_workspace_scope(monkeypatch)
    read_fd, write_fd = os.pipe()
    os.close(write_fd)  # EOF immediately, no bytes at all
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))

    with pytest.raises(SystemExit):
        load_workspace_secret_env_from_fd()


def test_workspace_scope_exits_nonzero_on_garbage_payload(monkeypatch):
    _bind_workspace_scope(monkeypatch)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"not-json")
    os.close(write_fd)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))

    with pytest.raises(SystemExit):
        load_workspace_secret_env_from_fd()


def test_workspace_scope_exits_nonzero_when_payload_lacks_llm_api_key(monkeypatch):
    """An empty-dict payload (Finding H5: the backend always creates the
    pipe for a workspace run, even with no resolvable key) must still be
    rejected — a JSON object without LLM_API_KEY is a workspace run with
    no usable credential, not a valid one."""
    _bind_workspace_scope(monkeypatch)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, json.dumps({}).encode("utf-8"))
    os.close(write_fd)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))

    with pytest.raises(SystemExit) as exc_info:
        load_workspace_secret_env_from_fd()
    assert "LLM_API_KEY" in str(exc_info.value)


def test_workspace_scope_exit_message_never_contains_the_secret(monkeypatch):
    """The fail-closed exit message names env VAR NAMES only — never the
    secret payload bytes themselves."""
    _bind_workspace_scope(monkeypatch)
    read_fd, write_fd = os.pipe()
    os.write(write_fd, b"super-secret-value-should-not-leak")
    os.close(write_fd)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))

    with pytest.raises(SystemExit) as exc_info:
        load_workspace_secret_env_from_fd()
    assert "super-secret-value-should-not-leak" not in str(exc_info.value)


def test_workspace_scope_accepts_valid_payload_and_pops_boost_keys(monkeypatch):
    """The happy path still works, AND boost is force-disabled up front —
    independent of whether a boost env var happened to be present."""
    _bind_workspace_scope(monkeypatch)
    monkeypatch.setenv("LLM_BOOST_API_KEY", "operator-boost-key")
    monkeypatch.setenv("LLM_BOOST_BASE_URL", "https://boost.example/v1")
    monkeypatch.setenv("LLM_BOOST_MODEL_NAME", "boost-model")
    monkeypatch.delenv("LLM_API_KEY", raising=False)

    read_fd, write_fd = os.pipe()
    os.write(write_fd, json.dumps({"LLM_API_KEY": "ws-secret"}).encode("utf-8"))
    os.close(write_fd)
    monkeypatch.setenv("AGORA_SECRET_ENV_FD", str(read_fd))

    load_workspace_secret_env_from_fd()

    assert os.environ["LLM_API_KEY"] == "ws-secret"
    assert "LLM_BOOST_API_KEY" not in os.environ
    assert "LLM_BOOST_BASE_URL" not in os.environ
    assert "LLM_BOOST_MODEL_NAME" not in os.environ


def test_operator_scope_ignores_missing_fd_unchanged(monkeypatch):
    """Without the AGORA_CREDENTIAL_SCOPE=workspace signal, a missing FD
    stays the unchanged legacy no-op (operator runs never set it)."""
    monkeypatch.delenv("AGORA_CREDENTIAL_SCOPE", raising=False)
    monkeypatch.delenv("AGORA_SECRET_ENV_FD", raising=False)

    load_workspace_secret_env_from_fd()  # must not raise


def test_load_project_env_skipped_for_workspace_scope(monkeypatch, tmp_path):
    """Finding H5: a workspace-scoped run must never load the operator's
    .env — load_project_env becomes a no-op instead of reading it off disk."""
    _bind_workspace_scope(monkeypatch)
    (tmp_path / ".env").write_text("LLM_API_KEY=operator-dotenv-key\n", encoding="utf-8")
    script_file = tmp_path / "backend" / "scripts" / "run_parallel_simulation.py"
    script_file.parent.mkdir(parents=True)
    script_file.write_text("", encoding="utf-8")

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = load_project_env(str(script_file))

    assert result is None
    assert "LLM_API_KEY" not in os.environ


def test_load_project_env_still_loads_dotenv_for_operator_scope(monkeypatch, tmp_path):
    """Unchanged legacy behaviour for an operator run (no scope signal)."""
    monkeypatch.delenv("AGORA_CREDENTIAL_SCOPE", raising=False)
    (tmp_path / ".env").write_text("LLM_API_KEY=operator-dotenv-key\n", encoding="utf-8")
    script_file = tmp_path / "backend" / "scripts" / "run_parallel_simulation.py"
    script_file.parent.mkdir(parents=True)
    script_file.write_text("", encoding="utf-8")

    monkeypatch.delenv("LLM_API_KEY", raising=False)
    result = load_project_env(str(script_file))

    assert result is not None
    assert os.environ.get("LLM_API_KEY") == "operator-dotenv-key"
