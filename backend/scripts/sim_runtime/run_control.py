"""Gemeinsame Rundengrenzen-Kontrolle: Pause, Stop, Budget (Tech-Review Slice B4c).

Vor dieser Extraktion hatte nur ``platform_runner.py`` (Single-Platform
Twitter/Reddit) diese drei Pruefungen an jeder Rundengrenze:
Pause abwarten, kooperativen Stop pruefen, hartes Budget pruefen.
``run_parallel_simulation.py`` — der Default-Pfad fuer jeden Lauf, der nicht
explizit Twitter- oder Reddit-only ist — hatte keine davon: kein Hard-Budget,
keine Pause, kein Stop griffen dort.

Dieses Modul zieht die Pruefreihenfolge aus ``platform_runner.py`` heraus,
damit beide Runner denselben Kontrollpfad benutzen. Verhaltenserhalt fuer
``platform_runner.py`` ist Pflicht: identische Reihenfolge (Pause -> Stop ->
Budget), identische Log-Ausgaben, identische Exception-Behandlung.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional


class RoundAction(str, Enum):
    """Ergebnis einer Rundengrenzen-Pruefung."""

    CONTINUE = "continue"
    STOP = "stop"
    BUDGET_ABORT = "budget_abort"


class RoundDecision:
    """Entscheidung von :meth:`RoundBoundaryControl.check` fuer eine Runde."""

    __slots__ = ("action", "budget_abort_info")

    def __init__(self, action: RoundAction, budget_abort_info: Optional[dict] = None) -> None:
        self.action = action
        self.budget_abort_info = budget_abort_info


class RoundBoundaryControl:
    """Pause/Stop/Budget-Pruefung an der Grenze zwischen zwei Simulationsrunden.

    Der Aufrufer ruft :meth:`check` am Anfang jeder Runden-Iteration, VOR dem
    Bau der Runden-Aktionen. Reihenfolge (Pause abwarten -> Stop-Request
    pruefen -> Budget-Grenze pruefen) ist ein Verhaltensvertrag aus
    ``platform_runner.py`` und darf sich nicht aendern.
    """

    def __init__(self, simulation_dir: str, budget_guard: Optional[Any] = None) -> None:
        self.simulation_dir = simulation_dir
        self.budget_guard = budget_guard

    def check(self, round_num: int) -> RoundDecision:
        # Pause abwarten + kooperativen Stop pruefen (Phase 4 — Soft-Pause
        # zwischen Runden). Wie im urspruenglichen Inline-Code: jede Exception
        # (fehlende Flask-App, Importfehler bei Direktausfuehrung) wird
        # geschluckt — die Simulation laeuft dann ungebremst weiter.
        try:
            from app.services.simulation_ipc import read_control_state, wait_while_paused

            wait_while_paused(self.simulation_dir)
            if read_control_state(self.simulation_dir).get("stop_requested"):
                print(f"  Stop requested via control_state.json — exiting after round {round_num}")
                return RoundDecision(RoundAction.STOP)
        except Exception:
            pass

        # Budget-Guard (Issue #764): harte Limits an der Runden-Grenze, BEVOR
        # weitere planbare Modellaufrufe entstehen. Die laufende Runde wurde
        # zuvor sauber abgeschlossen; Teilresultate bleiben in der SQLite-DB
        # erhalten.
        if self.budget_guard is not None:
            try:
                budget_abort_info = self.budget_guard.check_round_boundary(round_num)
            except Exception as exc:  # noqa: BLE001 — Check-Fehler stoppt die Sim nicht
                print(f"[budget-guard] round check failed ({exc})", flush=True)
                budget_abort_info = None
            if budget_abort_info is not None:
                print(
                    f"  [budget-guard] hard budget exceeded "
                    f"({budget_abort_info['dimension']}: "
                    f"{budget_abort_info['observed']} >= {budget_abort_info['threshold']}) "
                    f"— stopping before round {round_num + 1}",
                    flush=True,
                )
                return RoundDecision(RoundAction.BUDGET_ABORT, budget_abort_info)

        return RoundDecision(RoundAction.CONTINUE)
