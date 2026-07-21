"""RED→GREEN: Der gelockte report_generation-Route-Snapshot muss den tatsächlich
erzeugten ``LLMClient`` beschreiben (Issue #817).

Belegt die Divergenz: bei gesetztem LLM-Profil beschrieb der gelockte
``report_generation``-Snapshot den Workspace-Default (z. B. Google), während der
ausgeführte ``LLMClient`` über ``build_client_from_profile`` ein anderes Profil
(z. B. MiniMax) nutzte.

Verglichen werden ausschließlich Provider-Connection-ID, Modell und Base-URL —
niemals Secret-Werte (nur Secret-Quelle/-Referenz).
"""
from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.contracts.ai_provider_contract import AiModel, AiModelRef, ProviderConnection
from app.contracts.llm_profile_contract import LlmProfile
from app.contracts.llm_routing_contract import RuntimeLlmRouting, StageLLMRoute
from app.services import report_generation as rg
from app.services.llm_runtime import RuntimeLlmConfig
from app.services.provider_connections.adapters import ProviderProbeResult
from app.services.runtime_run_config import RuntimeRunConfig
from app.utils.artifact_locator import ArtifactLocator

RUN_ID = "run_ssot_red"
_GOOGLE_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"
_MINIMAX_BASE = "https://api.minimaxi.chat/v1"


def _ensure_dir(path):
    path.mkdir(parents=True, exist_ok=True)
    return path


def _minimax_profile() -> LlmProfile:
    now = datetime.now(UTC)
    return LlmProfile(
        id="prof-minimax",
        name="MiniMax M3",
        provider="minimax",
        base_url=_MINIMAX_BASE,
        model_name="MiniMax-M3",
        api_key=None,
        created_at=now,
        updated_at=now,
    )


def _minimax_connection() -> ProviderConnection:
    return ProviderConnection(
        id="conn-minimax",
        provider_kind="minimax",
        display_name="MiniMax",
        transport="http",
        auth_mode="api_key",
        base_url=_MINIMAX_BASE,
        secret_ref="conn-minimax",
        enabled=True,
    )


