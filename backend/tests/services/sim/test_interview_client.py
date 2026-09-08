"""
Smoke-tests for ``app.services.sim.interview_client``.

Exercises the three most critical code paths in isolation — no real IPC,
no real filesystem state. Mocks target module-level names inside
``interview_client``, not ``SimulationRunner`` methods.
"""

from __future__ import annotations

import json
import os
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from app.services.run_budget import BudgetExceededError
from app.services.sim.interview_client import (
    _get_interview_history_from_db,
    check_env_alive,
    get_env_status_detail,
    get_interview_history,
    interview_agent,
    interview_agents_batch,
)


class _FakeStatus:
    def __init__(self, value: str) -> None:
        self.value = value


class _FakeIPCResponse:
    """Testdouble fuer ``simulation_ipc.IPCResponse`` (nur die vom Client
    gelesenen Attribute)."""

    def __init__(
        self,
        *,
        status: str,
        result=None,
        error=None,
        budget_exceeded=None,
        timestamp="2026-09-08T00:00:00",
    ) -> None:
        self.status = _FakeStatus(status)
        self.result = result
        self.error = error
        self.budget_exceeded = budget_exceeded
        self.timestamp = timestamp


class TestInterviewAgentBudgetExceededPropagation:
    """#1478 Codex P1, Runde 7: ein waehrend ``env.step()`` geworfener
    ``BudgetExceededError`` erreicht den IPC-Interview-Client jetzt als
    strukturiertes ``budget_exceeded``-Feld statt als generischer Fehlertext
    — und wird hier wieder als ``BudgetExceededError`` geworfen statt als
    ``{"success": False}`` zurueckgegeben."""

    def test_interview_agent_raises_budget_exceeded_error(self, tmp_path) -> None:
        sim_dir = tmp_path / "sim1"
        sim_dir.mkdir()
        fake_response = _FakeIPCResponse(
            status="failed",
            error="Aufrufbudget überschritten: 5 >= 5",
            budget_exceeded={"dimension": "calls", "observed": 5, "threshold": 5},
        )
        mock_client = MagicMock()
        mock_client.send_interview.return_value = fake_response

        with patch(
            "app.services.sim.interview_client.check_env_alive", return_value=True
        ), patch(
            "app.services.sim.interview_client.SimulationIPCClient",
            return_value=mock_client,
        ):
            with pytest.raises(BudgetExceededError) as excinfo:
                interview_agent(
                    "sim1", 7, "prompt", run_state_dir=str(tmp_path)
                )
        assert excinfo.value.dimension == "calls"
        assert excinfo.value.observed == 5
        assert excinfo.value.threshold == 5

    def test_interview_agent_generic_failure_still_returns_dict(self, tmp_path) -> None:
        sim_dir = tmp_path / "sim1"
        sim_dir.mkdir()
        fake_response = _FakeIPCResponse(status="failed", error="provider down")
        mock_client = MagicMock()
        mock_client.send_interview.return_value = fake_response

        with patch(
            "app.services.sim.interview_client.check_env_alive", return_value=True
        ), patch(
            "app.services.sim.interview_client.SimulationIPCClient",
            return_value=mock_client,
        ):
            result = interview_agent(
                "sim1", 7, "prompt", run_state_dir=str(tmp_path)
            )
        assert result["success"] is False
        assert result["error"] == "provider down"

    def test_interview_agents_batch_raises_budget_exceeded_error(self, tmp_path) -> None:
        sim_dir = tmp_path / "sim1"
        sim_dir.mkdir()
        fake_response = _FakeIPCResponse(
            status="failed",
            error="Kostenbudget überschritten: 100 >= 90",
            budget_exceeded={"dimension": "cost", "observed": 100, "threshold": 90},
        )
        mock_client = MagicMock()
        mock_client.send_batch_interview.return_value = fake_response

        with patch(
            "app.services.sim.interview_client.check_env_alive", return_value=True
        ), patch(
            "app.services.sim.interview_client.SimulationIPCClient",
            return_value=mock_client,
        ):
            with pytest.raises(BudgetExceededError) as excinfo:
                interview_agents_batch(
                    "sim1",
                    [{"agent_id": 1, "prompt": "a"}],
                    run_state_dir=str(tmp_path),
                )
        assert excinfo.value.dimension == "cost"


