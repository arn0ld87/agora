"""Slice 6 / B-28 — ``log_round_end`` schrieb die simulierte Zeit nie.

Der Reader las ``action_data.get("simulated_hours", 0)``, der Writer legte den
Schlüssel nie an. Der Fortschritt blieb dadurch in jedem Lauf konstant 0 — die
UI zeigte dauerhaft „0 h“, obwohl die Simulation lief. Beide Seiten teilen
jetzt ``RoundEndEvent`` als Vertrag statt eines impliziten Dict-Schlüssels.

Kanonische Einheit sind Minuten: ``round * minutes_per_round`` ist ganzzahlig
exakt (``minutes_per_round`` liegt in [30, 120]). Stunden werden als ``float``
abgeleitet — bei 30 min/Runde ergäbe eine int-Stunde die Folge 0, 1, 1, 2 und
damit keinen streng wachsenden Fortschritt mehr.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.contracts.sim_action_log_contract import RoundEndEvent
from app.services.sim.action_log_reader import read_action_log_chunk
from app.services.sim.run_state_store import SimulationRunState

# ``action_logger`` lebt in backend/scripts und wird im Simulations-Subprozess
# als Top-Level-Modul importiert — hier derselbe Pfad wie zur Laufzeit.
_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from action_logger import PlatformActionLogger  # noqa: E402

# Default aus run_parallel_simulation.py: time_config.get("minutes_per_round", 30).
# Genau der Wert, bei dem eine int-Stunde die Monotonie brechen würde.
MINUTES_PER_ROUND = 30


def _read(logger: PlatformActionLogger, state: SimulationRunState, position: int = 0) -> int:
    return read_action_log_chunk(logger.log_path, position, state, "twitter")


def test_simulierte_zeit_waechst_nach_jeder_runde(tmp_path: Path) -> None:
    """Akzeptanzkriterium: nach jeder Runde echt größer als davor."""
    logger = PlatformActionLogger("twitter", str(tmp_path))
    state = SimulationRunState(simulation_id="sim_monotonie")

    position = 0
    verlauf: list[float] = []
    for round_num in range(1, 7):
        logger.log_round_end(round_num, 3, simulated_minutes=round_num * MINUTES_PER_ROUND)
        position = _read(logger, state, position)
        verlauf.append(state.simulated_hours)

    assert verlauf == [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    assert all(spaeter > frueher for frueher, spaeter in zip(verlauf, verlauf[1:])), verlauf
    assert state.current_round == 6


def test_writer_schreibt_den_schluessel_den_der_reader_liest(tmp_path: Path) -> None:
    """Kern von B-28: Writer und Reader benennen dasselbe Feld gleich."""
    logger = PlatformActionLogger("twitter", str(tmp_path))
    logger.log_round_end(1, 0, simulated_minutes=90)

    entry = json.loads(Path(logger.log_path).read_text(encoding="utf-8").strip())

    assert entry["event_type"] == "round_end"
    assert entry["simulated_minutes"] == 90
    assert RoundEndEvent.from_log_entry(entry).simulated_hours == 1.5


def test_altlog_ohne_zeitfeld_bricht_den_reader_nicht(tmp_path: Path) -> None:
    """Vor Slice 6 geschriebene Logs bleiben lesbar — 0 h statt Crash."""
    log_path = tmp_path / "twitter" / "actions.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        json.dumps({"event_type": "round_end", "round": 4, "actions_count": 2}) + "\n",
        encoding="utf-8",
    )
    state = SimulationRunState(simulation_id="sim_legacy")

    read_action_log_chunk(str(log_path), 0, state, "twitter")

    assert state.current_round == 4
    assert state.simulated_hours == 0.0


def test_fortschritt_faellt_nicht_auf_alteintraege_zurueck(tmp_path: Path) -> None:
    """Ein Eintrag ohne Zeitfeld darf einen erreichten Stand nicht nullen."""
    logger = PlatformActionLogger("twitter", str(tmp_path))
    state = SimulationRunState(simulation_id="sim_mixed")

    logger.log_round_end(1, 1, simulated_minutes=120)
    position = _read(logger, state)
    assert state.simulated_hours == 2.0

    with open(logger.log_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps({"event_type": "round_end", "round": 2}) + "\n")
    _read(logger, state, position)

    assert state.simulated_hours == 2.0


def test_defekte_zeile_verwirft_nicht_den_rest_des_chunks(tmp_path: Path) -> None:
    """Ein kaputtes Event darf nur sich selbst kosten, nicht die Folgezeilen."""
    log_path = tmp_path / "twitter" / "actions.jsonl"
    log_path.parent.mkdir(parents=True)
    log_path.write_text(
        json.dumps({"event_type": "round_end", "round": -5, "simulated_minutes": -60}) + "\n"
        + json.dumps({"event_type": "round_end", "round": 2, "simulated_minutes": 60}) + "\n",
        encoding="utf-8",
    )
    state = SimulationRunState(simulation_id="sim_korrupt")

    read_action_log_chunk(str(log_path), 0, state, "twitter")

    assert state.current_round == 2
    assert state.simulated_hours == 1.0


@pytest.mark.parametrize("runde", [48, 96])
def test_tages_uhrzeit_ist_kein_fortschritt(runde: int) -> None:
    """``simulated_hour`` springt bei ``% 24`` zurück — der Vertrag nicht.

    Runde 48 bei 30 min/Runde entspricht 24 h. Die Tages-Uhrzeit wäre wieder 0,
    der Fortschritt muss weiterlaufen. Genau diese Verwechslung soll der
    Vertrag durch die Feldbenennung ausschließen.
    """
    event = RoundEndEvent(round=runde, timestamp="", simulated_minutes=runde * MINUTES_PER_ROUND)

    assert event.simulated_hours == runde / 2
    assert event.simulated_hours >= 24.0
