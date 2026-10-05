"""Issue #1779, Schritt 2.4: Aktivitätsmodell mit belegten Raten und Obergrenze je Aktivierung.

Die Tests belegen Verhalten des Modells, keine Aussage über reales Verhalten:
Agora sagt kein menschliches Verhalten vorher, und ein gleicher Seed erzeugt
nicht denselben Lauf (die Modellantworten bleiben offen).
"""

from __future__ import annotations

import asyncio
import importlib
import math
import random
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.contracts.simulation_activity_contract import (
    ActivityMode,
    ActivityModelConfig,
    ActorClass,
)
from app.services import simulation_activity_model as sam
from app.services.entity_reader import EntityNode
from app.services.simulation_activity_policy import select_active_agent_ids
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.simulation_config_schemas import AgentActivityConfigSchema

_SCRIPTS_DIR = Path(__file__).resolve().parents[2] / "scripts"
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

activation_limit = importlib.import_module("activation_limit")


def _model(mode: ActivityMode = ActivityMode.REALISTIC) -> ActivityModelConfig:
    return sam.build_activity_model(mode)


def _one_agent_per_class() -> List[Dict[str, Any]]:
    return [
        {"agent_id": index, "actor_class": actor_class.value}
        for index, actor_class in enumerate(ActorClass)
    ]


# --- Vertrag -----------------------------------------------------------------------------


class TestContract:
    def test_enum_values(self) -> None:
        assert [mode.value for mode in ActivityMode] == ["realistic", "active"]
        assert [item.value for item in ActorClass] == [
            "individual",
            "politician",
            "authority",
            "organisation",
            "media",
        ]

    def test_condensed_is_not_a_mode(self) -> None:
        with pytest.raises(ValidationError):
            ActivityModelConfig.model_validate({**_model().model_dump(mode="json"), "mode": "condensed"})

    def test_built_model_has_24_weights_summing_to_one(self) -> None:
        model = _model()
        assert len(model.hourly_weights) == 24
        assert abs(sum(model.hourly_weights) - 1.0) <= 1e-6

    @pytest.mark.parametrize("count", [0, 23, 25])
    def test_rejects_wrong_weight_count(self, count: int) -> None:
        payload = _model().model_dump(mode="json")
        payload["hourly_weights"] = [1.0 / count] * count if count else []
        with pytest.raises(ValidationError, match="24"):
            ActivityModelConfig.model_validate(payload)

    def test_rejects_weights_not_summing_to_one(self) -> None:
        payload = _model().model_dump(mode="json")
        payload["hourly_weights"] = [0.05] * 24
        with pytest.raises(ValidationError, match="Summe"):
            ActivityModelConfig.model_validate(payload)

    def test_accepts_sum_within_tolerance(self) -> None:
        payload = _model().model_dump(mode="json")
        payload["hourly_weights"] = [1.0 / 24 + 1e-8] + [1.0 / 24] * 23
        ActivityModelConfig.model_validate(payload)

    def test_forbids_extra_fields(self) -> None:
        payload = {**_model().model_dump(mode="json"), "condensed_hours_per_round": 12}
        with pytest.raises(ValidationError):
            ActivityModelConfig.model_validate(payload)

    def test_schema_version_is_literal_one(self) -> None:
        payload = {**_model().model_dump(mode="json"), "schema_version": 2}
        with pytest.raises(ValidationError):
            ActivityModelConfig.model_validate(payload)

    def test_rates_must_cover_every_actor_class(self) -> None:
        payload = _model().model_dump(mode="json")
        del payload["text_posts_per_day"]["media"]
        with pytest.raises(ValidationError, match="media"):
            ActivityModelConfig.model_validate(payload)

    def test_serialised_model_round_trips(self) -> None:
        dumped = sam.activity_model_dict(ActivityMode.ACTIVE)
        assert ActivityModelConfig.model_validate(dumped) == _model(ActivityMode.ACTIVE)


class TestDefaults:
    def test_realistic_rates(self) -> None:
        rates = _model(ActivityMode.REALISTIC).text_posts_per_day
        assert rates == {
            ActorClass.INDIVIDUAL: 0.5,
            ActorClass.POLITICIAN: 1.0,
            ActorClass.AUTHORITY: 1.0,
            ActorClass.ORGANISATION: 1.0,
            ActorClass.MEDIA: 3.0,
        }

    def test_active_rates(self) -> None:
        rates = _model(ActivityMode.ACTIVE).text_posts_per_day
        assert rates == {
            ActorClass.INDIVIDUAL: 2.0,
            ActorClass.POLITICIAN: 3.0,
            ActorClass.AUTHORITY: 2.5,
            ActorClass.ORGANISATION: 2.5,
            ActorClass.MEDIA: 6.0,
        }

    def test_limits(self) -> None:
        model = _model()
        assert (model.max_text_actions_per_activation, model.max_reactions_per_activation) == (1, 2)

    def test_hourly_profile_is_normalised_from_the_published_percentages(self) -> None:
        assert len(sam.HOURLY_PROFILE_PERCENT) == 24
        total = sum(sam.HOURLY_PROFILE_PERCENT)
        for percent, weight in zip(sam.HOURLY_PROFILE_PERCENT, sam.HOURLY_WEIGHTS):
            assert weight == pytest.approx(percent / total)

    def test_every_rate_table_covers_every_class(self) -> None:
        for table in sam.TEXT_POSTS_PER_DAY_BY_MODE.values():
            assert set(table) == set(ActorClass)


