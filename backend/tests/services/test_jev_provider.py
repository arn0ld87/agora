"""Tests für den JevDecisionProvider-Referenzadapter (f005, Slice
`decision-pilot`, Task `jev-adapter`).

``client`` wird als ``MagicMock`` injiziert — genau wie bei ``LLMProvider``
(``test_decision_providers.py``) — weil ``typesafe-sdk`` bewusst noch keine
Produktabhängigkeit ist (siehe Moduldocstring von ``jev_provider.py``).
"""

from __future__ import annotations

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
    DecisionJevAuthError,
    DecisionJevResponseError,
    JevDecisionProvider,
    resolve_jev_api_key,
)
from app.services.pricing_registry import get_pricing_registry, reset_pricing_registry

_STATE = DecisionState(use_case_id="persona-eligibility", state="Bundeskanzleramt", context_hash="h1")


class TestJevDecisionProvider:
    def test_satisfies_the_decision_provider_protocol(self) -> None:
        assert isinstance(JevDecisionProvider(MagicMock()), DecisionProvider)

    def test_choice_question_maps_answer_and_confidence(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "choice": "Organisation", "confidence": 0.8}],
            "model": "jev-1.13.0",
            "request_id": "req-abc",
            "usage": {"input_tokens": 100, "output_tokens": 0},
        }
        provider = JevDecisionProvider(client)

        question = ChoiceQuestion(options=["Person", "Organisation"])
        result = provider.decide(_STATE, question)

        sent_questions = client.system_one.call_args.kwargs["questions"]
        assert sent_questions == [
            {"id": "q1", "type": "choice", "options": ["Person", "Organisation"]}
        ]
        assert client.system_one.call_args.kwargs["model"] == JEV_PINNED_MODEL_VERSION
        assert client.system_one.call_args.kwargs["state"] == _STATE.state
        assert result.answer == "Organisation"
        assert result.distribution == {"Organisation": 0.8}
        assert result.provider == "jev"
        assert result.model_version == "jev-1.13.0"
        assert result.request_id == "req-abc"
        # 100 Input-Tokens * 42000 Micros/Mio. Tokens // 1_000_000 = 4 Micros.
        assert result.cost_micros == 4

    def test_score_question_maps_stage_and_validates_range(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "stage": 4, "confidence": 0.6}],
            "model": "jev-1.13.0",
            "usage": {"input_tokens": 0, "output_tokens": 0},
        }
        provider = JevDecisionProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=5, legend={i: str(i) for i in range(1, 6)})
        result = provider.decide(_STATE, question)

        assert result.answer == 4
        assert result.confidence == pytest.approx(0.6)
        assert result.cost_micros == 0

    def test_score_stage_outside_range_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "stage": 9, "confidence": 0.6}],
            "model": "jev-1.13.0",
            "usage": None,
        }
        provider = JevDecisionProvider(client)

        question = ScoreQuestion(min_stage=1, max_stage=5, legend={i: str(i) for i in range(1, 6)})
        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, question)

    def test_noul_question_maps_probability_yes(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "probability_yes": 0.73, "confidence": 0.73}],
            "model": "jev-1.13.0",
            "usage": None,
        }
        provider = JevDecisionProvider(client)

        result = provider.decide(_STATE, NoulQuestion())

        assert result.probability_yes == pytest.approx(0.73)
        assert result.answer is None

    def test_choice_outside_sent_options_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "choice": "Ort", "confidence": 0.5}],
            "model": "jev-1.13.0",
        }
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, ChoiceQuestion(options=["Person", "Organisation"]))

    def test_missing_confidence_field_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "probability_yes": 0.5}],
        }
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, NoulQuestion())

    def test_missing_question_id_in_answers_is_a_response_error(self) -> None:
        """jev-provider-evidence.md: das SDK kann unbekannte Antwortarten
        warnend überspringen — eine fehlende Fragen-ID ist trotzdem ein
        Fehler, kein stiller Leerwert."""
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {"answers": []}
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, NoulQuestion())

    def test_non_mapping_response_is_a_response_error(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = "not-a-dict"
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevResponseError):
            provider.decide(_STATE, NoulQuestion())

    def test_auth_error_propagates_without_being_retried(self) -> None:
        """Kein zweiter Retry-Layer im Adapter (Moduldocstring) — 401/422
        laufen unverändert zum Aufrufer durch, exakt einmal versucht."""
        client = MagicMock(spec=["system_one"])
        client.system_one.side_effect = DecisionJevAuthError("401")
        provider = JevDecisionProvider(client)

        with pytest.raises(DecisionJevAuthError):
            provider.decide(_STATE, NoulQuestion())
        client.system_one.assert_called_once()

    def test_cost_is_priced_against_the_model_jev_actually_reports(self) -> None:
        """Jev kann laut Anbieterdoku eine andere Version zurückmelden als
        die angefragte. Der Preis des gepinnten Modells wäre dann der Preis
        eines anderen Modells."""
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "probability_yes": 0.5, "confidence": 0.5}],
            "model": "jev-9.9.9-unbekannt",
            "usage": {"input_tokens": 1_000_000, "output_tokens": 0},
        }

        result = JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        assert result.model_version == "jev-9.9.9-unbekannt"
        # Kein Preiseintrag für diese Version -> unbekannt, nicht 0.
        assert result.cost_micros is None

    def test_missing_usage_makes_the_cost_unknown_not_zero(self) -> None:
        """Ohne ``usage`` ist der Verbrauch unbekannt, nicht null —
        ``pricing_registry`` hält dieselbe Regel fest: ein unbekannter
        Preis wird niemals als 0 ausgegeben."""
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "probability_yes": 0.5, "confidence": 0.5}],
            "model": "jev-1.13.0",
        }

        result = JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        assert result.cost_micros is None

    def test_response_payload_never_reaches_the_error_message(self) -> None:
        """Die Fehlermeldung wandert über den Shadow-Aufrufer in die Logs;
        eine Antwort eines externen Dienstes kann Teile der Anfrage
        spiegeln (ADR-0016: Telemetrie referenziert nur den context_hash)."""
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "echo": "Bundeskanzleramt, Bundesminister Musterfrau, streng vertraulich",
        }

        with pytest.raises(DecisionJevResponseError) as excinfo:
            JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        message = str(excinfo.value)
        assert "Musterfrau" not in message
        assert "vertraulich" not in message
        assert "echo" in message

    @pytest.mark.parametrize(
        "transient",
        [TimeoutError("read timeout"), ConnectionError("reset"), RuntimeError("429 rate limit")],
    )
    def test_transient_errors_propagate_after_exactly_one_attempt(
        self, transient: Exception
    ) -> None:
        """Der Adapter baut bewusst keine zweite Retry-Schleife über die
        des SDK (jev-provider-evidence.md warnt vor verschachtelten
        Retries). Dieser Test nagelt das fest: genau ein Versuch, Fehler
        unverändert nach außen, damit die Fallback-Kette des Aufrufers
        entscheidet."""
        client = MagicMock(spec=["system_one"])
        client.system_one.side_effect = transient

        with pytest.raises(type(transient)):
            JevDecisionProvider(client).decide(_STATE, NoulQuestion())

        client.system_one.assert_called_once()

    def test_model_version_falls_back_to_pinned_default_when_response_omits_it(self) -> None:
        client = MagicMock(spec=["system_one"])
        client.system_one.return_value = {
            "answers": [{"id": "q1", "probability_yes": 0.5, "confidence": 0.5}],
        }
        provider = JevDecisionProvider(client)

        result = provider.decide(_STATE, NoulQuestion())

        assert result.model_version == JEV_PINNED_MODEL_VERSION


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


class TestJevPricingEntry:
    """Contract-Test für den 'jev'-Eintrag in model_pricing.json (Task
    `jev-adapter`) — keine zweite Preisquelle neben der PricingRegistry."""

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