def _minimax_probe_result() -> ProviderProbeResult:
    """Deterministisches Ergebnis für den in Issue #819 eingeführten
    Model-Discovery-Check (``ProviderConnectionService.probe``) — die MiniMax-
    Connection der Fixture bietet exakt das in den Tests referenzierte Modell
    ``MiniMax-M3`` an."""
    return ProviderProbeResult(
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


def _google_workspace_default() -> RuntimeLlmRouting:
    return RuntimeLlmRouting(
        global_default=StageLLMRoute(
            provider_id="google",
            model="gemini-1.5-pro",
            provider_options={"base_url": _GOOGLE_BASE},
        ),
        stage_overrides={},
    )


@pytest.fixture
def report_env(monkeypatch, tmp_path):
    """Verdrahtet ``start_generation`` mit In-Memory-Stubs und fängt den
    ``LLMClient`` ab, den ``GraphToolsService``/``ReportAgent`` bekommen."""
    run_root = tmp_path / "runs"
    run_root.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(
        ArtifactLocator,
        "run_dir",
        classmethod(lambda cls, run_id: str(_ensure_dir(run_root / run_id))),
    )

    profile_store = MagicMock()
    profile_store.get.return_value = _minimax_profile()

    connection_store = MagicMock()
    connection_store.list_connections.return_value = [_minimax_connection()]

    secrets_store = MagicMock()
    secrets_store.get_plaintext.return_value = "sk-test-not-a-real-secret"

    workspace_store = MagicMock()
    workspace_store.load.return_value = _google_workspace_default()

    monkeypatch.setattr(
        "app.services.llm_profiles_store.get_llm_profiles_store", lambda: profile_store
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_profiles_store",
        lambda: profile_store,
        raising=False,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore", lambda: connection_store
    )
    monkeypatch.setattr(
        "app.services.provider_connection_store.ProviderConnectionStore",
        lambda: connection_store,
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_workspace_routing_store", lambda: workspace_store
    )
    # Issue #819: der Model-Discovery-Check ruft ProviderConnectionService.probe
    # auf — hier deterministisch gestellt statt eines echten Netzwerk-Calls.
    probe_service = MagicMock()
    probe_service.probe.return_value = _minimax_probe_result()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionService", lambda **kwargs: probe_service
    )
    for target in (
        "app.services.llm_provider_secrets_store.get_llm_provider_secrets_store",
        "app.services.llm_routing_seed.get_llm_provider_secrets_store",
        "app.llm.client.get_llm_provider_secrets_store",
        "app.services.secret_resolver.get_llm_provider_secrets_store",
    ):
        monkeypatch.setattr(target, lambda: secrets_store, raising=False)

    state = SimpleNamespace(
        project_id="proj-1",
        graph_id="graph-1",
        source_simulation_id=None,
        root_simulation_id=None,
        branch_name=None,
        branch_depth=0,
    )
    sim_mgr = MagicMock()
    sim_mgr.get_simulation.return_value = state
    monkeypatch.setattr(rg, "SimulationManager", lambda: sim_mgr)

    project = SimpleNamespace(
        graph_id="graph-1", simulation_requirement="Requirement X", llm_profile_id=None
    )
    monkeypatch.setattr(rg.ProjectManager, "get_project", staticmethod(lambda pid: project))

    task_mgr = MagicMock()
    task_mgr.create_task.return_value = "task-1"
    monkeypatch.setattr(rg, "TaskManager", lambda: task_mgr)

    run_registry = MagicMock()
    run_registry.create_run.return_value = {"run_id": RUN_ID}
    monkeypatch.setattr(rg, "run_registry", run_registry)

    captured: dict[str, object] = {}

    class _FakeGraphTools:
        def __init__(self, *, storage=None, llm_client=None):
            captured["client"] = llm_client

    monkeypatch.setattr(rg, "GraphToolsService", _FakeGraphTools)
    monkeypatch.setattr(rg, "current_app", MagicMock())
    monkeypatch.setattr("app.jobs.enqueue", lambda *a, **k: "job-test")

    return SimpleNamespace(
        captured=captured,
        run_id=RUN_ID,
        profile_store=profile_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        workspace_store=workspace_store,
        run_registry=run_registry,
    )


def test_locked_route_snapshot_matches_actual_client_for_profile(report_env):
    """Der gelockte Snapshot und der ausgeführte Client beschreiben dieselbe Route."""
    result = rg.ReportGenerationService.start_generation(
        simulation_id="sim_abc",
        report_mode="balanced",
        force_regenerate=True,
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        llm_profile_id="prof-minimax",
    )
    assert result["status"] == "generating"

    client = report_env.captured.get("client")
    assert client is not None, "GraphToolsService erhielt keinen LLMClient"

    locked = RuntimeRunConfig(report_env.run_id).load_ai_route_snapshot("report_generation")
    assert locked is not None, "Kein gelockter report_generation-Snapshot"

    assert client.model == locked.model_id
    assert client.route_provider_id == locked.provider_connection_id
    assert (client.base_url or "").rstrip("/") == (
        locked.provider_options.get("base_url") or ""
    ).rstrip("/")


def _start(report_env, **overrides):
    kwargs = dict(
        simulation_id="sim_abc",
        report_mode="balanced",
        force_regenerate=True,
        llm_model_override=None,
        llm_runtime=RuntimeLlmConfig(),
        llm_profile_id=None,
        ai_model_ref=None,
    )
    kwargs.update(overrides)
    return rg.ReportGenerationService.start_generation(**kwargs)


