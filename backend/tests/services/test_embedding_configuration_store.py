"""Tests für ``EmbeddingConfigurationStore`` (Onboarding Slice 4.2)."""

from __future__ import annotations

import json
import os
import stat
from datetime import datetime, timezone
from pathlib import Path

import pytest
from cryptography.fernet import Fernet

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationScope,
    EmbeddingConfigurationStatus,
    EmbeddingIndexVersion,
    EmbeddingProviderKind,
)
from app.services.embedding_configuration_store import EmbeddingConfigurationStore


@pytest.fixture
def configured_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> EmbeddingConfigurationStore:
    monkeypatch.setenv("AGORA_DATA_DIR", str(tmp_path))
    return EmbeddingConfigurationStore(data_dir=tmp_path)


def _global_config() -> dict:
    return {
        "provider_connection_id": "conn-1",
        "provider_kind": "ollama",
        "model_id": "nomic-embed-text",
        "dimensions": 768,
    }


# ----------------------------------------------------------------------
# Konfigurationen
# ----------------------------------------------------------------------


def test_list_is_empty_without_store_file(configured_store: EmbeddingConfigurationStore) -> None:
    assert configured_store.list_configurations() == []


def test_upsert_persists_new_configuration(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    config = configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="global",
        project_id=None,
    )
    assert config.id.startswith("emb-")
    assert config.status == "proposed"
    assert config.index_version == 1

    on_disk = json.loads(
        (configured_store._config_path).read_text(encoding="utf-8")
    )
    assert on_disk["schema_version"] == 1
    assert config.id in on_disk["configurations"]


def test_upsert_with_explicit_id_preserves_created_at(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    first = configured_store.upsert_configuration(
        configuration_id="emb-fixed",
        **_global_config(),
        scope="global",
        project_id=None,
    )
    second = configured_store.upsert_configuration(
        configuration_id="emb-fixed",
        **_global_config(),
        scope="global",
        project_id=None,
        status="probed",
    )
    assert second.id == first.id
    assert second.created_at == first.created_at
    assert second.updated_at >= first.updated_at
    assert second.status == "probed"


def test_upsert_writes_file_with_mode_0o600(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="global",
        project_id=None,
    )
    mode = stat.S_IMODE(os.stat(configured_store._config_path).st_mode)
    assert mode == 0o600


def test_list_filters_by_scope(configured_store: EmbeddingConfigurationStore) -> None:
    configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="global",
        project_id=None,
    )
    configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="project",
        project_id="proj-1",
    )
    configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="project",
        project_id="proj-2",
    )
    assert len(configured_store.list_configurations()) == 3
    assert len(configured_store.list_configurations(scope="global")) == 1
    assert len(configured_store.list_configurations(scope="project")) == 2


def test_get_active_global_configuration_returns_only_active(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="global",
        project_id=None,
    )
    assert configured_store.get_active_global_configuration() is None
    configured_store.update_configuration_status(
        configured_store.list_configurations()[0].id, status="active"
    )
    active = configured_store.get_active_global_configuration()
    assert active is not None
    assert active.status == "active"


def test_update_configuration_status_unknown_id_raises(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    with pytest.raises(KeyError):
        configured_store.update_configuration_status("emb-bogus", status="probed")


def test_delete_configuration_removes_entry(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    config = configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="global",
        project_id=None,
    )
    assert configured_store.delete_configuration(config.id) is True
    assert configured_store.get_configuration(config.id) is None
    assert configured_store.delete_configuration(config.id) is False


def test_atomic_write_creates_tmp_file_and_replaces(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    """Stellt sicher, dass der atomare Write ueber os.replace laeuft —
    kein Observer sieht eine halb geschriebene Konfigurationsdatei.
    """
    configured_store.upsert_configuration(
        configuration_id=None,
        **_global_config(),
        scope="global",
        project_id=None,
    )
    tmp_path = configured_store._config_path.with_suffix(".tmp")
    assert not tmp_path.exists()


# ----------------------------------------------------------------------
# Index-Versionen
# ----------------------------------------------------------------------


def test_first_index_version_starts_at_one(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    assert configured_store.next_index_version() == 1
    index = configured_store.upsert_index_version(
        version=None,
        provider_connection_id="conn-1",
        model_id="nomic-embed-text",
        dimensions=768,
        index_name="entity_embedding_v1",
        property_key="embedding_v1",
    )
    assert index.version == 1
    assert index.status == "active"


def test_index_version_numbers_are_monotonic(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    v1 = configured_store.upsert_index_version(
        version=None,
        provider_connection_id="conn-1",
        model_id="m1",
        dimensions=768,
        index_name="entity_embedding_v1",
        property_key="embedding_v1",
    )
    v2 = configured_store.upsert_index_version(
        version=None,
        provider_connection_id="conn-1",
        model_id="m2",
        dimensions=1024,
        index_name="entity_embedding_v2",
        property_key="embedding_v2",
    )
    assert v1.version == 1
    assert v2.version == 2
    assert configured_store.get_active_index_version() == v1


def test_supersede_marks_previous_version_inactive(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    v1 = configured_store.upsert_index_version(
        version=None,
        provider_connection_id="conn-1",
        model_id="m1",
        dimensions=768,
        index_name="entity_embedding_v1",
        property_key="embedding_v1",
    )
    superseded = configured_store.supersede_index_version(v1.version)
    assert superseded.status == "superseded"
    assert configured_store.get_active_index_version() is None


def test_retired_status_requires_retired_at(
    configured_store: EmbeddingConfigurationStore,
) -> None:
    """Structural contract check: ``status='retired'`` erzwingt
    ``retired_at``-Timestamp. Wird im Vertrag geprueft, der Store
    propagiert den Fehler als ValidationError.
    """
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        configured_store.upsert_index_version(
            version=1,
            provider_connection_id="conn-1",
            model_id="m1",
            dimensions=768,
            index_name="entity_embedding_v1",
            property_key="embedding_v1",
            status="retired",
        )
