from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pytest

from app.contracts.ai_provider_contract import AiModel, AiModelRef, ProviderConnection
from app.contracts.llm_profile_contract import LlmProfile
from app.contracts.llm_routing_contract import ResolvedRoute
from app.services.llm_routing_seed import (
    build_route_subprocess_env,
    build_runtime_llm_config,
    resolve_route_api_key,
    seed_run_stage_routing,
)
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.provider_connections.adapters import ProviderProbeResult
from app.services.runtime_run_config import RuntimeRunConfig


def _profile(profile_id: str, *, model: str = "gpt-4.1-mini") -> LlmProfile:
    """
    Create a test profile with fixed OpenAI connection details and timestamps.
    
    Parameters:
        profile_id (str): Identifier assigned to the profile.
        model (str): Model name assigned to the profile.
    
    Returns:
        LlmProfile: A profile populated with the specified identifier and model.
    """
    now = datetime.now(UTC)
    return LlmProfile(
        id=profile_id,
        name="Contract profile",
        provider="openai",
        base_url="https://api.openai.com/v1",
        model_name=model,
        api_key="must-not-enter-route",
        created_at=now,
        updated_at=now,
    )


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_seed_run_stage_routing_persists_stage_override(mock_run_dir, tmp_path):
    run_id = "run_seed_123"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    config = seed_run_stage_routing(
        run_id,
        "report_generation",
        llm_model_override="gpt-4o-mini",
        llm_runtime=RuntimeLlmConfig(
            provider="custom_openai",
            api_key="session-secret",
            base_url="https://gateway.example/v1",
        ),
    )

    loaded = RuntimeRunConfig(run_id).load_config()
    override = loaded.stage_overrides["report_generation"]
    assert config.stage_overrides["report_generation"].provider_id == "openai_compatible"
    assert override.provider_id == "openai_compatible"
    assert override.model == "gpt-4o-mini"
    assert override.provider_options == {"base_url": "https://gateway.example/v1"}


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_seed_run_stage_routing_keeps_server_default_without_override(mock_run_dir, tmp_path):
    run_id = "run_seed_default"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    # WorkspaceRoutingStore mocken — sonst leckt ein im Container persistierter
    # Default in den Test und überschreibt den Config-Default
    # (Smoke-Live 2026-05-15).
    from app.services.workspace_routing_store import get_workspace_routing_store
    get_workspace_routing_store().reset_for_tests()

    with patch("app.config.Config.LLM_BASE_URL", "https://api.openai.com/v1"), patch(
        "app.config.Config.LLM_MODEL_NAME", "gpt-4o"
    ):
        loaded = seed_run_stage_routing(
            run_id,
            "graph_build",
            llm_model_override=None,
            llm_runtime=RuntimeLlmConfig(),
        )

    assert loaded.global_default.provider_id == "openai"
    assert loaded.global_default.model == "gpt-4o"
    assert loaded.stage_overrides == {}


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_profile_id_expands_to_a_secret_free_stage_route(mock_run_dir, monkeypatch, tmp_path):
    run_id = "run_profile_only"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)
    profile_store = MagicMock()
    profile_store.get.return_value = _profile("profile-openai")
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [
        ProviderConnection(
            id="openai",
            provider_kind="openai",
            display_name="OpenAI",
            transport="http",
            auth_mode="api_key",
            base_url="https://api.openai.com/v1",
            secret_ref="openai",
        )
    ]
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_profiles_store",
        lambda: profile_store,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )

    config = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        llm_profile_id="profile-openai",
    )

    route = config.stage_overrides["graph_build"]
    assert route.provider_id == "openai"
    assert route.model == "gpt-4.1-mini"
    assert route.provider_options == {
        "base_url": "https://api.openai.com/v1",
        "secret_ref": "openai",
        "connection_only": True,
    }
    assert "api_key" not in route.model_dump(mode="json")
    profile_store.get.assert_called_once_with("profile-openai", include_api_key=False)


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_local_no_auth_profile_route_omits_secret_binding(mock_run_dir, monkeypatch, tmp_path):
    """No-Auth-Connections (auth_mode='none') dürfen NICHT per connection_only an ein
    nicht existentes Secret gebunden werden. Sonst liefert die strikte Auflösung
    ``None`` und der Run bricht mit 'LLM_API_KEY not configured' — lokales Ollama
    (Agoras Kern-Betriebsmodell) bliebe gebrochen. Die Auth-Semantik der
    ProviderConnection ist maßgeblich, nicht ein pauschales connection_only."""
    run_id = "run_local_noauth"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    now = datetime.now(UTC)
    profile = LlmProfile(
        id="profile-ollama",
        name="Local Ollama",
        provider="custom",
        base_url="http://localhost:11434",
        model_name="qwen3:8b",
        api_key=None,
        created_at=now,
        updated_at=now,
    )
    profile_store = MagicMock()
    profile_store.get.return_value = profile
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [
        ProviderConnection(
            id="ollama-local",
            provider_kind="ollama",
            display_name="Local Ollama",
            transport="http",
            auth_mode="none",
            base_url="http://localhost:11434",
            secret_ref=None,
        )
    ]
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_profiles_store",
        lambda: profile_store,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )

    config = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        llm_profile_id="profile-ollama",
    )

    route = config.stage_overrides["graph_build"]
    assert route.provider_id == "ollama-local"
    assert route.model == "qwen3:8b"
    assert route.provider_options == {"base_url": "http://localhost:11434"}
    assert "connection_only" not in route.provider_options
    assert "secret_ref" not in route.provider_options


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_explicit_runtime_route_wins_without_reading_the_profile(mock_run_dir, monkeypatch, tmp_path):
    run_id = "run_explicit_over_profile"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)
    profile_store = MagicMock()
    profile_store.get.side_effect = AssertionError("profile path must not be read")
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_profiles_store",
        lambda: profile_store,
        raising=False,
    )

    config = seed_run_stage_routing(
        run_id,
        "graph_build",
        llm_model_override="gpt-5-mini",
        llm_runtime=RuntimeLlmConfig(
            provider="openai",
            api_key="request-secret",
            base_url="https://api.openai.com/v1",
        ),
        llm_profile_id="profile-openai",
    )

    route = config.stage_overrides["graph_build"]
    assert route.provider_id == "openai"
    assert route.model == "gpt-5-mini"
    profile_store.get.assert_not_called()


