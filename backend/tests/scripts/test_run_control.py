"""Tests fuer ``sim_runtime.run_control.RoundBoundaryControl`` (Tech-Review Slice B4c).

Sichern die aus ``platform_runner.py`` extrahierte Rundengrenzen-Kontrolle:
Pruefreihenfolge Pause -> Stop -> Budget, sowie das ``RoundDecision``-Ergebnis
je Zweig. ``check()`` importiert ``app.services.simulation_ipc`` inline pro
Aufruf — Monkeypatch auf Modulebene reicht deshalb, ohne echten Flask-Kontext
oder Artifact-Store.

Liegt bewusst unter ``tests/scripts/`` statt ``tests/sim_runtime/``: ein
eigenes ``tests/sim_runtime/__init__.py``-Paket kollidiert mit dem
Produktionspaket ``scripts/sim_runtime`` — ohne ``tests/__init__.py`` waehlt
pytests Rootdir-Insertion (Prepend-Import-Mode) ``backend/tests/`` als
sys.path-Eintrag und importiert das Testmodul als Top-Level-Paket
``sim_runtime``, das dann ``sim_runtime.run_control`` verdeckt
(``ModuleNotFoundError: No module named 'sim_runtime.run_control'`` trotz
vorhandener Datei — verifiziert waehrend der Testentwicklung dieses Slices).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from sim_runtime.run_control import RoundAction, RoundBoundaryControl  # noqa: E402


class FakeBudgetGuard:
    """Testdouble fuer ``SubprocessBudgetGuard.check_round_boundary``."""

    def __init__(
        self,
        abort_info: Optional[dict] = None,
        *,
        raises: Optional[Exception] = None,
    ) -> None:
        self._abort_info = abort_info
        self._raises = raises
        self.calls: list[int] = []

    def check_round_boundary(self, round_num: int) -> Optional[dict]:
        self.calls.append(round_num)
        if self._raises is not None:
            raise self._raises
        return self._abort_info


def _patch_control_state(
    monkeypatch: Any,
    *,
    paused: bool = False,
    stop_requested: bool = False,
) -> list[str]:
    """Patcht ``app.services.simulation_ipc.{read_control_state,wait_while_paused}``."""
    wait_calls: list[str] = []

    def fake_wait_while_paused(simulation_dir: str, poll_interval: float = 1.0) -> None:
        wait_calls.append(simulation_dir)

    def fake_read_control_state(simulation_dir: str) -> dict:
        return {"paused": paused, "stop_requested": stop_requested}

    monkeypatch.setattr(
        "app.services.simulation_ipc.wait_while_paused", fake_wait_while_paused
    )
    monkeypatch.setattr(
        "app.services.simulation_ipc.read_control_state", fake_read_control_state
    )
    return wait_calls


def test_check_continues_when_no_pause_stop_or_budget(monkeypatch: Any) -> None:
    _patch_control_state(monkeypatch)
    control = RoundBoundaryControl("sim-dir", None)
    decision = control.check(0)
    assert decision.action == RoundAction.CONTINUE
    assert decision.budget_abort_info is None


def test_check_returns_stop_when_stop_requested(monkeypatch: Any) -> None:
    """Stop hat Vorrang vor Budget — der Guard wird bei Stop nicht mehr gefragt."""
    _patch_control_state(monkeypatch, stop_requested=True)
    guard = FakeBudgetGuard()
    control = RoundBoundaryControl("sim-dir", guard)
    decision = control.check(3)
    assert decision.action == RoundAction.STOP
    assert decision.budget_abort_info is None
    assert guard.calls == []


def test_check_waits_while_paused(monkeypatch: Any) -> None:
    wait_calls = _patch_control_state(monkeypatch, paused=True)
    control = RoundBoundaryControl("sim-dir", None)
    decision = control.check(1)
    assert wait_calls == ["sim-dir"]
    assert decision.action == RoundAction.CONTINUE


def test_check_returns_budget_abort_when_guard_signals(monkeypatch: Any) -> None:
    _patch_control_state(monkeypatch)
    abort_info = {"dimension": "tokens", "observed": 100, "threshold": 50, "round": 2}
    guard = FakeBudgetGuard(abort_info)
    control = RoundBoundaryControl("sim-dir", guard)
    decision = control.check(2)
    assert decision.action == RoundAction.BUDGET_ABORT
    assert decision.budget_abort_info == abort_info
    assert guard.calls == [2]


def test_check_no_budget_guard_never_aborts(monkeypatch: Any) -> None:
    _patch_control_state(monkeypatch)
    control = RoundBoundaryControl("sim-dir", None)
    decision = control.check(5)
    assert decision.action == RoundAction.CONTINUE


def test_check_swallows_control_state_exceptions(monkeypatch: Any) -> None:
    """Fehlende Flask-App / Importfehler bei Direktausfuehrung: Sim laeuft weiter."""

    def raise_error(*_args: Any, **_kwargs: Any) -> None:
        raise RuntimeError("no flask app context")

    monkeypatch.setattr("app.services.simulation_ipc.wait_while_paused", raise_error)
    monkeypatch.setattr("app.services.simulation_ipc.read_control_state", raise_error)
    guard = FakeBudgetGuard()
    control = RoundBoundaryControl("sim-dir", guard)
    decision = control.check(0)
    assert decision.action == RoundAction.CONTINUE
    # Budget wird trotz geschluckter Pause/Stop-Exception weiter geprueft.
    assert guard.calls == [0]


def test_check_swallows_budget_guard_exceptions(monkeypatch: Any) -> None:
    _patch_control_state(monkeypatch)
    guard = FakeBudgetGuard(raises=RuntimeError("guard exploded"))
    control = RoundBoundaryControl("sim-dir", guard)
    decision = control.check(0)
    assert decision.action == RoundAction.CONTINUE
    assert decision.budget_abort_info is None
