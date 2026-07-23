"""Reproduction tests for BUG A (Embedding 401) and BUG B (Persona JSON failures)."""

from unittest.mock import MagicMock, patch
import pytest

from app.config import Config
from app.storage.embedding_service import EmbeddingService, EmbeddingError
from app.services.oasis_profile_generator import OasisProfileGenerator


# ---------------------------------------------------------------------------
# BUG A Reproduction Tests: Embedding Key/Provider mismatch & 401 Unauthorized
# ---------------------------------------------------------------------------

def test_repro_bug_a_embedding_key_fallback_sends_chat_key_to_openai(monkeypatch):
    """BUG A Repro:
    When EMBEDDING_BASE_URL is an OpenAI-compatible endpoint, but EMBEDDING_API_KEY is empty,
    EmbeddingService._request_headers() should raise EmbeddingError rather than sending an unrelated
    LLM_API_KEY to OpenAI embeddings.
    """
    # Simulate env where EMBEDDING_API_KEY is unset/empty, LLM_API_KEY is 'ollama-chat-key'
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "ollama-chat-key")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "https://api.openai.com")

    service = EmbeddingService(
        model="text-embedding-3-small",
        base_url="https://api.openai.com",
    )
    assert service._provider == "openai"
    assert service.api_key == ""
    with pytest.raises(EmbeddingError, match="EMBEDDING_API_KEY is required for OpenAI embeddings"):
        service._request_headers()


def test_repro_bug_a_neo4j_storage_uses_raw_config_defaults_without_provider_connection():
    """BUG A Repro:
    Neo4jStorage initializes EmbeddingService() during real __init__ when no embedding_service is passed.
    """
    with patch("neo4j.GraphDatabase.driver"), \
         patch("app.storage.neo4j_storage.EmbeddingService") as mock_emb_cls, \
         patch("app.storage.neo4j_storage.NERExtractor"):
        from app.storage.neo4j_storage import Neo4jStorage
        storage = Neo4jStorage(uri="bolt://localhost:7687", user="neo4j", password="password")
        mock_emb_cls.assert_called_once_with()
        assert storage._embedding == mock_emb_cls.return_value


# ---------------------------------------------------------------------------
# BUG B Reproduction Tests: Persona JSON generation failures
# ---------------------------------------------------------------------------

def test_repro_bug_b_oasis_profile_generator_thinking_tokens_parsing():
    """BUG B Repro:
    When reasoning/thinking models (e.g. DeepSeek-R1 / Qwen3-Thinking) output <think>...</think>
    tags before the JSON payload, OasisProfileGenerator should strip the envelope cleanly.
    """
    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)
    generator.model_name = "qwen3-thinking"
    generator.base_url = "http://localhost:11434"
    generator.api_key = "test-key"
    generator.language = "de"
    generator._industry_quota_plan = MagicMock()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = (
        "<think>\n"
        "Need to create persona for Max.\n"
        "Age around 30, MBTI INTJ, male.\n"
        "</think>\n"
        "{\n"
        '  "bio": "Softwareentwickler aus Berlin",\n'
        '  "persona": "Detaillierte Persona von Max...",\n'
        '  "age": 32,\n'
        '  "gender": "male",\n'
        '  "mbti": "INTJ",\n'
        '  "country": "Germany",\n'
        '  "profession": "Softwareentwickler",\n'
        '  "interested_topics": ["Python", "KI"],\n'
        '  "voice_register": "neutral-de"\n'
        "}\n"
    )
    mock_response.choices[0].finish_reason = "stop"
    mock_client.chat.completions.create.return_value = mock_response
    generator.client = mock_client

    with patch.object(generator, "_is_individual_entity", return_value=True), \
         patch.object(generator, "_build_individual_persona_prompt", return_value="prompt"), \
         patch.object(generator, "_get_system_prompt", return_value="sys_prompt"):

        result = generator._generate_profile_with_llm(
            entity_name="Max",
            entity_type="person",
            entity_summary="Summary",
            entity_attributes={},
            context="Context"
        )

        assert result.get("bio") == "Softwareentwickler aus Berlin"
        assert result.get("age") == 32
        assert result.get("gender") == "male"
        assert result.get("mbti") == "INTJ"


def test_repro_bug_b_oasis_profile_generator_handles_none_or_empty_content():
    """BUG B Repro:
    When reasoning/thinking models or API proxies return None or empty string in message.content,
    or output thinking content, OasisProfileGenerator must handle it gracefully.
    """
    generator = OasisProfileGenerator.__new__(OasisProfileGenerator)
    generator.model_name = "thinking-model"
    generator.base_url = "http://localhost:11434"
    generator.api_key = "test-key"
    generator.language = "de"
    generator._industry_quota_plan = MagicMock()

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = None
    mock_response.choices[0].finish_reason = "stop"
    mock_client.chat.completions.create.return_value = mock_response
    generator.client = mock_client

    with patch.object(generator, "_is_individual_entity", return_value=True), \
         patch.object(generator, "_build_individual_persona_prompt", return_value="prompt"), \
         patch.object(generator, "_get_system_prompt", return_value="sys_prompt"), \
         patch.object(generator, "_generate_profile_rule_based", return_value={"bio": "Rule Bio", "persona": "Rule Persona", "age": 30, "gender": "male", "mbti": "INTJ"}):
        
        # Should gracefully fall back to rule-based without crashing
        result = generator._generate_profile_with_llm(
            entity_name="Max",
            entity_type="person",
            entity_summary="Summary",
            entity_attributes={},
            context="Context"
        )
        assert result["bio"] == "Rule Bio"
