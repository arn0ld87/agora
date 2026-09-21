"""Tests für den JevDecisionProvider-Referenzadapter (f005, Slice
`jev-benchmark`, Task `real-jev-client`) — gegen die echte, verifizierte
``typesafe-sdk``-Antwortform (siehe Moduldocstring von ``jev_provider.py``).

``client.system_one(...)`` wird als ``MagicMock`` injiziert, dessen
Rückgabe die reale ``SystemOneResponse``-Form nachbildet (per
``SimpleNamespace`` statt des echten, frozen Pydantic-Modells — die
Attributzugriffe sind identisch, der Adapter unterscheidet nicht).
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.contracts.decision_contract import (
    ChoiceQuestion,
    DecisionState,
    NoulQuestion,
    ScoreQuestion,
)
from app.repositories.decision_provider import DecisionProvider
from app.services.decisions.jev_provider import (
    JEV_PINNED_MODEL_VERSION,
    DecisionJevResponseError,
    JevDecisionProvider,
    resolve_jev_api_key,
)
from app.services.pricing_registry import get_pricing_registry, reset_pricing_registry

_STATE = DecisionState(use_case_id="persona-eligibility", state="Bundeskanzleramt", context_hash="h1")


def _usage(input_tokens: int = 100, output_tokens: int = 10) -> SimpleNamespace:
    return SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)


def _response(
    *,
    model: str = "jev-1.13.0",
    request_id: str | None = "req-abc",
    usage: SimpleNamespace | None = None,
    choices: dict[str, SimpleNamespace] | None = None,
    scores: dict[str, SimpleNamespace] | None = None,
    nouls: dict[str, SimpleNamespace] | None = None,
    answers: object = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        model=model,
        request_id=request_id,
        usage=usage if usage is not None else _usage(),
        choices=choices or {},
        scores=scores or {},
        nouls=nouls or {},
        answers=answers if answers is not None else {},
    )


class TestJevDecisionProvider:
    def test_satisfies_the_decision_provider_protocol(self) -> None:
        assert isinstance(JevDecisionProvider(MagicMock()), DecisionProvider)

    def test_choice_question_maps_answer_confidence_and_distribution(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            choices={
                "decision": SimpleNamespace(
                    choice="Organisation",
                    confidence=0.9,
                    probabilities={"Organisation": 0.9, "Person": 0.1},
                )
            },
        )
        provider = JevDecisionProvider(client)

        question = ChoiceQuestion(options=["Person", "Organisation"])
        result = provider.decide(_STATE, question)

        sent_questions = client.system_one.call_args.kwargs["questions"]
        assert set(sent_questions) == {"decision"}
        assert sent_questions["decision"].criteria == {"Person": None, "Organisation": None}
        assert client.system_one.call_args.kwargs["state"] == _STATE.state
        assert result.answer == "Organisation"
        assert result.distribution == {"Organisation": 0.9, "Person": 0.1}
        assert result.confidence == pytest.approx(0.9)
        assert result.provider == "jev"
        assert result.model_version == "jev-1.13.0"
        assert result.request_id == "req-abc"
        # 100 Input-Tokens * 42000 Micros/Mio. Tokens // 1_000_000 = 4 Micros.
        assert result.cost_micros == 4

    def test_choice_outside_sent_options_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            choices={"decision": SimpleNamespace(choice="Ort", confidence=0.5, probabilities={"Ort": 0.5})},
        )
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, ChoiceQuestion(options=["Person", "Organisation"]))

    def test_out_of_range_value_never_appears_in_the_error_even_truncated(self) -> None:
        """Review-Befund (Codex, PR #1547): eine auf 80 Zeichen gekürzte
        Wertdarstellung reicht aus, um ein gespiegeltes Secret zu leaken —
        Kürzung ist keine Redaktion. Der Fehler darf nur Typ/Länge/Hash
        zeigen, nie einen Ausschnitt des tatsächlichen Werts."""
        secret_looking_choice = "sk-live-AKIAEXAMPLESECRETVALUE1234567890"
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            choices={
                "decision": SimpleNamespace(
                    choice=secret_looking_choice,
                    confidence=0.5,
                    probabilities={secret_looking_choice: 0.5},
                )
            },
        )
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError) as excinfo:
            provider.decide(_STATE, ChoiceQuestion(options=["Person", "Organisation"]))

        message = str(excinfo.value)
        assert secret_looking_choice not in message
        assert secret_looking_choice[:20] not in message
        assert "str(len=" in message

    def test_missing_choice_answer_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(choices={})
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, ChoiceQuestion(options=["Person", "Organisation"]))

    def test_score_question_sends_an_ordered_criteria_list_and_rounds_to_a_stage(self) -> None:
        client = MagicMock(spec=["system_one"])
        # score=1.6 liegt naeher an Index 2 (0-basiert: 0,1,2 fuer Stufen 1,2,3)
        # als an Index 1 -> gerundet auf 2 -> Stufe min_stage(1) + 2 = 3.
        client.system_one.return_value = _response(
            scores={"decision": SimpleNamespace(score=1.6, confidence=0.7)},
        )
        provider = JevDecisionProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=3, legend={1: "niedrig", 2: "mittel", 3: "hoch"})
        result = provider.decide(_STATE, question)

        sent_questions = client.system_one.call_args.kwargs["questions"]
        assert sent_questions["decision"].criteria == ["niedrig", "mittel", "hoch"]
        assert result.answer == 3
        assert result.confidence == pytest.approx(0.7)

    def test_score_rounds_down_when_closer_to_the_lower_stage(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            scores={"decision": SimpleNamespace(score=0.3, confidence=0.6)},
        )
        provider = JevDecisionProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=3, legend={1: "niedrig", 2: "mittel", 3: "hoch"})
        result = provider.decide(_STATE, question)

        assert result.answer == 1

    def test_missing_score_answer_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(scores={})
        provider = JevDecisionProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=3, legend={1: "a", 2: "b", 3: "c"})
        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, question)

    def test_noul_question_maps_probability_and_derives_confidence_from_distance_to_half(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            nouls={"decision": SimpleNamespace(noul=0.93)},
        )
        provider = JevDecisionProvider(client)

        result = provider.decide(_STATE, NoulQuestion())

        assert result.probability_yes == pytest.approx(0.93)
        assert result.answer is None
        # 2 * |0.93 - 0.5| = 0.86
        assert result.confidence == pytest.approx(0.86)

    def test_noul_near_one_half_yields_low_derived_confidence(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            nouls={"decision": SimpleNamespace(noul=0.52)},
        )
        result = JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        assert result.confidence == pytest.approx(0.04)

    def test_missing_noul_answer_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(nouls={})
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, NoulQuestion())

    def test_cost_is_priced_against_the_model_jev_actually_reports(self) -> None:
        """Jev kann laut Anbieterdoku eine andere Version zurückmelden als
        die angefragte. Der Preis des gepinnten Modells wäre dann der Preis
        eines anderen Modells."""
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            model="jev-9.9.9-unbekannt",
            nouls={"decision": SimpleNamespace(noul=0.5)},
            usage=_usage(1_000_000, 0),
        )

        result = JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        assert result.model_version == "jev-9.9.9-unbekannt"
        # Kein Preiseintrag für diese Version -> unbekannt, nicht 0.
        assert result.cost_micros is None

    def test_missing_usage_makes_the_cost_unknown_not_zero(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = _response(
            usage=SimpleNamespace(),  # kein input_tokens/output_tokens
            nouls={"decision": SimpleNamespace(noul=0.5)},
        )

        result = JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        assert result.cost_micros is None

    @pytest.mark.parametrize(
        "transient",
        [TimeoutError("read timeout"), ConnectionError("reset"), RuntimeError("429 rate limit")],
    )
    def test_transient_errors_propagate_after_exactly_one_attempt(
        self, transient: Exception
    ) -> None:
        """Der Adapter baut bewusst keine zweite Retry-Schleife über die
        des SDK. Genau ein Versuch, Fehler unverändert nach außen, damit
        die Fallback-Kette des Aufrufers entscheidet."""
        client = MagicMock(spec=["system_one"])
        client.system_one.side_effect = transient

        with pytest.raises(type(transient)):
            JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        client.system_one.assert_called_once()


class TestResolveJevApiKey:
    def test_delegates_to_bound_store_lookup(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.decisions.jev_provider.get_bound_store_api_key",
            lambda secret_ref, *, secrets_store=None: (
                "jev-secret-value" if secret_ref == "jev" else None
            ),
        )
        assert resolve_jev_api_key() == "jev-secret-value"

    def test_returns_none_when_no_secret_is_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            "app.services.decisions.jev_provider.get_bound_store_api_key",
            lambda secret_ref, *, secrets_store=None: None,
        )
        assert resolve_jev_api_key() is None


class TestBuildJevClient:
    def test_raises_when_no_secret_is_bound(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from app.services.decisions.jev_provider import build_jev_client

        monkeypatch.setattr(
            "app.services.decisions.jev_provider.resolve_jev_api_key", lambda: None
        )
        with pytest.raises(RuntimeError, match="Kein Jev-API-Key"):
            build_jev_client()

    def test_builds_a_real_client_with_the_pinned_model_when_a_secret_exists(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from typesafe_sdk import TypeSafeClient

        from app.services.decisions.jev_provider import build_jev_client

        monkeypatch.setattr(
            "app.services.decisions.jev_provider.resolve_jev_api_key", lambda: "test-key"
        )
        client = build_jev_client()

        assert isinstance(client, TypeSafeClient)


class TestJevPricingEntry:
    """Contract-Test für den 'jev'-Eintrag in model_pricing.json — keine
    zweite Preisquelle neben der PricingRegistry."""

    def teardown_method(self) -> None:
        reset_pricing_registry()

    def test_jev_pinned_model_resolves_to_the_documented_price(self) -> None:
        reset_pricing_registry()
        quote = get_pricing_registry().resolve("jev", JEV_PINNED_MODEL_VERSION)

        assert quote.status == "priced"
        # USD 0,042 / Mio. Input-Tokens (jev-provider-evidence.md) = 42000 Micros/Mio.
        assert quote.input_per_mtok_micros == 42000
        # Output-Tokens sind laut Anbieterangabe kostenlos.
        assert quote.output_per_mtok_micros == 0
