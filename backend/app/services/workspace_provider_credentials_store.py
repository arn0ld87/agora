"""Encrypted provider keys isolated by workspace ID.

This store deliberately has no operator-key fallback. Callers must pass a
workspace UUID obtained from a verified principal or persisted run context.
"""

from __future__ import annotations

from pathlib import Path
from uuid import UUID

from ..contracts.workspace_provider_credentials_contract import (
    WorkspaceProviderCredentialStatus,
)
from .data_dir import resolve_data_dir
from .llm_provider_secrets_store import LlmProviderSecretsStore


class WorkspaceProviderCredentialsStore:
    def __init__(self, *, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or resolve_data_dir()

    def _store(self, workspace_id: UUID) -> LlmProviderSecretsStore:
        if not isinstance(workspace_id, UUID):
            raise TypeError("workspace_id must be a UUID")
        return LlmProviderSecretsStore(
            data_dir=self._data_dir / "workspace_provider_credentials" / str(workspace_id)
        )

    def list_entries(self, workspace_id: UUID) -> list[WorkspaceProviderCredentialStatus]:
        return [
            WorkspaceProviderCredentialStatus(
                provider_id=entry.provider_id,
                configured=True,
                updated_at=entry.updated_at,
            )
            for entry in self._store(workspace_id).list_entries()
        ]

    def get_plaintext(self, workspace_id: UUID, provider_id: str) -> str | None:
        return self._store(workspace_id).get_plaintext(provider_id)

    def upsert(
        self, workspace_id: UUID, provider_id: str, *, api_key: str
    ) -> WorkspaceProviderCredentialStatus:
        entry = self._store(workspace_id).upsert(provider_id, api_key=api_key)
        return WorkspaceProviderCredentialStatus(
            provider_id=provider_id, configured=True, updated_at=entry.updated_at
        )

    def delete(self, workspace_id: UUID, provider_id: str) -> bool:
        return self._store(workspace_id).delete(provider_id)
