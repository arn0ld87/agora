"""Issue #1772: Der Konfigurations-Assistent schlaegt standardmaessig 1 Tag / 24 Runden vor.

Die Laufgroesse (``total_simulation_hours`` x ``minutes_per_round``) ist der
Hebel auf den Tokenverbrauch. Der Prompt nennt 24 Stunden als Standard, und
``_parse_time_config`` klemmt jede LLM-Antwort danach deterministisch auf die
konfigurierte Obergrenze (``AGORA_SIM_MAX_HOURS``, Standard 24).
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import patch

import pytest

from app.services.settings_schema import field_by_key
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.simulation_config_models import (
    DEFAULT_MINUTES_PER_ROUND,
    DEFAULT_TOTAL_SIMULATION_HOURS,
    TimeSimulationConfig,
)
from app.services.simulation_config_schemas import get_time_config_schema
from app.services.simulation_config_time import (
    ENV_MAX_SIMULATION_HOURS,
    resolve_max_simulation_hours,
)

NUM_ENTITIES = 30


@pytest.fixture
def generator(monkeypatch: pytest.MonkeyPatch) -> Any:
    monkeypatch.delenv(ENV_MAX_SIMULATION_HOURS, raising=False)
    with patch("app.services.simulation_config_generator.LLMClient"):
        return SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434/v1")


def _llm_result(hours: Any, minutes: Any = 60, reasoning: str = "LLM-Begruendung") -> dict[str, Any]:
    return {
        "total_simulation_hours": hours,
        "minutes_per_round": minutes,
        "agents_per_hour_min": 8,
        "agents_per_hour_max": 15,
        "peak_hours": [18, 19, 20, 21, 22],
        "off_peak_hours": [0, 1, 2, 3, 4, 5],
        "morning_hours": [6, 7, 8],
        "work_hours": [9, 10, 11, 12, 13, 14, 15, 16],
        "reasoning": reasoning,
    }


class _LogCollector(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _collect(logger_name: str) -> tuple[logging.Logger, _LogCollector]:
    target = logging.getLogger(logger_name)
    handler = _LogCollector()
    target.addHandler(handler)
    return target, handler


class TestDefaults:
    def test_model_default_is_one_day_with_24_rounds(self) -> None:
        cfg = TimeSimulationConfig()
        assert (cfg.total_simulation_hours, cfg.minutes_per_round) == (24, 60)
        assert (DEFAULT_TOTAL_SIMULATION_HOURS, DEFAULT_MINUTES_PER_ROUND) == (24, 60)

    def test_rule_based_fallback_is_24_hours_60_minutes(self, generator: Any) -> None:
        fallback = generator._get_default_time_config(NUM_ENTITIES)
        assert (fallback["total_simulation_hours"], fallback["minutes_per_round"]) == (24, 60)
        parsed = generator._parse_time_config(fallback, NUM_ENTITIES)
        assert (parsed.total_simulation_hours, parsed.minutes_per_round) == (24, 60)
        assert "Hinweis" not in fallback["reasoning"]

    def test_missing_fields_in_llm_result_use_the_default(self, generator: Any) -> None:
        parsed = generator._parse_time_config({}, NUM_ENTITIES)
        assert (parsed.total_simulation_hours, parsed.minutes_per_round) == (24, 60)

    def test_llm_response_schema_defaults_to_24_hours_and_allows_shorter_runs(self) -> None:
        schema = get_time_config_schema(NUM_ENTITIES)
        assert schema().total_simulation_hours == 24
        assert schema(total_simulation_hours=12).total_simulation_hours == 12

    def test_settings_schema_default_matches_the_constant(self) -> None:
        spec = field_by_key(ENV_MAX_SIMULATION_HOURS)
        assert spec is not None
        assert spec.default == DEFAULT_TOTAL_SIMULATION_HOURS
        assert spec.section == "oasis"


class TestClamp:
    def test_96_hours_without_user_signal_is_clamped_to_24_with_log_and_note(
        self, generator: Any
    ) -> None:
        target, handler = _collect("agora.simulation_config")
        result = _llm_result(96)
        try:
            parsed = generator._parse_time_config(result, NUM_ENTITIES)
        finally:
            target.removeHandler(handler)

        assert parsed.total_simulation_hours == 24
        assert parsed.minutes_per_round == 60
        # Sichtbarer Hinweis im transportierten Begruendungstext.
        assert result["reasoning"].startswith("LLM-Begruendung")
        assert "96" in result["reasoning"] and "24" in result["reasoning"]
        assert ENV_MAX_SIMULATION_HOURS in result["reasoning"]
        # Strukturierter Log-Eintrag.
        messages = [r.getMessage() for r in handler.records if r.levelno == logging.WARNING]
        assert any("96" in m and "24" in m and "total_simulation_hours" in m for m in messages)

    def test_12_hours_stays_12_without_note_or_log(self, generator: Any) -> None:
        target, handler = _collect("agora.simulation_config")
        result = _llm_result(12)
        try:
            parsed = generator._parse_time_config(result, NUM_ENTITIES)
        finally:
            target.removeHandler(handler)
        assert parsed.total_simulation_hours == 12
        assert result["reasoning"] == "LLM-Begruendung"
        assert not [r for r in handler.records if "total_simulation_hours" in r.getMessage()]

    def test_exactly_the_cap_is_not_clamped(self, generator: Any) -> None:
        result = _llm_result(24)
        parsed = generator._parse_time_config(result, NUM_ENTITIES)
        assert parsed.total_simulation_hours == 24
        assert result["reasoning"] == "LLM-Begruendung"

    def test_note_is_added_even_if_the_llm_gave_no_reasoning(self, generator: Any) -> None:
        result = _llm_result(96)
        del result["reasoning"]
        generator._parse_time_config(result, NUM_ENTITIES)
        assert "96" in result["reasoning"]

    def test_short_rounds_that_exceed_the_round_cap_are_lifted_to_60_minutes(
        self, generator: Any
    ) -> None:
        # 24 h bei 30 Minuten je Runde waeren 48 Runden -- doppelte Kosten.
        result = _llm_result(24, minutes=30)
        parsed = generator._parse_time_config(result, NUM_ENTITIES)
        assert (parsed.total_simulation_hours, parsed.minutes_per_round) == (24, 60)
        assert "minutes_per_round" in result["reasoning"]

    def test_short_run_with_short_rounds_stays_untouched(self, generator: Any) -> None:
        # 12 h bei 30 Minuten = 24 Runden: innerhalb des Standards.
        result = _llm_result(12, minutes=30)
        parsed = generator._parse_time_config(result, NUM_ENTITIES)
        assert (parsed.total_simulation_hours, parsed.minutes_per_round) == (12, 30)
        assert result["reasoning"] == "LLM-Begruendung"

    def test_longer_rounds_are_kept(self, generator: Any) -> None:
        parsed = generator._parse_time_config(_llm_result(24, minutes=120), NUM_ENTITIES)
        assert (parsed.total_simulation_hours, parsed.minutes_per_round) == (24, 120)

    def test_clamp_applies_on_top_of_dict_style_llm_values(self, generator: Any) -> None:
        parsed = generator._parse_time_config(
            _llm_result({"value": 96, "reasoning": "vier Tage"}), NUM_ENTITIES
        )
        assert parsed.total_simulation_hours == 24

    def test_clamp_does_not_touch_the_activity_floor(self, generator: Any) -> None:
        parsed = generator._parse_time_config(_llm_result(96), 52)
        # #1772 Aktivitaetsquote (0,25/0,5) bleibt unveraendert wirksam.
        assert (parsed.agents_per_hour_min, parsed.agents_per_hour_max) == (13, 26)


class TestConfiguredCap:
    def test_configured_value_is_the_cap(
        self, generator: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_MAX_SIMULATION_HOURS, "48")
        over = generator._parse_time_config(_llm_result(96), NUM_ENTITIES)
        within = generator._parse_time_config(_llm_result(36), NUM_ENTITIES)
        assert over.total_simulation_hours == 48
        assert within.total_simulation_hours == 36
        # Der Standardvorschlag bleibt 24 -- die Obergrenze hebt nur das Limit.
        assert generator._get_default_time_config(NUM_ENTITIES)["total_simulation_hours"] == 24

    def test_round_cap_follows_the_configured_cap(
        self, generator: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_MAX_SIMULATION_HOURS, "48")
        kept = generator._parse_time_config(_llm_result(24, minutes=30), NUM_ENTITIES)
        lifted = generator._parse_time_config(_llm_result(48, minutes=30), NUM_ENTITIES)
        assert (kept.total_simulation_hours, kept.minutes_per_round) == (24, 30)  # 48 Runden
        assert (lifted.total_simulation_hours, lifted.minutes_per_round) == (48, 60)

    def test_default_without_configuration(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv(ENV_MAX_SIMULATION_HOURS, raising=False)
        assert resolve_max_simulation_hours() == 24

    @pytest.mark.parametrize(
        "raw, expected",
        [(48, 48), ("72", 72), (168, 168), (1, 1), (48.0, 48), (None, 24)],
    )
    def test_valid_values(self, raw: Any, expected: int) -> None:
        assert resolve_max_simulation_hours({ENV_MAX_SIMULATION_HOURS: raw}.get) == expected

    @pytest.mark.parametrize("raw", [0, -5, 169, 100000, "abc", "", 12.5, True, float("nan"), [48]])
    def test_invalid_values_fall_back_to_24_and_log(self, raw: Any) -> None:
        target, handler = _collect("agora.simulation_config")
        try:
            value = resolve_max_simulation_hours({ENV_MAX_SIMULATION_HOURS: raw}.get)
        finally:
            target.removeHandler(handler)
        assert value == 24
        assert any(
            r.levelno == logging.WARNING and ENV_MAX_SIMULATION_HOURS in r.getMessage()
            for r in handler.records
        )

    def test_env_value_is_read_through_the_settings_layer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_MAX_SIMULATION_HOURS, "72")
        assert resolve_max_simulation_hours() == 72


class TestPrompt:
    def _prompt(self, generator: Any) -> str:
        captured: dict[str, str] = {}

        def fake_call(prompt: str, system_prompt: str, schema: Any) -> dict[str, Any]:  # noqa: ARG001
            captured["prompt"] = prompt
            return _llm_result(24)

        with patch.object(generator, "_call_llm_with_retry", side_effect=fake_call):
            generator._generate_time_config("Kontext", NUM_ENTITIES)
        return captured["prompt"]

    def test_prompt_names_24_hours_as_default_and_demands_an_explicit_wish(
        self, generator: Any
    ) -> None:
        prompt = self._prompt(generator)
        assert '"total_simulation_hours": 24,' in prompt
        assert '"total_simulation_hours": 72' not in prompt
        assert "24-168" not in prompt
        assert "Default and recommendation: 24" in prompt
        assert "explicitly" in prompt and "longer" in prompt
        assert "Hard limit of 24 hours" in prompt

    def test_prompt_limit_follows_the_configured_cap(
        self, generator: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv(ENV_MAX_SIMULATION_HOURS, "48")
        prompt = self._prompt(generator)
        assert "Hard limit of 48 hours" in prompt
        assert "Default and recommendation: 24" in prompt
