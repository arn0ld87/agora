"""Tests für die Sim-Zeit-Auflösung innerhalb einer Runde (#1018).

Die simulierte Uhr rückte bisher nur einmal pro Runde vor: ``_sim_dt`` wurde
vor der Action-Schleife berechnet, alle CREATE_POST-Frames einer Runde trugen
denselben ``sim_time``. Die Live-Feed-Kopfzeile sprang dadurch nur an
Rundengrenzen und stand dazwischen still.

``compute_post_sim_time`` verteilt die Actions einer Runde über deren
Minutenbudget. Kritisch ist die obere Schranke: der letzte Wert einer Runde
muss strikt kleiner bleiben als der erste Wert der Folgerunde — ``useSimClock``
im Frontend erzwingt Monotonie und verwirft rückwärts laufende Frames
kommentarlos.
"""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import compute_post_sim_time  # noqa: E402

ANCHOR = datetime(2026, 8, 1, 0, 0, 0, tzinfo=timezone.utc)
START_HOUR_OFFSET = 22
MINUTES_PER_ROUND = 60


def _at(simulated_minutes: int, action_index: int, action_count: int) -> datetime:
    return compute_post_sim_time(
        ANCHOR,
        START_HOUR_OFFSET,
        simulated_minutes,
        MINUTES_PER_ROUND,
        action_index,
        action_count,
    )


class TestIntraRoundResolution:
    def test_actions_of_one_round_are_strictly_increasing(self):
        """Der eigentliche Defekt: vorher waren alle Werte einer Runde gleich."""
        times = [_at(0, idx, 5) for idx in range(5)]

        assert times == sorted(times)
        assert len(set(times)) == 5, f"Werte nicht eindeutig: {times}"

    def test_first_action_matches_previous_round_value(self):
        """Rückwärtskompatibilität: Index 0 liefert exakt den alten Rundenwert."""
        expected = ANCHOR.replace(hour=START_HOUR_OFFSET)

        assert _at(0, 0, 12) == expected

    def test_last_action_stays_below_next_round_start(self):
        """Die Rundengrenze darf nicht überschritten werden."""
        action_count = 7
        last_of_round = _at(0, action_count - 1, action_count)
        first_of_next_round = _at(MINUTES_PER_ROUND, 0, action_count)

        assert last_of_round < first_of_next_round

    def test_single_and_empty_action_counts_fall_back_to_round_value(self):
        """Kein ZeroDivisionError, kein Sprung bei 0 oder 1 Action."""
        round_value = ANCHOR.replace(hour=START_HOUR_OFFSET)

        assert _at(0, 0, 1) == round_value
        assert _at(0, 0, 0) == round_value
        assert _at(0, 3, 1) == round_value

    def test_index_beyond_count_is_clamped(self):
        """Ein zu großer Index darf die Rundengrenze nicht aufbrechen."""
        action_count = 4
        clamped = _at(0, 99, action_count)

        assert clamped == _at(0, action_count - 1, action_count)
        assert clamped < _at(MINUTES_PER_ROUND, 0, action_count)

    def test_sequence_across_two_rounds_is_monotonic(self):
        """Über Rundengrenzen hinweg bleibt die gesamte Folge monoton."""
        action_count = 3
        sequence = [
            _at(simulated_minutes, idx, action_count)
            for simulated_minutes in (0, MINUTES_PER_ROUND, MINUTES_PER_ROUND * 2)
            for idx in range(action_count)
        ]

        assert sequence == sorted(sequence)
        assert len(set(sequence)) == len(sequence)

    def test_zero_minutes_per_round_keeps_round_value(self):
        """Ohne Minutenbudget gibt es nichts zu verteilen."""
        times = [
            compute_post_sim_time(ANCHOR, START_HOUR_OFFSET, 0, 0, idx, 5)
            for idx in range(5)
        ]

        assert set(times) == {ANCHOR.replace(hour=START_HOUR_OFFSET)}
