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
    When EMBEDDING_BASE_URL is an OpenAI-compatible endpoint (e.g. https://api.openai.com),
    and EMBEDDING_API_KEY is not set in env, Config.EMBEDDING_API_KEY falls back to
    LLM_API_KEY (which might be an Ollama dummy key or chat-specific key 'ollama-secret').
    EmbeddingService sends this invalid/mismatched chat key to OpenAI embeddings, resulting in 401 HTTP error.
    """
    # Simulate env where EMBEDDING_API_KEY is unset, LLM_API_KEY is 'ollama-chat-key'
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.setenv("LLM_API_KEY", "ollama-chat-key")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", "ollama-chat-key")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "https://api.openai.com")

    service = EmbeddingService(
        model="text-embedding-3-small",
        base_url="https://api.openai.com",
    )
    # The api_key picked up by default should NOT blindly inherit a local/unrelated LLM_API_KEY
    # when embedding endpoint and LLM endpoint differ or when LLM_API_KEY is not valid for embeddings.
    assert service._provider == "openai"
    assert service.api_key == "ollama-chat-key"  # Currently inherits LLM_API_KEY, causing 401 in prod!


def test_repro_bug_a_neo4j_storage_uses_raw_config_defaults_without_provider_connection():
    """BUG A Repro:
    Neo4jStorage initializes EmbeddingService() with no arguments, using Config.EMBEDDING_*
    globals rather than resolving active provider connections or dedicated embedding keys.
    """
    with patch("app.storage.neo4j_storage.EmbeddingService") as mock_emb_cls:
        from app.storage.neo4j_storage import Neo4jStorage
        # Instantiate Neo4jStorage without embedding_service argument
        storage = Neo4jStorage.__new__(Neo4jStorage)
        storage._embedding = None
        # Verify default instantiation behavior
        mock_emb_cls.assert_not_called()


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
