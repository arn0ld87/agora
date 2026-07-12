"""Provider-connection service tests."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.contracts.ai_provider_contract import ProviderConnection
from app.services.provider_connections.adapters import ProviderProbeResult
from app.services.provider_connections.service import ProviderConnectionService


class _Store:
    def __init__(self, connection: ProviderConnection) -> None:
        self.connection = connection
        self.updated: dict[str, object] | None = None

    def update_probe(self, connection_id: str, **kwargs: object) -> ProviderConnection:
        self.updated = {"connection_id": connection_id, **kwargs}
        return self.connection


class _Secrets:
    def get_plaintext(self, provider_id: str) -> str | None:
        assert provider_id == "openai"
        return "secret-value"


def _connection() -> ProviderConnection:
    return ProviderConnection(
        id="openai",
        provider_kind="openai",
        display_name="OpenAI",
        transport="http",
        auth_mode="api_key",
        base_url="https://api.openai.com/v1",
        secret_ref="openai",
    )


@pytest.mark.parametrize(
    ("probe_status", "stored_status"),
    [
        ("available", "connected"),
        ("unavailable", "disconnected"),
        ("invalid_credentials", "error"),
        ("degraded", "degraded"),
        ("unsupported", "error"),
    ],
)
def test_probe_persists_normalized_result_without_secret(
    probe_status: str, stored_status: str
) -> None:
    store = _Store(_connection())
    service = ProviderConnectionService(
        store=store,
        secrets_store=_Secrets(),
        adapter_factory=lambda _kind: _Adapter(
            ProviderProbeResult(status=probe_status, status_message="normalized")
        ),
        now=lambda: datetime(2026, 7, 12, tzinfo=timezone.utc),
    )

    result = service.probe(_connection())

    assert result.status == probe_status
    assert store.updated == {
        "connection_id": "openai",
        "status": stored_status,
        "status_message": "normalized",
        "tested_at": datetime(2026, 7, 12, tzinfo=timezone.utc),
    }


class _Adapter:
    def __init__(self, result: ProviderProbeResult) -> None:
        self._result = result

    def probe(
        self, connection: ProviderConnection, api_key: str | None
    ) -> ProviderProbeResult:
        assert connection.id == "openai"
        assert api_key == "secret-value"
        return self._result
