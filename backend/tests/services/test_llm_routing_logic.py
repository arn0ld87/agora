import pytest
from unittest.mock import patch
from app.services.runtime_run_config import RuntimeRunConfig, _detect_default_provider_id
from app.services.stage_model_router import StageModelRouter
from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute

@pytest.fixture
def temp_run_dir(tmp_path):
    run_id = "proj_testrun123"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)

    with patch("app.utils.artifact_locator.ArtifactLocator.run_dir", return_value=str(run_dir)):
        yield run_id

def test_runtime_run_config_persistence(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    global_default = StageLLMRoute(provider_id="ollama", model="qwen")
    config = RuntimeLlmRouting(global_default=global_default, routing_version=1)

    service.save_config(config)
    loaded = service.load_config()
    assert loaded.routing_version == 1
    assert loaded.global_default.provider_id == "ollama"

def test_stage_model_router_resolution(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    global_default = StageLLMRoute(provider_id="openai", model="gpt-4o")
    override_route = StageLLMRoute(provider_id="ollama", model="qwen")
    config = RuntimeLlmRouting(
        global_default=global_default,
        stage_overrides={"graph_build": override_route},
        routing_version=1
    )
    service.save_config(config)

    router = StageModelRouter(temp_run_dir)

    # Resolve default
    resolved_ingest = router.resolve("document_ingest")
    assert resolved_ingest.provider_id == "openai"

    # Resolve override
    resolved_graph = router.resolve("graph_build")
    assert resolved_graph.provider_id == "ollama"

def test_stage_model_router_snapshot_isolation(temp_run_dir):
    service = RuntimeRunConfig(temp_run_dir)
    router = StageModelRouter(temp_run_dir)

    global_default = StageLLMRoute(provider_id="openai", model="gpt-4o")
    config = RuntimeLlmRouting(global_default=global_default, routing_version=1)
    service.save_config(config)

    # 1. Resolve and lock stage
    resolved = router.resolve("document_ingest")
    router.lock_stage("document_ingest", resolved)
    canonical = service.load_ai_route_snapshot("document_ingest")
    assert canonical is not None
    assert canonical.provider_connection_id == "openai"
    assert canonical.model_id == "gpt-4o"
    assert canonical.source == "legacy"
    assert canonical.resolved_at is not None

    # 2. Update runtime config
    new_global_default = StageLLMRoute(provider_id="ollama", model="qwen")
    new_config = RuntimeLlmRouting(global_default=new_global_default, routing_version=2)
    service.save_config(new_config)

    # 3. Resolve again - should still return the locked version
    resolved_after = router.resolve("document_ingest")
    assert resolved_after.provider_id == "openai"
    assert resolved_after.routing_version == 1

    # 4. Resolve another stage - should return the new version
    resolved_other = router.resolve("graph_build")
    assert resolved_other.provider_id == "ollama"
    assert resolved_other.routing_version == 2


def test_resolve_from_canonical_snapshot_yields_iso8601_started_at(temp_run_dir):
    """Regression für PR-#700-Review-Finding #2: Wird nur ein kanonischer
    ``AiRoute``-Snapshot gespeichert (kein Legacy-Stage-Snapshot), muss
    ``StageModelRouter.resolve()`` über den Canonical-Adapter laufen und ein
    ``started_at`` als ISO-8601-String liefern — nicht als ``datetime``.
    ``ResolvedRoute.started_at`` ist ``str | None``; der Adapter muss
    ``resolved_at.isoformat()`` aufrufen."""
    from datetime import datetime, timezone
    from app.contracts.ai_provider_contract import AiRoute

    service = RuntimeRunConfig(temp_run_dir)
    resolved_at = datetime(2026, 7, 13, 11, 12, 41, tzinfo=timezone.utc)
    service.save_ai_route_snapshot(
        "graph_build",
        AiRoute(
            stage="graph_build",
            provider_connection_id="openai",
            model_id="gpt-4o",
            source="stage_override",
            resolved_at=resolved_at,
        ),
    )

    resolved = StageModelRouter(temp_run_dir).resolve("graph_build")

    assert resolved.provider_id == "openai"
    assert resolved.model == "gpt-4o"
    assert isinstance(resolved.started_at, str)
    assert resolved.started_at == resolved_at.isoformat()
    # ISO-8601 rundum-parsbar zum selben Instant.
    assert datetime.fromisoformat(resolved.started_at) == resolved_at


def test_detect_default_provider_id_matches_mainstream_hosts():
    """Mainstream hosts still resolve to the expected provider IDs now that
    detection is delegated to the SSoT (``app.llm.providers.registry.detect_provider``,
    mode="http") instead of a locally re-implemented heuristic."""
    assert _detect_default_provider_id("https://api.openai.com/v1", "gpt-4o") == "openai"
    assert _detect_default_provider_id(
        "https://generativelanguage.googleapis.com/v1beta/openai/", "gemini-1.5-pro"
    ) == "google"


def test_detect_default_provider_id_gemini_model_without_google_base_url_converges_to_compat():
    """Weakness #3 / SSoT convergence (audit B6/T4): the old inline heuristic
    forced ``PROVIDER_GOOGLE`` whenever ``"gemini" in model`` (an over-broad
    substring match that also caught e.g. ``"my-gemini-tune"``), *regardless of
    the base URL*. The http-mode SSoT (``detect_provider(..., mode="http")``)
    deliberately detects Gemini via the base URL only, so a Gemini-named model
    pointed at a non-Google base URL now resolves to ``openai_compatible``.

    This is an intentional behavior change, not a regression: this function
    feeds the backend runtime routing, which drives ``LLMClient`` — and the
    HTTP client would itself route such a config through the OpenAI-compatible
    path. Converging the fallback onto the same SSoT removes a latent
    fallback-vs-runtime divergence. Frozen here explicitly so the change is
    never silent (a Google base URL still wins, see the mainstream-hosts test).
    """
    assert _detect_default_provider_id("", "gemini-1.5-pro") == "openai_compatible"
    assert (
        _detect_default_provider_id("https://compat-gateway.example/v1", "gemini-1.5-pro")
        == "openai_compatible"
    )
    # The old substring rule also mis-fired on incidental "gemini" occurrences;
    # these likewise no longer force Google.
    assert _detect_default_provider_id("https://compat-gateway.example/v1", "my-gemini-tune") == (
        "openai_compatible"
    )


def test_detect_default_provider_id_delegates_ssot_substring_semantics():
    """The SSoT uses substring matching on the base URL (same semantics already
    shipped in production via ``LLMClient._detect_provider``), which is a
    deliberate trade-off vs. the old, stricter exact-hostname comparison: it
    trades resistance to look-alike/path-embedded strings for recognizing
    legitimate variants (see
    ``test_detect_default_provider_id_recognizes_subdomains_ssot_weakness_fix``
    below). ``_detect_default_provider_id`` now inherits this SSoT behavior
    verbatim rather than diverging from the single source of truth."""
    assert _detect_default_provider_id("https://evil-openai.com/v1", "custom-model") == "openai"
    assert _detect_default_provider_id(
        "https://proxy.example/generativelanguage.googleapis.com", "custom-model"
    ) == "google"


def test_detect_default_provider_id_recognizes_subdomains_ssot_weakness_fix():
    """Weakness #1 (audit B6/T4): the old heuristic only matched hostnames via
    exact equality (``hostname == "ollama.com"`` / ``"generativelanguage.googleapis.com"``
    / ``hostname in {"api.openai.com", "openai.com"}``), so legitimate
    subdomains/variants of these hosts silently fell back to
    ``openai_compatible``. Delegating to the SSoT fixes this."""
    assert _detect_default_provider_id("https://eu.api.openai.com/v1", "gpt-4o") == "openai"
    assert _detect_default_provider_id("https://www.ollama.com/v1", "some-model") == "ollama_cloud"


def test_detect_default_provider_id_recognizes_sized_cloud_tags_ssot_weakness_fix():
    """Weakness #2 (audit B6/T4): the old heuristic only matched the bare
    ``:cloud`` model tag suffix (``normalized_model.endswith(":cloud")``), so
    real Ollama Cloud size-prefixed tags (e.g. ``gpt-oss:20b-cloud``) were
    missed. Delegating to the SSoT's ``_is_ollama_cloud_tag`` fixes this."""
    assert _detect_default_provider_id(
        "https://custom-gateway.example/v1", "gpt-oss:20b-cloud"
    ) == "ollama_cloud"
    assert _detect_default_provider_id(
        "https://custom-gateway.example/v1", "qwen3-coder-next:cloud"
    ) == "ollama_cloud"
