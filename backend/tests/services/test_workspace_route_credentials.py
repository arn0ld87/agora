"""Workspace credentials are the sole secret source for tenant routes."""

from uuid import UUID
from unittest.mock import MagicMock

import pytest

from app.contracts.llm_routing_contract import ResolvedRoute
from app.llm.client import LLMClient
from app.llm.factory import resolve_connection_for_base_url
from app.services.llm_routing_seed import resolve_route_api_key
from app.services.llm_routing_seed import workspace_credential_id_for_run
from app.services.llm_routing_seed import workspace_credential_context_for_run
from app.services.sim.interview_direct import _default_client_factory
from app.services.simulation_config_generator import SimulationConfigGenerator
from app.services.simulation_config_agents import _generate_agent_configs_parallel


WORKSPACE_A = UUID("11111111-1111-4111-8111-111111111111")
WORKSPACE_B = UUID("22222222-2222-4222-8222-222222222222")


@pytest.fixture(autouse=True)
def _connection(monkeypatch):
    connection = MagicMock(
        id="openai",
        provider_kind="openai",
        enabled=True,
        transport="http",
        auth_mode="api_key",
        base_url="https://api.openai.com/v1",
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: MagicMock(list_connections=lambda: [connection]),
    )


def _route() -> ResolvedRoute:
    return ResolvedRoute(
        stage="report_generation",
        provider_id="openai",
        model="gpt-4.1-mini",
        base_url_sanitized="https://api.openai.com/v1",
        routing_version=1,
        provider_options={"connection_only": True, "secret_ref": "operator-secret"},
    )


@pytest.mark.parametrize(
    ("workspace_id", "expected"),
    [(WORKSPACE_A, "workspace-a-key"), (WORKSPACE_B, "workspace-b-key")],
)
def test_route_uses_only_own_workspace_key(monkeypatch, workspace_id, expected):
    store = MagicMock()
    store.get_plaintext.side_effect = lambda owner, _provider: {
        WORKSPACE_A: "workspace-a-key",
        WORKSPACE_B: "workspace-b-key",
    }[owner]
    monkeypatch.setattr(
        "app.services.llm_routing_seed.WorkspaceProviderCredentialsStore", lambda: store
    )
    operator = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store", operator
    )

    assert resolve_route_api_key(_route(), workspace_id=workspace_id) == expected
    store.get_plaintext.assert_called_once_with(workspace_id, "openai")
    operator.assert_not_called()


def test_missing_workspace_key_never_uses_operator_or_runtime(monkeypatch):
    store = MagicMock()
    store.get_plaintext.return_value = None
    monkeypatch.setattr(
        "app.services.llm_routing_seed.WorkspaceProviderCredentialsStore", lambda: store
    )
    operator = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.get_llm_provider_secrets_store", operator
    )

    assert resolve_route_api_key(_route(), workspace_id=WORKSPACE_A) is None
    operator.assert_not_called()


def test_workspace_key_rejected_when_connection_base_url_overridden(monkeypatch):
    """Finding M3 (#1688): a connection whose ``base_url`` was edited away
    from the provider's registry default must never receive a workspace
    key, even if the route itself still points at that (now-mismatched)
    connection — mirrors the gate ``list_workspace_available_models``
    already applies when surfacing routable connections."""
    connection = MagicMock(
        id="openai",
        provider_kind="openai",
        enabled=True,
        transport="http",
        auth_mode="api_key",
        base_url="https://attacker.example/v1",
    )
    monkeypatch.setattr(
        "app.services.llm_routing_seed.ProviderConnectionStore",
        lambda: MagicMock(list_connections=lambda: [connection]),
    )
    store = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.WorkspaceProviderCredentialsStore", lambda: store
    )
    route = _route().model_copy(update={"base_url_sanitized": "https://attacker.example/v1"})

    with pytest.raises(ValueError, match="endpoint does not match"):
        resolve_route_api_key(route, workspace_id=WORKSPACE_A)
    store.get_plaintext.assert_not_called()


