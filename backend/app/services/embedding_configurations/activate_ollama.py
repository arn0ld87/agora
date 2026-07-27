"""Activate Ollama embedding configuration (Issue #934).

Helper that pins the active ``EmbeddingConfiguration`` to a local Ollama
model (default: ``embeddinggemma:300m`` / 768-dim). Idempotent: repeated
calls converge to the same state.

Read/write paths are exclusively routed through
``EmbeddingConfigurationStore`` and ``ProviderConnectionStore`` — no
direct file or database writes, no raw Cypher. This honours the Single
Source of Truth rules from ADR-0007.

Out of scope (deliberate):

* Gemini re-embedding is *not* supported (ADR-0007). This helper only
  pins the configuration metadata; data migration from 3072-dim
  (Gemini) vectors to 768-dim (Ollama) vectors is a separate effort.
* The runtime ``Config.EMBEDDING_BASE_URL`` (e.g.
  ``http://host.docker.internal:11434``) is honoured at request time
  by ``EmbeddingService``. The persisted ``ProviderConnection`` carries
  structural metadata only and must use a loopback URL per the
  ``LocalOllamaBaseUrl`` validator — the runtime URL is resolved at
  embed-call time, not from the store.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Optional

from app.contracts.ai_provider_contract import (
    LocalOllamaBaseUrl,
    ProviderConnection,
    ProviderConnectionUpsertRequest,
)
from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationScope,
)
from app.services.embedding_configuration_store import EmbeddingConfigurationStore
from app.services.embedding_configurations.service import EmbeddingConfigurationService
from app.services.llm_provider_secrets_store import LlmProviderSecretsStore
from app.services.provider_connection_store import ProviderConnectionStore


# Default-Werte entsprechen dem Hotfix (.env) vom 2026-07-27:
# ``EMBEDDING_MODEL=embeddinggemma:300m``, ``VECTOR_DIM=768``.
DEFAULT_OLLAMA_MODEL = "embeddinggemma:300m"
DEFAULT_OLLAMA_DIMENSIONS = 768
DEFAULT_OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_OLLAMA_DISPLAY_NAME = "Local Ollama (embedding)"
DEFAULT_PROVIDER_KIND = "ollama"


def _find_existing_configuration(
    *,
    configuration_store: EmbeddingConfigurationStore,
    provider_connection_id: str,
    model_id: str,
    dimensions: int,
    scope: EmbeddingConfigurationScope,
    project_id: Optional[str],
) -> Optional[EmbeddingConfiguration]:
    """Sucht eine bestehende Konfiguration mit passendem Fingerabdruck.

    Identitaetsmerkmal: ``(provider_connection_id, model_id, dimensions,
    scope, project_id)``. Liefert ``None``, wenn keine solche Konfiguration
    existiert; sonst den ersten Treffer.
    """
    for existing in configuration_store.list_configurations(scope=scope):
        if (
            existing.provider_connection_id == provider_connection_id
            and existing.model_id == model_id
            and existing.dimensions == dimensions
            and existing.project_id == project_id
        ):
            return existing
    return None


def _ensure_provider_connection(
    *,
    provider_kind: str,
    display_name: str,
    base_url: str,
    connection_store: ProviderConnectionStore,
) -> ProviderConnection:
    """Stellt sicher, dass eine ``ProviderConnection`` mit der gewuenschten
    ``provider_kind`` existiert. Bei ``provider_kind='ollama'`` wird die
    ``base_url`` durch ``LocalOllamaBaseUrl`` validiert (Loopback-pflicht).
    """
    validated_base_url: LocalOllamaBaseUrl | None
    if provider_kind == "ollama":
        validated_base_url = LocalOllamaBaseUrl(base_url)
    else:
        # Andere Provider-Kinds werden ueber ``ProviderConnection``-
        # Default-Validierung (PublicBaseUrl) gefuehrt; fuer diesen
        # Issue-Scope (nur Ollama) bleibt das ein defensiver Default.
        validated_base_url = None  # type: ignore[assignment]
    request = ProviderConnectionUpsertRequest(
        provider_kind=provider_kind,  # type: ignore[arg-type]
        display_name=display_name,
        base_url=(
            base_url if provider_kind != "ollama" else str(validated_base_url)
        ),
        enabled=True,
    )
    return connection_store.upsert_connection(request)


def activate_ollama_embedding(
    *,
    model_id: str = DEFAULT_OLLAMA_MODEL,
    dimensions: int = DEFAULT_OLLAMA_DIMENSIONS,
    base_url: str = DEFAULT_OLLAMA_BASE_URL,
    display_name: str = DEFAULT_OLLAMA_DISPLAY_NAME,
    provider_kind: str = DEFAULT_PROVIDER_KIND,
    scope: EmbeddingConfigurationScope = "global",
    project_id: Optional[str] = None,
    configuration_id: Optional[str] = None,
    configuration_store: EmbeddingConfigurationStore,
    connection_store: Optional[ProviderConnectionStore] = None,
    secrets_store: Optional[LlmProviderSecretsStore] = None,
    now: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> EmbeddingConfiguration:
    """Pin the active embedding configuration to a local Ollama endpoint.

    Vorgehen (idempotent):

    1. ``ProviderConnection`` mit ``provider_kind='ollama'`` sicherstellen
       (anlegen, falls noch nicht vorhanden).
    2. Existierende ``EmbeddingConfiguration`` mit passendem Fingerabdruck
       suchen und wiederverwenden, sonst neu anlegen.
    3. Ueber ``EmbeddingConfigurationService.activate`` aktivieren.
       Vorhandene aktive Konfigurationen des gleichen Scopes werden
       auf ``status='rolled_back'`` gesetzt (Audit-Trail — Knoten
       bleibt erhalten, nicht geloescht).

    Liefert die aktivierte ``EmbeddingConfiguration`` zurueck.
    """
    if connection_store is None:
        connection_store = ProviderConnectionStore()
    if secrets_store is None:
        secrets_store = LlmProviderSecretsStore()

    connection = _ensure_provider_connection(
        provider_kind=provider_kind,
        display_name=display_name,
        base_url=base_url,
        connection_store=connection_store,
    )

    target_id = configuration_id
    if target_id is None:
        existing = _find_existing_configuration(
            configuration_store=configuration_store,
            provider_connection_id=connection.id,
            model_id=model_id,
            dimensions=dimensions,
            scope=scope,
            project_id=project_id,
        )
        if existing is not None:
            target_id = existing.id

    config = configuration_store.upsert_configuration(
        configuration_id=target_id,
        provider_connection_id=connection.id,
        provider_kind=provider_kind,  # type: ignore[arg-type]
        model_id=model_id,
        dimensions=dimensions,
        scope=scope,
        project_id=project_id,
        status="proposed",
        status_message="Issue #934: pinning to local Ollama (pending probe)",
    )

    service = EmbeddingConfigurationService(
        store=configuration_store,
        connection_store=connection_store,
        secrets_store=secrets_store,
        now=now,
    )
    return service.activate(config.id)


__all__ = [
    "activate_ollama_embedding",
    "DEFAULT_OLLAMA_MODEL",
    "DEFAULT_OLLAMA_DIMENSIONS",
    "DEFAULT_OLLAMA_BASE_URL",
    "DEFAULT_OLLAMA_DISPLAY_NAME",
    "DEFAULT_PROVIDER_KIND",
]
