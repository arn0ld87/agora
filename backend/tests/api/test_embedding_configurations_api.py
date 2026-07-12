"""API-Tests für ``/api/api/llm/embedding/configurations`` (Onboarding Slice 4.2)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

import pytest
from flask import Flask

from app.api import llm_bp
from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationScope,
    EmbeddingConfigurationStatus,
    EmbeddingProviderKind,
)
from app.services.embedding_configurations.adapters import EmbeddingProbeResult


# ----------------------------------------------------------------------
# In-Memory-Stores + Service-Stubs
# ----------------------------------------------------------------------


class _FakeConfigurationStore:
    def __init__(self) -> None:
        self._items: dict[str, EmbeddingConfiguration] = {}

    def list_configurations(
        self, *, scope: Optional[EmbeddingConfigurationScope] = None
    ) -> list[EmbeddingConfiguration]:
        items = list(self._items.values())
        if scope is not None:
            items = [c for c in items if c.scope == scope]
        return items

    def get_active_global_configuration(self) -> EmbeddingConfiguration | None:
        for c in self._items.values():
            if c.scope == "global" and c.status == "active":
                return c
        return None

    def get_configuration(self, configuration_id: str) -> EmbeddingConfiguration | None:
        return self._items.get(configuration_id)

    def upsert_configuration(
        self,
        *,
        configuration_id: Optional[str],
        provider_connection_id: str,
        provider_kind: EmbeddingProviderKind,
        model_id: str,
        dimensions: int,
        scope: EmbeddingConfigurationScope,
        project_id: Optional[str],
        status: EmbeddingConfigurationStatus = "proposed",
        status_message: Optional[str] = None,
        last_validated_at: Optional[datetime] = None,
    ) -> EmbeddingConfiguration:
        cid = configuration_id or f"emb-test-{len(self._items) + 1}"
        now = datetime.now(timezone.utc)
        config = EmbeddingConfiguration(
            id=cid,
            provider_connection_id=provider_connection_id,
            provider_kind=provider_kind,
            model_id=model_id,
            dimensions=dimensions,
            scope=scope,
            project_id=project_id,
            index_version=1,
            status=status,
            status_message=status_message,
            created_at=now,
            updated_at=now,
            last_validated_at=last_validated_at,
        )
        self._items[cid] = config
        return config

    def update_configuration_status(
        self,
        configuration_id: str,
        *,
        status: EmbeddingConfigurationStatus,
        status_message: Optional[str] = None,
        last_validated_at: Optional[datetime] = None,
        index_version: Optional[int] = None,
    ) -> EmbeddingConfiguration:
        config = self._items[configuration_id]
        updated = config.model_copy(
            update={
                "status": status,
                "status_message": status_message,
                "updated_at": datetime.now(timezone.utc),
                "last_validated_at": last_validated_at,
                "index_version": (
                    index_version if index_version is not None else config.index_version
                ),
            }
        )
        self._items[configuration_id] = updated
        return updated

    def delete_configuration(self, configuration_id: str) -> bool:
        return self._items.pop(configuration_id, None) is not None


class _FakeConnectionStore:
    def __init__(self) -> None:
        self.connections: list = []

    def list_connections(self) -> list:
        return list(self.connections)


class _FakeSecretsStore:
    def get_plaintext(self, secret_ref: str) -> Optional[str]:
        return None


def _make_test_connection(connection_id: str, *, kind: str = "ollama"):
    """Baut eine minimale Provider-Connection fuer API-Tests."""
    from datetime import datetime, timezone
    from app.contracts.ai_provider_contract import (
        LocalOllamaBaseUrl,
        ProviderConnection,
    )

    now = datetime.now(timezone.utc)
    is_ollama = kind == "ollama"
    base_url: Optional[str] = "http://localhost:11434" if is_ollama else None
    if is_ollama and base_url is not None:
        base_url = LocalOllamaBaseUrl(base_url)
    return ProviderConnection(
        id=connection_id,
        provider_kind=kind,  # type: ignore[arg-type]
        display_name=kind,
        transport="local" if is_ollama else "http",
        auth_mode="none",
        base_url=base_url,
        enabled=True,
        status="unknown",
        secret_ref=None,
        capabilities={},
        created_at=now,
        updated_at=now,
    )


class _StubService:
    """Ersetzt ``EmbeddingConfigurationService`` mit deterministischem Verhalten."""

    def __init__(self, *, probe_status: str = "available", probe_dim: int = 768) -> None:
        self.probe_status = probe_status
        self.probe_dim = probe_dim
        self.probe_calls: list[str] = []
        self.activate_calls: list[str] = []

    def probe(
        self, configuration_id: str
    ) -> tuple[EmbeddingConfiguration, EmbeddingProbeResult]:
        self.probe_calls.append(configuration_id)
        from app.services.embedding_configuration_store import (  # local import for tests
            EmbeddingConfigurationStore,
        )
        # Reuse the in-memory store via app context, not possible here
        # without more wiring. We return a synthetic result and let the
        # caller (API) update the store.
        result = EmbeddingProbeResult(
            status=self.probe_status,  # type: ignore[arg-type]
            status_message=None,
            actual_dimensions=self.probe_dim if self.probe_status == "available" else None,
        )
        # We can't reach the store from here; return a placeholder config.
        placeholder = EmbeddingConfiguration(
            id=configuration_id,
            provider_connection_id="conn-1",
            provider_kind="ollama",
            model_id="nomic-embed-text",
            dimensions=self.probe_dim,
            scope="global",
            project_id=None,
            index_version=1,
            status="probed" if self.probe_status == "available" else "failed",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        return placeholder, result

    def activate(self, configuration_id: str) -> EmbeddingConfiguration:
        self.activate_calls.append(configuration_id)
        return EmbeddingConfiguration(
            id=configuration_id,
            provider_connection_id="conn-1",
            provider_kind="ollama",
            model_id="nomic-embed-text",
            dimensions=768,
            scope="global",
            project_id=None,
            index_version=1,
            status="active",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )


# ----------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------


@pytest.fixture
def fake_store() -> _FakeConfigurationStore:
    return _FakeConfigurationStore()


@pytest.fixture
def fake_connection_store() -> _FakeConnectionStore:
    return _FakeConnectionStore()


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
    fake_store: _FakeConfigurationStore,
    fake_connection_store: _FakeConnectionStore,
) -> object:
    import app.api.embedding_configurations as ec_api

    monkeypatch.setattr(ec_api, "get_embedding_configuration_store", lambda: fake_store)
    monkeypatch.setattr(ec_api, "ProviderConnectionStore", lambda: fake_connection_store)
    monkeypatch.setattr(ec_api, "get_llm_provider_secrets_store", lambda: _FakeSecretsStore())

    app = Flask(__name__)
    app.config["TESTING"] = True
    app.register_blueprint(ec_api.llm_bp, url_prefix="/api/llm")
    return app.test_client()


# ----------------------------------------------------------------------
# Routes
# ----------------------------------------------------------------------


def test_list_empty_returns_zero_configurations(client: object) -> None:
    response = client.get("/api/llm/embedding/configurations")  # type: ignore[attr-defined]
    assert response.status_code == 200
    body = response.get_json()
    assert body["success"] is True
    assert body["data"]["configurations"] == []


def test_list_filters_by_scope(client: object, fake_store: _FakeConfigurationStore) -> None:
    fake_store.upsert_configuration(
        configuration_id="emb-global",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    fake_store.upsert_configuration(
        configuration_id="emb-proj",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="project",
        project_id="proj-1",
    )
    response = client.get("/api/llm/embedding/configurations?scope=global")  # type: ignore[attr-defined]
    assert response.status_code == 200
    body = response.get_json()
    assert len(body["data"]["configurations"]) == 1
    assert body["data"]["configurations"][0]["id"] == "emb-global"


def test_list_with_invalid_scope_returns_400(client: object) -> None:
    response = client.get("/api/llm/embedding/configurations?scope=bogus")  # type: ignore[attr-defined]
    assert response.status_code == 400


def test_get_active_returns_legacy_when_store_is_empty(
    client: object, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Konfiguriere Config so, dass build_legacy_view() etwas liefert.
    from app.config import Config
    from app.services.embedding_configurations import legacy as legacy_mod

    monkeypatch.setattr(Config, "EMBEDDING_MODEL", "nomic-embed-text")
    monkeypatch.setattr(Config, "EMBEDDING_BASE_URL", "http://localhost:11434")
    monkeypatch.setattr(Config, "EMBEDDING_API_KEY", None)
    monkeypatch.setattr(Config, "VECTOR_DIM", 768)
    response = client.get("/api/llm/embedding/configurations/active")  # type: ignore[attr-defined]
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["source"] == "legacy"
    assert body["data"]["configuration"]["status"] == "proposed"


def test_get_active_returns_store_when_active_present(
    client: object, fake_store: _FakeConfigurationStore
) -> None:
    fake_store.upsert_configuration(
        configuration_id="emb-active",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
        status="active",
    )
    response = client.get("/api/llm/embedding/configurations/active")  # type: ignore[attr-defined]
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["source"] == "store"
    assert body["data"]["configuration"]["id"] == "emb-active"


def test_get_unknown_configuration_returns_404(client: object) -> None:
    response = client.get("/api/llm/embedding/configurations/emb-bogus")  # type: ignore[attr-defined]
    assert response.status_code == 404


def test_get_existing_configuration_returns_200(
    client: object, fake_store: _FakeConfigurationStore
) -> None:
    fake_store.upsert_configuration(
        configuration_id="emb-1",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    response = client.get("/api/llm/embedding/configurations/emb-1")  # type: ignore[attr-defined]
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["configuration"]["id"] == "emb-1"


def test_put_creates_new_configuration(
    client: object,
    fake_store: _FakeConfigurationStore,
    fake_connection_store: _FakeConnectionStore,
) -> None:
    fake_connection_store.connections.append(
        _make_test_connection("conn-1", kind="ollama")
    )
    response = client.put(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/new",
        json={
            "provider_connection_id": "conn-1",
            "provider_kind": "ollama",
            "model_id": "nomic-embed-text",
            "dimensions": 768,
            "scope": "global",
            "project_id": None,
        },
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["configuration"]["status"] == "proposed"
    assert body["data"]["configuration"]["id"].startswith("emb-")
    assert any(cid.startswith("emb-") for cid in fake_store._items)


def test_put_with_unknown_provider_connection_returns_404(
    client: object, fake_store: _FakeConfigurationStore
) -> None:
    response = client.put(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/new",
        json={
            "provider_connection_id": "conn-bogus",
            "provider_kind": "ollama",
            "model_id": "nomic-embed-text",
            "dimensions": 768,
            "scope": "global",
            "project_id": None,
        },
    )
    assert response.status_code == 404


def test_put_with_invalid_body_returns_400(client: object) -> None:
    response = client.put(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/new",
        json={"provider_kind": "ollama"},
    )
    assert response.status_code == 400


def test_delete_unknown_configuration_returns_404(client: object) -> None:
    response = client.delete(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/emb-bogus"
    )
    assert response.status_code == 404


def test_delete_existing_configuration_returns_success(
    client: object, fake_store: _FakeConfigurationStore
) -> None:
    fake_store.upsert_configuration(
        configuration_id="emb-1",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    response = client.delete(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/emb-1"
    )
    assert response.status_code == 200
    assert fake_store.get_configuration("emb-1") is None


def test_test_endpoint_invokes_service(
    client: object,
    fake_store: _FakeConfigurationStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store.upsert_configuration(
        configuration_id="emb-1",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    fake_store.update_configuration_status(
        "emb-1", status="probed", last_validated_at=datetime.now(timezone.utc)
    )
    import app.api.embedding_configurations as ec_api

    stub = _StubService(probe_status="available", probe_dim=768)
    monkeypatch.setattr(ec_api, "get_embedding_configuration_service", lambda: stub)

    response = client.post(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/emb-1/test"
    )
    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["probe"]["status"] == "available"
    assert body["data"]["probe"]["actual_dimensions"] == 768
    assert stub.probe_calls == ["emb-1"]


def test_activate_endpoint_invokes_service(
    client: object,
    fake_store: _FakeConfigurationStore,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_store.upsert_configuration(
        configuration_id="emb-1",
        provider_connection_id="conn-1",
        provider_kind="ollama",
        model_id="nomic-embed-text",
        dimensions=768,
        scope="global",
        project_id=None,
    )
    import app.api.embedding_configurations as ec_api

    stub = _StubService()
    monkeypatch.setattr(ec_api, "get_embedding_configuration_service", lambda: stub)

    response = client.post(  # type: ignore[attr-defined]
        "/api/llm/embedding/configurations/emb-1/activate"
    )
    assert response.status_code == 200
    assert stub.activate_calls == ["emb-1"]