# --- Erwartungswert ----------------------------------------------------------------------


def _activations_per_day(
    mode: ActivityMode, days: int, seed: int = 20260101
) -> Dict[int, float]:
    model = _model(mode)
    agents = _one_agent_per_class()
    rng = random.Random(seed)
    counts: Dict[int, int] = {cfg["agent_id"]: 0 for cfg in agents}
    for _ in range(days):
        for hour in range(24):
            for agent_id in sam.select_active_agent_ids_by_rate(agents, model, hour, rng):
                counts[agent_id] += 1
    return {agent_id: count / days for agent_id, count in counts.items()}


class TestExpectedRate:
    @pytest.mark.parametrize("mode", list(ActivityMode))
    def test_mean_activations_per_day_match_the_class_rate(self, mode: ActivityMode) -> None:
        days = 3000
        measured = _activations_per_day(mode, days)
        rates = sam.TEXT_POSTS_PER_DAY_BY_MODE[mode]
        for cfg in _one_agent_per_class():
            rate = rates[ActorClass(cfg["actor_class"])]
            tolerance = 5 * math.sqrt(rate / days)
            assert measured[cfg["agent_id"]] == pytest.approx(rate, abs=tolerance), cfg

    def test_active_mode_writes_more_than_realistic_for_every_class(self) -> None:
        for actor_class in ActorClass:
            assert (
                sam.TEXT_POSTS_PER_DAY_ACTIVE[actor_class]
                > sam.TEXT_POSTS_PER_DAY_REALISTIC[actor_class]
            )

    def test_one_round_is_one_hour_in_both_modes(self) -> None:
        for mode in ActivityMode:
            model = _model(mode)
            for actor_class in ActorClass:
                total = sum(sam.activation_probability(model, actor_class, hour) for hour in range(24))
                assert total == pytest.approx(model.text_posts_per_day[actor_class])

    @pytest.mark.parametrize("minutes_per_round", [30, 45, 60, 90, 120])
    def test_daily_rate_does_not_depend_on_the_round_length(self, minutes_per_round: int) -> None:
        """Regression: ohne Skalierung verdoppelte eine 30-Minuten-Runde die Tagesrate,
        und ohne Startminute zählten 90-Minuten-Runden Stundenanteile doppelt."""
        rounds_per_day = 24 * 60 // minutes_per_round
        for mode in ActivityMode:
            model = _model(mode)
            for actor_class in ActorClass:
                total = sum(
                    sam.activation_probability(
                        model,
                        actor_class,
                        (round_num * minutes_per_round) // 60,
                        minutes_per_round,
                        sam.round_start_minute(round_num, minutes_per_round),
                    )
                    for round_num in range(rounds_per_day)
                )
                assert total == pytest.approx(model.text_posts_per_day[actor_class])

    def test_ninety_minute_round_starting_at_half_past_covers_the_right_hours(self) -> None:
        weights = list(_model().hourly_weights)
        # Runde 1 bei 90 Minuten: 01:30 bis 03:00.
        assert sam.round_start_minute(1, 90) == 30
        assert sam._round_weight(weights, 1, 90, 30) == pytest.approx(weights[1] / 2 + weights[2])
        # Runde 2: 03:00 bis 04:30.
        assert sam.round_start_minute(2, 90) == 0
        assert sam._round_weight(weights, 3, 90, 0) == pytest.approx(weights[3] + weights[4] / 2)

    @pytest.mark.parametrize("bad", [None, 0, -30, "60", True])
    def test_unusable_round_length_counts_as_one_hour(self, bad: object) -> None:
        model = _model()
        assert sam.activation_probability(
            model, ActorClass.POLITICIAN, 20, bad
        ) == sam.activation_probability(model, ActorClass.POLITICIAN, 20)

    def test_round_selection_reads_the_round_length_from_the_time_config(self) -> None:
        agents = [{"agent_id": i, "actor_class": "media"} for i in range(400)]
        model = _model(ActivityMode.ACTIVE).model_dump(mode="json")

        def count(minutes: int) -> int:
            config = {
                "time_config": {"minutes_per_round": minutes, "activity_model": model},
                "agent_configs": agents,
            }
            return len(
                sam.select_round_agent_ids(
                    config, 12, 3, seed=7, platform="twitter", platforms=["twitter"]
                )
            )

        assert count(30) < count(60) < count(120)

    def test_probability_is_capped_at_one(self) -> None:
        model = _model().model_copy(update={"text_posts_per_day": {item: 100.0 for item in ActorClass}})
        assert sam.activation_probability(model, ActorClass.MEDIA, 21) == 1.0

    def test_evening_is_busier_than_night(self) -> None:
        model = _model()
        assert sam.activation_probability(model, ActorClass.MEDIA, 21) > sam.activation_probability(
            model, ActorClass.MEDIA, 4
        )

    def test_missing_actor_class_counts_as_individual(self) -> None:
        agents = [{"agent_id": 0}, {"agent_id": 1, "actor_class": "wizard"}]
        assert [sam.resolve_agent_actor_class(cfg) for cfg in agents] == [ActorClass.INDIVIDUAL] * 2