def test_workspace_key_is_not_sent_to_overridden_endpoint(monkeypatch):
    store = MagicMock()
    monkeypatch.setattr(
        "app.services.llm_routing_seed.WorkspaceProviderCredentialsStore", lambda: store
    )
    route = _route().model_copy(update={"base_url_sanitized": "https://attacker.example/v1"})

    with pytest.raises(ValueError, match="endpoint does not match"):
        resolve_route_api_key(route, workspace_id=WORKSPACE_A)
    store.get_plaintext.assert_not_called()


def test_client_connection_only_uses_workspace_even_with_override(monkeypatch):
    store = MagicMock()
    store.get_plaintext.return_value = "workspace-key"
    monkeypatch.setattr(
        "app.services.workspace_provider_credentials_store.WorkspaceProviderCredentialsStore.get_plaintext",
        lambda _self, owner, provider: store.get_plaintext(owner, provider),
    )
    captured = {}
    monkeypatch.setattr(LLMClient, "__init__", lambda _self, **kw: captured.update(kw))

    LLMClient.from_route(
        _route(), workspace_id=WORKSPACE_A, api_key_override="operator-key"
    )

    assert captured["api_key"] == "workspace-key"
    assert captured["use_active_config"] is False
    assert captured["allow_api_key_fallback"] is False
    store.get_plaintext.assert_called_once_with(WORKSPACE_A, "openai")


def test_missing_client_workspace_key_cannot_use_operator_config(monkeypatch):
    monkeypatch.setattr(
        "app.services.workspace_provider_credentials_store.WorkspaceProviderCredentialsStore.get_plaintext",
        lambda _self, _owner, _provider: None,
    )
    monkeypatch.setattr("app.config.Config.LLM_API_KEY", "operator-key")

    with pytest.raises(ValueError, match="LLM_API_KEY"):
        LLMClient.from_route(_route(), workspace_id=WORKSPACE_A)


def test_persisted_run_workspace_is_checked_against_database_owner(monkeypatch):
    run = {
        "metadata": {
            "credential_scope": "workspace",
            "credential_workspace_id": str(WORKSPACE_A),
        }
    }
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(get=lambda _id: MagicMock(to_manifest=lambda: run)),
    )
    checked = []

    def reference_state(kind, identifier, workspace_id):
        checked.append((kind, identifier, workspace_id))
        return "own"

    monkeypatch.setattr(
        "app.infrastructure.postgres.workspace_scope.reference_state", reference_state
    )

    assert workspace_credential_id_for_run("run-a") == WORKSPACE_A
    assert checked == [("run_id", "run-a", WORKSPACE_A)]

    monkeypatch.setattr(
        "app.infrastructure.postgres.workspace_scope.reference_state",
        lambda *_args: "foreign",
    )
    with pytest.raises(ValueError, match="persisted owner"):
        workspace_credential_id_for_run("run-a")


def test_direct_interview_missing_workspace_key_does_not_use_global_config(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_routing_seed.workspace_credential_id_for_run",
        lambda _run_id: WORKSPACE_A,
    )
    monkeypatch.setattr(
        "app.llm.factory.resolve_connection_for_base_url",
        lambda _base_url, *, workspace_id: (None, "openai", "api_key"),
    )
    operator_client = MagicMock(side_effect=AssertionError("global fallback"))
    monkeypatch.setattr("app.llm.client.LLMClient", operator_client)

    factory = _default_client_factory(
        10.0,
        {"llm_model": "gpt-4.1-mini", "llm_base_url": "https://api.openai.com/v1"},
    )

    with pytest.raises(ValueError, match="Workspace provider credential"):
        factory()
    operator_client.assert_not_called()


