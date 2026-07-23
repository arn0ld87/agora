"""Reproduction tests for BUG A (Embedding 401), BUG B (Persona JSON failures)
and BUG C (stale per-run LLM stage-routing cache)."""

from pathlib import Path
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


# ---------------------------------------------------------------------------
# BUG C Reproduction Tests: stale per-run stage_override routing cache
# ---------------------------------------------------------------------------

@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_repro_bug_c_stale_provider_id_is_dropped_and_workspace_default_takes_over(
    mock_run_dir, monkeypatch, tmp_path
):
    """BUG C Repro:
    Wenn ``seed_run_stage_routing`` für einen Run aufgerufen wird, dessen
    ``runtime_llm_routing.json`` bereits persistiert ist, und der
    persistierte ``stage_overrides[stage_id].provider_id`` ist in der
    aktuellen ``LlmProviderRegistry`` nicht (mehr) bekannt — typisch nach
    einem Env-Wechsel (z. B. ``Ollama-Cloud-Proxy`` → ``MiniMax``) — muss
    der stale Eintrag verworfen und der Workspace-Default für die Stage
    übernommen werden. Sonst ruft der Stage-Router den alten Endpoint auf,
    der jetzt HTML statt JSON liefert (z. B. ``<title>Ollama</title>``),
    und NER loggt ``NER done: 0 entities, 0 relations`` ohne Fehler.
    """
    from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
    from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
    from app.services.llm_routing_seed import seed_run_stage_routing
    from app.services.llm_runtime import RuntimeLlmConfig
    from app.services.runtime_run_config import RuntimeRunConfig
    from app.services.workspace_routing_store import WorkspaceRoutingStore

    run_id = "run_stale_provider_id"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    stale = RuntimeLlmRouting(
        global_default=StageLLMRoute(
            provider_id="ollama_cloud_proxy",
            model="qwen3-coder:cloud",
            provider_options={"base_url": "https://stale.ollama-proxy.example/v1"},
        ),
        stage_overrides={
            "graph_build": StageLLMRoute(
                provider_id="ollama_cloud_proxy",
                model="qwen3-coder:cloud",
                provider_options={"base_url": "https://stale.ollama-proxy.example/v1"},
            ),
        },
        routing_version=1,
    )
    config_path = Path(str(run_dir)) / "runtime_llm_routing.json"
    config_path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    workspace_store = WorkspaceRoutingStore(data_dir=tmp_path)
    workspace_store.save(
        WorkspaceLlmRoutingDefaults(
            global_default=StageLLMRoute(
                provider_id="openai",
                model="gpt-4o-mini",
                provider_options={"base_url": "https://api.openai.com/v1"},
            ),
            stage_overrides={
                "graph_build": StageLLMRoute(
                    provider_id="openai",
                    model="gpt-4o-mini",
                    provider_options={"base_url": "https://api.openai.com/v1"},
                ),
            },
        )
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: workspace_store,
    )

    loaded = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
    )

    override = loaded.stage_overrides["graph_build"]
    assert override.provider_id == "openai"
    assert override.model == "gpt-4o-mini"
    assert override.provider_options == {
        "base_url": "https://api.openai.com/v1",
    }

    persisted = RuntimeRunConfig(run_id).load_config()
    assert persisted.stage_overrides["graph_build"].provider_id == "openai"


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_repro_bug_c_stale_base_url_dropped_when_provider_id_still_known(
    mock_run_dir, monkeypatch, tmp_path
):
    """BUG C Repro (Variante):
    ``provider_id`` ist in der aktuellen Registry noch bekannt, aber der
    persistierte ``base_url`` passt zu keiner aktivierten
    ``ProviderConnection`` mehr — typisch wenn die alte
    ``Ollama-Cloud``-Connection entfernt und eine ``MiniMax``-Connection
    angelegt wurde, der Run aber unter dem alten Endpoint persistiert war.
    Auch hier muss der stage_override verworfen und der Workspace-Default
    übernommen werden.
    """
    from app.contracts.ai_provider_contract import ProviderConnection
    from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
    from app.contracts.workspace_routing_contract import WorkspaceLlmRoutingDefaults
    from app.services.llm_routing_seed import seed_run_stage_routing
    from app.services.llm_runtime import RuntimeLlmConfig
    from app.services.workspace_routing_store import WorkspaceRoutingStore

    run_id = "run_stale_base_url"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    stale = RuntimeLlmRouting(
        global_default=StageLLMRoute(
            provider_id="ollama_cloud",
            model="qwen3-coder:cloud",
            provider_options={"base_url": "https://defunct.ollama-proxy.example/v1"},
        ),
        stage_overrides={
            "graph_build": StageLLMRoute(
                provider_id="ollama_cloud",
                model="qwen3-coder:cloud",
                provider_options={"base_url": "https://defunct.ollama-proxy.example/v1"},
            ),
        },
        routing_version=1,
    )
    config_path = Path(str(run_dir)) / "runtime_llm_routing.json"
    config_path.write_text(stale.model_dump_json(indent=2), encoding="utf-8")

    # Aktuell aktivierte Connection ist MiniMax mit anderer base_url.
    active_minimax = ProviderConnection(
        id="minimax",
        provider_kind="minimax",
        display_name="MiniMax",
        transport="http",
        auth_mode="api_key",
        base_url="https://api.minimax.io/v1",
        secret_ref=None,
        enabled=True,
    )
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [active_minimax]
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )

    workspace_store = WorkspaceRoutingStore(data_dir=tmp_path)
    workspace_store.save(
        WorkspaceLlmRoutingDefaults(
            global_default=StageLLMRoute(
                provider_id="minimax",
                model="MiniMax-M3",
                provider_options={"base_url": "https://api.minimax.io/v1"},
            ),
            stage_overrides={
                "graph_build": StageLLMRoute(
                    provider_id="minimax",
                    model="MiniMax-M3",
                    provider_options={"base_url": "https://api.minimax.io/v1"},
                ),
            },
        )
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: workspace_store,
    )

    loaded = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
    )

    override = loaded.stage_overrides["graph_build"]
    assert override.provider_id == "minimax"
    assert override.model == "MiniMax-M3"


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_repro_bug_c_valid_override_is_not_pruned(
    mock_run_dir, monkeypatch, tmp_path
):
    """BUG C Regressionsschutz:
    Ein stage_override mit bekannter provider_id und passender base_url
    (gültige ProviderConnection aktiv) bleibt unangetastet — sonst würde
    die Heuristik bewusst gesetzte Routen stillschweigend verwerfen.
    """
    from app.contracts.ai_provider_contract import ProviderConnection
    from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
    from app.services.llm_routing_seed import seed_run_stage_routing
    from app.services.llm_runtime import RuntimeLlmConfig

    run_id = "run_valid_override"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    active_ollama_cloud = ProviderConnection(
        id="ollama_cloud",
        provider_kind="ollama_cloud",
        display_name="Ollama Cloud",
        transport="http",
        auth_mode="api_key",
        base_url="https://ollama.com/v1",
        secret_ref=None,
        enabled=True,
    )
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [active_ollama_cloud]
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )

    valid = RuntimeLlmRouting(
        global_default=StageLLMRoute(
            provider_id="ollama_cloud",
            model="qwen3-coder:cloud",
            provider_options={"base_url": "https://ollama.com/v1"},
        ),
        stage_overrides={
            "graph_build": StageLLMRoute(
                provider_id="ollama_cloud",
                model="qwen3-coder:cloud",
                provider_options={"base_url": "https://ollama.com/v1"},
            ),
        },
        routing_version=1,
    )
    config_path = Path(str(run_dir)) / "runtime_llm_routing.json"
    config_path.write_text(valid.model_dump_json(indent=2), encoding="utf-8")

    # Workspace-Defaults dürfen den validen Override nicht überschreiben
    # (nur stale Overrides werden ersetzt).
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store",
        lambda: MagicMock(load=MagicMock(return_value=None)),
    )

    loaded = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
    )

    override = loaded.stage_overrides["graph_build"]
    assert override.provider_id == "ollama_cloud"
    assert override.model == "qwen3-coder:cloud"
    assert override.provider_options == {"base_url": "https://ollama.com/v1"}
