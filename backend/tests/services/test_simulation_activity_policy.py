"""Tests fuer Aktivitaets-Untergrenzen und geteilte Runden-Auswahl (#1713 Slice S4).

Siehe ``docs/runbooks/simulation-liveness.md``: L1 (``actions_per_agent_round``)
>= 0,6, L2 (``active_agent_share_median``) >= 40 %. Baseline vor diesem Slice
lag bei 0,16-0,22 Aktionen/Agent/Runde bzw. rund 25 % aktiven Agenten/Runde.
"""

from __future__ import annotations

import random
import statistics

import pytest

from app.services.simulation_activity_policy import (
    ACTIVITY_LEVEL_FLOOR,
    CORE_ACTIVE_HOURS,
    enforce_active_hours_floor,
    enforce_activity_level_floor,
    enforce_agents_per_hour_floor,
    select_active_agent_ids,
)


class TestEnforceAgentsPerHourFloor:
    @pytest.mark.parametrize(
        "num_entities, given_min, given_max, expected_min, expected_max",
        [
            # N=1: keine echte Bandbreite moeglich, min==max bleibt bei 1.
            (1, 1, 5, 1, 1),
            # N=5: Werte unter der Untergrenze (0,4*5=2 / 0,7*5=3,5->4) werden
            # angehoben.
            (5, 1, 2, 2, 4),
            # N=55: der Baseline-Defekt (5/20 unabhaengig von N) wird auf die
            # Ratio angehoben.
            (55, 5, 20, 22, 39),
            # N=55: bereits ueber der Untergrenze liegende Werte bleiben
            # unveraendert.
            (55, 30, 40, 30, 40),
        ],
    )
    def test_raises_low_values_to_floor(
        self, num_entities, given_min, given_max, expected_min, expected_max
    ) -> None:
        result_min, result_max = enforce_agents_per_hour_floor(
            given_min, given_max, num_entities
        )
        assert (result_min, result_max) == (expected_min, expected_max)

    def test_never_exceeds_num_entities(self) -> None:
        result_min, result_max = enforce_agents_per_hour_floor(1, 2, 3)
        assert result_min <= 3
        assert result_max <= 3
        assert (result_min, result_max) == (2, 3)

    def test_zero_entities_is_a_noop(self) -> None:
        assert enforce_agents_per_hour_floor(5, 20, 0) == (5, 20)


class TestEnforceActivityLevelFloor:
    @pytest.mark.parametrize(
        "given, expected",
        [
            (0.1, ACTIVITY_LEVEL_FLOOR),
            (0.2, ACTIVITY_LEVEL_FLOOR),  # Baseline-Defektwert (Behoerden-Regel)
            (0.5, 0.5),
            (0.8, 0.8),
            (1.5, 1.0),  # gedeckelt
        ],
    )
    def test_floor_and_cap(self, given: float, expected: float) -> None:
        assert enforce_activity_level_floor(given) == expected


class TestEnforceActiveHoursFloor:
    def test_narrow_window_gets_core_hours_added(self) -> None:
        # Baseline-Defekt: Behoerden-Regel liefert nur 9-17 Uhr (9 Stunden).
        result = enforce_active_hours_floor(range(9, 18))
        assert set(result) == CORE_ACTIVE_HOURS
        assert result == sorted(CORE_ACTIVE_HOURS)

    def test_off_peak_hours_are_preserved_not_added(self) -> None:
        result = enforce_active_hours_floor([1, 2, 3])
        assert set(result) == {1, 2, 3} | CORE_ACTIVE_HOURS
        assert 0 not in result
        assert 4 not in result
        assert 5 not in result

    def test_already_wide_window_is_unaffected(self) -> None:
        wide = list(range(0, 24))
        assert enforce_active_hours_floor(wide) == wide


class TestSelectActiveAgentIds:
    @staticmethod
    def _agent_configs(count: int, *, activity_level: float, active_hours) -> list[dict]:
        return [
            {
                "agent_id": i,
                "activity_level": activity_level,
                "active_hours": list(active_hours),
            }
            for i in range(count)
        ]

    @staticmethod
    def _cycled_hours(rounds: int) -> list[int]:
        """20 Runden ueber einen 18-Stunden-Zyklus (06-23 Uhr)."""
        return [(h % 18) + 6 for h in range(rounds)]

    def test_pre_floor_baseline_misses_the_l2_target(self) -> None:
        """Nachweis des Defekts: Baseline-Werte (agents_per_hour 5/20,
        activity_level 0.2, active_hours nur 9-17 Uhr) erreichen den
        L2-Zielwert (>= 40 %) nicht — deshalb braucht es die Floors.
        """
        num_agents = 100
        agent_configs = self._agent_configs(
            num_agents, activity_level=0.2, active_hours=range(9, 18)
        )
        time_config = {
            "agents_per_hour_min": 5,
            "agents_per_hour_max": 20,
            "peak_hours": [],
            "off_peak_hours": [],
        }
        rng = random.Random(1234)
        shares = [
            len(select_active_agent_ids(time_config, agent_configs, hour, rng)) / num_agents
            for hour in self._cycled_hours(20)
        ]
        assert statistics.median(shares) < 0.4

    def test_post_floor_meets_the_l2_target(self) -> None:
        """Nach Anwendung aller drei Floors (agents_per_hour, activity_level,
        active_hours) liegt der Median ueber 20 Runden >= 40 % — der Nachweis
        fuer L2 (``active_agent_share_median``,
        ``docs/runbooks/simulation-liveness.md``).
        """
        num_agents = 500
        min_floor, max_floor = enforce_agents_per_hour_floor(5, 20, num_agents)
        activity_level = enforce_activity_level_floor(0.2)
        active_hours = enforce_active_hours_floor(range(9, 18))
        agent_configs = self._agent_configs(
            num_agents, activity_level=activity_level, active_hours=active_hours
        )
        time_config = {
            "agents_per_hour_min": min_floor,
            "agents_per_hour_max": max_floor,
            "peak_hours": [],
            "off_peak_hours": [],
        }
        rng = random.Random(1234)
        shares = [
            len(select_active_agent_ids(time_config, agent_configs, hour, rng)) / num_agents
            for hour in self._cycled_hours(20)
        ]
        assert statistics.median(shares) >= 0.4

    def test_empty_candidate_pool_returns_empty_list(self) -> None:
        assert select_active_agent_ids({}, [], 12, random.Random(0)) == []

    def test_default_rng_is_the_global_random_module(self) -> None:
        """Ohne expliziten ``rng`` bleibt der Produktivpfad unveraendert: der
        globale ``random``-Zustand (seedbar via ``seed_simulation_rng`` in
        ``backend/scripts/_sim_common.py``).
        """
        agent_configs = self._agent_configs(10, activity_level=1.0, active_hours=range(0, 24))
        # min == max => random.uniform(5, 5) ist deterministisch 5.0,
        # unabhaengig vom Seed-Zustand.
        time_config = {"agents_per_hour_min": 5, "agents_per_hour_max": 5}
        random.seed(42)
        result = select_active_agent_ids(time_config, agent_configs, 12)
        assert len(result) == 5
