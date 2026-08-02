"""Slice 6 / B-28 — ``log_round_end`` schrieb die simulierte Zeit nie.

Der Reader las ``action_data.get("simulated_hours", 0)``, der Writer legte den
Schlüssel nie an. In ``run_state.json`` stand deshalb über den ganzen Lauf
``simulated_hours: 0`` bei ``total_simulation_hours: 72`` (#1014). Beide Seiten
teilen jetzt ``RoundEndEvent`` als Vertrag statt eines impliziten Dict-
Schlüssels.

Diese Tests decken den Datenpfad Writer → Reader → ``SimulationRunState`` ab.
Die Frontend-Anzeige ist laut #1014 out of scope und liest den Wert bis heute
nicht (#1018) — kein Test hier belegt eine Wirkung auf die Oberfläche.

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
from pydantic import ValidationError

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
    """Vor Slice 6 geschriebene Logs bleiben lesbar — 0 h statt Crash.

    Anker ist ``simulated_minutes: int = Field(default=0)``. Ohne den Default
    ist das Feld required, ``from_log_entry`` wirft eine ValidationError, der
    Reader verwirft die Zeile — ``current_round`` bliebe dann 0 statt 4.
    """
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


@pytest.mark.parametrize("runde", [48, 49, 97])
def test_tages_uhrzeit_ist_kein_fortschritt(runde: int) -> None:
    """``simulated_hour`` springt bei ``% 24`` zurück — der Vertrag nicht.

    Runde 48 bei 30 min/Runde entspricht 24 h. Die Tages-Uhrzeit wäre wieder 0,
    der Fortschritt muss weiterlaufen. Genau diese Verwechslung soll der
    Vertrag durch die Feldbenennung ausschließen.

    49 und 97 liegen bewusst auf einer halben Stunde (1470 min ⇒ 24.5 h,
    2910 min ⇒ 48.5 h): sie fallen um, sobald ``simulated_hours`` ganzzahlig
    dividiert. Ein Parametersatz aus reinen Stunden-Vielfachen wäre gegen
    ``//`` blind.
    """
    event = RoundEndEvent(round=runde, timestamp="", simulated_minutes=runde * MINUTES_PER_ROUND)

    assert event.simulated_hours == runde / 2
    assert event.simulated_hours >= 24.0


def test_float_minuten_toeten_den_writer_nicht(tmp_path: Path) -> None:
    """Eine Config am Schema vorbei darf ``log_round_end`` nicht abstürzen lassen.

    Der Subprozess lädt ``minutes_per_round`` roh aus JSON. Bei ``45.5``
    erreicht der Writer einen Float; ohne die Rundung im Vertrag stürbe er an
    einer ValidationError, statt eine Zeile zu schreiben.
    """
    logger = PlatformActionLogger("twitter", str(tmp_path))
    state = SimulationRunState(simulation_id="sim_float")

    logger.log_round_end(1, 0, simulated_minutes=45.5)  # type: ignore[arg-type]
    _read(logger, state)

    entry = json.loads(Path(logger.log_path).read_text(encoding="utf-8").strip())
    assert entry["simulated_minutes"] == 46
    assert state.current_round == 1


@pytest.mark.parametrize(
    ("feld", "wert"),
    [
        ("simulated_minutes", -1),
        ("simulated_minutes", -30),
        ("round", -1),
        ("actions_count", -1),
    ],
)
def test_negative_werte_werden_abgelehnt(feld: str, wert: int) -> None:
    """Negative Zähler sind keine gültige Sim-Zeit — der Vertrag muss sie ablehnen.

    Ohne diesen Test bliebe ``ge=0`` ein ungeprüftes Versprechen: Man könnte
    die Schranke aus dem Feld entfernen, ohne dass ein Test umfällt. Eine
    negative Minutenzahl würde als Fortschritt durchlaufen und die Anzeige
    rückwärts laufen lassen — derselbe Klassenfehler wie das dauerhafte 0
    aus B-28, nur mit umgekehrtem Vorzeichen.
    """
    with pytest.raises(ValidationError):
        RoundEndEvent(**{"timestamp": "", feld: wert})  # type: ignore[arg-type]


def test_alt_log_mit_negativer_zeit_bricht_den_reader_nicht(tmp_path: Path) -> None:
    """Ein defekter Alt-Eintrag wird verworfen, nicht durchgereicht.

    ``from_log_entry`` validiert dieselbe Schranke wie der Konstruktor. Ein
    von Hand manipuliertes Log darf den Fortschritt nicht zurückdrehen.
    """
    with pytest.raises(ValidationError):
        RoundEndEvent.from_log_entry(
            {"event_type": "round_end", "round": 1, "simulated_minutes": -60}
        )


def test_reader_traegt_die_zeit_ueber_die_tagesgrenze(tmp_path: Path) -> None:
    """Derselbe Schutz wie ``test_tages_uhrzeit_ist_kein_fortschritt``, eine Ebene tiefer.

    Jener Test endet beim ``RoundEndEvent``. Ob der *Reader* die Stunden
    kumulativ übernimmt, blieb offen: ``test_simulierte_zeit_waechst_nach_jeder_runde``
    kommt über Runde 6 (3.0 h) nicht hinaus und sieht die Tagesgrenze nie.

    Baute jemand im Reader ein ``% 24`` ein oder läse er ein Tages-Uhrzeit-Feld,
    kollabierten 24.0/24.5/48.5 h auf 0.0/0.5/0.5. Das ``max()`` in
    ``read_action_log_chunk`` würde den Rückschritt *verdecken* statt ihn zu
    melden — die Anzeige bliebe ab Tag 2 stehen. Genau der Klassenfehler aus
    B-28 (dauerhafte 0), nur eine Tagesgrenze später.
    """
    logger = PlatformActionLogger("twitter", str(tmp_path))
    state = SimulationRunState(simulation_id="sim_tagesgrenze")

    position = 0
    verlauf: list[float] = []
    for round_num in (48, 49, 97):
        logger.log_round_end(round_num, 3, simulated_minutes=round_num * MINUTES_PER_ROUND)
        position = _read(logger, state, position)
        verlauf.append(state.simulated_hours)

    assert verlauf == [24.0, 24.5, 48.5]
    assert all(spaeter > frueher for frueher, spaeter in zip(verlauf, verlauf[1:])), verlauf
    assert state.current_round == 97
