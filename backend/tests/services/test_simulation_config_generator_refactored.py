from __future__ import annotations

from unittest.mock import MagicMock, patch
import pytest

from app.services.entity_reader import EntityNode
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.simulation_config_schemas import get_time_config_schema


class TestSimulationConfigGeneratorRefactored:
    @patch("app.services.simulation_config_generator.LLMClient")
    def test_reasoning_prefix_cleaned_and_parsed_correctly(self, mock_llm_client_cls):
        # 1. Mock the LLMClient instance
        mock_client = MagicMock()
        mock_llm_client_cls.return_value = mock_client
        # Kein hartes Aufrufbudget in diesem Test: ohne diese Vorgabe liefert
        # der MagicMock ein weiteres MagicMock statt ``None`` und der
        # Poolgroessen-Deckel in ``_generate_agent_configs_parallel``
        # vergleicht es mit einem int (#1452).
        mock_client.remaining_hard_call_budget.return_value = None

        time_data = {
            "total_simulation_hours": 72,
            "minutes_per_round": 60,
            "agents_per_hour_min": 5,
            "agents_per_hour_max": 20,
            "peak_hours": [18, 19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16],
            "reasoning": "Standard timing",
        }

        # With 30 entities and batch size of 8 (default), we have math.ceil(30/8) = 4 batches of agents.
        # Total calls to chat_json: 1 (time) + 1 (event) + 4 (agent batches) = 6 calls.
        mock_client.chat_json.side_effect = [
            # 1. Time Config
            time_data,
            # 2. Event Config
            {
                "hot_topics": ["topic1"],
                "narrative_direction": "some direction",
                "initial_posts": [],
                "reasoning": "some reasoning",
            },
            # 3. Agent Batch 1 (0-7)
            {
                "agent_configs": [
                    {
                        "agent_id": i,
                        "activity_level": 0.5,
                        "posts_per_hour": 1.0,
                        "comments_per_hour": 2.0,
                        "active_hours": list(range(8, 23)),
                        "response_delay_min": 5,
                        "response_delay_max": 60,
                        "sentiment_bias": 0.0,
                        "stance": "neutral",
                        "influence_weight": 1.0,
                    }
                    for i in range(0, 8)
                ]
            },
            # 4. Agent Batch 2 (8-15)
            {
                "agent_configs": [
                    {
                        "agent_id": i,
                        "activity_level": 0.5,
                        "posts_per_hour": 1.0,
                        "comments_per_hour": 2.0,
                        "active_hours": list(range(8, 23)),
                        "response_delay_min": 5,
                        "response_delay_max": 60,
                        "sentiment_bias": 0.0,
                        "stance": "neutral",
                        "influence_weight": 1.0,
                    }
                    for i in range(8, 16)
                ]
            },
            # 5. Agent Batch 3 (16-23)
            {
                "agent_configs": [
                    {
                        "agent_id": i,
                        "activity_level": 0.5,
                        "posts_per_hour": 1.0,
                        "comments_per_hour": 2.0,
                        "active_hours": list(range(8, 23)),
                        "response_delay_min": 5,
                        "response_delay_max": 60,
                        "sentiment_bias": 0.0,
                        "stance": "neutral",
                        "influence_weight": 1.0,
                    }
                    for i in range(16, 24)
                ]
            },
            # 6. Agent Batch 4 (24-29)
            {
                "agent_configs": [
                    {
                        "agent_id": i,
                        "activity_level": 0.5,
                        "posts_per_hour": 1.0,
                        "comments_per_hour": 2.0,
                        "active_hours": list(range(8, 23)),
                        "response_delay_min": 5,
                        "response_delay_max": 60,
                        "sentiment_bias": 0.0,
                        "stance": "neutral",
                        "influence_weight": 1.0,
                    }
                    for i in range(24, 30)
                ]
            },
        ]

        # Instantiate generator
        generator = SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434")

        entities = [
            EntityNode(
                uuid=f"e-{i}",
                name=f"Entity {i}",
                labels=["Person"],
                summary="",
                attributes={},
            )
            for i in range(30)
        ]

        # Call generate_config
        params = generator.generate_config(
            simulation_id="sim-1",
            project_id="proj-1",
            graph_id="graph-1",
            simulation_requirement="Requirement",
            document_text="Document content",
            entities=entities,
            enable_twitter=True,
            enable_reddit=True,
        )

        assert params is not None
        assert params.time_config.total_simulation_hours == 72
        assert len(params.agent_configs) == 36  # 30 entities + 6 synthetic skeptics due to skepticism quota enforcement (36 total)

    @pytest.mark.parametrize(
        "agents_per_hour_max, expected_max",
        [
            (45, 15),  # 45 > 30 (num_entities) -> max_agents_allowed limit (validator coercion to num_entities // 2)
            (25, 25),  # 25 <= 30 -> remains 25
        ],
    )
    def test_schema_violating_bounds_corrected_by_pydantic_validator(
        self, agents_per_hour_max, expected_max
    ):
        # We test the dynamic schema validator directly to verify constraint enforcement
        schema_cls = get_time_config_schema(num_entities=30)

        # Instantiate with values violating the boundaries
        response = schema_cls(
            total_simulation_hours=72,
            minutes_per_round=60,
            agents_per_hour_min=5,
            agents_per_hour_max=agents_per_hour_max,
            peak_hours=[18, 19, 20, 21, 22],
            off_peak_hours=[0, 1, 2, 3, 4, 5],
            morning_hours=[6, 7, 8],
            work_hours=[9, 10, 11, 12, 13, 14, 15, 16],
            reasoning="Testing validator",
        )

        # Pydantic's validator should coerce agents_per_hour_max to be <= num_entities and min < max
        assert response.agents_per_hour_max <= 30
        assert response.agents_per_hour_max == expected_max

    @patch("app.services.simulation_config_generator.LLMClient")
    def test_fallback_when_chat_json_fails_but_regex_repair_succeeds(self, mock_llm_client_cls):
        # If chat_json raises Exception, the generator falls back to calling chat()
        # and applying regex-based JSON repair.
        mock_client = MagicMock()
        mock_llm_client_cls.return_value = mock_client
        # Kein hartes Aufrufbudget in diesem Test: ohne diese Vorgabe liefert
        # der MagicMock ein weiteres MagicMock statt ``None`` und der
        # Poolgroessen-Deckel in ``_generate_agent_configs_parallel``
        # vergleicht es mit einem int (#1452).
        mock_client.remaining_hard_call_budget.return_value = None

        # chat_json fails
        mock_client.chat_json.side_effect = ValueError("Strict Schema Violation or parsing failed")

        # chat() succeeds with reasoning/codefence and slightly truncated JSON that _try_fix_config_json can fix
        mock_client.chat.return_value = """
        Here is the JSON you requested:
        ```json
        {
            "total_simulation_hours": 48,
            "minutes_per_round": 30,
            "agents_per_hour_min": 2,
            "agents_per_hour_max": 10,
            "peak_hours": [18, 19, 20, 21, 22],
            "off_peak_hours": [0, 1, 2, 3, 4, 5],
            "morning_hours": [6, 7, 8],
            "work_hours": [9, 10, 11, 12, 13, 14, 15, 16],
            "reasoning": "Parsed after fallback"
        }
        ```
        """

        generator = SimulationConfigGenerator(api_key="test-key", base_url="http://localhost:11434")

        schema_cls = get_time_config_schema(num_entities=20)

        # Call the private retry method
        result = generator._call_llm_with_retry(
            prompt="Prompt", system_prompt="System Prompt", schema=schema_cls
        )

        assert result is not None
        assert result["total_simulation_hours"] == 48
        assert result["minutes_per_round"] == 30
        assert result["reasoning"] == "Parsed after fallback"


