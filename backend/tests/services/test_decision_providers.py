"""Tests für die DecisionProvider-Referenzadapter (f005, Slice `decision-pilot`,
Task `provider-port`): RuleProvider, FakeProvider, LLMProvider.

Jeder Adapter wird gegen den ``DecisionProvider``-Port geprüft (isinstance-
Check via ``runtime_checkable``), damit ein künftiger Jev-Adapter denselben
Vertrag erfüllen muss, ohne dass diese Tests ihn kennen müssen.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.contracts.decision_contract import (
    ChoiceQuestion,
    DecisionResult,
    DecisionState,
    NoulQuestion,
    ScoreQuestion,
)
from app.repositories.decision_provider import DecisionProvider
from app.services.decisions.fake_provider import FakeProvider, FakeProviderExhaustedError
from app.services.decisions.llm_provider import DecisionLLMResponseError, LLMProvider
from app.services.decisions.rule_provider import (
    RuleNotConfiguredError,
    RuleOutcome,
    RuleProvider,
)

_STATE = DecisionState(use_case_id="persona-eligibility", state="Bundeskanzleramt", context_hash="h1")


class TestRuleProvider:
    def test_satisfies_the_decision_provider_protocol(self) -> None:
        provider = RuleProvider(use_case_id="u", rule_fn=lambda s, q: RuleOutcome(answer="x", confidence=1.0))
        assert isinstance(provider, DecisionProvider)

    def test_wraps_the_rule_functions_outcome(self) -> None:
        def rule_fn(state: DecisionState, question) -> RuleOutcome:
            assert state is _STATE
            return RuleOutcome(answer="ineligible", confidence=1.0)

        provider = RuleProvider(use_case_id="persona-eligibility", rule_fn=rule_fn)
        result = provider.decide(_STATE, NoulQuestion())

        assert isinstance(result, DecisionResult)
        assert result.provider == "rule"
        assert result.answer == "ineligible"
        assert result.cost_micros == 0
        assert result.shadow is False

    def test_raises_when_not_configured(self) -> None:
        provider = RuleProvider(use_case_id="u", rule_fn=None)
        with pytest.raises(RuleNotConfiguredError):
            provider.decide(_STATE, NoulQuestion())


class TestFakeProvider:
    def test_satisfies_the_decision_provider_protocol(self) -> None:
        assert isinstance(FakeProvider([]), DecisionProvider)

    def test_returns_programmed_responses_in_order(self) -> None:
        first = DecisionResult(
            use_case_id="u", provider="fake", answer="a", confidence=0.9,
            cost_micros=0, latency_ms=0, shadow=False,
        )
        second = DecisionResult(
            use_case_id="u", provider="fake", answer="b", confidence=0.5,
            cost_micros=0, latency_ms=0, shadow=False,
        )
        provider = FakeProvider([first, second])

        assert provider.decide(_STATE, NoulQuestion()) is first
        assert provider.decide(_STATE, NoulQuestion()) is second
        assert len(provider.calls) == 2

    def test_raises_a_programmed_exception(self) -> None:
        provider = FakeProvider([TimeoutError("simulated")])
        with pytest.raises(TimeoutError):
            provider.decide(_STATE, NoulQuestion())

    def test_raises_when_exhausted(self) -> None:
        provider = FakeProvider([])
        with pytest.raises(FakeProviderExhaustedError):
            provider.decide(_STATE, NoulQuestion())


class TestLLMProvider:
    def test_satisfies_the_decision_provider_protocol(self) -> None:
        client = MagicMock(spec=["chat_json", "model"])
        assert isinstance(LLMProvider(client), DecisionProvider)

    def test_choice_question_builds_an_enum_schema_and_maps_the_response(self) -> None:
        client = MagicMock(spec=["chat_json", "model", "run_id"])
        client.model = "gpt-test"
        client.run_id = "run-1"
        client.chat_json.return_value = {"choice": "Organisation", "confidence": 0.8}

        provider = LLMProvider(client, provider_label="llm_cheap")
        question = ChoiceQuestion(options=["Person", "Organisation"])
        result = provider.decide(_STATE, question)

        sent_schema = client.chat_json.call_args.kwargs["schema"]
        assert sent_schema["properties"]["choice"]["enum"] == ["Person", "Organisation"]
        assert result.answer == "Organisation"
        assert result.distribution == {"Organisation": 0.8}
        assert result.provider == "llm_cheap"
        assert result.model_version == "gpt-test"
        # 0 heißt hier "vom Ledger gebucht" — der Client trägt eine run_id,
        # also protokolliert chat_json die Kosten selbst (ADR-0016).
        assert result.cost_micros == 0

    def test_cost_is_unknown_not_zero_when_the_client_has_no_run_id(self) -> None:
        """Ohne ``run_id`` kehrt ``_log_invocation_event`` früh zurück — die
        Kosten sind entstanden, aber nirgends gebucht. ``0`` würde das als
        "kostenlos" tarnen, deshalb ``None``."""
        client = MagicMock(spec=["chat_json", "model"])
        client.model = "gpt-test"
        client.chat_json.return_value = {"choice": "Organisation", "confidence": 0.8}

        result = LLMProvider(client).decide(_STATE, ChoiceQuestion(options=["Organisation"]))

        assert result.cost_micros is None

    def test_response_payload_never_reaches_the_error_message(self) -> None:
        """Die Fehlermeldung wandert über den Shadow-Aufrufer in die Logs;
        eine LLM-Antwort kann Teile des Prompts spiegeln, und der Prompt
        trägt den Entscheidungskontext im Klartext (ADR-0016: Telemetrie
        referenziert nur den context_hash)."""
        client = MagicMock(spec=["chat_json", "model"])
        client.model = "gpt-test"
        client.chat_json.return_value = {
            "echo": "Bundeskanzleramt, Bundesminister Musterfrau, streng vertraulich",
        }

        with pytest.raises(DecisionLLMResponseError) as excinfo:
            LLMProvider(client).decide(_STATE, NoulQuestion())

        message = str(excinfo.value)
        assert "Musterfrau" not in message
        assert "vertraulich" not in message
        # Die Form bleibt diagnostizierbar.
        assert "echo" in message

    def test_choice_outside_sent_options_is_a_response_error(self) -> None:
        client = MagicMock(spec=["chat_json", "model"])
        client.chat_json.return_value = {"choice": "Ort", "confidence": 0.5}
        provider = LLMProvider(client)

        with pytest.raises(DecisionLLMResponseError):
            provider.decide(_STATE, ChoiceQuestion(options=["Person", "Organisation"]))

    def test_score_question_maps_stage_and_validates_range(self) -> None:
        client = MagicMock(spec=["chat_json", "model"])
        client.chat_json.return_value = {"stage": 4, "confidence": 0.6}
        client.model = "gpt-test"
        provider = LLMProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=5, legend={i: str(i) for i in range(1, 6)})
        result = provider.decide(_STATE, question)

        assert result.answer == 4
        assert result.confidence == pytest.approx(0.6)

    def test_score_stage_outside_range_is_a_response_error(self) -> None:
        client = MagicMock(spec=["chat_json", "model"])
        client.chat_json.return_value = {"stage": 9, "confidence": 0.6}
        provider = LLMProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=5, legend={i: str(i) for i in range(1, 6)})
        with pytest.raises(DecisionLLMResponseError):
            provider.decide(_STATE, question)

    def test_noul_question_maps_probability_yes(self) -> None:
        client = MagicMock(spec=["chat_json", "model"])
        client.chat_json.return_value = {"probability_yes": 0.73, "confidence": 0.73}
        client.model = "gpt-test"
        provider = LLMProvider(client)

        result = provider.decide(_STATE, NoulQuestion())

        assert result.probability_yes == pytest.approx(0.73)
        assert result.answer is None

    def test_missing_confidence_field_is_a_response_error(self) -> None:
        client = MagicMock(spec=["chat_json", "model"])
        client.chat_json.return_value = {"probability_yes": 0.5}
        provider = LLMProvider(client)

        with pytest.raises(DecisionLLMResponseError):
            provider.decide(_STATE, NoulQuestion())

    def test_only_calls_chat_json_never_a_second_llm_path(self) -> None:
        """ADR-0017: kein zweiter roher LLM-Zugriffspfad neben chat_json."""
        client = MagicMock(spec=["chat_json", "model"])
        client.chat_json.return_value = {"probability_yes": 0.5, "confidence": 0.5}
        client.model = "gpt-test"
        LLMProvider(client).decide(_STATE, NoulQuestion())

        client.chat_json.assert_called_once()
