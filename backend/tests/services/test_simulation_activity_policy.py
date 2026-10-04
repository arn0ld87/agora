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
    AGENTS_PER_HOUR_MAX_RATIO,
    AGENTS_PER_HOUR_MIN_RATIO,
    CORE_ACTIVE_HOURS,
    ENV_AGENTS_PER_HOUR_MAX_RATIO,
    ENV_AGENTS_PER_HOUR_MIN_RATIO,
    enforce_active_hours_floor,
    enforce_activity_level_floor,
    enforce_agents_per_hour_floor,
    resolve_agents_per_hour_ratios,
    select_active_agent_ids,
)

# Bis Issue #1772 waren 0,4/0,7 der feste Standard (#1713 S4, L2-Ziel >= 40 %).
# Seit #1772 sind die Quoten konfigurierbar, der Standard liegt bei 0,25/0,5.
# Die Tests der urspruenglichen S4-Zahlen geben die frueheren Quoten daher
# ausdruecklich mit -- die Erwartungswerte bleiben unveraendert.
S4_MIN_RATIO = 0.4
S4_MAX_RATIO = 0.7


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
            given_min,
            given_max,
            num_entities,
            min_ratio=S4_MIN_RATIO,
            max_ratio=S4_MAX_RATIO,
        )
        assert (result_min, result_max) == (expected_min, expected_max)

    def test_never_exceeds_num_entities(self) -> None:
        result_min, result_max = enforce_agents_per_hour_floor(
            1, 2, 3, min_ratio=S4_MIN_RATIO, max_ratio=S4_MAX_RATIO
        )
        assert result_min <= 3
        assert result_max <= 3
        assert (result_min, result_max) == (2, 3)

    def test_zero_entities_is_a_noop(self) -> None:
        assert enforce_agents_per_hour_floor(5, 20, 0) == (5, 20)