class TestSimulationConfigGeneratorCodexCliProviderType:
    """Regression for Issue #1418.

    ``codex_cli`` (transport="cli", #1405) hat weder base_url noch api_key —
    das ist der Normalfall, kein unaufgeloester Zustand. Ohne
    ``provider_type`` fuellte der eigene ``LLMClient`` dieses Generators
    ``.env``-Werte auf (beobachtet: das aus der Route gerouteten Modell ging
    an ``https://api.minimax.io/v1`` → HTTP 400 "unknown model").
    """

    @patch("app.services.simulation_config_generator.LLMClient")
    def test_llm_client_receives_provider_type_and_no_base_url(self, mock_llm_client_cls, monkeypatch):
        from app.config import Config

        monkeypatch.setattr(Config, "LLM_BASE_URL", "https://api.minimax.io/v1")
        monkeypatch.setattr(Config, "LLM_API_KEY", "env-minimax-key")

        SimulationConfigGenerator(provider_type="codex_cli", model_name="gpt-5.6-luna")

        assert mock_llm_client_cls.call_args.kwargs["provider_type"] == "codex_cli"
        assert mock_llm_client_cls.call_args.kwargs["base_url"] is None
        assert mock_llm_client_cls.call_args.kwargs["api_key"] != "env-minimax-key"

    @patch("app.services.simulation_config_generator.LLMClient")
    def test_self_base_url_stays_env_fallback_for_rounds_config(self, mock_llm_client_cls, monkeypatch):
        """``self.base_url`` bleibt unveraendert (auch fuer codex_cli): es
        speist ``SimulationParameters.llm_base_url`` fuer die Simulations-
        Runden — ein Pfad, den Issue #1418 nicht anfasst. Nur der eigene
        ``LLMClient`` dieses Generators (Config-Generierung) darf nicht mit
        dem Fallback gebaut werden (siehe Test oben).
        """
        from app.config import Config

        monkeypatch.setattr(Config, "LLM_BASE_URL", "https://api.minimax.io/v1")

        generator = SimulationConfigGenerator(provider_type="codex_cli", model_name="gpt-5.6-luna")

        assert generator.base_url == "https://api.minimax.io/v1"
