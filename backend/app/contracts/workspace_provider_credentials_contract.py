"""Workspace-scoped provider credential API contracts.

The request contains a third-party secret. Responses expose only presence and
timestamps; a provider credential must never be returned to the browser.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, SecretStr


class WorkspaceProviderCredentialUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    api_key: SecretStr = Field(min_length=4, max_length=1024)


class WorkspaceProviderCredentialStatus(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider_id: str = Field(min_length=1, max_length=64)
    configured: bool
    updated_at: datetime | None = None


class WorkspaceProviderCredentialsList(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[WorkspaceProviderCredentialStatus]
    total: int = Field(ge=0)