def test_explicit_ai_model_ref_becomes_locked_route_and_client(report_env):
    """Slice A: die UI-gewählte AiModelRef wird 1:1 die gelockte Route und der Client."""
    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    result = _start(report_env, ai_model_ref=ref)
    assert result["status"] == "generating"

    client = report_env.captured["client"]
    locked = RuntimeRunConfig(report_env.run_id).load_ai_route_snapshot("report_generation")

    assert locked.provider_connection_id == "conn-minimax"
    assert locked.model_id == "MiniMax-M3"
    assert client.route_provider_id == locked.provider_connection_id
    assert client.model == locked.model_id
    # Secret nur über die Route-Referenz — der Wert wird nie verglichen.
    assert locked.provider_options.get("secret_ref") == "conn-minimax"
    assert locked.provider_options.get("connection_only") is True


def test_unknown_provider_connection_is_rejected(report_env):
    """Slice A: unbekannte Connection → harter Fehler, kein stiller Fallback."""
    report_env.connection_store.list_connections.return_value = []
    ref = AiModelRef(
        provider_connection_id="conn-ghost", model_id="ghost-1", source="explicit"
    )
    with pytest.raises(ValueError, match="nicht gefunden"):
        _start(report_env, ai_model_ref=ref)


def test_disabled_provider_connection_is_rejected(report_env):
    """Slice A: deaktivierte Connection → harter Fehler."""
    disabled = _minimax_connection().model_copy(update={"enabled": False})
    report_env.connection_store.list_connections.return_value = [disabled]
    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    with pytest.raises(ValueError, match="deaktiviert"):
        _start(report_env, ai_model_ref=ref)


def test_run_metadata_reflects_locked_route(report_env):
    """Run-Metadaten (Model-Attribution) stammen aus der gelockten Route, nicht
    aus den rohen Request-Feldern."""
    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    _start(report_env, ai_model_ref=ref)

    metadata_updates = [
        call.kwargs.get("metadata", {})
        for call in report_env.run_registry.update_run.call_args_list
    ]
    route_meta = next(m for m in metadata_updates if m.get("llm_model"))
    assert route_meta["llm_model"] == "MiniMax-M3"
    assert route_meta["llm_provider"]["provider_id"] == "conn-minimax"
    # Kein Secret in den Run-Metadaten.
    assert "api_key" not in route_meta["llm_provider"]


def test_cloud_connection_without_bound_secret_is_rejected(report_env):
    """Slice A: api_key-Connection ohne gebundenes secret_ref → klarer Fehler,
    kein stiller .env-/Server-Key-Fallback."""
    no_secret = _minimax_connection().model_copy(update={"secret_ref": None})
    report_env.connection_store.list_connections.return_value = [no_secret]
    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    with pytest.raises(ValueError, match="gebundenes Secret"):
        _start(report_env, ai_model_ref=ref)


def test_profile_path_cloud_connection_without_bound_secret_is_rejected(report_env):
    """Derselbe Reject wie über ``ai_model_ref`` muss auch über den
    ``llm_profile_id``-Pfad greifen — sonst umginge das Profil-Routing die
    Secret-Bindung (#817, CodeRabbit-Finding PR #820)."""
    no_secret = _minimax_connection().model_copy(update={"secret_ref": None})
    report_env.connection_store.list_connections.return_value = [no_secret]
    with pytest.raises(ValueError, match="gebundenes Secret"):
        _start(report_env, llm_profile_id="prof-minimax")


def test_no_secret_value_leaks_into_locked_snapshot(report_env):
    """Der gelockte Snapshot trägt nur die Secret-Referenz, nie den Klartext-Key."""
    ref = AiModelRef(
        provider_connection_id="conn-minimax", model_id="MiniMax-M3", source="explicit"
    )
    _start(report_env, ai_model_ref=ref)
    locked = RuntimeRunConfig(report_env.run_id).load_ai_route_snapshot("report_generation")
    serialized = locked.model_dump_json().lower()
    assert "sk-test-not-a-real-secret" not in serialized
    assert "api_key" not in serialized