@patch("app.services.secret_resolver.SecretResolver.get_api_key")
def test_resolve_route_api_key_prefers_runtime_secret_for_matching_provider(mock_get_api_key):
    route = ResolvedRoute(
        stage="report_generation",
        provider_id="google",
        model="gemini-1.5-pro",
        routing_version=3,
    )

    api_key = resolve_route_api_key(
        route,
        RuntimeLlmConfig(
            provider="google",
            api_key="runtime-google-key",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        ),
    )

    assert api_key == "runtime-google-key"
    mock_get_api_key.assert_not_called()


def test_build_route_subprocess_env_uses_resolved_route_values():
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=2,
        provider_options={"num_ctx": 32768},
    )

    env = build_route_subprocess_env(route, api_key="server-key", run_id="run_telemetry")

    assert env["AGORA_RUN_ID"] == "run_telemetry"
    assert env["LLM_API_KEY"] == "server-key"
    assert env["OPENAI_API_KEY"] == "server-key"
    assert env["LLM_BASE_URL"] == "https://api.openai.com/v1"
    assert env["LLM_MODEL_NAME"] == "gpt-4o-mini"


def test_build_route_subprocess_env_injects_google_api_key_for_gemini():
    """OASIS subprocess findet den Gemini-Key ohne .env, sobald der Workspace-
    Secrets-Store ihn liefert (`api_key_ref="GOOGLE_API_KEY"` aus Registry)."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="google",
        model="models/gemini-2.5-flash",
        base_url_sanitized="https://generativelanguage.googleapis.com/v1beta/openai/",
        routing_version=3,
    )

    env = build_route_subprocess_env(route, api_key="goog-server-key", run_id="run_gemini")

    assert env["GOOGLE_API_KEY"] == "goog-server-key"
    assert env["LLM_API_KEY"] == "goog-server-key"
    assert env["OPENAI_API_KEY"] == "goog-server-key"
    assert env["LLM_MODEL_NAME"] == "models/gemini-2.5-flash"


def test_build_route_subprocess_env_aliases_gemini_api_key_for_camel():
    """CAMELs GeminiModel im OASIS-Subprozess liest ``GEMINI_API_KEY``, nicht
    ``GOOGLE_API_KEY`` (die ``api_key_ref`` des Google-Providers). Ohne diesen
    Alias crasht der Subprozess trotz gesetztem Store-Key mit
    ``ValueError: Missing required API keys: GEMINI_API_KEY`` (Arbeitsprotokoll
    2026-07-18, Symptom 4). Damit bleibt der UI-Secrets-Store Single Source und
    ``.env`` wird fuer Gemini-Sims nicht mehr gebraucht."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="google",
        model="models/gemini-2.5-flash",
        base_url_sanitized="https://generativelanguage.googleapis.com/v1beta/openai/",
        routing_version=3,
    )

    env = build_route_subprocess_env(route, api_key="goog-server-key", run_id="run_gemini")

    assert env["GEMINI_API_KEY"] == "goog-server-key"