# --- Gemeinsame Ziehung -------------------------------------------------------------------


def _agents(count: int = 60) -> List[Dict[str, Any]]:
    classes = list(ActorClass)
    return [{"agent_id": i, "actor_class": classes[i % len(classes)].value} for i in range(count)]


def _platform_draw(platform: str, platforms: List[str], round_num: int, seed: int = 7) -> List[int]:
    model = _model(ActivityMode.ACTIVE)
    return sam.select_active_agent_ids_for_platform(
        model, _agents(), 20, round_num, seed, platform=platform, platforms=platforms
    )


class TestSharedDraw:
    def test_no_agent_is_active_on_both_platforms_in_one_round(self) -> None:
        for round_num in range(200):
            twitter = set(_platform_draw("twitter", ["twitter", "reddit"], round_num))
            reddit = set(_platform_draw("reddit", ["twitter", "reddit"], round_num))
            assert not twitter & reddit, round_num

    def test_both_platforms_together_equal_the_single_draw(self) -> None:
        rng = sam.activity_round_rng(7, 3, "draw")
        expected = sam.select_active_agent_ids_by_rate(_agents(), _model(ActivityMode.ACTIVE), 20, rng)
        twitter = _platform_draw("twitter", ["twitter", "reddit"], 3)
        reddit = _platform_draw("reddit", ["twitter", "reddit"], 3)
        assert sorted(twitter + reddit) == sorted(expected)

    def test_single_platform_gets_all_active_agents(self) -> None:
        rng = sam.activity_round_rng(7, 3, "draw")
        expected = sam.select_active_agent_ids_by_rate(_agents(), _model(ActivityMode.ACTIVE), 20, rng)
        assert _platform_draw("twitter", ["twitter"], 3) == expected
        assert _platform_draw("reddit", ["reddit"], 3) == expected

    def test_split_is_roughly_even(self) -> None:
        twitter = reddit = 0
        for round_num in range(400):
            twitter += len(_platform_draw("twitter", ["twitter", "reddit"], round_num))
            reddit += len(_platform_draw("reddit", ["twitter", "reddit"], round_num))
        assert twitter + reddit > 1000
        assert abs(twitter - reddit) / (twitter + reddit) < 0.08

    def test_draw_is_deterministic_in_seed_and_round_not_in_global_state(self) -> None:
        random.seed(1)
        first = _platform_draw("twitter", ["twitter", "reddit"], 5)
        random.seed(999)
        random.random()
        second = _platform_draw("twitter", ["twitter", "reddit"], 5)
        assert first == second

    def test_draw_differs_between_rounds_and_seeds(self) -> None:
        by_round = {tuple(_platform_draw("twitter", ["twitter"], r)) for r in range(30)}
        assert len(by_round) > 1
        assert _platform_draw("twitter", ["twitter"], 5, seed=1) != _platform_draw(
            "twitter", ["twitter"], 5, seed=2
        ) or _platform_draw("twitter", ["twitter"], 6, seed=1) != _platform_draw(
            "twitter", ["twitter"], 6, seed=2
        )

    def test_unknown_platform_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            _platform_draw("mastodon", ["twitter", "reddit"], 1)

    def test_expected_rate_holds_across_both_platforms(self) -> None:
        model = _model(ActivityMode.ACTIVE)
        agents = [{"agent_id": 0, "actor_class": "politician"}]
        days = 1500
        hits = 0
        for day in range(days):
            for hour in range(24):
                round_num = day * 24 + hour
                for platform in ("twitter", "reddit"):
                    hits += len(
                        sam.select_active_agent_ids_for_platform(
                            model, agents, hour, round_num, 11, platform=platform, platforms=["twitter", "reddit"]
                        )
                    )
        rate = model.text_posts_per_day[ActorClass.POLITICIAN]
        assert hits / days == pytest.approx(rate, abs=5 * math.sqrt(rate / days))

    def test_platform_list_helper(self) -> None:
        assert sam.activity_platforms(True, False) == ["twitter"]
        assert sam.activity_platforms(False, True) == ["reddit"]
        assert sam.activity_platforms(False, False) == ["twitter", "reddit"]


# --- Alter Pfad ---------------------------------------------------------------------------


_OLD_TIME_CONFIG: Dict[str, Any] = {
    "agents_per_hour_min": 5,
    "agents_per_hour_max": 12,
    "peak_hours": [20],
    "off_peak_hours": [3],
}
_OLD_AGENTS = [
    {"agent_id": i, "activity_level": 0.7, "active_hours": list(range(6, 24))} for i in range(30)
]


