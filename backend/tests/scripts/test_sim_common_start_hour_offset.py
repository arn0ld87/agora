"""Sub-Slice 05.9 — `compute_start_hour_offset` für kurze Smoke-Runs.

Bei `max_rounds=3` und `minutes_per_round=60` durchläuft der Simulator
nur die Stunden 0/1/2. Wenn alle Agents `active_hours` ≥ 9 haben,
ist das Round-Loop ein No-Op ("0 actions, 0.0s pro Round").

Lösung: simulated_clock-Offset auf die meistgenutzte Aktivstunde
verschieben, sofern der Run zu kurz für einen ganzen 24-h-Zyklus ist
UND keine explizite `time_config.start_hour` gesetzt wurde.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[2]
_SCRIPTS_DIR = _BACKEND_DIR / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from _sim_common import compute_start_hour_offset  # noqa: E402


class TestExplicitStartHourWins:
    """``time_config.start_hour`` setzt den Offset hart — Heuristik out."""

    def test_explicit_zero(self):
        config = {"time_config": {"start_hour": 0}, "agent_configs": []}
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 0

    def test_explicit_value_passes_through(self):
        config = {"time_config": {"start_hour": 14}, "agent_configs": []}
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 14

    def test_explicit_overrides_active_hours_heuristic(self):
        """Auch wenn Active-Hours-Cluster anders peakt — explicit gewinnt."""
        config = {
            "time_config": {"start_hour": 3},
            "agent_configs": [{"active_hours": [9, 10, 11]}] * 5,
        }
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 3

    def test_explicit_modulo_24(self):
        config = {"time_config": {"start_hour": 27}, "agent_configs": []}
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 3


class TestLongRunReturnsZero:
    """Bei Runs ≥ 24 h simulierter Zeit greift Offset nicht — Loop deckt
    den ganzen Tag ab, jeder Active-Hour-Cluster wird erreicht."""

    def test_24h_run_returns_zero(self):
        config = {"agent_configs": [{"active_hours": [9, 10, 11]}]}
        # 24 rounds * 60 min = 1440 min = 24 h
        assert compute_start_hour_offset(config, total_rounds=24, minutes_per_round=60) == 0

    def test_more_than_24h_returns_zero(self):
        config = {"agent_configs": [{"active_hours": [9]}]}
        assert compute_start_hour_offset(config, total_rounds=48, minutes_per_round=60) == 0


class TestShortRunUsesActiveHourHeuristic:
    """Kurze Runs: am meistgenutzte Active-Hour-Bucket gewinnt."""

    def test_most_common_active_hour_wins(self):
        config = {
            "agent_configs": [
                {"active_hours": [9, 10]},
                {"active_hours": [9, 14]},
                {"active_hours": [9, 18]},
                {"active_hours": [10, 11]},
            ],
        }
        # 9 erscheint 3x, 10 + 14 + 18 + 11 je 1-2x → 9 gewinnt
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 9

    def test_short_run_no_agents_falls_back_to_nine(self):
        """Ohne agent_configs: fallback 9 (typischer Office-Start)."""
        config = {"agent_configs": []}
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 9

    def test_short_run_no_active_hours_falls_back_to_nine(self):
        config = {"agent_configs": [{"active_hours": []}, {"active_hours": []}]}
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 9

    def test_short_run_with_modulo_24_hours(self):
        """Active-Hour-Werte > 23 werden via mod 24 gebucket."""
        config = {"agent_configs": [{"active_hours": [27, 9]}]}  # 27 % 24 == 3
        result = compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60)
        assert result in (3, 9)  # Counter ist tie-break-frei → beide OK


class TestEdgeCases:
    """Boundary-Behaviour: leere Configs, Tipos, missing keys."""

    def test_empty_config(self):
        assert compute_start_hour_offset({}, total_rounds=3, minutes_per_round=60) == 9

    def test_missing_time_config(self):
        config = {"agent_configs": [{"active_hours": [9]}]}
        # time_config fehlt → kein explicit, Heuristik greift
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=60) == 9

    def test_minutes_per_round_30_short_run(self):
        """3 rounds * 30 min = 90 min — eindeutig kurz, Heuristik greift."""
        config = {"agent_configs": [{"active_hours": [9, 10]}]}
        assert compute_start_hour_offset(config, total_rounds=3, minutes_per_round=30) == 9

    def test_borderline_just_under_24h(self):
        """23 rounds * 60 min = 23 h → < 24 → Heuristik greift."""
        config = {"agent_configs": [{"active_hours": [14]}]}
        assert compute_start_hour_offset(config, total_rounds=23, minutes_per_round=60) == 14