def test_profile_connection_lookup_uses_workspace_secret_only(monkeypatch):
    connection = MagicMock(
        id="openai",
        enabled=True,
        transport="http",
        auth_mode="api_key",
        base_url="https://api.openai.com/v1",
    )
    monkeypatch.setattr(
        "app.services.provider_connection_store.ProviderConnectionStore",
        lambda: MagicMock(list_connections=lambda: [connection]),
    )
    workspace_store = MagicMock()
    workspace_store.get_plaintext.return_value = "workspace-a-key"
    monkeypatch.setattr(
        "app.services.workspace_provider_credentials_store.WorkspaceProviderCredentialsStore.get_plaintext",
        lambda _self, owner, provider: workspace_store.get_plaintext(owner, provider),
    )
    operator_store = MagicMock(side_effect=AssertionError("operator key read"))
    monkeypatch.setattr(
        "app.services.llm_provider_secrets_store.get_llm_provider_secrets_store",
        operator_store,
    )

    result = resolve_connection_for_base_url(
        "https://api.openai.com/v1", workspace_id=WORKSPACE_A
    )

    assert result == ("workspace-a-key", "openai", "api_key")
    workspace_store.get_plaintext.assert_called_once_with(WORKSPACE_A, "openai")
    operator_store.assert_not_called()


def test_background_credential_context_is_scoped_and_reset(monkeypatch):
    run = {
        "metadata": {
            "credential_scope": "workspace",
            "credential_workspace_id": str(WORKSPACE_B),
        }
    }
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(get=lambda _id: MagicMock(to_manifest=lambda: run)),
    )
    monkeypatch.setattr(
        "app.infrastructure.postgres.workspace_scope.reference_state", lambda *_args: "own"
    )

    with workspace_credential_context_for_run("run-b"):
        assert workspace_credential_id_for_run(None) == WORKSPACE_B
    assert workspace_credential_id_for_run(None) is None


def test_simulation_config_rejects_operator_key_fallback_for_workspace(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_routing_seed.workspace_credential_id_for_run",
        lambda _run_id: WORKSPACE_A,
    )
    monkeypatch.setattr("app.config.Config.LLM_API_KEY", "operator-key")
    monkeypatch.setattr("app.config.Config.LLM_BASE_URL", "https://api.openai.com/v1")

    with pytest.raises(ValueError, match="Workspace simulation config"):
        SimulationConfigGenerator(
            api_key=None,
            base_url="https://api.openai.com/v1",
            model_name="gpt-4.1-mini",
        )


def test_direct_client_rejects_global_fallback_in_workspace_context(monkeypatch):
    monkeypatch.setattr(
        "app.services.llm_routing_seed.workspace_credential_id_for_run",
        lambda _run_id: WORKSPACE_A,
    )
    monkeypatch.setattr("app.config.Config.LLM_API_KEY", "operator-key")

    with pytest.raises(ValueError, match="Workspace LLM route"):
        LLMClient(model="gpt-4.1-mini", base_url="https://api.openai.com/v1")


def test_parallel_config_batches_keep_workspace_credential_context(monkeypatch):
    run = {
        "metadata": {
            "credential_scope": "workspace",
            "credential_workspace_id": str(WORKSPACE_A),
        }
    }
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(get=lambda _id: MagicMock(to_manifest=lambda: run)),
    )
    monkeypatch.setattr(
        "app.infrastructure.postgres.workspace_scope.reference_state", lambda *_args: "own"
    )
    monkeypatch.setattr("gevent.monkey.is_module_patched", lambda _name: False)
    generator = MagicMock()
    generator.MAX_PARALLEL_AGENT_BATCHES = 2
    generator.llm_client.remaining_hard_call_budget.return_value = None
    generator._generate_agent_configs_batch.side_effect = (
        lambda **_kwargs: [workspace_credential_id_for_run(None)]
    )

    with workspace_credential_context_for_run("run-a"):
        result = _generate_agent_configs_parallel(
            generator, "context", [object(), object()], [(0, 1), (1, 2)], "requirement"
        )

    assert result == [WORKSPACE_A, WORKSPACE_A]


# ---------------------------------------------------------------------------
# Finding H1 (Security-Review 2026-09-26, #1688): fail-open credential scope
# ---------------------------------------------------------------------------