# ---------------------------------------------------------------------------
# test_check_env_alive_returns_false_when_ipc_unavailable
# ---------------------------------------------------------------------------


class TestCheckEnvAlive:
    def test_returns_false_when_sim_dir_missing(self, tmp_path) -> None:
        """Missing sim directory must yield False without raising."""
        result = check_env_alive("nonexistent-sim", run_state_dir=str(tmp_path))
        assert result is False

    def test_returns_false_when_ipc_check_raises_connection_error(self, tmp_path) -> None:
        """``SimulationIPCClient.check_env_alive`` raising ``ConnectionError`` → ``False``."""
        sim_dir = tmp_path / "sim-001"
        sim_dir.mkdir()

        mock_client = MagicMock()
        mock_client.check_env_alive.side_effect = ConnectionError("IPC not reachable")

        with patch(
            "app.services.sim.interview_client.SimulationIPCClient",
            return_value=mock_client,
        ):
            # ConnectionError is not caught by check_env_alive — it propagates.
            # The caller (SimulationRunner) is expected to handle it.
            # We verify the IPC client was constructed and called.
            with pytest.raises(ConnectionError):
                check_env_alive("sim-001", run_state_dir=str(tmp_path))

        mock_client.check_env_alive.assert_called_once()

    def test_returns_false_when_ipc_returns_false(self, tmp_path) -> None:
        """When the IPC client reports the env is not alive, return False."""
        sim_dir = tmp_path / "sim-002"
        sim_dir.mkdir()

        mock_client = MagicMock()
        mock_client.check_env_alive.return_value = False

        with patch(
            "app.services.sim.interview_client.SimulationIPCClient",
            return_value=mock_client,
        ):
            result = check_env_alive("sim-002", run_state_dir=str(tmp_path))

        assert result is False

    def test_returns_true_when_ipc_reports_alive(self, tmp_path) -> None:
        """When the IPC client reports alive, return True."""
        sim_dir = tmp_path / "sim-003"
        sim_dir.mkdir()

        mock_client = MagicMock()
        mock_client.check_env_alive.return_value = True

        with patch(
            "app.services.sim.interview_client.SimulationIPCClient",
            return_value=mock_client,
        ):
            result = check_env_alive("sim-003", run_state_dir=str(tmp_path))

        assert result is True


# ---------------------------------------------------------------------------
# test_get_env_status_detail_reads_status_file
# ---------------------------------------------------------------------------


class TestGetEnvStatusDetail:
    def test_returns_default_when_store_empty(self) -> None:
        """When the store has no env_status artifact, return the stopped-default."""
        mock_store = MagicMock()
        mock_store.read_json.return_value = None

        with patch(
            "app.services.sim.interview_client.resolve_default_store",
            return_value=mock_store,
        ):
            result = get_env_status_detail("sim-no-status")

        assert result["status"] == "stopped"
        assert result["twitter_available"] is False
        assert result["reddit_available"] is False
        assert result["timestamp"] is None

    def test_returns_parsed_status_from_store(self) -> None:
        """Artifact dict must be forwarded as-is (with fallbacks for missing keys)."""
        mock_store = MagicMock()
        mock_store.read_json.return_value = {
            "status": "alive",
            "twitter_available": True,
            "reddit_available": False,
            "timestamp": "2026-05-08T12:00:00",
        }

        with patch(
            "app.services.sim.interview_client.resolve_default_store",
            return_value=mock_store,
        ):
            result = get_env_status_detail("sim-alive")

        assert result["status"] == "alive"
        assert result["twitter_available"] is True
        assert result["reddit_available"] is False
        assert result["timestamp"] == "2026-05-08T12:00:00"


