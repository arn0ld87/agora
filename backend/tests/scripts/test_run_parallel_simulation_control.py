"""Tests fuer ``run_parallel_simulation.py``: RoundBoundaryControl in den
Twitter-/Reddit-Schleifen (Tech-Review Slice B4c).

Vor diesem Fix hatte der Default-Pfad (Twitter+Reddit parallel, kein
``--twitter-only``/``--reddit-only``) weder Hard-Budget noch Pause/Stop-
Kontrolle. Diese Tests scripten ``RoundBoundaryControl`` (per Monkeypatch auf
den in ``run_parallel_simulation`` importierten Namen) und pruefen, dass
beide Runden-Schleifen STOP/BUDGET_ABORT ehren: die Schleife bricht sauber
ab, ``result.budget_abort_info`` traegt bei Budget-Abbruch das Info-Dict und
bleibt bei Stop ``None`` — identisch zu ``platform_runner.py``.

Alle uebrigen OASIS-/CAMEL-Abhaengigkeiten (Modell, Agent-Graph, Environment)
werden gefaked; ``get_active_agents_for_round`` liefert bewusst eine leere
Liste, damit der Rest des Rundenkoerpers (env.step, Action-Logging,
Redis-Emit) gar nicht erst betreten wird — der Test isoliert die
Kontrollpfad-Frage von der restlichen ~2400-Zeilen-Datei.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

import run_parallel_simulation as rps  # type: ignore[import-not-found]  # noqa: E402
from sim_runtime.run_control import RoundAction, RoundDecision  # noqa: E402


class _FakeAgentGraph:
    """Leerer Agent-Graph — genug fuer die Namens-Backfill-Schleife."""

    def get_agents(self):
        return []


class _FakeEnv:
    async def reset(self) -> None:
        return None


class _ScriptedControl:
    """Ersatz fuer ``RoundBoundaryControl``: liefert vorgegebene Entscheidungen.

    ``decisions`` mapped ``round_num -> RoundDecision``; fehlende Runden
    liefern CONTINUE, identisch zum echten Default-Verhalten ohne Guard.
    """

    def __init__(self, decisions: Dict[int, RoundDecision]) -> None:
        self._decisions = decisions
        self.checked_rounds: List[int] = []

    def check(self, round_num: int) -> RoundDecision:
        self.checked_rounds.append(round_num)
        return self._decisions.get(round_num, RoundDecision(RoundAction.CONTINUE))


def _patch_common(monkeypatch: Any, tmp_path: Path, *, active_agent_calls: List[int]) -> _ScriptedControl:
    """Faked die schweren OASIS/CAMEL-Abhaengigkeiten fuer beide Plattformen."""
    holder: Dict[str, _ScriptedControl] = {}

    def scripted_control_factory(simulation_dir: str, budget_guard: Any) -> _ScriptedControl:
        # Der Test setzt ``holder["control"]`` VOR dem Aufruf; hier nur zurueckgeben.
        return holder["control"]

    monkeypatch.setattr(rps, "RoundBoundaryControl", scripted_control_factory)

    async def fake_generate_agent_graph(*, profile_path: str, model: Any, available_actions: Any) -> _FakeAgentGraph:
        return _FakeAgentGraph()

    monkeypatch.setattr(rps, "generate_twitter_agent_graph", fake_generate_agent_graph)
    monkeypatch.setattr(rps, "generate_reddit_agent_graph", fake_generate_agent_graph)
    monkeypatch.setattr(rps, "create_model", lambda config, use_boost=False: object())
    monkeypatch.setattr(rps, "preflight_model_probe", lambda model: None)
    monkeypatch.setattr(rps, "compute_start_hour_offset", lambda config, total_rounds, minutes_per_round: 0)
    monkeypatch.setattr(rps.oasis, "make", lambda **kwargs: _FakeEnv())

    def fake_get_active_agents_for_round(env: Any, config: Any, simulated_hour: int, round_num: int):
        active_agent_calls.append(round_num)
        return []

    monkeypatch.setattr(rps, "get_active_agents_for_round", fake_get_active_agents_for_round)

    return holder  # type: ignore[return-value]


def _base_config() -> Dict[str, Any]:
    return {
        "agent_configs": [],
        "event_config": {},
        "enable_agent_tools": False,
        # 5h / 30min => 10 Runden — genug Platz fuer Abbruch nach Runde N.
        "time_config": {"total_simulation_hours": 5, "minutes_per_round": 30},
    }


@pytest.mark.asyncio
async def test_twitter_loop_stops_on_budget_abort(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
    active_agent_calls: List[int] = []
    holder = _patch_common(monkeypatch, tmp_path, active_agent_calls=active_agent_calls)
    abort_info = {"dimension": "tokens", "observed": 999, "threshold": 500, "round": 5}
    control = _ScriptedControl({5: RoundDecision(RoundAction.BUDGET_ABORT, abort_info)})
    holder["control"] = control

    result = await rps.run_twitter_simulation(_base_config(), str(tmp_path))

    assert control.checked_rounds == [0, 1, 2, 3, 4, 5]
    # Runde 5 bricht VOR dem Aktiv-Agenten-Fetch ab — nur Runden 0-4 kamen so weit.
    assert active_agent_calls == [0, 1, 2, 3, 4]
    assert result.budget_abort_info == abort_info


@pytest.mark.asyncio
async def test_twitter_loop_stops_on_stop_marker(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
    active_agent_calls: List[int] = []
    holder = _patch_common(monkeypatch, tmp_path, active_agent_calls=active_agent_calls)
    control = _ScriptedControl({3: RoundDecision(RoundAction.STOP)})
    holder["control"] = control

    result = await rps.run_twitter_simulation(_base_config(), str(tmp_path))

    assert control.checked_rounds == [0, 1, 2, 3]
    assert active_agent_calls == [0, 1, 2]
    assert result.budget_abort_info is None


@pytest.mark.asyncio
async def test_reddit_loop_stops_on_budget_abort(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / "reddit_profiles.json").write_text("{}", encoding="utf-8")
    active_agent_calls: List[int] = []
    holder = _patch_common(monkeypatch, tmp_path, active_agent_calls=active_agent_calls)
    abort_info = {"dimension": "calls", "observed": 42, "threshold": 40, "round": 2}
    control = _ScriptedControl({2: RoundDecision(RoundAction.BUDGET_ABORT, abort_info)})
    holder["control"] = control

    result = await rps.run_reddit_simulation(_base_config(), str(tmp_path))

    assert control.checked_rounds == [0, 1, 2]
    assert active_agent_calls == [0, 1]
    assert result.budget_abort_info == abort_info


@pytest.mark.asyncio
async def test_reddit_loop_stops_on_stop_marker(monkeypatch: Any, tmp_path: Path) -> None:
    (tmp_path / "reddit_profiles.json").write_text("{}", encoding="utf-8")
    active_agent_calls: List[int] = []
    holder = _patch_common(monkeypatch, tmp_path, active_agent_calls=active_agent_calls)
    control = _ScriptedControl({1: RoundDecision(RoundAction.STOP)})
    holder["control"] = control

    result = await rps.run_reddit_simulation(_base_config(), str(tmp_path))

    assert control.checked_rounds == [0, 1]
    assert active_agent_calls == [0]
    assert result.budget_abort_info is None


@pytest.mark.asyncio
async def test_twitter_loop_runs_to_completion_without_control_hits(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Gegenprobe: ohne Stop/Budget laeuft die Schleife alle Runden durch."""
    (tmp_path / "twitter_profiles.csv").write_text("", encoding="utf-8")
    active_agent_calls: List[int] = []
    holder = _patch_common(monkeypatch, tmp_path, active_agent_calls=active_agent_calls)
    control = _ScriptedControl({})
    holder["control"] = control

    result = await rps.run_twitter_simulation(_base_config(), str(tmp_path))

    assert control.checked_rounds == list(range(10))
    assert active_agent_calls == list(range(10))
    assert result.budget_abort_info is None