def test_build_route_subprocess_env_no_gemini_alias_for_non_google():
    """Nicht-Google-Routen bekommen KEINEN GEMINI_API_KEY-Alias untergeschoben."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="openai",
        model="gpt-4o-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=2,
    )

    env = build_route_subprocess_env(route, api_key="server-key")

    assert "GEMINI_API_KEY" not in env


def test_build_route_subprocess_env_injects_ollama_api_key_for_ollama_cloud():
    """
    Ensure Ollama Cloud routes receive their API key in the subprocess environment.
    
    Returns:
        None
    """
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="ollama_cloud",
        model="qwen3-coder-next:cloud",
        base_url_sanitized="https://ollama.com/v1",
        routing_version=1,
    )

    env = build_route_subprocess_env(route, api_key="ollama-cloud-key")

    assert env["OLLAMA_API_KEY"] == "ollama-cloud-key"
    assert env["LLM_API_KEY"] == "ollama-cloud-key"


def test_build_route_subprocess_env_does_not_set_provider_key_without_api_key():
    """Ohne resolved api_key bleiben sowohl generische als auch provider-
    spezifische Env-Vars leer — die Subprozesse müssen dann selbst entscheiden,
    ob sie aus dem Parent-Env (`.env`-Fallback) ziehen."""
    route = ResolvedRoute(
        stage="simulation_rounds",
        provider_id="google",
        model="models/gemini-2.5-flash",
        routing_version=1,
    )

    env = build_route_subprocess_env(route, api_key=None)

    assert "GOOGLE_API_KEY" not in env
    assert "LLM_API_KEY" not in env
    assert "OPENAI_API_KEY" not in env


def _mismatch_connection() -> ProviderConnection:
    return ProviderConnection(
        id="conn-mismatch",
        provider_kind="openai_compatible",
        display_name="Custom Gateway",
        transport="http",
        auth_mode="api_key",
        base_url="https://gateway.example/v1",
        secret_ref="conn-mismatch",
        enabled=True,
    )


def _stub_probe(monkeypatch, connection_store, result: ProviderProbeResult) -> MagicMock:
    """Patcht den einzigen Model-Discovery-Pfad (ProviderConnectionService.probe)
    im ``ai_model_ref``-Zweig von ``llm_routing_seed`` — kein neuer Katalog, keine
    lokale Heuristik, nur der bestehende Probe-Pfad wird auf ein deterministisches
    Ergebnis gestellt."""
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store",
        lambda: MagicMock(),
        raising=False,
    )
    probe_service = MagicMock()
    probe_service.probe.return_value = result
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionService",
        lambda **kwargs: probe_service,
    )
    return probe_service


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_model_mismatch_is_rejected(mock_run_dir, monkeypatch, tmp_path):
    """Issue #819: model_id gehört zu einem anderen Provider als die gewählte
    provider_connection_id → ValueError (→ HTTP 400 in report.py), klar
    unterscheidbar von einem Discovery-Fehlschlag."""
    run_id = "run_model_mismatch"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    connection = _mismatch_connection()
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    _stub_probe(
        monkeypatch,
        connection_store,
        ProviderProbeResult(
            status="available",
            status_message=None,
            models=(
                AiModel(
                    provider_connection_id=connection.id,
                    model_id="some-other-model",
                    display_name="some-other-model",
                    source="live",
                    status="available",
                    local_or_cloud="cloud",
                ),
            ),
        ),
    )

    ref = AiModelRef(
        provider_connection_id="conn-mismatch", model_id="gpt-4o-mini", source="explicit"
    )
    with pytest.raises(ValueError, match="gehört nicht zur"):
        seed_run_stage_routing(
            run_id,
            "report_generation",
            llm_model_override=None,
            llm_runtime=RuntimeLlmConfig(),
            ai_model_ref=ref,
        )


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_discovery_failure_is_rejected_distinctly(mock_run_dir, monkeypatch, tmp_path):
    """Issue #819: schlägt die Live-Discovery fehl (Provider nicht erreichbar/
    ungültige Credentials), muss die Fehlermeldung das klarstellen — nicht
    fälschlich behaupten, das Modell gehöre nicht zur Connection."""
    run_id = "run_discovery_failure"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    connection = _mismatch_connection()
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    _stub_probe(
        monkeypatch,
        connection_store,
        ProviderProbeResult(
            status="invalid_credentials", status_message="Anmeldung abgelehnt"
        ),
    )

    ref = AiModelRef(
        provider_connection_id="conn-mismatch", model_id="gpt-4o-mini", source="explicit"
    )
    with pytest.raises(ValueError, match="nicht abrufbar") as exc_info:
        seed_run_stage_routing(
            run_id,
            "report_generation",
            llm_model_override=None,
            llm_runtime=RuntimeLlmConfig(),
            ai_model_ref=ref,
        )
    assert "gehört nicht zur" not in str(exc_info.value)


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_valid_model_passes_discovery_check(mock_run_dir, monkeypatch, tmp_path):
    """Regressionsschutz für #817/#818: eine gültige (Connection, Modell)-
    Kombination bleibt weiterhin erlaubt und wird 1:1 zur gelockten Route."""
    run_id = "run_model_valid"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    connection = _mismatch_connection()
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    _stub_probe(
        monkeypatch,
        connection_store,
        ProviderProbeResult(
            status="available",
            status_message=None,
            models=(
                AiModel(
                    provider_connection_id=connection.id,
                    model_id="gpt-4o-mini",
                    display_name="gpt-4o-mini",
                    source="live",
                    status="available",
                    local_or_cloud="cloud",
                ),
            ),
        ),
    )

    ref = AiModelRef(
        provider_connection_id="conn-mismatch", model_id="gpt-4o-mini", source="explicit"
    )
    config = seed_run_stage_routing(
        run_id,
        "report_generation",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        ai_model_ref=ref,
    )

    route = config.stage_overrides["report_generation"]
    assert route.provider_id == "conn-mismatch"
    assert route.model == "gpt-4o-mini"


def _seed_with_ref(mock_run_dir, monkeypatch, tmp_path, run_id: str, ref: AiModelRef):
    """Seed-Aufruf mit gestellter Discovery — Kern von #901."""
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    connection = _mismatch_connection()
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    _stub_probe(
        monkeypatch,
        connection_store,
        ProviderProbeResult(
            status="available",
            status_message=None,
            models=(
                AiModel(
                    provider_connection_id=connection.id,
                    model_id="gpt-4o-mini",
                    display_name="gpt-4o-mini",
                    source="live",
                    status="available",
                    local_or_cloud="cloud",
                ),
            ),
        ),
    )

    return seed_run_stage_routing(
        run_id,
        "report_generation",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        ai_model_ref=ref,
    )


