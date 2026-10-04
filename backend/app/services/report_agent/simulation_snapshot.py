"""Erfasst den Simulationsstand beim Start einer Reportgenerierung (Issue #1192).

Eine Reportgenerierung darf starten, während die zugrunde liegende Simulation
noch läuft — das ist eine bewusste Produktentscheidung und bleibt erlaubt.
Fachlich fragwürdig war nicht der Start, sondern die Stille darüber: der Report
analysierte dann einen Zwischenstand, dessen Rundenzahl im Ergebnis nirgends
ausgewiesen wurde. Einem fertigen Bericht war nicht anzusehen, ob er auf zehn
abgeschlossenen Runden beruht oder auf vieren.

Erfasst wird der Stand **beim Start**, nicht beim Abschluss — das ist der
Datenbestand, den der Agent tatsächlich gesehen hat. Läuft die Simulation
während der Reportgenerierung weiter, gehen die späteren Runden nicht mehr in
den Bericht ein; sie hier auszuweisen wäre irreführend.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from ...utils.logger import get_logger

logger = get_logger("agora.report_agent")


def capture_simulation_snapshot(simulation_id: str) -> Optional[Dict[str, Any]]:
    """Liest den aktuellen Laufzustand der Simulation.

    Gibt ``None`` zurück, wenn kein Laufzustand ermittelbar ist — etwa bei
    einer Simulation, die nie über den Runner gestartet wurde. Ein fehlender
    Snapshot ist kein Fehler: er bedeutet "unbekannt", und das ist ehrlicher
    als eine erfundene Null.

    Die Ermittlung darf die Reportgenerierung unter keinen Umständen stoppen.
    """
    try:
        from ..simulation_runner import SimulationRunner  # noqa: PLC0415

        run_state = SimulationRunner.get_run_state(simulation_id)
    except Exception:  # noqa: BLE001 — ein unbekannter Stand kostet keinen Report
        logger.warning(
            "simulation snapshot not readable: simulation=%s",
            simulation_id,
            exc_info=True,
        )
        return None

    if run_state is None:
        return None

    runner_status = getattr(run_state, "runner_status", None)
    status_value = getattr(runner_status, "value", runner_status)

    return {
        "rounds_completed": int(getattr(run_state, "current_round", 0) or 0),
        "total_rounds": int(getattr(run_state, "total_rounds", 0) or 0),
        "simulation_running": status_value == "running",
        # Der Status wurde bisher gelesen und weggeworfen — nur die Frage "läuft
        # sie noch?" überlebte. Damit war einem Report nicht anzusehen, ob die
        # Simulation abgeschlossen oder gescheitert war: im Referenzlauf
        # report_cc2ef45da5e9 stand "failed" bei 45 von 48 Runden, und der
        # Bericht ging als "completed" hinaus.
        "simulation_status": str(status_value) if status_value is not None else None,
        "captured_at": datetime.now().isoformat(),
    }


def load_simulation_llm_call_stats(
    simulation_id: str,
) -> tuple[Optional[int], Optional[int]]:
    """``(Aufrufe gesamt, davon fehlgeschlagen)`` des Simulations-Jobs (#1766).

    Die Zuordnung Simulation -> Job ist dieselbe wie bei
    ``run_budget.inherit_budget_from_simulation``: der juengste ``simulation_run``
    der Run-Registry mit ``linked_ids.simulation_id``. Der Subprozess schreibt
    jeden physischen Modellversuch (auch gescheiterte) unter dessen ``run_id``
    ins Ledger (``sim_runtime.budget_guard``); gelesen wird der persistierte
    Abschluss-Snapshot, bei einem noch laufenden Job die Aggregation der
    Events (wie ``report_export``).

    ``(None, None)`` heisst "nicht ermittelbar" — kein Job gefunden, kein
    lesbares Summary oder ein Altbestand ohne ``failed_llm_calls``. Das ist
    ausdruecklich keine Aussage "keine Ausfaelle". Die Ermittlung darf die
    Reportgenerierung unter keinen Umstaenden stoppen.
    """
    try:
        from ..run_registry import RunRegistry  # noqa: PLC0415
        from ..run_usage_ledger import (  # noqa: PLC0415
            aggregate_usage,
            load_usage_summary,
        )

        run = RunRegistry().get_latest_by_linked_id(
            "simulation_id", simulation_id, run_type="simulation_run"
        )
        run_id = (run or {}).get("run_id")
        if not run_id:
            return (None, None)

        usage = load_usage_summary(run_id) or aggregate_usage(run_id)
    except Exception:  # noqa: BLE001 — ein unbekannter Stand kostet keinen Report
        logger.warning(
            "simulation llm call stats not readable: simulation=%s",
            simulation_id,
            exc_info=True,
        )
        return (None, None)

    return (usage.totals.llm_calls, usage.totals.failed_llm_calls)


__all__ = ["capture_simulation_snapshot", "load_simulation_llm_call_stats"]