class TestLegacyConfig:
    def test_without_activity_model_the_old_path_runs_unchanged(self) -> None:
        config = {"time_config": dict(_OLD_TIME_CONFIG), "agent_configs": _OLD_AGENTS}
        for hour in (3, 12, 20):
            expected = select_active_agent_ids(
                _OLD_TIME_CONFIG, _OLD_AGENTS, hour, random.Random(42)
            )
            actual = sam.select_round_agent_ids(
                config, hour, 0, seed=1, platform="twitter", platforms=["twitter", "reddit"], rng=random.Random(42)
            )
            assert actual == expected

    def test_old_path_ignores_platform_and_uses_the_given_rng_state(self) -> None:
        config = {"time_config": dict(_OLD_TIME_CONFIG), "agent_configs": _OLD_AGENTS}
        random.seed(5)
        via_config = sam.select_round_agent_ids_from_config(config, 12, 0, fallback_seed=3)
        random.seed(5)
        expected = select_active_agent_ids(_OLD_TIME_CONFIG, _OLD_AGENTS, 12)
        assert via_config == expected

    def test_with_activity_model_the_rate_path_runs(self) -> None:
        time_config = {**_OLD_TIME_CONFIG, "activity_model": sam.activity_model_dict(ActivityMode.ACTIVE)}
        config = {"time_config": time_config, "agent_configs": _agents()}
        expected = _platform_draw("twitter", ["twitter"], 4, seed=9)
        actual = sam.select_round_agent_ids(
            config, 20, 4, seed=9, platform="twitter", platforms=["twitter"]
        )
        assert actual == expected

    def test_invalid_activity_model_falls_back_to_the_old_path(self) -> None:
        warnings: List[str] = []
        time_config = {**_OLD_TIME_CONFIG, "activity_model": {"mode": "condensed"}}
        with patch.object(sam.logger, "warning", lambda msg, *args: warnings.append(msg % args)):
            assert sam.activity_model_from_time_config(time_config) is None
        assert warnings and "activity_model" in warnings[0]

    def test_runtime_context_selects_platform_and_seed(self) -> None:
        time_config = {"activity_model": sam.activity_model_dict(ActivityMode.ACTIVE)}
        base = {"time_config": time_config, "agent_configs": _agents()}
        base.update(sam.activity_runtime_context(9, ["twitter", "reddit"]))
        twitter = sam.select_round_agent_ids_from_config(
            sam.for_platform(base, "twitter"), 20, 4, fallback_seed=0
        )
        reddit = sam.select_round_agent_ids_from_config(
            sam.for_platform(base, "reddit"), 20, 4, fallback_seed=0
        )
        assert twitter == _platform_draw("twitter", ["twitter", "reddit"], 4, seed=9)
        assert reddit == _platform_draw("reddit", ["twitter", "reddit"], 4, seed=9)

    def test_missing_runtime_context_uses_one_platform_and_the_fallback_seed(self) -> None:
        time_config = {"activity_model": sam.activity_model_dict(ActivityMode.ACTIVE)}
        config = {"time_config": time_config, "agent_configs": _agents()}
        assert sam.select_round_agent_ids_from_config(
            config, 20, 4, fallback_seed=9
        ) == _platform_draw("twitter", ["twitter"], 4, seed=9)


# --- Modus: Aufrufparameter und Einstellung -----------------------------------------------


