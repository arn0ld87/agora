"""Lifecycle-API für persistierte Provider-Verbindungen."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
from flask import Flask

from app.api import llm_bp
from app.contracts.ai_provider_contract import ProviderConnection
from app.services.provider_connections.adapters import ProviderProbeResult


SECRET = "test-provider-secret-must-never-leak"


def _connection(*, enabled: bool = True, status: str = "unknown") -> ProviderConnection:
    now = datetime.now(timezone.utc)
    return ProviderConnection(
        id="openai",
        provider_kind="openai",
        display_name="OpenAI",
        transport="http",
        auth_mode="api_key",
        base_url="https://api.openai.com/v1",
        enabled=enabled,
        status=status,
        secret_ref="openai",
        created_at=now,
        updated_at=now,
    )


class _Store:
    def __init__(self, connections: list[ProviderConnection] | None = None) -> None:
        self.connections = {connection.id: connection for connection in connections or []}

    def list_connections(self) -> list[ProviderConnection]:
        return list(self.connections.values())

    def upsert_connection(self, request):
        connection = _connection(enabled=request.enabled)
        connection = connection.model_copy(
            update={
                "display_name": request.display_name,
                "provider_kind": request.provider_kind,
                "base_url": request.base_url,
            }
        )
        self.connections[connection.id] = connection
        return connection

    def delete_connection(self, connection_id: str) -> bool:
        return self.connections.pop(connection_id, None) is not None

    def get_connection(self, connection_id: str) -> ProviderConnection | None:
        return self.connections.get(connection_id)


class _Service:
    def __init__(self, result: ProviderProbeResult) -> None:
        self.result = result
        self.probed: list[str] = []

    def probe(self, connection: ProviderConnection) -> ProviderProbeResult:
        self.probed.append(connection.id)
        return self.result


@pytest.fixture()
def api_client(monkeypatch):
    monkeypatch.delenv("AGORA_AUTH_TOKEN", raising=False)
    app = Flask(__name__)
    app.config["AGORA_AUTH_TOKEN"] = ""
    app.register_blueprint(llm_bp, url_prefix="/api/llm")
    return app.test_client()


@pytest.fixture()
def lifecycle(monkeypatch):
    store = _Store()
    service = _Service(
        ProviderProbeResult(
            status="available",
            status_message=None,
            models=(),
        )
    )
    monkeypatch.setattr(
        "app.api.llm_providers.get_provider_connection_store", lambda: store, raising=False
    )
    monkeypatch.setattr(
        "app.api.llm_providers.get_provider_connection_service", lambda: service, raising=False
    )
    return store, service


def test_list_provider_connections_returns_public_metadata(api_client, lifecycle):
    store, _ = lifecycle
    store.connections["openai"] = _connection()

    response = api_client.get("/api/llm/provider-connections")

    assert response.status_code == 200
    body = response.get_json()
    assert body["data"]["items"][0]["id"] == "openai"
    assert SECRET not in response.get_data(as_text=True)


def test_upsert_provider_connection_persists_key_without_leaking_it(api_client, lifecycle):
    response = api_client.put(
        "/api/llm/provider-connections/openai",
        json={
            "display_name": "OpenAI",
            "provider_kind": "openai",
            "base_url": "https://api.openai.com/v1",
            "api_key": SECRET,
        },
    )

    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["data"]["connection"]["id"] == "openai"
    assert SECRET not in response.get_data(as_text=True)


def test_upsert_rejects_connection_id_that_does_not_match_provider_kind(api_client, lifecycle):
    response = api_client.put(
        "/api/llm/provider-connections/anthropic",
        json={"display_name": "OpenAI", "provider_kind": "openai"},
    )

    assert response.status_code == 400


def test_upsert_rejects_invalid_public_base_url(api_client, lifecycle):
    response = api_client.put(
        "/api/llm/provider-connections/openai",
        json={
            "display_name": "OpenAI",
            "provider_kind": "openai",
            "base_url": "http://localhost:11434",
        },
    )

    assert response.status_code == 400


@pytest.mark.parametrize(
    ("method", "path", "json"),
    [
        (
            "put",
            "/api/llm/provider-connections/opencode_go",
            {
                "display_name": "OpenCode Go",
                "provider_kind": "opencode_go",
                "base_url": "https://api.example.test/v1",
                "api_key": SECRET,
            },
        ),
        ("post", "/api/llm/provider-connections/opencode_go/test", None),
        ("get", "/api/llm/provider-connections/opencode_go/models", None),
    ],
)
def test_canonical_unsupported_connection_routes_reject_before_store_or_service(
    api_client, monkeypatch, method: str, path: str, json: dict[str, str] | None
):
    store_calls = 0
    service_calls = 0

    def get_store():
        nonlocal store_calls
        store_calls += 1
        return _Store()

    def get_service():
        nonlocal service_calls
        service_calls += 1
        return _Service(ProviderProbeResult(status="available", status_message=None, models=()))

    monkeypatch.setattr("app.api.llm_providers.get_provider_connection_store", get_store)
    monkeypatch.setattr("app.api.llm_providers.get_provider_connection_service", get_service)

    response = getattr(api_client, method)(path, json=json)

    assert response.status_code == 409
    assert response.get_json()["code"] == "provider_unsupported"
    assert store_calls == 0
    assert service_calls == 0


def test_delete_provider_connection_returns_404_for_unknown_connection(api_client, lifecycle):
    response = api_client.delete("/api/llm/provider-connections/missing")

    assert response.status_code == 404


def test_test_provider_connection_uses_service_and_never_leaks_secret(api_client, lifecycle):
    store, service = lifecycle
    store.connections["openai"] = _connection()
    service.result = ProviderProbeResult(
        status="available",
        status_message=None,
        models=(),
    )

    response = api_client.post("/api/llm/provider-connections/openai/test")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"]["status"] == "available"
    assert service.probed == ["openai"]
    assert SECRET not in response.get_data(as_text=True)


def test_test_provider_connection_rejects_disabled_status_transition(api_client, lifecycle):
    store, _ = lifecycle
    store.connections["openai"] = _connection(enabled=False)

    response = api_client.post("/api/llm/provider-connections/openai/test")

    assert response.status_code == 409


def test_models_uses_canonical_probe_result_and_404s_for_unknown_connection(api_client, lifecycle):
    store, service = lifecycle
    store.connections["openai"] = _connection()
    service.result = ProviderProbeResult(
        status="available",
        status_message=None,
        models=(),
    )

    known = api_client.get("/api/llm/provider-connections/openai/models")
    unknown = api_client.get("/api/llm/provider-connections/missing/models")

    assert known.status_code == 200, known.get_json()
    assert known.get_json()["data"] == []
    assert unknown.status_code == 404


def test_legacy_models_route_delegates_to_connection_service(api_client, lifecycle):
    store, service = lifecycle
    store.connections["openai"] = _connection()

    response = api_client.get("/api/llm/providers/openai/models")

    assert response.status_code == 200, response.get_json()
    assert response.get_json()["data"] == []
    assert service.probed == ["openai"]
    assert response.headers["Deprecation"] == "@1784332800"
    assert response.headers["X-Agora-Removal-Version"] == "1.0.0"
    assert response.headers["Link"] == '</api/llm/provider-connections>; rel="successor-version"'


def test_legacy_opencode_route_is_unsupported_without_probe(api_client, lifecycle):
    _, service = lifecycle

    response = api_client.get("/api/llm/providers/opencode_go/models")

    assert response.status_code == 409
    assert response.get_json()["code"] == "provider_unsupported"
    assert service.probed == []


def test_legacy_api_key_rejects_non_lifecycle_base_url(api_client, lifecycle):
    response = api_client.put(
        "/api/llm/providers/openai/api-key",
        json={"api_key": SECRET, "base_url": "http://localhost:11434"},
    )

    assert response.status_code == 400
    assert SECRET not in response.get_data(as_text=True)
