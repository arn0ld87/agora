"""Tenant embeddings must never use the operator's embedding credential."""

from uuid import uuid4

import pytest

from app.services.embedding_configurations.runtime import ResolvedEmbeddingRoute
from app.storage.embedding_service import EmbeddingError, EmbeddingService


def _service(monkeypatch, workspace_id, key):
    monkeypatch.setattr(
        EmbeddingService, "_workspace_credential_id", staticmethod(lambda: workspace_id)
    )
    monkeypatch.setattr(
        "app.services.embedding_configurations.runtime.resolve_active_embedding_route",
        lambda *, include_secret=True: ResolvedEmbeddingRoute(
            model="text-embedding-3-small",
            base_url="https://api.openai.com/v1",
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
        base_url="https://api.openai.com/v1",
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
