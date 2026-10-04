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