@pytest.mark.parametrize(
    "ref_source",
    ["stage-override", "run-override", "project-default", "workspace-default", "explicit"],
)
@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_source_landet_im_stage_route_snapshot(
    mock_run_dir, monkeypatch, tmp_path, ref_source
):
    """Issue #901 — AK 1: die geseedete Route trägt die ursprüngliche Herkunft.

    Vorher verwarf ``seed_run_stage_routing`` ``AiModelRef.source``, weil
    ``StageLLMRoute`` kein Feld dafür hatte; ``ai_route_from_stage_route``
    schrieb beim Zurückprojizieren hart ``source="legacy"``. Jede explizite
    UI-Modellwahl war danach im Snapshot und im ``AiRouteAudit`` von einem
    Legacy-Fallback ununterscheidbar.
    """
    ref = AiModelRef(
        provider_connection_id="conn-mismatch",
        model_id="gpt-4o-mini",
        source=ref_source,
    )
    config = _seed_with_ref(
        mock_run_dir, monkeypatch, tmp_path, f"run_src_{ref_source.replace('-', '_')}", ref
    )

    route = config.stage_overrides["report_generation"]
    assert route.ai_model_ref_source == ref_source, (
        "Die Herkunft der Routing-Entscheidung darf beim Seeden nicht verloren gehen"
    )
    assert route.ai_model_ref_source != "legacy"


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_fallback_reicht_den_grund_mit_durch(
    mock_run_dir, monkeypatch, tmp_path
):
    """``fallback`` bildet auf ``provider_fallback`` ab, das einen Grund verlangt.

    Ohne Durchreichen scheiterte erst die spätere AiRoute-Projektion — an einer
    Stelle ohne Bezug zur Ursache.
    """
    ref = AiModelRef(
        provider_connection_id="conn-mismatch",
        model_id="gpt-4o-mini",
        source="fallback",
        fallback_reason="Primaermodell nicht erreichbar",
    )
    config = _seed_with_ref(mock_run_dir, monkeypatch, tmp_path, "run_src_fallback", ref)

    route = config.stage_overrides["report_generation"]
    assert route.ai_model_ref_source == "fallback"
    assert route.fallback_reason == "Primaermodell nicht erreichbar"

    # Die Projektion muss damit ohne ValidationError durchlaufen.
    from app.contracts.ai_provider_contract import ai_route_from_stage_route

    ai_route = ai_route_from_stage_route(route)
    assert ai_route.source == "provider_fallback"
    assert ai_route.fallback_reason == "Primaermodell nicht erreichbar"


