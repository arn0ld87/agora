"""Seed secret-free provider metadata for a fresh, isolated public demo.

Run once inside the demo backend container after the private data volume exists.
The script refuses any pre-existing operator secret or non-canonical connection.
"""

from __future__ import annotations

from app.contracts.ai_provider_contract import ProviderConnectionUpsertRequest
from app.contracts.llm_routing_contract import StageLLMRoute
from app.services.llm_provider_registry import LlmProviderRegistry
from app.services.provider_connection_store import ProviderConnectionStore
from app.services.workspace_routing_store import WorkspaceRoutingStore
from app.utils.logger import get_logger

logger = get_logger("agora.bootstrap_public_demo_providers")

_PROVIDERS = ("openai", "google", "minimax")


def bootstrap_public_demo_providers() -> None:
    store = ProviderConnectionStore()
    existing = {connection.id: connection for connection in store.list_connections()}
    if set(existing) - set(_PROVIDERS):
        raise RuntimeError("public demo provider store contains an unexpected connection")
    for provider_id in _PROVIDERS:
        definition = LlmProviderRegistry.connection_definition(provider_id)
        if definition is None or definition.default_base_url is None:
            raise RuntimeError(f"provider definition unavailable: {provider_id}")
        current = existing.get(provider_id)
        if current and (current.secret_ref or current.base_url != definition.default_base_url):
            raise RuntimeError(f"public demo provider is not secret-free and canonical: {provider_id}")
        if current is None:
            store.upsert_connection(ProviderConnectionUpsertRequest(
                provider_kind=provider_id,
                display_name=definition.display_name,
                base_url=definition.default_base_url,
            ))

    routing = WorkspaceRoutingStore()
    if routing.load().global_default.provider_id is None:
        routing.set_global_default(StageLLMRoute(provider_id="openai", model="gpt-4o-mini"))
    logger.info("public demo provider metadata ready: providers=%s", ",".join(_PROVIDERS))


if __name__ == "__main__":
    bootstrap_public_demo_providers()
