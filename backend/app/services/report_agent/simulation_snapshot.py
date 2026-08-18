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


__all__ = ["capture_simulation_snapshot"]