class TestModeResolution:
    def test_missing_setting_gives_realistic(self) -> None:
        assert sam.resolve_activity_mode(read=lambda key: None) is ActivityMode.REALISTIC

    def test_valid_setting(self) -> None:
        assert sam.resolve_activity_mode(read=lambda key: "active") is ActivityMode.ACTIVE
        assert sam.resolve_activity_mode(read=lambda key: " Realistic ") is ActivityMode.REALISTIC

    def test_setting_key_is_the_documented_one(self) -> None:
        keys: List[str] = []
        sam.resolve_activity_mode(read=lambda key: keys.append(key))
        assert keys == ["AGORA_SIM_ACTIVITY_MODE"]

    @pytest.mark.parametrize("raw", ["condensed", "fast", 5, "", True])
    def test_invalid_setting_falls_back_with_warning(self, raw: Any) -> None:
        warnings: List[str] = []
        with patch.object(sam.logger, "warning", lambda msg, *args: warnings.append(msg % args)):
            mode = sam.resolve_activity_mode(read=lambda key: raw)
        assert mode is ActivityMode.REALISTIC
        assert bool(warnings) == (raw != "")

    def test_request_wins_over_setting(self) -> None:
        assert sam.resolve_activity_mode("active", read=lambda key: "realistic") is ActivityMode.ACTIVE
        assert sam.resolve_activity_mode(ActivityMode.REALISTIC, read=lambda key: "active") is ActivityMode.REALISTIC

    def test_invalid_request_falls_back_to_the_setting(self) -> None:
        warnings: List[str] = []
        with patch.object(sam.logger, "warning", lambda msg, *args: warnings.append(msg % args)):
            mode = sam.resolve_activity_mode("condensed", read=lambda key: "active")
        assert mode is ActivityMode.ACTIVE
        assert warnings

    def test_setting_is_registered_in_the_settings_schema(self) -> None:
        from app.services.settings_schema import field_by_key

        spec = field_by_key("AGORA_SIM_ACTIVITY_MODE")
        assert spec is not None
        assert spec.default == "realistic"
        assert spec.enum_values == ("realistic", "active")

    def test_time_config_carries_the_model_of_the_requested_mode(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("AGORA_SIM_ACTIVITY_MODE", raising=False)
        monkeypatch.delenv("AGORA_SIM_MAX_HOURS", raising=False)
        with patch("app.services.simulation_config_generator.LLMClient"):
            generator = SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434/v1")
        default = generator._parse_time_config({}, 30)
        active = generator._parse_time_config({}, 30, "active")
        assert default.activity_model is not None
        assert default.activity_model["mode"] == "realistic"
        assert active.activity_model is not None and active.activity_model["mode"] == "active"
        assert active.activity_model["text_posts_per_day"]["media"] == 6.0
        # Alte Felder bleiben im Artefakt (Rückwärtskompatibilität).
        assert default.agents_per_hour_min >= 1 and default.peak_hours

    def test_env_setting_reaches_the_time_config(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("AGORA_SIM_ACTIVITY_MODE", "active")
        with patch("app.services.simulation_config_generator.LLMClient"):
            generator = SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434/v1")
        parsed = generator._parse_time_config({}, 30)
        assert parsed.activity_model is not None and parsed.activity_model["mode"] == "active"


# --- Akteursklasse ------------------------------------------------------------------------


def _entity(entity_type: str, name: str = "Eintrag") -> EntityNode:
    return EntityNode(
        uuid=f"uuid-{name}",
        name=name,
        labels=["Entity", entity_type],
        summary="Kurzbeschreibung",
        attributes={},
    )


@pytest.fixture
def generator() -> Any:
    with patch("app.services.simulation_config_generator.LLMClient"):
        return SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434/v1")


class TestActorClass:
    @pytest.mark.parametrize("raw", ["politician", " Media ", ActorClass.AUTHORITY])
    def test_coerce_accepts_enum_values(self, raw: Any) -> None:
        assert sam.coerce_actor_class(raw) is ActorClass(raw.value if isinstance(raw, ActorClass) else raw.strip().lower())

    @pytest.mark.parametrize("raw", [None, "", "wizard", 3, ["media"]])
    def test_coerce_rejects_everything_else(self, raw: Any) -> None:
        assert sam.coerce_actor_class(raw) is None

    def test_schema_normalises_invalid_to_none_without_failing_the_answer(self) -> None:
        assert AgentActivityConfigSchema.model_validate({"agent_id": 1, "actor_class": "wizard"}).actor_class is None
        assert AgentActivityConfigSchema.model_validate({"agent_id": 1}).actor_class is None
        assert (
            AgentActivityConfigSchema.model_validate({"agent_id": 1, "actor_class": "Media"}).actor_class
            is ActorClass.MEDIA
        )

    def test_fallback_uses_the_collective_distinction(self) -> None:
        assert sam.fallback_actor_class("EmployeeGroup") is ActorClass.ORGANISATION
        assert sam.fallback_actor_class("HospitalNetwork") is ActorClass.ORGANISATION
        assert sam.fallback_actor_class("Person") is ActorClass.INDIVIDUAL
        assert sam.fallback_actor_class(None) is ActorClass.INDIVIDUAL

    def _generate(self, generator: Any, entities: List[EntityNode], answers: List[Dict[str, Any]]) -> list:
        base = {"activity_level": 0.7, "posts_per_hour": 0.5, "comments_per_hour": 1.0, "stance": "neutral"}
        generator._call_llm_with_retry = lambda prompt, system, schema: {
            "agent_configs": [{**base, **answer, "agent_id": index} for index, answer in enumerate(answers)]
        }
        return generator._generate_agent_configs_batch(
            context="", entities=entities, start_idx=0, simulation_requirement="Anforderung"
        )

    def test_valid_class_from_the_assistant_is_kept_and_invalid_falls_back_with_log(
        self, generator: Any
    ) -> None:
        entities = [
            _entity("Person", "a"),
            _entity("Person", "b"),
            _entity("EmployeeGroup", "c"),
            _entity("EmployeeGroup", "d"),
        ]
        infos: List[str] = []
        from app.services import simulation_config_agents as agents_module

        with patch.object(agents_module.logger, "info", lambda msg, *args: infos.append(msg % args)):
            configs = self._generate(
                generator,
                entities,
                [{"actor_class": "media"}, {"actor_class": "wizard"}, {}, {"actor_class": "individual"}],
            )
        assert [cfg.actor_class for cfg in configs] == ["media", "individual", "organisation", "individual"]
        fallback_logs = [line for line in infos if "actor_class" in line]
        assert len(fallback_logs) == 2
        assert "agent_id=1" in fallback_logs[0] and "agent_id=2" in fallback_logs[1]

    def test_rule_based_fallback_without_any_assistant_answer(self, generator: Any) -> None:
        generator._call_llm_with_retry = lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("down"))
        configs = generator._generate_agent_configs_batch(
            context="",
            entities=[_entity("Person"), _entity("Association Group")],
            start_idx=0,
            simulation_requirement="Anforderung",
        )
        assert [cfg.actor_class for cfg in configs] == ["individual", "organisation"]

    def test_actor_class_lands_in_the_serialised_artefact(self, generator: Any) -> None:
        from dataclasses import asdict

        configs = self._generate(generator, [_entity("Person")], [{"actor_class": "politician"}])
        assert asdict(configs[0])["actor_class"] == "politician"
        # Altfelder unverändert im Artefakt.
        assert {"activity_level", "posts_per_hour", "comments_per_hour", "active_hours"} <= set(asdict(configs[0]))

    def test_prompt_defines_the_five_classes_and_leaves_rates_to_the_system(self, generator: Any) -> None:
        prompts: List[str] = []

        def capture(prompt: str, system: str, schema: Any) -> Dict[str, Any]:
            prompts.append(prompt)
            return {"agent_configs": []}

        generator._call_llm_with_retry = capture
        generator._generate_agent_configs_batch(
            context="", entities=[_entity("Person")], start_idx=0, simulation_requirement="x"
        )
        assert prompts
        for name in ("individual", "politician", "authority", "organisation", "media"):
            assert name in prompts[0]
        assert "never by you" in prompts[0]


# --- Obergrenze je Aktivierung ------------------------------------------------------------


class _Recorder:
    """Ersetzt ``SocialAction.perform_action``: zählt tatsächlich ausgeführte Aktionen."""

    def __init__(self) -> None:
        self.executed: List[str] = []

    async def __call__(self, message: Any, type: str) -> Dict[str, Any]:  # noqa: A002 — OASIS-Signatur
        self.executed.append(type)
        return {"success": True}


def _real_social_agent(agent_id: int = 0) -> tuple[Any, _Recorder]:
    """Agent-Attrappe mit den echten OASIS-Aktions-Tools (``SocialAction``) als CAMEL-``FunctionTool``."""
    from oasis.social_platform.channel import Channel
    from oasis.social_agent.agent_action import SocialAction

    action = SocialAction(agent_id, Channel())
    recorder = _Recorder()
    action.perform_action = recorder  # type: ignore[method-assign]
    tools = {tool.get_function_name(): tool for tool in action.get_openai_function_list()}
    return SimpleNamespace(tool_dict=tools, action=action), recorder


def _graph(*agents: Any) -> Any:
    return SimpleNamespace(get_agents=lambda: list(enumerate(agents)))


_TEXT_CALLS = [
    ("create_post", {"content": "a"}),
    ("create_post", {"content": "b"}),
    ("create_comment", {"post_id": 1, "content": "c"}),
    ("quote_post", {"post_id": 1, "quote_content": "d"}),
    ("create_post", {"content": "e"}),
]
_REACTION_CALLS = [
    ("like_post", {"post_id": 1}),
    ("repost", {"post_id": 1}),
    ("dislike_post", {"post_id": 2}),
    ("follow", {"followee_id": 3}),
]
_READING_CALLS = [
    ("search_posts", {"query": "x"}),
    ("search_user", {"query": "y"}),
    ("trend", {}),
    ("refresh", {}),
    ("do_nothing", {}),
]


def _activate(agent: Any, calls: List[tuple[str, Dict[str, Any]]]) -> List[Any]:
    """Führt Tool-Calls wie CAMELs ``_aexecute_tool`` aus (``tool.async_call``)."""

    async def run() -> List[Any]:
        return [await agent.tool_dict[name].async_call(**args) for name, args in calls]

    return asyncio.run(run())


class TestActivationLimit:
    def test_five_text_and_four_reaction_calls_execute_one_text_and_two_reactions(self) -> None:
        agent, recorder = _real_social_agent()
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        assert limits is not None
        limits.begin_round()
        results = _activate(agent, _TEXT_CALLS + _REACTION_CALLS)
        text = [t for t in recorder.executed if t in {"create_post", "create_comment", "quote_post"}]
        reactions = [t for t in recorder.executed if t in {"like_post", "repost", "dislike_post", "follow"}]
        assert len(text) == 1 and len(reactions) == 2
        assert recorder.executed == ["create_post", "like_post", "repost"]
        refused = [r for r in results if isinstance(r, dict) and r.get("success") is False]
        assert len(refused) == 4 + 2
        assert all("limit reached" in r["error"] for r in refused)
        assert "not executed" in refused[0]["error"]

    def test_counter_is_free_again_after_reset(self) -> None:
        agent, recorder = _real_social_agent()
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        assert limits is not None
        limits.begin_round()
        _activate(agent, _TEXT_CALLS)
        limits.end_round(1)
        limits.begin_round()
        _activate(agent, _TEXT_CALLS)
        assert recorder.executed.count("create_post") == 2
        assert len(recorder.executed) == 2

    def test_reading_actions_are_unlimited(self) -> None:
        agent, recorder = _real_social_agent()
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        assert limits is not None
        limits.begin_round()
        results = _activate(agent, _READING_CALLS * 4)
        assert len(recorder.executed) == len(_READING_CALLS) * 4
        assert not any(isinstance(r, dict) and r.get("success") is False for r in results)

    def test_text_and_reaction_budgets_are_independent(self) -> None:
        agent, recorder = _real_social_agent()
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        assert limits is not None
        limits.begin_round()
        _activate(agent, _REACTION_CALLS + _TEXT_CALLS[:1])
        assert recorder.executed == ["like_post", "repost", "create_post"]

    def test_outside_a_round_nothing_is_limited(self) -> None:
        agent, recorder = _real_social_agent()
        activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        _activate(agent, _TEXT_CALLS)
        assert len(recorder.executed) == len(_TEXT_CALLS)

    def test_each_agent_has_its_own_counter(self) -> None:
        first, first_recorder = _real_social_agent(0)
        second, second_recorder = _real_social_agent(1)
        limits = activation_limit.install_activation_limits(
            _graph(first, second), _model(), log=lambda line: None
        )
        assert limits is not None
        limits.begin_round()
        _activate(first, _TEXT_CALLS)
        _activate(second, _TEXT_CALLS)
        assert len(first_recorder.executed) == len(second_recorder.executed) == 1

    def test_wrapper_keeps_name_signature_schema_and_async_kind(self) -> None:
        agent, _ = _real_social_agent()
        before = {name: tool.get_openai_tool_schema() for name, tool in agent.tool_dict.items()}
        activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        for name in ("create_post", "like_post", "repost", "follow"):
            tool = agent.tool_dict[name]
            assert tool.func.__name__ == name
            assert tool.is_async
            assert tool.get_openai_tool_schema() == before[name]
        assert agent.tool_dict["do_nothing"].func.__name__ == "do_nothing"
        assert not getattr(agent.tool_dict["do_nothing"].func, "_agora_activation_limited", False)

    def test_install_is_idempotent(self) -> None:
        agent, recorder = _real_social_agent()
        graph = _graph(agent)
        limits = activation_limit.install_activation_limits(graph, _model(), log=lambda line: None)
        again = activation_limit.install_activation_limits(graph, _model(), log=lambda line: None)
        assert limits is not None and again is not None
        again.begin_round()
        _activate(agent, _TEXT_CALLS)
        assert len(recorder.executed) == 1

    def test_no_model_means_no_limits(self) -> None:
        agent, recorder = _real_social_agent()
        assert activation_limit.install_activation_limits(_graph(agent), None) is None
        _activate(agent, _TEXT_CALLS)
        assert len(recorder.executed) == len(_TEXT_CALLS)

    def test_limit_values_come_from_the_model(self) -> None:
        agent, recorder = _real_social_agent()
        model = _model().model_copy(
            update={"max_text_actions_per_activation": 3, "max_reactions_per_activation": 0}
        )
        limits = activation_limit.install_activation_limits(_graph(agent), model, log=lambda line: None)
        assert limits is not None
        limits.begin_round()
        _activate(agent, _TEXT_CALLS + _REACTION_CALLS)
        assert len(recorder.executed) == 3

    def test_round_summary_is_logged_as_one_structured_line(self) -> None:
        agent, _ = _real_social_agent()
        lines: List[str] = []
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lines.append)
        assert limits is not None
        with activation_limit.round_activation_limits(limits, 7):
            _activate(agent, _TEXT_CALLS + _REACTION_CALLS)
        last = lines[-1]
        assert last == (
            "[activation-limit] round=7 agents=1 blocked_agents=1 blocked_text=4 blocked_reactions=2"
        )

    def test_round_context_manager_disarms_even_on_error(self) -> None:
        agent, recorder = _real_social_agent()
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        with pytest.raises(RuntimeError):
            with activation_limit.round_activation_limits(limits, 1):
                raise RuntimeError("env.step failed")
        _activate(agent, _TEXT_CALLS)
        assert len(recorder.executed) == len(_TEXT_CALLS)

    def test_context_manager_without_limits_is_a_no_op(self) -> None:
        with activation_limit.round_activation_limits(None, 1):
            pass

    def test_agent_without_action_tools_is_reported(self) -> None:
        lines: List[str] = []
        bare = SimpleNamespace(tool_dict={})
        activation_limit.install_activation_limits(_graph(bare), _model(), log=lines.append)
        assert "WITHOUT enforcement" in lines[-1]

    def test_config_helper_reads_the_model_from_time_config(self) -> None:
        agent, recorder = _real_social_agent()
        config = {"time_config": {"activity_model": sam.activity_model_dict(ActivityMode.REALISTIC)}}
        limits = activation_limit.install_activation_limits_from_config(
            _graph(agent), config, log=lambda line: None
        )
        assert limits is not None
        assert activation_limit.install_activation_limits_from_config(_graph(agent), {}) is None

    def test_works_through_the_camel_execution_path(self) -> None:
        """CAMELs ``ChatAgent._aexecute_tool`` ruft den Umschlag wie die echte Aktion."""
        from camel.agents import ChatAgent
        from camel.agents._types import ToolCallRequest

        agent, recorder = _real_social_agent()
        limits = activation_limit.install_activation_limits(_graph(agent), _model(), log=lambda line: None)
        assert limits is not None
        stub = SimpleNamespace(
            _internal_tools=agent.tool_dict,
            _record_tool_calling=lambda name, args, result, call_id, mask_output=False: result,
        )

        async def run() -> List[Any]:
            out = []
            for index, (name, args) in enumerate(_TEXT_CALLS):
                request = ToolCallRequest(tool_name=name, args=args, tool_call_id=f"call-{index}")
                out.append(await ChatAgent._aexecute_tool(stub, request))  # type: ignore[arg-type]
            return out

        limits.begin_round()
        results = asyncio.run(run())
        assert recorder.executed == ["create_post"]
        assert sum(1 for r in results if isinstance(r, dict) and r.get("success") is False) == 4


