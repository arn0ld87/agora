"""Orchestriert Probe-Ergebnisse ohne Secret-Werte zu persistieren oder zu loggen."""
from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone

from app.contracts.ai_provider_contract import ProviderConnection, ProviderStatus
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore

from .adapters import ProviderConnectionAdapter, ProviderProbeResult, adapter_for_connection

_STORE_STATUS: dict[str, ProviderStatus] = {
    "available": "connected",
    "unavailable": "disconnected",
    "invalid_credentials": "error",
    "degraded": "degraded",
    "unsupported": "error",
}


class ProviderConnectionService:
    """Fuehrt die kanonische Probe aus und persistiert nur Metadaten."""

    def __init__(
        self,
        *,
        store: ProviderConnectionStore,
        secrets_store: LlmProviderSecretsStore,
        adapter_factory: Callable[[str], ProviderConnectionAdapter] = adapter_for_connection,
        now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._store = store
        self._secrets_store = secrets_store
        self._adapter_factory = adapter_factory
        self._now = now

    def probe(self, connection: ProviderConnection) -> ProviderProbeResult:
        api_key = (
            self._secrets_store.get_plaintext(connection.secret_ref)
            if connection.secret_ref
            else None
        )
        result = self._adapter_factory(connection.provider_kind).probe(connection, api_key)
        self._store.update_probe(
            connection.id,
            status=_STORE_STATUS[result.status],
            status_message=result.status_message,
            tested_at=self._now(),
        )
        return result