@pytest.mark.parametrize("missing_reason", [None, "", "   "])
@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_fallback_ohne_grund_laesst_den_seed_nicht_scheitern(
    mock_run_dir, monkeypatch, tmp_path, missing_reason
):
    """``source="fallback"`` ohne Grund ist über die UI real erreichbar.

    ``AiModelPicker.vue`` emittiert bei einer unbekannten Item-ID
    ``source: 'fallback'``, ohne einen Grund ableiten zu können, und
    ``AiModelRefPayload`` überträgt ``fallback_reason`` gar nicht erst.
    ``provider_fallback`` verlangt aber einen nicht-leeren Grund.

    Der Seed darf daran nicht scheitern: ``seed_run_stage_routing`` läuft in
    ``api/simulation_run.py`` **nach** ``run_registry.create_run`` und ist dort
    nicht in ein ``try/except`` gefasst — eine Exception hinterließe einen
    verwaisten ``pending``-Run und antwortete mit 500.

    Die Lücke wird deterministisch aufgefüllt, nicht kaschiert: der Ersatzwert
    ist als solcher erkennbar und im Audit von einem echten Grund
    unterscheidbar.
    """
    ref = AiModelRef(
        provider_connection_id="conn-mismatch",
        model_id="gpt-4o-mini",
        source="fallback",
        fallback_reason=missing_reason,
    )
    config = _seed_with_ref(
        mock_run_dir, monkeypatch, tmp_path, f"run_fb_{len(missing_reason or '')}", ref
    )

    route = config.stage_overrides["report_generation"]
    assert route.ai_model_ref_source == "fallback"
    assert route.fallback_reason == "unspecified_fallback"

    # Entscheidend ist nicht der Ersatzwert, sondern dass die Projektion
    # durchläuft — genau dort schlug die Kombination vorher fehl.
    from app.contracts.ai_provider_contract import ai_route_from_stage_route

    ai_route = ai_route_from_stage_route(route)
    assert ai_route.source == "provider_fallback"
    assert ai_route.fallback_reason == "unspecified_fallback"


def test_build_runtime_llm_config_maps_resolved_route_for_legacy_callers():
    route = ResolvedRoute(
        stage="persona_generation",
        provider_id="ollama_cloud",
        model="qwen2.5:32b",
        base_url_sanitized="http://localhost:11434/v1",
        routing_version=4,
    )

    cfg = build_runtime_llm_config(route, api_key="local-key")

    assert cfg.provider == "custom_openai"
    assert cfg.api_key == "local-key"
    assert cfg.base_url == "http://localhost:11434/v1"


# ---------------------------------------------------------------------------
# OASIS-Sim-Start: eine ausgewählte MiniMax-ProviderConnection muss Modell,
# Base-URL und gebundenen Key als zusammengehörige Einheit bis in den
# Subprozess-Env durchreichen (Root Cause „404 model MiniMax-M3 not found").
# ---------------------------------------------------------------------------


def _minimax_connection() -> ProviderConnection:
    return ProviderConnection(
        id="conn-minimax",
        provider_kind="openai_compatible",
        display_name="MiniMax",
        transport="http",
        auth_mode="api_key",
        base_url="https://api.minimax.io/v1",
        secret_ref="minimax-conn",
        enabled=True,
    )


