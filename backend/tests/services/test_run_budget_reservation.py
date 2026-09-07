"""Reservierung laufender Calls im ``RunBudgetEnforcer``.

Codex-Finding P1 auf PR #1461: eine Deckelung der Gleichzeitigkeit im
Dispatcher erzwingt ``max_llm_calls`` nicht. Sobald ein Worker fertig ist,
startet der naechste, waehrend andere Calls noch fliegen — der neue Check
sieht nur die bereits verbuchten und laesst einen weiteren Call zu.

Diese Tests zaehlen deshalb **bestandene Checks**, nicht gleichzeitig aktive
Worker. Ohne Reservierung passieren alle Aufrufer den Check, weil sie
denselben Vor-Aufruf-Stand lesen.
"""

from __future__ import annotations

import threading
import time

import pytest

from app.contracts.run_budget_contract import RunBudgetConfig
from app.services.run_budget import (
    BudgetExceededError,
    RunBudgetEnforcer,
    reset_call_reservations,
)


class _Ledger:
    """Zaehlt nur, was ``record_after_call`` bereits verbucht hat."""

    def __init__(self) -> None:
        self.recorded = 0
        self._lock = threading.Lock()

    def bump(self) -> None:
        with self._lock:
            self.recorded += 1


@pytest.fixture
def enforcer(monkeypatch):
    reset_call_reservations()
    ledger = _Ledger()
    inst = RunBudgetEnforcer(
        run_id="run-reservation-test",
        config=RunBudgetConfig(max_llm_calls=2, enforcement="hard"),
    )

    class _Metrics:
        def __init__(self, calls: int) -> None:
            self.llm_calls = calls
            self.total_tokens = None
            self.cost_micros = None

    monkeypatch.setattr(
        RunBudgetEnforcer, "consumed", lambda self: _Metrics(ledger.recorded)
    )
    monkeypatch.setattr(RunBudgetEnforcer, "_record_warning", lambda self, *a, **k: None)
    monkeypatch.setattr(
        RunBudgetEnforcer,
        "_observed",
        lambda self, consumed: {
            "calls": consumed.llm_calls,
            "tokens": None,
            "cost": None,
            "time": None,
        },
    )
    yield inst, ledger
    reset_call_reservations()


class TestReservationEnforcesHardCallLimit:
    def test_parallel_checks_never_exceed_the_call_limit(self, enforcer):
        """Sechs gleichzeitige Aufrufer, Budget 2 — genau zwei duerfen durch.

        Ohne Reservierung passieren alle sechs, weil jeder ``consumed() == 0``
        liest, bevor irgendein Call verbucht ist.
        """
        inst, ledger = enforcer
        approved = 0
        rejected = 0
        lock = threading.Lock()
        start = threading.Barrier(6)

        def worker() -> None:
            nonlocal approved, rejected
            start.wait()
            try:
                inst.check_before_call()
            except BudgetExceededError:
                with lock:
                    rejected += 1
                return
            with lock:
                approved += 1
            # Der Call selbst. Diese Pause ist der Kern des Tests: genau in
            # diesem Fenster ist der Call gestartet, aber noch nicht verbucht.
            # Ohne Reservierung sehen alle sechs Aufrufer hier denselben
            # Vor-Aufruf-Stand und kommen durch.
            time.sleep(0.05)
            ledger.bump()
            inst.record_after_call()

        threads = [threading.Thread(target=worker) for _ in range(6)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert approved == 2, (
            f"{approved} Calls durchgelassen, erlaubt waren 2 "
            f"(abgelehnt: {rejected})"
        )
        assert ledger.recorded == 2

    def test_recorded_call_frees_its_slot(self, enforcer):
        """Nach dem Verbuchen darf die Reservierung das Budget nicht doppelt belasten."""
        inst, ledger = enforcer

        inst.check_before_call()
        ledger.bump()
        inst.record_after_call()

        # Ein Call verbucht, einer frei — der zweite muss durchgehen.
        inst.check_before_call()
        ledger.bump()
        inst.record_after_call()

        assert ledger.recorded == 2
        with pytest.raises(BudgetExceededError):
            inst.check_before_call()

    def test_remaining_hard_calls_accounts_for_reservations(self, enforcer):
        """``remaining_hard_calls`` zaehlt laufende Calls mit, nicht nur verbuchte."""
        inst, _ledger = enforcer

        assert inst.remaining_hard_calls() == 2
        inst.check_before_call()
        assert inst.remaining_hard_calls() == 1, (
            "Eine offene Reservierung muss das Restbudget senken, sonst "
            "deckelt der Dispatcher gegen einen veralteten Stand"
        )
