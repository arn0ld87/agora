"""Tests for app.services.sim.process_manager.

M11 Phase 5 PR 5 — verifies extracted process-manager functions.

Design notes:
- subprocess.Popen and threading.Thread are mocked (no real subprocesses).
- Tests target the module-level functions in process_manager directly.
- No monkeypatch.setattr(SimulationRunner, ...) — the refactor rebuilds those.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_process(*, poll_return: Any = None) -> MagicMock:
    """Return a mock subprocess.Popen object.

    poll_return=None  → process is still running.
    poll_return=0     → process exited with code 0.
    """
    p = MagicMock()
    p.pid = 12345
    p.poll.return_value = poll_return
    return p


# ---------------------------------------------------------------------------
# _compute_oasis_db_path
# ---------------------------------------------------------------------------


class TestComputeOasisDbPath:
    def test_returns_sim_specific_path(self, tmp_path):
        from app.services.sim.process_manager import _compute_oasis_db_path

        sim_dir = str(tmp_path / "sim_abc")
        os.makedirs(sim_dir)
        db_path = _compute_oasis_db_path(sim_dir)

        assert "oasis_db" in db_path
        assert db_path.endswith("social_media.db") or db_path.endswith(
            "social_media.db"
        )

    def test_creates_directory(self, tmp_path):
        """_compute_oasis_db_path must create the oasis_db sub-directory."""
        from app.services.sim.process_manager import _compute_oasis_db_path

        sim_dir = str(tmp_path / "sim_create_dir")
        os.makedirs(sim_dir)
        db_path = _compute_oasis_db_path(sim_dir)

        assert os.path.isdir(os.path.dirname(db_path)), (
            "oasis_db directory must exist before subprocess starts"
        )

    def test_is_idempotent(self, tmp_path):
        from app.services.sim.process_manager import _compute_oasis_db_path

        sim_dir = str(tmp_path / "sim_idem")
        os.makedirs(sim_dir)
        p1 = _compute_oasis_db_path(sim_dir)
        p2 = _compute_oasis_db_path(sim_dir)
        assert p1 == p2


# ---------------------------------------------------------------------------
# _inject_oasis_db_env
# ---------------------------------------------------------------------------


class TestInjectOasisDbEnv:
    def test_no_override_when_already_set(self, tmp_path, monkeypatch):
        """If OASIS_DB_PATH is already in env dict, do not overwrite."""
        from app.services.sim.process_manager import _inject_oasis_db_env

        sim_dir = str(tmp_path / "sim_nooverride")
        os.makedirs(sim_dir)

        env: dict = {"OASIS_DB_PATH": "/explicit/user/path.db"}
        _inject_oasis_db_env(env, sim_dir)

        assert env["OASIS_DB_PATH"] == "/explicit/user/path.db"

    def test_sets_when_unset(self, tmp_path, monkeypatch):
        """When OASIS_DB_PATH is absent, inject a sim-specific path."""
        from app.services.sim.process_manager import _inject_oasis_db_env

        sim_dir = str(tmp_path / "sim_inject")
        os.makedirs(sim_dir)
        monkeypatch.delenv("OASIS_DB_PATH", raising=False)

        env: dict = {}
        _inject_oasis_db_env(env, sim_dir)

        assert "OASIS_DB_PATH" in env
        assert env["OASIS_DB_PATH"].startswith(sim_dir)
        assert env["OASIS_DB_PATH"].endswith("social_media.db")
        assert os.path.isdir(os.path.dirname(env["OASIS_DB_PATH"]))


# ---------------------------------------------------------------------------
# start_simulation security guards
# ---------------------------------------------------------------------------


class TestStartSimulationSecurity:
    def test_rejects_simulation_id_path_traversal_before_io(self, tmp_path):
        from app.services.sim import process_manager

        with pytest.raises(ValueError, match="Invalid simulation_id"):
            process_manager.start_simulation(
                "../escape",
                "parallel",
                run_state_dir=str(tmp_path),
                scripts_dir=str(tmp_path),
                processes={},
                action_queues={},
                monitor_threads={},
                stdout_files={},
                stderr_files={},
                graph_memory_enabled={},
                get_run_state=MagicMock(side_effect=AssertionError("should not read")),
                save_state=MagicMock(),
                on_monitor_start=MagicMock(),
                write_control_state=MagicMock(),
                get_config=MagicMock(),
                config_exists=MagicMock(),
                setup_graph_memory=MagicMock(),
            )


# ---------------------------------------------------------------------------
# terminate_process
# ---------------------------------------------------------------------------


class TestTerminateProcess:
    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_unix_sigterm_path(self):
        """On Unix, terminate_process uses os.killpg(pgid, SIGTERM)."""
        from app.services.sim.process_manager import terminate_process

        mock_process = _make_mock_process(poll_return=None)
        mock_process.pid = 9999

        with (
            patch("os.getpgid", return_value=9999) as mock_getpgid,
            patch("os.killpg") as mock_killpg,
            patch.object(mock_process, "wait"),
        ):
            terminate_process(mock_process, "sim_test_sigterm", timeout=5)

        mock_getpgid.assert_called_once_with(9999)
        # First call should be SIGTERM
        import signal
        first_call = mock_killpg.call_args_list[0]
        assert first_call == call(9999, signal.SIGTERM)

    @pytest.mark.skipif(sys.platform == "win32", reason="Unix-only test")
    def test_unix_sigkill_on_timeout(self):
        """On timeout, terminate_process escalates to SIGKILL."""
        import signal
        from app.services.sim.process_manager import terminate_process
        import subprocess as _subprocess

        mock_process = _make_mock_process(poll_return=None)
        mock_process.pid = 8888
        mock_process.wait.side_effect = [_subprocess.TimeoutExpired(cmd="x", timeout=5), None]

        with (
            patch("os.getpgid", return_value=8888),
            patch("os.killpg") as mock_killpg,
        ):
            terminate_process(mock_process, "sim_test_sigkill", timeout=5)

        calls = [c[0][1] for c in mock_killpg.call_args_list]
        assert signal.SIGTERM in calls
        assert signal.SIGKILL in calls


# ---------------------------------------------------------------------------
# get_running_simulations
# ---------------------------------------------------------------------------


class TestGetRunningSimulations:
    def test_filters_dead_processes(self):
        """Only simulations with poll()==None (still running) are returned."""
        from app.services.sim.process_manager import get_running_simulations

        running_proc = _make_mock_process(poll_return=None)
        dead_proc = _make_mock_process(poll_return=0)

        processes = {
            "sim_running": running_proc,
            "sim_dead": dead_proc,
        }

        result = get_running_simulations(processes=processes)

        assert "sim_running" in result
        assert "sim_dead" not in result

    def test_empty_processes(self):
        from app.services.sim.process_manager import get_running_simulations

        result = get_running_simulations(processes={})
        assert result == []

    def test_all_running(self):
        from app.services.sim.process_manager import get_running_simulations

        procs = {
            "sim_a": _make_mock_process(poll_return=None),
            "sim_b": _make_mock_process(poll_return=None),
        }
        result = get_running_simulations(processes=procs)
        assert sorted(result) == ["sim_a", "sim_b"]


# ---------------------------------------------------------------------------
# register_cleanup
# ---------------------------------------------------------------------------


class TestRegisterCleanup:
    def test_registers_atexit_handler(self):
        """register_cleanup must register an atexit handler."""
        from app.services.sim import process_manager

        cleanup_called = []

        def my_cleanup():
            cleanup_called.append(True)

        with (
            patch("atexit.register") as mock_atexit,
            patch("signal.signal"),
            patch("signal.getsignal", return_value=None),
            patch.dict(os.environ, {"WERKZEUG_RUN_MAIN": "true"}, clear=False),
        ):
            # Reset module-level flag so registration runs
            original_flag = process_manager._cleanup_registered
            process_manager._cleanup_registered = False
            try:
                process_manager.register_cleanup(cleanup_callable=my_cleanup)
            finally:
                process_manager._cleanup_registered = original_flag

        mock_atexit.assert_called_once()

    def test_reloader_child_guard_skips_in_debug_mode(self):
        """In Flask debug mode without WERKZEUG_RUN_MAIN, registration is skipped."""
        from app.services.sim import process_manager

        # Remove WERKZEUG_RUN_MAIN to simulate parent process
        env_without_main = {k: v for k, v in os.environ.items() if k != "WERKZEUG_RUN_MAIN"}
        env_without_main["FLASK_DEBUG"] = "1"

        with (
            patch("atexit.register") as mock_atexit,
            patch.dict(os.environ, env_without_main, clear=True),
        ):
            original_flag = process_manager._cleanup_registered
            process_manager._cleanup_registered = False
            try:
                process_manager.register_cleanup(cleanup_callable=lambda: None)
            finally:
                process_manager._cleanup_registered = original_flag

        mock_atexit.assert_not_called()