def _stub_minimax_probe(monkeypatch, connection_store) -> MagicMock:
    """Stellt den Model-Discovery-Pfad für die MiniMax-Connection auf ein
    deterministisches ``available``-Ergebnis mit ``MiniMax-M3`` im Katalog."""
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: connection_store,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store",
        lambda: MagicMock(),
        raising=False,
    )
    probe_service = MagicMock()
    probe_service.probe.return_value = ProviderProbeResult(
        status="available",
        status_message=None,
        models=(
            AiModel(
                provider_connection_id="conn-minimax",
                model_id="MiniMax-M3",
                display_name="MiniMax-M3",
                source="live",
                status="available",
                local_or_cloud="cloud",
            ),
        ),
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionService",
        lambda **kwargs: probe_service,
    )
    return probe_service


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_minimax_route_reaches_subprocess_as_unit(
    mock_run_dir, monkeypatch, tmp_path
):
    """Regression für den OASIS-404: Eine ausgewählte MiniMax-ProviderConnection
    mit ``MiniMax-M3`` muss Modell, Base-URL und den gebundenen Key derselben
    Connection gemeinsam bis in den OASIS-Subprozess-Env gelangen lassen — als
    eine Route, nicht als isolierte Env-Variablen.

    Vor dem Fix reichte ``start_simulation`` das ``ai_model_ref`` nicht an
    ``seed_run_stage_routing`` weiter; der Legacy-``llm_model``-Override
    produzierte eine Route ohne Base-URL und mit dem Default-Provider-Key →
    CAMEL traf den OpenAI-Default-Endpoint → 404 ``model MiniMax-M3 not found``.
    """
    from app.services.stage_model_router import StageModelRouter
    from app.services.workspace_routing_store import get_workspace_routing_store

    get_workspace_routing_store().reset_for_tests()

    run_id = "run_minimax_unit"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    connection = _minimax_connection()
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    _stub_minimax_probe(monkeypatch, connection_store)

    # Gebundener MiniMax-Key aus dem Secrets-Store (kein .env-Fallback).
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_bound_store_api_key",
        lambda secret_ref, *, secrets_store=None: (
            "mm-bound-secret" if secret_ref == "minimax-conn" else None
        ),
    )

    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    seed_run_stage_routing(
        run_id,
        "simulation_rounds",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        ai_model_ref=ref,
    )

    router = StageModelRouter(run_id)
    resolved_route = router.resolve("simulation_rounds")
    api_key = resolve_route_api_key(resolved_route, RuntimeLlmConfig())
    env = build_route_subprocess_env(resolved_route, api_key, run_id)

    # Modell, Base-URL und Key stammen atomar aus derselben MiniMax-Connection.
    assert env["LLM_MODEL_NAME"] == "MiniMax-M3"
    assert env["LLM_BASE_URL"] == "https://api.minimax.io/v1"
    assert env["LLM_API_KEY"] == "mm-bound-secret"
    assert env["OPENAI_API_KEY"] == "mm-bound-secret"
    # connection_only ist versiegelt — kein fremder Default-Provider-Key.
    assert resolved_route.provider_options.get("connection_only") is True
    assert resolved_route.provider_options.get("secret_ref") == "minimax-conn"


@patch("app.utils.artifact_locator.ArtifactLocator.run_dir")
def test_ai_model_ref_minimax_route_no_env_or_foreign_key_fallback(
    mock_run_dir, monkeypatch, tmp_path
):
    """Bei einer expliziten Cloud-ProviderConnection darf der Key-NICht aus
    ``Config.LLM_API_KEY`` oder dem Settings-DB-Key eines anderen Providers
    stammen. ``SecretResolver.get_api_key`` (der .env-/Store-Fallback-Pfad) darf
    für eine ``connection_only``-Route gar nicht erst angerufen werden."""
    from app.services.stage_model_router import StageModelRouter
    from app.services.workspace_routing_store import get_workspace_routing_store

    get_workspace_routing_store().reset_for_tests()

    run_id = "run_minimax_no_fallback"
    run_dir = tmp_path / "runs" / run_id
    run_dir.mkdir(parents=True)
    mock_run_dir.return_value = str(run_dir)

    connection = _minimax_connection()
    connection_store = MagicMock()
    connection_store.list_connections.return_value = [connection]
    _stub_minimax_probe(monkeypatch, connection_store)

    get_api_key_mock = MagicMock(return_value="foreign-default-key")
    monkeypatch.setattr(
        "app.services.secret_resolver.SecretResolver.get_api_key", get_api_key_mock
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_bound_store_api_key",
        lambda secret_ref, *, secrets_store=None: "mm-bound-secret",
    )

    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    seed_run_stage_routing(
        run_id,
        "simulation_rounds",
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        ai_model_ref=ref,
    )

    resolved_route = StageModelRouter(run_id).resolve("simulation_rounds")
    api_key = resolve_route_api_key(resolved_route, RuntimeLlmConfig())

    assert api_key == "mm-bound-secret"
    get_api_key_mock.assert_not_called()