# --- Satz im Agenten-Prompt ---------------------------------------------------------------


class TestPromptSentence:
    def test_sentence_names_both_limits(self) -> None:
        sentence = sam.describe_activity_limits(_model())
        assert "höchstens einen Beitrag" in sentence
        assert "höchstens 2 Reaktionen" in sentence
        assert "nicht ausgeführt" in sentence

    def test_no_sentence_without_a_model(self) -> None:
        assert sam.describe_activity_limits(None) == ""
        assert sam.activity_limits_sentence({"time_config": {}}) == ""

    def test_sentence_from_config(self) -> None:
        config = {"time_config": {"activity_model": sam.activity_model_dict(ActivityMode.ACTIVE)}}
        assert sam.activity_limits_sentence(config) == sam.describe_activity_limits(_model(ActivityMode.ACTIVE))

    def test_profile_text_carries_the_sentence_only_with_a_model(self, tmp_path: Path) -> None:
        import json

        agent_tools = importlib.import_module("agent_tools")
        profile = tmp_path / "reddit_profiles.json"
        profile.write_text(
            json.dumps([{"persona": "Basis", "profession": "Pflegerin", "source_entity_type": "Person"}]),
            encoding="utf-8",
        )
        configs = [{"agent_id": 0, "stance": "neutral", "entity_type": "Person"}]
        sentence = sam.describe_activity_limits(_model())
        with_limits = agent_tools.augment_profile_with_stance(
            str(profile), configs, platform="reddit", activity_limits=sentence
        )
        assert sentence in json.loads(Path(with_limits).read_text(encoding="utf-8"))[0]["persona"]
        without = agent_tools.augment_profile_with_stance(str(profile), configs, platform="reddit")
        assert sentence not in json.loads(Path(without).read_text(encoding="utf-8"))[0]["persona"]

    def test_prompt_note_reaches_system_message_and_memory(self) -> None:
        notes: List[str] = []
        message = SimpleNamespace(content="System")
        original = SimpleNamespace(content="System")
        agent = SimpleNamespace(
            system_message=message,
            _original_system_message=original,
            init_messages=lambda: notes.append("init"),
        )
        config = {"time_config": {"activity_model": sam.activity_model_dict(ActivityMode.REALISTIC)}}
        count = activation_limit.append_activity_limits_to_prompts(_graph(agent), config, log=lambda line: None)
        assert count == 1 and notes == ["init"]
        assert sam.describe_activity_limits(_model()) in message.content
        assert message.content == original.content
        # Zweiter Aufruf hängt nichts doppelt an.
        activation_limit.append_activity_limits_to_prompts(_graph(agent), config, log=lambda line: None)
        assert message.content.count("Deine Aktivität") == 1

    def test_no_prompt_note_without_a_model(self) -> None:
        agent = SimpleNamespace(system_message=SimpleNamespace(content="System"))
        assert activation_limit.append_activity_limits_to_prompts(_graph(agent), {}) == 0
        assert agent.system_message.content == "System"