def test_bound_context_wins_even_when_run_id_is_passed_through(monkeypatch):
    """A background job that (correctly) passes its own ``run_id`` through
    on a nested lookup must still see its bound scope, even when that
    lookup's persisted-metadata read comes back empty (e.g. a transient
    repository read) — the previous implementation only consulted the bound
    contextvar when ``run_id`` was ``None`` and fell open to operator
    (``None``) in exactly this case."""
    run = {
        "metadata": {
            "credential_scope": "workspace",
            "credential_workspace_id": str(WORKSPACE_B),
        }
    }
    repo = MagicMock(get=lambda _id: MagicMock(to_manifest=lambda: run))
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository", lambda **_kwargs: repo
    )
    monkeypatch.setattr(
        "app.infrastructure.postgres.workspace_scope.reference_state", lambda *_args: "own"
    )

    with workspace_credential_context_for_run("run-b"):
        # A later, in-context lookup for the same run finds no record this
        # time — before H1, passing ``run_id`` here skipped the bound
        # contextvar entirely and would have resolved to operator (None).
        repo.get = lambda _id: None
        assert workspace_credential_id_for_run("run-b") == WORKSPACE_B


def test_bound_context_contradicting_persisted_scope_raises(monkeypatch):
    """A resolved workspace that disagrees with the bound one is a
    contradiction, not a silent override."""
    records = {
        "run-b": {
            "metadata": {
                "credential_scope": "workspace",
                "credential_workspace_id": str(WORKSPACE_A),
            }
        },
        "run-other": {
            "metadata": {
                "credential_scope": "workspace",
                "credential_workspace_id": str(WORKSPACE_B),
            }
        },
    }
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(
            get=lambda rid: MagicMock(to_manifest=lambda: records[rid])
        ),
    )
    monkeypatch.setattr(
        "app.infrastructure.postgres.workspace_scope.reference_state", lambda *_args: "own"
    )

    with workspace_credential_context_for_run("run-b"):
        with pytest.raises(ValueError, match="does not match resolved run workspace"):
            workspace_credential_id_for_run("run-other")


def test_demo_mode_denies_run_with_no_persisted_credential_scope(monkeypatch):
    """On a demo instance, a run whose creation path never attached a
    ``credential_scope`` must not fall back to operator credentials."""
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(get=lambda _id: MagicMock(to_manifest=lambda: {"metadata": {}})),
    )

    with pytest.raises(ValueError, match="no persisted credential scope"):
        workspace_credential_id_for_run("run-legacy")


def test_non_demo_instance_still_defaults_missing_scope_to_operator(monkeypatch):
    """Off a demo instance, a run with no persisted scope keeps the
    unchanged legacy operator default."""
    monkeypatch.delenv("AGORA_DEMO_MODE", raising=False)
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(get=lambda _id: MagicMock(to_manifest=lambda: {"metadata": {}})),
    )

    assert workspace_credential_id_for_run("run-legacy") is None


def test_operator_scoped_run_metadata_is_explicit_not_missing(monkeypatch):
    """An explicit ``"operator"`` scope (persisted by
    ``workspace_credential_metadata()`` for a master-token/legacy request)
    resolves to operator even in demo mode — only a genuinely *missing*
    scope is default-denied there (Finding H1)."""
    monkeypatch.setenv("AGORA_DEMO_MODE", "true")
    monkeypatch.setattr(
        "app.repositories.run_repository.get_run_repository",
        lambda **_kwargs: MagicMock(
            get=lambda _id: MagicMock(
                to_manifest=lambda: {"metadata": {"credential_scope": "operator"}}
            )
        ),
    )
    # An explicit operator scope resolves to operator (None) even in demo
    # mode — only a genuinely *missing* scope is default-denied there.
    assert workspace_credential_id_for_run("run-op") is None


def test_workspace_route_rejects_keyless_connection(monkeypatch):
    """Finding H1: a workspace run must not be routed to a keyless/local
    (``auth_mode="none"``) connection such as a local Ollama — only
    ``api_key`` connections carry a workspace-owned secret at all."""
    from app.services.llm_routing_seed import _bind_connection_secret

    monkeypatch.setattr(
        "app.services.llm_routing_seed.workspace_credential_id_for_run",
        lambda _run_id: WORKSPACE_A,
    )
    keyless_connection = MagicMock(id="ollama-local", auth_mode="none")

    with pytest.raises(ValueError, match="keyless/lokale"):
        _bind_connection_secret(keyless_connection, {})