class TestConfigurableRatios:
    """Issue #1772: Quoten konfigurierbar, Standard 0,25/0,5."""

    def test_defaults_are_025_and_05(self) -> None:
        assert (AGENTS_PER_HOUR_MIN_RATIO, AGENTS_PER_HOUR_MAX_RATIO) == (0.25, 0.5)
        assert resolve_agents_per_hour_ratios({}.get) == (0.25, 0.5)

    @pytest.mark.parametrize(
        "num_entities, given_min, given_max, expected",
        [
            (5, 1, 2, (2, 3)),  # ceil(1,25)=2 / ceil(2,5)=3
            (52, 5, 20, (13, 26)),  # der gemessene Lauf: 52 Agenten
            (55, 5, 20, (14, 28)),
            (55, 30, 40, (30, 40)),  # ueber der Untergrenze: unveraendert
        ],
    )
    def test_default_floor(self, num_entities, given_min, given_max, expected) -> None:
        assert enforce_agents_per_hour_floor(given_min, given_max, num_entities) == expected

    def test_configured_ratios_are_used(self, monkeypatch) -> None:
        values = {ENV_AGENTS_PER_HOUR_MIN_RATIO: 0.4, ENV_AGENTS_PER_HOUR_MAX_RATIO: 0.7}
        assert resolve_agents_per_hour_ratios(values.get) == (0.4, 0.7)
        monkeypatch.setattr(
            "app.services.simulation_activity_policy._settings_reader",
            lambda: values.get,
        )
        assert enforce_agents_per_hour_floor(5, 20, 55) == (22, 39)

    def test_string_values_from_env_are_accepted(self) -> None:
        values = {ENV_AGENTS_PER_HOUR_MIN_RATIO: "0.3", ENV_AGENTS_PER_HOUR_MAX_RATIO: "0.6"}
        assert resolve_agents_per_hour_ratios(values.get) == (0.3, 0.6)

    @pytest.mark.parametrize(
        "min_value, max_value",
        [
            (0.0, 0.5),  # min muss > 0 sein
            (-0.1, 0.5),
            (0.6, 0.5),  # min > max
            (0.25, 1.5),  # max > 1
            ("abc", 0.5),
            (0.25, "viel"),
            (float("nan"), 0.5),
            (float("inf"), float("inf")),
        ],
    )
    def test_invalid_pair_falls_back_to_defaults_and_logs(
        self, min_value, max_value, caplog
    ) -> None:
        import logging

        records: list[logging.LogRecord] = []

        class _Collect(logging.Handler):
            def emit(self, record: logging.LogRecord) -> None:
                records.append(record)

        target = logging.getLogger("agora.simulation_activity_policy")
        handler = _Collect(level=logging.WARNING)
        target.addHandler(handler)
        try:
            values = {
                ENV_AGENTS_PER_HOUR_MIN_RATIO: min_value,
                ENV_AGENTS_PER_HOUR_MAX_RATIO: max_value,
            }
            assert resolve_agents_per_hour_ratios(values.get) == (0.25, 0.5)
        finally:
            target.removeHandler(handler)
        assert any(
            r.levelno == logging.WARNING and ENV_AGENTS_PER_HOUR_MIN_RATIO in r.getMessage()
            for r in records
        )

    def test_settings_schema_defaults_match_policy_constants(self) -> None:
        from app.services.settings_schema import field_by_key

        min_spec = field_by_key(ENV_AGENTS_PER_HOUR_MIN_RATIO)
        max_spec = field_by_key(ENV_AGENTS_PER_HOUR_MAX_RATIO)
        assert min_spec is not None and max_spec is not None
        assert min_spec.default == AGENTS_PER_HOUR_MIN_RATIO
        assert max_spec.default == AGENTS_PER_HOUR_MAX_RATIO

    def test_default_settings_layer_resolves_to_defaults(self, monkeypatch) -> None:
        monkeypatch.delenv(ENV_AGENTS_PER_HOUR_MIN_RATIO, raising=False)
        monkeypatch.delenv(ENV_AGENTS_PER_HOUR_MAX_RATIO, raising=False)
        assert resolve_agents_per_hour_ratios() == (0.25, 0.5)

    def test_env_override_reaches_the_floor_via_settings_layer(self, monkeypatch) -> None:
        monkeypatch.setenv(ENV_AGENTS_PER_HOUR_MIN_RATIO, "0.4")
        monkeypatch.setenv(ENV_AGENTS_PER_HOUR_MAX_RATIO, "0.7")
        assert enforce_agents_per_hour_floor(5, 20, 55) == (22, 39)


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
        min_floor, max_floor = enforce_agents_per_hour_floor(
            5, 20, num_agents, min_ratio=S4_MIN_RATIO, max_ratio=S4_MAX_RATIO
        )
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

    def test_default_ratios_trade_the_l2_target_for_cost(self) -> None:
        """Dokumentiert die Folge des niedrigeren Standards (#1772): mit 0,25/0,5
        liegt der Erwartungswert aktiver Agenten je Runde bei ~37,5 % und damit
        unter dem L2-Ziel von 40 % (das stellt erst 0,4/0,7 wieder her, siehe
        oben), aber weiter ueber der Baseline von ~25 % (Baseline-Test oben).
        Ueber 180 Runden gemittelt, weil der Median einzelner 20-Runden-Laeufe
        um das Ziel streut.
        """
        num_agents = 500
        min_floor, max_floor = enforce_agents_per_hour_floor(
            5, 20, num_agents, min_ratio=AGENTS_PER_HOUR_MIN_RATIO, max_ratio=AGENTS_PER_HOUR_MAX_RATIO
        )
        agent_configs = self._agent_configs(
            num_agents,
            activity_level=enforce_activity_level_floor(0.2),
            active_hours=enforce_active_hours_floor(range(9, 18)),
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
            for hour in self._cycled_hours(180)
        ]
        mean = statistics.fmean(shares)
        assert 0.3 <= mean < 0.4

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
