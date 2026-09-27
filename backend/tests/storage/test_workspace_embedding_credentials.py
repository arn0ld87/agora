"""Tenant embeddings must never use the operator's embedding credential."""

from uuid import uuid4

import pytest

from app.services.embedding_configurations.runtime import ResolvedEmbeddingRoute
from app.storage.embedding_service import EmbeddingError, EmbeddingService


def _service(monkeypatch, workspace_id, key, base_url="https://api.openai.com/v1"):
    monkeypatch.setattr(
        EmbeddingService, "_workspace_credential_id", staticmethod(lambda: workspace_id)
    )
    monkeypatch.setattr(
        "app.services.embedding_configurations.runtime.resolve_active_embedding_route",
        lambda *, include_secret=True: ResolvedEmbeddingRoute(
            model="text-embedding-3-small",
            base_url=base_url,
            api_key="operator-key" if include_secret else None,
            configuration_id="embedding",
            dimensions=1536,
            provider_id="openai",
        ),
    )
    monkeypatch.setattr(
        "app.services.workspace_provider_credentials_store.WorkspaceProviderCredentialsStore",
        lambda: type(
            "Credentials", (),
            {"get_plaintext": lambda _self, current_id, provider_id: key
             if current_id == workspace_id and provider_id == "openai" else None},
        )(),
    )
    return EmbeddingService(
        model="text-embedding-3-small",
        base_url=base_url,
        api_key="operator-key",
    )


def test_tenant_embedding_uses_only_its_own_key(monkeypatch):
    workspace_id = uuid4()
    service = _service(monkeypatch, workspace_id, "workspace-key")

    assert service._request_headers()["Authorization"] == "Bearer workspace-key"


def test_missing_tenant_embedding_key_fails_closed(monkeypatch):
    service = _service(monkeypatch, uuid4(), None)

    with pytest.raises(EmbeddingError, match="Workspace embedding provider key"):
        service._request_headers()


def test_tenant_embedding_with_non_canonical_base_url_fails_closed(monkeypatch):
    """A workspace key must never be sent to a non-canonical operator endpoint.

    ``resolve_active_embedding_route`` reports ``provider_id="openai"``, but the
    operator has configured a custom (non-default) ``base_url``. Sending the
    workspace's own OpenAI key there would leak it to an arbitrary endpoint.
    """
    workspace_id = uuid4()
    service = _service(
        monkeypatch,
        workspace_id,
        "workspace-key",
        base_url="https://attacker.example.com/v1",
    )

    with pytest.raises(EmbeddingError, match="canonical"):
        service._request_headers()


def test_tenant_embedding_does_not_reuse_operator_cache(monkeypatch):
    service = _service(monkeypatch, uuid4(), "workspace-key")
    service._cache["same text"] = [99.0]
    requests = []
    monkeypatch.setattr(
        service, "_request_embeddings",
        lambda texts: requests.append(texts) or [[1.0] for _ in texts],
    )

    assert service.embed("same text") == [1.0]
    assert requests == [["same text"]]
    assert service._cache["same text"] == [99.0]


def test_shared_operator_endpoint_uses_operator_embedding_key(monkeypatch):
    """#1688: ein per AGORA_SHARED_EMBEDDING_BASE_URL freigegebener
    Betreiber-Endpoint bekommt den Betreiber-Key, nie den Workspace-Key."""
    shared = "https://embed.tailnet.example/v1"
    monkeypatch.setenv("AGORA_SHARED_EMBEDDING_BASE_URL", shared + "/")
    service = _service(monkeypatch, uuid4(), "workspace-key", base_url=shared)

    assert service._request_headers()["Authorization"] == "Bearer operator-key"


def test_shared_endpoint_env_does_not_open_other_urls(monkeypatch):
    monkeypatch.setenv("AGORA_SHARED_EMBEDDING_BASE_URL", "https://embed.tailnet.example/v1")
    service = _service(
        monkeypatch, uuid4(), "workspace-key", base_url="https://attacker.example.com/v1"
    )

    with pytest.raises(EmbeddingError, match="canonical"):
        service._request_headers()