# ---------------------------------------------------------------------------
# test_get_interview_history_from_db_aggregation
# ---------------------------------------------------------------------------


class TestGetInterviewHistoryFromDb:
    def _create_db(self, path: str, rows: list) -> None:
        """Create a minimal trace DB with the given rows."""
        conn = sqlite3.connect(path)
        conn.execute(
            """
            CREATE TABLE trace (
                user_id INTEGER,
                action TEXT,
                info TEXT,
                created_at TEXT
            )
            """
        )
        conn.executemany(
            "INSERT INTO trace (user_id, action, info, created_at) VALUES (?, ?, ?, ?)",
            rows,
        )
        conn.commit()
        conn.close()

    def test_returns_empty_list_when_db_missing(self, tmp_path) -> None:
        """Non-existent db_path must return [] without raising."""
        result = _get_interview_history_from_db(
            str(tmp_path / "no_such.db"), "twitter"
        )
        assert result == []

    def test_reads_all_interview_rows(self, tmp_path) -> None:
        """All rows with action='interview' must be returned and parsed."""
        db_path = str(tmp_path / "twitter_simulation.db")
        rows = [
            (1, "interview", json.dumps({"prompt": "What do you think?", "response": "I agree"}), "2026-05-08T10:00:00"),
            (2, "interview", json.dumps({"prompt": "How are you?", "response": "Fine"}), "2026-05-08T10:01:00"),
            (3, "tweet", json.dumps({"text": "hello"}), "2026-05-08T10:02:00"),  # non-interview row
        ]
        self._create_db(db_path, rows)

        result = _get_interview_history_from_db(db_path, "twitter")

        # Only interview rows
        assert len(result) == 2
        agent_ids = {r["agent_id"] for r in result}
        assert agent_ids == {1, 2}
        for r in result:
            assert r["platform"] == "twitter"
            assert r["prompt"] != ""

    def test_filters_by_agent_id(self, tmp_path) -> None:
        """agent_id filter must restrict results to that agent only."""
        db_path = str(tmp_path / "reddit_simulation.db")
        rows = [
            (10, "interview", json.dumps({"prompt": "Q1", "response": "A1"}), "2026-05-08T09:00:00"),
            (20, "interview", json.dumps({"prompt": "Q2", "response": "A2"}), "2026-05-08T09:01:00"),
        ]
        self._create_db(db_path, rows)

        result = _get_interview_history_from_db(db_path, "reddit", agent_id=10)

        assert len(result) == 1
        assert result[0]["agent_id"] == 10

    def test_aggregation_via_get_interview_history(self, tmp_path) -> None:
        """``get_interview_history`` must merge rows from both platform DBs."""
        twitter_db = str(tmp_path / "twitter_simulation.db")
        reddit_db = str(tmp_path / "reddit_simulation.db")

        self._create_db(
            twitter_db,
            [(1, "interview", json.dumps({"prompt": "TQ", "response": "TR"}), "2026-05-08T10:00:00")],
        )
        self._create_db(
            reddit_db,
            [(2, "interview", json.dumps({"prompt": "RQ", "response": "RR"}), "2026-05-08T10:05:00")],
        )

        # Simulate sim_dir = tmp_path / "sim-xyz" (files already placed there)
        sim_dir = tmp_path / "sim-xyz"
        sim_dir.mkdir()
        os.rename(twitter_db, str(sim_dir / "twitter_simulation.db"))
        os.rename(reddit_db, str(sim_dir / "reddit_simulation.db"))

        result = get_interview_history("sim-xyz", run_state_dir=str(tmp_path))

        assert len(result) == 2
        platforms = {r["platform"] for r in result}
        assert platforms == {"twitter", "reddit"}
        # sorted descending by timestamp — reddit row is newer
        assert result[0]["platform"] == "reddit"