# --- API: Moduswahl je Simulation ---------------------------------------------------------


@pytest.fixture
def app_ctx() -> Any:
    """``json_error`` baut echte Flask-Responses."""
    from flask import Flask

    with Flask(__name__).test_request_context() as ctx:
        yield ctx


class TestPrepareRequestActivityMode:
    def test_request_contract_accepts_both_modes_and_defaults_to_none(self) -> None:
        from app.api.simulation_prepare_contracts import PrepareRequest

        assert PrepareRequest(simulation_id="sim_0123456789ab").activity_mode is None
        assert (
            PrepareRequest(simulation_id="sim_0123456789ab", activity_mode="active").activity_mode
            is ActivityMode.ACTIVE
        )
        with pytest.raises(ValidationError):
            PrepareRequest(simulation_id="sim_0123456789ab", activity_mode="condensed")

    @pytest.mark.parametrize("payload", [{}, {"activity_mode": None}, {"activity_mode": "  "}])
    def test_body_without_a_mode_means_no_choice(self, payload: Dict[str, Any]) -> None:
        from app.api.simulation_prepare_contracts import _parse_prepare_activity_mode

        assert _parse_prepare_activity_mode(payload) is None

    def test_body_with_a_mode(self) -> None:
        from app.api.simulation_prepare_contracts import _parse_prepare_activity_mode

        assert _parse_prepare_activity_mode({"activity_mode": "Active"}) is ActivityMode.ACTIVE

    @pytest.mark.parametrize("value", ["condensed", 3, ["active"], True])
    def test_body_with_an_unknown_mode_is_rejected(self, value: Any, app_ctx: Any) -> None:
        from app.api.simulation_prepare_contracts import PrepareRejected, _parse_prepare_activity_mode

        with pytest.raises(PrepareRejected):
            _parse_prepare_activity_mode({"activity_mode": value})

    def test_restart_reads_the_mode_from_the_run_or_the_stored_config(self) -> None:
        from app.api.runs import _restart_activity_mode

        stored = {"time_config": {"activity_model": {"mode": "active"}}}
        assert _restart_activity_mode({"metadata": {"activity_mode": "realistic"}}, stored) == "realistic"
        assert _restart_activity_mode({"metadata": {}}, stored) == "active"
        assert _restart_activity_mode({}, {}) is None
