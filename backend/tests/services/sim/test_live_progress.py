"""#1759 C1: Fortschritt und Aktionen sind innerhalb einer Runde sichtbar.

Beobachtet im Lauf ``sim_3d3d8b2d8342``: 16 Aktionen im ``run_state.json``,
obwohl die OASIS-DBs schon 95 Kommentare und 59 Likes hielten, und ein
``state.json`` mit ``current_round: 0`` / ``not_started`` bis zum Ende.
"""

from __future__ import annotations

import sqlite3
from types import SimpleNamespace
from typing import Any, Optional

import pytest

from app.services.sim import monitor as monitor_module
from app.services.sim.live_progress import (
    count_trace_actions,
    derive_platform_status,
    mirror_runtime_progress,
    refresh_live_action_counts,
    reset_live_action_counts,
    runtime_progress_key,
)
from app.services.sim.monitor import monitor_simulation
from app.services.sim.run_state_store import RunnerStatus, SimulationRunState


def _make_trace_db(path, actions: list[str]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute("CREATE TABLE trace (user_id INTEGER, action TEXT, info TEXT)")
        conn.executemany(
            "INSERT INTO trace (user_id, action, info) VALUES (1, ?, '{}')",
            [(action,) for action in actions],
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# DB-Zaehlung
# ---------------------------------------------------------------------------


def test_count_trace_actions_skips_refresh_and_sign_up(tmp_path):
    db = tmp_path / "twitter_simulation.db"
    _make_trace_db(db, ["sign_up", "refresh", "create_post", "like_post", "create_comment"])

    assert count_trace_actions(str(db)) == 3


def test_count_trace_actions_missing_db_or_table_is_none_not_zero(tmp_path):
    assert count_trace_actions(str(tmp_path / "absent.db")) is None

    empty = tmp_path / "empty.db"
    sqlite3.connect(empty).close()
    assert count_trace_actions(str(empty)) is None


def test_count_trace_actions_does_not_write_to_the_db(tmp_path):
    db = tmp_path / "reddit_simulation.db"
    _make_trace_db(db, ["create_post"])

    count_trace_actions(str(db))

    conn = sqlite3.connect(db)
    try:
        assert conn.execute("SELECT COUNT(*) FROM trace").fetchone()[0] == 1
    finally:
        conn.close()


def test_refresh_sets_live_counts_per_platform_and_never_decreases(tmp_path):
    _make_trace_db(tmp_path / "twitter_simulation.db", ["create_post", "like_post"])
    _make_trace_db(tmp_path / "reddit_simulation.db", ["create_comment"])
    state = SimulationRunState(simulation_id="sim_x")

    refresh_live_action_counts(str(tmp_path), state)

    assert (state.twitter_live_actions, state.reddit_live_actions) == (2, 1)

    # DB kurz nicht lesbar (None) -> kein Rueckfall auf 0
    (tmp_path / "twitter_simulation.db").unlink()
    refresh_live_action_counts(str(tmp_path), state)
    assert state.twitter_live_actions == 2


# ---------------------------------------------------------------------------
# Anzeige: max(protokolliert, live), ohne Doppelzaehlung
# ---------------------------------------------------------------------------


def test_displayed_counts_use_live_value_within_a_round():
    state = SimulationRunState(simulation_id="sim_x")
    state.twitter_actions_count = 16
    state.twitter_live_actions = 154  # 95 Kommentare + 59 Likes aus der DB

    payload = state.to_dict()

    assert payload["twitter_actions_count"] == 154
    assert payload["total_actions_count"] == 154


def test_displayed_counts_do_not_double_count_after_round_end():
    state = SimulationRunState(simulation_id="sim_x")
    state.twitter_live_actions = 154
    state.twitter_actions_count = 154  # Rundenende: Protokoll hat aufgeholt

    assert state.to_dict()["twitter_actions_count"] == 154


def test_reset_returns_to_logged_counts():
    state = SimulationRunState(simulation_id="sim_x")
    state.twitter_actions_count = 10
    state.twitter_live_actions = 12
    state.reddit_live_actions = 3

    reset_live_action_counts(state)

    payload = state.to_dict()
    assert payload["twitter_actions_count"] == 10
    assert payload["reddit_actions_count"] == 0


# ---------------------------------------------------------------------------
# Monitor-Integration
# ---------------------------------------------------------------------------


class _FinishedProcess:
    returncode = 0

    def poll(self):
        return self.returncode


class _OneTickProcess:
    """Laeuft fuer genau einen Schleifendurchlauf."""

    returncode = None

    def poll(self):
        return None


def _monitor_kwargs(
    run_state_dir, sim_id, process, state, saved: list, *, is_current=None
) -> dict[str, Any]:
    def save_state(s):
        saved.append(s.to_dict())

    return dict(
        run_state_dir=str(run_state_dir),
        processes={sim_id: process},
        graph_memory_enabled={},
        action_queues={},
        stdout_files={},
        stderr_files={},
        get_run_state=lambda _sid: state,
        save_state=save_state,
        generation=1,
        is_current_generation=is_current,
    )


@pytest.fixture()
def quiet_monitor(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor_module.time, "sleep", lambda _s: None)
    monkeypatch.setattr(monitor_module, "_budget_supervision", lambda *_a, **_k: None)
    monkeypatch.setattr(monitor_module, "_cancel_supervision", lambda *_a, **_k: None)
    return tmp_path


def test_monitor_tick_publishes_live_db_counts_before_round_end(quiet_monitor):
    sim_id = "sim_live"
    sim_dir = quiet_monitor / sim_id
    sim_dir.mkdir()
    _make_trace_db(sim_dir / "twitter_simulation.db", ["create_post", "like_post", "create_comment"])
    state = SimulationRunState(simulation_id=sim_id, runner_status=RunnerStatus.RUNNING)
    saved: list = []

    calls = {"n": 0}

    def is_current(_sid, _gen):
        calls["n"] += 1
        return calls["n"] <= 1  # erster Takt aktuell, danach stale -> Schleife endet

    monitor_simulation(
        sim_id,
        **_monitor_kwargs(quiet_monitor, sim_id, _OneTickProcess(), state, saved, is_current=is_current),
    )

    assert saved, "Monitor hat im Takt nichts gespeichert"
    assert saved[0]["twitter_actions_count"] == 3
    assert saved[0]["total_actions_count"] == 3


def test_monitor_resets_live_counts_when_process_has_ended(quiet_monitor, monkeypatch):
    sim_id = "sim_end"
    (quiet_monitor / sim_id).mkdir()
    monkeypatch.setattr(monitor_module, "_apply_terminal_state", lambda *_a, **_k: "completed")
    monkeypatch.setattr(monitor_module, "_finalize_manifest_for_simulation", lambda *_a, **_k: None)
    state = SimulationRunState(simulation_id=sim_id, runner_status=RunnerStatus.RUNNING)
    state.twitter_live_actions = 99  # z. B. spaetere Interview-Trace-Zeilen
    saved: list = []

    monitor_simulation(
        sim_id, **_monitor_kwargs(quiet_monitor, sim_id, _FinishedProcess(), state, saved)
    )

    assert state.twitter_live_actions == 0
    assert saved[-1]["twitter_actions_count"] == 0


# ---------------------------------------------------------------------------
# state.json mitfuehren
# ---------------------------------------------------------------------------


def test_platform_status_derivation():
    running = dict(enabled=True, running=True, completed=False, runner_status=RunnerStatus.RUNNING)
    assert derive_platform_status(**running) == "running"
    assert derive_platform_status(**{**running, "running": False, "completed": True}) == "completed"
    assert derive_platform_status(**{**running, "running": False, "runner_status": RunnerStatus.FAILED}) == "failed"
    assert derive_platform_status(**{**running, "running": False, "runner_status": RunnerStatus.STOPPED}) == "stopped"
    assert derive_platform_status(**{**running, "running": False, "runner_status": RunnerStatus.IDLE}) == "not_started"
    assert derive_platform_status(**{**running, "enabled": False}) == "not_started"


class _FakeManager:
    def __init__(self, state: Optional[SimpleNamespace]) -> None:
        self.state = state
        self.saved: list[SimpleNamespace] = []

    def get_simulation(self, _simulation_id: str):
        return self.state

    def _save_simulation_state(self, state) -> None:
        self.saved.append(state)


def _sim_state(**overrides) -> SimpleNamespace:
    base = dict(
        enable_twitter=True,
        enable_reddit=True,
        status="running",
        current_round=0,
        twitter_status="not_started",
        reddit_status="not_started",
    )
    base.update(overrides)
    return SimpleNamespace(**base)


def test_mirror_writes_round_and_platform_status_but_leaves_status_alone():
    run_state = SimulationRunState(simulation_id="sim_x", runner_status=RunnerStatus.RUNNING)
    run_state.current_round = 6
    run_state.twitter_running = True
    run_state.reddit_running = True
    manager = _FakeManager(_sim_state())

    result = mirror_runtime_progress(manager, run_state)

    assert result == (6, "running", "running")
    saved = manager.saved[0]
    assert (saved.current_round, saved.twitter_status, saved.reddit_status) == (6, "running", "running")
    assert saved.status == "running"


def test_mirror_without_simulation_state_is_a_noop():
    run_state = SimulationRunState(simulation_id="sim_x")
    manager = _FakeManager(None)

    assert mirror_runtime_progress(manager, run_state) is None
    assert manager.saved == []


def test_mirror_marks_finished_platforms_completed():
    run_state = SimulationRunState(simulation_id="sim_x", runner_status=RunnerStatus.COMPLETED)
    run_state.current_round = 24
    run_state.twitter_completed = True
    run_state.reddit_completed = True
    manager = _FakeManager(_sim_state())

    assert mirror_runtime_progress(manager, run_state) == (24, "completed", "completed")


def test_runner_mirrors_only_when_progress_key_changes(monkeypatch):
    from app.services import simulation_manager
    from app.services.simulation_runner import SimulationRunner

    managers: list[_FakeManager] = []

    def factory():
        manager = _FakeManager(_sim_state())
        managers.append(manager)
        return manager

    monkeypatch.setattr(simulation_manager, "SimulationManager", factory)
    SimulationRunner._mirrored_progress.pop("sim_throttle", None)
    run_state = SimulationRunState(simulation_id="sim_throttle", runner_status=RunnerStatus.RUNNING)
    run_state.twitter_running = True

    try:
        run_state.current_round = 1
        SimulationRunner._mirror_runtime_progress(run_state)
        SimulationRunner._mirror_runtime_progress(run_state)  # gleicher Takt, kein 2. Write
        run_state.current_round = 2
        SimulationRunner._mirror_runtime_progress(run_state)
    finally:
        SimulationRunner._mirrored_progress.pop("sim_throttle", None)

    assert sum(len(m.saved) for m in managers) == 2
    assert runtime_progress_key(run_state)[0] == 2


def test_runner_mirror_failure_never_raises(monkeypatch):
    from app.services import simulation_manager
    from app.services.simulation_runner import SimulationRunner

    def boom():
        raise RuntimeError("repository down")

    monkeypatch.setattr(simulation_manager, "SimulationManager", boom)
    SimulationRunner._mirrored_progress.pop("sim_fail", None)
    run_state = SimulationRunState(simulation_id="sim_fail")

    SimulationRunner._mirror_runtime_progress(run_state)  # darf nicht werfen

    assert "sim_fail" not in SimulationRunner._mirrored_progress
