"""Tests für die Streitfrage des Laufs (Issue #1778, Schritt 1.4).

Deckt die fünf im Planschritt 1.4 geforderten Fälle ab: Aussage über den
LLM-Stub, keine Streitfrage über den Stub, Nutzervorgabe ohne LLM-Aufruf,
durchgereichter ``BudgetExceededError`` und sichtbarer Fallback bei jedem
anderen Fehler.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from app.contracts.contested_question_contract import ContestedQuestion
from app.services.run_budget import BudgetExceededError
from app.services.simulation_config_contested_question import (
    generate_contested_question,
)
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.simulation_config_schemas import ContestedQuestionResponse

_STATEMENT = "Die Geburtshilfe in Brenkhausen wird zum 30. Juni 2027 geschlossen."


def _stub_call_llm(response: dict, calls: list | None = None):
    def call_llm(prompt: str, system_prompt: str, schema: Any) -> dict:
        if calls is not None:
            calls.append((prompt, system_prompt, schema))
        return response

    return call_llm


class TestGenerateContestedQuestion:
    def test_llm_liefert_aussage_danach_origin_assistant(self):
        call_llm = _stub_call_llm(
            {"has_contested_question": True, "statement": _STATEMENT, "absence_reason": None}
        )
        cq = generate_contested_question(call_llm, "Wie reagiert das Umfeld auf die Schließung?")
        assert cq == ContestedQuestion(statement=_STATEMENT, origin="assistant")

    def test_llm_ohne_streitfrage_danach_origin_none(self):
        call_llm = _stub_call_llm(
            {
                "has_contested_question": False,
                "statement": None,
                "absence_reason": "Offene Wahrnehmungsfrage.",
            }
        )
        cq = generate_contested_question(call_llm, "Anforderung")
        assert cq.origin == "none"
        assert cq.statement is None
        assert cq.absence_reason == "Offene Wahrnehmungsfrage."

    def test_budget_exceeded_wird_durchgereicht(self):
        def call_llm(prompt: str, system_prompt: str, schema: Any) -> dict:
            raise BudgetExceededError("calls", 101, 100)

        with pytest.raises(BudgetExceededError):
            generate_contested_question(call_llm, "Anforderung")

    def test_anderer_fehler_fuehrt_auf_origin_none(self):
        def call_llm(prompt: str, system_prompt: str, schema: Any) -> dict:
            raise RuntimeError("Provider nicht erreichbar")

        cq = generate_contested_question(call_llm, "Anforderung")
        assert cq.origin == "none"
        assert cq.statement is None
        assert cq.absence_reason == "Streitfrage konnte nicht ermittelt werden."


class TestOverrideImKonfigurationsAssistent:
    @patch("app.services.simulation_config_generator.LLMClient")
    def test_override_setzt_origin_user_ohne_llm_aufruf(self, mock_llm_client_cls):
        mock_client = MagicMock()
        mock_llm_client_cls.return_value = mock_client
        mock_client.remaining_hard_call_budget.return_value = None

        cq_schemas: list[type] = []

        def fake_chat_json(
            messages: Any,
            temperature: float = 0.7,
            schema: Any = None,
            context: Any = None,
        ) -> dict:
            if schema is ContestedQuestionResponse:
                cq_schemas.append(schema)
                return {
                    "has_contested_question": False,
                    "statement": None,
                    "absence_reason": "darf nicht erreicht werden",
                }
            name = getattr(schema, "__name__", str(schema))
            if name == "TimeConfigResponse":
                return {
                    "total_simulation_hours": 24,
                    "minutes_per_round": 60,
                    "agents_per_hour_min": 5,
                    "agents_per_hour_max": 20,
                    "peak_hours": [18, 19, 20, 21, 22],
                    "off_peak_hours": [0, 1, 2, 3, 4, 5],
                    "morning_hours": [6, 7, 8],
                    "work_hours": list(range(9, 17)),
                    "reasoning": "Standard",
                }
            if name == "EventConfigResponse":
                return {
                    "hot_topics": [],
                    "narrative_direction": "",
                    "initial_posts": [],
                    "reasoning": "leer",
                }
            raise AssertionError(f"unerwartetes Schema: {name}")

        mock_client.chat_json.side_effect = fake_chat_json

        generator = SimulationConfigGenerator(
            api_key="test-key", base_url="http://localhost:11434"
        )
        params = generator.generate_config(
            simulation_id="sim-1",
            project_id="proj-1",
            graph_id="graph-1",
            simulation_requirement="Anforderung",
            document_text="Dokument",
            entities=[],
            enable_twitter=False,
            enable_reddit=False,
            contested_question_override=(
                "  Die Kita am Berg wird zum Schuljahresende geschlossen.  "
            ),
        )

        # Override darf den Streitfragen-LLM-Aufruf komplett ersetzen.
        assert cq_schemas == []
        assert params.contested_question == {
            "statement": "Die Kita am Berg wird zum Schuljahresende geschlossen.",
            "origin": "user",
            "absence_reason": None,
        }


class TestOverrideAusDemPrepareLauf:
    """Schritt 1.6: Die Nutzervorgabe aus dem Prepare-Request erreicht ``generate_config``."""

    @staticmethod
    def _run_phase(monkeypatch, **kwargs: Any) -> MagicMock:
        from app.services import prepare_service
        from app.services.llm_runtime import RuntimeLlmConfig

        fake_params = MagicMock(
            to_json=lambda: '{"time_config": {}}', generation_reasoning="ok"
        )
        generator = MagicMock(generate_config=MagicMock(return_value=fake_params))
        monkeypatch.setattr(
            prepare_service, "SimulationConfigGenerator", lambda **kw: generator
        )
        state = MagicMock(
            project_id="proj_x", graph_id="g_x", enable_twitter=True, enable_reddit=True
        )
        prepare_service._phase_generate_config(
            MagicMock(name="SimulationManager"),
            state,
            "sim_xyz",
            "requirement",
            "doc",
            expanded_entities=[],
            llm_model=None,
            llm_runtime=RuntimeLlmConfig(
                provider="custom_openai",
                api_key="runtime-override-placeholder",
                base_url="http://llm.invalid/v1",
            ),
            language=None,
            **kwargs,
        )
        return generator

    def test_vorgabe_wird_an_generate_config_uebergeben(self, monkeypatch):
        generator = self._run_phase(
            monkeypatch, contested_question_override="Die Kita am Berg wird geschlossen."
        )

        assert (
            generator.generate_config.call_args.kwargs["contested_question_override"]
            == "Die Kita am Berg wird geschlossen."
        )

    def test_ohne_vorgabe_wird_none_uebergeben(self, monkeypatch):
        generator = self._run_phase(monkeypatch)

        assert generator.generate_config.call_args.kwargs["contested_question_override"] is None

    def test_manager_reicht_die_vorgabe_an_den_service_durch(self, monkeypatch):
        from app.services import prepare_service
        from app.services.simulation_manager import SimulationManager

        received: dict[str, Any] = {}

        def fake_prepare_simulation(manager, simulation_id, requirement, document_text, **kwargs):
            received.update(kwargs)
            return MagicMock(name="state")

        monkeypatch.setattr(prepare_service, "prepare_simulation", fake_prepare_simulation)
        SimulationManager.prepare_simulation(
            MagicMock(),
            simulation_id="sim_xyz",
            simulation_requirement="requirement",
            document_text="doc",
            contested_question_override="Die Kita am Berg wird geschlossen.",
        )

        assert received["contested_question_override"] == "Die Kita am Berg wird geschlossen."


class TestAlignSentimentSign:
    """Schritt 1.5: Haltung und Vorzeichen von ``sentiment_bias`` passen zusammen.

    Messwert aus dem Referenzlauf: AfD ``opposing`` mit +0,65, Samtgemeinde
    Ohlendorf ``supportive`` mit -0,4. Die Haltung gewinnt.
    """

    def test_opposing_mit_positivem_bias_wird_negativ(self):
        from app.services.simulation_config_agents import _align_sentiment_sign

        assert _align_sentiment_sign("opposing", 0.65) == -0.65

    def test_supportive_mit_negativem_bias_wird_positiv(self):
        from app.services.simulation_config_agents import _align_sentiment_sign

        assert _align_sentiment_sign("supportive", -0.4) == 0.4

    def test_neutral_bleibt_unveraendert(self):
        from app.services.simulation_config_agents import _align_sentiment_sign

        assert _align_sentiment_sign("neutral", 0.3) == 0.3


class TestContestedQuestionInAgentConfigPrompt:
    """Schritt 1.5: Der Konfigurations-Prompt bezieht die Haltung auf die Streitfrage."""

    @staticmethod
    def _generator(prompts: list[str]) -> SimulationConfigGenerator:
        with patch("app.services.simulation_config_generator.LLMClient", MagicMock()):
            generator = SimulationConfigGenerator(api_key="k", base_url="http://localhost")

        def call_llm(prompt: str, system_prompt: str, schema: Any) -> dict:
            prompts.append(prompt)
            return {
                "agent_configs": [
                    {"agent_id": 0, "stance": "opposing", "sentiment_bias": 0.65}
                ]
            }

        generator._call_llm_with_retry = call_llm  # type: ignore[method-assign]
        return generator

    @staticmethod
    def _entity():
        from app.services.entity_reader import EntityNode

        return EntityNode(
            uuid="e-1",
            name="Betriebsrat",
            labels=["Entity", "Organization"],
            summary="Vertretung der Beschäftigten",
            attributes={},
            related_edges=[],
            related_nodes=[],
        )

    def test_streitfrage_steht_im_prompt_und_bias_folgt_der_haltung(self):
        prompts: list[str] = []
        generator = self._generator(prompts)

        configs = generator._generate_agent_configs_batch(
            "ctx", [self._entity()], 0, "Was passiert?", contested_statement=_STATEMENT
        )

        assert f"Contested question: {_STATEMENT}" in prompts[0]
        assert "refer ONLY to this contested question" in prompts[0]
        assert configs[0].stance == "opposing"
        assert configs[0].sentiment_bias == -0.65

    def test_ohne_streitfrage_bleibt_der_prompt_unveraendert(self):
        prompts: list[str] = []
        generator = self._generator(prompts)

        generator._generate_agent_configs_batch("ctx", [self._entity()], 0, "Was passiert?")

        assert "Contested question" not in prompts[0]

    def test_ohne_streitfrage_bleibt_das_vorzeichen_des_bias_unveraendert(self):
        """Review PR #1780: Läufe ohne Streitfrage ändern ihr Verhalten nicht."""
        generator = self._generator([])

        configs = generator._generate_agent_configs_batch(
            "ctx", [self._entity()], 0, "Was passiert?"
        )

        assert configs[0].stance == "opposing"
        assert configs[0].sentiment_bias == 0.65
