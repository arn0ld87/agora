"""Echter Integrationstest für ``JevDecisionProvider`` gegen die reale
TypeSafe-API (f005, Slice `jev-benchmark`).

Anders als die Redis-/Neo4j-/Postgres-Fixtures in ``conftest.py`` bindet
dieser Test NICHT an ``AGORA_TEST_REQUIRE_SERVICES``: Jev ist ein
bezahlter externer Drittanbieter-Dienst, kein von CI selbst hochgefahrener
Servicecontainer. Ein Skip ohne ``TYPESAFE_API_KEY`` ist deshalb dauerhaft
korrekt, nicht nur eine lokale Bequemlichkeit — CI soll nie implizit
gegen einen echten, kostenpflichtigen Account laufen.
"""

from __future__ import annotations

import os

import pytest

from app.contracts.decision_contract import ChoiceQuestion, DecisionState, NoulQuestion, ScoreQuestion
from app.services.decisions.jev_provider import JEV_PINNED_MODEL_VERSION, build_jev_client
from app.services.decisions.jev_provider import JevDecisionProvider

pytestmark = pytest.mark.integration


@pytest.fixture
def jev_client(monkeypatch: pytest.MonkeyPatch):
    api_key = os.environ.get("TYPESAFE_API_KEY")
    if not api_key:
        pytest.skip("TYPESAFE_API_KEY nicht gesetzt. Integrationstest uebersprungen.")
    # build_jev_client liest ueber den Secret-Store, nicht ueber das
    # Environment direkt — fuer den Integrationstest genuegt es, den
    # Store-Zugriff auf den Env-Wert umzuleiten, statt echte Store-Daten
    # anzulegen.
    monkeypatch.setattr(
        "app.services.decisions.jev_provider.resolve_jev_api_key", lambda: api_key
    )
    client = build_jev_client()
    yield client
    client.close()


class TestJevDecisionProviderAgainstTheRealApi:
    def test_noul_question_returns_a_plausible_probability(self, jev_client) -> None:
        state = DecisionState(
            use_case_id="integration-test",
            state="Der Text erwähnt das Bundeskanzleramt in Berlin.",
            context_hash="itest-noul",
        )
        result = JevDecisionProvider(jev_client).decide(
            state, NoulQuestion()
        )

        assert 0.0 <= result.probability_yes <= 1.0
        assert result.model_version == JEV_PINNED_MODEL_VERSION
        assert result.provider == "jev"
        assert result.request_id
        assert result.cost_micros is not None and result.cost_micros >= 0
        assert result.latency_ms >= 0

    def test_choice_question_selects_one_of_the_sent_options(self, jev_client) -> None:
        state = DecisionState(
            use_case_id="integration-test",
            state="Das Bundeskanzleramt hat heute eine Entscheidung getroffen.",
            context_hash="itest-choice",
        )
        question = ChoiceQuestion(options=["Person", "Organisation"])

        result = JevDecisionProvider(jev_client).decide(state, question)

        assert result.answer in question.options
        assert result.distribution is not None
        assert set(result.distribution) <= set(question.options)

    def test_score_question_returns_a_stage_within_range(self, jev_client) -> None:
        state = DecisionState(
            use_case_id="integration-test",
            state="Ich wurde doppelt belastet, bitte dringend beheben!",
            context_hash="itest-score",
        )
        question = ScoreQuestion(
            min_stage=1, max_stage=3, legend={1: "niedrig", 2: "mittel", 3: "hoch"}
        )

        result = JevDecisionProvider(jev_client).decide(state, question)

        assert result.answer in (1, 2, 3)

    def test_empty_api_key_is_rejected_before_any_retry_loop(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Failure-Injection (benchmark-design.md, 1.5): ein ungültiger Key
        muss sichtbar scheitern, nicht still eine falsche Antwort liefern
        oder unbegrenzt retryen."""
        api_key = os.environ.get("TYPESAFE_API_KEY")
        if not api_key:
            pytest.skip("TYPESAFE_API_KEY nicht gesetzt. Integrationstest uebersprungen.")
        from typesafe_sdk import TypeSafeAPIError

        monkeypatch.setattr(
            "app.services.decisions.jev_provider.resolve_jev_api_key",
            lambda: "invalid-key-for-failure-injection-test",
        )
        client = build_jev_client()
        try:
            state = DecisionState(use_case_id="integration-test", state="x", context_hash="itest-fail")
            with pytest.raises(TypeSafeAPIError) as excinfo:
                JevDecisionProvider(client).decide(state, NoulQuestion())
            assert excinfo.value.status == 401
        finally:
            client.close()
