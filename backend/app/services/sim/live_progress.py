"""Live-Fortschritt eines laufenden Simulations-Laufs (#1759 C1).

Der OASIS-Subprozess schreibt ``actions.jsonl`` und damit auch den Fortschritt
im ``run_state.json`` erst am Rundenende (``env.step`` fuehrt alle Agenten einer
Runde in einem Schritt aus). Die Trace-Tabellen der OASIS-SQLite-DBs fuellen
sich dagegen waehrend der Runde. Dieses Modul liest diesen Stand schreibgeschuetzt
und liefert ausserdem die Statusableitung, mit der ``state.json`` (Feld
``current_round``/``twitter_status``/``reddit_status``) waehrend des Laufs
mitgefuehrt wird.
"""

from __future__ import annotations

import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Optional

from .run_state_store import RunnerStatus, SimulationRunState

logger = logging.getLogger(__name__)

# Spiegel von ``scripts/oasis_action_ingest.FILTERED_ACTIONS``: dieselben
# Nicht-Kernaktionen zaehlen weder im Aktionsprotokoll noch hier.
_FILTERED_TRACE_ACTIONS = ("refresh", "sign_up")

_PLATFORM_DB_FILES = {
    "twitter": "twitter_simulation.db",
    "reddit": "reddit_simulation.db",
}


def count_trace_actions(db_path: str) -> Optional[int]:
    """Zaehlt die Kernaktionen in der ``trace``-Tabelle (read-only).

    Returns:
        Anzahl, oder ``None``, wenn die DB (noch) nicht existiert, gesperrt oder
        ohne ``trace``-Tabelle ist. ``None`` heisst "unveraendert lassen" und
        nie "0 Aktionen".
    """
    if not os.path.exists(db_path):
        return None
    placeholders = ",".join("?" for _ in _FILTERED_TRACE_ACTIONS)
    try:
        conn = sqlite3.connect(Path(db_path).resolve().as_uri() + "?mode=ro", uri=True, timeout=1.0)
        try:
            row = conn.execute(
                f"SELECT COUNT(*) FROM trace WHERE action NOT IN ({placeholders})",  # noqa: S608 — feste Platzhalter
                _FILTERED_TRACE_ACTIONS,
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        logger.debug("live_progress: trace-Zaehlung uebersprungen (%s): %s", db_path, exc)
        return None
    return int(row[0]) if row else None


def refresh_live_action_counts(sim_dir: str, state: SimulationRunState) -> None:
    """Setzt ``state.*_live_actions`` aus den OASIS-DBs; Werte sinken nie."""
    twitter = count_trace_actions(os.path.join(sim_dir, _PLATFORM_DB_FILES["twitter"]))
    if twitter is not None:
        state.twitter_live_actions = max(state.twitter_live_actions, twitter)
    reddit = count_trace_actions(os.path.join(sim_dir, _PLATFORM_DB_FILES["reddit"]))
    if reddit is not None:
        state.reddit_live_actions = max(state.reddit_live_actions, reddit)


def reset_live_action_counts(state: SimulationRunState) -> None:
    """Nach Prozessende zaehlt nur noch das Aktionsprotokoll."""
    state.twitter_live_actions = 0
    state.reddit_live_actions = 0


_RUNNER_TERMINAL_LABELS = {
    RunnerStatus.COMPLETED: "completed",
    RunnerStatus.FAILED: "failed",
    RunnerStatus.STOPPED: "stopped",
}


def derive_platform_status(
    *, enabled: bool, running: bool, completed: bool, runner_status: RunnerStatus
) -> str:
    """Plattformstatus fuer ``state.json`` aus dem Run-State.

    Deaktivierte Plattformen bleiben ``not_started``; sonst gewinnt das
    ``simulation_end``-Signal der Plattform vor dem Prozessstatus.
    """
    if not enabled:
        return "not_started"
    if completed:
        return "completed"
    if running:
        return "running"
    return _RUNNER_TERMINAL_LABELS.get(runner_status, "not_started")


def runtime_progress_key(run_state: SimulationRunState) -> tuple[Any, ...]:
    """Aenderungsschluessel: nur wenn er wechselt, wird ``state.json`` neu geschrieben.

    Der Monitor speichert alle 2 s; ``state.json`` soll aber nur bei einem
    Rundenwechsel oder Plattform-/Prozessstatuswechsel angefasst werden.
    """
    return (
        run_state.current_round,
        run_state.twitter_running,
        run_state.twitter_completed,
        run_state.reddit_running,
        run_state.reddit_completed,
        run_state.runner_status,
    )


def runtime_progress_snapshot(run_state: SimulationRunState, simulation_state: Any) -> tuple[int, str, str]:
    """(current_round, twitter_status, reddit_status) fuer ``state.json``."""
    return (
        run_state.current_round,
        derive_platform_status(
            enabled=bool(simulation_state.enable_twitter),
            running=run_state.twitter_running,
            completed=run_state.twitter_completed,
            runner_status=run_state.runner_status,
        ),
        derive_platform_status(
            enabled=bool(simulation_state.enable_reddit),
            running=run_state.reddit_running,
            completed=run_state.reddit_completed,
            runner_status=run_state.runner_status,
        ),
    )


def mirror_runtime_progress(manager: Any, run_state: SimulationRunState) -> Optional[tuple[int, str, str]]:
    """Schreibt Runde und Plattformstatus des Laufs in ``state.json``.

    Laedt den ``SimulationState`` frisch und ueberschreibt ausschliesslich diese
    drei Felder; ``status`` und alles andere bleiben unangetastet.

    Returns:
        Das geschriebene Tripel, oder ``None`` wenn es keinen State gibt.
    """
    simulation_state = manager.get_simulation(run_state.simulation_id)
    if simulation_state is None:
        return None
    snapshot = runtime_progress_snapshot(run_state, simulation_state)
    current_round, twitter_status, reddit_status = snapshot
    simulation_state.current_round = current_round
    simulation_state.twitter_status = twitter_status
    simulation_state.reddit_status = reddit_status
    manager._save_simulation_state(simulation_state)
    return snapshot
