"""Contract tests for embedding configuration, migration job and index version (Slice 4.1)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import get_args

import pytest
from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError as JsonSchemaValidationError
from pydantic import TypeAdapter, ValidationError

from app.contracts.embedding_contract import (
    EmbeddingConfiguration,
    EmbeddingConfigurationResponse,
    EmbeddingConfigurationScope,
    EmbeddingConfigurationStatus,
    EmbeddingConfigurationUpsertRequest,
    EmbeddingIndexStatus,
    EmbeddingIndexVersion,
    EmbeddingMigrationJob,
    EmbeddingMigrationJobResponse,
    EmbeddingMigrationProgress,
    EmbeddingMigrationStatus,
    EmbeddingModelMetadata,
    EmbeddingProviderKind,
    embedding_provider_kinds,
    provider_kind_supports_embeddings,
)

NOW = datetime(2026, 7, 12, 12, 0, tzinfo=timezone.utc)
REPO_ROOT = Path(__file__).resolve().parents[3]

CONTRACT_CASES: dict[str, tuple[TypeAdapter, Path]] = {
    "embedding-configuration": (
        TypeAdapter(EmbeddingConfiguration),
        REPO_ROOT / "schemas/embedding-configuration.schema.json",
    ),
    "embedding-configuration-upsert-request": (
        TypeAdapter(EmbeddingConfigurationUpsertRequest),
        REPO_ROOT / "schemas/embedding-configuration-upsert-request.schema.json",
    ),
    "embedding-configuration-response": (
        TypeAdapter(EmbeddingConfigurationResponse),
        REPO_ROOT / "schemas/embedding-configuration-response.schema.json",
    ),
    "embedding-migration-job": (
        TypeAdapter(EmbeddingMigrationJob),
        REPO_ROOT / "schemas/embedding-migration-job.schema.json",
    ),
    "embedding-migration-job-response": (
        TypeAdapter(EmbeddingMigrationJobResponse),
        REPO_ROOT / "schemas/embedding-migration-job-response.schema.json",
    ),
    "embedding-index-version": (
        TypeAdapter(EmbeddingIndexVersion),
        REPO_ROOT / "schemas/embedding-index-version.schema.json",
    ),
    "embedding-model-metadata": (
        TypeAdapter(EmbeddingModelMetadata),
        REPO_ROOT / "schemas/embedding-model-metadata.schema.json",
    ),
}


def _configuration_data(
    *,
    scope: EmbeddingConfigurationScope = "global",
    project_id: str | None = None,
    status: EmbeddingConfigurationStatus = "proposed",
    provider_kind: EmbeddingProviderKind = "ollama",
) -> dict:
    return {
        "id": "emb-1",
        "provider_connection_id": "conn-1",
        "provider_kind": provider_kind,
        "model_id": "nomic-embed-text",
        "dimensions": 768,
        "scope": scope,
        "project_id": project_id,
        "index_version": 1,
        "status": status,
        "status_message": None,
        "created_at": NOW.isoformat(),
        "updated_at": NOW.isoformat(),
        "last_validated_at": None,
    }


# ----------------------------------------------------------------------
# Konstruktion und Roundtrips
# ----------------------------------------------------------------------


def test_embedding_configuration_constructs_minimal_global() -> None:
    config = EmbeddingConfiguration(**_configuration_data())
    assert config.scope == "global"
    assert config.project_id is None
    assert config.provider_kind == "ollama"
    assert config.dimensions == 768
    assert config.status == "proposed"


def test_embedding_configuration_constructs_project_scope() -> None:
    config = EmbeddingConfiguration(
        **_configuration_data(scope="project", project_id="proj-1")
    )
    assert config.scope == "project"
    assert config.project_id == "proj-1"


def test_embedding_configuration_roundtrip_dict() -> None:
    config = EmbeddingConfiguration(**_configuration_data())
    raw = config.model_dump()
    again = EmbeddingConfiguration(**raw)
    assert again == config


# ----------------------------------------------------------------------
# extra="forbid"
# ----------------------------------------------------------------------


def test_embedding_configuration_rejects_unknown_fields() -> None:
    payload = _configuration_data()
    payload["unknown_field"] = "x"
    with pytest.raises(ValidationError):
        EmbeddingConfiguration(**payload)


def test_embedding_configuration_upsert_request_rejects_unknown_fields() -> None:
    payload = {
        "provider_connection_id": "conn-1",
        "provider_kind": "openai",
        "model_id": "text-embedding-3-small",
        "dimensions": 1536,
        "scope": "global",
        "project_id": None,
        "extra": "nope",
    }
    with pytest.raises(ValidationError):
        EmbeddingConfigurationUpsertRequest(**payload)


# ----------------------------------------------------------------------
# Scope-Konsistenz
# ----------------------------------------------------------------------


def test_embedding_configuration_rejects_project_scope_without_project_id() -> None:
    with pytest.raises(ValidationError, match="project_id"):
        EmbeddingConfiguration(**_configuration_data(scope="project", project_id=None))


def test_embedding_configuration_rejects_global_scope_with_project_id() -> None:
    with pytest.raises(ValidationError, match="project_id"):
        EmbeddingConfiguration(
            **_configuration_data(scope="global", project_id="proj-1")
        )


def test_embedding_configuration_upsert_request_enforces_scope_consistency() -> None:
    base = {
        "provider_connection_id": "conn-1",
        "provider_kind": "ollama",
        "model_id": "nomic-embed-text",
        "dimensions": 768,
    }
    with pytest.raises(ValidationError, match="project_id"):
        EmbeddingConfigurationUpsertRequest(**base, scope="project", project_id=None)
    with pytest.raises(ValidationError, match="project_id"):
        EmbeddingConfigurationUpsertRequest(
            **base, scope="global", project_id="proj-1"
        )


# ----------------------------------------------------------------------
# Provider-Restriktion (Anthropic, OpenCode-Go, etc.)
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "provider_kind",
    [
        "ollama",
        "openai",
        "google",
        "custom",
        "ollama_cloud",
        "openai_compatible",
    ],
)
def test_embedding_configuration_accepts_supported_provider_kinds(
    provider_kind: EmbeddingProviderKind,
) -> None:
    config = EmbeddingConfiguration(
        **_configuration_data(provider_kind=provider_kind)
    )
    assert config.provider_kind == provider_kind


@pytest.mark.parametrize(
    "provider_kind",
    ["anthropic", "opencode_go", "minimax", "github_copilot", "unknown"],
)
def test_embedding_configuration_rejects_unsupported_provider_kinds(
    provider_kind: str,
) -> None:
    with pytest.raises(ValidationError):
        EmbeddingConfiguration(
            **_configuration_data(provider_kind=provider_kind)  # type: ignore[arg-type]
        )


def test_provider_kind_supports_embeddings_helper() -> None:
    assert provider_kind_supports_embeddings("ollama") is True
    assert provider_kind_supports_embeddings("openai") is True
    assert provider_kind_supports_embeddings("google") is True
    assert provider_kind_supports_embeddings("custom") is True
    assert provider_kind_supports_embeddings("ollama_cloud") is True
    assert provider_kind_supports_embeddings("openai_compatible") is True
    assert provider_kind_supports_embeddings("anthropic") is False
    assert provider_kind_supports_embeddings("opencode_go") is False
    assert provider_kind_supports_embeddings("minimax") is False


def test_embedding_provider_kinds_helper_matches_literal() -> None:
    kinds = embedding_provider_kinds()
    assert kinds == frozenset(
        {
            "ollama",
            "openai",
            "google",
            "custom",
            "ollama_cloud",
            "openai_compatible",
        }
    )


# ----------------------------------------------------------------------
# Dimensions-Validierung
# ----------------------------------------------------------------------


@pytest.mark.parametrize("dimensions", [0, -1, -768])
def test_embedding_configuration_rejects_non_positive_dimensions(
    dimensions: int,
) -> None:
    payload = _configuration_data()
    payload["dimensions"] = dimensions
    with pytest.raises(ValidationError):
        EmbeddingConfiguration(**payload)


def test_embedding_model_metadata_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValidationError):
        EmbeddingModelMetadata(
            provider_kind="ollama",
            model_id="nomic-embed-text",
            display_name="Nomic Embed",
            embedding_dimensions=0,
            source="live",
        )


# ----------------------------------------------------------------------
# Status- und Lifecycle-Validierung
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "status",
    [
        "proposed",
        "probed",
        "reembedding",
        "validated",
        "active",
        "rolled_back",
        "failed",
    ],
)
def test_embedding_configuration_accepts_all_lifecycle_statuses(
    status: EmbeddingConfigurationStatus,
) -> None:
    config = EmbeddingConfiguration(**_configuration_data(status=status))
    assert config.status == status


def test_embedding_migration_job_rejects_identical_versions() -> None:
    with pytest.raises(ValidationError, match="must differ"):
        EmbeddingMigrationJob(
            id="job-1",
            configuration_id="emb-1",
            source_index_version=1,
            target_index_version=1,
            status="pending",
            progress=EmbeddingMigrationProgress(total=0, processed=0, failed=0),
            error_message=None,
            created_at=NOW,
            updated_at=NOW,
        )


def test_embedding_migration_job_accepts_distinct_versions() -> None:
    job = EmbeddingMigrationJob(
        id="job-1",
        configuration_id="emb-1",
        source_index_version=1,
        target_index_version=2,
        status="running",
        progress=EmbeddingMigrationProgress(
            total=100, processed=42, failed=0, started_at=NOW
        ),
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert job.source_index_version == 1
    assert job.target_index_version == 2
    assert job.status == "running"


@pytest.mark.parametrize(
    "status",
    [
        "pending",
        "running",
        "validating",
        "completed",
        "rolled_back",
        "failed",
    ],
)
def test_embedding_migration_job_accepts_all_lifecycle_statuses(
    status: EmbeddingMigrationStatus,
) -> None:
    job = EmbeddingMigrationJob(
        id="job-1",
        configuration_id="emb-1",
        source_index_version=1,
        target_index_version=2,
        status=status,
        progress=EmbeddingMigrationProgress(total=0, processed=0, failed=0),
        error_message=None,
        created_at=NOW,
        updated_at=NOW,
    )
    assert job.status == status


# ----------------------------------------------------------------------
# Index-Version
# ----------------------------------------------------------------------


def test_embedding_index_version_requires_retired_at_when_retired() -> None:
    with pytest.raises(ValidationError, match="retired_at"):
        EmbeddingIndexVersion(
            version=1,
            provider_connection_id="conn-1",
            model_id="nomic-embed-text",
            dimensions=768,
            index_name="entity_embedding_v1",
            property_key="embedding_v1",
            status="retired",
            created_at=NOW,
            retired_at=None,
        )


@pytest.mark.parametrize(
    "status",
    ["active", "superseded", "rolled_back", "retired"],
)
def test_embedding_index_version_accepts_all_statuses(
    status: EmbeddingIndexStatus,
) -> None:
    retired_at = NOW if status == "retired" else None
    version = EmbeddingIndexVersion(
        version=1,
        provider_connection_id="conn-1",
        model_id="nomic-embed-text",
        dimensions=768,
        index_name="entity_embedding_v1",
        property_key="embedding_v1",
        status=status,
        created_at=NOW,
        retired_at=retired_at,
    )
    assert version.status == status


@pytest.mark.parametrize("status", ["active", "superseded", "rolled_back"])
def test_embedding_index_version_rejects_retired_at_for_non_retired_status(
    status: EmbeddingIndexStatus,
) -> None:
    """Gemini-Finding (MEDIUM): ``retired_at`` darf nur gesetzt sein,
    wenn der Status tatsaechlich ``'retired'`` ist. Sonst entstehen
    zustaende, in denen ein aktiver Index ein Retirement-Datum haette.
    """
    with pytest.raises(ValidationError, match="retired_at"):
        EmbeddingIndexVersion(
            version=1,
            provider_connection_id="conn-1",
            model_id="nomic-embed-text",
            dimensions=768,
            index_name="entity_embedding_v1",
            property_key="embedding_v1",
            status=status,
            created_at=NOW,
            retired_at=NOW,
        )


def test_embedding_migration_progress_rejects_finished_at_without_started_at() -> None:
    """Gemini-Finding (MEDIUM): ``finished_at`` ohne ``started_at`` ist ein
    klarer Vertragsbruch — ein Job kann nicht enden, ohne je begonnen
    zu haben.
    """
    with pytest.raises(ValidationError, match="started_at"):
        EmbeddingMigrationProgress(
            total=10, processed=10, failed=0, started_at=None, finished_at=NOW
        )


def test_embedding_migration_progress_rejects_finished_at_before_started_at() -> None:
    with pytest.raises(ValidationError, match="finished_at"):
        EmbeddingMigrationProgress(
            total=10,
            processed=10,
            failed=0,
            started_at=NOW,
            finished_at=NOW.replace(year=NOW.year - 1),
        )


def test_embedding_migration_progress_accepts_consistent_timestamps() -> None:
    later = NOW.replace(year=NOW.year + 1)
    progress = EmbeddingMigrationProgress(
        total=10, processed=10, failed=0, started_at=NOW, finished_at=later
    )
    assert progress.started_at == NOW
    assert progress.finished_at == later


def test_embedding_migration_progress_accepts_running_state_with_no_finish() -> None:
    """Waehrend ``running`` ist ``finished_at`` None — das ist erlaubt und
    der haeufigste Fall. Der Test pinnt, dass der neue Validator den
    Normalfall nicht verschlechtert.
    """
    progress = EmbeddingMigrationProgress(
        total=100, processed=42, failed=0, started_at=NOW, finished_at=None
    )
    assert progress.finished_at is None


def test_embedding_migration_progress_last_processed_id_defaults_to_none() -> None:
    """Slice 4.3.4: ``last_processed_id`` ist der Resume-Cursor der
    Re-Embedding-Engine. Default None (frischer Job); persistierte
    Alt-Jobs ohne das Feld bleiben ladbar.
    """
    progress = EmbeddingMigrationProgress(total=0, processed=0, failed=0)
    assert progress.last_processed_id is None

    legacy_payload = '{"total": 5, "processed": 5, "failed": 0, "started_at": null, "finished_at": null}'
    parsed = EmbeddingMigrationProgress.model_validate_json(legacy_payload)
    assert parsed.last_processed_id is None


def test_embedding_migration_progress_last_processed_id_roundtrip() -> None:
    progress = EmbeddingMigrationProgress(
        total=10, processed=4, failed=1, last_processed_id="uuid-003"
    )
    restored = EmbeddingMigrationProgress.model_validate_json(
        progress.model_dump_json()
    )
    assert restored.last_processed_id == "uuid-003"


def test_embedding_provider_kinds_helper_is_derived_from_literal() -> None:
    """Gemini-Finding (MEDIUM): das ``_EMBEDDING_PROVIDER_KINDS``-Set muss
    dynamisch aus dem ``EmbeddingProviderKind``-Literal abgeleitet sein,
    damit es nicht zu Drift zwischen Vertrag und Laufzeit kommen kann.
    """
    kinds = embedding_provider_kinds()
    assert kinds == frozenset(get_args(EmbeddingProviderKind))


# ----------------------------------------------------------------------
# JSON-Schema-Validation
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "case_key", sorted(CONTRACT_CASES.keys())
)
def test_contract_schemas_validate_against_generated_jsonschema(
    case_key: str,
) -> None:
    adapter, schema_path = CONTRACT_CASES[case_key]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)

    if case_key == "embedding-configuration":
        instance = EmbeddingConfiguration(**_configuration_data())
    elif case_key == "embedding-configuration-upsert-request":
        instance = EmbeddingConfigurationUpsertRequest(
            provider_connection_id="conn-1",
            provider_kind="openai",
            model_id="text-embedding-3-small",
            dimensions=1536,
            scope="global",
            project_id=None,
        )
    elif case_key == "embedding-configuration-response":
        instance = EmbeddingConfigurationResponse(
            configuration=EmbeddingConfiguration(**_configuration_data())
        )
    elif case_key == "embedding-migration-job":
        instance = EmbeddingMigrationJob(
            id="job-1",
            configuration_id="emb-1",
            source_index_version=1,
            target_index_version=2,
            status="pending",
            progress=EmbeddingMigrationProgress(total=0, processed=0, failed=0),
            error_message=None,
            created_at=NOW,
            updated_at=NOW,
        )
    elif case_key == "embedding-migration-job-response":
        instance = EmbeddingMigrationJobResponse(
            job=EmbeddingMigrationJob(
                id="job-1",
                configuration_id="emb-1",
                source_index_version=1,
                target_index_version=2,
                status="pending",
                progress=EmbeddingMigrationProgress(
                    total=0, processed=0, failed=0
                ),
                error_message=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
    elif case_key == "embedding-index-version":
        instance = EmbeddingIndexVersion(
            version=1,
            provider_connection_id="conn-1",
            model_id="nomic-embed-text",
            dimensions=768,
            index_name="entity_embedding_v1",
            property_key="embedding_v1",
            status="active",
            created_at=NOW,
            retired_at=None,
        )
    elif case_key == "embedding-model-metadata":
        instance = EmbeddingModelMetadata(
            provider_kind="ollama",
            model_id="nomic-embed-text",
            display_name="Nomic Embed",
            embedding_dimensions=768,
            source="live",
        )
    else:  # pragma: no cover — defensive
        raise AssertionError(f"Unhandled case_key: {case_key}")

    validator.validate(instance.model_dump(mode="json"))


@pytest.mark.parametrize(
    "case_key", sorted(CONTRACT_CASES.keys())
)
def test_contract_schemas_reject_unknown_fields_via_jsonschema(
    case_key: str,
) -> None:
    _, schema_path = CONTRACT_CASES[case_key]
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    instance: dict = {"this_should_not_be_allowed": "x"}
    with pytest.raises(JsonSchemaValidationError):
        validator.validate(instance)
